"""Offline Northstar graph and actual publisher/browser-contract regressions."""
import json
import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

from truth_spine_frontend_graph import validate_northstar_graph
from truth_spine_full_day_service import service_response
import test_truth_spine_session as fixtures
import test_truth_spine_frontend_provenance as provenance


def pinned_test_node():
    """Use setup-node/PATH while retaining the independently required version."""
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('PINNED_NODE_REQUIRED')
    node = str(Path(node).resolve())
    version = subprocess.check_output([node, '--version'], text=True, timeout=10).strip()
    if version != 'v24.19.0':
        raise RuntimeError('NODE_VERSION_MISMATCH')
    return node


class NorthstarGraphTests(unittest.TestCase):
    def setUp(self):
        self.files = {'northstar-session.html': b'<script src="/review/assets/northstar-session-a.js"></script><link href="/review/assets/northstar-session-b.css">',
                      'assets/northstar-session-a.js': b'const portrait="/review/assets/portrait-c.png";',
                      'assets/northstar-session-b.css': b'main{display:block}', 'assets/portrait-c.png': b'fixture-image'}

    def test_complete_graph(self): self.assertEqual(len(validate_northstar_graph(self.files)['files']), 4)

    def test_missing_asset(self):
        del self.files['assets/portrait-c.png']
        with self.assertRaisesRegex(ValueError, 'MISSING_ASSET'): validate_northstar_graph(self.files)

    def test_extra_unbound_asset(self):
        self.files['assets/old-d.png'] = b'old'
        with self.assertRaisesRegex(ValueError, 'UNBOUND_ASSET'): validate_northstar_graph(self.files)

    def test_private_path_and_map_rejection(self):
        for body in [b'//# sourceMappingURL=bad', b'"/private/tmp/unbound"']:
            self.files['assets/northstar-session-a.js'] = body
            with self.assertRaisesRegex(ValueError, 'PATH_OR_MAP'): validate_northstar_graph(self.files)

    def test_html_cannot_escape_packaged_assets(self):
        self.files['northstar-session.html'] += b'<script src="https://invalid.example/unbound.js"></script>'
        with self.assertRaisesRegex(ValueError, 'HTML_GRAPH'): validate_northstar_graph(self.files)

    def test_retained_fixture_and_maps_forbidden(self):
        for name in ['fixtures/expansion-wing.json', 'assets/x.map', '../x.js']:
            f = {**self.files, name: b'bad'}
            with self.assertRaisesRegex(ValueError, 'INVENTORY'): validate_northstar_graph(f)

    def test_hash_bound_bytes_and_symlinks_rejected(self):
        p = provenance.p
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for key, value in self.files.items():
                target = root/key; target.parent.mkdir(exist_ok=True); target.write_bytes(value)
            rows = p.validate_outputs(root, northstar=True)
            (root/'assets/portrait-c.png').write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError, 'OUTPUT_MISMATCH'): p.validate_outputs(root, rows, northstar=True)
            (root/'assets/portrait-c.png').unlink(); (root/'assets/portrait-c.png').symlink_to(root/'northstar-session.html')
            with self.assertRaisesRegex(ValueError, 'SYMLINK'): p.validate_outputs(root, northstar=True)

    def test_source_review_provenance_not_installable(self):
        p = provenance.p
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root/'frontend-provenance.json').write_text(json.dumps({'schema':'iios-source-review-build-NOT-INSTALLABLE',
                'inputs':{},'input_hash':'','outputs':[],'output_hash':'','observation':{},'content_hash':''}))
            with self.assertRaisesRegex(ValueError, 'SCHEMA_INVALID'): p.verify(root, root, 'a'*40)


class NorthstarPublisherTests(unittest.TestCase):
    setUp = fixtures.ProductionPathTests.setUp
    write_cycle = fixtures.ProductionPathTests.write_cycle
    actual_probes = fixtures.ProductionPathTests.actual_probes

    def test_actual_publisher_view_is_admitted_without_projection_manufacturing(self):
        self.assertEqual(self.supervisor.cycle()['ready'], 200)
        code, view = service_response(self.root/'topology.json', '/truth-spine/full-session', now=self.clock())
        self.assertEqual(code, 200)
        self.assertEqual(view['factory'], json.loads((self.root/'projections/current.json').read_bytes())['factory'])
        frontend = Path(__file__).resolve().parents[2]/'FRONT END'
        script = "import {admitProjection} from './src/northstarSession.ts';let s='';for await(const c of process.stdin)s+=c;const x=JSON.parse(s);await admitProjection(x,null,Date.parse(x.published_at));console.log('ADMITTED_ACTUAL_PUBLISHER');"
        result = subprocess.run([pinned_test_node(),'--input-type=module','-e',script], cwd=frontend,
                                input=json.dumps(view),text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('ADMITTED_ACTUAL_PUBLISHER',result.stdout)

    def test_navigation_gets_cannot_create_activity(self):
        self.supervisor.cycle()
        before = self.store.watermark()
        with patch('socket.create_connection', side_effect=AssertionError('NO_PROVIDER_NETWORK')):
            for _ in range(10):
                code, view = service_response(self.root/'topology.json','/truth-spine/full-session',now=self.clock())
                self.assertEqual(code,200); self.assertTrue(all(v is False for v in view['capabilities'].values()))
        self.assertEqual(self.store.watermark(),before)


class FixtureCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2]/'scripts/truth_spine_northstar_browser.py'
        spec = importlib.util.spec_from_file_location('northstar_browser_contract', path)
        cls.runner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.runner
        spec.loader.exec_module(cls.runner)

    def test_fixture_is_bound_once_and_immutable_across_requests(self):
        seed = {'published_at':'2026-09-11T13:30:00Z','source_generation':'a'*64}
        bound = self.runner.BoundFixture.bind(seed)
        seed['published_at'] = '2026-09-11T13:30:05Z'
        for _ in range(20):
            self.assertEqual(hashlib.sha256(bound.response()).hexdigest(), bound.sha256)
            self.assertEqual(json.loads(bound.response())['published_at'],'2026-09-11T13:30:00Z')
        with self.assertRaises(AttributeError): bound.body = b'changed'

    def test_per_request_timestamp_regeneration_is_rejected(self):
        original = self.runner.BoundFixture.bind({'published_at':'2026-09-11T13:30:00Z'})
        altered = self.runner.BoundFixture.bind({'published_at':'2026-09-11T13:30:05Z'})
        with self.assertRaisesRegex(ValueError,'FIXTURE_BYTES_CHANGED'):
            self.runner.BoundFixture(altered.body,original.sha256).response()

    def capture(self):
        identity = {'generation':'a'*64,'projection_content_hash':'b'*64,'fixture_sha256':'c'*64,
                    'generated_at':'2026-09-11T13:30:00Z','source_cycle':'d'*64,'status':'CURRENT'}
        return {'name':'offline','beforeIdentity':{'binding':identity,'polling_sequence':1},
                'afterIdentity':{'binding':copy.deepcopy(identity),'polling_sequence':2},'screenshotGeometryMatches':True}

    def test_identical_poll_during_capture_is_accepted(self):
        evidence = {'captures':[]}; data = self.capture()
        self.runner.admit_capture(evidence,data)
        self.assertEqual(evidence['captures'],[data])
        self.assertNotIn('rejected_captures',evidence)

    def test_changing_generation_hash_timestamp_or_state_rejects_screenshot(self):
        for field in self.capture()['beforeIdentity']['binding']:
            with self.subTest(field=field):
                evidence = {'captures':[]}; data = self.capture()
                data['afterIdentity']['binding'][field] = 'changed'
                with self.assertRaisesRegex(RuntimeError,'SCREENSHOT_GENERATION_CHANGED'):
                    self.runner.admit_capture(evidence,data)
                self.assertEqual(evidence['captures'],[])
                self.assertEqual(evidence['rejected_captures'],[data])

    def test_geometry_and_responsive_failure_still_reject_without_tolerance(self):
        for field,value in [('screenshotGeometryMatches',False),('responsiveFailure',True)]:
            evidence = {'captures':[]}; data = self.capture(); data[field] = value
            with self.assertRaises(RuntimeError): self.runner.admit_capture(evidence,data)
            self.assertEqual(evidence['captures'],[])
            self.assertEqual(len(evidence['rejected_captures']),1)

    def test_server_has_no_per_request_constructor_or_clock(self):
        import inspect
        source = inspect.getsource(self.runner.main)
        block = source.split("if path == '/truth-spine/full-session':")[1].split('elif path in files:')[0]
        self.assertIn('fixture.response()',block)
        for forbidden in ['datetime.now','deepcopy','northstarFixture','published_at','content_hash\'] =']:
            self.assertNotIn(forbidden,block)
        self.assertLess(source.index('BoundFixture.bind(seed)'),source.index("server=FixtureHTTPServer"))
        self.assertIn("'fixture':binding_receipt",source)

    def test_individual_cleanup_and_persistence_errors_do_not_skip_later_steps(self):
        for failing in ['save', 'session', 'driver', 'server', 'receipt']:
            called = []
            def step(name):
                called.append(name)
                if name == failing: raise RuntimeError('ISOLATED_TEST_FAILURE')
            names = ['save', 'session', 'driver', 'server', 'receipt']
            result = self.runner.independent_cleanup([(name, lambda name=name: step(name)) for name in names])
            self.assertEqual(called, names)
            self.assertEqual([r['step'] for r in result if not r['ok']], [failing])
            self.assertEqual(result[names.index(failing)]['category'], 'RuntimeError')

    def test_provenance_schema_and_hash_rejection_precedes_inputs_or_startup(self):
        for record in [{}, {'schema':'untrusted','inputs':{},'input_hash':'','outputs':[],
                            'output_hash':'','observation':{},'content_hash':''}]:
            with tempfile.TemporaryDirectory() as name:
                root=Path(name).resolve()
                (root/'frontend-provenance.json').write_text(json.dumps(record))
                with patch('socket.socket', side_effect=AssertionError('NO_LISTENER')):
                    with self.assertRaisesRegex(ValueError,'REVIEW_PROVENANCE_SCHEMA'):
                        self.runner.verify_review_provenance(root, root)

    def test_all_image_paths_have_one_geometry_and_identity_admission_boundary(self):
        import inspect
        source=inspect.getsource(self.runner.main)
        self.assertIn("path.endswith('/screenshot')",source)
        self.assertIn("before['frame']==after['frame']",source)
        self.assertIn("before['active']==after['active']",source)
        self.assertIn('admit_capture(admissions,receipt)',source)
        self.assertLess(source.index('verify_review_provenance('),source.index('output.mkdir('))
        self.assertLess(source.index('verify_review_provenance('),source.index('FixtureHTTPServer('))
        self.assertIn('stop_verified_process',source)
        self.assertIn('EVIDENCE_PERSISTENCE_FAILED',source)

    def test_required_lines_accumulate_across_scroll_positions(self):
        import inspect
        source=inspect.getsource(self.runner.main)
        self.assertIn("id:i+':'+j",source)
        self.assertIn("if row['visible']:seen.add(row['id'])",source)
        self.assertNotIn("row['visible']==row['total']",source)

    def test_settlement_diagnostic_instruments_original_wait_before_repair(self):
        source=self.runner.SETTLEMENT_GEOMETRY
        for stage in ['fonts-wait-started','fonts-wait-completed','image-inventory-created',
                      'image-wait-started','image-wait-completed','frame-request','frame-callback',
                      'geometry-sample','stable-consecutive-samples','timer-macrotask-probe','microtask-probe']:
            self.assertIn(stage,source)
        self.assertIn('performance.now()',source)
        self.assertIn('document.visibilityState',source)
        self.assertIn('document.hasFocus()',source)
        self.assertNotIn('source:img.currentSrc',source)

    def test_outer_watchdog_and_failure_image_are_not_acceptance(self):
        import inspect
        source=inspect.getsource(self.runner.main)
        self.assertIn('threading.Timer(8',source)
        self.assertIn('watchdog.join(timeout=1)',source)
        self.assertIn('DIAGNOSTIC_ONLY_NOT_ACCEPTED',source)
        self.assertIn('progress_path.write_bytes(encoded(progress))',source)


class TemporaryLifecycleTests(unittest.TestCase):
    setUpClass=classmethod(FixtureCaptureTests.setUpClass.__func__)

    def inventory(self,port=None,pid=123,family='IPv4',state='LISTEN'):
        return {'listeners':[] if port is None or state!='LISTEN' else [{'address':('127.0.0.1:' if family=='IPv4' else '[::1]:')+str(port),'pid':pid,'family':family,'state':state}], 'sockets':[] if port is None else [str(port)+' '+state]}

    def clear(self,rows,**kwargs):
        recorded=[];iterator=iter(rows)
        result=self.runner.stable_port_clear(recorded.append,lambda:next(iterator),wait=lambda _:None,**kwargs)
        return result,recorded

    def test_5291_unknown_owner_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'UNOWNED_LISTENER'):self.clear([self.inventory(5291)])

    def test_5292_unknown_owner_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'UNOWNED_LISTENER'):self.clear([self.inventory(5292)])

    def test_time_wait_is_not_a_listener(self):
        x=self.inventory(5291,state='TIME_WAIT');result,rows=self.clear([x]*3)
        self.assertEqual(result,x);self.assertEqual(len(rows),3)

    def test_ipv4_ipv6_must_both_have_expected_owner(self):
        x=self.inventory(5292);x['listeners']+=self.inventory(5292,pid=456,family='IPv6')['listeners']
        with self.assertRaisesRegex(RuntimeError,'LISTENER_IDENTITY'):self.runner.listener_binding(x,5292,123)
        x['listeners'][1]['pid']=123
        self.assertEqual(len(self.runner.listener_binding(x,5292,123)),2)

    def test_no_wildcard_listener_is_admitted(self):
        x=self.inventory(5291);x['listeners'][0]['address']='*:5291'
        with self.assertRaises(RuntimeError):self.runner.listener_binding(x,5291,123)

    def test_delayed_socket_close_is_observed_not_assumed(self):
        x=self.inventory();result,rows=self.clear([self.inventory(5291),x,x,x],reject_listener=False)
        self.assertEqual(len(rows),4);self.assertEqual(result,x)

    def test_child_exit_does_not_excuse_remaining_listener(self):
        with self.assertRaisesRegex(RuntimeError,'PORT_CLEAR_NOT_STABLE'):
            self.clear([self.inventory(5292)]*4,reject_listener=False,limit=4)

    def test_consecutive_identical_observations_required(self):
        a=self.inventory();b=self.inventory(5291,state='TIME_WAIT')
        result,rows=self.clear([a,b,a,a,a]);self.assertEqual(len(rows),5)
        with self.assertRaisesRegex(RuntimeError,'PORT_CLEAR_NOT_STABLE'):self.clear([a,b,a,b],limit=4)

    def test_no_simultaneous_fixture_owners_or_probe_bind(self):
        import inspect
        self.assertTrue(self.runner.FixtureHTTPServer.allow_reuse_address)
        self.assertFalse(self.runner.FixtureHTTPServer.allow_reuse_port)
        code=inspect.getsource(self.runner.main)
        self.assertNotIn('s.bind(',code)
        self.assertEqual(code.count("FixtureHTTPServer(('127.0.0.1',5291),Handler)"),1)

    def test_bind_failure_incident_precedes_ready_receipt(self):
        import inspect
        code=inspect.getsource(self.runner.main)
        self.assertLess(code.index('FIXTURE_BIND_FAILED'),code.index("output/'startup.json'"))
        self.assertIn("'errno':getattr(exc,'errno',None)",code)

    def test_readiness_failure_cannot_publish_ready(self):
        import inspect
        code=inspect.getsource(self.runner.main)
        for gate in ['FIXTURE_HTTP_NOT_READY','WEBDRIVER_READY_DEADLINE','WEBDRIVER_START_IDENTITY_CHANGED']:
            self.assertLess(code.index(gate),code.index("output/'startup.json'"))

    def test_partial_startup_still_closes_server_and_log(self):
        import inspect
        code=inspect.getsource(self.runner.main)
        self.assertIn('server=None;thread=None;driver_log=None',code)
        self.assertIn("('driver_log',lambda:driver_log.close() if driver_log else None)",code)
        self.assertIn("lambda:server.server_close() if server else None",code)

    def test_cleanup_exception_does_not_skip_ports(self):
        calls=[]
        def fail():raise RuntimeError('injected')
        result=self.runner.independent_cleanup([('first',fail),('ports',lambda:calls.append('ports'))])
        self.assertFalse(result[0]['ok']);self.assertEqual(calls,['ports'])

    def test_mismatched_process_is_never_signaled(self):
        from unittest.mock import Mock
        p=Mock(pid=123);p.poll.return_value=None
        with self.assertRaisesRegex(RuntimeError,'NO_SIGNAL'):self.runner.stop_verified_process(p,'expected',lambda _: 'different')
        p.terminate.assert_not_called();p.wait.assert_not_called()

    def test_owned_process_exit_is_waited(self):
        from unittest.mock import Mock
        p=Mock(pid=123);p.poll.return_value=None
        self.runner.stop_verified_process(p,'expected',lambda _: 'expected')
        p.terminate.assert_called_once();p.wait.assert_called_once_with(timeout=10)

    def test_prior_child_alive_or_log_open_blocks_next_diagnostic(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'cleanup.json'
            base={'classification':'DIAGNOSTIC_ONLY','processes_exited':True,'logs_closed':True,'ports_stable':True,'owned_pids':[123]}
            path.write_text(json.dumps(base))
            with self.assertRaisesRegex(RuntimeError,'PRIOR_OWNED_PROCESS_ALIVE'):self.runner.verify_prior_cleanup(path,lambda _: 'alive')
            self.runner.verify_prior_cleanup(path,lambda _: '')
            for key in ['processes_exited','logs_closed','ports_stable']:
                path.write_text(json.dumps({**base,key:False}))
                with self.assertRaisesRegex(RuntimeError,'PRIOR_CLEANUP_INCOMPLETE'):self.runner.verify_prior_cleanup(path,lambda _: '')

    def test_repeated_sequential_clearance_has_independent_observations(self):
        for _ in range(3):
            _,rows=self.clear([self.inventory()]*3);self.assertEqual(len(rows),3)

    def safari_case(self):
        pins={'launcher':{'path':'/system/launcher'},'helper':{'path':'/system/owned-apple-xpc'}}
        for role,pin in pins.items():pin.update(sha256=role+'-hash',mode=0o755,uid=0,code_identity=role,code_verified=True,requirement='apple '+role,designated_requirement='apple '+role,bundle={'fixture':'pinned'})
        launcher={'pid':10,'ppid':9,'uid':501,'started':100,'executable':pins['launcher']['path']}
        listener={'pid':11,'ppid':1,'uid':501,'started':100,'executable':pins['helper']['path']}
        launcher['artifact']=dict(pins['launcher']);listener['artifact']=dict(pins['helper'])
        return dict(inventory=self.inventory(5292,pid=11),launcher=launcher,listener=listener,baseline=[],started=100.2,now=100.9,executables=pins,uid=501)

    def test_known_new_apple_xpc_dual_stack_listener(self):
        args=self.safari_case();args['inventory']['listeners']+=self.inventory(5292,pid=11,family='IPv6')['listeners']
        value=self.runner.authenticate_safari_listener(**args)
        self.assertEqual(value['role'],'APPLE_WEBDRIVER_XPC');self.assertEqual(value['signal_target'],'VERIFIED_LAUNCHER_ONLY')

    def test_preexisting_xpc_is_not_adopted(self):
        args=self.safari_case();args['baseline']=[args['listener']]
        with self.assertRaisesRegex(RuntimeError,'PREEXISTING'):self.runner.authenticate_safari_listener(**args)

    def test_exact_apple_incoming_cryptex_transition_requires_all_pins(self):
        args=self.safari_case();path='/System/Volumes/Preboot/Cryptexes/OS/System/helper'
        args['executables']['helper']['path']=path
        args['listener']['executable']=path.replace('/Cryptexes/OS/','/Cryptexes/Incoming/OS/')
        args['listener']['artifact']['path']=args['listener']['executable']
        self.assertEqual(self.runner.authenticate_safari_listener(**args)['role'],'APPLE_WEBDRIVER_XPC')
        for key,value in [('sha256','changed'),('code_verified',False),('code_identity','other'),('requirement','other'),('bundle',{}),('mode',0o777),('uid',501)]:
            import copy
            changed=copy.deepcopy(args);changed['listener']['artifact'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):self.runner.authenticate_safari_listener(**changed)

    def test_unmodeled_path_with_same_hash_is_rejected(self):
        args=self.safari_case();args['listener']['executable']='/unknown/apple/helper';args['listener']['artifact']['path']=args['listener']['executable']
        with self.assertRaisesRegex(RuntimeError,'UNMODELED'):self.runner.authenticate_safari_listener(**args)

    def test_stable_ownership_rejects_reuse_receipt_and_wrong_roles(self):
        import copy
        args=self.safari_case();value=self.runner.authenticate_safari_listener(**args);rows=[]
        receipt=args['launcher'];self.assertEqual(self.runner.stable_safari_ownership(lambda:value,rows.append,receipt,wait=lambda _:None)['stable_observations'],3)
        for key in ['pid','ppid','started','uid','executable']:
            altered={**receipt,key:'wrong'}
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'RECEIPT'):self.runner.stable_safari_ownership(lambda:value,lambda _:None,altered,wait=lambda _:None)
        changed=copy.deepcopy(value);changed['listener']['started']=101
        seq=iter([value,changed])
        with self.assertRaisesRegex(RuntimeError,'IDENTITY_CHANGED'):self.runner.stable_safari_ownership(lambda:next(seq),lambda _:None,receipt,wait=lambda _:None)
        args['inventory']=self.inventory(5291,pid=11)
        with self.assertRaisesRegex(RuntimeError,'LISTENER_IDENTITY'):self.runner.authenticate_safari_listener(**args)

    def test_wrong_binary_user_age_parent_and_duplicate_owner_rejected(self):
        for field,value in [('executable','/untrusted/process'),('uid',502),('started',99),('ppid',45)]:
            args=self.safari_case();args['listener'][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):self.runner.authenticate_safari_listener(**args)
        args=self.safari_case();args['inventory']['listeners']+=self.inventory(5292,pid=12,family='IPv6')['listeners']
        with self.assertRaises(RuntimeError):self.runner.authenticate_safari_listener(**args)

    def test_missing_child_and_late_start_rejected(self):
        args=self.safari_case();args['listener']=None
        with self.assertRaises(RuntimeError):self.runner.authenticate_safari_listener(**args)
        args=self.safari_case();args['now']=120
        with self.assertRaises(RuntimeError):self.runner.authenticate_safari_listener(**args)

    def test_transaction_is_single_invocation_and_single_close(self):
        records=[];t=self.runner.AcceptanceTransaction(records.append)
        for before,after in [('NEW','PREFLIGHT'),('PREFLIGHT','FIXTURE_READY'),('FIXTURE_READY','READY'),('READY','BROWSER_OPEN'),('BROWSER_OPEN','CLOSED')]:t.advance(before,after)
        for before,after in [('NEW','PREFLIGHT'),('READY','BROWSER_OPEN'),('BROWSER_OPEN','CLOSED')]:
            with self.assertRaisesRegex(RuntimeError,'TRANSACTION_ORDER'):t.advance(before,after)
        self.assertEqual(len(records),5)

    def test_receipt_failure_does_not_publish_success_or_prevent_cleanup(self):
        def fail(_):raise OSError('injected disk failure')
        t=self.runner.AcceptanceTransaction(fail)
        with self.assertRaises(OSError):t.advance('NEW','PREFLIGHT')
        self.assertEqual(t.state,'NEW');self.assertEqual(t.history,[])
        called=[]
        result=self.runner.independent_cleanup([('receipt',lambda:t.advance('NEW','CLOSED')),('ports',lambda:called.append('ports'))])
        self.assertFalse(result[0]['ok']);self.assertEqual(called,['ports'])

    def test_one_actual_session_no_port_rebind_between_viewports(self):
        import inspect
        code=inspect.getsource(self.runner.main)
        self.assertEqual(code.count("wd('POST','/session',"),1)
        self.assertEqual(code.count("wd('DELETE','/session/'+sid)"),1)
        self.assertEqual(code.count("subprocess.Popen([SAFARI_LAUNCHER"),1)
        self.assertEqual(code.count("FixtureHTTPServer(('127.0.0.1',5291),Handler)"),1)
        self.assertLess(code.index("wd('POST','/session',"),code.index('for width in [1512,1020,386]'))

    def test_each_image_retains_stable_sample_hashes(self):
        import inspect
        code=inspect.getsource(self.runner.main)
        self.assertIn("'consecutive_matches':settlement['consecutiveMatches']",code)
        self.assertIn("for s in settlement['samples']",code)
        self.assertIn("'build_input_hash':record['input_hash']",code)

    def test_owned_foreground_acquisition_preserves_context_and_is_bounded(self):
        base={'handle':'owned','url':'fixture','identity':{'generation':'fixed'},'active':['BUTTON','policy'],'scroll':[0,0],'visible':True,'focused':False}
        rows=iter([base,base,{**base,'focused':True}]);selected=[];events=[]
        result=self.runner.acquire_owned_browser_focus(lambda:next(rows),selected.append,'owned',events.append,wait=lambda _:None)
        self.assertTrue(result['focused']);self.assertEqual(selected,['owned']);self.assertEqual(len(events),3)
        selected.clear()
        self.runner.acquire_owned_browser_focus(lambda:{**base,'focused':True},selected.append,'owned',lambda _:None)
        self.assertEqual(selected,[])
        with self.assertRaisesRegex(RuntimeError,'UNAVAILABLE'):self.runner.acquire_owned_browser_focus(lambda:base,selected.append,'owned',lambda _:None,limit=2,wait=lambda _:None)

    def test_foreground_never_adopts_a_foreign_or_changed_context(self):
        base={'handle':'owned','url':'fixture','identity':'fixed','active':'policy','scroll':[0,0],'visible':True,'focused':False}
        for key,value in [('handle','other'),('url','other'),('identity','other'),('active','other'),('scroll',[1,0])]:
            rows=iter([base,{**base,key:value,'focused':True}])
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'CONTEXT_CHANGED'):self.runner.acquire_owned_browser_focus(lambda:next(rows),lambda _:None,'owned',lambda _:None,wait=lambda _:None)
        selected=[]
        with self.assertRaisesRegex(RuntimeError,'OWNERSHIP_MISMATCH'):self.runner.acquire_owned_browser_focus(lambda:base,selected.append,'foreign',lambda _:None)
        self.assertEqual(selected,[])

    def test_native_foreground_is_explicit_once_and_still_requires_observed_focus(self):
        base={'handle':'owned','url':'fixture','identity':'fixed','active':'policy','scroll':[0,0],'visible':False,'focused':False}
        rows=iter([base,{**base,'focused':True,'visible':True}]);actions=[];events=[]
        self.runner.acquire_owned_browser_focus(lambda:next(rows),lambda _:actions.append('webdriver'),'owned',events.append,activate_native=lambda row:actions.append('native') or {'window_id':7})
        self.assertEqual(actions,['webdriver','native']);self.assertEqual(events[1]['stage'],'native-window-acquisition')
        with self.assertRaisesRegex(RuntimeError,'UNAVAILABLE'):self.runner.acquire_owned_browser_focus(lambda:base,lambda _:None,'owned',lambda _:None,activate_native=lambda _:7,limit=2,wait=lambda _:None)

    def test_native_window_binding_requires_exact_fixture_url_and_receipt(self):
        url='http://127.0.0.1:5291/review/northstar-session.html?fullSession=1#gallery'
        with patch.object(self.runner.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'7\n','')) as invoke:
            self.assertEqual(self.runner.safari_fixture_window(url),7)
            initial=invoke.call_args.args[0][-1];self.assertNotIn('\nactivate\n',initial)
            self.assertEqual(self.runner.safari_fixture_window(url,7,activate=True),7)
            script=invoke.call_args.args[0][-1]
            for token in ['count of matches is not 1','selectedID is not 7','URL of current tab','set index of window id selectedID to 1','application id "com.apple.Safari"']:self.assertIn(token,script)
            self.assertNotIn('front window',script);self.assertNotIn('set current tab',script)
            for bad in ['https://example.invalid','http://127.0.0.1:5176/',url+'\nactivate']:
                invoke.reset_mock()
                with self.assertRaisesRegex(RuntimeError,'URL_INVALID'):self.runner.safari_fixture_window(bad,7,activate=True)
                invoke.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'RECEIPT_REQUIRED'):self.runner.safari_fixture_window(url,activate=True)
            for bad in [True,0,'7',-1]:
                with self.assertRaisesRegex(RuntimeError,'ID_INVALID'):self.runner.safari_fixture_window(url,bad,activate=True)

    def test_native_window_changed_missing_or_timed_out_fails_closed(self):
        url='http://127.0.0.1:5291/review/northstar-session.html?fullSession=1'
        for value in ['8','unknown','0']:
            with patch.object(self.runner.subprocess,'run',return_value=subprocess.CompletedProcess([],0,value,'')),self.assertRaisesRegex(RuntimeError,'RECEIPT_INVALID'):self.runner.safari_fixture_window(url,7,activate=True)
        for error in [subprocess.CalledProcessError(1,[],stderr='private details'),subprocess.TimeoutExpired([],8)]:
            with patch.object(self.runner.subprocess,'run',side_effect=error),self.assertRaisesRegex(RuntimeError,'NATIVE_WINDOW_ACQUISITION_FAILED') as caught:self.runner.safari_fixture_window(url,7,activate=True)
            self.assertNotIn('private details',str(caught.exception))


class PortableSettlementTests(unittest.TestCase):
    setUpClass=classmethod(FixtureCaptureTests.setUpClass.__func__)

    def node(self,body,core_only=True):
        code=self.runner.SETTLEMENT_GEOMETRY
        if core_only:code=code.split('// PORTABLE_CORE_BEGIN:')[1].split('// PORTABLE_CORE_END')[0].split('\n',1)[1]
        script="const vm=require('node:vm'),assert=require('node:assert/strict');const api=vm.runInNewContext("+json.dumps(code)+"+'\\n({createSettlementCore,runSettlement"+('' if core_only else ',browserTelemetryAdapter,settleNorthstar')+"})',{});"+body
        result=subprocess.run([pinned_test_node(),'-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout

    def setup_js(self):
        return """
const geometry={coordinateSpace:'viewport-css-px',url:'fixture',destination:'Gallery',viewport:[1512,825,1,1512,1512],scroll:[0,0,0,0],fonts:'loaded',pendingAnimations:0,elements:[],text:[]};
const row=(at,change={})=>({at,identity:{generation:'fixed',source:'frozen'},geometry:{...geometry,...change}});
const core=()=>api.createSettlementCore({start:0,timeoutMs:100,destination:'Gallery'});
"""

    def test_core_has_no_browser_globals_or_import_side_effects(self):
        code=self.runner.SETTLEMENT_GEOMETRY.split('// PORTABLE_CORE_BEGIN:')[1].split('// PORTABLE_CORE_END')[0]
        import re
        self.assertIsNone(re.search(r'\b(window|document|navigator|performance|requestAnimationFrame|HTMLElement)\b',code))
        self.node("assert.equal(typeof api.createSettlementCore,'function');")

    def test_core_runs_without_window_and_document(self):
        self.node(self.setup_js()+"const c=core();c.accept(row(1));c.accept(row(2));assert.equal(c.accept(row(3)).ok,true);")

    def test_zero_frames(self):
        self.node(self.setup_js()+"const r=core().expire(100);assert.equal(r.failureCategory,'ZERO_FRAMES');assert.equal(r.ok,false);")

    def test_one_frame(self):
        self.node(self.setup_js()+"const c=core();c.accept(row(1));assert.equal(c.expire(100).failureCategory,'ONE_FRAME');")

    def test_changing_geometry(self):
        self.node(self.setup_js()+"const c=core();for(let i=1;i<5;i++)c.accept(row(i,{viewport:[i]}));assert.equal(c.expire(100).ok,false);")

    def test_two_stable_consecutive_pairs_pass(self):
        self.node(self.setup_js()+"const c=core();assert.equal(c.accept(row(1)),null);assert.equal(c.accept(row(2)),null);const r=c.accept(row(3));assert.equal(r.ok,true);assert.equal(r.consecutiveMatches,2);assert.equal(r.samples.length,3);")

    def test_exact_deadline_and_late_callback(self):
        self.node(self.setup_js()+"const c=core();assert.equal(c.expire(99),null);assert.equal(c.accept(row(100)).ok,false);assert.equal(c.accept(row(101)).samples.length,0);")

    def test_generation_and_source_change(self):
        for key in ['source','generation']:
            self.node(self.setup_js()+"const c=core();c.accept(row(1));const x=row(2);x.identity["+json.dumps(key)+"]='changed';assert.equal(c.accept(x).failureCategory,'IDENTITY_CHANGED');")

    def test_prerequisite_failure(self):
        self.node(self.setup_js()+"const c=core(),x=row(1);x.prerequisites={documentVisible:false};assert.equal(c.accept(x).ok,false);")

    def test_repeated_runs_retain_no_state_and_output_is_plain(self):
        self.node(self.setup_js()+"const run=()=>{const c=core();c.accept(row(1));c.accept(row(2));return c.accept(row(3));};const a=run(),b=run();assert.equal(JSON.stringify(a),JSON.stringify(b));assert.deepEqual(JSON.parse(JSON.stringify(a)),JSON.parse(JSON.stringify(b)));assert(!JSON.stringify(a).includes('window'));")

    def test_injected_scheduler_clock_and_telemetry(self):
        result=self.node(self.setup_js()+self.registration_js()+"""
let time=0,callback=null,timer=null;const registered=signal();
const deps={now:()=>time,schedule:f=>{callback=f;registered.emit();return 1},cancel:()=>{callback=null},timer:f=>(timer=f,2),clearTimer:()=>{timer=null},ready:()=>Promise.resolve(),telemetry:()=>row(time)};
bounded(async()=>{const p=api.runSettlement({timeoutMs:100,destination:'Gallery'},deps);for(let i=1;i<=3;i++){await registration(registered,i,p);assert.equal(typeof callback,'function');time++;callback();}const r=await p;assert.equal(r.ok,true);assert.equal(r.samples.length,3);assert.equal(callback,null);assert.equal(timer,null);assert.equal(registered.pending(),0);console.log('REGISTERED_SUCCESS');});
""")
        self.assertIn('REGISTERED_SUCCESS',result)

    @staticmethod
    def registration_js():
        return """
// Test-owned observable events, never a guessed number of microtasks.
const signal=()=>{let count=0,waiters=[];return {
 emit(){count++;const ready=waiters.filter(w=>w.target<=count);waiters=waiters.filter(w=>w.target>count);for(const w of ready)w.resolve();},
 wait(target){if(count>=target)return {promise:Promise.resolve(),cancel(){}};let entry;const promise=new Promise(resolve=>{entry={target,resolve};waiters.push(entry)});return {promise,cancel(){waiters=waiters.filter(w=>w!==entry)}};},
 pending:()=>waiters.length
}};
const registration=async(event,target,result)=>{const wait=event.wait(target);try{return await Promise.race([wait.promise,result.then(r=>{throw new Error('settled before registration: '+r.reason)})]);}finally{wait.cancel();}};
// A deadline only detects a hung test; it never establishes readiness.
const bounded=task=>{let timer;const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('TEST_DEADLINE')),2000)});return Promise.race([Promise.resolve().then(task),deadline]).catch(e=>{console.error(e);process.exitCode=1}).finally(()=>clearTimeout(timer));};
"""

    def test_registration_signal_handles_arbitrary_ready_microtask_depth(self):
        for depth in (0,1,7):
            with self.subTest(depth=depth):
                self.scheduler_scenario("""
deps.ready=()=>{let ready;for(let i=0;i<DEPTH;i++)ready=Promise.resolve(ready).then(()=>undefined);return ready};
const p=start();for(let frame=1;frame<=3;frame++){await registration(invoked,frame,p);assert.equal(callbacks.length,frame);now=frame;callbacks[frame-1]();}
const r=await p;assert.equal(r.ok,true);assert.equal(r.samples.length,3);assert.equal(invoked.pending(),0);assert.deepEqual(cleared,['timer']);
""".replace('DEPTH',str(depth)))

    def test_missing_registration_has_structured_deadline_and_no_waiter_leak(self):
        self.scheduler_scenario("""
const entered=signal();deps.ready=()=>{entered.emit();return new Promise(()=>{})};
const p=start();await registration(entered,1,p);const waiting=registration(invoked,1,p).then(()=>assert.fail('unexpected registration'),e=>e);
now=100;deadlineCallback();const r=await p;assert.equal(r.ok,false);assert.equal(r.failureCategory,'ZERO_FRAMES');assert.equal(r.failure.stage,'deadline');assert.equal(callbacks.length,0);assert.match((await waiting).message,/settled before registration/);assert.equal(invoked.pending(),0);assert.deepEqual(cleared,['timer']);assert.doesNotThrow(()=>JSON.stringify(r));
""")

    def test_adapter_exception_is_structured(self):
        self.node(self.setup_js()+"""
const deps={now:()=>0,schedule:()=>{throw Error('private diagnostic')},cancel:()=>{},timer:()=>1,clearTimer:()=>{},ready:()=>Promise.resolve(),telemetry:()=>row(1)};
api.runSettlement({timeoutMs:100},deps).then(r=>{assert.equal(r.failureCategory,'ADAPTER_EXCEPTION');assert(!JSON.stringify(r).includes('private diagnostic'));}).catch(e=>{console.error(e);process.exitCode=1});
""")

    def test_browser_adapter_missing_capabilities_fails_closed(self):
        self.node("const r=api.browserTelemetryAdapter();assert.equal(r.ok,false);assert.equal(r.reason,'BROWSER_CAPABILITY_MISSING');assert(r.missing.includes('window'));assert(r.missing.includes('document'));",False)

    def test_browser_telemetry_uses_declared_plain_records(self):
        code=self.runner.SETTLEMENT_GEOMETRY.split('function browserTelemetryAdapter')[1].split('async function settleNorthstar')[0]
        self.assertIn('return JSON.parse(JSON.stringify({geometry,identity:{binding,initialBinding},prerequisites}))',code)
        for field in ['documentReady','documentVisible','focused','targetConnected','targetVisible','focusUnchanged','imagesReady']:
            self.assertIn(field,code)

    def test_real_runner_explicitly_selects_browser_adapter(self):
        import inspect
        self.assertIn("options={'browser':True}",inspect.getsource(self.runner.main))
        self.assertIn("watchdog.join(timeout=1)",inspect.getsource(self.runner.main))

    def scheduler_scenario(self,body):
        result=self.node(self.setup_js()+self.registration_js()+"""
let now=0,next=0,callbacks=[],deadlineCallback,cancelled=[],cleared=[],completions=0;
const invoked=signal(),cancelledSignal=signal();
const deps={now:()=>now,schedule:fn=>{callbacks.push(fn);return ++next},cancel:h=>cancelled.push(h),timer:fn=>{deadlineCallback=fn;return 'timer'},clearTimer:h=>cleared.push(h),ready:()=>Promise.resolve(),telemetry:()=>row(now)};
const start=()=>{const schedule=deps.schedule,cancel=deps.cancel;deps.schedule=fn=>{try{return schedule(fn)}finally{invoked.emit()}};deps.cancel=h=>{try{return cancel(h)}finally{cancelledSignal.emit()}};return api.runSettlement({timeoutMs:100,destination:'Gallery'},deps).then(r=>{completions++;return r});};
bounded(async()=>{
"""+body+"\nassert.equal(completions,1);assert.equal(invoked.pending(),0);console.log('SCENARIO_PASSED');});")
        self.assertIn('SCENARIO_PASSED',result)

    def test_first_scheduler_throw_has_complete_sanitized_evidence(self):
        self.scheduler_scenario("""
deps.schedule=()=>{throw new TypeError('never persist this payload')};const p=start();const r=await p;
assert.equal(r.ok,false);assert.equal(r.failure.stage,'frame-scheduler');assert.equal(r.failure.errorType,'TypeError');assert.equal(r.failure.frameCount,0);assert.equal(r.failure.elapsedMonotonicMs,0);assert.equal(r.failure.lastValidGeometry,null);assert.equal(r.failure.identity,null);assert(!JSON.stringify(r).includes('never persist'));assert.deepEqual(cleared,['timer']);
""")

    def test_later_scheduler_throw_after_one_frame_preserves_geometry(self):
        self.scheduler_scenario("""
let calls=0;deps.schedule=fn=>{if(calls++)throw new RangeError('secret');callbacks.push(fn);return 1};const p=start();await registration(invoked,1,p);now=7;callbacks[0]();const r=await p;
assert.equal(r.failure.frameCount,1);assert.equal(r.failure.elapsedMonotonicMs,7);assert.equal(r.failure.identity.generation,'fixed');assert.equal(r.failure.lastValidGeometry.destination,'Gallery');assert.equal(r.failure.errorType,'RangeError');assert.deepEqual(cancelled,[1]);assert.deepEqual(cleared,['timer']);
""")

    def test_scheduler_rejected_promise_is_consumed(self):
        self.scheduler_scenario("deps.schedule=()=>Promise.reject(new Error('payload'));const r=await start();assert.equal(r.failureCategory,'ADAPTER_EXCEPTION');assert.equal(r.failure.stage,'frame-scheduler');assert.deepEqual(cleared,['timer']);")

    def test_timer_and_frame_scheduler_rejections_complete_once(self):
        self.scheduler_scenario("""
let rejectTimer,rejectFrame;deps.timer=()=>new Promise((_,reject)=>{rejectTimer=reject});deps.schedule=()=>new Promise((_,reject)=>{rejectFrame=reject});const p=start();await registration(invoked,1,p);rejectTimer(Error('one'));rejectFrame(Error('two'));const r=await p;assert.equal(r.ok,false);assert.equal(r.failure.stage,'deadline-scheduler');
""")

    def test_callback_after_completion_cannot_change_result(self):
        self.scheduler_scenario("const p=start();await registration(invoked,1,p);const late=callbacks[0];now=100;deadlineCallback();const r=await p;const before=JSON.stringify(r);now=101;late();assert.equal(JSON.stringify(r),before);assert.equal(callbacks.length,1);")

    def test_cleanup_error_cannot_skip_other_handle_cleanup(self):
        self.scheduler_scenario("deps.cancel=()=>{throw Error('cancel failed')};const p=start();await registration(invoked,1,p);now=100;deadlineCallback();const r=await p;assert.equal(r.ok,false);assert.equal(r.failureCategory,'SCHEDULER_CLEANUP_FAILED');assert.deepEqual(cleared,['timer']);assert(r.cleanup.some(x=>!x.ok));")

    def test_async_cleanup_error_becomes_failed_closed(self):
        self.scheduler_scenario("deps.cancel=()=>Promise.reject(new Error('hidden'));const p=start();await registration(invoked,1,p);now=100;deadlineCallback();const r=await p;assert.equal(r.failureCategory,'SCHEDULER_CLEANUP_FAILED');assert.deepEqual(cleared,['timer']);")

    def test_late_promised_handle_is_cancelled_without_rescheduling(self):
        self.scheduler_scenario("let supply;deps.schedule=()=>new Promise(resolve=>{supply=resolve});const p=start();await registration(invoked,1,p);now=100;deadlineCallback();const r=await p;const before=JSON.stringify(r);const cancellation=cancelledSignal.wait(1);supply(99);try{await cancellation.promise}finally{cancellation.cancel()}assert.deepEqual(cancelled,[99]);assert.equal(JSON.stringify(r),before);assert.equal(cancelledSignal.pending(),0);")

    def test_deadline_scheduler_throw_prevents_readiness_and_dispatch(self):
        self.scheduler_scenario("deps.timer=()=>{throw Error('timer')};deps.ready=()=>{throw Error('must not run')};const r=await start();assert.equal(r.failure.stage,'deadline-scheduler');assert.equal(callbacks.length,0);")

    def test_second_run_has_independent_completion_and_handles(self):
        result=self.node(self.setup_js()+"""
(async()=>{const results=[];for(let i=0;i<2;i++){const cancelled=[];const deps={now:()=>i,schedule:()=>Promise.reject(Error('x')),cancel:h=>cancelled.push(h),timer:()=>i+1,clearTimer:h=>cancelled.push(h),ready:()=>Promise.resolve()};const r=await api.runSettlement({timeoutMs:10},deps);results.push(r);assert.equal(cancelled.length,1);assert.equal(cancelled[0],i+1);}assert.equal(results[0].failure.frameCount,0);assert.equal(results[1].failure.frameCount,0);console.log('SCENARIO_PASSED')})().catch(e=>{console.error(e);process.exitCode=1});
""")
        self.assertIn('SCENARIO_PASSED',result)


if __name__ == '__main__': unittest.main()
