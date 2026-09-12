"""Offline tests only: all process, TLS and OS boundaries are mocked."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from alpha_market_baseline import radar_plan
from alpha_session_execution import execute_schedule
from opportunity_spine_contract import schedule
from provider_gateway_contract import canonical, content_hash, utc
from provider_gateway_https import Response
from truth_spine_process_identity import ProcessObservation
from alpha_radar_admission import (admit, AUTHORITY, SCOPE, envelope, verify_envelope, store,
                                   verify_inputs, exact_root)
from alpha_radar_runner import Session, OwnedProcesses, fixture_exchange, listener_owners, require_confinement
from alpha_radar_fixture import response

CALENDAR = {'calendar': 'XNYS', 'session': '2026-09-14',
            'open': '2026-09-14T13:30:00+00:00', 'close': '2026-09-14T20:00:00+00:00'}


def fixture():
    root = Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
    case = Path(tempfile.mkdtemp(prefix='native-case-', dir=root))
    runtime = case / 'runtime'
    runtime.mkdir(mode=0o700)
    files = {'python': b'SYNTHETIC_INTERPRETER_NOT_EXECUTED', 'tls.pem': b'SYNTHETIC_TLS',
             'fixture-key.pem': b'SYNTHETIC_TLS_KEY_NOT_A_PROVIDER_CREDENTIAL',
             'policy.sb': b'(version 1)\n(deny default)\n',
             'responses.json': canonical({'scope': SCOPE, 'faults': {}})}
    sources = ['alpha_session_execution.py', 'provider_gateway_https.py', 'alpha_market_baseline.py',
        'opportunity_spine_contract.py', 'provider_gateway_contract.py', 'truth_spine_contract.py',
        'truth_spine_process_identity.py', 'alpha_radar_admission.py', 'alpha_radar_runner.py',
        'alpha_radar_fixture.py', 'alpha_radar.sb.in', 'alpha_session_readiness.py']
    files.update({n: b'SYNTHETIC_RUNTIME_INPUT_NOT_EXECUTED\n' for n in sources})
    rows = []
    for name, data in files.items():
        path = runtime / name
        path.write_bytes(data)
        mode = 0o500 if name == 'python' else 0o400
        path.chmod(mode)
        rows.append({'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode})
    runtime.chmod(0o500)
    r = {'scope': SCOPE, 'source_commit': 'a'*40, 'root': str(runtime), 'files': rows,
         'interpreter': 'python', 'tls': 'tls.pem', 'source_files': sources, 'confinement': 'policy.sb'}
    out = case / 'output'
    universe = {'symbols': [f'S{i:03}' for i in range(517)]}
    proposal = schedule(universe, content_hash(universe), CALENDAR, content_hash(CALENDAR),
                        mode='FULL_OPPORTUNITY_RADAR', root=str(out/'journal'))
    plan = radar_plan(universe, content_hash(universe), CALENDAR, content_hash(CALENDAR),
                      root=str(out/'journal'), opportunity_schedule=proposal, schedule_hash=content_hash(proposal))
    f = {'scope': SCOPE, 'address': '127.0.0.1', 'port': 38491, 'server_name': '127.0.0.1',
         'certificate': 'tls.pem', 'certificate_sha256': hashlib.sha256(files['tls.pem']).hexdigest(),
         'private_key': 'fixture-key.pem', 'responses': 'responses.json',
         'responses_sha256': hashlib.sha256(files['responses.json']).hexdigest()}
    p = {'schema': 'iios-alpha-radar-synthetic-package-v1', 'scope': SCOPE, 'source_commit': 'a'*40,
         'runtime_parent': content_hash(r), 'plan': plan, 'plan_parent': content_hash(plan),
         'fixture': f, 'fixture_parent': content_hash(f),
         'confinement_parent': hashlib.sha256(files['policy.sb']).hexdigest(), 'root': str(out), 'authority': AUTHORITY}
    expected = {'package': content_hash(p), 'runtime': content_hash(r), 'plan': content_hash(plan),
                'universe': content_hash(universe), 'schedule': content_hash(proposal),
                'fixture': content_hash(f), 'confinement': p['confinement_parent']}
    return root, p, r, expected


def repin(p, r, pins):
    p.update(runtime_parent=content_hash(r), plan_parent=content_hash(p['plan']), fixture_parent=content_hash(p['fixture']))
    pins.update(package=content_hash(p), runtime=content_hash(r), plan=content_hash(p['plan']), fixture=content_hash(p['fixture']))


class AdmissionTests(unittest.TestCase):
    def test_valid_admission_and_duplicate_output_rejection(self):
        root,p,r,e=fixture()
        cap=admit(p,r,expected=e,authorized_root=root)
        self.assertEqual(cap.recheck()[0],p)
        with self.assertRaises(FileExistsError):admit(p,r,expected=e,authorized_root=root)

    def test_independent_missing_or_wrong_pin(self):
        for key in ('package','runtime','plan','universe','schedule','fixture','confinement'):
            root,p,r,e=fixture();e.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):admit(p,r,expected=e,authorized_root=root)
            self.assertFalse(Path(p['root']).exists())

    def test_public_address_and_dns_names_rejected(self):
        for address in ('8.8.8.8','localhost','192.0.2.1','::1','127.0.0.2'):
            root,p,r,e=fixture();p['fixture']['address']=address;repin(p,r,e)
            with self.subTest(address=address), self.assertRaises(ValueError):admit(p,r,expected=e,authorized_root=root)
            self.assertFalse(Path(p['root']).exists())

    def test_selectors_rejected_before_creation(self):
        for field,value in [('selectors',[]),('service','IIOS_ALPHA_VANTAGE_API_KEY'),('account','iios-provider')]:
            root,p,r,e=fixture();p[field]=value;repin(p,r,e)
            with self.assertRaises(ValueError):admit(p,r,expected=e,authorized_root=root)
            self.assertFalse(Path(p['root']).exists())

    def test_scope_and_authority_rejected(self):
        for mutate in (lambda p:p.update(scope='LIVE_QUALIFICATION'),
                       lambda p:p.update(authority={**AUTHORITY,'live_execution':True})):
            root,p,r,e=fixture();mutate(p);repin(p,r,e)
            with self.assertRaises(ValueError):admit(p,r,expected=e,authorized_root=root)

    def test_arbitrary_tmp_and_protected_paths_rejected_without_access(self):
        root,p,r,e=fixture()
        for target in ('/private/tmp/unregistered','/Library/Application Support/IIOS', '/Library/Keychains'):
            with self.assertRaises(ValueError):exact_root(target)

    def test_runtime_tamper_and_inode_substitution(self):
        for operation in ('bytes','inode','symlink','hardlink','extra'):
            root,p,r,e=fixture();cap=admit(p,r,expected=e,authorized_root=root)
            runtime=Path(r['root']);runtime.chmod(0o700);target=runtime/'tls.pem'
            if operation=='bytes':target.chmod(0o600);target.write_bytes(b'ALTERED');target.chmod(0o400)
            elif operation=='inode':
                other=runtime/'replacement';other.write_bytes(target.read_bytes());other.chmod(0o400);other.replace(target)
            elif operation=='symlink':
                target.rename(runtime/'original');target.symlink_to(runtime/'original')
            elif operation=='hardlink':os.link(target,runtime/'alias')
            else:(runtime/'extra').write_bytes(b'EXTRA')
            runtime.chmod(0o500)
            with self.subTest(operation=operation),self.assertRaises(ValueError):cap.recheck()

    def test_universe_order_count_and_budget_substitution(self):
        for mutate in (lambda p:p['plan']['universe']['symbols'].reverse(),
                       lambda p:p['plan'].update(maximum_requests=476),
                       lambda p:p['plan'].update(maximum_starts_per_rolling_minute=4),
                       lambda p:p['plan'].update(timeout_seconds=21),
                       lambda p:p['plan'].update(maximum_response_bytes=1000001)):
            root,p,r,e=fixture();mutate(p);repin(p,r,e)
            with self.assertRaises(ValueError):admit(p,r,expected=e,authorized_root=root)

    def test_receipt_wrong_parent_relabel_and_content(self):
        doc=envelope({'result':'OBSERVED'},{'package':'a'*64})
        self.assertEqual(verify_envelope(doc,content_hash(doc),parents={'package':'a'*64}),{'result':'OBSERVED'})
        with self.assertRaises(ValueError):verify_envelope(doc,content_hash(doc),parents={'package':'b'*64})
        for key,value in [('scope','LIVE_QUALIFICATION'),('value',{'result':'PASS'})]:
            bad=deepcopy(doc);bad[key]=value
            with self.assertRaises(ValueError):verify_envelope(bad,content_hash(bad),parents=doc['parents'])
        from provider_gateway_live_contract import verify_qualification_receipt
        with self.assertRaises(ValueError):verify_qualification_receipt(doc,content_hash(doc),parents=doc['parents'])

    def test_exclusive_publication(self):
        root,p,r,e=fixture();cap=admit(p,r,expected=e,authorized_root=root)
        store(cap,'test.json',{'status':'SYNTHETIC_TEST_ONLY'})
        original=(Path(p['root'])/'test.json').read_bytes()
        with self.assertRaises(FileExistsError):store(cap,'test.json',{'status':'NEW'})
        self.assertEqual((Path(p['root'])/'test.json').read_bytes(),original)


class ExecutionTests(unittest.TestCase):
    def setup_session(self):
        root,p,r,e=fixture();cap=admit(p,r,expected=e,authorized_root=root)
        now=[utc(p['plan']['rows'][0]['valid_from'])];calls=[]
        def wait(seconds):now[0]+=timedelta(seconds=seconds)
        def exchange(cap,slot,at):
            from urllib.parse import urlencode
            calls.append(slot)
            status,body=response(cap,f'/slot/{slot}?'+urlencode({'at':at}))
            actual='2026-09-11T23:00:00+00:00'
            return Response(status,body,actual,actual)
        session=Session(cap,clock=lambda:now[0].isoformat(),wait=wait,stop=lambda:False,exchange=exchange)
        return session,now,calls

    def test_shared_475_schedule_and_rolling_minute(self):
        session,now,calls=self.setup_session();plan=session.p['plan'];starts=[]
        def execute(request,previous):
            starts.append(now[0]);return {'result':'OBSERVED','bulk_checks':{'freshness':'WITHIN_AGE_BOUND'},'dispatch_time':now[0].isoformat()}
        receipts,reason=execute_schedule(plan,[{}]*475,clock=session.clock,wait=session.wait,stop=lambda:False,
            executor=execute,verify=lambda *_:None,completion_parent=lambda *args:'a'*64)
        self.assertEqual(len(receipts),475);self.assertIsNone(reason)
        self.assertTrue(all((starts[i]-starts[i-3]).total_seconds()>=60 for i in range(3,475)))
        self.assertEqual(len(plan['rows']),1+79*6)
        self.assertEqual([len(x['symbols']) for x in plan['rows'][1:7]],[100,100,100,100,100,17])

    def test_journal_preflight_and_recovery_no_duplicate_dispatch(self):
        session,now,calls=self.setup_session();p=session.p
        Path(p['plan']['root']).mkdir(mode=0o700)
        for row in p['plan']['rows']:Path(row['root']).mkdir(mode=0o700)
        first=session.execute(session.request(0),None)
        self.assertEqual(first['result'],'OBSERVED');self.assertEqual(calls,[0])
        previous=session.completion(session.request(0),0,None,first)
        with self.assertRaises(ValueError):session.execute(session.request(0),None)
        now[0]=utc(p['plan']['rows'][1]['valid_from'])
        with self.assertRaises(ValueError):session.execute(session.request(1),'0'*64)
        self.assertEqual(calls,[0])
        second=session.execute(session.request(1),previous)
        self.assertEqual(second['result'],'OBSERVED');self.assertEqual(calls,[0,1])
        for path in Path(p['plan']['root']).rglob('*.json'):
            self.assertEqual(json.loads(path.read_bytes())['scope'],SCOPE)

    def test_timeout_or_error_keeps_reservation_and_zero_retry(self):
        session,now,calls=self.setup_session();p=session.p
        def fail(*args):calls.append(0);raise TimeoutError('SYNTHETIC_TIMEOUT')
        session.exchange=fail
        result=session.run()
        self.assertEqual(calls,[0]);self.assertEqual(result['classification'],'SYNTHETIC_FAILED')
        self.assertTrue((Path(p['plan']['root'])/'0.reserved.json').exists())
        with self.assertRaises(FileExistsError):session.run()
        self.assertEqual(calls,[0])

    def test_stop_and_missed_opening_zero_dispatch(self):
        for stopped in (True,False):
            session,now,calls=self.setup_session()
            session.stop=lambda:stopped
            if not stopped:now[0]=utc(session.p['plan']['rows'][0]['expires_at'])
            result=session.run();self.assertEqual(calls,[])
            self.assertEqual(result['stop_reason'],'COOPERATIVE_SHUTDOWN' if stopped else 'MISSED_INTERVAL_NO_BACKFILL')

    def test_no_capability_no_transport(self):
        with patch('alpha_radar_runner.bounded_https') as wire:
            with self.assertRaises(ValueError):fixture_exchange(None,0,'unused')
            wire.assert_not_called()

    def test_exact_loopback_tls_boundaries(self):
        session,_,_=self.setup_session()
        with patch('alpha_radar_runner.bounded_https',return_value=Response(200,b'{}')) as wire:
            fixture_exchange(session.cap,0,session.clock())
        args=wire.call_args.kwargs
        self.assertEqual((args['address'],args['host'],args['port']),('127.0.0.1','127.0.0.1',38491))
        self.assertEqual((args['timeout'],args['limit']),(20,1000000));self.assertEqual(args['body'],None)


class LifecycleTests(unittest.TestCase):
    def setup_owned(self):
        root,p,r,e=fixture();cap=admit(p,r,expected=e,authorized_root=root)
        clock=[0.0]
        def pause(seconds):clock[0]+=seconds
        observed=ProcessObservation(12345,os.getpid(),'2026-09-11T23:00:00+00:00','/synthetic/python -B',
                                   '/synthetic/python','a'*64,p['root'],('/synthetic/python','-B'))
        inspector=MagicMock(return_value=observed)
        owned=OwnedProcesses(cap,inspect=inspector,monotonic=lambda:clock[0],pause=pause)
        child=MagicMock(pid=12345);child.poll.return_value=None
        owned.register('worker',child,argv=observed.argv,cwd=p['root'],executable=observed.executable,executable_hash=observed.executable_hash)
        launch='b'*64
        startup_hash=store(cap,'worker-startup.json',{'role':'worker','launch_parent':launch,
            'pid':observed.pid,'parent_pid':observed.parent_pid,'argv':list(observed.argv),
            'cwd':observed.cwd,'runtime_parent':p['runtime_parent'],
            'package_parent':e['package'],'port':p['fixture']['port']})
        owned.startup_pins['worker']=(launch,startup_hash)
        return owned,child,inspector,observed

    def test_pid_reuse_never_signaled(self):
        owned,child,inspector,observed=self.setup_owned()
        inspector.return_value=replace(observed,start_time='2026-09-11T23:00:01+00:00')
        result=owned.cleanup(lambda:True)
        child.terminate.assert_not_called();child.kill.assert_not_called();self.assertFalse(result['clean'])

    def test_fingerprint_mismatch_never_signaled(self):
        for key,value in [('parent_pid',1),('cwd','/wrong'),('executable_hash','b'*64),('argv',('other',))]:
            owned,child,inspector,observed=self.setup_owned();inspector.return_value=replace(observed,**{key:value})
            self.assertFalse(owned.cleanup(lambda:True)['clean'])
            child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_cleanup_reverifies_before_force_and_continues_after_failure(self):
        import subprocess
        owned,child,inspector,observed=self.setup_owned()
        def wait(timeout):
            if child.wait.call_count==1:raise subprocess.TimeoutExpired('SYNTHETIC',timeout)
            child.poll.return_value=0
        child.wait.side_effect=wait
        self.assertTrue(owned.cleanup(lambda:True)['clean'])
        child.terminate.assert_called_once();child.kill.assert_called_once()
        self.assertGreaterEqual(inspector.call_count,5)

    def test_surviving_child_or_listener_fails(self):
        owned,child,_,_=self.setup_owned()
        self.assertFalse(owned.cleanup(lambda:True)['clean'])
        owned,child,_,_=self.setup_owned();child.poll.return_value=0
        self.assertFalse(owned.cleanup(lambda:False)['clean'])

    def test_cleanup_exception_continues(self):
        owned,child,_,_=self.setup_owned()
        other=MagicMock(pid=23456);other.poll.return_value=0
        owned.children['fixture']={'child':other,'observation':{},'expected':{}}
        child.terminate.side_effect=RuntimeError('synthetic')
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['clean']);self.assertNotIn('fixture',owned.children)

    def test_listener_owner_parser_and_errors(self):
        run=MagicMock(return_value=MagicMock(returncode=0,stderr='',stdout='p12345\nn127.0.0.1:38491\n'))
        self.assertEqual(listener_owners(38491,run=run),[(12345,'127.0.0.1:38491')])
        run.return_value=MagicMock(returncode=1,stderr='',stdout='')
        self.assertEqual(listener_owners(38491,run=run),[])
        run.return_value.stderr='ERROR'
        with self.assertRaises(ValueError):listener_owners(38491,run=run)

    def test_os_confinement_missing_sentinel_fails_without_library_load(self):
        owned,_,_,_=self.setup_owned()
        with patch('ctypes.CDLL') as library:
            with self.assertRaises(ValueError):require_confinement(owned.cap)
            library.assert_not_called()

    def test_static_production_cli_has_no_test_entrypoint_or_bypass(self):
        base=Path(__file__).resolve().parents[2]/'BACK END'/'backend'
        source=(base/'alpha_session_runner.py').read_text()
        self.assertIn("'CLI_LIVE_ONLY'",source);self.assertIn("'RADAR_NATIVE_ADAPTER_PENDING'",source)
        self.assertNotIn('alpha_radar_',source);self.assertNotIn('--synthetic',source);self.assertNotIn('--test',source)
        core=(base/'alpha_session_execution.py').read_text()
        self.assertNotIn('MacKeychain',core);self.assertNotIn('NativeHTTPS',core)


class AdversarialExecutionTests(unittest.TestCase):
    setup_session = ExecutionTests.setup_session
    def test_full_mocked_journal_session_475(self):
        session,now,calls=self.setup_session()
        result=session.run()
        self.assertEqual(result['classification'],'SYNTHETIC_PASS')
        self.assertEqual(calls,list(range(475)))
        self.assertEqual(result['requests'],475)
        self.assertEqual(result['additional_provider_requests'],0)
        self.assertEqual(result['live_readiness'],'NOT_QUALIFIED')
        self.assertFalse(result['armed'])

    def test_payload_faults_and_wrong_wire_timing_stop_without_retry(self):
        for fault in ('missing','duplicate','unexpected','malformed','stale','oversize','redirect','throttle','deadline','order','missing_timestamp'):
            session,now,calls=self.setup_session()
            original=session.exchange
            def bad(cap,slot,at):
                reply=original(cap,slot,at)
                if fault=='oversize':return Response(200,b' '*1000001,reply.request_start,reply.response_end)
                if fault=='redirect':return Response(302,b'',reply.request_start,reply.response_end)
                if fault=='throttle':return Response(429,b'',reply.request_start,reply.response_end)
                if fault=='malformed':return Response(200,b'{',reply.request_start,reply.response_end)
                if fault=='deadline':return Response(200,reply.body,reply.request_start,'2026-09-11T23:00:21+00:00')
                payload=json.loads(reply.body)
                if fault=='missing':payload['data'].pop()
                elif fault=='duplicate':payload['data'].append(dict(payload['data'][0]))
                elif fault=='unexpected':payload['data'][0]['symbol']='EXTRA'
                elif fault=='stale':payload['data'][0]['timestamp']='2026-09-14T00:00:00+00:00'
                elif fault=='order':payload['data'].reverse()
                else:payload['data'][0].pop('timestamp')
                return Response(200,json.dumps(payload).encode(),reply.request_start,reply.response_end)
            session.exchange=bad
            with self.subTest(fault=fault):
                result=session.run()
                self.assertEqual(calls,[0]);self.assertEqual(result['classification'],'SYNTHETIC_FAILED')
                self.assertTrue((Path(session.p['plan']['root'])/'0.reserved.json').exists())

    def test_foreign_directory_descriptor_rejected(self):
        session,_,_=self.setup_session()
        fd=os.open(session.cap.authorized_root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            with self.assertRaises(ValueError):session.write(fd,'forbidden.json',{})
            self.assertFalse((Path(session.cap.authorized_root)/'forbidden.json').exists())
        finally:os.close(fd)

    def test_missing_and_replayed_recovery_cannot_dispatch(self):
        for mutation in ('missing','parent','scope','content'):
            session,now,calls=self.setup_session();p=session.p
            Path(p['plan']['root']).mkdir(mode=0o700)
            for row in p['plan']['rows']:Path(row['root']).mkdir(mode=0o700)
            first=session.execute(session.request(0),None)
            parent=session.completion(session.request(0),0,None,first)
            path=Path(p['plan']['rows'][0]['root'])/'ALPHA_VANTAGE.receipt.json'
            original=path.read_bytes()
            # Preserve original synthetic bytes beside the deliberately corrupted fixture.
            (Path(p['root'])/'original-receipt.json').write_bytes(original)
            if mutation=='missing':path.rename(path.with_suffix('.missing'))
            else:
                value=json.loads(original)
                if mutation=='parent':value['parents']['package']='b'*64
                elif mutation=='scope':value['scope']='LIVE_QUALIFICATION'
                else:value['value']['result']='OBSERVED_ALTERED'
                path.chmod(0o600);path.write_bytes(canonical(value));path.chmod(0o400)
            now[0]=utc(p['plan']['rows'][1]['valid_from'])
            with self.assertRaises((ValueError,FileNotFoundError)):session.execute(session.request(1),parent)
            self.assertEqual(calls,[0]);self.assertTrue((Path(p['plan']['root'])/'0.reserved.json').exists())


class AdditionalLifecycleTests(unittest.TestCase):
    setup_owned = LifecycleTests.setup_owned

    def test_missing_startup_receipt_never_signaled(self):
        owned,child,_,_=self.setup_owned();owned.startup_pins.clear()
        self.assertFalse(owned.cleanup(lambda:True)['clean'])
        child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_pid_reuse_after_graceful_timeout_never_force_stopped(self):
        import subprocess
        owned,child,inspector,observed=self.setup_owned()
        def timeout(**kwargs):
            inspector.return_value=replace(observed,start_time='2026-09-11T23:10:00+00:00')
            raise subprocess.TimeoutExpired('synthetic',5)
        child.wait.side_effect=timeout
        self.assertFalse(owned.cleanup(lambda:True)['clean'])
        child.terminate.assert_called_once();child.kill.assert_not_called()

    def test_failure_evidence_survives_runtime_tamper(self):
        owned,child,_,_=self.setup_owned();p,r,_=owned.cap.documents()
        file=Path(r['root'])/'tls.pem';file.chmod(0o600);file.write_bytes(b'ALTERED');file.chmod(0o400)
        self.assertFalse(owned.cleanup(lambda:True)['clean'])
        child.terminate.assert_not_called()
        self.assertTrue(list(Path(p['root']).glob('lifecycle-*.json')))

    def test_parent_ack_timeout_is_bounded(self):
        from alpha_radar_runner import await_parent_ack
        owned,_,_,_=self.setup_owned();clock=[0.0]
        def pause(seconds):clock[0]+=seconds
        with self.assertRaisesRegex(ValueError,'PARENT_ACK_TIMEOUT'):
            await_parent_ack(owned.cap,'worker','b'*64,monotonic=lambda:clock[0],pause=pause)
        self.assertLess(clock[0],10.1)

    def test_deny_default_profile_and_no_global_tmp_permission(self):
        from alpha_radar_runner import confinement_profile
        text=confinement_profile('/isolated/runtime','/isolated/output','/isolated/runtime/python',38491)
        self.assertIn('(deny default)',text)
        self.assertIn('127.0.0.1:38491',text)
        self.assertNotIn('(allow default)',text)
        self.assertNotIn('(subpath "/private/tmp")',text)
        self.assertNotIn('(allow mach-lookup',text)

    def test_runtime_required_source_membership_is_exact(self):
        root,p,r,e=fixture();r['source_files'].pop();repin(p,r,e)
        with self.assertRaisesRegex(ValueError,'SOURCE_CLOSURE'):admit(p,r,expected=e,authorized_root=root)

    def test_full_closure_module_replacement_fails_before_native_access(self):
        root,p,r,e=fixture();r['source_files'][0]='provider_gateway_credentials.py';repin(p,r,e)
        with self.assertRaises(ValueError):admit(p,r,expected=e,authorized_root=root)

    def test_partial_start_without_os_identity_never_signaled(self):
        owned,_,inspector,observed=self.setup_owned()
        other=MagicMock(pid=23456);other.poll.return_value=None
        inspector.return_value=None
        with self.assertRaises(ValueError):
            owned.register('fixture',other,argv=observed.argv,cwd=observed.cwd,
                           executable=observed.executable,executable_hash=observed.executable_hash)
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['clean']);other.terminate.assert_not_called();other.kill.assert_not_called()

    def test_changed_startup_parent_never_signaled(self):
        owned,child,_,_=self.setup_owned();p,_,_=owned.cap.documents()
        path=Path(p['root'])/'worker-startup.json'
        original=path.read_bytes();(Path(p['root'])/'original-startup.json').write_bytes(original)
        doc=json.loads(original);doc['value']['launch_parent']='c'*64
        path.chmod(0o600);path.write_bytes(canonical(doc));path.chmod(0o400)
        self.assertFalse(owned.cleanup(lambda:True)['clean']);child.terminate.assert_not_called()

    def test_false_authority_requires_boolean_false(self):
        root,p,r,e=fixture();p['authority']={**AUTHORITY,'live_execution':0};repin(p,r,e)
        with self.assertRaises(ValueError):admit(p,r,expected=e,authorized_root=root)

    def test_hash_cache_does_not_trust_mutated_object_identity(self):
        session,_,_=ExecutionTests.setup_session(self)
        doc={'result':'OBSERVED'};first=session.hash(doc)
        doc['result']='ALTERED'
        self.assertNotEqual(session.hash(doc),first)

    def test_descriptor_pin_alias_and_preexisting_input_identity(self):
        from alpha_radar_runner import read_descriptor
        root,p,r,e=fixture();case=Path(p['root']).parent
        path=case/'descriptor.json';raw=canonical({'scope':SCOPE})
        path.write_bytes(raw);path.chmod(0o400)
        h=hashlib.sha256(raw).hexdigest()
        self.assertEqual(read_descriptor(path,h),{'scope':SCOPE})
        with self.assertRaises(ValueError):read_descriptor(path,'0'*64)
        alias=case/'alias.json';alias.symlink_to(path)
        with self.assertRaises(ValueError):read_descriptor(alias,h)
        hard=case/'hard.json';os.link(path,hard)
        with self.assertRaises(ValueError):read_descriptor(hard,h)

    def test_descriptor_protected_path_rejected_before_open(self):
        from alpha_radar_runner import read_descriptor
        with patch('alpha_radar_runner.os.open') as opened:
            with self.assertRaises(ValueError):read_descriptor('/Library/Keychains/forbidden','a'*64)
            opened.assert_not_called()

    def test_fixture_timeout_uses_bounded_mock_clock_and_cooperative_stop(self):
        from alpha_radar_fixture import emit
        clock=[0.0];handler=MagicMock()
        def pause(seconds):clock[0]+=seconds
        emit(handler,200,b'{}',fault='timeout',stop=lambda:False,monotonic=lambda:clock[0],pause=pause)
        self.assertAlmostEqual(clock[0],21)
        clock[0]=0
        emit(handler,200,b'{}',fault='timeout',stop=lambda:clock[0]>=1,monotonic=lambda:clock[0],pause=pause)
        self.assertLess(clock[0],1.1)

    def test_fixture_interrupted_body_does_not_manufacture_complete_response(self):
        from alpha_radar_fixture import emit
        handler=MagicMock()
        emit(handler,200,b'{"data":[]}',fault='interrupt',stop=lambda:False)
        handler.send_header.assert_any_call('Content-Length','11')
        handler.wfile.write.assert_called_once_with(b'{"data":[')
        self.assertTrue(handler.close_connection)
