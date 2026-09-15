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
        self.assertEqual(len(uses),6)
        self.assertEqual(len(set(uses)),3)
        for value in set(uses): self.assertEqual(uses.count(value),2)
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


class ProfileProbeTests(unittest.TestCase):
    def sanitized(self, raw, **kwargs):
        from alpha_radar_ci import sanitize_probe_stderr
        return sanitize_probe_stderr(raw, {'/synthetic/runtime/python': 'INTERPRETER',
            '/synthetic/runtime': 'RUNTIME', '/synthetic/workspace': 'WORKSPACE',
            '/synthetic/tmp/profile.sb': 'PROFILE', '/synthetic/tmp': 'TEMP'}, **kwargs)

    def test_known_paths_replaced_longest_first(self):
        raw = b'sandbox-exec: /synthetic/tmp/profile.sb:10:2: unbound variable: ip\n'
        value = self.sanitized(raw)
        self.assertEqual(value['diagnostic'], 'sandbox-exec: <PROFILE>:10:2: unbound variable: ip\n')
        self.assertEqual(value['interpretation'], 'PROFILE_COMPILE_OUTPUT')
        self.assertEqual(raw, b'sandbox-exec: /synthetic/tmp/profile.sb:10:2: unbound variable: ip\n')
        for path, expected in (('/synthetic/runtime/python', 'INTERPRETER'),
                               ('/synthetic/runtime', 'RUNTIME'), ('/synthetic/workspace', 'WORKSPACE'),
                               ('/synthetic/tmp', 'TEMP')):
            self.assertEqual(self.sanitized(('error: "'+path+'"').encode())['diagnostic'], 'error: "<'+expected+'>"')

    def test_path_suffix_and_unregistered_path_rejected(self):
        for raw in (b'error: /synthetic/runtime/private/name', b'error: /unregistered/name',
                    b'error: /synthetic/runtime-other', b'error: C:\\private\\name'):
            value = self.sanitized(raw)
            self.assertEqual(value['status'], 'REJECTED'); self.assertIsNone(value['diagnostic'])

    def test_secret_like_input_rejected_entirely(self):
        for raw in (b'api_key=SYNTHETIC_NOT_A_KEY', b'Bearer SYNTHETIC', b'password: synthetic',
                    b'token=synthetic', b'https://example.invalid', b'error: user@example.invalid',
                    b'error: A1b2C3d4E5f6G7h8', b'error: 1234567890123456'):
            self.assertEqual(self.sanitized(raw)['status'], 'REJECTED')
            self.assertIsNone(self.sanitized(raw)['diagnostic'])

    def test_controls_non_ascii_and_oversize_rejected(self):
        for raw in (b'error:\x1b[0m', b'error:\r', b'error:\t', b'error:\x00', b'error:\x7f',
                    b'error:\xff', b'a'*4097):
            self.assertIsNone(self.sanitized(raw)['diagnostic'])
        self.assertEqual(self.sanitized(b'error', overflow=True)['reason'], 'SIZE')

    def test_unknown_and_mixed_output_cannot_prove_root_cause(self):
        self.assertEqual(self.sanitized(b'sandbox-exec: failed')['interpretation'], 'UNKNOWN')
        self.assertEqual(self.sanitized(b'unbound variable: ip\nsandbox_apply failed')['interpretation'], 'UNKNOWN')
        self.assertEqual(self.sanitized(b'unknownprivateword')['status'], 'REJECTED')
        self.assertEqual(self.sanitized(b'')['diagnostic'], '')

    def test_chunked_secret_and_path_checked_as_complete_payload(self):
        for parts in ((b'api_', b'key=', b'SYNTHETIC'),
                      (b'error: /synthetic/', b'runtime/private', b'/name')):
            self.assertIsNone(self.sanitized(b''.join(parts))['diagnostic'])
        parts = (b'error: /synthetic/', b'tmp/profile.sb:2:1: ', b'unbound variable: ip')
        self.assertIn('<PROFILE>', self.sanitized(b''.join(parts))['diagnostic'])

    def test_matrix_is_bounded_subsets_of_exact_policy(self):
        from alpha_radar_ci import profile_matrix, profile_clauses
        from alpha_radar_runner import confinement_profile
        exact = confinement_profile(Path('/synthetic/runtime'), Path('/synthetic/output'),
                                    Path('/synthetic/runtime/python'), 38493)
        matrix = profile_matrix(exact); forms = profile_clauses(exact)
        self.assertEqual(matrix[0], ('EXACT', exact)); self.assertEqual(len(matrix), 10)
        self.assertLessEqual(len(matrix), 12)
        for name, value in matrix:
            self.assertIn('(deny default)', value)
            self.assertNotIn('(allow default)', value)
            self.assertNotIn('0.0.0.0', value)
            if name != 'EXACT':
                self.assertTrue(all(line in exact for line in value.splitlines()))
        core = matrix[1][1]
        self.assertNotIn('network-', core); self.assertNotIn('file-write', core)
        self.assertEqual(matrix[-1][0], 'READ_WITHOUT_EXEC')
        self.assertNotIn('process-exec', matrix[-1][1])
        self.assertEqual(len(forms), 10)

    def test_changed_or_malformed_profile_rejected(self):
        from alpha_radar_ci import profile_matrix
        from alpha_radar_runner import confinement_profile
        exact = confinement_profile(Path('/synthetic/runtime'), Path('/synthetic/output'),
                                    Path('/synthetic/runtime/python'), 38493)
        for value in (exact+'(', exact.replace('(deny default)', '(allow default)'),
                      exact.replace('network-bind', 'unknown-filter'), exact+'arbitrary'):
            with self.assertRaisesRegex(ValueError, 'PROFILE_PROBE_PROFILE'): profile_matrix(value)

    def test_spawn_boundary_accepts_only_fixed_command_environment_and_cwd(self):
        from alpha_radar_ci import probe_spawn_audit, PROBE_ENV, PROBE_TAIL
        argv = ('/usr/bin/sandbox-exec', '-f', '/synthetic/profile.sb', '/synthetic/python', *PROBE_TAIL)
        audit = probe_spawn_audit(argv, '/synthetic')
        audit('subprocess.Popen', (argv[0], argv, '/synthetic', dict(PROBE_ENV)))
        cases = [(argv[0], (*argv[:-1], 'import os'), '/synthetic', PROBE_ENV),
                 ('/bin/sh', ('/bin/sh',), '/synthetic', PROBE_ENV),
                 (argv[0], argv, '/different', PROBE_ENV),
                 (argv[0], argv, '/synthetic', {**PROBE_ENV, 'SYNTHETIC_CREDENTIAL': 'REJECT'}),
                 (argv[0], (*argv[:4], 'alpha_radar_fixture.py'), '/synthetic', PROBE_ENV)]
        for args in cases:
            with self.assertRaises(ValueError): audit('subprocess.Popen', args)
        for event in ('os.posix_spawn', 'socket.__new__', 'socket.bind', 'ctypes.dlopen', 'os.killpg'):
            with self.assertRaises((ValueError, PermissionError)): audit(event, (argv[0], argv, {}))

    def test_invalid_event_stops_before_host_paths_and_child(self):
        import alpha_radar_ci as ci
        for event in ('workflow_dispatch', 'pull_request', 'schedule', ''):
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME': event}, clear=True), \
                 patch.object(ci, 'hosted') as host, patch.object(ci, 'probe_child') as child:
                with self.assertRaisesRegex(ValueError, 'PROFILE_PROBE_EVENT'): ci.profile_probe(Path('/not-accessed'))
                host.assert_not_called(); child.assert_not_called()

    def test_minimal_child_bounded_capture_and_no_signals(self):
        import alpha_radar_ci as ci
        child = MagicMock(); child.poll.return_value = 65
        with patch.object(ci.subprocess, 'Popen', return_value=child) as launch, \
             patch.object(ci.os, 'set_blocking'), patch.object(ci.os, 'read', side_effect=[b'error: ', b'failed', b'']), \
             patch.object(ci.time, 'sleep'):
            raw, overflow, code, eof = ci.probe_child(['/synthetic/python', *ci.PROBE_TAIL], Path('/synthetic'))
        self.assertEqual(raw, b'error: failed'); self.assertFalse(overflow); self.assertEqual(code, 65); self.assertTrue(eof)
        self.assertEqual(launch.call_args.kwargs['env'], ci.PROBE_ENV)
        child.kill.assert_not_called(); child.terminate.assert_not_called(); child.stderr.close.assert_called_once()

    def test_overflow_never_retains_over_four_kib(self):
        import alpha_radar_ci as ci
        child = MagicMock(); child.poll.return_value = 65
        with patch.object(ci.subprocess, 'Popen', return_value=child), patch.object(ci.os, 'set_blocking'), \
             patch.object(ci.os, 'read', side_effect=[b'x'*1024]*4+[b'x', b'']), patch.object(ci.time, 'sleep'):
            raw, overflow, _, _ = ci.probe_child(['/synthetic/python'], Path('/synthetic'))
        self.assertEqual(len(raw), 4096); self.assertTrue(overflow)
        self.assertIsNone(self.sanitized(raw, overflow=overflow)['diagnostic'])

    def test_timeout_preserves_unverified_status_without_signal(self):
        import alpha_radar_ci as ci
        child = MagicMock(); child.poll.return_value = None
        with patch.object(ci.subprocess, 'Popen', return_value=child), patch.object(ci.os, 'set_blocking'), \
             patch.object(ci.time, 'monotonic', side_effect=[0, 11]):
            raw, overflow, code, eof = ci.probe_child(['/synthetic/python'], Path('/synthetic'))
        self.assertIsNone(code); self.assertFalse(eof); self.assertEqual(raw, b'')
        child.kill.assert_not_called(); child.terminate.assert_not_called()

    def test_probe_cli_cannot_route_to_fixture_execution(self):
        import alpha_radar_ci as ci
        with patch('sys.argv', ['ci', 'profile-probe', '--root', '/not-accessed']), \
             patch.object(ci, 'profile_probe') as handler, patch.object(ci, 'execute') as fixture:
            self.assertEqual(ci.main(), 0); handler.assert_called_once(); fixture.assert_not_called()

    def test_workflow_push_no_longer_dispatches_closed_compiler_series(self):
        text = (Path(__file__).resolve().parents[2]/'.github/workflows/alpha-radar-native-diagnostics.yml').read_text()
        self.assertNotIn('alpha_radar_ci.py profile-probe', text)
        step = text.split('- name: Manual lifecycle only; no sandbox or worker')[1].split('- name:')[0]
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.lifecycle_only == true && inputs.native_startup != true", step)
        self.assertIn('alpha_radar_ci.py lifecycle --lifecycle-only', step)
        self.assertLess(text.index('alpha_radar_ci.py offline'), text.index('alpha_radar_ci.py lifecycle'))

    def test_probe_call_graph_cannot_invoke_fixture_or_worker(self):
        import ast
        import alpha_radar_ci as ci
        tree = ast.parse(Path(ci.__file__).read_text())
        names = {'profile_probe', 'profile_matrix', 'profile_clauses', 'probe_child', 'probe_spawn_audit', 'sanitize_probe_stderr'}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(functions), len(names))
        for node in functions:
            for call in (v for v in ast.walk(node) if isinstance(v, ast.Call)):
                target = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, 'attr', '')
                self.assertNotIn(target, ('execute', 'supervise', 'fixture_exchange', 'bind', 'connect', 'Session', 'exec', 'eval'))
        self.assertEqual(ci.PROBE_TAIL, ('-I', '-S', '-B', '-c', 'pass'))

    def mocked_matrix(self, outcomes):
        import alpha_radar_ci as ci
        from alpha_radar_runner import confinement_profile
        root = Path(tempfile.mkdtemp(prefix='probe-matrix-', dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        runtime = root/'runtime'; interpreter = runtime/'python/bin/python3.13'
        interpreter.parent.mkdir(parents=True); interpreter.write_bytes(b'SYNTHETIC_NOT_EXECUTED')
        (root/'export').mkdir()
        commit = 'a'*40
        exact = confinement_profile(runtime, root/'execution-output', interpreter, 38493)
        (runtime/'confinement.sb').write_text(exact)
        environment = {'source_commit': commit, 'tools': {'/usr/bin/sandbox-exec': 'b'*64}}
        docs = {'environment.json': environment, 'offline-results.json': {'success': True, 'skipped': [],
                'executed': 1, 'collected': 1, 'source_bindings': {}}, 'prepared-pins.json': {'descriptor_sha256': 'c'*64}}
        for name, value in docs.items(): (root/'export'/name).write_text(json.dumps(value))
        d = {'package': {'authority': AUTHORITY}, 'native_tools': environment['tools'],
             'runtime': {'interpreter': 'python/bin/python3.13', 'files': [{'path': 'python/bin/python3.13',
                          'sha256': ci.digest(interpreter.read_bytes())}]},
             'expected': {'confinement': ci.digest(exact.encode())}}
        env = {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/feature/iios-provider-gateway-superbatch-1',
               'GITHUB_SHA': commit}
        with patch.dict(os.environ, env), patch.object(ci, 'hosted'), patch.object(ci, 'root_check'), \
             patch.object(ci, 'command', side_effect=[commit.encode(), b'', b'/usr/bin/true:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n']), \
             patch.object(ci, 'fixed_probe_executable', return_value={'sha256': 'd'*64}), patch.object(ci, 'verify_bindings'), \
             patch('alpha_radar_runner.read_descriptor', return_value=d), patch('alpha_radar_runner.descriptor_schema'), \
             patch('alpha_radar_admission.verify_inputs'), patch('alpha_radar_runner.verify_tools'), \
             patch.object(ci.sys, 'executable', str(interpreter)), patch.object(ci.sys, 'addaudithook') as boundary, \
             patch.object(ci, 'probe_child', side_effect=outcomes) as child, patch.object(ci, 'execute') as fixture:
            error = None
            try: ci.profile_probe(root)
            except ValueError as exc: error = exc.args[0]
            fixture.assert_not_called(); boundary.assert_called_once()
            for call in child.call_args_list:
                self.assertEqual(tuple(call.args[0][3:]), ('/usr/bin/true',))
            return root, child.call_count, error

    def test_successful_core_still_runs_complete_independent_grammar_matrix(self):
        root, count, error = self.mocked_matrix([(b'', False, 0, True)]*10)
        self.assertIsNone(error); self.assertEqual(count, 10)
        value = json.loads((root/'export/profile-probe-summary.json').read_text())
        self.assertFalse(value['new_fixture_attempt']); self.assertEqual(value['authority'], AUTHORITY)
        self.assertFalse((root/'execution-output').exists())

    def test_failed_exact_profile_runs_bounded_subtractive_matrix(self):
        root, count, error = self.mocked_matrix([(b'sandbox-exec: failed', False, 65, True)]*10)
        self.assertIsNone(error); self.assertEqual(count, 10)
        rows = list((root/'export').glob('profile-probe-??.json')); self.assertEqual(len(rows), 10)
        for row in rows:
            value = json.loads(row.read_text())
            self.assertEqual(value['root_cause'], 'NOT_ESTABLISHED')
            self.assertEqual(value['fixture_launches'], 0); self.assertEqual(value['worker_launches'], 0)

    def test_failed_sanitization_or_timeout_publishes_safe_failure_then_stops(self):
        for outcome, expected in (((b'api_key=SYNTHETIC', False, 65, True), 'PROFILE_PROBE_SANITIZATION'),
                                  ((b'', False, None, False), 'PROFILE_PROBE_TIMEOUT')):
            root, count, error = self.mocked_matrix([outcome])
            self.assertEqual(error, expected); self.assertEqual(count, 1)
            saved = (root/'export/profile-probe-01.json').read_text()
            self.assertNotIn('api_key', saved); self.assertNotIn('SYNTHETIC\"', saved)
            self.assertFalse((root/'export/profile-probe-summary.json').exists())


class ProfileProbeLineFramingTests(unittest.TestCase):
    def test_control_line_is_rejected_without_losing_valid_independent_line(self):
        from alpha_radar_ci import sanitize_probe_lines, sanitize_probe_stderr
        raw = b'sandbox-exec: unbound variable: network-bind\n\tUNREVIEWED SYNTHETIC LINE\n'
        self.assertEqual(sanitize_probe_stderr(raw, {})['status'], 'REJECTED')
        value = sanitize_probe_lines(raw, {})
        self.assertEqual(value['status'], 'PARTIALLY_SANITIZED')
        self.assertEqual(value['diagnostic'], 'sandbox-exec: unbound variable: network-bind')
        self.assertEqual(value['rejected_lines'], [{'line': 2, 'reason': 'CONTROL'}])
        self.assertFalse(value['complete_launcher_message'])
        self.assertEqual(value['root_cause'], 'NOT_ESTABLISHED')

    def test_no_control_normalization_or_rejoining_contaminated_fragments(self):
        from alpha_radar_ci import sanitize_probe_lines
        for marker in (b'\x00', b'\t', b'\r', b'\x1b', b'\x7f'):
            raw = b'error: failed\nsecretprefix'+marker+b'syntheticsuffix'
            value = sanitize_probe_lines(raw, {})
            # Sensitive material anywhere rejects the entire message.
            self.assertEqual(value['status'], 'REJECTED'); self.assertIsNone(value['diagnostic'])
            value = sanitize_probe_lines(b'error: failed\nprofile'+marker+b'compilation failed', {})
            self.assertEqual(value['diagnostic'], 'error: failed')
            self.assertEqual(value['interpretation'], 'UNKNOWN')
            self.assertNotIn(marker.decode(), value['diagnostic'])

    def test_split_sensitive_words_never_leave_rejected_lines(self):
        from alpha_radar_ci import sanitize_probe_lines
        raw = b'error: failed\napi_\tkey=SYNTHETIC_NOT_A_KEY'
        value = sanitize_probe_lines(raw, {})
        self.assertEqual(value['diagnostic'], 'error: failed')
        self.assertNotIn('SYNTHETIC_NOT_A_KEY', json.dumps(value))
        self.assertNotIn('api_', json.dumps(value))

    def test_unknown_paths_and_tokens_never_retained_by_partial_framing(self):
        from alpha_radar_ci import sanitize_probe_lines
        raw = b'error: failed\n\tframing\n/unknown/private\nA1b2C3d4E5f6G7h8'
        value = sanitize_probe_lines(raw, {})
        self.assertEqual(value['diagnostic'], 'error: failed')
        self.assertEqual(len(value['rejected_lines']), 3)
        self.assertNotIn('/unknown', json.dumps(value)); self.assertNotIn('A1b2', json.dumps(value))

    def test_no_valid_line_size_failure_and_sensitive_content_stay_rejected(self):
        from alpha_radar_ci import sanitize_probe_lines
        for raw, overflow in ((b'\tbad\nunknownword', False), (b'error: failed\npassword=SYNTHETIC\t', False),
                              (b'error: failed\n'+b'x'*4096, False), (b'error: failed\n\t', True)):
            value = sanitize_probe_lines(raw, {}, overflow=overflow)
            self.assertEqual(value['status'], 'REJECTED'); self.assertIsNone(value['diagnostic'])

    def test_clean_message_contract_unchanged(self):
        from alpha_radar_ci import sanitize_probe_lines, sanitize_probe_stderr
        for raw in (b'', b'error: failed', b'unbound variable: ip', b'unknownword'):
            self.assertEqual(sanitize_probe_lines(raw, {}), sanitize_probe_stderr(raw, {}))

    def test_chunk_boundaries_do_not_rescue_invalid_lines(self):
        from alpha_radar_ci import sanitize_probe_lines
        raw = b'error: failed\n\tunsafe\n/unknown/path'
        expected = sanitize_probe_lines(raw, {})
        for index in range(len(raw)+1):
            self.assertEqual(sanitize_probe_lines(b''.join((raw[:index], raw[index:])), {}), expected)
        self.assertEqual(expected['diagnostic'], 'error: failed')

    def test_partial_message_keeps_rejections_visible_through_bounded_matrix(self):
        first = (b'sandbox-exec: unbound variable: network-bind\n\tUNREVIEWED\n', False, 65, True)
        root, count, error = ProfileProbeTests.mocked_matrix(self, [first]+[(b'', False, 0, True)]*9)
        self.assertIsNone(error); self.assertEqual(count, 10)
        value = json.loads((root/'export/profile-probe-01.json').read_text())
        self.assertEqual(value['diagnostic']['status'], 'PARTIALLY_SANITIZED')
        self.assertEqual(value['diagnostic']['rejected_lines'], [{'line': 2, 'reason': 'CONTROL'}])
        self.assertEqual(value['root_cause'], 'NOT_ESTABLISHED')


class SeatbeltGrammarTests(unittest.TestCase):
    def matrix(self):
        from alpha_radar_ci import grammar_matrix
        from alpha_radar_runner import confinement_profile
        return grammar_matrix(confinement_profile(Path('/synthetic/runtime'), Path('/synthetic/output'),
            Path('/synthetic/runtime/python'), 38493))

    def test_ten_independent_profiles_and_no_broad_network_grant(self):
        rows = self.matrix()
        self.assertEqual([n for n, _ in rows], ['MINIMAL', 'BARE_OUTBOUND', 'TCP_OUTBOUND',
            'BARE_INBOUND', 'TCP_INBOUND', 'BARE_BIND', 'TCP_BIND', 'TCP_COMBINED',
            'IP_NEGATIVE_CONTROL', 'EXEC_DENIED_CONTROL'])
        for name, text in rows:
            self.assertIn('(deny default)', text)
            self.assertNotIn('file-write', text)
            self.assertNotIn('python', text)
            for line in text.splitlines():
                if line.startswith('(allow network-'):
                    self.assertIn('"127.0.0.1:38493"', line)
                    self.assertIn(' tcp ' if name != 'IP_NEGATIVE_CONTROL' else ' ip ', line)
            self.assertEqual(text.count('(allow process-exec'), 0 if name == 'EXEC_DENIED_CONTROL' else 1)
        for index, op in ((1, 'outbound'), (3, 'inbound'), (5, 'bind')):
            self.assertIn('(deny network-'+op+')', rows[index][1])
            self.assertNotIn('(allow network-', rows[index][1])
        self.assertEqual(rows[7][1].count('(allow network-'), 3)
        self.assertEqual(rows[8][1].count(' ip '), 3)

    def test_negative_control_cannot_substitute_public_address(self):
        from alpha_radar_ci import grammar_matrix
        from alpha_radar_runner import confinement_profile
        exact = confinement_profile(Path('/synthetic/runtime'), Path('/synthetic/output'),
                                    Path('/synthetic/runtime/python'), 38493)
        for value in (exact.replace('127.0.0.1', '0.0.0.0'), exact.replace('38493', '443'),
                      exact.replace(' ip ', ' tcp ')):
            with self.assertRaisesRegex(ValueError, 'PROFILE_PROBE_PROFILE'): grammar_matrix(value)

    def classified(self, text='', code=65, eof=True, status='SANITIZED'):
        from alpha_radar_ci import classify_probe
        return classify_probe({'status': status, 'diagnostic': text}, code, eof, self.matrix()[2][1])

    def test_zero_exit_of_pinned_noop_proves_execution_and_compile(self):
        value = self.classified(code=0)
        self.assertEqual(value['profile_compilation'], 'PROFILE_COMPILE_ACCEPTED')
        self.assertEqual(value['command'], 'COMMAND_EXECUTED')

    def test_exact_execution_denial_is_not_syntax_failure(self):
        value = self.classified("sandbox-exec: execvp() of '<DIAGNOSTIC_EXECUTABLE>' failed: Operation not permitted\n", 71)
        self.assertEqual(value['profile_compilation'], 'PROFILE_COMPILE_ACCEPTED')
        self.assertEqual(value['command'], 'COMMAND_DENIED')

    def test_numeric_exits_empty_stderr_and_timeout_preserve_unknown(self):
        for code, eof in ((65, True), (71, True), (1, True), (None, False), (0, False), (True, True)):
            value = self.classified(code=code, eof=eof)
            self.assertEqual(value['profile_compilation'], 'UNKNOWN')
            self.assertEqual(value['command'], 'UNKNOWN')

    def test_sigabrt_never_proves_compilation_or_command_bootstrap_stage(self):
        for text in ('', '<PROFILE>:5:26:', 'profile compilation failed'):
            value = self.classified(text, -6)
            self.assertEqual(value['profile_compilation'], 'UNKNOWN')
            self.assertEqual(value['command'], 'COMMAND_ABORTED')
            self.assertEqual(value['basis'], 'SIGNAL_OBSERVED_STAGE_UNKNOWN')

    def test_location_without_semantic_evidence_remains_unknown(self):
        value = self.classified('<PROFILE>:5:26:')
        self.assertEqual(value['source_locations'], [{'line': 5, 'column': 26}])
        self.assertEqual(value['profile_compilation'], 'UNKNOWN')

    def test_location_bounds_and_no_private_path_retention(self):
        for text in ('<PROFILE>:0:1:', '<PROFILE>:99999:1:', '<PROFILE>:5:99999:',
                     '<PROFILE>:5:-1:', '/unreviewed/location:5:1:'):
            value = self.classified(text)
            self.assertEqual(value['source_locations'], [])
            self.assertNotIn('/unreviewed', json.dumps(value))

    def test_complete_consistent_compile_diagnostic_only(self):
        text = '<PROFILE>:5:26:\nerror: unbound variable: remote'
        value = self.classified(text)
        self.assertEqual(value['profile_compilation'], 'PROFILE_COMPILE_REJECTED')
        self.assertEqual(value['command'], 'UNKNOWN')
        for changed, code, status in ((text, 0, 'SANITIZED'), (text, 71, 'SANITIZED'),
                (text, 65, 'PARTIALLY_SANITIZED'), ('prefix '+text, 65, 'SANITIZED'),
                (text+'\nsandbox-exec: execvp', 65, 'SANITIZED')):
            value = self.classified(changed, code, status=status)
            self.assertEqual(value['profile_compilation'], 'UNKNOWN')
            self.assertEqual(value['command'], 'UNKNOWN')

    def test_sensitive_malformed_and_oversize_output_never_classified(self):
        from alpha_radar_ci import sanitize_probe_lines, classify_probe
        for raw in (b'api_key=SYNTHETIC', b'x'*4097, b'\x00', b'\xff', b'/unknown/path:5:1:'):
            value = sanitize_probe_lines(raw, {})
            self.assertEqual(value['status'], 'REJECTED')
            result = classify_probe(value, 0, True, self.matrix()[0][1])
            self.assertEqual(result['profile_compilation'], 'UNKNOWN')
            self.assertEqual(result['command'], 'UNKNOWN')

    def test_fixed_executable_identity_rejects_writes_aliases_and_replacement(self):
        import alpha_radar_ci as ci
        from types import SimpleNamespace
        def identity(**kwargs):
            return SimpleNamespace(**dict({'st_mode': 0o100555, 'st_uid': 0, 'st_nlink': 1,
                'st_dev': 1, 'st_ino': 2, 'st_size': 4, 'st_mtime_ns': 5}, **kwargs))
        path = Path(ci.PROBE_EXECUTABLE)
        with patch.object(Path, 'resolve', return_value=path), patch.object(Path, 'read_bytes', return_value=b'noop'), \
             patch.object(ci.os, 'statvfs', return_value=SimpleNamespace(f_flag=ci.os.ST_RDONLY)):
            with patch.object(Path, 'lstat', return_value=identity()):
                self.assertEqual(ci.fixed_probe_executable()['sha256'], ci.digest(b'noop'))
            for bad in (identity(st_mode=0o100775), identity(st_uid=501), identity(st_nlink=2),
                        identity(st_mode=0o120555)):
                with patch.object(Path, 'lstat', return_value=bad):
                    with self.assertRaisesRegex(ValueError, 'STATIC_IDENTITY'): ci.fixed_probe_executable()
            with patch.object(Path, 'lstat', side_effect=[identity(), identity(st_ino=3)]):
                with self.assertRaisesRegex(ValueError, 'STATIC_IDENTITY'): ci.fixed_probe_executable()

    def test_fixed_executable_requires_readonly_system_volume(self):
        import alpha_radar_ci as ci
        from types import SimpleNamespace
        st = SimpleNamespace(st_mode=0o100755, st_uid=0, st_nlink=1)
        with patch.object(Path, 'resolve', return_value=Path(ci.PROBE_EXECUTABLE)), \
             patch.object(Path, 'lstat', return_value=st), \
             patch.object(ci.os, 'statvfs', return_value=SimpleNamespace(f_flag=0)), \
             patch.object(Path, 'read_bytes') as read:
            with self.assertRaisesRegex(ValueError, 'STATIC_IDENTITY'): ci.fixed_probe_executable()
            read.assert_not_called()


class LifecycleOnlyTests(unittest.TestCase):
    def context(self):
        return {'GITHUB_ACTIONS':'true', 'RUNNER_ENVIRONMENT':'github-hosted', 'RUNNER_OS':'macOS',
            'RUNNER_ARCH':'ARM64','GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_ID':'12345',
            'GITHUB_SHA':'a'*40,'GITHUB_REF':'refs/heads/feature/iios-provider-gateway-superbatch-1'}

    def cap(self):
        root,p,r,e=fixture();cap=admit(p,r,expected=e,authorized_root=root)
        return cap, {**e,'lifecycle_descriptor':'c'*64}

    def test_manual_mode_requires_exact_true_and_rejects_conflicts(self):
        from alpha_radar_ci import lifecycle_execution_allowed
        for enabled in (True,'true'):
            self.assertTrue(lifecycle_execution_allowed('workflow_dispatch',{'inputs':{'lifecycle_only':enabled,'native_startup':'false'}},True))
        for event in ('push','schedule','pull_request',''):
            self.assertFalse(lifecycle_execution_allowed(event,{'inputs':{'lifecycle_only':True}},True))
        for bad in (False,'false',1,0,None,'TRUE',[],{}):
            self.assertFalse(lifecycle_execution_allowed('workflow_dispatch',{'inputs':{'lifecycle_only':bad}},True))
        for bad in (True,'true',0,1,None):
            self.assertFalse(lifecycle_execution_allowed('workflow_dispatch',{'inputs':{'lifecycle_only':True,'native_startup':bad}},True))

    def test_push_or_missing_selection_fails_before_access(self):
        import alpha_radar_ci as ci
        for event,flag in (('push',True),('workflow_dispatch',False)):
            with patch.dict(os.environ,{'GITHUB_EVENT_NAME':event},clear=True), patch.object(Path,'read_bytes') as read, patch.object(ci.subprocess,'Popen') as child:
                with self.assertRaises(ValueError):ci.execute_lifecycle(Path('/not-accessed'),explicit_request=flag)
                read.assert_not_called();child.assert_not_called()

    def test_environment_positive_membership_rejects_proxy_and_credentials(self):
        from alpha_radar_runner import lifecycle_environment,LIFECYCLE_ENV
        env=lifecycle_environment(self.context())
        self.assertEqual(set(env),set(self.context())|set(LIFECYCLE_ENV)|{'__CF_USER_TEXT_ENCODING'})
        self.assertEqual(env['__CF_USER_TEXT_ENCODING'],f'0x{os.getuid():X}:0x0:0x0')
        with patch.dict(os.environ,{'__CF_USER_TEXT_ENCODING':'SYNTHETIC_REJECT'}):
            self.assertEqual(lifecycle_environment(self.context()),env)
        from alpha_radar_runner import failure_category
        self.assertEqual(failure_category(ValueError('LIFECYCLE_ENVIRONMENT')),'LIFECYCLE_ENVIRONMENT')
        for key in ('HTTPS_PROXY','ALL_PROXY','GITHUB_TOKEN','API_KEY','KEYCHAIN_SELECTOR','DYLD_INSERT_LIBRARIES','__CF_USER_TEXT_ENCODING'):
            with self.assertRaises(ValueError):lifecycle_environment({**self.context(),key:'SYNTHETIC_REJECT'})
        for key,value in (('RUNNER_ENVIRONMENT','self-hosted'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_SHA','main'),('RUNNER_OS','Linux')):
            with self.assertRaises(ValueError):lifecycle_environment({**self.context(),key:value})

    def test_guard_rejects_nonloopback_dns_sockets_processes_and_signals(self):
        import alpha_radar_runner as run
        for host in ('localhost','127.0.0.2','::1','192.0.2.1','0.0.0.0'):
            with self.assertRaises(ValueError):run.lifecycle_audit('/synthetic/runtime','/synthetic/out',(host,38493),'fixture')
        audit,_=run.lifecycle_audit('/synthetic/runtime','/synthetic/out',('127.0.0.1',38493),'fixture')
        audit('socket.bind',(None,('127.0.0.1',38493)))
        audit('socket.__new__',(None,run.socket.AF_INET,run.socket.SOCK_STREAM,0))
        for event,args in [('socket.connect',(None,('127.0.0.1',38493))),('socket.bind',(None,('127.0.0.1',38494))),
            ('socket.bind',(None,('192.0.2.1',38493))),('socket.getaddrinfo',('localhost',38493)),
            ('socket.gethostbyaddr',('127.0.0.1',)),('subprocess.Popen',('/bin/sh',[],None,{})),
            ('os.kill',(12345,15)),('os.killpg',(12345,9)),('ctypes.dlopen',('/usr/lib/libSystem.B.dylib',))]:
            with self.assertRaises((ValueError,PermissionError)):audit(event,args)

    def test_guard_write_containment_and_unregistered_descriptor(self):
        from alpha_radar_runner import lifecycle_audit
        audit,opened=lifecycle_audit('/synthetic/runtime','/synthetic/out',('127.0.0.1',38493),'fixture')
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
        audit('open',('/synthetic/out/lc-startup.json',None,flags))
        for path,bits in [('/synthetic/runtime/lc-bad.json',flags),('/synthetic/out/../lc-bad.json',flags),
                          ('/synthetic/out/lc-bad.json',os.O_WRONLY|os.O_TRUNC),('/synthetic/out/raw.log',flags)]:
            with self.assertRaises(ValueError):audit('open',(path,None,bits))
        with self.assertRaises(ValueError):opened('lc-bad.json',flags,dir_fd=987654)
        with self.assertRaises(ValueError):audit('open',('/Library/Keychains/login.keychain-db','r',os.O_RDONLY))

    def test_supervisor_guard_one_child_and_bounded_inspection_only(self):
        from alpha_radar_runner import lifecycle_audit,lifecycle_environment,LIFECYCLE_ENV
        argv=['/synthetic/runtime/python','-B','/synthetic/runtime/runner','--ci-lifecycle-only']
        audit,_=lifecycle_audit('/synthetic/runtime','/synthetic/out',('127.0.0.1',38493),'supervisor',
            launch_argv=argv,child_pid=lambda:12345,context=self.context())
        args=(argv[0],argv,'/synthetic/out',lifecycle_environment(self.context()))
        audit('subprocess.Popen',args)
        with self.assertRaises(ValueError):audit('subprocess.Popen',args)
        audit('subprocess.Popen',('/bin/ps',['/bin/ps','-ww','-p','12345','-o','lstart='],None,LIFECYCLE_ENV))
        for cmd in (['/bin/ps','-e'],['/bin/ps','-ww','-p','1','-o','lstart='],['/usr/bin/sandbox-exec','-p','synthetic'],['/bin/sh','-c','synthetic']):
            with self.assertRaises(ValueError):audit('subprocess.Popen',(cmd[0],cmd,None,LIFECYCLE_ENV))

    def test_receipt_scope_fields_cannot_be_relabelled_or_used_in_production(self):
        from alpha_radar_runner import lifecycle_envelope,verify_lifecycle_receipt,LIFECYCLE_FLAGS,verify_startup_result
        parents={'lifecycle_descriptor':'a'*64};doc=lifecycle_envelope({'classification':'LIFECYCLE_PASS'},parents)
        self.assertEqual(verify_lifecycle_receipt(doc,content_hash(doc),parents),doc['value'])
        for key,value in LIFECYCLE_FLAGS.items():self.assertIs(type(doc[key]),type(value));self.assertEqual(doc[key],value)
        with self.assertRaises(ValueError):verify_envelope(doc,content_hash(doc),parents=parents)
        with self.assertRaises((ValueError,KeyError)):verify_startup_result(doc['value'],'a'*64)
        for scope in ('SYNTHETIC_TEST_ONLY','SYNTHETIC_NATIVE_QUALIFIED','LIVE_QUALIFICATION'):
            bad={**doc,'scope':scope}
            with self.assertRaises(ValueError):verify_lifecycle_receipt(bad,content_hash(bad),parents)
        with self.assertRaises(ValueError):verify_lifecycle_receipt(doc,content_hash(doc),{'lifecycle_descriptor':'b'*64})

    def test_independently_computed_ack_hash_rejects_forgery_and_duplicate_publication(self):
        from alpha_radar_runner import lifecycle_store,lifecycle_read
        cap,parents=self.cap();value={'event':'ACK','launch_parent':'a'*64,'startup_parent':'b'*64}
        lifecycle_store(cap,parents,'lc-ack.json',value)
        lifecycle_read(cap,parents,'lc-ack.json',value)
        with self.assertRaises(ValueError):lifecycle_read(cap,parents,'lc-ack.json',{**value,'startup_parent':'c'*64})
        with self.assertRaises(FileExistsError):lifecycle_store(cap,parents,'lc-ack.json',value)

    def test_lifecycle_runtime_and_fixture_changes_rejected(self):
        from alpha_radar_runner import lifecycle_descriptor,LIFECYCLE_SCOPE
        for change in ('runtime','fixture'):
            root,p,r,e=fixture()
            d={'schema':'iios-ci-native-lifecycle-v1','execution_mode':LIFECYCLE_SCOPE,'package':p,'runtime':r,
               'expected':e,'authorized_root':str(root),'native_tools':{},'maximum_duration_seconds':120,'context':self.context()}
            if change=='runtime':r['files'][0]['sha256']='b'*64
            else:p['fixture']['certificate_sha256']='b'*64
            with self.assertRaises(ValueError):lifecycle_descriptor(d)
            self.assertFalse(Path(p['root']).exists())

    def owned(self):
        from alpha_radar_runner import LifecycleOwnedProcesses,StderrCapture,lifecycle_store,lifecycle_startup_value
        cap,parents=self.cap();p,r,e=cap.documents();exe=str(Path(r['root'])/r['interpreter'])
        obs=ProcessObservation(12345,os.getpid(),'2026-09-14T12:00:00+00:00',exe,exe,r['files'][0]['sha256'],p['root'],(exe,))
        owned=LifecycleOwnedProcesses(cap,parents,inspect=lambda _:obs,pause=lambda _:None)
        child=MagicMock();child.pid=12345;child.poll.return_value=0
        entry={'child':child,'expected':{'pid':12345,'parent_pid':os.getpid(),'argv':(exe,),
            'cwd':p['root'],'executable':exe,'executable_hash':obs.executable_hash},'observation':dict(obs.__dict__),
            'launch_parent':'a'*64,'capture':StderrCapture()}
        owned.children['fixture']=entry
        value=lifecycle_startup_value(cap,'a'*64,entry['observation'])
        h=lifecycle_store(cap,parents,'lc-startup.json',value);owned.startup_pins['fixture']=('a'*64,h)
        lifecycle_store(cap,parents,'lc-child-exit.json',{'returncode':0})
        return owned,child,obs

    def test_cleanup_requires_owned_zero_exit_and_three_stable_observations(self):
        owned,child,_=self.owned();result=owned.cleanup(lambda:True)
        self.assertTrue(result['clean']);self.assertEqual(result['signals'],0)
        self.assertEqual(result['port_clear_observations'],[True]*3)
        child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_surviving_listener_or_unstable_clearance_fails(self):
        for samples in ([False]*3,[True,False,True]):
            owned,child,_=self.owned();values=iter(samples)
            self.assertFalse(owned.cleanup(lambda:next(values))['clean'])
            child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_early_exit_does_not_turn_port_clear_into_cleanup(self):
        owned,child,_=self.owned();child.poll.return_value=65;owned.children['fixture']['observation']=None
        result=owned.cleanup(lambda:True);self.assertFalse(result['clean'])
        self.assertEqual(result['remaining'],['fixture']);child.terminate.assert_not_called()

    def test_pid_reuse_and_identity_mismatch_prevent_stop_or_signal(self):
        for field,value in [('start_time','2026-09-14T12:00:01+00:00'),('parent_pid',1),('executable_hash','f'*64)]:
            owned,child,obs=self.owned();child.poll.return_value=None
            owned.inspect=lambda _,o=replace(obs,**{field:value}):o
            result=owned.cleanup(lambda:True);self.assertFalse(result['clean'])
            self.assertFalse((Path(owned.cap.documents()[0]['root'])/'lc-stop.json').exists())
            child.wait.assert_not_called();child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_cooperative_shutdown_failure_is_preserved_without_signal_fallback(self):
        import subprocess
        owned,child,_=self.owned();child.poll.return_value=None;child.wait.side_effect=subprocess.TimeoutExpired('SYNTHETIC',10)
        result=owned.cleanup(lambda:True);self.assertFalse(result['clean']);self.assertTrue(result['failures'])
        child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_tls_mismatch_keeps_scope_unqualified(self):
        from alpha_radar_runner import startup_tls
        cap,_=self.cap();owned=MagicMock();ctx=MagicMock();ctx.check_hostname=True;ctx.verify_mode=2
        channel=ctx.wrap_socket.return_value.__enter__.return_value;channel.getpeercert.return_value=b'WRONG_SYNTHETIC'
        with patch('alpha_radar_runner.ssl.create_default_context',return_value=ctx), \
             patch('alpha_radar_runner.ssl.PEM_cert_to_DER_cert',return_value=b'EXPECTED_SYNTHETIC'), \
             patch('alpha_radar_runner.socket.socket'):
            with self.assertRaises(ValueError):startup_tls(cap,owned)

    def test_lifecycle_call_graph_has_no_confinement_or_worker_execution(self):
        import ast,alpha_radar_runner as runner
        tree=ast.parse(Path(runner.__file__).read_text())
        for node in tree.body:
            if isinstance(node,ast.FunctionDef) and node.name in ('lifecycle_child','lifecycle_supervise','lifecycle_main'):
                calls=[v.func.id if isinstance(v.func,ast.Name) else getattr(v.func,'attr','') for v in ast.walk(node) if isinstance(v,ast.Call)]
                for bad in ('require_confinement','Session','fixture_exchange','supervise','child_main','kill','terminate'):
                    self.assertNotIn(bad,calls)
        self.assertIn('require_confinement(cap)',Path(runner.__file__).read_text())

    def test_live_admission_rejects_lifecycle_receipt(self):
        from alpha_radar_runner import lifecycle_envelope
        from provider_gateway_live_contract import verify_qualification_receipt
        doc=lifecycle_envelope({'result':'OBSERVED'},{'lifecycle_descriptor':'a'*64})
        with self.assertRaises((ValueError,KeyError,TypeError)):verify_qualification_receipt(doc,content_hash(doc),parents=doc['parents'])

    def orchestrated(self, failure=None):
        import alpha_radar_runner as run
        cap,unused=self.cap();p,r,e=cap.documents()
        d={'schema':'iios-ci-native-lifecycle-v1','execution_mode':run.LIFECYCLE_SCOPE,'package':p,'runtime':r,
           'expected':e,'authorized_root':cap.authorized_root,'native_tools':{},'maximum_duration_seconds':120,'context':self.context()}
        parents={**e,'lifecycle_descriptor':content_hash(d)}
        child=MagicMock();child.pid=12345;child.stderr=None;child.stdout=None
        child.stdin.closed=True;code=[None];child.poll.side_effect=lambda:code[0]
        observed=[None];owned_type=run.LifecycleOwnedProcesses
        def spawn(argv,**kwargs):
            self.assertNotIn('/usr/bin/sandbox-exec',argv);self.assertNotIn('worker',argv)
            self.assertEqual(kwargs['env'],run.lifecycle_environment(self.context()))
            observed[0]=ProcessObservation(child.pid,os.getpid(),'2026-09-14T12:00:00+00:00',' '.join(argv),
                argv[0],r['files'][0]['sha256'],str(kwargs['cwd']),tuple(argv))
            if failure=='early':
                code[0]=65;observed[0]=None
            else:
                run.lifecycle_store(cap,parents,'lc-startup.json',run.lifecycle_startup_value(cap,argv[-1],observed[0].__dict__))
            return child
        def waited(timeout):
            if failure=='shutdown':raise run.subprocess.TimeoutExpired('SYNTHETIC',timeout)
            run.lifecycle_store(cap,parents,'lc-child-exit.json',{'returncode':0});code[0]=0;return 0
        child.wait.side_effect=waited
        def ownership(cap,parents):return owned_type(cap,parents,inspect=lambda _:observed[0],pause=lambda _:None)
        listeners=[[],[(12345,'127.0.0.1:'+str(p['fixture']['port']))],[],[],[]]
        if failure=='early':listeners=[[],[],[],[]]
        with patch.dict(os.environ,run.lifecycle_environment(self.context()),clear=True), \
             patch.object(run,'verify_tools'),patch.object(run,'native_identity'), \
             patch.object(run,'LifecycleOwnedProcesses',side_effect=ownership), \
             patch.object(run,'lifecycle_audit',return_value=(lambda *_:None,os.open)), \
             patch.object(run.sys,'addaudithook'),patch.object(run,'listener_owners',side_effect=listeners), \
             patch.object(run,'startup_tls',side_effect=run.ssl.SSLError('SYNTHETIC') if failure=='tls' else None,
                          return_value={'hostname_verified':True,'http_requests':0,'protocol':'TLSv1.3'}) as tls:
            result=run.lifecycle_supervise(cap,d,popen=spawn)
            if failure=='early':tls.assert_not_called()
        child.kill.assert_not_called();child.terminate.assert_not_called()
        for path in Path(p['root']).glob('*.json'):
            doc=json.loads(path.read_text())
            for key,value in run.LIFECYCLE_FLAGS.items():self.assertEqual(doc[key],value)
        return result

    def test_mocked_complete_lifecycle_requires_every_gate(self):
        result=self.orchestrated()
        self.assertEqual(result['classification'],'LIFECYCLE_PASS')
        self.assertTrue(result['cleanup']['clean']);self.assertEqual(result['fixture_status']['exit_code'],0)
        self.assertIsNone(result['primary_failure']);self.assertIsNone(result['cleanup_failure'])

    def test_mocked_tls_failure_preserved_separately_from_successful_cleanup(self):
        result=self.orchestrated('tls')
        self.assertEqual(result['classification'],'LIFECYCLE_FAILED')
        self.assertEqual(result['primary_failure'],{'stage':'TLS_HANDSHAKE','category':'TLS_ERROR'})
        self.assertTrue(result['cleanup']['clean'])

    def test_mocked_early_exit_preserves_failure_without_claiming_cleanup(self):
        result=self.orchestrated('early')
        self.assertEqual(result['classification'],'LIFECYCLE_FAILED')
        self.assertEqual(result['fixture_status']['exit_code'],65)
        self.assertFalse(result['cleanup']['clean']);self.assertIsNotNone(result['primary_failure'])

    def test_mocked_cooperative_shutdown_failure_stays_failed(self):
        result=self.orchestrated('shutdown')
        self.assertEqual(result['classification'],'LIFECYCLE_FAILED')
        self.assertIsNone(result['primary_failure']);self.assertEqual(result['cleanup_failure'],'LIFECYCLE_CLEANUP_FAILED')


class ExportDependencyBoundaryTests(unittest.TestCase):
    def test_export_rejects_unpinned_dependencies_before_import(self):
        import alpha_radar_ci as ci
        root = Path(tempfile.mkdtemp(prefix='export-unpinned-'))
        (root/'export').mkdir()
        with self.assertRaises(FileNotFoundError):
            ci.export_dependencies(root)

    def test_fresh_export_gate_is_separate_from_mocked_offline(self):
        import alpha_radar_ci as ci
        workflow = (ci.REPO/'.github/workflows/alpha-radar-native-diagnostics.yml').read_text()
        self.assertIn('python -I -S -B tests/native/test_alpha_radar_export_process.py', workflow)
        self.assertIn('tests/native/test_alpha_radar_export_process.py', ci.binding_paths())
        import inspect
        self.assertIn("'subprocess.Popen'", inspect.getsource(ci.offline))
        self.assertIn("'OFFLINE_NATIVE_BOUNDARY'", inspect.getsource(ci.offline))


class LifecycleStdioTests(unittest.TestCase):
    def test_stdio_is_pipes_and_stdin_closed_before_registration(self):
        import inspect, alpha_radar_runner as run, alpha_radar_ci as ci
        text=inspect.getsource(run.lifecycle_supervise)
        self.assertNotIn('DEVNULL',text.split('child = popen')[1].split("stage = 'OWNERSHIP_REGISTER'")[0].split('#')[0])
        self.assertIn('stdin=subprocess.PIPE, stdout=subprocess.PIPE',text)
        self.assertLess(text.index('close_lifecycle_stdin(child)'),text.index("owned.register('fixture'"))
        self.assertNotIn('subprocess.DEVNULL',inspect.getsource(ci.execute_lifecycle))
        child=MagicMock();child.stdin.closed=True
        run.close_lifecycle_stdin(child);child.stdin.close.assert_called_once_with()
        child.stdin.closed=False
        with self.assertRaisesRegex(ValueError,'^LIFECYCLE_STDIO$'):run.close_lifecycle_stdin(child)

    def test_both_streams_nonblocking_sanitized_and_bounded(self):
        import alpha_radar_runner as run
        child=MagicMock();child.stdout.fileno.return_value=71;child.stderr.fileno.return_value=72
        with patch.object(run.os,'set_blocking') as nonblocking:
            capture=run.LifecycleStreams(child)
        self.assertEqual(nonblocking.call_args_list,[unittest.mock.call(71,False),unittest.mock.call(72,False)])
        capture.stderr.feed(b'RADAR_DIAG');capture.stderr.feed(b'NOSTIC: LIFECYCLE_WRITE\n')
        capture.stderr.feed(b'SYNTHETIC_SECRET_VALUE /synthetic/private/path\n')
        doc=json.dumps(capture.snapshot())
        self.assertNotIn('SYNTHETIC_SECRET_VALUE',doc);self.assertNotIn('/synthetic/private/path',doc)
        self.assertIn('STDERR_LIFECYCLE_WRITE',doc)
        capture.stdout.feed(b'unexpected\n')
        with self.assertRaisesRegex(ValueError,'^LIFECYCLE_STDOUT_UNEXPECTED$'):capture.check()
        for stream in (capture.stdout,capture.stderr):
            stream.feed(b'x'*70000)
            self.assertTrue(stream.overflow);self.assertLessEqual(len(stream.pending),2048)
            self.assertLessEqual(stream.retained,8192)
        with self.assertRaisesRegex(ValueError,'^DIAGNOSTIC_OVERFLOW$'):capture.check()

    def test_stream_drain_and_close_continue_after_individual_failure(self):
        import alpha_radar_runner as run
        child=MagicMock();child.stdout=None;child.stderr=None
        capture=run.LifecycleStreams(child)
        with patch.object(capture.stdout,'drain',side_effect=OSError),patch.object(capture.stderr,'drain') as second:
            with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_PIPE_FAILED'):capture.drain()
            second.assert_called_once_with()
        capture.stdout.stream=MagicMock();capture.stderr.stream=MagicMock()
        capture.stdout.stream.close.side_effect=OSError
        with self.assertRaisesRegex(ValueError,'DIAGNOSTIC_PIPE_FAILED'):capture.close()
        capture.stderr.stream.close.assert_called_once_with()

    def test_fixed_startup_category_and_no_devnull_write_allowance(self):
        import alpha_radar_runner as run
        self.assertEqual(run.failure_category(ValueError('LIFECYCLE_WRITE')),'LIFECYCLE_WRITE')
        audit,_=run.lifecycle_audit('/synthetic/runtime','/synthetic/out',('127.0.0.1',38493),'supervisor')
        for path in ('/dev/null','/dev/zero','/synthetic/other'):
            with self.assertRaisesRegex(ValueError,'^LIFECYCLE_WRITE$'):
                audit('open',(path,None,os.O_RDWR))

    def test_cleanup_stream_failure_preserves_other_cleanup_and_port_evidence(self):
        import alpha_radar_runner as run
        owned,child,_=LifecycleOnlyTests.owned(self)
        capture=run.LifecycleStreams(type('Child',(),{'stdout':None,'stderr':None})())
        capture.stdout.feed(b'UNEXPECTED\n');owned.children['fixture']['capture']=capture
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['clean']);self.assertEqual(result['port_clear_observations'],[True]*3)
        self.assertIn('LIFECYCLE_STDOUT_UNEXPECTED',result['diagnostic_failures'])
        child.kill.assert_not_called();child.terminate.assert_not_called()

    cap=LifecycleOnlyTests.cap


def fresh_stdio_validation(root):
    """Separate fresh-process gate; no fixture, worker, listener or provider.

    Each isolated parent installs the exact lifecycle audit. Its one admitted
    child is a fixed Python stdio command. The former DEVNULL failure must
    occur before subprocess.Popen's audit event (zero child launches).
    """
    import sys, subprocess, alpha_radar_ci as ci
    root=Path(root);ci.root_check(root)
    bindings=ci.source_bindings()
    code=ci.FRESH_STDIO_CODE
    rows=[];cases=[]
    expected_env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}
    for mode,expected in [('devnull','LIFECYCLE_WRITE'),('pipes',None),
                          ('stdout','LIFECYCLE_STDOUT_UNEXPECTED'),('overflow','DIAGNOSTIC_OVERFLOW')]:
        case=Path(tempfile.mkdtemp(prefix='stdio-'+mode+'-',dir=root))
        argv=[sys.executable,'-I','-S','-B','-c',code,str(ci.REPO/'tests/native'),str(ci.REPO/'BACK END/backend'),mode,str(case)]
        cases.append((mode,expected,case,argv))
    boundary=ci.fresh_stdio_boundary(root,cases,bindings)
    sys.addaudithook(boundary)
    for mode,expected,case,argv in cases:
        proc=ci.spawn_fresh_stdio(boundary,argv,case,expected_env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
        proc.stdin.close();proc.stdin=None
        raw,err=proc.communicate(timeout=30)
        # Only fixed sanitized output leaves memory, including on test failure.
        from alpha_radar_runner import StderrCapture
        diag=StderrCapture();diag.feed(err);diag.finish()
        valid=False;value=None
        try:
            value=json.loads(raw)
            valid=(proc.returncode==0 and value['category']==expected and
                   value['admitted_children']==(0 if mode=='devnull' else 1) and
                   value['child_returncode']==(None if mode=='devnull' else 0) and
                   value['stdin_closed']==(mode!='devnull') and
                   all(value[k]==0 for k in ('fixture_launches','worker_launches','requests')))
            if mode=='pipes':valid=valid and 'STDERR_LIFECYCLE_WRITE' in value['diagnostics']['stderr']['untrusted_stderr_hints']
        except (ValueError,KeyError,TypeError):pass
        row={'mode':mode,'success':valid,'parent_returncode':proc.returncode,'diagnostics':diag.snapshot(),
             'child_category':value.get('category') if isinstance(value,dict) and value.get('category') in (None,'LIFECYCLE_WRITE','LIFECYCLE_STDOUT_UNEXPECTED','DIAGNOSTIC_OVERFLOW') else 'UNCLASSIFIED_ERROR'}
        ci.document(root/'export'/('fresh-stdio-'+mode+'.json'),row);rows.append(row)
        ci.require(valid,'FRESH_STDIO_FAILED')
    ci.verify_bindings(bindings)
    ci.document(root/'export/fresh-stdio-results.json',{'scope':'FRESH_PROCESS_STDIO_ONLY','collected':4,
        'executed':len(rows),'success':True,'source_bindings':bindings,'fixture_launches':0,'worker_launches':0,'requests':0})


class FreshStdioAdmissionTests(unittest.TestCase):
    def inputs(self):
        import sys,alpha_radar_ci as ci
        root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        case=Path(tempfile.mkdtemp(prefix='stdio-pipes-',dir=root))
        argv=[sys.executable,'-I','-S','-B','-c',ci.FRESH_STDIO_CODE,
              str(ci.REPO/'tests/native'),str(ci.REPO/'BACK END/backend'),'pipes',str(case)]
        invocation=[str(Path(ci.__file__).resolve()),'offline','--root',str(root)]
        env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}
        return ci,root,case,argv,invocation,env

    def test_exact_phase_command_and_every_argv_mutation(self):
        ci,root,case,argv,invocation,env=self.inputs()
        args=(argv[0],argv,case,env)
        self.assertTrue(ci.fresh_stdio_shape('subprocess.Popen',args,invocation=invocation))
        for phase in ('execute','lifecycle','prepare','export','profile-probe','finalize'):
            with self.subTest(phase=phase),self.assertRaises(ValueError):
                ci.fresh_stdio_shape('subprocess.Popen',args,invocation=[invocation[0],phase,*invocation[2:]])
        for i in range(len(argv)):
            bad=list(argv);bad[i]='SYNTHETIC_ALTERED'
            with self.subTest(index=i),self.assertRaises(ValueError):
                ci.fresh_stdio_shape('subprocess.Popen',(argv[0],bad,case,env),invocation=invocation)
        for code in ('pass','import os; os.system("false")','alpha_radar_fixture.py',
                     'alpha_radar_runner.py','--child worker','security find-generic-password'):
            bad=list(argv);bad[5]=code
            with self.assertRaises(ValueError):ci.fresh_stdio_shape('subprocess.Popen',(argv[0],bad,case,env),invocation=invocation)

    def test_cwd_environment_alias_and_non_test_roots_rejected(self):
        ci,root,case,argv,invocation,env=self.inputs()
        for extra in ({'API_KEY':'SYNTHETIC'},{'HTTPS_PROXY':'https://invalid.example'},
                      {'PYTHONPATH':'/synthetic'},{'KEYCHAIN_SELECTOR':'SYNTHETIC'}):
            with self.assertRaises(ValueError):ci.fresh_stdio_shape('subprocess.Popen',(argv[0],argv,case,{**env,**extra}),invocation=invocation)
        for target in (root,root/'missing','/synthetic/outside'):
            with self.assertRaises(ValueError):ci.fresh_stdio_shape('subprocess.Popen',(argv[0],argv,target,env),invocation=invocation)
        alias=root/('stdio-pipes-'+'a'*8);alias.symlink_to(case,target_is_directory=True)
        bad=[*argv[:-1],str(alias)]
        with self.assertRaises(ValueError):ci.fresh_stdio_shape('subprocess.Popen',(argv[0],bad,alias,env),invocation=invocation)
        for event in ('os.posix_spawn','execute','socket.connect'):
            with self.assertRaises(ValueError):ci.fresh_stdio_shape(event,(argv[0],argv,case,env),invocation=invocation)

    def test_preparation_hook_rejects_dns_sockets_signals_and_fixture_commands(self):
        import alpha_radar_ci as ci
        for event in ('socket.getaddrinfo','socket.gethostbyname','socket.__new__','socket.connect','socket.bind'):
            with self.assertRaises(PermissionError):ci.preparation_audit(event,())
        for event,args in [('os.system',('SYNTHETIC',)),('os.kill',(99999999,15)),
                           ('os.killpg',(99999999,15))]:
            with self.assertRaises(PermissionError):ci.preparation_audit(event,args)
        for exe in ('/bin/sh','/usr/bin/security','/synthetic/alpha_radar_fixture.py','/synthetic/worker'):
            with self.assertRaises(ValueError):ci.preparation_audit('subprocess.Popen',(exe,[exe],None,{}))

    def test_pipe_options_are_mandatory_before_any_spawn(self):
        import alpha_radar_ci as ci,subprocess
        options={'stdin':subprocess.PIPE,'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'close_fds':True}
        for field in options:
            for bad in (None,subprocess.DEVNULL,False):
                altered={**options,field:bad}
                with patch.object(ci.subprocess,'Popen') as spawn:
                    with self.assertRaises(ValueError):ci.spawn_fresh_stdio(lambda *_:None,['SYNTHETIC'],Path('/synthetic'),{},**altered)
                    spawn.assert_not_called()

    def test_frozen_boundary_rejects_substitution_and_changed_source(self):
        import sys,alpha_radar_ci as ci
        ci,root,case,argv,invocation,env=self.inputs();cases=[]
        for mode in ('devnull','pipes','stdout','overflow'):
            target=case if mode=='pipes' else Path(tempfile.mkdtemp(prefix='stdio-'+mode+'-',dir=root))
            cases.append((mode,None,target,[*argv[:8],mode,str(target)]))
        with patch.object(sys,'argv',invocation):
            guard=ci.fresh_stdio_boundary(root,cases,ci.source_bindings())
            guard('subprocess.Popen',(argv[0],argv,case,env))
            other=Path(tempfile.mkdtemp(prefix='stdio-pipes-',dir=root))
            with self.assertRaises(ValueError):guard('subprocess.Popen',(argv[0],[*argv[:-1],str(other)],other,env))
            with patch.object(ci,'verify_bindings',side_effect=ValueError('OFFLINE_SOURCE_BINDING')):
                with self.assertRaisesRegex(ValueError,'OFFLINE_SOURCE_BINDING'):guard('subprocess.Popen',(argv[0],argv,case,env))

    def test_cli_installs_audit_before_mocked_handler_for_every_preparation_phase(self):
        import alpha_radar_ci as ci
        for phase in ('prepare','finalize','offline','export'):
            order=[]
            with patch('sys.argv',['ci',phase,'--root','/not-accessed']), \
                 patch.object(ci.sys,'addaudithook',side_effect=lambda _:order.append('AUDIT')), \
                 patch.object(ci,phase,side_effect=lambda *a:order.append('HANDLER')):
                self.assertEqual(ci.main(),0)
            self.assertEqual(order,['AUDIT','HANDLER'])


class FullSessionModeTests(unittest.TestCase):
    context = LifecycleOnlyTests.context

    def inputs(self):
        import alpha_radar_runner as run
        root,p,r,e=fixture();out=Path(p['root']).with_name('full-session-output')
        universe=p['plan']['universe'];cal=CALENDAR
        proposal=schedule(universe,content_hash(universe),cal,content_hash(cal),mode='FULL_OPPORTUNITY_RADAR',root=str(out/'journal'))
        p['root']=str(out)
        p['plan']=radar_plan(universe,content_hash(universe),cal,content_hash(cal),root=str(out/'journal'),
            opportunity_schedule=proposal,schedule_hash=content_hash(proposal))
        e['schedule']=content_hash(proposal);repin(p,r,e)
        package=run.full_package(p,e)
        d={'schema':'iios-ci-full-session-descriptor-v2','execution_mode':run.FULL_SCOPE,
            'package':p,'runtime':r,'expected':e,'authorized_root':str(root),'native_tools':{},
            'maximum_duration_seconds':6000,'context':self.context(),'session_package':package,
            'session_package_parent':content_hash(package)}
        d['validation_parent']='a'*64
        d['budget']={'schema':'iios-native-job-budget-v2','source_commit':d['context']['GITHUB_SHA'],
            'run_id':d['context']['GITHUB_RUN_ID'],'run_attempt':1,'start_monotonic':100,
            'prepared_monotonic':101,'hard_deadline':7240,'work_deadline':6466,'cleanup_deadline':6646,
            'deadline_unit':'MONOTONIC_NANOSECONDS','prepared_monotonic_ns':101_000_000_000,
            'startup_deadline_ns':466_000_000_000,
            'cleanup_seconds':180,'export_seconds':180,'real_clock_seconds':65,'work_seconds':6000}
        parents={**e,'session_package':content_hash(package),'full_descriptor':content_hash(d)}
        return root,p,r,e,d,parents

    def session(self):
        import alpha_radar_runner as run
        root,p,r,e,d,parents=self.inputs();cap=admit(p,r,expected=e,authorized_root=root)
        now=[utc(p['plan']['rows'][0]['valid_from'])];calls=[];waits=[]
        def wait(seconds):
            waits.append(seconds);run.advance_full_clock(session,now,seconds)
        def exchange(cap,slot,at):
            from urllib.parse import urlencode
            calls.append(slot);status,body=response(cap,f'/slot/{slot}?'+urlencode({'at':at}))
            return Response(status,body,'2026-09-14T12:00:00+00:00','2026-09-14T12:00:00+00:00')
        session=run.FullSession(cap,parents,clock=lambda:now[0].isoformat(),wait=wait,stop=lambda:False,exchange=exchange)
        session.logical_waits=waits
        return session,now,calls,d

    def journal(self,s):
        Path(s.p['plan']['root']).mkdir(mode=0o700)
        for row in s.p['plan']['rows']:Path(row['root']).mkdir(mode=0o700)

    def test_full_descriptor_exact_pins_and_distinct_package(self):
        import alpha_radar_runner as run
        root,p,r,e,d,parents=self.inputs()
        with patch.object(run,'verify_tools'):
            self.assertEqual(run.full_descriptor(d),parents)
        self.assertEqual(d['session_package']['maximum_requests'],475)
        self.assertEqual(d['session_package']['batch_sizes'],[100,100,100,100,100,17])
        with self.assertRaises(ValueError):run.lifecycle_descriptor(d)
        with self.assertRaises(ValueError):run.descriptor_schema(d)

    def test_each_independent_pin_is_required_before_output(self):
        import alpha_radar_runner as run
        for key in ('package','runtime','plan','universe','schedule','fixture','confinement'):
            root,p,r,e,d,_=self.inputs();d['expected'][key]='0'*64
            with patch.object(run,'verify_tools'),self.assertRaises(ValueError):run.full_descriptor(d)
            self.assertFalse(Path(p['root']).exists())

    def test_source_schema_mode_deadline_and_outer_package_mutations(self):
        import alpha_radar_runner as run
        for key,value in [('schema','other'),('execution_mode',run.LIFECYCLE_SCOPE),('maximum_duration_seconds',0),
                ('maximum_duration_seconds',901),('session_package_parent','0'*64)]:
            _,_,_,_,d,_=self.inputs();d[key]=value
            with patch.object(run,'verify_tools'),self.assertRaises(ValueError):run.full_descriptor(d)
        _,_,_,_,d,_=self.inputs();d['context']['GITHUB_SHA']='b'*40
        with patch.object(run,'verify_tools'),self.assertRaises(ValueError):run.full_descriptor(d)

    def test_universe_and_each_batch_mutation(self):
        import alpha_radar_runner as run
        for mutate in (lambda p:p['plan']['universe']['symbols'].pop(),
            lambda p:p['plan']['universe']['symbols'].reverse(),
            lambda p:p['plan']['universe']['symbols'].__setitem__(1,'S000'),
            lambda p:p['plan']['universe']['symbols'].__setitem__(1,'MU'),
            lambda p:p['plan']['universe']['symbols'].append('EXTRA'),
            lambda p:p['plan']['rows'].pop(),lambda p:p['plan']['rows'].append(deepcopy(p['plan']['rows'][0])),
            lambda p:p['plan']['rows'][1]['symbols'].reverse(),
            lambda p:p['plan']['rows'][6]['symbols'].append('S000'),
            lambda p:p['plan']['rows'].__setitem__(2,deepcopy(p['plan']['rows'][1]))):
            _,p,_,e,_,_=self.inputs();mutate(p)
            with self.assertRaises(ValueError):run.full_package(p,e)

    def test_manual_exact_boolean_mutual_exclusion(self):
        import alpha_radar_ci as ci
        for enabled in (True,'true'):
            self.assertTrue(ci.full_execution_allowed('workflow_dispatch',{'inputs':{'full_session_only':enabled}},True))
        for bad in (False,'false',1,None,'TRUE','yes',{},[]):
            self.assertFalse(ci.full_execution_allowed('workflow_dispatch',{'inputs':{'full_session_only':bad}},True))
        for key in ('native_startup','lifecycle_only','unexpected'):
            self.assertFalse(ci.full_execution_allowed('workflow_dispatch',{'inputs':{'full_session_only':True,key:True}},True))
        for event in ('push','pull_request','schedule',''):
            self.assertFalse(ci.full_execution_allowed(event,{'inputs':{'full_session_only':True}},True))
        self.assertFalse(ci.full_execution_allowed('workflow_dispatch',{'inputs':{'full_session_only':True}},False))

    def test_scope_replay_and_self_consistent_relabeling_rejected(self):
        import alpha_radar_runner as run
        _,_,_,_,_,parents=self.inputs();doc=run.full_envelope({'event':'SYNTHETIC'},parents,logical_time=CALENDAR['open'])
        self.assertEqual(run.verify_full_receipt(doc,content_hash(doc),parents),{'event':'SYNTHETIC'})
        for value in ({**parents,'full_descriptor':'0'*64},{**parents,'session_package':'0'*64}):
            with self.assertRaises(ValueError):run.verify_full_receipt(doc,content_hash(doc),value)
        for scope in (SCOPE,run.LIFECYCLE_SCOPE,'LIVE_QUALIFICATION'):
            forged={**doc,'scope':scope};forged['content_hash']=content_hash({k:v for k,v in forged.items() if k!='content_hash'})
            with self.assertRaises(ValueError):run.verify_full_receipt(forged,content_hash(forged),parents)
        with self.assertRaises(ValueError):run.verify_lifecycle_receipt(doc,content_hash(doc),parents)
        with self.assertRaises(ValueError):verify_envelope(doc,content_hash(doc),parents=parents)
        from provider_gateway_contract import verify_receipt
        with self.assertRaises(ValueError):verify_receipt(doc,content_hash(doc),parents=parents)

    def test_timing_evidence_separates_logical_actual_and_monotonic(self):
        import alpha_radar_runner as run
        _,_,_,_,_,parents=self.inputs()
        doc=run.full_envelope({'event':'SYNTHETIC'},parents,logical_time=CALENDAR['open'],
            actual_utc='2026-09-13T00:00:00+00:00',monotonic_seconds=42)
        self.assertEqual(doc['timing_proof'],'ACCELERATED_LOGICAL_TIME_ONLY')
        self.assertNotEqual(doc['logical_time'],doc['actual_utc']);self.assertEqual(doc['monotonic_seconds'],42)
        self.assertFalse(doc['production_qualified']);self.assertEqual(doc['os_confinement'],'UNQUALIFIED')
        for name in AUTHORITY:self.assertIs(doc[name],False)
        for bad in (-1,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):run.full_envelope({},parents,monotonic_seconds=bad)

    def test_pacing_fourth_start_boundary_and_rollback(self):
        import alpha_radar_runner as run
        gate=run.FullPacing()
        for tick in (0,0,0):gate.reserve(tick)
        for tick in (0,59.999):
            with self.assertRaisesRegex(ValueError,'FULL_ROLLING_RATE'):gate.reserve(tick)
        gate.reserve(60)
        with self.assertRaisesRegex(ValueError,'FULL_CLOCK_ROLLBACK'):gate.reserve(59)
        for bad in (-1,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):run.FullPacing().reserve(bad)

    def test_real_clock_scenario_mocked_only(self):
        import alpha_radar_runner as run
        clock=[100.0]
        def pause(seconds):clock[0]+=seconds
        value=run.full_real_clock_boundary(monotonic=lambda:clock[0],pause=pause)
        self.assertTrue(value['fourth_start_rejected']);self.assertGreaterEqual(value['elapsed_seconds'],60)
        self.assertFalse(value['full_day_wall_clock_proven']);self.assertEqual(value['market_requests'],0)
        ticks=iter([100,100,100,100,100,100,99])
        with self.assertRaisesRegex(ValueError,'FULL_CLOCK_ROLLBACK'):
            run.full_real_clock_boundary(monotonic=lambda:next(ticks),pause=lambda _:None)

    def test_runtime_fixture_public_path_and_credential_mutations(self):
        import alpha_radar_runner as run
        for mutate in (lambda d:d['package']['fixture'].update(address='8.8.8.8'),
            lambda d:d['package']['fixture'].update(server_name='localhost'),
            lambda d:d['package'].update(selector='IIOS_ALPHA_VANTAGE_API_KEY'),
            lambda d:d['package'].update(root='/Library/Application Support/IIOS'),
            lambda d:d['runtime'].update(tls='OTHER'),lambda d:d['session_package'].update(retries=1)):
            _,p,r,e,d,_=self.inputs();mutate(d)
            with patch.object(run,'verify_tools'),self.assertRaises(ValueError):run.full_descriptor(d)
            self.assertFalse(Path(d['authorized_root'],'full-session-output').exists())

    def test_environment_rejects_proxy_credentials_and_wrong_host(self):
        import alpha_radar_runner as run
        for key,value in [('HTTPS_PROXY','SYNTHETIC'),('API_KEY','SYNTHETIC'),('GH_TOKEN','SYNTHETIC'),
                          ('RUNNER_ENVIRONMENT','self-hosted'),('RUNNER_OS','Linux'),('GITHUB_RUN_ATTEMPT','2')]:
            context={**self.context(),key:value}
            with self.assertRaises(ValueError):run.lifecycle_environment(context)

    def test_guard_rejects_routes_dns_processes_signals_and_devnull_writes(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs()
        for role in ('fixture','worker'):
            guard,_=run.full_audit(r['root'],p['root'],('127.0.0.1',38493),role,plan=p['plan'])
            for event,args in [('socket.getaddrinfo',()),('socket.gethostbyname',()),('os.kill',(99999999,15)),
                ('os.system',('SYNTHETIC',)),('subprocess.Popen',('SYNTHETIC',['SYNTHETIC'],None,{}))]:
                with self.assertRaises((ValueError,PermissionError)):guard(event,args)
            for address in ('8.8.8.8','localhost','::1','127.0.0.2'):
                with self.assertRaises(ValueError):guard('socket.connect',(None,(address,38493)))
            with self.assertRaises(ValueError):guard('open',('/dev/null',None,os.O_RDWR))
            with self.assertRaises(ValueError):guard('open',('/Library/Keychains/login.keychain-db','r',os.O_RDONLY))
        for address in ('8.8.8.8','localhost','::1'):
            with self.assertRaises(ValueError):run.full_audit(r['root'],p['root'],(address,38493),'worker',plan=p['plan'])

    def test_guard_exact_worker_command_and_mutations(self):
        import alpha_radar_runner as run
        _,p,r,_,d,_=self.inputs();out=Path(p['root']);runtime=Path(r['root'])
        commands={role:[str(runtime/'python'),'-B',str(runtime/'alpha_radar_runner.py'),'--ci-full-session-only',
            '--child',role,'--descriptor',str(out/f'fs-{role}-launch.json'),'--expected-descriptor','a'*64] for role in ('fixture','worker')}
        guard,_=run.full_audit(runtime,out,('127.0.0.1',38493),'supervisor',plan=p['plan'],launch_commands=commands,context=d['context'])
        argv=commands['worker'];env=run.lifecycle_environment(d['context'])
        for index in range(len(argv)):
            altered=list(argv);altered[index]='ALTERED'
            with self.assertRaises(ValueError):guard('subprocess.Popen',(altered[0],altered,out,env))
        for cwd,environment in ((out.parent,env),(out,{**env,'TOKEN':'SYNTHETIC'})):
            with self.assertRaises(ValueError):guard('subprocess.Popen',(argv[0],argv,cwd,environment))
        guard('subprocess.Popen',(argv[0],argv,out,env))
        with self.assertRaises(ValueError):guard('subprocess.Popen',(argv[0],argv,out,env))

    def test_deferred_phase_command_is_one_time_and_exact(self):
        import alpha_radar_runner as run
        _,p,r,_,d,_=self.inputs();out=Path(p['root']);runtime=Path(r['root'])
        argv=[str(runtime/'python'),'-B',str(runtime/'alpha_radar_runner.py'),'--ci-full-session-only',
            '--child','worker','--descriptor',str(out/'fs-worker-launch.json'),'--expected-descriptor','a'*64]
        guard,_=run.full_audit(runtime,out,('127.0.0.1',38493),'supervisor',plan=p['plan'],context=d['context'])
        env=run.lifecycle_environment(d['context'])
        with self.assertRaises(ValueError):guard('subprocess.Popen',(argv[0],argv,out,env))
        guard.admit_command('worker',argv)
        with self.assertRaises(ValueError):guard.admit_command('worker',argv)
        changed=list(argv);changed[-1]='b'*64
        with self.assertRaises(ValueError):guard('subprocess.Popen',(changed[0],changed,out,env))
        guard('subprocess.Popen',(argv[0],argv,out,env))
        with self.assertRaises(ValueError):guard('subprocess.Popen',(argv[0],argv,out,env))
        for role in ('worker','fixture'):
            child_guard,_=run.full_audit(runtime,out,('127.0.0.1',38493),role,plan=p['plan'])
            with self.assertRaises(ValueError):child_guard.admit_command('worker',argv)

    def test_guard_only_exact_journal_directories_and_exclusive_receipts(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs();out=Path(p['root'])
        guard,_=run.full_audit(r['root'],out,('127.0.0.1',38493),'worker',plan=p['plan'])
        for path in (out/'OTHER.json',out.parent/'fs-secret.json',Path(p['plan']['root'])/'OTHER.json'):
            with self.assertRaises(ValueError):guard('open',(str(path),None,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW))
        for path in (out/'fs-session.json',Path(p['plan']['root'])/'0.reserved.json'):
            with self.assertRaises(ValueError):guard('open',(str(path),None,os.O_WRONLY|os.O_CREAT))
        with self.assertRaises(ValueError):guard('os.mkdir',(str(out/'OTHER'),0o700,-1))
        guard('os.mkdir',(p['plan']['root'],0o700,-1))

    def test_exact_request_and_independent_previous_parent_zero_dispatch_on_mutation(self):
        s,now,calls,_=self.session();self.journal(s)
        for mutate in (lambda r:r['account'].update(bulk_slot=1),lambda r:r['manifest'].update(role=SCOPE),
                       lambda r:r['expected'].update(slot='0'*64)):
            request=deepcopy(s.request(0));mutate(request)
            with self.assertRaises(ValueError):s.execute(request,None)
        with self.assertRaises(ValueError):s.execute(s.request(0),'0'*64)
        self.assertEqual(calls,[])
        receipt=s.execute(s.request(0),None);self.assertEqual(receipt['result'],'OBSERVED')
        with self.assertRaises(ValueError):s.execute(s.request(0),None)
        self.assertEqual(calls,[0])

    def test_interrupted_request_consumes_budget_and_never_retries(self):
        s,_,calls,_=self.session()
        def fail(*_):calls.append(0);raise TimeoutError('SYNTHETIC')
        s.exchange=fail;value,_=s.run()
        self.assertEqual(calls,[0]);self.assertEqual(value['attempted'],1);self.assertEqual(value['completed'],0)
        self.assertEqual(value['classification'],'FULL_SYNTHETIC_FAILED')
        self.assertTrue((Path(s.p['plan']['root'])/'0.reserved.json').is_file())
        with self.assertRaises(FileExistsError):s.run()
        self.assertEqual(calls,[0])

    def test_journal_recovery_requires_previously_witnessed_document(self):
        import alpha_radar_runner as run
        from alpha_session_execution import publish
        s,_,_,_=self.session();self.journal(s);fd=s.open_root(s.p['plan']['root'])
        try:
            value={'event':'SYNTHETIC'};doc=run.full_envelope(value,s.full_parents)
            publish(fd,'0.reserved.json',doc)
            with self.assertRaisesRegex(ValueError,'FULL_RECOVERY_PIN'):s.read(fd,'0.reserved.json')
        finally:os.close(fd)

    def test_forged_ack_parent_rejected_and_duplicate_publication(self):
        import alpha_radar_runner as run
        s,_,_,_=self.session();expected={'event':'ACK','role':'worker','launch_parent':'a'*64,'startup_parent':'b'*64}
        run.full_store(s.cap,s.full_parents,'fs-worker-ack.json',{**expected,'launch_parent':'c'*64})
        with self.assertRaises(ValueError):run.full_read(s.cap,s.full_parents,'fs-worker-ack.json',value=expected)
        with self.assertRaises(FileExistsError):run.full_store(s.cap,s.full_parents,'fs-worker-ack.json',expected)

    def test_http_schema_coverage_order_and_timeout_fail_closed(self):
        for kind in ('missing','duplicate','unexpected','stale','malformed','oversize','redirect','throttle','error','order','wire-time'):
            s,_,calls,_=self.session();original=s.exchange
            def exchange(cap,slot,at,kind=kind):
                value=original(cap,slot,at)
                if kind=='oversize':return Response(200,b' '*1_000_001,value.request_start,value.response_end)
                if kind=='malformed':return Response(200,b'{',value.request_start,value.response_end)
                if kind in ('redirect','throttle','error'):return Response({'redirect':302,'throttle':429,'error':500}[kind],b'',value.request_start,value.response_end)
                if kind=='wire-time':return Response(200,value.body,value.request_start,'2026-09-14T12:00:21+00:00')
                payload=json.loads(value.body)
                if kind=='missing':payload['data'].pop()
                if kind=='duplicate':payload['data'].append(payload['data'][0])
                if kind=='unexpected':payload['data'][0]['symbol']='OTHER'
                if kind=='stale':payload['data'][0]['timestamp']='2026-09-14T00:00:00+00:00'
                if kind=='order':payload['data'].reverse()
                return Response(200,canonical(payload),value.request_start,value.response_end)
            s.exchange=exchange;result,_=s.run()
            with self.subTest(kind=kind):
                self.assertEqual(result['classification'],'FULL_SYNTHETIC_FAILED');self.assertEqual(calls,[0])

    def test_full_475_mocked_session_accounting_and_every_record_scope(self):
        import alpha_radar_runner as run
        s,_,calls,_=self.session();result,parent=s.run()
        self.assertEqual(calls,list(range(475)));self.assertEqual(result['classification'],'FULL_SYNTHETIC_PASS')
        self.assertEqual(run.full_accounting(s.cap,s.full_parents,result)['receipts'],475)
        self.assertLessEqual(len(s.logical_waits),474)
        self.assertGreater((utc(s.clock())-utc(s.p['plan']['rows'][0]['valid_from'])).total_seconds(),6*3600)
        for path in Path(s.p['root']).rglob('*.json'):
            doc=json.loads(path.read_bytes())
            self.assertEqual(doc['scope'],run.FULL_SCOPE);self.assertEqual(doc['timing_proof'],run.FULL_TIMING)
            for key in AUTHORITY:self.assertIs(doc[key],False)
        for change in (lambda r:r.update(attempted=476),lambda r:r['receipt_parents'].pop(),
                       lambda r:r['receipt_parents'].reverse(),lambda r:r['receipt_parents'].__setitem__(1,r['receipt_parents'][0])):
            bad=deepcopy(result);change(bad)
            with self.assertRaises(ValueError):run.full_accounting(s.cap,s.full_parents,bad)
        value,_=run.full_read(s.cap,s.full_parents,'fs-session.json',expected=parent)
        self.assertEqual(value,result)

    def test_workflow_default_false_manual_exclusive_no_push_execution(self):
        import alpha_radar_ci as ci
        text=(ci.REPO/'.github/workflows/alpha-radar-native-diagnostics.yml').read_text()
        entry=text.split('      full_session_only:')[1].split('      expected_source_commit:')[0]
        self.assertIn('type: boolean',entry);self.assertIn('default: false',entry)
        step=text.split('- name: Manual full synthetic session;')[1].split('- name:')[0]
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.full_session_only == true && inputs.native_startup != true && inputs.lifecycle_only != true",step)
        self.assertIn('full-session --full-session-only',step)
        self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text)
        self.assertNotIn('alpha_radar_ci.py profile-probe',text)

    def test_cli_full_failure_does_not_retry_or_reach_other_modes(self):
        import alpha_radar_ci as ci
        root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        (root/'export').mkdir(exist_ok=True)
        with patch('sys.argv',['ci','full-session','--full-session-only','--root',str(root)]), \
            patch.object(ci,'execute_full',side_effect=ValueError('SUPERVISOR_FAILED')) as execute, \
            patch.object(ci,'execute') as native,patch.object(ci,'execute_lifecycle') as lifecycle:
            self.assertEqual(ci.main(),1)
        execute.assert_called_once();native.assert_not_called();lifecycle.assert_not_called()
        failure=json.loads(next((root/'export').glob('*failure*')).read_bytes())
        self.assertEqual(failure['scope'],'CI_SYNTHETIC_FULL_SESSION_ONLY')

    def test_full_preparation_cli_installs_guard_before_handler(self):
        import alpha_radar_ci as ci
        for phase in ('prepare','finalize'):
            order=[]
            with patch('sys.argv',['ci',phase,'--prepare-full-session','--root','/not-accessed']), \
                patch.object(ci.sys,'addaudithook',side_effect=lambda _:order.append('AUDIT')), \
                patch.object(ci,'full_event',side_effect=lambda _:order.append('EVENT')), \
                patch.object(ci,phase,side_effect=lambda *a,**kw:order.append(('HANDLER',kw))):
                self.assertEqual(ci.main(),0)
            self.assertEqual(order,['AUDIT','EVENT',('HANDLER',{'full_session':True})])

    def owned(self):
        import alpha_radar_runner as run
        s,_,_,_=self.session();p,r,_=s.cap.documents();observations={}
        owned=run.FullOwnedProcesses(s.cap,s.full_parents,inspect=lambda pid:observations[pid],pause=lambda _:None)
        for index,role in enumerate(('fixture','worker')):
            exe=str(Path(r['root'])/r['interpreter']);pid=12345+index
            obs=ProcessObservation(pid,os.getpid(),'2026-09-14T12:00:00+00:00',exe,exe,
                r['files'][0]['sha256'],p['root'],(exe,));observations[pid]=obs
            child=MagicMock();child.pid=pid;child.poll.return_value=None
            capture=run.LifecycleStreams(type('Streams',(),{'stdout':None,'stderr':None})())
            entry={'child':child,'expected':{'pid':pid,'parent_pid':os.getpid(),'argv':(exe,),
                'cwd':p['root'],'executable':exe,'executable_hash':obs.executable_hash},
                'observation':dict(obs.__dict__),'launch_parent':str(index+1)*64,'capture':capture}
            owned.children[role]=entry
            value=run.full_startup(s.cap,role,entry['launch_parent'],entry['observation'])
            parent=run.full_store(s.cap,s.full_parents,f'fs-{role}-startup.json',value)
            owned.startup_pins[role]=(entry['launch_parent'],parent)
            def wait(timeout,role=role,entry=entry):
                run.full_store(s.cap,s.full_parents,f'fs-{role}-exit.json',
                    {'role':role,'returncode':0,'launch_parent':entry['launch_parent']})
                entry['child'].poll.return_value=0
                return 0
            child.wait.side_effect=wait
        return owned,observations

    def test_full_owned_cooperative_cleanup_both_roles(self):
        owned,_=self.owned();children=[v['child'] for v in owned.children.values()]
        result=owned.cleanup(lambda:True)
        self.assertTrue(result['clean']);self.assertEqual(result['remaining'],[])
        self.assertEqual([v['role'] for v in result['exits']],['worker','fixture'])
        self.assertEqual(result['signals'],0)
        for child in children:child.kill.assert_not_called();child.terminate.assert_not_called()

    def test_full_cleanup_continues_after_worker_or_fixture_failure(self):
        for role in ('worker','fixture'):
            owned,_=self.owned();children=dict(owned.children)
            children[role]['child'].wait.side_effect=TimeoutError('SYNTHETIC')
            result=owned.cleanup(lambda:True)
            self.assertFalse(result['clean']);self.assertIn(role,result['remaining'])
            self.assertEqual(len(result['exits']),1);self.assertEqual(result['port_clear_observations'],[True]*3)
            for entry in children.values():entry['child'].kill.assert_not_called();entry['child'].terminate.assert_not_called()

    def test_full_pid_reuse_identity_mismatch_and_early_exit_fail_cleanup(self):
        for field,value in [('start_time','2026-09-14T12:00:01+00:00'),('parent_pid',1),('executable_hash','f'*64)]:
            owned,observations=self.owned();entry=owned.children['worker'];pid=entry['child'].pid
            observations[pid]=replace(observations[pid],**{field:value})
            result=owned.cleanup(lambda:True)
            self.assertFalse(result['clean']);entry['child'].wait.assert_not_called()
            self.assertFalse((Path(owned.cap.documents()[0]['root'])/'fs-worker-stop.json').exists())
        owned,_=self.owned();entry=owned.children['worker'];entry['observation']=None;entry['child'].poll.return_value=65
        self.assertFalse(owned.cleanup(lambda:True)['clean']);entry['child'].wait.assert_not_called()

    def test_full_cleanup_listener_survival_unstable_clearance(self):
        for values in ([False,False,False],[True,False,True]):
            owned,_=self.owned();samples=iter(values)
            result=owned.cleanup(lambda:next(samples));self.assertFalse(result['clean'])
            self.assertEqual(len(result['exits']),2);self.assertEqual(result['port_clear_observations'],values)

    def test_full_forged_startup_and_duplicate_role_rejected(self):
        owned,_=self.owned();entry=owned.children['worker']
        owned.startup_pins['worker']=(entry['launch_parent'],'0'*64)
        with self.assertRaises(ValueError):owned.verify('worker')
        with self.assertRaises(ValueError):owned.register('worker',entry['child'],argv=[],cwd='unused',
            executable='unused',executable_hash='0'*64)

    def registration_case(self, *, inspect=None, monotonic=None, pause=lambda _:None):
        import alpha_radar_runner as run
        s,_,_,d=self.session();p,r,_=s.cap.documents()
        exe=str(Path(r['root'])/r['interpreter']);pid=23456
        observation=ProcessObservation(pid,os.getpid(),'2026-09-14T12:00:00+00:00',exe,exe,
            next(v['sha256'] for v in r['files'] if v['path']==r['interpreter']),p['root'],(exe,))
        child=MagicMock();child.pid=pid;child.poll.return_value=None;child.stdout=None;child.stderr=None
        observed=(lambda _:observation) if inspect is None else inspect
        owned=run.FullOwnedProcesses(s.cap,s.full_parents,inspect=observed,
            monotonic=monotonic or (lambda:102),pause=pause)
        return run,s,d,owned,child,observation,exe

    def test_full_registration_admits_once_then_buffers_three_complete_observations(self):
        run,s,d,owned,child,observation,exe=self.registration_case();calls=[]
        original=run.checked_capability
        def checked(cap):calls.append('ADMISSION');return original(cap)
        started=__import__('time').monotonic()
        with patch.object(run,'checked_capability',side_effect=checked):
            owned.register('fixture',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                executable_hash=observation.executable_hash,stderr=None,launch_parent='1'*64,
                descriptor=d,deadline=run.full_startup_deadline(d))
        elapsed=__import__('time').monotonic()-started
        self.assertEqual(calls,['ADMISSION']);self.assertLess(elapsed,1)
        self.assertEqual(owned.children['fixture']['observation'],dict(observation.__dict__))
        files=sorted(Path(s.p['root']).glob('fs-event-*.json'))
        self.assertEqual(len(files),3)
        values=[json.loads(path.read_bytes())['value'] for path in files]
        batch=next(v for v in values if v['event']=='OWNERSHIP_INSPECTION_BATCH')
        self.assertEqual(batch['sample_count'],3);self.assertEqual(len(batch['samples']),3)
        self.assertTrue(all(v['observed']['field_matches'] and v['before']['state']=='CHILD_RUNNING'
            and v['after']['state']=='CHILD_RUNNING' for v in batch['samples']))

    def test_fresh_worker_phase_after_expired_fixture_deadline(self):
        run,s,d,owned,child,observation,exe=self.registration_case(monotonic=lambda:571)
        self.assertLess(run.full_startup_deadline(d),571)
        phase=run.full_phase(d,'worker',monotonic_ns=lambda:570_000_000_000)
        self.assertEqual(run.full_phase_deadline(d,'worker',phase),670)
        calls=[];original=run.checked_capability
        with patch.object(run,'checked_capability',side_effect=lambda cap:(calls.append(1) or original(cap))):
            owned.register('worker',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                executable_hash=observation.executable_hash,launch_parent='1'*64,
                descriptor=d,deadline=670,phase=phase)
        self.assertEqual(calls,[1])
        self.assertEqual(owned.children['worker']['observation'],dict(observation.__dict__))

    def test_phase_roundtrip_mutations_expiry_and_overall_budget(self):
        run,s,d,owned,child,observation,exe=self.registration_case(monotonic=lambda:471)
        phase=run.full_phase(d,'worker',monotonic_ns=lambda:370_000_000_000)
        self.assertEqual(run.full_phase_deadline(d,'worker',json.loads(json.dumps(phase))),470)
        for key,value in [('deadline_ns',470_000_000_001),('start_ns',370_000_000_001),
            ('unit','SECONDS'),('role','fixture'),('descriptor_parent','0'*64),
            ('start_ns',float('nan')),('deadline_ns',float('inf')),('deadline_ns',2**63)]:
            changed={**phase,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):run.full_phase_deadline(d,'worker',changed)
        with self.assertRaises(ValueError):
            run.full_phase(d,'worker',monotonic_ns=lambda:round(d['budget']['work_deadline']*1_000_000_000)-99_000_000_000)
        owned.inspect=MagicMock(return_value=observation)
        with self.assertRaises(ValueError):
            owned.register('worker',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                executable_hash=observation.executable_hash,launch_parent='1'*64,
                descriptor=d,deadline=470,phase=phase)
        owned.inspect.assert_not_called()
        self.assertEqual(owned.primary_failures[0]['stage'],'OWNERSHIP_REGISTER')
        child.terminate.assert_not_called();child.kill.assert_not_called()

    def test_expired_phase_prevents_ack_and_timeout_cleanup_preserves_other_role(self):
        import alpha_radar_runner as run
        owned,_=self.owned();worker=owned.children['worker'];worker['observation']=None
        owned.primary_failures.append({'role':'worker','stage':'OWNERSHIP_REGISTER',
            'category':'STARTUP_STABILIZATION_TIMEOUT'})
        with self.assertRaises(FileNotFoundError):
            run.full_read(owned.cap,owned.lifecycle_parents,'fs-worker-ack.json')
        with patch.object(run,'full_store') as publish,self.assertRaisesRegex(ValueError,'PARENT_ACK_TIMEOUT'):
            run.full_publish_startup_ack(owned.cap,owned.lifecycle_parents,'worker','1'*64,'2'*64,
                470,None,monotonic=lambda:470)
        publish.assert_not_called()
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['clean']);self.assertEqual(result['remaining'],['worker'])
        self.assertEqual([v['role'] for v in result['exits']],['fixture'])
        self.assertEqual(result['role_findings']['worker']['primary_failures'][0]['category'],
            'STARTUP_STABILIZATION_TIMEOUT')
        worker['child'].terminate.assert_not_called();worker['child'].kill.assert_not_called()

    def test_phase_parent_child_deadline_mismatch_rejected_before_inspection(self):
        run,s,d,owned,child,observation,exe=self.registration_case(monotonic=lambda:371)
        phase=run.full_phase(d,'worker',monotonic_ns=lambda:370_000_000_000)
        owned.inspect=MagicMock(return_value=observation)
        with self.assertRaises(ValueError):
            owned.register('worker',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                executable_hash=observation.executable_hash,launch_parent='1'*64,
                descriptor=d,deadline=471,phase=phase)
        owned.inspect.assert_not_called()

    def test_full_registration_buffers_bounded_sanitized_query_diagnostics(self):
        import alpha_radar_runner as run
        run,s,d,owned,child,observation,exe=self.registration_case()
        def inspect(pid,*,diagnostic):
            self.assertEqual(pid,child.pid)
            diagnostic({'query':'PS_START','started_at':'2026-09-14T12:00:00.000000+00:00',
                'ended_at':'2026-09-14T12:00:00.000001+00:00','monotonic_start':1,
                'monotonic_end':2,'returncode':0,'signal':None,'stdout_empty':False,
                'cwd_records':None,'failure':'NONE'})
            return observation
        with patch.object(run,'inspect_macos',side_effect=inspect) as native:
            owned.inspect=native
            owned.register('fixture',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                executable_hash=observation.executable_hash,launch_parent='1'*64,
                descriptor=d,deadline=run.full_startup_deadline(d))
        docs=[json.loads(path.read_bytes())['value'] for path in Path(s.p['root']).glob('fs-event-*.json')]
        batch=next(v for v in docs if v['event']=='OWNERSHIP_INSPECTION_BATCH')
        self.assertEqual([len(v['queries']) for v in batch['samples']],[1,1,1])
        self.assertEqual(batch['samples'][0]['queries'][0]['query'],'PS_START')

    def test_full_registration_rejects_pid_reuse_and_each_identity_mismatch(self):
        for field,value in [('pid',999),('parent_pid',1),('start_time','2026-09-14T12:00:01+00:00'),
                ('executable','/wrong'),('executable_hash','f'*64),('argv',('/wrong',)),('cwd','/wrong')]:
            samples=[]
            def inspect(_):
                samples.append(1)
                return observation if len(samples)<2 else replace(observation,**{field:value})
            run,s,d,owned,child,observation,exe=self.registration_case(inspect=inspect)
            with self.subTest(field=field),self.assertRaises(ValueError):
                owned.register('fixture',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                    executable_hash=observation.executable_hash,launch_parent='1'*64,
                    descriptor=d,deadline=run.full_startup_deadline(d))
            self.assertIsNone(owned.children['fixture']['observation'])

    def test_full_registration_deadline_and_slow_publication_fail_closed(self):
        ticks=[102]
        run,s,d,owned,child,observation,exe=self.registration_case(monotonic=lambda:ticks[0])
        deadline=run.full_startup_deadline(d);original=owned.registration_evidence
        def slow(fd,value):
            result=original(fd,value)
            if value['event']=='OWNERSHIP_INSPECTION_BATCH':ticks[0]=deadline
            return result
        owned.registration_evidence=slow
        with self.assertRaisesRegex(ValueError,'STARTUP_STABILIZATION_TIMEOUT'):
            owned.register('fixture',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                executable_hash=observation.executable_hash,launch_parent='1'*64,
                descriptor=d,deadline=deadline)
        self.assertIsNotNone(owned.children['fixture']['observation'])

    def test_full_registration_rejects_altered_descriptor_parents_before_inspection(self):
        run,s,d,owned,child,observation,exe=self.registration_case();calls=[]
        owned.lifecycle_parents={**owned.lifecycle_parents,'full_descriptor':'0'*64}
        owned.inspect=lambda pid:(calls.append(pid) or observation)
        with self.assertRaisesRegex(ValueError,'FULL_INDEPENDENT_PARENT'):
            owned.register('fixture',child,argv=(exe,),cwd=observation.cwd,executable=exe,
                executable_hash=observation.executable_hash,launch_parent='1'*64,
                descriptor=d,deadline=run.full_startup_deadline(d))
        self.assertEqual(calls,[])

    def test_full_shared_deadline_covers_registration_listener_and_ack_order(self):
        import alpha_radar_runner as run,inspect
        d=self.inputs()[4]
        self.assertEqual(run.full_startup_deadline(d),466)
        child_source=inspect.getsource(run.full_child);supervisor=inspect.getsource(run.full_supervise)
        self.assertIn('until=phase_deadline',child_source)
        self.assertIn("full_phase_deadline(d,role,launch['startup_phase'])",child_source)
        self.assertNotIn('time.monotonic()+10',child_source)
        self.assertNotIn('time.monotonic()+10',supervisor)
        ack=supervisor.index('full_publish_startup_ack(')
        self.assertLess(supervisor.index('owned.register('),ack)
        self.assertLess(supervisor.index("_,startup=full_read"),ack)
        self.assertLess(supervisor.index("'FULL_TLS_GATE'"),supervisor.index("child=popen("))

    def test_listener_mismatch_prevents_ack_and_worker_launch_gate_remains(self):
        import alpha_radar_runner as run,inspect
        run,s,d,owned,child,observation,exe=self.registration_case();published=MagicMock()
        with patch.object(run,'listener_owners',return_value=[(child.pid,'127.0.0.1:1')]), \
             patch.object(run,'full_store',published),self.assertRaisesRegex(ValueError,'LISTENER_OWNER_MISMATCH'):
            verified=run.full_verify_startup_listener('fixture',child,38491)
            run.full_publish_startup_ack(s.cap,s.full_parents,'fixture','1'*64,'2'*64,
                run.full_startup_deadline(d),verified,monotonic=lambda:102)
        published.assert_not_called()
        source=inspect.getsource(run.full_supervise)
        self.assertLess(source.index('full_publish_startup_ack('),source.index("stage='TLS_HANDSHAKE'"))
        self.assertLess(source.index("'FULL_TLS_GATE'"),source.index('child=popen('))

    def test_full_tls_mismatch_before_worker_launch_gate(self):
        import alpha_radar_runner as run,inspect
        s,_,_,_=self.session();owned=MagicMock();ctx=MagicMock();ctx.check_hostname=True;ctx.verify_mode=2
        channel=ctx.wrap_socket.return_value.__enter__.return_value;channel.getpeercert.return_value=b'WRONG_SYNTHETIC'
        with patch.object(run.ssl,'create_default_context',return_value=ctx), \
             patch.object(run.ssl,'PEM_cert_to_DER_cert',return_value=b'EXPECTED_SYNTHETIC'),patch.object(run.socket,'socket'):
            with self.assertRaises(ValueError):run.startup_tls(s.cap,owned)
        source=inspect.getsource(run.full_supervise)
        self.assertIn("require(tls is not None and tls['hostname_verified'] is True,'FULL_TLS_GATE')",source)
        self.assertNotIn('sandbox-exec',source);self.assertNotIn('DEVNULL',source)
        self.assertLess(source.index("'FULL_TLS_GATE'"),source.index('child=popen('))

    def test_full_child_and_lifecycle_cli_mutually_exclusive_before_read(self):
        import alpha_radar_runner as run
        with patch('sys.argv',['runner','--descriptor','not-read','--expected-descriptor','0'*64,
            '--ci-lifecycle-only','--ci-full-session-only']),patch.object(run,'read_descriptor') as read:
            with self.assertRaisesRegex(ValueError,'FULL_MODE_EXCLUSION'):run.main()
        read.assert_not_called()

    def test_full_guard_no_arbitrary_python_shell_or_confinement_command(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs()
        for argv in (['/bin/sh','-c','pass'],['/usr/bin/sandbox-exec'],[r['root']+'/python','-c','pass']):
            with self.assertRaises(ValueError):run.full_audit(r['root'],p['root'],('127.0.0.1',38493),
                'supervisor',plan=p['plan'],launch_commands={'fixture':argv,'worker':argv})


class FullPilotBindingTests(unittest.TestCase):
    context = FullSessionModeTests.context
    inputs = FullSessionModeTests.inputs
    def test_pilot_identity_separate_from_scan_universe(self):
        import alpha_radar_runner as run
        from provider_gateway_contract import PILOT
        _,p,_,e,_,_=self.inputs();package=run.full_package(p,e)
        pilot=package['preflight']
        self.assertEqual(pilot['identifier'],'PILOT')
        self.assertEqual(pilot['symbols'],list(PILOT));self.assertEqual(pilot['symbol_hash'],content_hash(list(PILOT)))
        self.assertEqual(pilot['request_count'],1);self.assertEqual(pilot['slot'],0)
        self.assertEqual(pilot['phase'],'PREFLIGHT');self.assertEqual(pilot['schedule_id'],'PREFLIGHT-0')
        self.assertEqual(pilot['row_parent'],content_hash(p['plan']['rows'][0]))
        self.assertEqual(pilot['valid_from'],'2026-09-14T13:20:00+00:00')
        self.assertEqual(pilot['expires_at'],'2026-09-14T13:25:00+00:00')
        self.assertFalse(set(PILOT)&set(package['ordered_universe']))
        self.assertNotIn('PILOT',package['ordered_universe'])
        self.assertEqual(1+package['cycles']*len(package['batch_sizes']),475)

    def test_every_pilot_symbol_and_order_mutation_even_when_rehashed(self):
        import alpha_radar_runner as run
        for index in range(10):
            for mode in ('replace','remove','duplicate','swap'):
                _,p,r,e,_,_=self.inputs();members=p['plan']['rows'][0]['symbols']
                if mode=='replace':members[index]='S000'
                elif mode=='remove':members.pop(index)
                elif mode=='duplicate':members[index]=members[(index+1)%10]
                else:members[index],members[(index+1)%10]=members[(index+1)%10],members[index]
                p['plan']['rows'][0]['symbol_hash']=content_hash(members)
                repin(p,r,e)
                with self.subTest(index=index,mode=mode),self.assertRaises(ValueError):run.full_package(p,e)

    def test_pilot_hash_phase_slot_identity_and_time_mutations(self):
        import alpha_radar_runner as run
        mutations=[('symbol_hash','0'*64),('phase','SCAN'),('id','PILOT'),('slot',1),('batch',1),
            ('valid_from','2026-09-14T13:21:00+00:00'),('expires_at','2026-09-14T13:26:00+00:00')]
        for key,value in mutations:
            _,p,r,e,_,_=self.inputs();p['plan']['rows'][0][key]=value;repin(p,r,e)
            with self.subTest(key=key),self.assertRaises(ValueError):run.full_package(p,e)

    def test_pilot_cannot_replace_any_normal_batch_or_enter_universe(self):
        import alpha_radar_runner as run
        for batch in range(6):
            _,p,r,e,_,_=self.inputs();p['plan']['rows'][batch+1]=deepcopy(p['plan']['rows'][0]);repin(p,r,e)
            with self.assertRaises(ValueError):run.full_package(p,e)
        for symbol in ('PILOT','MU'):
            _,p,r,e,_,_=self.inputs();p['plan']['universe']['symbols'][0]=symbol
            e['universe']=content_hash(p['plan']['universe']);repin(p,r,e)
            with self.assertRaises(ValueError):run.full_package(p,e)

    def test_s_batch_cannot_substitute_for_pilot_even_with_ten_members(self):
        import alpha_radar_runner as run
        for complete in (False,True):
            _,p,r,e,_,_=self.inputs()
            if complete:p['plan']['rows'][0]=deepcopy(p['plan']['rows'][1])
            else:
                p['plan']['rows'][0]['symbols']=[f'S{i:03}' for i in range(10)]
                p['plan']['rows'][0]['symbol_hash']=content_hash(p['plan']['rows'][0]['symbols'])
            repin(p,r,e)
            with self.assertRaises(ValueError):run.full_package(p,e)

    def test_missing_duplicate_pilot_and_request_count_mutations(self):
        import alpha_radar_runner as run
        for mutation in ('missing','duplicate','replace','preflight_count','total_count','scan_count'):
            _,p,r,e,_,_=self.inputs();plan=p['plan']
            if mutation=='missing':plan['rows'].pop(0)
            elif mutation=='duplicate':plan['rows'].insert(1,deepcopy(plan['rows'][0]))
            elif mutation=='replace':plan['rows'][1]=deepcopy(plan['rows'][0])
            elif mutation=='preflight_count':plan['preflight_requests']=2
            elif mutation=='total_count':plan['maximum_requests']=474
            else:plan['collection_requests']=473
            repin(p,r,e)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run.full_package(p,e)

    def test_rehashed_embedded_preflight_window_not_an_independent_pin(self):
        import alpha_radar_runner as run
        _,p,r,e,_,_=self.inputs();plan=p['plan']
        for row in (plan['rows'][0],plan['opportunity_schedule']['preflight']):
            row['valid_from']='2026-09-14T13:21:00+00:00'
        plan['schedule_parent']=content_hash(plan['opportunity_schedule']);e['schedule']=plan['schedule_parent']
        repin(p,r,e)
        with self.assertRaises(ValueError):run.full_package(p,e)


class FullCleanupIsolationTests(unittest.TestCase):
    context = FullSessionModeTests.context
    inputs = FullSessionModeTests.inputs
    session = FullSessionModeTests.session
    owned = FullSessionModeTests.owned

    def test_each_role_inspection_failure_still_inspects_other_role(self):
        for failed_role in ('worker','fixture'):
            owned,observations=self.owned();children=dict(owned.children);calls=[]
            failed_pid=children[failed_role]['child'].pid
            def inspect(pid):
                calls.append(pid)
                if pid==failed_pid:raise ValueError('PROCESS_INSPECTION_FAILED')
                return observations[pid]
            owned.inspect=inspect
            result=owned.cleanup(lambda:True)
            self.assertEqual(set(calls),set(observations))
            self.assertEqual(len(result['exits']),1);self.assertFalse(result['clean'])
            self.assertEqual(result['remaining'],[failed_role])
            self.assertEqual(result['role_findings'][failed_role]['cleanup_failures'][0]['category'],'PROCESS_INSPECTION_FAILED')
            children[failed_role]['child'].wait.assert_not_called()
            for entry in children.values():
                entry['child'].kill.assert_not_called();entry['child'].terminate.assert_not_called()

    def test_role_specific_diagnostic_publication_failure_is_not_shared(self):
        owned,observations=self.owned();children=dict(owned.children);worker=children['worker']['child'].pid
        original=owned.evidence;calls=[]
        def evidence(value):
            if value.get('event')=='OWNERSHIP_VERIFICATION_BATCH' and value.get('pid')==worker:
                raise OSError('SYNTHETIC_PUBLICATION_FAILURE')
            original(value)
        owned.evidence=evidence
        owned.inspect=lambda pid:(calls.append(pid) or observations[pid])
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['clean']);self.assertEqual([v['role'] for v in result['exits']],['fixture'])
        self.assertEqual(calls,[worker,children['fixture']['child'].pid])
        self.assertTrue(result['role_findings']['worker']['diagnostic_failures'])
        self.assertEqual(result['role_findings']['fixture']['diagnostic_failures'],[])
        self.assertTrue(result['diagnostic_failures'])

    def test_prior_child_diagnostics_remain_sticky_without_poisoning_other_role(self):
        owned,_=self.owned();children=dict(owned.children)
        children['worker']['inspection_diagnostic_failures']=['DIAGNOSTIC_PUBLICATION_FAILED']
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['clean']);self.assertEqual([v['role'] for v in result['exits']],['fixture'])
        self.assertEqual(result['role_findings']['worker']['diagnostic_failures'],['DIAGNOSTIC_PUBLICATION_FAILED'])
        children['worker']['child'].wait.assert_not_called()

    def test_both_role_failures_aggregate_and_clear_port_never_overrides_identity(self):
        import alpha_radar_runner as run
        owned,_=self.owned();children=dict(owned.children)
        def inspect(_):raise ValueError('PROCESS_IDENTITY')
        owned.inspect=inspect
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['clean']);self.assertEqual(result['exits'],[])
        self.assertEqual(set(result['remaining']),{'worker','fixture'})
        self.assertEqual(result['port_clear_observations'],[True]*3)
        for role,entry in children.items():
            self.assertEqual(result['role_findings'][role]['cleanup_failures'][0]['category'],'PROCESS_IDENTITY')
            self.assertFalse(result['role_findings'][role]['ownership_verified'])
            entry['child'].wait.assert_not_called();entry['child'].kill.assert_not_called();entry['child'].terminate.assert_not_called()
            self.assertFalse((Path(owned.cap.documents()[0]['root'])/f'fs-{role}-stop.json').exists())
        parent=run.full_store(owned.cap,owned.lifecycle_parents,'fs-cleanup-review.json',result)
        value,_=run.full_read(owned.cap,owned.lifecycle_parents,'fs-cleanup-review.json',expected=parent)
        self.assertEqual(value,result)

    def test_stream_snapshot_and_final_publication_exceptions_continue_cleanup(self):
        for failure in ('snapshot','publication'):
            owned,_=self.owned();worker=owned.children['worker'];original=owned.evidence
            if failure=='snapshot':worker['capture'].snapshot=MagicMock(side_effect=OSError('SYNTHETIC'))
            else:
                def evidence(value):
                    if value.get('event')=='FINAL_CHILD_STATUS' and value.get('role')=='worker':raise OSError('SYNTHETIC')
                    original(value)
                owned.evidence=evidence
            result=owned.cleanup(lambda:True)
            self.assertFalse(result['clean']);self.assertEqual(len(result['exits']),2)
            self.assertTrue(result['role_findings']['worker']['cleanup_failures'])
            self.assertEqual(result['role_findings']['fixture']['cleanup_failures'],[])

    def test_supervisor_failure_does_not_suppress_child_cleanup_or_listener_checks(self):
        owned,_=self.owned();calls=[]
        def supervisor():raise ValueError('PROCESS_IDENTITY')
        result=owned.cleanup(lambda:(calls.append('LISTENER') or True),supervisor_check=supervisor)
        self.assertFalse(result['clean']);self.assertEqual(len(result['exits']),2)
        self.assertEqual(calls,['LISTENER']*3)
        self.assertEqual(result['supervisor']['failures'],[{'stage':'SUPERVISOR_IDENTITY','category':'PROCESS_IDENTITY'}])

    def test_listener_inspection_and_pause_failures_are_independent_and_preserved(self):
        owned,_=self.owned();calls=[]
        def listener():
            calls.append('LISTENER')
            if len(calls)==1:raise ValueError('LISTENER_INSPECTION')
            return True
        def pause(_):raise OSError('SYNTHETIC_PAUSE')
        owned.pause=pause
        result=owned.cleanup(listener)
        self.assertFalse(result['clean']);self.assertEqual(len(result['exits']),2)
        self.assertEqual(calls,['LISTENER']*3);self.assertEqual(result['port_clear_observations'],[False,True,True])
        self.assertEqual(len(result['listener']['failures']),4)

    def test_success_requires_both_owned_exits_and_stable_listener(self):
        owned,_=self.owned();checks=[]
        result=owned.cleanup(lambda:True,supervisor_check=lambda:checks.append('SUPERVISOR'))
        self.assertTrue(result['clean']);self.assertEqual(checks,['SUPERVISOR'])
        self.assertEqual(set(result['role_findings']),{'worker','fixture'})
        self.assertTrue(all(v['ownership_verified'] and v['exit_verified'] for v in result['role_findings'].values()))
        self.assertEqual(result['failures'],[]);self.assertEqual(result['signals'],0)
        self.assertTrue(result['listener']['stable_clear'])


class FullLexicalAdmissionTests(unittest.TestCase):
    inputs = FullSessionModeTests.inputs
    context = FullSessionModeTests.context

    def instrument(self):
        from contextlib import ExitStack
        import builtins, io, glob
        stack = ExitStack(); calls = []
        def forbidden(*args, **kwargs):
            calls.append('FILESYSTEM_CALL')
            raise AssertionError('FILESYSTEM_BEFORE_LEXICAL_ADMISSION')
        for owner, names in ((Path, ('resolve','stat','lstat','exists','is_file','is_dir','is_symlink',
                                    'open','glob','rglob','iterdir','readlink')),
                             (os, ('stat','lstat','open','fstat','listdir','scandir','readlink')),
                             (builtins, ('open',)), (io, ('open',)), (glob, ('glob','iglob'))):
            for name in names: stack.enter_context(patch.object(owner,name,side_effect=forbidden))
        return stack, calls

    def denied(self, root):
        from pathlib import PureWindowsPath
        class UnsafePath:
            def __fspath__(self): raise AssertionError('CUSTOM_FSPATH_CALLED')
        return ['/Library/Keychains', '/Library/Keychains/login.keychain-db',
            '/System/Library/Keychains/child', '/Users/owner/Library/Keychains/child',
            '/home/owner/L7/data', '~/Library/Keychains/child', '/var/ledger/L8',
            str(root)+'/../protected', str(root)+'ish/file', str(root)+'//file',
            str(root)+'/./file', str(root)+'/L7/child', str(root)+'/L8/child',
            '../escape', 'relative', '', '\x00', str(root)+'/bad\x00file',
            '/dev/fd/4', '/proc/self/fd/4', '/tmp/alias',
            str(root)+'/alias/../../protected', b'/Library/Keychains', None,
            PureWindowsPath('C:/protected'), UnsafePath()]

    def test_denied_inputs_have_zero_filesystem_calls_in_both_entrypoints(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs()
        guard,opened=run.full_audit(r['root'],p['root'],('127.0.0.1',38493),'worker',plan=p['plan'])
        for value in self.denied(Path(p['root'])):
            for entry in (lambda v:guard('open',(v,'r',os.O_RDONLY)),lambda v:opened(v,os.O_RDONLY)):
                stack,calls=self.instrument()
                with stack, self.assertRaisesRegex(ValueError,'^FULL_PATH_LEXICAL$'):
                    entry(value)
                self.assertEqual(calls,[])

    def test_shared_helper_is_pure_and_component_based(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs(); roots=(r['root'],p['root'])
        good=str(Path(p['root'])/'fs-session.json')
        stack,calls=self.instrument()
        with stack:
            self.assertEqual(str(run.full_lexical_path(good,roots=roots)),good)
            self.assertEqual(str(run.full_lexical_path('fs-session.json',roots=roots,parent=p['root'])),good)
            for bad in [*self.denied(Path(p['root'])),1]:
                with self.assertRaisesRegex(ValueError,'^FULL_PATH_LEXICAL$'):
                    run.full_lexical_path(bad,roots=roots)
        self.assertEqual(calls,[])

    def test_relative_descriptor_escape_rejected_before_fstat(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs();out=Path(p['root']);out.mkdir()
        _,opened=run.full_audit(r['root'],out,('127.0.0.1',38493),'worker',plan=p['plan'])
        fd=opened(out,os.O_RDONLY|os.O_DIRECTORY)
        try:
            for path in ('../escape','a/../../escape','./file','a//b','/Library/Keychains'):
                stack,calls=self.instrument()
                with stack,self.assertRaisesRegex(ValueError,'^FULL_PATH_LEXICAL$'):
                    opened(path,os.O_RDONLY,dir_fd=fd)
                self.assertEqual(calls,[])
        finally:os.close(fd)

    def test_admitted_symlink_entry_rejected_without_resolution_or_target_access(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs();out=Path(p['root']);out.mkdir()
        # Synthetic dangling target only. Creating a symlink does not read it.
        link=out/'fs-alias.json';link.symlink_to(out.parent/'SYNTHETIC-UNADMITTED')
        guard,_=run.full_audit(r['root'],out,('127.0.0.1',38493),'worker',plan=p['plan'])
        calls=[];actual=os.lstat
        def observe(path,*args,**kwargs):
            self.assertIn(Path(path),(out,link));calls.append(Path(path))
            return actual(path,*args,**kwargs)
        with patch.object(Path,'resolve',side_effect=AssertionError('SYMLINK_RESOLVED')) as resolve, \
             patch.object(os,'readlink',side_effect=AssertionError('SYMLINK_FOLLOWED')) as readlink, \
             patch.object(os,'lstat',side_effect=observe),self.assertRaisesRegex(ValueError,'^FULL_PATH_ALIAS$'):
            guard('open',(str(link),'r',os.O_RDONLY))
        self.assertEqual(calls,[out,link]);resolve.assert_not_called();readlink.assert_not_called()

    def test_valid_root_paths_keep_canonical_and_exclusive_checks(self):
        import alpha_radar_runner as run
        _,p,r,_,_,_=self.inputs();out=Path(p['root']);out.mkdir()
        guard,opened=run.full_audit(r['root'],out,('127.0.0.1',38493),'worker',plan=p['plan'])
        path=out/'fs-example.json'
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
        fd=opened(path,flags,0o600);os.close(fd)
        with self.assertRaises(FileExistsError):opened(path,flags,0o600)
        with self.assertRaisesRegex(ValueError,'FULL_WRITE'):guard('open',(str(path),None,os.O_WRONLY))
        with patch.object(Path,'resolve',return_value=out.parent),self.assertRaisesRegex(ValueError,'FULL_PATH_ALIAS'):
            guard('open',(str(path),'r',os.O_RDONLY))

def measured_workload(seconds=1200, admission_ns=300_000_000_000, calls=2375):
    import alpha_radar_ci as ci
    return {'node':ci.WORKLOAD_NODE,'wall_seconds':seconds,
        'cost_partition':{'schema':'iios-workload-cost-partition-v1',
            'wall_ns':round(seconds*1_000_000_000),'admission_ns':admission_ns,
            'admission_calls':calls}}


class QualificationBudgetTests(unittest.TestCase):
    def descriptor(self): return FullSessionModeTests().inputs()[4]

    def proof(self):
        import alpha_radar_ci as ci
        partition=ci.collect_validation()
        value={'schema':'iios-offline-validation-v1','scope':ci.VALIDATION_SCOPE,
            **ci.validation_identity(),'job':'validation','source_bindings':ci.source_bindings(),
            'collection_parent':ci.digest(ci.canonical(partition)),
            'offline':{'executed':len(partition['offline']),'passed':len(partition['offline']),
                'failed':0,'errors':0,'skipped':0,'native_not_run':partition['native_not_run']},
            'fresh_stdio':4,'fresh_export':10,'result_parents':{n:'a'*64 for n in (
                'offline-results.json','fresh-stdio-results.json','fresh-export-results.json','python-syntax.json','workflow-syntax.json')},
            'runtime_archive_sha256':ci.ARCHIVE_SHA256,
            'workload_measurement':measured_workload()}
        return value

    def test_validation_parent_commit_run_source_collection_and_all_counts(self):
        import alpha_radar_ci as ci
        with patch.dict(os.environ,{'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'1'}):
            value=self.proof();parent=ci.digest(ci.canonical(value))
            self.assertEqual(ci.check_validation_proof(value,parent),value)
            with self.assertRaises(ValueError):ci.check_validation_proof(value,'b'*64)
            mutations=[lambda v:v.update(source_commit='b'*40),lambda v:v.update(run_id='2'),
                lambda v:v.update(run_attempt=2),lambda v:v.update(job='native'),
                lambda v:v.update(collection_parent='b'*64),lambda v:v.update(source_bindings={}),
                lambda v:v['offline'].update(passed=0),lambda v:v['offline'].update(skipped=1),
                lambda v:v['offline'].update(failed=1),lambda v:v['offline'].update(executed=0),
                lambda v:v.update(fresh_stdio=0),lambda v:v.update(fresh_export=0),
                lambda v:v.update(result_parents={}),lambda v:v.update(runtime_archive_sha256='b'*64)]
            for mutate in mutations:
                bad=deepcopy(value);mutate(bad)
                with self.assertRaises(ValueError):ci.check_validation_proof(bad,ci.digest(ci.canonical(bad)))

    def test_validation_import_rejects_noncanonical_duplicate_or_bad_parent(self):
        import alpha_radar_ci as ci,base64
        root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        with patch.dict(os.environ,{'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'native'}),patch.object(ci,'hosted'):
            value=self.proof();raw=ci.canonical(value)
            for data,expected in [(raw,'b'*64),(b'{"a":1,"a":2}',ci.digest(b'{"a":1,"a":2}')),
                                  (b' '+raw,ci.digest(raw)),(b'not-json','a'*64)]:
                with patch.dict(os.environ,{'IIOS_VALIDATION_PROOF':base64.b64encode(data).decode(),
                                          'IIOS_EXPECTED_VALIDATION_SHA256':expected}),patch.object(ci,'put') as publish:
                    with self.assertRaises(ValueError):ci.import_validation(root)
                    publish.assert_not_called()

    def test_new_preparation_phases_install_audit_before_dispatch(self):
        import alpha_radar_ci as ci
        for phase,handler in [('validation-proof','publish_validation'),('accept-validation','import_validation')]:
            order=[]
            with patch('sys.argv',['ci',phase,'--root','/not-accessed']), \
                patch.object(ci.sys,'addaudithook',side_effect=lambda _:order.append('AUDIT')), \
                patch.object(ci,handler,side_effect=lambda _:order.append('HANDLER')), \
                patch.object(ci,'execute_full') as execute:
                self.assertEqual(ci.main(),0)
            self.assertEqual(order,['AUDIT','HANDLER']);execute.assert_not_called()

    def test_budget_requires_cleanup_export_and_real_clock_reserves(self):
        import alpha_radar_runner as run
        d=self.descriptor();b=run.full_launch_budget(d,monotonic=lambda:101)
        self.assertEqual(b['real_clock_seconds'],65);self.assertEqual(b['cleanup_seconds'],180)
        self.assertLessEqual(b['cleanup_deadline']+b['export_seconds'],b['hard_deadline'])
        for tick in (100,402,float('nan'),float('inf')):
            with self.assertRaises(ValueError):run.full_launch_budget(d,monotonic=lambda:tick)
        for key,val in [('cleanup_seconds',0),('export_seconds',0),('real_clock_seconds',60),
            ('work_seconds',900),('hard_deadline',5000),('cleanup_deadline',5000),
            ('work_deadline',5000),('prepared_monotonic',float('nan'))]:
            bad=deepcopy(d);bad['budget'][key]=val
            with self.assertRaises(ValueError):run.full_budget(bad)
        bad=deepcopy(d);bad['validation_parent']=''
        with self.assertRaises(ValueError):run.full_budget(bad)

    def test_120_minute_budget_rejects_old_budget_and_one_unit_mutations(self):
        import alpha_radar_runner as run
        d=self.descriptor()
        self.assertEqual(run.full_budget(d)['work_seconds'],6000)
        old=deepcopy(d)
        old['maximum_duration_seconds']=3300
        old['budget'].update(work_seconds=3300,hard_deadline=4540,
            work_deadline=3766,cleanup_deadline=3946)
        with self.assertRaisesRegex(ValueError,'FULL_JOB_BUDGET'):
            run.full_budget(old)
        for key in ('hard_deadline','work_deadline','cleanup_deadline',
                    'work_seconds','cleanup_seconds','export_seconds','real_clock_seconds'):
            for delta in (-1,1):
                bad=deepcopy(d);bad['budget'][key]+=delta
                with self.assertRaises(ValueError):run.full_budget(bad)
        for delta in (-1,1):
            bad=deepcopy(d);bad['maximum_duration_seconds']+=delta
            with self.assertRaises(ValueError):run.full_budget(bad)

    def test_revised_budget_creator_verifier_and_workflow_agree(self):
        import alpha_radar_ci as ci, alpha_radar_runner as run
        d=self.descriptor();root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        env={'GITHUB_SHA':d['context']['GITHUB_SHA'],'GITHUB_RUN_ID':d['context']['GITHUB_RUN_ID'],
             'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'native','IIOS_NATIVE_JOB_START':'100'}
        with patch.dict(os.environ,env),patch.object(ci,'document'), \
             patch.object(ci.time,'monotonic',return_value=400):
            d['budget']=ci.prepare_job_budget(root)
        d=json.loads(json.dumps(d))
        b=run.full_launch_budget(d,monotonic=lambda:400)
        self.assertEqual(b['hard_deadline'],7240)
        self.assertEqual(b['work_deadline'],6765)
        self.assertEqual(b['cleanup_deadline'],6945)
        self.assertEqual(b['cleanup_deadline']+180,7125)
        self.assertEqual(b['hard_deadline']-(b['cleanup_deadline']+180),115)
        self.assertEqual(ci.NATIVE_JOB_SECONDS,120*60)
        self.assertEqual(sum((ci.NATIVE_PREPARATION_SECONDS,ci.NATIVE_STARTUP_SECONDS,
            ci.REAL_CLOCK_SECONDS,ci.FULL_WORK_SECONDS,ci.CLEANUP_SECONDS,
            ci.EXPORT_SECONDS,ci.NATIVE_START_RESERVE)),7085)
        self.assertEqual(run.full_startup_deadline(d),765)
        # Last launch-admission instant and one nanosecond beyond the boundary.
        run.full_launch_budget(d,monotonic=lambda:700)
        with self.assertRaisesRegex(ValueError,'FULL_INSUFFICIENT_BUDGET'):
            run.full_launch_budget(d,monotonic=lambda:700.000000001)
        for role in ('fixture','worker'):
            phase=run.full_phase(d,role,monotonic_ns=lambda:800_000_000_000)
            self.assertEqual(phase['deadline_ns']-phase['start_ns'],100_000_000_000)
            self.assertEqual(run.full_phase_deadline(d,role,phase),900)
        for key in ('hard_deadline','work_deadline','cleanup_deadline','work_seconds',
                    'startup_deadline_ns','cleanup_seconds','export_seconds'):
            for delta in (-1,1):
                bad=deepcopy(d);bad['budget'][key]+=delta
                with self.subTest(key=key,delta=delta),self.assertRaises(ValueError):
                    run.full_budget(bad)

    def test_canonical_startup_deadline_survives_observed_two_ulp_round_trip(self):
        import alpha_radar_runner as run
        d=self.descriptor();b=d['budget']
        # Preserve the exact historical two-ULP reproduction independently of
        # the revised allocation; no float equality is used for startup identity.
        from_work=3079.378764083-2700
        from_prepared=214.378764083+65+100
        b.update(start_monotonic=199.422550333,prepared_monotonic=214.378764083,
            hard_deadline=199.422550333+7140,work_deadline=214.378764083+6365,
            cleanup_deadline=214.378764083+6365+180,prepared_monotonic_ns=214_378_764_083,
            startup_deadline_ns=579_378_764_083)
        self.assertNotEqual(from_work,from_prepared)
        self.assertEqual(abs(from_work-from_prepared),1.1368683772161603e-13)
        encoded=json.dumps(d,sort_keys=True,separators=(',',':'))
        admitted=json.loads(encoded)
        self.assertEqual(run.full_startup_deadline(admitted),579.378764083)
        self.assertEqual(admitted['budget']['startup_deadline_ns'],579_378_764_083)

    def test_canonical_startup_deadline_rejects_unit_tick_and_budget_mutations(self):
        import alpha_radar_runner as run
        mutations=(
            ('deadline_unit','MONOTONIC_MILLISECONDS'),
            ('prepared_monotonic_ns',101_000_000_001),
            ('startup_deadline_ns',466_000_000_001),
            ('startup_deadline_ns',466_000_000_000.0),
            ('startup_deadline_ns',-1),
            ('startup_deadline_ns',2**63),
            ('prepared_monotonic_ns',2**63),
            ('work_seconds',3299),
            ('work_seconds',3301),
            ('real_clock_seconds',64),
            ('real_clock_seconds',66),
        )
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                bad=deepcopy(self.descriptor());bad['budget'][key]=value
                with self.assertRaisesRegex(ValueError,'FULL_JOB_BUDGET'):
                    run.full_budget(bad)
        for key,value in (('prepared_monotonic',float('nan')),
                          ('prepared_monotonic',float('inf')),
                          ('prepared_monotonic',-1)):
            bad=deepcopy(self.descriptor());bad['budget'][key]=value
            with self.assertRaisesRegex(ValueError,'FULL_JOB_BUDGET'):
                run.full_budget(bad)

    def test_fixture_creation_waits_for_every_canonical_budget_pin(self):
        import alpha_radar_runner as run
        for key,value in (('deadline_unit','WRONG'),('startup_deadline_ns',466_000_000_001),
                          ('prepared_monotonic_ns',101_000_000_001),('work_deadline',3765),
                          ('cleanup_deadline',3945),('hard_deadline',4539)):
            bad=deepcopy(self.descriptor());bad['budget'][key]=value
            with self.subTest(key=key),patch.object(run,'admit') as admit_mock,\
                 patch.object(run,'full_supervise') as supervise:
                with self.assertRaisesRegex(ValueError,'FULL_JOB_BUDGET'):
                    run.full_main(bad,content_hash(bad),None)
                admit_mock.assert_not_called();supervise.assert_not_called()

    def test_insufficient_budget_prevents_admission_or_process_creation(self):
        import alpha_radar_runner as run
        d=self.descriptor()
        with patch.object(run,'full_descriptor'),patch.object(run,'full_launch_budget',side_effect=ValueError('FULL_INSUFFICIENT_BUDGET')), \
            patch.object(run,'admit') as admit_mock,patch.object(run,'full_supervise') as supervise:
            with self.assertRaisesRegex(ValueError,'FULL_INSUFFICIENT_BUDGET'):run.full_main(d,content_hash(d),None)
        admit_mock.assert_not_called();supervise.assert_not_called()

    def test_cancellation_handlers_only_request_and_restore_without_signals(self):
        import alpha_radar_runner as run,signal
        with patch.object(signal,'getsignal',return_value='previous'),patch.object(signal,'signal') as register, \
            patch.object(os,'kill') as kill:
            with run.FullCancellation() as cancel:
                self.assertFalse(cancel());cancel.request(signal.SIGTERM,None);self.assertTrue(cancel())
            self.assertEqual(register.call_count,4);kill.assert_not_called()
            self.assertEqual(register.call_args_list[-1].args[1],'previous')

    def test_cancel_receipt_requires_independent_launch_and_parent(self):
        import alpha_radar_runner as run
        root,p,r,e,d,parents=FullSessionModeTests().inputs();cap=admit(p,r,expected=e,authorized_root=root)
        launch={**run.FULL_FLAGS,'descriptor':d,'output_identity':list(cap.output_identity),'parent_pid':12345,'role':'fixture'}
        run.full_store(cap,parents,'fs-fixture-launch.json',launch)
        with patch.object(run,'verify_tools'):
            with self.assertRaises(ValueError):run.request_full_cancel(d,'b'*64,12345)
            with self.assertRaises(ValueError):run.request_full_cancel(d,content_hash(d),12346)
            self.assertFalse((Path(p['root'])/'fs-cancel.json').exists())
            run.request_full_cancel(d,content_hash(d),12345)
            raw=(Path(p['root'])/'fs-cancel.json').read_bytes()
            run.request_full_cancel(d,content_hash(d),12345)
            self.assertEqual((Path(p['root'])/'fs-cancel.json').read_bytes(),raw)

    def test_logical_jump_exact_target_rate_and_no_actual_sleep(self):
        import alpha_radar_runner as run,time
        s,now,_,_=FullSessionModeTests().session();s.next_slot=1
        before=now[0];target=utc(s.p['plan']['rows'][1]['valid_from'])
        with patch.object(time,'sleep',side_effect=AssertionError('REAL_WAIT')):
            run.advance_full_clock(s,now,1)
        self.assertEqual(now[0],target);self.assertGreater((target-before).total_seconds(),60)
        for seconds in (0,-1,2,float('nan')):
            with self.assertRaises(ValueError):run.advance_full_clock(s,now,seconds)
        s.rate.starts=[target.timestamp()]*3;now[0]=target
        run.advance_full_clock(s,now,1);self.assertEqual(now[0],target+timedelta(seconds=60))
        with self.assertRaises(ValueError):run.advance_full_clock(s,now,1)

    def test_cleanup_expired_budget_preserves_failure_and_continues_both_roles(self):
        import alpha_radar_runner as run
        owned,observations=FullSessionModeTests().owned()
        # This test uses the same independent role setup and mocked process boundary.
        with patch.object(owned,'monotonic',return_value=1000):
            result=owned.cleanup(lambda:True,deadline=999)
        self.assertFalse(result['clean']);self.assertEqual(set(result['role_findings']),{'fixture','worker'})
        for value in result['role_findings'].values():
            self.assertTrue(value['ownership_verified']);self.assertFalse(value['exit_verified'])
            self.assertTrue(value['cleanup_failures']);self.assertEqual(value['signals'],0)
        self.assertEqual(result['port_clear_observations'],[True,True,True])

    def test_workflow_validates_once_and_native_requires_same_commit_proof(self):
        import alpha_radar_ci as ci,ast
        text=(ci.REPO/'.github/workflows/alpha-radar-native-diagnostics.yml').read_text()
        validation,native=text.split('\n  native:\n')
        self.assertEqual(text.count('alpha_radar_ci.py offline'),1)
        self.assertIn('needs: validation',native);self.assertNotIn('alpha_radar_ci.py offline',native)
        self.assertNotIn('test_alpha_radar_export_process.py',native)
        self.assertIn('needs.validation.outputs.proof_sha256',native)
        self.assertIn('needs.validation.outputs.proof',native)
        self.assertIn("github.event_name == 'workflow_dispatch'",native)
        self.assertIn('timeout-minutes: 120',native);self.assertIn('timeout-minutes: 60',validation)
        source=Path(ci.__file__).read_text();tree=ast.parse(source)
        for name in ('execute','execute_lifecycle','execute_full'):
            f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            calls=[n.func.id for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
            self.assertIn('require_validation',calls);self.assertNotIn('offline',calls)

    def test_native_job_budget_rejects_slow_preparation_and_clock_rollback(self):
        import alpha_radar_ci as ci
        root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        env={'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'1',
             'GITHUB_JOB':'native','IIOS_NATIVE_JOB_START':'100'}
        with patch.dict(os.environ,env),patch.object(ci,'document') as publish:
            for tick in (99,401,float('nan')):
                with patch.object(ci.time,'monotonic',return_value=tick),self.assertRaises(ValueError):
                    ci.prepare_job_budget(root)
            publish.assert_not_called()
            with patch.object(ci.time,'monotonic',return_value=101):b=ci.prepare_job_budget(root)
            self.assertEqual(b['work_seconds'],6000)
            self.assertEqual(b['work_deadline']-b['prepared_monotonic'],6365)
            self.assertLessEqual(b['cleanup_deadline']+180,b['hard_deadline'])
            publish.assert_called_once()

    def test_publish_validation_requires_complete_records_and_exclusive_receipt(self):
        import alpha_radar_ci as ci
        root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        (root/'export').mkdir(exist_ok=True)
        env={'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'validation'}
        with patch.dict(os.environ,env),patch.object(ci,'hosted'):
            partition=ci.collect_validation();binding=ci.source_bindings();count=len(partition['offline'])
            records={'offline-collection.json':partition,
                'offline-results.json':{'scope':'MOCKED_OFFLINE_ONLY','success':True,'collected':count,
                    'executed':count,'passed':count,'skipped':[],'source_bindings':binding,
                    'timings':[{**measured_workload(),'node':n} for n in partition['offline']]},
                'fresh-stdio-results.json':{'scope':'FRESH_PROCESS_STDIO_ONLY','success':True,'collected':4,
                    'executed':4,'source_bindings':binding},
                'fresh-export-results.json':{'scope':'FRESH_PROCESS_EXPORT_ONLY','success':True,'collected':10,
                    'executed':10,'skipped':0,'source_bindings':binding},
                'python-syntax.json':{'scope':'STATIC_SYNTAX_ONLY','success':True,'skipped':0,
                    'collected':len([n for n in ci.binding_paths() if n.endswith('.py')]),
                    'executed':len([n for n in ci.binding_paths() if n.endswith('.py')]),'source_bindings':binding},
                'workflow-syntax.json':{'scope':'STATIC_SYNTAX_ONLY','success':True,'scripts':18,'executed_commands':0}}
            for name,record in records.items():ci.document(root/'export'/name,record)
            ci.publish_validation(root)
            receipt=json.loads((root/'export/validation-proof.json').read_bytes())
            self.assertEqual(receipt['offline']['executed'],count)
            for name,parent in receipt['result_parents'].items():
                self.assertEqual(parent,ci.digest((root/'export'/name).read_bytes()))
            with self.assertRaises(FileExistsError):ci.publish_validation(root)
            with patch.object(ci,'verify_bindings',side_effect=ValueError('OFFLINE_SOURCE_BINDING')):
                with self.assertRaises(ValueError):ci.publish_validation(root)

    def test_validation_record_rejects_aliases_modes_and_unknown_names_before_open(self):
        import alpha_radar_ci as ci,stat
        from types import SimpleNamespace
        root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        directory=SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=os.getuid())
        regular=SimpleNamespace(st_mode=stat.S_IFREG|0o400,st_uid=os.getuid(),st_nlink=1,st_size=10)
        for changed in ({'st_mode':stat.S_IFLNK|0o400},{'st_mode':stat.S_IFREG|0o600},
                        {'st_nlink':2},{'st_size':1_000_001},{'st_uid':os.getuid()+1}):
            bad=SimpleNamespace(**{**regular.__dict__,**changed})
            with patch.object(ci,'root_check'),patch.object(Path,'lstat',side_effect=[directory,bad]), \
                patch.object(ci.os,'open') as opened:
                with self.assertRaises(ValueError):ci.validation_record(root,'validation-proof.json')
                opened.assert_not_called()
        with patch.object(Path,'lstat') as metadata,patch.object(ci.os,'open') as opened:
            with self.assertRaises(ValueError):ci.validation_record(root,'../not-admitted')
            metadata.assert_not_called();opened.assert_not_called()


class SchedulerSanitizedFailureTests(unittest.TestCase):
    def call(self, executor, diagnostics=None, **overrides):
        at = '2026-09-14T13:20:00+00:00'
        kwargs = dict(clock=lambda:at, wait=lambda _:None, executor=executor,
                      stop=lambda:False, verify=lambda *_:None,
                      completion_parent=lambda *_:None,
                      failure_diagnostics=diagnostics)
        kwargs.update(overrides)
        return execute_schedule({'rows':[{'valid_from':at,
            'expires_at':'2026-09-14T13:25:00+00:00'}]}, [{}], **kwargs)

    def test_exception_text_and_locals_never_retained(self):
        def fail(*_):
            sensitive_local = 'DO_NOT_RETAIN_SYNTHETIC_SENTINEL'
            raise ValueError(sensitive_local)
        diagnostics=[]
        receipts, reason=self.call(fail,diagnostics)
        self.assertEqual((receipts,reason),([], 'AMBIGUOUS_OR_FAILED_STOP'))
        self.assertEqual(len(diagnostics),1)
        self.assertEqual(diagnostics[0]['exception_type'],'VALUE_ERROR')
        self.assertEqual(diagnostics[0]['stage'],'EXECUTOR')
        self.assertNotIn('DO_NOT_RETAIN',json.dumps(diagnostics))
        self.assertFalse(diagnostics[0]['message_retained'])
        self.assertFalse(diagnostics[0]['locals_retained'])

    def test_custom_exception_name_and_stringification_not_used(self):
        class UntrustedError(Exception):
            def __str__(self): raise AssertionError('MUST_NOT_STRINGIFY')
        def fail(*_): raise UntrustedError('DO_NOT_RETAIN')
        diagnostics=[]; self.call(fail,diagnostics)
        self.assertEqual(diagnostics[0]['exception_type'],'UNKNOWN')
        self.assertNotIn('UntrustedError',json.dumps(diagnostics))

    def test_fail_closed_without_diagnostic_sink(self):
        executor=MagicMock(side_effect=PermissionError('DO_NOT_RETAIN'))
        self.assertEqual(self.call(executor),([], 'AMBIGUOUS_OR_FAILED_STOP'))
        executor.assert_called_once()

    def test_verify_failure_stage_and_no_duplicate_dispatch(self):
        diagnostics=[]; executor=MagicMock(return_value={})
        self.assertEqual(self.call(executor,diagnostics,
            verify=MagicMock(side_effect=KeyError('DO_NOT_RETAIN'))),
            ([], 'AMBIGUOUS_OR_FAILED_STOP'))
        self.assertEqual(diagnostics[0]['stage'],'VERIFY')
        self.assertEqual(diagnostics[0]['exception_type'],'KEY_ERROR')
        executor.assert_called_once()

    def test_nonempty_or_untrusted_sink_rejected_before_dispatch(self):
        for sink in ({}, [1], ()):
            executor=MagicMock()
            with self.assertRaises(ValueError): self.call(executor,sink)
            executor.assert_not_called()

    def test_location_comes_only_from_known_scheduler_code(self):
        def fail(*_): raise ValueError('DO_NOT_RETAIN')
        diagnostics=[]; self.call(fail,diagnostics)
        self.assertEqual(diagnostics[0]['location']['site'],'EXECUTE_SCHEDULE')
        self.assertIs(type(diagnostics[0]['location']['line']),int)
        self.assertNotIn('file',diagnostics[0]['location'])


class JournalLockAuditTests(unittest.TestCase):
    def test_only_cloexec_is_additionally_admitted_for_exact_worker_lock(self):
        import alpha_radar_runner as runner
        root=Path(tempfile.mkdtemp(prefix='lock-audit-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        runtime=root/'runtime';out=root/'output';journal=out/'journal'
        for path in (runtime,out,journal):path.mkdir(mode=0o700)
        plan={'root':str(journal),'rows':[]}
        base=os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW
        for role in ('worker','fixture','supervisor'):
            audit,_=runner.full_audit(runtime,out,('127.0.0.1',38493),role,plan=plan)
            for extra in (0,os.O_CLOEXEC):
                if role=='worker':audit('open',(journal/'day.lock',None,base|extra))
                else:
                    with self.assertRaises(ValueError):audit('open',(journal/'day.lock',None,base|extra))
            for altered in (base|os.O_TRUNC,base|os.O_APPEND,base|os.O_EXCL,
                            base&~os.O_NOFOLLOW,os.O_RDWR,base|os.O_NONBLOCK):
                with self.assertRaises(ValueError):audit('open',(journal/'day.lock',None,altered))
            with self.assertRaises(ValueError):audit('open',(journal/'other.lock',None,base|os.O_CLOEXEC))


class OneRequestDiagnosticTests(unittest.TestCase):
    def session(self,fail=False):
        import alpha_radar_runner as run
        root,p,r,e,_,_=FullSessionModeTests().inputs();cap=admit(p,r,expected=e,authorized_root=root)
        parents={**e,'diagnostic_descriptor':'c'*64,'diagnostic_source':'d'*64};calls=[]
        def exchange(cap,slot,at):
            from urllib.parse import urlencode
            calls.append(slot)
            if fail:raise TimeoutError('NOT_RETAINED')
            status,body=response(cap,'/slot/'+str(slot)+'?'+urlencode({'at':at}))
            return Response(status,body,'2026-09-14T13:20:00+00:00','2026-09-14T13:20:00+00:00')
        s=run.DiagnosticSession(cap,parents,clock=lambda:p['plan']['rows'][0]['valid_from'],
            wait=lambda _:self.fail('UNEXPECTED_WAIT'),stop=lambda:False,exchange=exchange)
        return s,calls

    def test_one_request_keeps_full_plan_and_rejects_second_dispatch(self):
        import alpha_radar_runner as run
        s,calls=self.session();before=canonical(s.p['plan']);value,parent=s.run()
        self.assertEqual(value['classification'],'DIAGNOSTIC_PASS');self.assertEqual(calls,[0])
        self.assertEqual((value['attempted'],value['completed'],value['reservations']),(1,1,1))
        self.assertEqual(canonical(s.p['plan']),before);self.assertEqual(len(s.p['plan']['rows']),475)
        with self.assertRaises(ValueError):s.execute(s.request(1),None)
        self.assertEqual(calls,[0])
        doc=json.loads((Path(s.p['root'])/'fs-session.json').read_bytes())
        self.assertEqual(run.diagnostic_verify(doc,parent,s.full_parents),value)
        with self.assertRaises(ValueError):run.verify_full_receipt(doc,parent,s.full_parents)
        with self.assertRaises(ValueError):run.verify_envelope(doc,content_hash(doc),parents=s.pins)

    def test_ambiguous_request_stays_consumed_no_retry_and_no_full_acceptance(self):
        s,calls=self.session(True);value,_=s.run()
        self.assertEqual(calls,[0]);self.assertEqual(value['classification'],'DIAGNOSTIC_FAILED')
        self.assertEqual(value['completed'],0)
        self.assertTrue((Path(s.p['plan']['root'])/'0.reserved.json').is_file())
        with self.assertRaises(ValueError):s.execute(s.request(0),None)
        self.assertEqual(calls,[0])

    def test_relabelled_or_reparented_diagnostic_receipt_rejected(self):
        import alpha_radar_runner as run
        parents={'diagnostic_descriptor':'a'*64};doc=run.diagnostic_envelope({'result':'TEST'},parents)
        for key,value in [('scope',run.FULL_SCOPE),('production_qualified',True),('parents',{})]:
            bad=deepcopy(doc);bad[key]=value;bad['content_hash']=content_hash({k:v for k,v in bad.items() if k!='content_hash'})
            with self.assertRaises(ValueError):run.diagnostic_verify(bad,content_hash(bad),parents)


class DiagnosticSupervisorAdmissionTests(unittest.TestCase):
    def test_only_explicit_self_and_owned_pids_admitted(self):
        import alpha_radar_runner as run
        root=Path(tempfile.mkdtemp(prefix='diagnostic-self-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        runtime=root/'runtime';out=root/'output'
        runtime.mkdir();out.mkdir()
        plan={'root':str(out/'journal'),'rows':[]}
        audit,_=run.full_audit(runtime,out,('127.0.0.1',38494),'supervisor',plan=plan,
            child_pids=lambda:(os.getpid(),))
        argv=['/bin/ps','-ww','-p',str(os.getpid()),'-o','ppid=']
        audit('subprocess.Popen',('/bin/ps',argv,None,run.LIFECYCLE_ENV))
        argv[3]=str(os.getpid()+1)
        with self.assertRaises(ValueError):audit('subprocess.Popen',('/bin/ps',argv,None,run.LIFECYCLE_ENV))
        try:audit('subprocess.Popen',('/bin/ps',argv,None,run.LIFECYCLE_ENV))
        except ValueError as error:
            diagnostic=run.diagnostic_failure(error,'STARTUP')
        self.assertEqual(diagnostic['diagnostic']['location']['site'],'NATIVE_FULL_AUDIT')


class FullSessionPreflightDifferenceTests(unittest.TestCase):
    def test_pilot_to_normal_batches_revalidates_every_prior_record(self):
        helper=FullSessionModeTests();s,now,calls,_=helper.session();helper.journal(s)
        previous=None
        for slot in range(3):
            now[0]=utc(s.p['plan']['rows'][slot]['valid_from'])
            request=s.request(slot)
            with patch.object(s,'read',wraps=s.read) as reads:
                receipt=s.execute(request,previous)
                self.assertEqual(reads.call_count,3*slot)
            previous=s.completion(request,slot,previous,receipt)
            self.assertEqual(receipt['result'],'OBSERVED')
            self.assertEqual(receipt['scope'],s.receipt_scope)
        self.assertEqual(calls,[0,1,2]);self.assertEqual(s.next_slot,3)
        self.assertEqual(len(s.p['plan']['rows']),475)
        self.assertEqual(len(s.p['plan']['rows'][0]['symbols']),10)
        self.assertEqual([len(s.p['plan']['rows'][i]['symbols']) for i in (1,2)],[100,100])

    def test_normal_batch_wrong_recovery_parent_never_dispatches(self):
        helper=FullSessionModeTests();s,now,calls,_=helper.session();helper.journal(s)
        first=s.execute(s.request(0),None)
        self.assertEqual(first['result'],'OBSERVED')
        now[0]=utc(s.p['plan']['rows'][1]['valid_from'])
        with self.assertRaises(ValueError):s.execute(s.request(1),'0'*64)
        self.assertEqual(calls,[0]);self.assertEqual(s.next_slot,1)
        self.assertFalse((Path(s.p['plan']['root'])/'1.reserved.json').exists())


class HostedFeasibilityTests(unittest.TestCase):
    def case(self):
        import alpha_radar_ci as ci
        root=Path(tempfile.mkdtemp(prefix='feasibility-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        (root/'export').mkdir()
        d=FullSessionModeTests().inputs()[4]
        proof={'workload_measurement':measured_workload()}
        env={'GITHUB_SHA':d['context']['GITHUB_SHA'],'GITHUB_RUN_ID':d['context']['GITHUB_RUN_ID'],
             'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'native','GITHUB_ENV':str(root/'step-env')}
        return ci,root,d,proof,env

    def test_request_journal_benchmark_and_conservative_cost(self):
        import alpha_radar_ci as ci
        b=measured_workload(1275.691580959)
        self.assertAlmostEqual(ci.feasibility_estimate(b,[400_000_000,450_000_000,420_000_000]),2822.73947619875)
        for bad in ({}, {'node':'different','wall_seconds':1200}, {'node':ci.WORKLOAD_NODE,'wall_seconds':float('nan')},
                    {'node':ci.WORKLOAD_NODE,'wall_seconds':float('inf')}, {'node':ci.WORKLOAD_NODE,'wall_seconds':0}):
            with self.assertRaises(ValueError):ci.feasibility_estimate(bad,[1,1,1])
        for samples in ([],[1,1],[1,1,1,1],[1,1,0],[1,1,True],[1,1,float('nan')],[1,1,30_000_000_001]):
            with self.assertRaises(ValueError):ci.feasibility_estimate(b,samples)

    def test_every_measured_component_is_counted_exactly_once(self):
        import alpha_radar_ci as ci
        b=measured_workload(1000,250_000_000_000,2380)
        c=ci.feasibility_components(b,[100_000_000,200_000_000,150_000_000])
        self.assertEqual(c['non_admission_ns'],750_000_000_000)
        self.assertEqual(c['native_admission_calls'],2855)
        self.assertEqual(c['native_admission_ns'],571_000_000_000)
        self.assertEqual(c['subtotal_ns'],1_321_000_000_000)
        self.assertEqual(c['estimated_work_seconds'],1651.25)
        # Changing embedded admission time and wall time together leaves the
        # non-admission workload unchanged. No admission is counted twice.
        moved=measured_workload(1100,350_000_000_000,2380)
        self.assertEqual(ci.feasibility_components(moved,[100_000_000,200_000_000,150_000_000]),c)
        # Increasing only residual work charges it once, followed by headroom.
        changed=measured_workload(1100,250_000_000_000,2380)
        self.assertEqual(ci.feasibility_estimate(changed,[100_000_000,200_000_000,150_000_000])-1651.25,125)

    def test_aggregate_only_or_malformed_partition_cannot_authorize_subtraction(self):
        import alpha_radar_ci as ci
        with self.assertRaises(ValueError):
            ci.workload_measurement({'node':ci.WORKLOAD_NODE,'wall_seconds':1053.447414125})
        for field,value in [('schema','old'),('wall_ns',0),('wall_ns',1_200_000_000_001),
            ('admission_ns',0),('admission_ns',1_200_000_000_000),('admission_ns',-1),
            ('admission_ns',float('nan')),('admission_ns',float('inf')),('admission_ns',True),
            ('admission_calls',2374),('admission_calls',2851),('admission_calls',True)]:
            b=measured_workload();b['cost_partition'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):ci.workload_measurement(b)
        for field in measured_workload()['cost_partition']:
            b=measured_workload();del b['cost_partition'][field]
            with self.assertRaises(ValueError):ci.workload_measurement(b)

    def test_meter_preserves_admission_arguments_result_and_exception(self):
        import alpha_radar_ci as ci
        target=MagicMock(return_value=object());clock=iter([10,20,25,40])
        meter=ci.AdmissionCostMeter(target,lambda:next(clock))
        self.assertIs(meter('package',expected='parent'),target.return_value)
        target.assert_called_once_with('package',expected='parent')
        failure=ValueError('RUNTIME_IDENTITY_CHANGED');target.side_effect=failure
        with self.assertRaises(ValueError) as caught:meter('changed')
        self.assertIs(caught.exception,failure)
        self.assertEqual((meter.calls,meter.elapsed_ns),(2,25))
        self.assertFalse(meter.active)

    def test_meter_rejects_nested_accounting_and_clock_rollback(self):
        import alpha_radar_ci as ci
        clock=iter([10,20]);meter=ci.AdmissionCostMeter(lambda:meter(),lambda:next(clock))
        with self.assertRaisesRegex(ValueError,'FEASIBILITY_MEASUREMENT'):meter()
        self.assertEqual((meter.calls,meter.elapsed_ns),(1,10))
        for ticks in ([10,10],[20,10]):
            clock=iter(ticks);meter=ci.AdmissionCostMeter(lambda:None,lambda:next(clock))
            with self.assertRaises(ValueError):meter()

    def test_timing_wrapper_restores_real_admission_after_failed_test(self):
        import alpha_radar_ci as ci,alpha_radar_admission as admission
        root=Path(tempfile.mkdtemp(dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        original=admission.verify_inputs
        class FailedBenchmark(unittest.TestCase):
            def id(self):return ci.WORKLOAD_NODE
            def runTest(self):
                self.assertIsInstance(admission.verify_inputs,ci.AdmissionCostMeter)
                self.fail('SYNTHETIC_FAILURE')
        result=ci.TimedOfflineResult(root);FailedBenchmark().run(result)
        self.assertIs(admission.verify_inputs,original)
        self.assertEqual(len(result.failures),1)
        self.assertEqual(result.timings[0]['cost_partition']['admission_calls'],0)
        self.assertTrue((root/'test-duration-0001.json').is_file())

    def publish(self,ci,root,d,proof,env,ns=400_000_000):
        ticks=[110_000_000_000]
        for i in range(3):ticks.extend([111_000_000_000+i*1_000_000_000,111_000_000_000+i*1_000_000_000+ns])
        ticks.append(114_000_000_000)
        with patch.dict(os.environ,env),patch.object(ci,'hosted'),patch.object(ci,'root_check'), \
             patch.object(ci,'require_validation',return_value=proof),patch.object(ci.time,'monotonic_ns',side_effect=ticks), \
             patch('alpha_radar_admission.verify_inputs') as verify:
            value=ci.prepare_feasibility(root,d)
            self.assertEqual(verify.call_count,3)
            for call in verify.call_args_list:self.assertEqual(call.args,(d['package'],d['runtime'],d['expected'],d['authorized_root']))
        return value

    def test_fresh_samples_round_trip_and_independent_pin(self):
        ci,root,d,proof,env=self.case();parent=ci.digest(ci.canonical(d));value=self.publish(ci,root,d,proof,env)
        self.assertFalse((root/'full-session-output').exists());self.assertFalse((root/'full-attempt.json').exists())
        d['budget']['prepared_monotonic_ns']=115_000_000_000
        env['IIOS_FEASIBILITY_SHA256']=ci.digest(ci.canonical(value))
        self.assertIn(env['IIOS_FEASIBILITY_SHA256'],(root/'step-env').read_text())
        with patch.dict(os.environ,env),patch.object(ci,'root_check'),patch.object(ci,'require_validation',return_value=proof), \
             patch.object(ci.time,'monotonic_ns',return_value=116_000_000_000):
            self.assertEqual(ci.require_feasibility(root,d,parent),value)
            with patch.dict(os.environ,{'IIOS_FEASIBILITY_SHA256':'0'*64}),self.assertRaises(ValueError):
                ci.require_feasibility(root,d,parent)
            with self.assertRaises(ValueError):ci.require_feasibility(root,d,'0'*64)
        with self.assertRaises(FileExistsError):self.publish(ci,root,d,proof,env)

    def test_over_budget_preserves_measured_values_without_launch(self):
        ci,root,d,proof,env=self.case()
        with patch.object(ci.subprocess,'Popen') as spawn,self.assertRaisesRegex(ValueError,'FEASIBILITY_EXCEEDED'):
            self.publish(ci,root,d,proof,env,ns=2_000_000_000)
        spawn.assert_not_called()
        value=json.loads((root/'export/full-feasibility.json').read_bytes())
        self.assertEqual(value['classification'],'INFEASIBLE')
        self.assertEqual(value['estimated_work_seconds'],8250)
        self.assertFalse((root/'step-env').exists());self.assertFalse((root/'full-attempt.json').exists())

    def test_missing_stale_changed_source_runtime_workload_and_replay(self):
        ci,root,d,proof,env=self.case();parent=ci.digest(ci.canonical(d));v=self.publish(ci,root,d,proof,env)
        d['budget']['prepared_monotonic_ns']=115_000_000_000
        with patch.dict(os.environ,env),patch.object(ci,'root_check'),patch.object(ci,'require_validation',return_value=proof), \
             patch.object(ci.time,'monotonic_ns',return_value=116_000_000_000):
            for key,val in [('source_commit','b'*40),('run_id','different'),('root','different'),('runtime_parent','b'*64),
                ('workload_parent','b'*64),('validation_parent','b'*64),('started_ns',99_000_000_000),
                ('finished_ns',1),('estimated_work_seconds',1),('components',{}),('work_limit_seconds',9999),('classification','INFEASIBLE')]:
                bad={**v,key:val};raw=ci.canonical(bad)
                with self.subTest(key=key),patch.object(ci,'validation_record',return_value=raw), \
                     patch.dict(os.environ,{'IIOS_FEASIBILITY_SHA256':ci.digest(raw)}),self.assertRaises(ValueError):
                    ci.require_feasibility(root,d,parent)
            with patch.object(ci,'validation_record',side_effect=FileNotFoundError),self.assertRaises(FileNotFoundError):
                ci.require_feasibility(root,d,parent)
            with patch.dict(os.environ,{'IIOS_FEASIBILITY_SHA256':ci.digest(ci.canonical(v))}), \
                 patch.object(ci.time,'monotonic_ns',return_value=215_000_000_000),self.assertRaisesRegex(ValueError,'FEASIBILITY_STALE'):
                ci.require_feasibility(root,d,parent)

    def test_gate_precedes_attempt_publication_and_spawn_and_sampling_is_charged(self):
        import alpha_radar_ci as ci,inspect
        source=inspect.getsource(ci.execute_full)
        self.assertLess(source.index('require_feasibility('),source.index("document(root/'full-attempt.json'"))
        self.assertLess(source.index('require_feasibility('),source.index('subprocess.Popen('))
        source=inspect.getsource(ci.prepare_full_descriptor)
        self.assertLess(source.index('prepare_feasibility('),source.index('prepare_job_budget('))
        self.assertEqual(ci.NATIVE_JOB_SECONDS,7200);self.assertEqual(ci.NATIVE_PREPARATION_SECONDS,300)
        self.assertEqual(ci.CLEANUP_SECONDS,180);self.assertEqual(ci.EXPORT_SECONDS,180)

    def test_failed_gate_blocks_actual_execute_entry_before_attempt_or_spawn(self):
        import alpha_radar_runner as run
        ci,root,d,proof,env=self.case()
        pins={'descriptor_parent':content_hash(d),'parents':{},'preparation_descriptor_parent':'a'*64}
        env['IIOS_EXPECTED_VALIDATION_SHA256']=d['validation_parent']
        ci.document(root/'export/full-pins.json',pins)
        with patch.dict(os.environ,env),patch.object(ci,'full_event'),patch.object(ci,'hosted'), \
             patch.object(ci,'root_check'),patch.object(run,'read_descriptor',return_value=d), \
             patch.object(run,'full_descriptor',return_value={}),patch.object(ci,'require_validation'), \
             patch.object(ci,'require_feasibility',side_effect=ValueError('FEASIBILITY_EXCEEDED')), \
             patch.object(ci.subprocess,'Popen') as spawn,self.assertRaisesRegex(ValueError,'FEASIBILITY_EXCEEDED'):
            ci.execute_full(root,explicit_request=True)
        spawn.assert_not_called()
        self.assertFalse((root/'full-attempt.json').exists());self.assertFalse((root/'full-session-output').exists())


class RehearsalBoundaryRepairTests(unittest.TestCase):
    def test_recovery_crossing_deadline_cannot_reserve_or_dispatch(self):
        helper=FullSessionModeTests();s,now,calls,_=helper.session();helper.journal(s)
        request=s.request(0);receipt=s.execute(request,None)
        previous=s.completion(request,0,None,receipt)
        now[0]=utc(s.p['plan']['rows'][1]['valid_from'])
        read=s.read;expired=[False]
        def recovery(*args,**kwargs):
            value=read(*args,**kwargs);expired[0]=True;return value
        s.stop=lambda:expired[0]
        with patch.object(s,'read',side_effect=recovery),self.assertRaisesRegex(ValueError,'FULL_CANCELLED'):
            s.execute(s.request(1),previous)
        self.assertEqual(calls,[0])
        self.assertFalse((Path(s.p['plan']['root'])/'1.reserved.json').exists())

    def test_expiry_after_reservation_preserves_consumed_slot(self):
        helper=FullSessionModeTests();s,_,calls,_=helper.session();helper.journal(s)
        reservation=Path(s.p['plan']['root'])/'0.reserved.json'
        s.stop=lambda:reservation.exists()
        with self.assertRaisesRegex(ValueError,'FULL_CANCELLED'):s.execute(s.request(0),None)
        self.assertTrue(reservation.exists());self.assertEqual(calls,[])
        self.assertEqual(s.attempted,0)
        self.assertFalse((reservation.parent/'0.complete.json').exists())

    def test_work_deadline_checked_after_stop_check(self):
        import alpha_radar_runner as run
        s,_,_,_=FullSessionModeTests().session();s.work_deadline=10
        clock=[9]
        def stop():clock[0]=10;return False
        s.stop=stop
        with patch.object(run.time,'monotonic',side_effect=lambda:clock[0]),self.assertRaisesRegex(ValueError,'NATIVE_SESSION_TIMEOUT'):
            s.check_work()

    def test_transport_admission_expiry_prevents_wire_call(self):
        import alpha_radar_runner as run
        s,_,_,_=FullSessionModeTests().session()
        def expired():raise ValueError('NATIVE_SESSION_TIMEOUT')
        with patch.object(run,'bounded_https') as wire,self.assertRaisesRegex(ValueError,'NATIVE_SESSION_TIMEOUT'):
            run.fixture_exchange(s.cap,0,CALENDAR['open'],check_deadline=expired)
        wire.assert_not_called()

    def test_tls_setup_expiry_prevents_http_request_and_closes_sockets(self):
        import provider_gateway_https as wire
        import ssl
        context=MagicMock();context.verify_mode=ssl.CERT_REQUIRED;context.check_hostname=True
        sock=MagicMock();connection=MagicMock()
        def expired():raise ValueError('NATIVE_SESSION_TIMEOUT')
        with patch.object(wire.ssl,'create_default_context',return_value=context), \
                patch.object(wire.socket,'socket',return_value=sock), \
                patch.object(wire.http.client,'HTTPSConnection',return_value=connection), \
                self.assertRaisesRegex(ValueError,'NATIVE_SESSION_TIMEOUT'):
            wire.bounded_https(host='127.0.0.1',address='127.0.0.1',port=38491,
                method='GET',target='/synthetic',headers={},body=None,tls_file='SYNTHETIC',
                timeout=20,limit=1000,before_request=expired)
        context.wrap_socket.assert_called_once()
        connection.request.assert_not_called();connection.close.assert_called_once()
        context.wrap_socket.return_value.close.assert_called_once()

    def test_observation_publishes_one_batch_after_inspection(self):
        owned,observations=FullSessionModeTests().owned();entry=owned.children['worker'];events=[]
        owned.inspect=lambda pid:(events.append('INSPECT') or observations[pid])
        original=owned.evidence
        def publish(value):events.append(value['event']);return original(value)
        owned.evidence=publish
        self.assertEqual(owned.observe(entry),entry['observation'])
        self.assertEqual(events,['INSPECT','OWNERSHIP_VERIFICATION_BATCH'])

    def test_batch_publication_failure_rejects_ownership(self):
        owned,_=FullSessionModeTests().owned()
        owned.evidence=MagicMock(side_effect=OSError('SYNTHETIC'))
        with self.assertRaises(OSError):owned.verify('worker')
        self.assertIn('DIAGNOSTIC_PUBLICATION_FAILED',owned.diagnostic_failures)

    def test_inspection_failure_survives_batch_publication_failure(self):
        owned,_=FullSessionModeTests().owned()
        primary=ValueError('ARGV_OBSERVATION_FAILED')
        owned.inspect=MagicMock(side_effect=primary)
        owned.evidence=MagicMock(side_effect=OSError('SYNTHETIC'))
        with self.assertRaises(ValueError) as caught:
            owned.verify('worker')
        self.assertIs(caught.exception,primary)
        self.assertIn('DIAGNOSTIC_PUBLICATION_FAILED',owned.diagnostic_failures)
        self.assertIn('DIAGNOSTIC_PUBLICATION_FAILED',
            owned.children['worker']['inspection_diagnostic_failures'])

    def test_inspection_failure_survives_successful_batch_publication(self):
        owned,_=FullSessionModeTests().owned()
        primary=ValueError('ARGV_OBSERVATION_FAILED')
        owned.inspect=MagicMock(side_effect=primary)
        with self.assertRaises(ValueError) as caught:
            owned.verify('worker')
        self.assertIs(caught.exception,primary)
        self.assertEqual(owned.diagnostic_failures,[])

    def test_exited_owned_worker_records_termination_without_live_inspection(self):
        owned,observations=FullSessionModeTests().owned();entry=owned.children['worker']
        child=entry['child'];child.poll.return_value=1;child.wait.side_effect=None;child.wait.return_value=1
        calls=[];owned.inspect=lambda pid:(calls.append(pid) or observations[pid])
        result=owned.cleanup(lambda:True)
        finding=result['role_findings']['worker']
        self.assertTrue(finding['termination_verified'])
        self.assertFalse(finding['cooperative_shutdown_verified'])
        self.assertFalse(result['clean']);self.assertEqual(result['remaining'],[])
        self.assertNotIn(child.pid,calls)
        child.kill.assert_not_called();child.terminate.assert_not_called()

    def test_exited_unregistered_worker_stays_unverified(self):
        owned,_=FullSessionModeTests().owned();entry=owned.children['worker']
        entry['child'].poll.return_value=1;entry['observation']=None
        result=owned.cleanup(lambda:True)
        self.assertFalse(result['role_findings']['worker']['termination_verified'])
        self.assertIn('worker',result['remaining']);self.assertFalse(result['clean'])


class DepthSeedAdmissionTests(unittest.TestCase):
    def build(self, depth):
        import alpha_radar_runner as run
        s,_=OneRequestDiagnosticTests().session();parents=s.full_parents
        manifest=run.depth_seed_manifest(s.cap,parents,depth);calls=[]
        at=manifest['measured_at']
        def exchange(cap,slot,when):
            from urllib.parse import urlencode
            calls.append(slot);status,body=response(cap,f'/slot/{slot}?'+urlencode({'at':when}))
            return Response(status,body,when,when)
        def create(value=manifest,pin=None):
            return run.DepthMeasurementSession(s.cap,parents,manifest=value,
                expected_manifest=content_hash(manifest) if pin is None else pin,
                clock=lambda:at,wait=lambda _:self.fail('WAIT'),stop=lambda:False,
                work_deadline=run.time.monotonic()+120,exchange=exchange)
        return create,manifest,calls

    def test_three_depths_seed_zero_requests_and_execute_exactly_one(self):
        import alpha_radar_runner as run
        for depth in (0,237,474):
            with self.subTest(depth=depth):
                create,m,calls=self.build(depth);s=create();before=canonical(s.p['plan'])
                s.seed();self.assertEqual(calls,[]);self.assertEqual(s.attempted,0)
                self.assertEqual(m['requests_attempted'],0);self.assertEqual(m['seed_records'],3*depth)
                result=s.run();self.assertEqual(result['classification'],'DEPTH_REQUEST_PASS',result)
                self.assertEqual(calls,[depth]);self.assertEqual((result['attempted'],result['completed']),(1,1))
                self.assertEqual(run.verify_depth_accounting(s.cap,{'depth':depth,'expected_manifest':content_hash(m)},result,s.full_parents),
                    {'seed_records':depth*3,'executed_reservations':1,'executed_responses':1,'executed_completions':1})
                self.assertEqual(canonical(s.p['plan']),before)
                self.assertGreaterEqual(result['seed_seconds'],0);self.assertGreaterEqual(result['measured_seconds'],0)
                spans=result['timings']['intervals'];self.assertTrue({'SEEDING','RECOVERY','PUBLICATION','REQUEST_EXECUTION'} <= {r['stage'] for r in spans})
                self.assertTrue(all(r['exclusive_ns']>=0 for r in spans))
                with self.assertRaises(ValueError):s.run()
                with self.assertRaises(ValueError):s.seed()
                self.assertEqual(calls,[depth])
                for item in m['rows']:
                    self.assertIsNone(item['response']['value']['actual_dispatch_time'])
                    self.assertEqual(item['response']['origin'],'SYNTHETIC_SEED')
                fd=s.open_root(s.p['plan']['root'])
                try:doc=run.read_record(fd,f'{depth}.complete.json')
                finally:os.close(fd)
                with self.assertRaises(ValueError):run.verify_full_receipt(doc,content_hash(doc),s.full_parents)
                with self.assertRaises(ValueError):run.diagnostic_verify(doc,content_hash(doc),s.full_parents)

    def test_manifest_missing_altered_reordered_and_wrong_parent_rejected(self):
        create,m,calls=self.build(237)
        mutations=[lambda v:v['rows'].pop(),lambda v:v['rows'].reverse(),
            lambda v:v['rows'][0]['reservation']['value'].update(slot=1),
            lambda v:v.update(last_completion_parent='0'*64),
            lambda v:v.update(source_commit='0'*40),lambda v:v.update(depth=474)]
        for mutate in mutations:
            bad=deepcopy(m);mutate(bad)
            with self.assertRaises(ValueError):create(bad)
            with self.assertRaises(ValueError):create(bad,content_hash(bad))
        self.assertEqual(calls,[])

    def test_missing_and_altered_seed_disk_records_fail_before_dispatch(self):
        for kind in ('missing','altered'):
            create,m,calls=self.build(237);s=create();s.seed()
            path=Path(s.p['plan']['root'])/'0.reserved.json'
            if kind=='missing':path.unlink()
            else:
                path.chmod(0o600);path.write_bytes(b'{}');path.chmod(0o400)
            result=s.run();self.assertEqual(result['classification'],'DEPTH_REQUEST_FAILED')
            self.assertEqual(calls,[])
            self.assertFalse((path.parent/'237.reserved.json').exists())
            with self.assertRaises(ValueError):s.run()

    def test_seed_expiration_and_existing_destination_fail_closed(self):
        create,_,calls=self.build(0);s=create();s.work_deadline=1
        with self.assertRaises(ValueError):s.seed()
        create,_,calls=self.build(0);s=create();Path(s.p['plan']['root']).mkdir()
        with self.assertRaises(FileExistsError):s.seed()
        self.assertEqual(calls,[])

    def test_wrong_previous_parent_and_wrong_clock_fail_before_exchange(self):
        create,_,calls=self.build(0);s=create();s.seed()
        with self.assertRaises(ValueError):s.execute(s.request(0),'0'*64)
        s.clock=lambda:'2026-09-14T00:00:00+00:00'
        with self.assertRaises(ValueError):s.run()
        self.assertEqual(calls,[])


class CompactDepthTimingTests(unittest.TestCase):
    def test_real_loading_compact_binding_all_depths_and_wrong_hash(self):
        import alpha_radar_runner as run
        from alpha_session_execution import publish,safe_root
        for depth in (0,237,474):
            create,m,_=DepthSeedAdmissionTests().build(depth);s=create()
            compact={'depth':depth,'expected_manifest':content_hash(m)}
            root=Path(tempfile.mkdtemp(dir=os.environ['IIOS_GATEWAY_TEST_ROOT'],prefix='compact-'))
            name='compact-'+str(depth)+'.json';fd=safe_root(root)
            try:pin=publish(fd,name,compact)
            finally:os.close(fd)
            loaded=run.read_descriptor(root/name,pin)
            self.assertEqual(run.regenerate_depth_seed(s.p,s.pins,s.full_parents,loaded),m)
            self.assertLess((root/name).stat().st_size,8000000)
            bad={**loaded,'expected_manifest':'0'*64}
            with self.assertRaises(ValueError):run.regenerate_depth_seed(s.p,s.pins,s.full_parents,bad)
            with self.assertRaises(ValueError):run.read_descriptor(root/name,'0'*64)
            with self.assertRaises(ValueError):run.regenerate_depth_seed(s.p,s.pins,s.full_parents,{**loaded,'manifest':m})

    def test_oversized_loader_still_rejects(self):
        import alpha_radar_runner as run
        root=Path(tempfile.mkdtemp(dir=os.environ['IIOS_GATEWAY_TEST_ROOT'],prefix='oversized-'));path=root/'oversized-timing.json'
        with path.open('xb') as f:f.write(b' '*8000001)
        with self.assertRaisesRegex(ValueError,'DESCRIPTOR_SIZE'):run.read_descriptor(path,'0'*64)

    def test_nested_timing_and_failure_are_retained_without_addition(self):
        import alpha_radar_runner as run
        ticks=iter([10,20,30,40]);t=run.DepthTimings('worker',lambda:next(ticks))
        def inner():raise ValueError('SYNTHETIC')
        with self.assertRaises(ValueError):t.measure('REQUEST_EXECUTION',lambda:t.measure('RECOVERY',inner))
        report=t.report();a,b=report['intervals']
        self.assertEqual((a['start_ns'],a['end_ns']),(10,40));self.assertEqual(b['parent'],a['id'])
        self.assertIn('NOT_ADDITIVE',report['accounting']);self.assertEqual(a['exclusive_ns'],20);self.assertEqual(b['exclusive_ns'],10)

    def test_timing_rollback_invalid_stage_and_bound_rejected(self):
        import alpha_radar_runner as run
        for ticks in ([10,9],[0,800000000001],[True]):
            it=iter(ticks);t=run.DepthTimings('worker',lambda:next(it))
            with self.assertRaises(ValueError):t.measure('SEEDING',lambda:None)
        with self.assertRaises(ValueError):run.DepthTimings('worker').measure('UNTRUSTED',lambda:None)

    def test_supervisor_registration_and_cleanup_spans_preserve_calls(self):
        import alpha_radar_runner as run
        owned=run.DiagnosticOwnedProcesses.__new__(run.DiagnosticOwnedProcesses)
        ticks=iter([1,2,3,4]);owned.depth_timings=run.DepthTimings('supervisor',lambda:next(ticks))
        with patch.object(run.FullOwnedProcesses,'register',return_value='registered') as register, patch.object(run.FullOwnedProcesses,'cleanup',side_effect=ValueError('SYNTHETIC')) as cleanup:
            self.assertEqual(owned.register('worker',None,deadline=1),'registered')
            register.assert_called_once_with(owned,'worker',None,deadline=1)
            with self.assertRaises(ValueError):owned.cleanup(None)
            cleanup.assert_called_once_with(owned,None)
        report=owned.depth_timings.report()
        self.assertEqual([r['stage'] for r in report['intervals']],['SUPERVISOR_ACTIVITY','CLEANUP'])
        self.assertEqual(report['actor'],'supervisor')


class DepthOuterSupervisorTests(unittest.TestCase):
    def fixture(self,depth=0,fail=None,exit_at=2):
        import alpha_radar_runner as run
        clock=[0];events=[]
        class Backend:
            def __init__(self):self.depth=depth
            def prepare(self,start):events.append('prepare')
            def launch(self):
                events.append('launch')
                if fail=='launch':raise ValueError('SYNTHETIC')
            def register(self,*args):
                events.append('register')
                if fail=='identity':raise ValueError('PROCESS_IDENTITY')
            def poll(self):return 0 if clock[0]>=exit_at*10**9 else None
            def pump(self):
                if fail=='stream':raise ValueError('DIAGNOSTIC_OVERFLOW')
            def cancel(self):
                events.append('cancel')
                if fail=='identity':raise ValueError('PROCESS_IDENTITY')
            def finish(self):
                events.append('finish')
                if fail or self.poll() is None:raise ValueError('OUTER_EXIT_UNVERIFIED')
                return {'cleanup':True}
            def export(self,result):
                events.append('export')
                if fail=='export':raise OSError('NOT_RETAINED')
        return Backend(),clock,events,lambda:clock[0],lambda seconds:clock.__setitem__(0,clock[0]+int(seconds*10**9))

    def test_three_sequential_cases_and_budgets(self):
        import alpha_radar_runner as run
        b,clock,events,now,pause=self.fixture();cases=[]
        for depth in run.DEPTHS:
            c,_,_,_,_=self.fixture(depth);c.poll=lambda:0;cases.append((depth,c))
        result=run.run_depth_outer_series(cases,now=now,pause=pause)
        self.assertEqual(result['classification'],'PASS');self.assertEqual(len(result['results']),3)
        for row in result['results']:
            self.assertEqual(row['export_deadline_ns']-row['start_ns'],800_000_000_000)
            self.assertEqual(row['cleanup_deadline_ns']-row['work_deadline_ns'],180_000_000_000)

    def test_work_timeout_retains_failure_and_exports_after_cleanup(self):
        import alpha_radar_runner as run
        b,c,e,now,pause=self.fixture(exit_at=450)
        result=run.run_depth_outer_case(b,now=now,pause=pause,series_deadline=2_400_000_000_000)
        self.assertEqual(result['classification'],'FAILED');self.assertIn('cancel',e);self.assertIn('finish',e);self.assertEqual(e[-1],'export')
        self.assertGreaterEqual(c[0],450_000_000_000);self.assertLess(c[0],620_000_000_000)

    def test_partial_start_identity_stream_child_and_export_failures_stop_series(self):
        import alpha_radar_runner as run
        for failure in ('launch','identity','stream','export'):
            b,c,e,now,pause=self.fixture(fail=failure)
            second,_,e2,_,_=self.fixture(depth=237);third,_,e3,_,_=self.fixture(depth=474)
            result=run.run_depth_outer_series([(0,b),(237,second),(474,third)],now=now,pause=pause)
            self.assertEqual(result['classification'],'FAILED');self.assertEqual(len(result['results']),1)
            self.assertIn('finish',e);self.assertIn('export',e);self.assertEqual(e2+e3,[])

    def test_surviving_child_reaches_export_without_signal_or_green(self):
        import alpha_radar_runner as run
        b,c,e,now,pause=self.fixture(exit_at=1000)
        result=run.run_depth_outer_case(b,now=now,pause=pause,series_deadline=2_400_000_000_000)
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['signals'],0)
        self.assertGreaterEqual(c[0],620_000_000_000);self.assertLess(c[0],800_000_000_000)
        self.assertEqual(e[-1],'export')

    def test_no_start_when_budget_or_depth_order_invalid(self):
        import alpha_radar_runner as run
        b,c,e,now,pause=self.fixture()
        with self.assertRaises(ValueError):run.run_depth_outer_case(b,now=now,pause=pause,series_deadline=799_000_000_000)
        self.assertEqual(e,[])
        with self.assertRaises(ValueError):run.run_depth_outer_series([(237,b)],now=now,pause=pause)

    def test_export_deadline_and_clock_rollback_fail(self):
        import alpha_radar_runner as run
        b,c,e,now,pause=self.fixture(exit_at=0)
        b.export=lambda result:c.__setitem__(0,801_000_000_000)
        result=run.run_depth_outer_case(b,now=now,pause=pause,series_deadline=2_400_000_000_000)
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['failures'][-1]['stage'],'EXPORT')
        b,c,e,now,pause=self.fixture(exit_at=0);b.prepare=lambda start:c.__setitem__(0,-1)
        result=run.run_depth_outer_case(b,now=now,pause=pause,series_deadline=2_400_000_000_000)
        self.assertEqual(result['classification'],'FAILED');self.assertNotIn('launch',e)

    def test_unverified_outer_owner_cannot_cancel(self):
        import alpha_radar_runner as run
        b=run.DepthOuterCase('unused','a'*64,0);b.child=MagicMock();b.child.poll.return_value=None
        with patch.object(run,'publish') as publish:
            with self.assertRaises(ValueError):b.cancel()
        publish.assert_not_called()

    def test_depth_child_uses_descriptor_package_not_unbound_global(self):
        import alpha_radar_runner as run
        import ast,inspect,textwrap
        tree=ast.parse(textwrap.dedent(inspect.getsource(run.diagnostic_child)))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='regenerate_depth_seed']
        self.assertEqual(len(calls),1)
        self.assertEqual(ast.dump(calls[0].args[0]),ast.dump(ast.parse("d['package']",mode='eval').body))

    def test_actual_depth_child_branch_reaches_seed_session_without_native_calls(self):
        import alpha_radar_runner as run
        import time
        package={'plan':{'rows':[{'valid_from':'synthetic'}]}}
        d={'package':package,'runtime':{},'expected':{},'authorized_root':'synthetic',
            'schema':'iios-local-depth-measurement-descriptor-v1','source_parent':'a'*64,
            'measurement':{'depth':0,'expected_manifest':'b'*64},
            'work_deadline_ns':time.monotonic_ns()+100_000_000_000,'cleanup_deadline_ns':time.monotonic_ns()+280_000_000_000}
        start=time.monotonic_ns();phase={'descriptor_parent':content_hash(d),'role':'worker','start_ns':start,'deadline_ns':start+100_000_000_000}
        d['work_deadline_ns']=phase['deadline_ns'];phase['descriptor_parent']=content_hash(d)
        launch={**run.DIAG_FLAGS,'descriptor':d,'role':'worker','parent_pid':os.getppid(),'output_identity':[1,2],'phase':phase}
        seed={'measured_at':'synthetic','parents':{}}
        original_open=os.open
        with patch.dict(os.environ,run.DIAG_ENV,clear=True), patch.object(run,'diagnostic_descriptor',return_value={}), patch.object(run,'verify_inputs',return_value={}), patch.object(run,'SyntheticCapability'), patch.object(run,'native_identity'), patch.object(run,'diagnostic_audit',return_value=(lambda *a:None,original_open)), patch.object(run.sys,'addaudithook'), patch.object(run.os,'open',original_open), patch.object(run,'full_startup',return_value={}), patch.object(run,'diagnostic_store',return_value='c'*64), patch.object(run,'diagnostic_read',return_value=({},'c'*64)), patch.object(run,'regenerate_depth_seed',return_value=seed) as regenerate, patch.object(run,'DepthMeasurementSession') as session:
            self.assertEqual(run.diagnostic_child(launch,'c'*64),0)
        regenerate.assert_called_once_with(package,{}, {'measurement_source':'a'*64},d['measurement'])
        session.return_value.seed.assert_called_once();session.return_value.run.assert_called_once()


class SeedReconciliationTests(unittest.TestCase):
    def journal(self):
        import alpha_radar_runner as run
        root,p,r,e,_,_=FullSessionModeTests().inputs()
        cap=admit(p,r,expected=e,authorized_root=root)
        parents={**e,'seed_measurement':'a'*64}
        manifest=run.reconciliation_seed_manifest(cap,parents)
        journal=Path(p['plan']['root']);journal.mkdir(mode=0o700)
        (journal/'day.lock').touch(mode=0o600)
        fd=run.safe_root(journal)
        try:
            for item,row in zip(manifest['rows'],p['plan']['rows']):
                Path(row['root']).mkdir(mode=0o700);child=run.safe_root(row['root'])
                try:
                    for dest,name,key in ((fd,f"{item['slot']}.reserved.json",'reservation'),
                        (child,'ALPHA_VANTAGE.receipt.json','response'),
                        (fd,f"{item['slot']}.complete.json",'completion')):
                        doc=item[key]
                        run.verify_depth_record(doc,content_hash(doc),parents,'SYNTHETIC_SEED')
                        run.publish(dest,name,doc)
                finally:os.close(child)
        finally:os.close(fd)
        return run,cap,parents,manifest

    def test_complete_seed_reconciliation_zero_requests_and_cross_scope_rejection(self):
        run,cap,parents,m=self.journal()
        value=run.reconcile_seed_journal(cap,parents,m,content_hash(m))
        self.assertEqual([value[k] for k in ('seed_reservations','seed_responses','seed_completions')],[475]*3)
        self.assertEqual(value['requests_attempted'],0);self.assertEqual(value['requests_completed'],0)
        self.assertFalse(value['production_qualified']);self.assertEqual(value['authority'],run.AUTHORITY)
        forged={'classification':'FULL_SYNTHETIC_PASS','attempted':475,'completed':475,'reservations':475,
            'receipt_parents':[content_hash(v['response']) for v in m['rows']]}
        with self.assertRaises(ValueError):run.full_accounting(cap,parents,forged)
        with self.assertRaises(ValueError):run.depth_seed_documents(cap.documents()[0],cap.documents()[2],parents,475)

    def test_seed_hash_order_parent_and_content_mutations_rejected(self):
        run,cap,parents,m=self.journal()
        with self.assertRaises(ValueError):run.reconcile_seed_journal(cap,parents,m,'0'*64)
        for mutate in (lambda x:x['rows'].reverse(),lambda x:x['rows'].pop(),
                       lambda x:x['parents'].update(seed_measurement='b'*64),
                       lambda x:x['rows'][237]['response']['value'].update(result='ALTERED')):
            bad=deepcopy(m);mutate(bad)
            with self.assertRaises(ValueError):run.reconcile_seed_journal(cap,parents,bad,content_hash(bad))

    def test_seed_missing_altered_record_and_expired_deadline_rejected(self):
        run,cap,parents,m=self.journal();original=run.read_record
        def altered(fd,name,**kw):
            doc=original(fd,name,**kw)
            if name=='237.complete.json':doc['value']['previous']='0'*64
            return doc
        with patch.object(run,'read_record',side_effect=altered),self.assertRaises(ValueError):
            run.reconcile_seed_journal(cap,parents,m,content_hash(m))
        with patch.object(run,'read_record',side_effect=FileNotFoundError),self.assertRaises(FileNotFoundError):
            run.reconcile_seed_journal(cap,parents,m,content_hash(m))
        with patch.object(run,'read_record') as read,self.assertRaisesRegex(ValueError,'TEST_DEADLINE'):
            run.reconcile_seed_journal(cap,parents,m,content_hash(m),check_deadline=lambda:run.require(False,'TEST_DEADLINE'))
        read.assert_not_called()

    def test_full_wrapper_keeps_full_verifier_and_never_accepts_seed_result(self):
        import alpha_radar_runner as run
        root,p,r,e,_,_=FullSessionModeTests().inputs();cap=admit(p,r,expected=e,authorized_root=root)
        session={'classification':'FULL_SYNTHETIC_PASS','attempted':475,'completed':475,'reservations':475,
                 'receipt_parents':[f'{i:064x}' for i in range(475)]}
        with patch.object(run,'_reconcile_full_journal',return_value={'test':'ONLY_MOCKED'}) as traversal:
            self.assertEqual(run.full_accounting(cap,e,session),{'test':'ONLY_MOCKED'})
            self.assertIs(traversal.call_args.args[4],run.verify_full_receipt)
            self.assertEqual(traversal.call_args.args[5],run.FULL_SCOPE)
            for mutation in ({'classification':'SEED_RECONCILIATION_ONLY'}, {'attempted':0},
                             {'completed':474}, {'receipt_parents':['0'*64]*475}):
                traversal.reset_mock()
                with self.assertRaises(ValueError):run.full_accounting(cap,e,{**session,**mutation})
                traversal.assert_not_called()


class TailMeasurementAdapterTests(unittest.TestCase):
    def test_manual_gate_is_exclusive_and_strict(self):
        import alpha_radar_ci as ci
        good={'inputs':{'tail_measurement_only':True}}
        self.assertTrue(ci.tail_execution_allowed('workflow_dispatch',good,True))
        for event in ('push','pull_request','schedule',''):
            self.assertFalse(ci.tail_execution_allowed(event,good,True))
        for value in (None,1,0,'TRUE','',[],{}):
            self.assertFalse(ci.tail_execution_allowed('workflow_dispatch',{'inputs':{'tail_measurement_only':value}},True))
        for name in ('full_session_only','lifecycle_only','native_startup','unknown'):
            v=deepcopy(good);v['inputs'][name]=True
            self.assertFalse(ci.tail_execution_allowed('workflow_dispatch',v,True))

    def test_other_modes_reject_tail_mode(self):
        import alpha_radar_ci as ci
        for mode,gate in (('full_session_only',ci.full_execution_allowed),
                ('lifecycle_only',ci.lifecycle_execution_allowed),('native_startup',ci.native_execution_allowed)):
            self.assertFalse(gate('workflow_dispatch',{'inputs':{mode:True,'tail_measurement_only':True}},True))

    def test_independent_allocations_and_one_request(self):
        import alpha_radar_ci as ci
        self.assertEqual(ci.TAIL_LIMITS['depth'],474)
        self.assertEqual(ci.TAIL_LIMITS['actual_requests'],1)
        self.assertEqual([ci.TAIL_LIMITS[k] for k in ('work_seconds','cleanup_seconds','export_seconds','total_seconds')], [440,180,180,800])
        self.assertEqual((ci.FULL_WORK_SECONDS,ci.NATIVE_JOB_SECONDS,ci.CLEANUP_SECONDS,ci.EXPORT_SECONDS),(6000,7200,180,180))

    def export_fixture(self):
        import alpha_radar_runner as run
        root=Path(tempfile.mkdtemp(prefix='iios-provider-connection-source-tests-tail-unit-',dir='/private/tmp'))
        out=root/'one-request-output';out.mkdir();(root/'export').mkdir()
        parents={'test':'a'*64}
        doc=run.diagnostic_envelope({'event':'SAFE_SYNTHETIC'},parents)
        path=out/'fs-final.json';path.write_bytes(canonical(doc));path.chmod(0o400)
        return root,{'package':{'root':str(out)},'expected':{},'source_parent':'b'*64},parents,path

    def test_export_keeps_diagnostic_scope_and_all_records(self):
        import alpha_radar_ci as ci
        import alpha_radar_runner as run
        root,d,parents,path=self.export_fixture()
        with patch.object(run,'diagnostic_descriptor',return_value=parents):
            result=ci.export_tail_records(root,d,root/'export/tail-records',10,now=lambda:1)
        self.assertEqual(result['files'],1)
        copied=json.loads((root/'export/tail-records/record-00000.json').read_bytes())
        self.assertEqual(copied,json.loads(path.read_bytes()))
        with self.assertRaises(ValueError):run.verify_full_receipt(copied,content_hash(copied),parents)
        with self.assertRaises(FileExistsError):
            (root/'export/tail-records/inventory.json').open('x')

    def test_export_deadline_and_tamper_rejection(self):
        import alpha_radar_ci as ci
        import alpha_radar_runner as run
        for failure in ('deadline','hash','mode','symlink'):
            root,d,parents,path=self.export_fixture()
            if failure=='hash':
                path.chmod(0o600);doc=json.loads(path.read_bytes());doc['value']={'event':'ALTERED'}
                path.write_bytes(canonical(doc));path.chmod(0o400)
            if failure=='mode':path.chmod(0o600)
            if failure=='symlink':(path.parent/'fs-alias.json').symlink_to(path)
            with patch.object(run,'diagnostic_descriptor',return_value=parents):
                with self.assertRaises(ValueError):
                    ci.export_tail_records(root,d,root/'export/tail-records',10,now=lambda:10 if failure=='deadline' else 1)

    def test_post_tail_timing_is_separate_and_bounded(self):
        import alpha_radar_runner as run
        clock=iter([1,5]);t=run.DepthTimings('supervisor',clock=lambda:next(clock))
        self.assertEqual(t.measure('POST_SESSION',lambda:42),42)
        self.assertEqual(t.report()['intervals'][0]['exclusive_ns'],4)
        self.assertIn('CONCURRENT_ACTORS_NOT_ADDITIVE',t.report()['accounting'])

    def test_volume_records_are_inert_and_deterministic(self):
        import alpha_radar_ci as ci
        import alpha_radar_runner as run
        value=ci.tail_volume_record(12,512,'a'*64)
        self.assertEqual(value,ci.tail_volume_record(12,512,'a'*64))
        self.assertEqual(len(value['padding']),512)
        self.assertEqual(value['requests_attempted'],0)
        self.assertFalse(value['production_qualified'])
        self.assertEqual(value['kind'],'EXPORT_VOLUME_ONLY')
        for args in ((-1,1,'a'*64),(50000,1,'a'*64),(1,-1,'a'*64),(1,8_000_001,'a'*64),(1,2,'wrong')):
            with self.assertRaises(ValueError):ci.tail_volume_record(*args)
        with self.assertRaises((ValueError,KeyError)):run.verify_full_receipt(value,content_hash(value),{})

    def test_volume_export_cannot_ignore_deadline(self):
        import alpha_radar_ci as ci
        with patch.object(ci,'put') as put:
            with self.assertRaises(ValueError):
                ci.export_tail_volume(Path('/unused'),{'files':1,'bytes':1,'inventory_parent':'a'*64},10,now=lambda:10)
            put.assert_not_called()

    def test_tail_interval_rejects_clock_failures(self):
        import alpha_radar_runner as run
        self.assertEqual(run.bounded_tail_interval(1,2)['end_ns'],2)
        for start,end in ((2,1),(-1,2),(1,float('nan')),(1,10**18),(True,2),(0,800_000_000_001)):
            with self.assertRaises(ValueError):run.bounded_tail_interval(start,end)

    def test_upload_reserve_does_not_borrow_work_time(self):
        import alpha_radar_ci as ci
        self.assertEqual(ci.tail_upload_minutes(180_000_000_000,1),2)
        self.assertEqual(ci.tail_upload_minutes(180_000_000_000,105_000_000_000),1)
        for deadline,now in ((180_000_000_000,121_000_000_000),(6000_000_000_000,1),
                (10,10),(float('inf'),0),(-1,0)):
            with self.assertRaises(ValueError):ci.tail_upload_minutes(deadline,now)

    def test_wrong_source_blocks_before_native_backend(self):
        import alpha_radar_ci as ci
        import alpha_radar_runner as run
        root=Path(tempfile.mkdtemp(prefix='iios-provider-connection-source-tests-tail-source-',dir='/private/tmp'))
        (root/'export').mkdir()
        (root/'export/tail-pins.json').write_text(json.dumps({'scope':ci.TAIL_SCOPE,'limits':ci.TAIL_LIMITS,'source_commit':'a'*40}))
        with patch.object(ci,'tail_event'),patch.object(ci,'require_validation'),                patch.dict(os.environ,{'GITHUB_SHA':'b'*40}),patch.object(run,'DepthOuterCase') as backend:
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN'):ci.execute_tail(root)
            backend.assert_not_called()


class TailPrerequisiteRepairTests(unittest.TestCase):
    def test_tail_import_exact_scope_and_parents(self):
        import alpha_radar_ci as ci, base64
        root=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])
        event=root/'tail-event.json'
        event.write_bytes(ci.canonical({'inputs':{'tail_measurement_only':True,'expected_source_commit':'a'*40}}))
        env={'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'12345','GITHUB_RUN_ATTEMPT':'1',
             'GITHUB_JOB':'tail-measurement','GITHUB_REF':'refs/heads/feature/iios-provider-gateway-superbatch-1',
             'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_EVENT_PATH':str(event)}
        with patch.dict(os.environ,env),patch.object(ci,'hosted'):
            proof=QualificationBudgetTests().proof()
            def invoke(value,parent=None):
                raw=ci.canonical(value)
                with patch.dict(os.environ,{'IIOS_VALIDATION_PROOF':base64.b64encode(raw).decode(),
                    'IIOS_EXPECTED_VALIDATION_SHA256':parent or ci.digest(raw)}):ci.import_validation(root)
            with patch.object(ci,'put') as put:
                invoke(proof);put.assert_called_once()
            for key,value in [('scope',ci.TAIL_SCOPE),('source_commit','b'*40),('run_id','2'),('job','tail-measurement')]:
                bad=deepcopy(proof);bad[key]=value
                with patch.object(ci,'put') as put:
                    with self.assertRaises(ValueError):invoke(bad)
                    put.assert_not_called()
            with patch.object(ci,'put') as put:
                with self.assertRaises(ValueError):invoke(proof,'b'*64)
                put.assert_not_called()
            for key,value in [('GITHUB_JOB','unrelated'),('GITHUB_EVENT_NAME','push'),('GITHUB_REF','refs/heads/main')]:
                with patch.dict(os.environ,{key:value}),patch.object(ci,'put') as put:
                    with self.assertRaises(ValueError):invoke(proof)
                    put.assert_not_called()
            event.write_bytes(ci.canonical({'inputs':{'tail_measurement_only':True,'full_session_only':True,'expected_source_commit':'a'*40}}))
            with patch.object(ci,'put') as put:
                with self.assertRaises(ValueError):invoke(proof)
                put.assert_not_called()

    def test_canonical_outer_start_survives_elapsed_check(self):
        import alpha_radar_runner as run
        b,c,e,now,pause=DepthOuterSupervisorTests().fixture(exit_at=0)
        c[0]=1
        result=run.run_depth_outer_case(b,now=now,pause=pause,series_deadline=800_000_000_000,canonical_start_ns=0)
        self.assertEqual(result['classification'],'PASS')
        self.assertEqual(result['start_ns'],0)
        self.assertEqual(result['export_deadline_ns'],800_000_000_000)
        self.assertEqual(result['work_deadline_ns'],440_000_000_000)

    def test_outer_single_tick_mutation_expiry_and_types(self):
        import alpha_radar_runner as run
        for start,end,observed in [(0,800_000_000_001,1),(1,800_000_000_000,2),
                (0,799_999_999_999,1),(0,800_000_000_000,800_000_000_000),
                (True,800_000_000_000,1),(0,800_000_000_000.0,1),(2,800_000_000_002,1)]:
            b,c,e,now,pause=DepthOuterSupervisorTests().fixture(exit_at=0);c[0]=observed
            with self.assertRaises(ValueError):
                run.run_depth_outer_case(b,now=now,pause=pause,series_deadline=end,canonical_start_ns=start)
            self.assertEqual(e,[])
