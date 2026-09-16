"""Real connected gateway/journal path; only external effects are substituted."""
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import alpha_observation_execution as execution
from alpha_session_contract import instant
from provider_gateway_contract import content_hash, locked_authority
from provider_gateway_live_contract import request_parameters
from provider_gateway_transport import Response
from test_provider_gateway_live_contract import quote_fixture, repin
from test_provider_gateway_credentials import FakeCredentials, FAKE
import test_alpha_short_observation as short_tests


class Effects(execution.OfflineLifecycle):
    def __init__(self): self.calls=[]; self.fail=None
    def start(self):
        self.calls.append('start')
        if self.fail=='start':raise ValueError('not retained')
    def verify_ready(self):self.calls.append('ready');return self.fail!='ready'
    def cleanup(self):
        self.calls.append('cleanup')
        if self.fail=='cleanup':raise ValueError('not retained')
        return dict(verified=True,cooperative=True,roles=['scheduler','publisher','backend'],
                    listener_owner_reconciled=True,port_clear=[True]*3)


class ConnectedTests(unittest.TestCase):
    def setUp(self):
        h=short_tests.ShortPlanTests();h.setUp();p=h.build()
        self.root=Path(tempfile.mkdtemp(prefix='connected-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        inputs=dict(contract=h.h.contract,calendar=h.h.calendar,universe=h.h.universe,
            spine_session=h.h.spine,observation=h.observation,expected=h.expected,
            now=h.h.now.isoformat(),source_commit='a'*40)
        self.plan=execution.gateway_plan(p,content_hash(p),inputs,root=str(self.root))
        self.now=instant(p['startup_not_before']);self.origin=self.now
        self.effects=Effects();self.calls=0;self.delay=0;self.failure=False;self.payload_bad=False
        self.requests=[];self.pins=[];m,a,r=quote_fixture();self.runtime=r
        r['source_commit']='a'*40
        for row in self.plan['rows']:
            Path(row['root']).mkdir(mode=0o700);m=deepcopy(m);a=deepcopy(a)
            m.update(source_commit='a'*40,root=row['root'],batch_id=row['id'],
                role='GOVERNED_REALTIME_MARKET_BASELINE',endpoint='REALTIME_BULK_QUOTES',feed='real_time',
                symbols=row['symbols'],valid_from=row['valid_from'],expires_at=row['expires_at'],
                maximum_response_bytes=1_000_000,timeout_seconds=20,maximum_age_seconds=60)
            m['parameters']=request_parameters('ALPHA_VANTAGE',m['symbols'],'real_time',function='REALTIME_BULK_QUOTES')
            a.update(endpoint=m['endpoint'],feed=m['feed'],symbols=m['symbols'],qualification_parameters=m['parameters'],
                bulk_plan=self.plan,bulk_plan_parent=content_hash(self.plan),bulk_slot=row['slot'],
                valid_from=p['startup_not_before'],expires_at=p['finalization_deadline'],available_unreserved='3')
            a['retention'].update(mode='EPHEMERAL_ALPHA_BULK',raw_body=False,normalized=False,references=False,
                hashes=False,sanitized_receipt=True,retain_until=p['finalization_deadline'])
            a['short_allowance']=dict(plan_parent=content_hash(self.plan),source_commit='a'*40,
                account_identity=a['account_identity'],maximum_requests=3,maximum_cost='3',cost_unit=m['cost_unit'],
                expires_at=p['finalization_deadline'],enrichment_requests=0,released=False)
            self.pins.append(repin(m,a,r));self.requests.append(dict(manifest=m,account=a,runtime=r))
        outer=self
        class Network:
            def exchange(self,**kwargs):
                outer.now+=timedelta(seconds=outer.delay)
                kwargs['before_request']()
                outer.calls+=1
                if outer.failure:raise TimeoutError('sensitive text')
                data=[dict(symbol=s,timestamp=outer.now.isoformat(),open='17.123456',high='18',low='16',close='17.5',volume='12')
                    for s in outer.plan['rows'][outer.calls-1]['symbols']]
                if outer.payload_bad:data.pop()
                return Response(200,json.dumps({'data':data}).encode())
        self.network=Network()
    def run_path(self):
        return execution.run_observation(self.plan,content_hash(self.plan),self.requests,self.pins,lifecycle=self.effects,
            credential_backend=FakeCredentials(),network=self.network,clock=lambda:self.now.isoformat(),
            monotonic_ns=lambda:int((self.now-self.origin).total_seconds()*1e9),
            wait=lambda at:setattr(self,'now',instant(at)))
    def test_complete_actual_gateway_journals_and_cleanup(self):
        result=self.run_path();self.assertEqual(result['result'],'OFFLINE_COMPLETE',result)
        self.assertEqual(self.calls,3);self.assertEqual(len(list(self.root.glob('*.reserved.json'))),3)
        self.assertEqual(len(list(self.root.glob('*.complete.json'))),3)
        self.assertEqual(len(list(self.root.rglob('ALPHA_VANTAGE.receipt.json'))),3)
        self.assertEqual(len(list(self.root.rglob('ALPHA_VANTAGE.reserved.json'))),3)
        self.assertTrue(result['cleanup_verified']);self.assertFalse(result['production_qualified'])
        self.assertEqual(result['provider_requests'],0);self.assertEqual(result['authority'],locked_authority())
        for path in self.root.rglob('*.json'):
            b=path.read_bytes();self.assertNotIn(FAKE,b);self.assertNotIn(b'17.123456',b)
    def test_transport_delay_past_send_window_consumes_without_send(self):
        self.delay=5;result=self.run_path();self.assertEqual(self.calls,0)
        self.assertEqual(result['result'],'BLOCKED');self.assertTrue(result['cleanup_verified'])
        self.assertEqual(len(list(self.root.glob('*.reserved.json'))),1)
        self.assertEqual(len(list(self.root.rglob('ALPHA_VANTAGE.reserved.json'))),1)
    def test_provider_failure_stops_no_retry_and_preserves_receipt(self):
        self.failure=True;result=self.run_path();self.assertEqual(self.calls,1)
        self.assertEqual(result['primary_failure'],'GATEWAY');self.assertTrue(result['cleanup_verified'])
        self.assertEqual(len(list(self.root.rglob('ALPHA_VANTAGE.receipt.json'))),1)
    def test_partial_coverage_stops_following_requests(self):
        self.payload_bad=True;result=self.run_path();self.assertEqual(self.calls,1)
        self.assertEqual(result['result'],'BLOCKED')
    def test_startup_failure_always_attempts_cleanup(self):
        self.effects.fail='start';result=self.run_path();self.assertEqual(self.calls,0)
        self.assertEqual(self.effects.calls,['start','cleanup']);self.assertEqual(result['primary_failure'],'STARTUP')
    def test_ownership_failure_no_dispatch(self):
        self.effects.fail='ready';result=self.run_path();self.assertEqual(self.calls,0)
        self.assertEqual(result['result'],'BLOCKED')
    def test_cleanup_failure_cannot_be_overridden_by_responses(self):
        self.effects.fail='cleanup';result=self.run_path();self.assertEqual(self.calls,3)
        self.assertFalse(result['cleanup_verified']);self.assertEqual(result['result'],'BLOCKED')
    def test_altered_independent_request_pin_before_lifecycle(self):
        self.pins[1]['manifest']='0'*64
        with self.assertRaises(ValueError):self.run_path()
        self.assertEqual(self.effects.calls,[]);self.assertEqual(self.calls,0)
    def test_duplicate_invocation_never_redispatches(self):
        self.run_path();self.now=self.origin
        before=list(self.effects.calls)
        with self.assertRaises(FileExistsError):self.run_path()
        self.assertEqual(self.calls,3);self.assertEqual(self.effects.calls,before)
    def test_relabel_to_live_rejected_before_effect(self):
        self.plan['scope']='LIVE_QUALIFICATION'
        with self.assertRaises(ValueError):self.run_path()
        self.assertEqual(self.calls,0);self.assertEqual(self.effects.calls,[])
    def test_exact_rows_order_and_bounds_reconstruction(self):
        for key,value in [('maximum_requests',4),('retry_count',1),('scope','LIVE_QUALIFICATION'),('timeout_seconds',21)]:
            bad=deepcopy(self.plan);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):execution.verify_gateway_plan(bad,content_hash(bad))
        bad=deepcopy(self.plan);bad['rows'].reverse()
        with self.assertRaises(ValueError):execution.verify_gateway_plan(bad,content_hash(bad))
    def test_all_budget_mutations_rejected_before_effect(self):
        for key,value in [('maximum_requests',4),('released',True),('maximum_cost','2'),('enrichment_requests',1)]:
            original=deepcopy(self.requests[0]);self.requests[0]['account']['short_allowance'][key]=value
            b=self.requests[0];self.pins[0]=repin(b['manifest'],b['account'],b['runtime'])
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_path()
            self.requests[0]=original
        self.assertEqual(self.effects.calls,[])

    def test_missed_window_never_creates_a_reservation(self):
        def late(_):self.now=instant(self.plan['rows'][0]['dispatch_before'])
        with patch.object(execution,'qualify',wraps=execution.qualify) as dispatch:
            result=execution.run_observation(self.plan,content_hash(self.plan),self.requests,self.pins,
                lifecycle=self.effects,credential_backend=FakeCredentials(),network=self.network,
                clock=lambda:self.now.isoformat(),monotonic_ns=lambda:int((self.now-self.origin).total_seconds()*1e9),wait=late)
        self.assertEqual(result['result'],'BLOCKED');dispatch.assert_not_called()
        self.assertEqual(len(list(self.root.glob('*.reserved.json'))),0)
    def test_clock_rollback_stops_before_dispatch(self):
        clock_values=iter([100,99])
        result=execution.run_observation(self.plan,content_hash(self.plan),self.requests,self.pins,
            lifecycle=self.effects,credential_backend=FakeCredentials(),network=self.network,
            clock=lambda:self.now.isoformat(),monotonic_ns=lambda:next(clock_values,100),wait=lambda _:None)
        self.assertEqual(self.calls,0);self.assertEqual(result['result'],'BLOCKED')
    def test_extra_journal_record_during_cleanup_invalidates_final_result(self):
        cleanup=self.effects.cleanup
        def changed():
            (self.root/'extra.json').write_text('{}')
            return cleanup()
        self.effects.cleanup=changed
        result=self.run_path();self.assertEqual(self.calls,3)
        self.assertEqual(result['primary_failure'],'FINAL_RECONCILIATION');self.assertFalse(result['complete_accounting'])
    def test_tampered_receipt_during_cleanup_invalidates_final_result(self):
        cleanup=self.effects.cleanup
        def changed():
            p=self.root/self.plan['rows'][0]['id']/'ALPHA_VANTAGE.receipt.json'
            p.chmod(0o600);p.write_text('{}');p.chmod(0o400)
            return cleanup()
        self.effects.cleanup=changed
        result=self.run_path();self.assertEqual(result['primary_failure'],'FINAL_RECONCILIATION')
    def test_publication_failure_still_cleans_up(self):
        original=execution.publish
        def publish(fd,name,value):
            if name=='controller-final.json':raise OSError('do not retain')
            return original(fd,name,value)
        with patch.object(execution,'publish',side_effect=publish),self.assertRaises(OSError):self.run_path()
        self.assertEqual(self.effects.calls[-1],'cleanup')
    def test_each_authority_flag_rejected(self):
        for flag in locked_authority():
            b=deepcopy(self.requests[0]);self.requests[0]['manifest']['authority'][flag]=True
            x=self.requests[0];self.pins[0]=repin(x['manifest'],x['account'],x['runtime'])
            with self.assertRaises(ValueError):self.run_path()
            self.requests[0]=b
        self.assertEqual(self.calls,0)
    def test_final_transport_hook_reaches_native_wire_boundary(self):
        from provider_gateway_transport import NativeHTTPS
        guard=object()
        with patch('provider_gateway_transport.bounded_https',return_value='dummy') as wire:
            NativeHTTPS().exchange(host='www.alphavantage.co',address='192.0.2.1',method='GET',target='/query',
                headers={},body=None,tls_file='/disposable/tls',timeout=20,limit=1_000_000,before_request=guard)
        self.assertIs(wire.call_args.kwargs['before_request'],guard)
