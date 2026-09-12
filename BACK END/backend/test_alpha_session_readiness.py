from datetime import timedelta
import json
from pathlib import Path
import unittest

from alpha_session_readiness import readiness_plan, final_session_receipt, STAGES, FLAGS
from alpha_market_baseline import verify_plan
from provider_gateway_contract import content_hash, utc
from provider_gateway_qualification import qualify
import test_alpha_market_baseline as bulk_tests
CALENDAR = bulk_tests.CALENDAR
from test_provider_gateway_live_contract import repin
from test_provider_gateway_credentials import FakeCredentials
from test_provider_gateway_transport import FakeNetwork
from copy import deepcopy


class RadarPackageTests(unittest.TestCase):
    def setUp(self):
        from test_provider_gateway_live_contract import quote_fixture
        self.value = bulk_tests.radar_fixture_plan()
        self.helper = bulk_tests.BulkTests()
        self.helper.day = Path(self.value['root'])
        self.helper.plan = self.value
        self.template = quote_fixture()
        for row in self.value['rows']:
            Path(row['root']).mkdir(mode=0o700)

    def docs(self, slot=0):
        from provider_gateway_live_contract import request_parameters
        m, a = (deepcopy(d) for d in self.template[:2]);r = self.template[2]
        row = self.value['rows'][slot]
        m.update(role=bulk_tests.ROLE, endpoint=bulk_tests.FUNCTION, feed='real_time',
                 symbols=row['symbols'], root=row['root'], batch_id=row['id'],
                 valid_from=row['valid_from'], expires_at=row['expires_at'],
                 timeout_seconds=20, maximum_response_bytes=1000000)
        m['parameters'] = request_parameters('ALPHA_VANTAGE', m['symbols'], 'real_time',
                                             function=bulk_tests.FUNCTION)
        a.update(endpoint=bulk_tests.FUNCTION, feed='real_time', symbols=m['symbols'],
                 qualification_parameters=m['parameters'], bulk_plan=self.value,
                 bulk_plan_parent=content_hash(self.value), bulk_slot=slot,
                 expires_at=self.value['finalization_deadline'], available_unreserved='475')
        a['retention'].update(mode=bulk_tests.RETENTION, raw_body=False, normalized=False,
                              references=False, hashes=False, sanitized_receipt=True,
                              retain_until=self.value['finalization_deadline'])
        a['radar_allowance'] = {'plan_parent': a['bulk_plan_parent'],
            'source_commit': m['source_commit'], 'account_identity': a['account_identity'],
            'maximum_requests': 475, 'maximum_cost': '475', 'cost_unit': m['cost_unit'],
            'expires_at': self.value['finalization_deadline'], 'enrichment_requests': 0}
        return m, a, r

    def package(self):
        requests = []
        for slot in range(475):
            m,a,r = self.docs(slot)
            requests.append({'manifest':m, 'account':a, 'runtime':r, 'expected':repin(m,a,r)})
        return {'schema':'iios-opportunity-package-v1', 'scope':'OFFLINE_TEST',
                'plan':self.value, 'plan_parent':content_hash(self.value),
                'requests':requests, 'external_stages':{}, 'external_pins':{}}

    def invoke(self, slot=0, previous=None, offset=0, payload=None):
        m,a,r = self.docs(slot)
        stamp = (utc(m['valid_from'])+timedelta(seconds=offset)).isoformat()
        body = self.helper.payload(slot) if payload is None else payload
        for row in body['data']:row['timestamp'] = stamp
        net = FakeNetwork(payload=body)
        result = qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),
                         network=net,clock=lambda:stamp,expected_bulk_previous=previous)
        completed = self.helper.day/f'{slot}.complete.json'
        return result, content_hash(json.loads(completed.read_bytes())), net.calls

    def test_a_475_package_readiness_and_disabled_dispatch(self):
        from alpha_session_runner import validate_package, run
        p = self.package()
        self.assertEqual(len(validate_package(p,content_hash(p))['rows']),475)
        # Run the default path with boundaries that fail if called; no activation.
        def forbidden(*args):raise AssertionError('DISABLED_DISPATCH')
        result=run(p,content_hash(p),clock=forbidden,wait=forbidden,executor=forbidden)
        self.assertEqual(result['requests'],0)
        self.assertEqual(result['status'],'DISABLED_VALIDATION_ONLY')
        for flag in FLAGS:self.assertIs(result[flag],False)

    def test_budget_missing_wrong_parent_expired_or_extra_enrichment_zero_calls(self):
        mutations = [lambda a:a.pop('radar_allowance'),
            lambda a:a['radar_allowance'].update(plan_parent='0'*64),
            lambda a:a['radar_allowance'].update(maximum_requests=476),
            lambda a:a['radar_allowance'].update(enrichment_requests=1),
            lambda a:a['radar_allowance'].update(maximum_cost='474'),
            lambda a:a.update(available_unreserved='474'),
            lambda a:a['radar_allowance'].update(expires_at='2026-09-14T20:05:00+00:00'),
            lambda a:a.update(expires_at='2026-09-14T20:05:00+00:00')]
        for mutate in mutations:
            m,a,r=self.docs();mutate(a);net=FakeNetwork()
            with self.assertRaises(ValueError):
                qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),
                        network=net,clock=lambda:m['valid_from'])
            self.assertEqual(net.calls,0)
        self.assertFalse(list(self.helper.day.glob('*.json')))

    def test_preflight_then_three_start_gate(self):
        receipt,parent,calls=self.invoke()
        self.assertEqual(receipt['result'],'OBSERVED');self.assertEqual(calls,1)
        for slot,offset in ((1,0),(2,1),(3,2)):
            receipt,parent,calls=self.invoke(slot,parent,offset)
            self.assertEqual(receipt['result'],'OBSERVED')
        with self.assertRaisesRegex(ValueError,'ROLLING_RATE_GATE'):self.invoke(4,parent,3)
        receipt,parent,_=self.invoke(4,parent,60)
        self.assertEqual(receipt['result'],'OBSERVED')

    def test_reordered_response_stops_and_retains_consumed_reservation(self):
        body=self.helper.payload(0);body['data'].reverse()
        receipt,parent,calls=self.invoke(payload=body)
        self.assertEqual(receipt['result'],'AMBIGUOUS_OR_UNVERIFIED_STOP')
        self.assertEqual(calls,1)
        self.assertTrue((self.helper.day/'0.reserved.json').is_file())
        with self.assertRaises(ValueError):self.invoke(1,parent)
        with self.assertRaises(ValueError):self.invoke()

    def test_response_deadline_fail_closed(self):
        m,a,r=self.docs();state=[False]
        class Slow(FakeNetwork):
            def exchange(self,**kw):
                result=super().exchange(**kw);state[0]=True;return result
        clock=lambda:(utc(m['valid_from'])+timedelta(seconds=21 if state[0] else 0)).isoformat()
        net=Slow(payload=self.helper.payload(0))
        result=qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),
                       network=net,clock=clock)
        self.assertEqual(result['result'],'AMBIGUOUS_OR_UNVERIFIED_STOP')
        self.assertEqual(net.calls,1)

    def test_missing_credential_has_zero_dispatch_and_consumes_reservation(self):
        m,a,r=self.docs();net=FakeNetwork()
        class Missing:
            def read(self,service,account):raise ValueError('SYNTHETIC_SELECTOR_MISSING')
        result=qualify(m,a,r,expected=repin(m,a,r),credential_backend=Missing(),
                       network=net,clock=lambda:m['valid_from'])
        self.assertEqual(result['result'],'AMBIGUOUS_OR_UNVERIFIED_STOP')
        self.assertEqual(net.calls,0)
        self.assertTrue((self.helper.day/'0.reserved.json').is_file())

    def test_package_version_and_exact_request_count_are_separate_gates(self):
        from alpha_session_runner import validate_package
        for version, count in [('unknown',475), ('iios-alpha-monday-package-v1',475),
                               ('iios-opportunity-package-v1',474), ('iios-opportunity-package-v1',476)]:
            p={'schema':version,'scope':'OFFLINE_TEST','plan':self.value,
               'plan_parent':content_hash(self.value),'requests':[{} for _ in range(count)],
               'external_stages':{},'external_pins':{}}
            with self.subTest(version=version,count=count), self.assertRaises(ValueError):
                validate_package(p,content_hash(p))

    def test_unfinished_receipt_is_not_native_or_full_session_green(self):
        from alpha_session_runner import run
        p=self.package();calls=[];now=p['plan']['rows'][0]['valid_from']
        def execute(request,previous):
            calls.append(1)
            m,a,r=(request[k] for k in ('manifest','account','runtime'))
            return qualify(m,a,r,expected=request['expected'],credential_backend=FakeCredentials(),
                           network=FakeNetwork(payload={'data':[]}),clock=lambda:now,
                           expected_bulk_previous=previous)
        result=run(p,content_hash(p),enabled=True,clock=lambda:now,wait=lambda _:None,executor=execute)
        self.assertEqual(calls,[1]);self.assertEqual(result['status'],'RED')
        self.assertEqual(result['additional_provider_requests'],0)
        self.assertEqual(result['native_readiness'],'NOT_QUALIFIED')
        self.assertFalse(result['armed'])


class ReadinessTests(unittest.TestCase):
    def prepare(self):
        self.helper = bulk_tests.BulkTests()
        self.helper.setup_plan()
        u = self.helper.universe
        self.value = readiness_plan(u, content_hash(u), CALENDAR, content_hash(CALENDAR), root=str(self.helper.day))
        self.helper.plan = self.value
        Path(self.value['rows'][0]['root']).mkdir(mode=0o700)
        verify_plan(self.value, content_hash(self.value))

    def invoke(self, slot, previous=None, offset=0, stale=False):
        m,a,r=self.helper.docs(slot)
        stamp=(utc(m['valid_from'])+timedelta(seconds=offset)).isoformat()
        payload=self.helper.payload(slot)
        for row in payload['data']: row['timestamp']='2026-09-11T13:30:00Z' if stale else stamp
        net=FakeNetwork(payload=payload)
        receipt=qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),network=net,clock=lambda:stamp,expected_bulk_previous=previous)
        complete=json.loads((self.helper.day/f'{slot}.complete.json').read_text())
        return receipt, content_hash(complete), net.calls

    def test_preflight_and_exact_intervals(self):
        self.prepare();rows=self.value['rows']
        self.assertEqual(len(rows),19);self.assertEqual(len(rows[0]['symbols']),10)
        self.assertEqual(rows[0]['valid_from'],'2026-09-14T13:20:00+00:00')
        self.assertEqual(rows[0]['expires_at'],'2026-09-14T13:25:00+00:00')
        self.assertEqual(rows[1]['expires_at'],'2026-09-14T13:32:10+00:00')
        self.assertEqual(rows[7]['expires_at'],'2026-09-14T16:32:00+00:00')
        self.assertEqual(rows[13]['expires_at'],'2026-09-14T20:02:10+00:00')

    def test_all_nineteen_pass_only_with_fresh_complete_evidence(self):
        self.prepare();previous=None;calls=0
        for slot in range(19):
            offset=0 if slot==0 else (0,1,2,61,62,63)[(slot-1)%6]
            receipt,previous,count=self.invoke(slot,previous,offset)
            self.assertEqual(receipt['result'],'OBSERVED')
            self.assertIn('dispatch_time',receipt);self.assertIn('response_time',receipt)
            calls+=count
        self.assertEqual(calls,19)

    def test_no_preflight_cannot_start_opening(self):
        self.prepare()
        with self.assertRaises(ValueError):self.invoke(1)

    def test_stale_preflight_blocks_opening(self):
        self.prepare();receipt,parent,_=self.invoke(0,stale=True)
        self.assertEqual(receipt['result'],'AMBIGUOUS_OR_UNVERIFIED_STOP')
        with self.assertRaises(ValueError):self.invoke(1,parent)

    def test_fourth_start_within_minute_rejected(self):
        self.prepare();_,parent,_=self.invoke(0)
        for slot in (1,2,3):_,parent,_=self.invoke(slot,parent,slot)
        with self.assertRaises(ValueError):self.invoke(4,parent,4)

    def test_response_overrun_never_observed(self):
        self.prepare();m,a,r=self.helper.docs(0)
        class Slow(FakeNetwork):
            late=False
            def exchange(self,**kw):
                result=super().exchange(**kw);self.late=True;return result
        net=Slow(payload=self.helper.payload(0))
        clock=lambda:'2026-09-14T13:25:01Z' if net.late else m['valid_from']
        receipt=qualify(m,a,r,expected=repin(m,a,r),credential_backend=FakeCredentials(),network=net,clock=clock)
        self.assertEqual(receipt['result'],'AMBIGUOUS_OR_UNVERIFIED_STOP')

    def test_final_join_missing_stages_is_yellow_and_flags_false(self):
        value=final_session_receipt({}, {})
        self.assertEqual(value['status'],'YELLOW')
        for key in FLAGS:self.assertIs(value[key],False)

    def test_synthetic_complete_chain_never_live_green(self):
        evidence={};expected={};previous=None
        for stage in STAGES:
            receipt={'stage':stage,'session':'2026-09-14','scope':'OFFLINE_TEST','previous':previous,'result':'PASS','authority':dict.fromkeys(FLAGS,False)}
            evidence[stage]=receipt;expected[stage]=content_hash(receipt);previous=expected[stage]
        self.assertEqual(final_session_receipt(evidence,expected)['status'],'YELLOW')
        with self.assertRaises(ValueError):final_session_receipt(evidence,expected,scope='LIVE_EVIDENCE')
        evidence['risk']['previous']='0'*64;expected['risk']=content_hash(evidence['risk'])
        with self.assertRaises(ValueError):final_session_receipt(evidence,expected)

    def test_native_wire_times_with_fully_mocked_boundaries(self):
        from unittest.mock import MagicMock, patch
        import ssl
        from datetime import datetime
        from provider_gateway_transport import NativeHTTPS
        ctx,sock,conn,response=MagicMock(),MagicMock(),MagicMock(),MagicMock()
        ctx.verify_mode,ctx.check_hostname=ssl.CERT_REQUIRED,True
        ctx.wrap_socket.return_value=sock;conn.getresponse.return_value=response
        response.status=200
        response.getheader.side_effect=lambda key,default: {'Content-Type':'application/json'}.get(key,default)
        response.read1.side_effect=[b'{}',b'']
        start=datetime.fromisoformat('2026-09-14T13:20:00+00:00');end=start+timedelta(seconds=1)
        with patch('provider_gateway_transport.ssl.create_default_context',return_value=ctx),patch('provider_gateway_transport.socket.socket',return_value=sock),patch('provider_gateway_transport.http.client.HTTPSConnection',return_value=conn),patch('provider_gateway_https.datetime') as dt:
            dt.now.side_effect=[start,end]
            result=NativeHTTPS().exchange(host='www.alphavantage.co',address='192.0.2.1',method='GET',target='/query',headers={},body=None,tls_file='synthetic.pem',timeout=20,limit=1000000)
        self.assertEqual(result.request_start,start.isoformat());self.assertEqual(result.response_end,end.isoformat())
        conn.request.assert_called_once();sock.close.assert_called_once();conn.close.assert_called_once()

    def package(self):
        self.prepare();requests=[]
        for slot in range(19):
            m,a,r=self.helper.docs(slot);a['available_unreserved']='19'
            requests.append({'manifest':m,'account':a,'runtime':r,'expected':repin(m,a,r)})
        return {'schema':'iios-alpha-monday-package-v1','scope':'OFFLINE_TEST','plan':self.value,
                'plan_parent':content_hash(self.value),'requests':requests,'external_stages':{},'external_pins':{}}

    def test_disabled_package_no_boundaries_invoked(self):
        from alpha_session_runner import run
        p=self.package()
        def forbidden(*args):raise AssertionError('DISABLED_BOUNDARY_CALLED')
        result=run(p,content_hash(p),clock=forbidden,wait=forbidden,executor=forbidden)
        self.assertEqual(result['requests'],0);self.assertEqual(result['status'],'DISABLED_VALIDATION_ONLY')

    def test_runner_respects_rate_and_returns_missing_external_stages(self):
        from alpha_session_runner import run
        p=self.package();now=[utc(self.value['rows'][0]['valid_from'])]
        def clock():return now[0].isoformat()
        def wait(seconds):now[0]+=timedelta(seconds=seconds)
        def execute(request,previous):
            m,a,r=(request[k] for k in ('manifest','account','runtime'))
            payload=self.helper.payload(a['bulk_slot'])
            for row in payload['data']:row['timestamp']=clock()
            return qualify(m,a,r,expected=request['expected'],credential_backend=FakeCredentials(),network=FakeNetwork(payload=payload),clock=clock,expected_bulk_previous=previous)
        result=run(p,content_hash(p),enabled=True,clock=clock,wait=wait,executor=execute)
        self.assertEqual(len(result['request_receipt_parents']),19)
        self.assertEqual(result['status'],'YELLOW')
        self.assertEqual(result['checks']['yahoo_discovery'],'MISSING')
        self.assertEqual(result['checks']['closing'],'PASS')

    def test_runner_shutdown_and_expiry_make_zero_dispatches(self):
        from alpha_session_runner import run
        for shutdown in (True,False):
            p=self.package();calls=[]
            result=run(p,content_hash(p),enabled=True,clock=lambda:'2026-09-14T13:26:00Z',wait=lambda x:None,executor=lambda *a:calls.append(1),stop=lambda:shutdown)
            self.assertEqual(calls,[]);self.assertEqual(result['status'],'RED')

    def test_package_aggregate_budget_fails_closed(self):
        from alpha_session_runner import validate_package
        p=self.package()
        for request in p['requests']:
            request['account']['available_unreserved']='1'
            request['expected']=repin(request['manifest'],request['account'],request['runtime'])
        with self.assertRaises(ValueError):validate_package(p,content_hash(p))

    def test_disabled_descriptor_rehearsal_and_duplicate_rejection(self):
        from alpha_session_runner import disabled_installation_rehearsal
        import hashlib
        p=self.package();root=self.helper.day
        package=root/'package.json';package.write_text(json.dumps(p))
        interpreter=root/'synthetic-python';interpreter.write_bytes(b'synthetic executable not run')
        entry=root/'synthetic-runner.py';entry.write_bytes(b'# synthetic source not run')
        spec={'root':str(root/'disabled-review'),'package_hash':content_hash(p)}
        for key,path in [('package',package),('interpreter',interpreter),('entrypoint',entry)]:
            spec[key]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        result=disabled_installation_rehearsal(spec,content_hash(spec))
        self.assertFalse(result['registered']);self.assertFalse(result['armed'])
        with self.assertRaises(ValueError):disabled_installation_rehearsal(spec,content_hash(spec))


class SharedSchedulerBoundaryTests(unittest.TestCase):
    def test_runner_uses_shared_scheduler_and_retains_both_guards(self):
        import inspect
        import alpha_session_runner as runner
        from alpha_session_execution import execute_schedule
        self.assertIs(runner.execute_schedule, execute_schedule)
        self.assertIn("'CLI_LIVE_ONLY'", inspect.getsource(runner.main))
        self.assertIn("'RADAR_NATIVE_ADAPTER_PENDING'", inspect.getsource(runner.run))
