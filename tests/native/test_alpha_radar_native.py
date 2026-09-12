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


class StartupDiagnosticsTests(unittest.TestCase):
    def capability(self):
        root, p, r, e = fixture()
        return admit(p, r, expected=e, authorized_root=root)

    def records(self, cap):
        p, _, _ = cap.documents()
        return [json.loads(f.read_bytes())['value'] for f in
                sorted(Path(p['root']).glob('lifecycle-*.json'))]

    def test_chunked_stderr_never_retains_or_hashes_raw_material(self):
        from alpha_radar_runner import StderrCapture
        raw = (b'PermissionError: sample-sensitive-value /Users/private/person/key\n'
               b'https://example.invalid/?apikey=sample-token\n'
               b'-----BEGIN PRIVATE KEY-----\n\x1b[31msecret\xff\n'
               b'RADAR_DIAGNOSTIC: IMPORT_ERROR\n')
        for width in (1, 2, 7, 2048):
            capture = StderrCapture()
            with patch('alpha_radar_runner.hashlib.sha256') as hash_function:
                for i in range(0, len(raw), width):
                    capture.feed(raw[i:i+width])
                capture.finish()
                result = json.dumps(capture.snapshot())
                hash_function.assert_not_called()
            for forbidden in ('sample-sensitive', '/Users/', 'apikey', 'sample-token',
                              'PRIVATE KEY', 'https://', '\\u001b'):
                self.assertNotIn(forbidden, result)
            self.assertIn('STDERR_PERMISSION_ERROR', result)
            self.assertIn('STDERR_IMPORT_ERROR', result)
            self.assertIn('REDACTED_UNRECOGNIZED', result)
            self.assertFalse(capture.overflow)

    def test_deceptive_prefix_is_only_an_untrusted_fixed_hint(self):
        from alpha_radar_runner import StderrCapture
        capture = StderrCapture()
        capture.feed(b'PermissionError: attacker-content\n'
                     b'RADAR_DIAGNOSTIC: PROCESS_IDENTITY secret\n'
                     b'{"stage":"TLS_LOAD","scope":"LIVE_QUALIFICATION"}\n')
        capture.finish()
        value = capture.snapshot()
        self.assertEqual(value['untrusted_stderr_hints'],
                         ['STDERR_PERMISSION_ERROR', 'REDACTED_UNRECOGNIZED', 'REDACTED_UNRECOGNIZED'])
        self.assertNotIn('authority', value)
        self.assertFalse(value['raw_retained'])

    def test_stderr_line_total_and_retained_bounds(self):
        from alpha_radar_runner import StderrCapture
        for data in (b'x'*80000, b'x\n'*40000, b'PermissionError: detail\n'*4000):
            capture = StderrCapture()
            capture.feed(data)
            capture.finish()
            self.assertTrue(capture.overflow)
            self.assertLessEqual(len(capture.pending), 2048)
            self.assertLessEqual(capture.retained, 8192)
            self.assertNotIn('detail', json.dumps(capture.snapshot()))

    def test_nonblocking_pipe_eof_and_bounded_drain(self):
        from alpha_radar_runner import StderrCapture
        stream = MagicMock();stream.fileno.return_value = 900
        with patch('alpha_radar_runner.os.set_blocking') as nonblocking:
            capture = StderrCapture(stream)
        nonblocking.assert_called_once_with(900, False)
        with patch('alpha_radar_runner.os.read', side_effect=[b'Import', BlockingIOError()]):
            capture.drain()
        self.assertFalse(capture.eof)
        with patch('alpha_radar_runner.os.read', side_effect=[b'Error: hidden\n', b'']):
            capture.drain()
        self.assertTrue(capture.eof)
        self.assertEqual(capture.lines, ['STDERR_IMPORT_ERROR'])
        capture = StderrCapture();capture.fd = 900
        with patch('alpha_radar_runner.os.read', return_value=b'x'*8192) as reader:
            capture.drain()
        self.assertEqual(reader.call_count, 8)
        self.assertTrue(capture.overflow)

    def test_exception_mapping_does_not_stringify_secrets(self):
        from alpha_radar_runner import failure_category
        class Hostile(Exception):
            def __str__(self):
                raise AssertionError('must not stringify')
        self.assertEqual(failure_category(Hostile('sample-secret')), 'UNCLASSIFIED_ERROR')
        self.assertEqual(failure_category(PermissionError(13, 'sample-secret', '/private/person')), 'PERMISSION_ERROR')
        self.assertEqual(failure_category(ValueError('PROCESS_IDENTITY')), 'PROCESS_IDENTITY')

    def test_child_returncode_signal_and_supervisor_are_separate(self):
        from alpha_radar_runner import child_status
        child = MagicMock()
        for code, exit_code, sig in [(None, None, None), (0, 0, None), (7, 7, None), (-9, None, 9)]:
            child.poll.return_value = code
            value = child_status(child)
            self.assertEqual(value['exit_code'], exit_code)
            self.assertEqual(value['signal'], sig)
            self.assertNotIn('supervisor_exit_code', value)
        child.poll.return_value = True
        with self.assertRaises(ValueError):child_status(child)

    def test_unexpected_fingerprint_values_are_neither_retained_nor_hashed(self):
        from alpha_radar_runner import observed_diagnostic
        entry = {'expected': {'pid': 123, 'parent_pid': 456, 'argv': ('expected',),
                 'cwd': '/approved', 'executable': '/approved/python', 'executable_hash': 'a'*64}}
        actual = {'pid': 123, 'parent_pid': 456, 'argv': ('sample-secret',),
                  'cwd': '/Users/private/person', 'executable': '/unapproved',
                  'executable_hash': 'b'*64, 'start_time': '2026-09-12T00:00:00+00:00'}
        with patch('alpha_radar_runner.hashlib.sha256') as h:
            value = observed_diagnostic(entry, actual)
            h.assert_not_called()
        self.assertFalse(value['field_matches']['argv'])
        self.assertIsNone(value['executable_hash'])
        self.assertNotIn('sample-secret', json.dumps(value))
        self.assertNotIn('/Users', json.dumps(value))

    def test_exact_failed_registration_retains_exit_without_signaling(self):
        from alpha_radar_runner import OwnedProcesses
        for cause in (None, PermissionError('synthetic-denial'), ValueError('ARGV_OBSERVATION_FAILED')):
            cap = self.capability()
            inspector = MagicMock(return_value=None, side_effect=cause)
            owned = OwnedProcesses(cap, inspect=inspector, pause=lambda _: None)
            child = MagicMock(pid=12345);child.poll.return_value = 7
            with self.assertRaises((ValueError, PermissionError)):
                owned.register('fixture', child, argv=('synthetic',), cwd=cap.documents()[0]['root'],
                               executable='/synthetic/python', executable_hash='a'*64,
                               launch_parent='b'*64)
            primary = deepcopy(owned.primary_failures)
            result = owned.cleanup(lambda: True)
            self.assertFalse(result['clean'])
            self.assertTrue(result['port_clear'])
            self.assertEqual(owned.primary_failures, primary)
            self.assertIn('fixture', result['remaining'])
            child.terminate.assert_not_called();child.kill.assert_not_called()
            statuses = [v for v in self.records(cap) if v['event'] == 'FINAL_CHILD_STATUS']
            self.assertEqual(statuses[0]['pid'], 12345)
            self.assertEqual(statuses[0]['status']['exit_code'], 7)
            self.assertFalse(statuses[0]['ownership_verified'])
            self.assertFalse((Path(cap.documents()[0]['root'])/'worker-launch.json').exists())
            self.assertFalse((Path(cap.documents()[0]['root'])/'journal').exists())

    def test_inspection_timeout_is_preserved(self):
        import subprocess
        from alpha_radar_runner import OwnedProcesses
        cap = self.capability();child = MagicMock(pid=12345);child.poll.return_value = 1
        owned = OwnedProcesses(cap, inspect=MagicMock(side_effect=subprocess.TimeoutExpired('unretained-command', 1)), pause=lambda _:None)
        with self.assertRaises(subprocess.TimeoutExpired):
            owned.register('fixture', child, argv=(), cwd=cap.documents()[0]['root'], executable='/synthetic', executable_hash='a'*64)
        self.assertEqual(owned.primary_failures[0]['category'], 'PROCESS_TIMEOUT')
        self.assertNotIn('unretained-command', json.dumps(self.records(cap)))
        self.assertFalse(owned.cleanup(lambda:True)['clean'])

    def test_cleanup_publication_failure_continues_and_cannot_be_green(self):
        owned, child, _, _ = LifecycleTests.setup_owned(self)
        child.poll.return_value = 0
        other = MagicMock(pid=23456);other.poll.return_value = 0
        owned.children['fixture'] = {'child':other,'observation':{},'expected':{}}
        with patch.object(owned, 'evidence', side_effect=PermissionError('unretained')):
            result = owned.cleanup(lambda:True)
        self.assertFalse(result['clean'])
        self.assertIn('DIAGNOSTIC_PUBLICATION_FAILED', result['diagnostic_failures'])
        self.assertTrue(child.poll.called and other.poll.called)
        child.terminate.assert_not_called();other.terminate.assert_not_called()

    def test_popen_failure_and_cleanup_failure_keep_primary(self):
        from alpha_radar_runner import supervise, OwnedProcesses
        cap = self.capability()
        descriptor = {'native_tools':{}, 'clock_mode':'ACCELERATED_LOGICAL_TIME', 'maximum_duration_seconds':60}
        popen = MagicMock(side_effect=PermissionError('sample-sensitive-error'))
        with patch('alpha_radar_runner.native_identity'), patch('alpha_radar_runner.verify_tools'), \
             patch('alpha_radar_runner.listener_owners', return_value=[]), \
             patch('alpha_radar_runner.signal.signal'), \
             patch.object(OwnedProcesses, 'cleanup', side_effect=RuntimeError('sample-cleanup-secret')):
            result = supervise(cap, descriptor, popen=popen)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(result['primary_failure']['stage'], 'PROCESS_CREATE')
        self.assertEqual(result['primary_failure']['creation_state'], 'NO_CHILD_CREATED')
        self.assertEqual(result['primary_failure']['category'], 'PERMISSION_ERROR')
        self.assertEqual(result['supervisor_exit_code'], 1)
        self.assertEqual(result['secondary_failures'], ['UNCLASSIFIED_ERROR'])
        self.assertFalse(result['cleanup']['clean'])
        self.assertNotIn('sample-sensitive', json.dumps(result))
        self.assertNotIn('sample-cleanup', json.dumps(result))
        self.assertFalse((Path(cap.documents()[0]['root'])/'worker-launch.json').exists())

    def test_all_child_stages_are_bound_diagnostics_not_live_receipts(self):
        from alpha_radar_runner import ChildDiagnostics, STAGES, verify_child_diagnostic
        from provider_gateway_live_contract import verify_qualification_receipt
        cap = self.capability();diag = ChildDiagnostics(cap, 'fixture', 'a'*64)
        p, _, pins = cap.documents()
        for stage in sorted(STAGES):diag.emit(stage)
        for f in Path(p['root']).glob('fixture-diagnostic-*.json'):
            doc = json.loads(f.read_bytes())
            value = verify_child_diagnostic(doc, content_hash(doc), parents=pins, role='fixture',
                launch_parent='a'*64, pid=os.getpid(), parent_pid=os.getppid())
            self.assertIn(value['stage'], STAGES)
            with self.assertRaises(ValueError):verify_qualification_receipt(doc, content_hash(doc), parents=pins)

    def test_forged_diagnostic_parents_roles_pid_and_categories_rejected(self):
        from alpha_radar_runner import ChildDiagnostics, verify_child_diagnostic
        cap = self.capability();p,_,pins=cap.documents()
        ChildDiagnostics(cap, 'fixture', 'a'*64).emit('TLS_LOAD')
        doc = json.loads((Path(p['root'])/'fixture-diagnostic-0001.json').read_bytes())
        for key,value in [('launch_parent','b'*64),('role','worker'),('pid',12345),
                          ('parent_pid',12345),('category','sample-secret'),('stage','UNKNOWN')]:
            bad=deepcopy(doc);bad['value'][key]=value
            with self.assertRaises(ValueError):verify_child_diagnostic(bad, content_hash(bad),
                parents=pins,role='fixture',launch_parent='a'*64,pid=os.getpid(),parent_pid=os.getppid())
        with self.assertRaises(ValueError):verify_child_diagnostic(doc,content_hash(doc),
            parents={**pins,'package':'b'*64},role='fixture',launch_parent='a'*64,
            pid=os.getpid(),parent_pid=os.getppid())

    def test_diagnostic_publication_cannot_replace_primary_exception(self):
        import io
        from alpha_radar_runner import ChildDiagnostics
        cap=self.capability();diag=ChildDiagnostics(cap,'fixture','a'*64)
        primary=PermissionError('sample-primary-secret')
        with patch('alpha_radar_runner.store', side_effect=OSError('sample-secondary-secret')), \
             patch('alpha_radar_runner.sys.stderr',new_callable=io.StringIO) as stream:
            diag.failure(primary)
            self.assertEqual(stream.getvalue(),'RADAR_DIAGNOSTIC: DIAGNOSTIC_PUBLICATION_FAILED\n')

    def test_child_diagnostics_reject_arbitrary_category_before_publication(self):
        from alpha_radar_runner import ChildDiagnostics
        cap=self.capability();diag=ChildDiagnostics(cap,'fixture','a'*64)
        with patch('alpha_radar_runner.store') as writer:
            with self.assertRaises(ValueError):diag.emit('TLS_LOAD',category='sample-secret')
            writer.assert_not_called()

    def test_child_failure_stages_preserve_original_and_do_not_launch(self):
        from alpha_radar_runner import child_main
        for stage in ('RUNTIME_VERIFY','CONFINEMENT_CHECK','TLS_LOAD','SOCKET_BIND',
                      'SOCKET_LISTEN','TLS_WRAP','STARTUP_PUBLISH','PARENT_ACK'):
            cap=self.capability();p,r,pins=cap.documents()
            launch={'scope':SCOPE,'authority':AUTHORITY,'descriptor':{'package':p,'runtime':r,
                'expected':pins,'authorized_root':cap.authorized_root,'native_tools':{},
                'clock_mode':'ACCELERATED_LOGICAL_TIME','maximum_duration_seconds':60},
                'output_identity':list(cap.output_identity),'role':'fixture',
                'parent_pid':os.getppid(),'created_at':'2026-09-12T00:00:00+00:00'}
            primary=PermissionError('sample-secret')
            def fake_serve(cap,stop,ready,*,stage=stage):
                # The keyword receives the actual stage publisher.
                stage(target)
                raise primary
            target=stage
            runtime_error=primary if stage=='RUNTIME_VERIFY' else None
            confinement_error=primary if stage=='CONFINEMENT_CHECK' else None
            with patch('alpha_radar_runner.native_identity',side_effect=runtime_error), \
                 patch('alpha_radar_runner.require_confinement',side_effect=confinement_error), \
                 patch('alpha_radar_runner.signal.signal'), \
                 patch('alpha_radar_fixture.serve',side_effect=fake_serve):
                with self.assertRaises(PermissionError) as caught:child_main(launch,'fixture','a'*64)
            self.assertIs(caught.exception,primary)
            docs=[json.loads(f.read_bytes())['value'] for f in Path(p['root']).glob('fixture-diagnostic-*.json')]
            failures=[d for d in docs if d['category'] is not None]
            self.assertEqual(failures[-1]['stage'],stage)
            self.assertEqual(failures[-1]['category'],'PERMISSION_ERROR')
            self.assertNotIn('sample-secret',json.dumps(docs))

    def test_fixture_stage_order_with_entirely_mocked_socket_and_tls(self):
        from alpha_radar_fixture import serve
        cap=self.capability();events=[];instances=[]
        class FakeServer:
            def __init__(self,address,handler):
                self.server_address=address;self.socket=MagicMock();self.closed=False
                instances.append(self);self.server_bind();self.server_activate()
            def server_activate(self):pass
            def server_close(self):self.closed=True
        context=MagicMock();context.wrap_socket.side_effect=lambda sock,**kwargs:sock
        ready=MagicMock(side_effect=lambda:events.append('READY'))
        with patch('alpha_radar_fixture.HTTPServer',FakeServer), \
             patch('alpha_radar_fixture.ssl.SSLContext',return_value=context):
            serve(cap,lambda:True,ready,stage=events.append)
        self.assertEqual(events,['TLS_CONTEXT','TLS_LOAD','SOCKET_CREATE','SOCKET_BIND',
            'SOCKET_LISTEN','TLS_WRAP','READY','FIXTURE_SERVE'])
        self.assertTrue(instances[0].closed)
        instances[0].socket.bind.assert_called_once_with(('127.0.0.1',38491))
        context.load_cert_chain.assert_called_once()

    def test_duplicate_diagnostic_publication_preserves_original(self):
        from alpha_radar_runner import ChildDiagnostics
        cap=self.capability();p,_,_=cap.documents()
        first=ChildDiagnostics(cap,'fixture','a'*64);first.emit('TLS_LOAD')
        path=Path(p['root'])/'fixture-diagnostic-0001.json';before=path.read_bytes()
        with self.assertRaises(FileExistsError):ChildDiagnostics(cap,'fixture','a'*64).emit('TLS_WRAP')
        self.assertEqual(path.read_bytes(),before)


class QueryDiagnosticTests(unittest.TestCase):
    def capability(self):
        return StartupDiagnosticsTests.capability(self)

    def records(self, cap):
        return StartupDiagnosticsTests.records(self, cap)

    def test_observed_exit65_pattern_brackets_failed_query_without_authority(self):
        import subprocess
        import truth_spine_process_identity as identity
        cap=self.capability();child=MagicMock(pid=28326)
        statuses=iter([None,None,65]);child.poll.side_effect=lambda:next(statuses,65)
        owned=OwnedProcesses(cap,pause=lambda _:None)
        replies=[subprocess.CompletedProcess([],0,'Sat Sep 12 04:28:48 2026',''),
                 subprocess.CompletedProcess([],1,'','unretained inspector text')]
        with patch.object(identity.subprocess,'run',side_effect=replies) as run:
            with self.assertRaisesRegex(identity.IdentityFailure,'^PROCESS_INSPECTION_FAILED$'):
                owned.register('fixture',child,argv=('synthetic',),cwd=cap.documents()[0]['root'],
                               executable='/synthetic/python',executable_hash='a'*64,launch_parent='b'*64)
        self.assertEqual(run.call_count,2)
        capture=owned.children['fixture']['capture']
        capture.feed((b'x'*33+b'\n')*5+b'x'*37+b'\n');capture.finish()
        result=owned.cleanup(lambda:True)
        records=self.records(cap)
        bracket=[v for v in records if v['event']=='INSPECTION_CHILD_STATUS']
        self.assertEqual([v['phase'] for v in bracket],['BEFORE','AFTER'])
        self.assertEqual([v['status']['returncode'] for v in bracket],[None,65])
        query=[v for v in records if v['event']=='INSPECTION_QUERY']
        self.assertEqual(query[-1]['diagnostic']['query'],'PS_PARENT')
        self.assertEqual(query[-1]['diagnostic']['failure'],'TOOL_EXIT')
        self.assertTrue(all(v['launch_parent']=='b'*64 and not v['ownership_authority'] for v in query+bracket))
        self.assertEqual(capture.snapshot()['untrusted_stderr_hints'],['REDACTED_UNRECOGNIZED']*6)
        self.assertEqual(capture.received,208)
        self.assertEqual(owned.primary_failures[0]['category'],'PROCESS_INSPECTION_FAILED')
        self.assertFalse(result['clean']);self.assertTrue(result['port_clear'])
        child.terminate.assert_not_called();child.kill.assert_not_called()
        out=Path(cap.documents()[0]['root'])
        self.assertFalse((out/'worker-launch.json').exists());self.assertFalse((out/'journal').exists())
        self.assertFalse(any(v['event']=='OWNERSHIP' for v in records))
        self.assertNotIn('unretained inspector',json.dumps(records))

    def test_status_or_query_publication_failure_keeps_original_error(self):
        import truth_spine_process_identity as identity
        cap=self.capability();child=MagicMock(pid=12345);child.poll.return_value=65
        owned=OwnedProcesses(cap,pause=lambda _:None)
        write=owned.evidence
        def failing(value):
            if value['event']=='INSPECTION_QUERY' or (value['event']=='INSPECTION_CHILD_STATUS' and value['phase']=='AFTER'):
                raise PermissionError('private diagnostic failure')
            write(value)
        original=PermissionError('private inspector failure')
        with patch.object(owned,'evidence',side_effect=failing),patch.object(identity.subprocess,'run',side_effect=original):
            with self.assertRaises(PermissionError) as caught:
                owned.register('fixture',child,argv=(),cwd=cap.documents()[0]['root'],
                               executable='/synthetic',executable_hash='a'*64,launch_parent='b'*64)
        self.assertIs(caught.exception,original)
        self.assertIn('DIAGNOSTIC_PUBLICATION_FAILED',owned.diagnostic_failures)
        self.assertIn('DIAGNOSTIC_STATUS_UNAVAILABLE',owned.diagnostic_failures)
        self.assertFalse(owned.cleanup(lambda:True)['clean'])
        child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_forged_query_metadata_is_rejected_before_publication(self):
        import alpha_radar_runner as runner
        cap=self.capability();child=MagicMock(pid=12345);child.poll.return_value=65
        def inspector(pid,*,diagnostic):
            diagnostic({'raw':'secret /private/forged'})
        with patch.object(runner,'inspect_macos',inspector):
            owned=OwnedProcesses(cap,inspect=inspector,pause=lambda _:None)
            with self.assertRaises(ValueError):
                owned.register('fixture',child,argv=(),cwd=cap.documents()[0]['root'],
                               executable='/synthetic',executable_hash='a'*64,launch_parent='b'*64)
        body=json.dumps(self.records(cap))
        self.assertNotIn('secret',body);self.assertNotIn('/private/forged',body)
        self.assertNotIn('INSPECTION_QUERY',body)
        self.assertFalse(owned.cleanup(lambda:True)['clean'])

    def test_bootstrap_import_failure_retains_only_fixed_early_hints(self):
        import builtins,io
        import alpha_radar_runner as runner
        source=Path(runner.__file__).read_text().split('# Diagnostics are observations only;')[0]
        real_import=builtins.__import__
        error=ImportError('secret /private/path')
        def importing(name,*args,**kwargs):
            if name=='alpha_market_baseline':raise error
            return real_import(name,*args,**kwargs)
        stderr=io.StringIO()
        with patch('sys.stderr',stderr),patch('builtins.__import__',side_effect=importing):
            with self.assertRaises(SystemExit) as caught:
                exec(compile(source,'synthetic-bootstrap','exec'),{'__name__':'__main__'})
        self.assertEqual(caught.exception.code,1)
        self.assertEqual(stderr.getvalue().splitlines(),['RADAR_EARLY: PYTHON_ENTRY',
                         'RADAR_EARLY: IMPORT_BEGIN','RADAR_EARLY: IMPORT_FAILED'])
        self.assertNotIn('secret',stderr.getvalue())
        with patch('builtins.__import__',side_effect=importing):
            with self.assertRaises(ImportError) as imported:
                exec(compile(source,'synthetic-bootstrap','exec'),{'__name__':'offline_import'})
        self.assertIs(imported.exception,error)

    def test_early_descriptor_failure_stage_does_not_claim_admission(self):
        import io
        import alpha_radar_runner as runner
        stderr=io.StringIO()
        with patch.object(runner,'__name__','__main__'),patch('sys.stderr',stderr), \
             patch('sys.argv',['runner','--descriptor','/synthetic/descriptor','--expected-descriptor','a'*64]), \
             patch.object(runner,'read_descriptor',side_effect=PermissionError('secret')), \
             patch.object(runner,'child_main') as child,patch.object(runner,'admit') as admission:
            with self.assertRaises(PermissionError):runner.main()
        self.assertEqual(stderr.getvalue(),'RADAR_EARLY: DESCRIPTOR_READ\n')
        child.assert_not_called();admission.assert_not_called()

    def test_early_hints_are_chunk_safe_and_never_accept_appended_values(self):
        from alpha_radar_runner import StderrCapture,EARLY_STAGES
        for width in (1,7,4096):
            capture=StderrCapture()
            data=b''.join(('RADAR_EARLY: '+stage+'\n').encode() for stage in sorted(EARLY_STAGES))
            data+=b'RADAR_EARLY: IMPORT_FAILED secret /private/path\n'
            for at in range(0,len(data),width):capture.feed(data[at:at+width])
            capture.finish()
            hints=capture.snapshot()['untrusted_stderr_hints']
            self.assertEqual(hints[:-1],['UNTRUSTED_EARLY_'+stage for stage in sorted(EARLY_STAGES)])
            self.assertEqual(hints[-1],'REDACTED_UNRECOGNIZED')
            self.assertNotIn('secret',json.dumps(capture.snapshot()))
            self.assertFalse(capture.overflow)

    def test_early_admission_failure_never_emits_verified_stage(self):
        import io
        import alpha_radar_runner as runner
        cap=self.capability();p,r,pins=cap.documents()
        launch={'scope':SCOPE,'authority':AUTHORITY,'role':'fixture','parent_pid':os.getppid(),
                'created_at':'synthetic','output_identity':list(cap.output_identity),
                'descriptor':{'package':p,'runtime':r,'expected':pins,'authorized_root':cap.authorized_root,
                              'native_tools':{},'clock_mode':'ACCELERATED_LOGICAL_TIME','maximum_duration_seconds':60}}
        stderr=io.StringIO()
        with patch.object(runner,'__name__','__main__'),patch('sys.stderr',stderr), \
             patch.object(runner,'verify_inputs',side_effect=ValueError('synthetic rejection')), \
             patch.object(runner,'ChildDiagnostics') as diagnostic:
            with self.assertRaises(ValueError):runner.child_main(launch,'fixture','a'*64)
        self.assertEqual(stderr.getvalue(),'RADAR_EARLY: CHILD_ADMISSION_BEGIN\n')
        diagnostic.assert_not_called()


class StartupOnlyTests(unittest.TestCase):
    capability = StartupDiagnosticsTests.capability
    records = StartupDiagnosticsTests.records
    # Reuse capability/record helpers without recollecting inherited test methods.
    def descriptor(self, cap):
        from alpha_radar_runner import STARTUP_MODE, STARTUP_SCHEMA
        p, r, pins = cap.documents()
        return {'schema': STARTUP_SCHEMA, 'execution_mode': STARTUP_MODE,
                'package': p, 'runtime': r, 'expected': pins,
                'authorized_root': cap.authorized_root,
                'native_tools': {'/usr/bin/sandbox-exec': 'a'*64},
                'clock_mode': 'STARTUP_WALL_CLOCK', 'maximum_duration_seconds': 120}

    def run_startup(self, *, registration_error=None, cleanup_clean=True, tls_error=None):
        from contextlib import ExitStack
        import io
        from alpha_radar_runner import supervise
        cap = self.capability(); d = self.descriptor(cap)
        child = MagicMock(pid=12345); child.poll.return_value = None
        owned = MagicMock(); owned.children = {}; owned.startup_pins = {}
        def register(role, process, **kwargs):
            self.assertEqual(role, 'fixture')
            if registration_error: raise registration_error
            owned.children[role] = {'child': process}
            store(cap, 'fixture-startup.json', {'mock': True})
        owned.register.side_effect = register
        owned.cleanup.return_value = {'clean': cleanup_clean, 'port_clear': True,
                                      'remaining': [] if cleanup_clean else ['fixture']}
        popen = MagicMock(return_value=child)
        tls = {'hostname_verified': True, 'http_requests': 0,
               'protocol': 'TLSv1.3', 'certificate_der_sha256': 'a'*64}
        # Mock the native sentinel boundary only. Other file admission and all
        # receipt publications remain real, exclusive artifact-local writes.
        sentinel = Path(cap.authorized_root)/'confinement-denied-input'
        original_open, original_chmod = Path.open, Path.chmod
        def open_path(path, *args, **kwargs):
            if path == sentinel:
                self.assertEqual(args, ('xb',))
                return io.BytesIO()
            return original_open(path, *args, **kwargs)
        def chmod_path(path, mode, **kwargs):
            if path == sentinel:
                self.assertEqual(mode, 0o400)
                return None
            return original_chmod(path, mode, **kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, 'open', open_path))
            stack.enter_context(patch.object(Path, 'chmod', chmod_path))
            for name in ('native_identity', 'verify_tools', 'signal.signal'):
                stack.enter_context(patch('alpha_radar_runner.' + name))
            stack.enter_context(patch('alpha_radar_runner.OwnedProcesses', return_value=owned))
            stack.enter_context(patch('alpha_radar_runner.read_startup', return_value='b'*64))
            stack.enter_context(patch('alpha_radar_runner.listener_owners',
                                     side_effect=[[], [(12345, '127.0.0.1:38491')]]))
            handshake = stack.enter_context(patch('alpha_radar_runner.startup_tls',
                                                  return_value=tls, side_effect=tls_error))
            session = stack.enter_context(patch('alpha_radar_runner.Session'))
            result = supervise(cap, d, popen=popen)
            session.assert_not_called()
        self.assertEqual(popen.call_count, 1)
        argv = popen.call_args.args[0]
        self.assertEqual(argv[argv.index('--child')+1], 'fixture')
        self.assertFalse((Path(d['package']['root'])/'worker-launch.json').exists())
        self.assertFalse((Path(d['package']['root'])/'session.json').exists())
        self.assertFalse((Path(d['package']['root'])/'journal').exists())
        return cap, d, result, owned, handshake

    def test_startup_only_never_launches_worker_or_qualifies_session(self):
        from alpha_radar_runner import verify_startup_result
        cap, d, result, owned, handshake = self.run_startup()
        verify_startup_result(result, content_hash(d))
        self.assertEqual(result['classification'], 'SYNTHETIC_STARTUP_PASS')
        self.assertEqual(result['requests'], 0)
        self.assertIsNone(result['session'])
        owned.register.assert_called_once(); owned.cleanup.assert_called_once()
        handshake.assert_called_once()
        self.assertFalse(any(cap.documents()[0]['authority'].values()))
        for mutation in ({'classification':'SYNTHETIC_PASS'}, {'session':{'requests':475}},
                         {'requests':475}, {'worker_launches':1}, {'armed':True},
                         {'live_readiness':'GREEN'}, {'descriptor_parent':'0'*64}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_startup_result({**result, **mutation}, content_hash(d))

    def test_ownership_failure_prevents_handshake_and_stays_failed(self):
        _, _, result, owned, handshake = self.run_startup(
            registration_error=ValueError('PROCESS_INSPECTION_FAILED'), cleanup_clean=False)
        self.assertEqual(result['classification'], 'SYNTHETIC_STARTUP_FAILED')
        self.assertEqual(result['primary_failure']['stage'], 'OWNERSHIP_REGISTER')
        handshake.assert_not_called(); owned.cleanup.assert_called_once()

    def test_clear_port_does_not_replace_verified_cleanup(self):
        _, _, result, _, _ = self.run_startup(cleanup_clean=False)
        self.assertTrue(result['cleanup']['port_clear'])
        self.assertEqual(result['classification'], 'SYNTHETIC_STARTUP_FAILED')
        self.assertEqual(result['supervisor_exit_code'], 1)

    def test_tls_failure_is_primary_and_cleanup_is_still_required(self):
        import ssl
        _, _, result, owned, _ = self.run_startup(tls_error=ssl.SSLError('unretained'))
        self.assertEqual(result['primary_failure']['stage'], 'TLS_HANDSHAKE')
        self.assertEqual(result['primary_failure']['category'], 'TLS_ERROR')
        owned.cleanup.assert_called_once()
        self.assertEqual(result['classification'], 'SYNTHETIC_STARTUP_FAILED')

    def test_explicit_contract_and_deadline_cannot_fall_back(self):
        from alpha_radar_runner import descriptor_schema, startup_only
        cap = self.capability(); d = self.descriptor(cap)
        descriptor_schema(d); self.assertTrue(startup_only(d))
        for key in ('schema', 'execution_mode'):
            bad = deepcopy(d); bad.pop(key)
            with self.assertRaises(ValueError): descriptor_schema(bad)
        for mutation in ({'schema':'unknown'}, {'execution_mode':'FULL'},
                         {'maximum_duration_seconds':121}, {'maximum_duration_seconds':True},
                         {'clock_mode':'ACCELERATED_LOGICAL_TIME'}, {'extra':False}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                descriptor_schema({**d, **mutation})
        legacy = {k:v for k,v in d.items() if k not in ('schema','execution_mode')}
        legacy['clock_mode'] = 'ACCELERATED_LOGICAL_TIME'
        descriptor_schema(legacy); self.assertFalse(startup_only(legacy))

    def test_worker_child_rejected_before_runtime_or_credentials(self):
        from alpha_radar_runner import child_main
        cap = self.capability(); d = self.descriptor(cap)
        launch = {'scope':SCOPE, 'authority':AUTHORITY, 'descriptor':d,
                  'output_identity':list(cap.output_identity), 'role':'worker',
                  'parent_pid':os.getppid(), 'created_at':'2026-09-14T00:00:00+00:00'}
        with patch('alpha_radar_runner.verify_inputs') as admission, \
             patch('alpha_radar_runner.Session') as session:
            with self.assertRaisesRegex(ValueError, 'CHILD_ROLE'):
                child_main(launch, 'worker', 'a'*64)
            admission.assert_not_called(); session.assert_not_called()

    def test_tls_handshake_numeric_only_bounded_and_verified_twice(self):
        from alpha_radar_runner import startup_tls
        cap = self.capability(); owned = MagicMock()
        raw = MagicMock(); raw.__enter__.return_value = raw
        context = MagicMock(); context.check_hostname=True
        import ssl
        context.verify_mode=ssl.CERT_REQUIRED
        channel = context.wrap_socket.return_value.__enter__.return_value
        channel.getpeercert.return_value=b'SYNTHETIC_CERT'; channel.version.return_value='TLSv1.3'
        with patch('alpha_radar_runner.socket.socket', return_value=raw) as create, \
             patch('alpha_radar_runner.socket.getaddrinfo') as dns, \
             patch('alpha_radar_runner.ssl.create_default_context', return_value=context), \
             patch('alpha_radar_runner.ssl.PEM_cert_to_DER_cert', return_value=b'SYNTHETIC_CERT'):
            result=startup_tls(cap, owned)
            self.assertEqual(create.call_count,1); dns.assert_not_called()
        raw.settimeout.assert_called_once_with(5)
        raw.connect.assert_called_once_with(('127.0.0.1',38491))
        channel.send.assert_not_called(); channel.sendall.assert_not_called()
        self.assertEqual(owned.verify.call_args_list, [unittest.mock.call('fixture')]*2)
        self.assertEqual(result['http_requests'],0)

    def test_tls_does_not_open_socket_after_identity_failure(self):
        from alpha_radar_runner import startup_tls
        cap = self.capability(); owned = MagicMock()
        owned.verify.side_effect=ValueError('PROCESS_IDENTITY')
        import ssl
        context=MagicMock(check_hostname=True,verify_mode=ssl.CERT_REQUIRED)
        with patch('alpha_radar_runner.ssl.create_default_context',return_value=context), \
             patch('alpha_radar_runner.ssl.PEM_cert_to_DER_cert',return_value=b'cert'), \
             patch('alpha_radar_runner.socket.socket') as opened:
            with self.assertRaisesRegex(ValueError,'PROCESS_IDENTITY'): startup_tls(cap,owned)
            opened.assert_not_called()


class HostedPreparationTests(unittest.TestCase):
    def archive(self, entries):
        import io
        import tarfile
        root=Path(tempfile.mkdtemp(prefix='archive-case-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as bundle:
            for name,kind,value in entries:
                member=tarfile.TarInfo(name)
                if kind=='file':
                    member.size=len(value);member.mode=0o500
                    bundle.addfile(member,io.BytesIO(value))
                else:
                    member.type=tarfile.SYMTYPE;member.linkname=value
                    bundle.addfile(member)
        archive=root/'fixture.tar.gz';archive.write_bytes(data.getvalue())
        return archive, root/'destination', hashlib.sha256(data.getvalue()).hexdigest()

    def test_verified_archive_materializes_independent_files(self):
        from alpha_radar_ci import materialize
        archive,destination,parent=self.archive([('python/bin/python3.13','file',b'SYNTHETIC'),
                                               ('python/bin/python','link','python3.13')])
        materialize(archive,destination,parent)
        first=destination/'python/bin/python3.13';alias=destination/'python/bin/python'
        self.assertEqual(first.read_bytes(),alias.read_bytes())
        self.assertFalse(alias.is_symlink())
        self.assertNotEqual(first.stat().st_ino,alias.stat().st_ino)
        self.assertEqual(alias.stat().st_nlink,1)
        with self.assertRaises(FileExistsError):materialize(archive,destination,parent)

    def test_archive_wrong_pin_rejected_before_output(self):
        from alpha_radar_ci import materialize
        archive,destination,_=self.archive([('python/bin/python3.13','file',b'SYNTHETIC')])
        with self.assertRaisesRegex(ValueError,'ARCHIVE_PIN'):materialize(archive,destination,'0'*64)
        self.assertFalse(destination.exists())

    def test_archive_traversal_absolute_duplicate_and_escape_rejected(self):
        from alpha_radar_ci import materialize
        cases=[ [('python/../../outside','file',b'x')], [('/python/absolute','file',b'x')],
                [('python/a','file',b'x'),('python/a','file',b'y')],
                [('python/link','link','../../outside')],
                [('python/a','link','b'),('python/b','link','a')] ]
        for entries in cases:
            archive,destination,parent=self.archive(entries)
            with self.subTest(entries=entries),self.assertRaises(ValueError):materialize(archive,destination,parent)
            self.assertFalse((archive.parent/'outside').exists())

    def test_hosted_admission_rejects_self_hosted_rerun_and_proxy(self):
        from alpha_radar_ci import hosted
        env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'macOS',
             'RUNNER_ARCH':'ARM64','GITHUB_RUN_ATTEMPT':'1'}
        with patch('alpha_radar_ci.platform.system',return_value='Darwin'), \
             patch('alpha_radar_ci.platform.machine',return_value='arm64'), \
             patch('alpha_radar_ci.platform.mac_ver',return_value=('26.0',(),'')):
            with patch.dict(os.environ,env,clear=True):hosted()
            for mutation in ({'RUNNER_ENVIRONMENT':'self-hosted'},{'GITHUB_RUN_ATTEMPT':'2'},
                             {'HTTPS_PROXY':'https://example.invalid'},{'RUNNER_ARCH':'X64'}):
                with self.subTest(mutation=mutation),patch.dict(os.environ,{**env,**mutation},clear=True):
                    with self.assertRaises(ValueError):hosted()

    def test_ci_entrypoint_has_no_live_or_worker_dispatch_interface(self):
        import ast
        import alpha_radar_ci
        source=Path(alpha_radar_ci.__file__).read_text()
        tree=ast.parse(source)
        self.assertNotIn('MacKeychain',source)
        self.assertNotIn('provider_gateway_credentials',source)
        self.assertNotIn('Session(',source)
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
        calls=[n for n in ast.walk(function) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
               and n.func.attr=='Popen']
        self.assertEqual(len(calls),1)
        self.assertIn("require(startup_only(d),'STARTUP_ONLY_REQUIRED')",source)
        self.assertIn("'OFFLINE_SOURCE_BINDING'",source)
        self.assertIn("'--expected-descriptor',pins['descriptor_sha256']",source)
        self.assertNotIn('kill(',ast.get_source_segment(source,function))

    def test_workflow_preserves_minimal_permissions_and_pinned_actions(self):
        import re
        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/alpha-radar-native-diagnostics.yml').read_text()
        self.assertIn('contents: read',text)
        self.assertIn('runs-on: macos-26',text)
        self.assertIn('persist-credentials: false',text)
        self.assertNotIn('secrets.',text)
        self.assertNotIn('self-hosted',text)
        uses=re.findall(r'uses: ([^\n]+)',text)
        self.assertEqual(len(uses),3)
        for value in uses:self.assertRegex(value,r'^actions/[a-z-]+@[a-f0-9]{40}$')
        self.assertLess(text.index('alpha_radar_ci.py offline'),text.index('alpha_radar_ci.py execute'))
        self.assertIn('/export/',text)

    def test_offline_partition_preserves_every_ordinary_test_and_native_gate(self):
        from alpha_radar_ci import offline_partition, NATIVE_ONLY
        def test(node):
            value=unittest.FunctionTestCase(lambda:None)
            value.id=lambda:node
            return value
        native=next(iter(NATIVE_ONLY))
        suite,partition=offline_partition(unittest.TestSuite([test(native),test('mock.a'),test('mock.b')]))
        self.assertEqual(partition['offline'],['mock.a','mock.b'])
        self.assertEqual(suite.countTestCases(),2)
        self.assertEqual(partition['native_not_run'][0]['node'],native)
        self.assertEqual(len(partition['collected']),3)
        for ids in ([native,native,'mock.a'],['mock.a'],[native,'unittest.loader._FailedTest.bad']):
            with self.assertRaisesRegex(ValueError,'OFFLINE_COLLECTION'):
                offline_partition(unittest.TestSuite(test(v) for v in ids))

    def test_dylib_identity_is_not_a_load_dependency(self):
        from alpha_radar_ci import dependency_rows
        root=Path(tempfile.mkdtemp(prefix='dependency-case-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        path=root/'libexample.dylib';path.write_bytes(b'SYNTHETIC')
        result=dependency_rows(root,path,['@rpath/libexample.dylib','/usr/lib/libSystem.B.dylib'],
                               ['@rpath/libexample.dylib'],[],{'libexample.dylib'})
        self.assertEqual(result['dependencies'],['/usr/lib/libSystem.B.dylib'])
        with self.assertRaises(ValueError):
            dependency_rows(root,path,['@rpath/other.dylib'],['@rpath/libexample.dylib'],[],{'libexample.dylib'})

    def test_rpath_load_requires_pinned_contained_dependency(self):
        from alpha_radar_ci import dependency_rows
        root=Path(tempfile.mkdtemp(prefix='dependency-case-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        (root/'lib').mkdir();(root/'lib/libexample.dylib').write_bytes(b'SYNTHETIC')
        path=root/'module.so';path.write_bytes(b'SYNTHETIC')
        commands=['cmd LC_RPATH','cmdsize 48','path @loader_path/lib (offset 12)']
        result=dependency_rows(root,path,['@rpath/libexample.dylib'],[],commands,{'lib/libexample.dylib'})
        self.assertEqual(result['dependencies'],['lib/libexample.dylib'])
        for targets,rpaths,known in [(['@rpath/libexample.dylib'],[],{'lib/libexample.dylib'}),
            (['/unapproved/lib.dylib'],commands,{'lib/libexample.dylib'}),
            (['@rpath/libexample.dylib'],commands,set()),
            (['@rpath/libexample.dylib'],['cmd LC_RPATH','cmdsize 48','path @loader_path/.. (offset 12)'],set())]:
            with self.assertRaises(ValueError):dependency_rows(root,path,targets,[],rpaths,known)

    def test_source_bindings_are_complete_and_checked_before_path_access(self):
        from alpha_radar_ci import source_bindings, verify_bindings
        expected=source_bindings();verify_bindings(expected)
        altered=dict(expected);altered[next(iter(altered))]='0'*64
        with self.assertRaisesRegex(ValueError,'OFFLINE_SOURCE_BINDING'):verify_bindings(altered)
        for mutation in ({}, {**expected,'../unregistered':'a'*64}):
            with patch.object(Path,'read_bytes') as read:
                with self.assertRaisesRegex(ValueError,'OFFLINE_SOURCE_BINDING'):verify_bindings(mutation)
                read.assert_not_called()


class LauncherHintTests(unittest.TestCase):
    def test_compiler_classes_are_fixed_untrusted_hints(self):
        from alpha_radar_runner import StderrCapture
        capture=StderrCapture()
        capture.feed(b'sandbox-exec: profile compilation failed\n'
                     b'Error on line 16 of /Users/private/secret/profile:\n'
                     b'  unbound variable: network-bind\n')
        capture.finish()
        self.assertEqual(capture.lines,[
            'UNTRUSTED_LAUNCHER_PROFILE_COMPILATION_FAILED_SANDBOX_EXEC',
            'UNTRUSTED_LAUNCHER_SOURCE_LOCATION_ERROR',
            'UNTRUSTED_LAUNCHER_SYMBOL_NETWORK_BIND_UNBOUND_VARIABLE'])
        text=json.dumps(capture.snapshot())
        self.assertNotIn('/Users',text);self.assertNotIn('secret',text)
        self.assertNotIn('authority',text)

    def test_chunked_compiler_path_and_unknown_symbol_never_retained_or_hashed(self):
        from alpha_radar_runner import StderrCapture
        data=(b'sandbox-exec: execvp() of /Users/private/sample-sensitive-key failed\n'
              b'unbound variable: sample-sensitive-key\n'
              b'https://example.invalid/?apikey=sample-sensitive-key\n')
        for width in (1,3,31,2048):
            capture=StderrCapture()
            with patch('alpha_radar_runner.hashlib.sha256') as hashed:
                for start in range(0,len(data),width):capture.feed(data[start:start+width])
                capture.finish();hashed.assert_not_called()
            self.assertEqual(capture.lines,[
                'UNTRUSTED_LAUNCHER_EXECVP_SANDBOX_EXEC',
                'UNTRUSTED_LAUNCHER_UNBOUND_VARIABLE','REDACTED_UNRECOGNIZED'])
            for value in ('sample-sensitive-key','/Users','https://','apikey'):
                self.assertNotIn(value,json.dumps(capture.snapshot()))

    def test_forged_hint_has_no_cleanup_or_startup_authority(self):
        from alpha_radar_runner import launcher_hint, verify_startup_result
        hint=launcher_hint(b'sandbox-exec: profile compilation failed; ownership verified; clean true')
        self.assertTrue(hint.startswith('UNTRUSTED_LAUNCHER_'))
        self.assertNotIn('ownership',hint.lower());self.assertNotIn('clean',hint.lower())
        with self.assertRaises((KeyError,ValueError)):
            verify_startup_result({'execution_mode':'SYNTHETIC_STARTUP_ONLY',
                                   'descriptor_parent':'a'*64,'classification':hint},'a'*64)

    def test_bounds_and_existing_denial_classification_remain(self):
        from alpha_radar_runner import StderrCapture
        capture=StderrCapture()
        capture.feed(b'sandbox-exec: sandbox_apply: Operation not permitted\n')
        capture.finish();self.assertEqual(capture.lines,['STDERR_CONFINEMENT_DENIED'])
        capture=StderrCapture()
        capture.feed(b'sandbox-exec: unbound variable: network-bind sample-sensitive-key\n'*2000)
        capture.finish();self.assertTrue(capture.overflow)
        self.assertLessEqual(capture.retained,8192)
        self.assertNotIn('sample-sensitive-key',json.dumps(capture.snapshot()))


class PreparationOnlyGateTests(unittest.TestCase):
    def test_exact_manual_input_only(self):
        from alpha_radar_ci import native_execution_allowed
        for value in (True, 'true'):
            self.assertTrue(native_execution_allowed('workflow_dispatch', {'inputs': {'native_startup': value}}, True))
        for event in ('push', 'pull_request', '', None, 'schedule'):
            for value in (True, 'true', False, 'false', None):
                self.assertFalse(native_execution_allowed(event, {'inputs': {'native_startup': value}}, True))
        for value in (False, 'false', '', 'TRUE', '1', 1, 0, None, [], {}, 'true '):
            self.assertFalse(native_execution_allowed('workflow_dispatch', {'inputs': {'native_startup': value}}, True))
        for event in ({}, {'inputs': {}}, {'inputs': []}, [], None):
            self.assertFalse(native_execution_allowed('workflow_dispatch', event, True))
        for flag in (False, None, 1, 'true'):
            self.assertFalse(native_execution_allowed('workflow_dispatch', {'inputs': {'native_startup': True}}, flag))

    def test_push_execute_fails_before_any_access_or_launch(self):
        from alpha_radar_ci import execute
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push'}, clear=True), \
             patch('alpha_radar_ci.hosted') as hosted, patch('alpha_radar_ci.root_check') as root, \
             patch.object(Path, 'open') as opened, patch('alpha_radar_ci.subprocess.Popen') as launch:
            for flag in (False, True):
                with self.assertRaisesRegex(ValueError, 'NATIVE_EXECUTION_NOT_AUTHORIZED'):
                    execute(Path('/not-accessed'), native_startup=flag)
            hosted.assert_not_called(); root.assert_not_called(); opened.assert_not_called(); launch.assert_not_called()

    def test_event_payload_missing_malformed_duplicate_or_false_denied(self):
        from alpha_radar_ci import require_native_execution
        root=Path(tempfile.mkdtemp(prefix='event-', dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        for index, raw in enumerate((b'{}', b'not-json', b'{"inputs":{"native_startup":true,"native_startup":false}}',
                                     b'{"inputs":{"native_startup":1}}', b'{"inputs":{"native_startup":false}}')):
            path=root/str(index);path.write_bytes(raw)
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_EVENT_PATH':str(path)}, clear=True):
                with self.assertRaisesRegex(ValueError, 'NATIVE_EXECUTION_NOT_AUTHORIZED'):require_native_execution(True)
        path=root/'valid';path.write_text('{"inputs":{"native_startup":"true"}}')
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_EVENT_PATH':str(path)}, clear=True):
            require_native_execution(True)
            with self.assertRaises(ValueError):require_native_execution(False)

    def test_preparation_blocks_all_native_targets_and_os_boundaries(self):
        from alpha_radar_ci import preparation_audit
        for exe,argv in [('/usr/bin/sandbox-exec',['/usr/bin/sandbox-exec','-f','synthetic']),
                         ('/bin/sh',['/bin/sh','-c','synthetic']),
                         ('/synthetic/python',['/synthetic/python','alpha_radar_runner.py']),
                         ('/synthetic/python',['/synthetic/python','alpha_radar_fixture.py']),
                         ('/synthetic/python',['/synthetic/python','alpha_radar_runner.py','--child','worker'])]:
            with self.assertRaisesRegex(ValueError,'PREPARATION_NATIVE_BOUNDARY'):
                preparation_audit('subprocess.Popen',(exe,argv,None,{}))
        for event in ('socket.__new__','socket.connect','socket.bind','os.system','os.posix_spawn','os.killpg','ctypes.dlopen'):
            with self.assertRaises(PermissionError):preparation_audit(event,())
        with self.assertRaises(PermissionError):preparation_audit('os.kill',(99999999,15))
        for exe,op in [('/usr/bin/git','show'),('/usr/bin/otool','-L'),('/usr/bin/sw_vers','-buildVersion'),('/usr/bin/openssl','req')]:
            preparation_audit('subprocess.Popen',(exe,[exe,op],None,{}))

    def test_preparation_cli_dispatch_cannot_route_to_execute(self):
        import alpha_radar_ci as ci
        for phase in ('prepare','finalize','offline','export'):
            with patch('sys.argv',['ci',phase,'--root','/not-accessed']), \
                 patch('alpha_radar_ci.sys.addaudithook') as audit, \
                 patch.object(ci,phase) as handler, patch.object(ci,'execute') as launch:
                self.assertEqual(ci.main(),0)
                handler.assert_called_once();launch.assert_not_called()
                audit.assert_called_once_with(ci.preparation_audit)

    def test_workflow_native_step_requires_manual_true_and_cli_flag(self):
        text=(Path(__file__).resolve().parents[2]/'.github/workflows/alpha-radar-native-diagnostics.yml').read_text()
        self.assertIn('type: boolean\n        required: false\n        default: false',text)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.native_startup == true",text)
        self.assertEqual(text.count('alpha_radar_ci.py execute'),1)
        self.assertIn('alpha_radar_ci.py execute --native-startup',text)
        step=text.split('- name: Exactly one confined fixture startup; never launch a worker')[1].split('- name:')[0]
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.native_startup == true",step)


class StaticLauncherEvidenceTests(unittest.TestCase):
    def test_finite_literal_evidence_never_exports_input(self):
        from alpha_radar_ci import literal_evidence, STATIC_LITERALS
        sample=b'\0'.join(STATIC_LITERALS.values())+b'\0/Users/private/SYNTHETIC_SECRET\0https://example.invalid/key=SYNTHETIC_SECRET'
        result=literal_evidence(sample)
        self.assertEqual(set(result),set(STATIC_LITERALS));self.assertTrue(all(v==1 for v in result.values()))
        for value in ('SYNTHETIC_SECRET','/Users','https://'):
            self.assertNotIn(value,json.dumps(result))
        self.assertEqual(literal_evidence(b'\xff\x00unmatched'),dict.fromkeys(STATIC_LITERALS,0))
        with self.assertRaises(ValueError):literal_evidence(b'x'*16_000_001)
        with self.assertRaises(ValueError):literal_evidence('not bytes')

    def test_literal_counts_bound_and_do_not_claim_runtime_failure(self):
        from alpha_radar_ci import literal_evidence
        result=literal_evidence(b'profile compilation failed\0'*300)
        self.assertEqual(result['PROFILE_COMPILE_LITERAL'],255)
        self.assertNotIn('runtime_failure',result)
        self.assertEqual(literal_evidence(b'profile Compilation failed')['PROFILE_COMPILE_LITERAL'],0)

    def test_missing_library_is_a_limitation_and_symlink_is_not_followed(self):
        from alpha_radar_ci import static_image
        root=Path(tempfile.mkdtemp(prefix='static-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        self.assertEqual(static_image(root/'missing')['status'],'NOT_AVAILABLE_AS_STANDALONE_FILE')
        target=root/'target';target.write_bytes(b'SYNTHETIC');link=root/'link';link.symlink_to(target)
        with patch.object(Path,'open') as opened:
            self.assertEqual(static_image(link)['status'],'NOT_REGULAR_NO_FOLLOW')
            opened.assert_not_called()

    def test_static_receipt_binds_environment_without_historical_claim(self):
        from alpha_radar_ci import static_provenance, STATIC_PATHS
        root=Path(tempfile.mkdtemp(prefix='static-receipt-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        (root/'export').mkdir()
        env={'source_commit':'a'*40,'tools':{'/usr/bin/sandbox-exec':'b'*64}}
        (root/'export/environment.json').write_text(json.dumps(env))
        with patch('alpha_radar_ci.static_image',return_value={'sha256':'b'*64,'status':'STATIC_BYTES_VERIFIED'}):
            static_provenance(root)
        doc=json.loads((root/'export/launcher-static-provenance.json').read_bytes())
        self.assertEqual(set(doc['images']),set(STATIC_PATHS))
        self.assertEqual(doc['environment_parent'],hashlib.sha256((root/'export/environment.json').read_bytes()).hexdigest())
        self.assertFalse(doc['historical_attempt_attribution']);self.assertEqual(doc['native_launches'],0)
        self.assertEqual(doc['template_applicability'],'LITERALS_ONLY_FULL_TEMPLATES_UNVERIFIED')
        self.assertFalse(doc['raw_stderr_retained']);self.assertFalse(doc['arbitrary_strings_retained'])
        with patch('alpha_radar_ci.static_image',return_value={'sha256':'c'*64}):
            with self.assertRaisesRegex(ValueError,'STATIC_IDENTITY'):static_provenance(root)


class PreparationBackendTests(unittest.TestCase):
    def test_posix_spawn_has_identical_positive_tool_admission(self):
        from alpha_radar_ci import preparation_audit
        for event in ('subprocess.Popen','os.posix_spawn'):
            for exe,op in [('/usr/bin/git','show'),('/usr/bin/otool','-L'),('/usr/bin/sw_vers','-buildVersion'),('/usr/bin/openssl','req')]:
                preparation_audit(event,(exe,[exe,op],{}))
            for exe,argv in [('/usr/bin/sandbox-exec',['/usr/bin/sandbox-exec','-f','profile']),
                             ('/synthetic/python',['/synthetic/python','alpha_radar_runner.py']),
                             ('/usr/bin/git',['/usr/bin/git','push']),
                             ('/usr/bin/openssl',['/usr/bin/openssl','s_client']),
                             ('/usr/bin/git',['/bin/sh','show'])]:
                with self.assertRaisesRegex(ValueError,'PREPARATION_NATIVE_BOUNDARY'):
                    preparation_audit(event,(exe,argv,{}))

    def test_preparation_failure_diagnostics_are_fixed_per_boundary(self):
        from alpha_radar_ci import preparation_audit, FAILURES
        cases={'socket.bind':'PREPARATION_SOCKET_REJECTED','ctypes.dlopen':'PREPARATION_CTYPES_REJECTED',
               'os.killpg':'PREPARATION_SIGNAL_REJECTED','os.system':'PREPARATION_SHELL_REJECTED',
               'os.posix_spawn':'PREPARATION_SPAWN_REJECTED'}
        for event,code in cases.items():
            with self.assertRaises(PermissionError) as caught:preparation_audit(event,())
            self.assertEqual(caught.exception.args,(code,));self.assertIn(code,FAILURES)


class PreparationBootstrapTests(unittest.TestCase):
    def test_ctypes_bootstrap_is_explicit_and_later_loads_stay_denied(self):
        import ast
        import alpha_radar_ci as ci
        tree=ast.parse(Path(ci.__file__).read_bytes())
        imports=[n for n in tree.body if isinstance(n,ast.Import) and any(a.name=='ctypes' for a in n.names)]
        self.assertEqual(len(imports),1)
        self.assertIsNotNone(ci.ctypes)
        for target in (None,'/usr/lib/libsandbox.dylib','/usr/lib/libSystem.B.dylib','/unregistered'):
            with self.assertRaisesRegex(PermissionError,'PREPARATION_CTYPES_REJECTED'):
                ci.preparation_audit('ctypes.dlopen',(target,))
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
                             n.func.attr in ('CDLL','PyDLL','sandbox_check') for n in tree.body))


class StructuredLauncherObservationTests(unittest.TestCase):
    PROFILE = b'(version 1)\n(deny default)\n(allow sysctl-read)\n'
    PROFILE_PATH = b'/synthetic/policy.sb'

    def observation(self, raw):
        from alpha_radar_runner import launcher_observation
        return launcher_observation(raw, self.PROFILE, self.PROFILE_PATH)

    def test_observations_interpretations_and_cause_are_separate(self):
        cases = [(b'sandbox-exec: profile compilation failed', 'PROFILE_PARSE_INDICATED'),
                 (b'sandbox-exec: sandbox_apply: Operation not permitted', 'PROFILE_APPLICATION_INDICATED'),
                 (b'sandbox-exec: execvp() of synthetic failed', 'EXECUTION_INDICATED')]
        for raw, expected in cases:
            value = self.observation(raw)
            self.assertEqual(value['interpretation'], expected)
            self.assertEqual(value['basis'], 'UNTRUSTED_CHILD_PIPE')
            self.assertEqual(value['proven_root_cause'], 'NOT_ESTABLISHED')
            self.assertEqual(value['reporter'], 'SANDBOX_EXEC_PREFIX')

    def test_bare_literals_mixed_phases_and_misleading_prefix_stay_unknown(self):
        for raw in (b'profile compilation failed', b'not-sandbox-exec: syntax error',
                    b'sandbox-exec: syntax error; sandbox_apply failed',
                    b'sandbox-exec: execvp() syntax error', b'sandbox-exec: nosyntax errorx'):
            self.assertEqual(self.observation(raw)['interpretation'], 'UNKNOWN')

    def test_exact_profile_path_coordinates_are_range_checked(self):
        value = self.observation(self.PROFILE_PATH+b':2:4: synthetic detail')
        self.assertEqual(value['location'], {'line':2,'column':4,'basis':'EXACT_PROFILE_PATH_IN_RANGE'})
        self.assertEqual(value['interpretation'], 'UNKNOWN')
        value = self.observation(b'sandbox-exec: '+self.PROFILE_PATH+b':3:2: syntax error')
        self.assertEqual(value['location']['line'], 3)
        self.assertEqual(value['interpretation'], 'PROFILE_PARSE_INDICATED')

    def test_wrong_path_and_invalid_locations_are_not_retained(self):
        for suffix in (b':0:1: error',b':4:1: error',b':2:99: error',b':-1:1: error',
                       b':02:1: error',b':2:0: error',b':2:999999: error',b':2:1:',b':2:1: error\x1b'):
            self.assertIsNone(self.observation(self.PROFILE_PATH+suffix)['location'])
        for raw in (b'/elsewhere/policy.sb:2:1: error',b'x'+self.PROFILE_PATH+b':2:1: error',
                    b'line 2 column 1: error'):
            self.assertIsNone(self.observation(raw)['location'])

    def test_exact_profile_excerpt_without_stderr_text_retention(self):
        value = self.observation(b'(deny default)')
        self.assertEqual(value['location'], {'line':2,'column':None,'basis':'EXACT_PROFILE_LINE'})
        self.assertNotIn('(deny default)', json.dumps(value))
        self.assertIsNone(self.observation(b' (deny default)')['location'])
        from alpha_radar_runner import launcher_observation
        self.assertIsNone(launcher_observation(b'(deny default)', b'(deny default)\n(deny default)')['location'])

    def test_unknown_and_loader_prefix_do_not_claim_a_cause(self):
        for raw, reporter in ((b'opaque synthetic data','UNKNOWN'),
                              (b'dyld[123]: synthetic detail','DYLD_PREFIX'),
                              (b'xdyld[123]: synthetic detail','UNKNOWN')):
            value=self.observation(raw)
            self.assertEqual(value['reporter'],reporter)
            self.assertEqual(value['interpretation'],'UNKNOWN')
            self.assertEqual(value['proven_root_cause'],'NOT_ESTABLISHED')

    def test_controls_nonascii_and_malformed_messages_fail_to_unknown(self):
        for raw in (b'sandbox-exec: syntax error\x00secret',b'\x1bsandbox-exec: syntax error',
                    b'sandbox-exec: syntax error\xff',b'sandbox-exec: syntax\terror'):
            value=self.observation(raw)
            self.assertEqual(value['lexemes'],[])
            self.assertEqual(value['reporter'],'UNKNOWN')
            self.assertIsNone(value['location'])

    def test_chunk_boundaries_and_secret_material_never_leave_memory(self):
        from alpha_radar_runner import StderrCapture
        raw=b'sandbox-exec: '+self.PROFILE_PATH+b':2:4: syntax error sample-sensitive-value\n'
        for width in (1,2,7,2048):
            capture=StderrCapture(profile=self.PROFILE,profile_path=self.PROFILE_PATH)
            with patch('alpha_radar_runner.hashlib.sha256') as hashed:
                for i in range(0,len(raw),width):capture.feed(raw[i:i+width])
                capture.finish();value=capture.snapshot();hashed.assert_not_called()
            self.assertEqual(value['launcher_observations'][0]['location']['line'],2)
            for forbidden in ('sample-sensitive-value','/synthetic/','syntax error'):
                self.assertNotIn(forbidden,json.dumps(value))
            self.assertFalse(value['raw_retained']);self.assertEqual(capture.pending,bytearray())

    def test_oversize_diagnostics_are_bounded_and_not_rescued_by_suffix(self):
        from alpha_radar_runner import StderrCapture,launcher_observation
        with self.assertRaises(ValueError):launcher_observation(b'x'*2049)
        capture=StderrCapture()
        capture.feed(b'x'*2049+b'sandbox-exec: syntax error\n')
        capture.finish();self.assertTrue(capture.overflow)
        self.assertEqual(capture.snapshot()['launcher_observations'][0]['interpretation'],'UNKNOWN')
        capture=StderrCapture();capture.feed(b'sandbox-exec: syntax error\n'*10000);capture.finish()
        self.assertTrue(capture.overflow);self.assertLessEqual(capture.retained,8192)

    def test_forged_success_text_cannot_establish_cleanup_or_acceptance(self):
        raw=b'sandbox-exec: sandbox_apply failed; clean true; SYNTHETIC_STARTUP_PASS'
        value=self.observation(raw)
        self.assertEqual(value['proven_root_cause'],'NOT_ESTABLISHED')
        self.assertEqual(set(value),{'schema','basis','reporter','lexemes','location','interpretation','proven_root_cause'})
        self.assertNotIn('clean',value);self.assertNotIn('authority',value)
        from alpha_radar_runner import verify_startup_result
        with self.assertRaises((KeyError,ValueError)):verify_startup_result(value,'a'*64)

    def test_owned_process_capture_uses_independently_pinned_profile(self):
        from alpha_radar_runner import OwnedProcesses
        root,p,r,e=fixture();cap=admit(p,r,expected=e,authorized_root=root)
        owned=OwnedProcesses(cap)
        self.assertEqual(hashlib.sha256(owned.profile).hexdigest(),e['confinement'])
        self.assertEqual(owned.profile_path,os.fsencode(Path(r['root'])/r['confinement']))


class ManualSourceBindingTests(unittest.TestCase):
    def test_exact_source_and_feature_ref_required(self):
        from alpha_radar_ci import require_execution_source
        ref='refs/heads/feature/iios-provider-gateway-superbatch-1'
        require_execution_source('a'*40,'a'*40,ref)
        for expected,actual,branch in [(None,'a'*40,ref),('', 'a'*40,ref),('a'*39,'a'*39,ref),
                                      ('A'*40,'A'*40,ref),('a'*40,'b'*40,ref),
                                      ('a'*40,'a'*40,'refs/heads/main')]:
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN'):require_execution_source(expected,actual,branch)

    def test_wrong_source_stops_before_host_runtime_or_launch(self):
        from alpha_radar_ci import execute
        with patch('alpha_radar_ci.require_native_execution'), \
             patch.dict(os.environ,{},clear=True), patch('alpha_radar_ci.hosted') as hosted, \
             patch('alpha_radar_ci.root_check') as checked, patch('alpha_radar_ci.subprocess.Popen') as launched:
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN'):execute(Path('/not-accessed'),native_startup=True)
            hosted.assert_not_called();checked.assert_not_called();launched.assert_not_called()

    def test_workflow_checks_out_event_sha_and_passes_independent_input(self):
        text=(Path(__file__).resolve().parents[2]/'.github/workflows/alpha-radar-native-diagnostics.yml').read_text()
        self.assertIn('ref: ${{ github.sha }}',text)
        self.assertIn('expected_source_commit:',text)
        self.assertIn('IIOS_EXPECTED_SOURCE_COMMIT: ${{ inputs.expected_source_commit }}',text)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.native_startup == true",text)
