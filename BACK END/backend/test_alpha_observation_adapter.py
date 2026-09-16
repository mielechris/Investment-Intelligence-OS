"""Mocked process facts and effects; no process, listener or network is used."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta
import unittest

import test_alpha_observation_lifecycle as fixtures
from alpha_observation_adapter import ObservationAdapter, SCOPE
from alpha_session_contract import instant
from provider_gateway_contract import content_hash, locked_authority
from truth_spine_process_identity import ProcessObservation
from truth_spine_session_supervisor import ROLES


class AdapterTests(unittest.TestCase):
    def setUp(self):
        h=fixtures.ObservationTopologyTests(); h.setUp()
        self.topology=h.build(); self.adapter=ObservationAdapter(self.topology,content_hash(self.topology),**h.inputs)
        self.start=instant(self.topology['startup_deadline']); self.now=self.start-timedelta(seconds=40)
        self.samples={}; self.stops=[]

    def doc(self,stage,payload):
        t=self.topology
        d=dict(schema='iios-alpha-observation-adapter-evidence-v1',scope=SCOPE,stage=stage,
            topology_parent=content_hash(t),generation=t['generation'],source_commit=t['source_commit'],
            authority=locked_authority(),payload=payload)
        return d,content_hash(d)

    def launch(self,role):
        o=ProcessObservation(100+ROLES.index(role),99,'2026-09-14T13:00:00+00:00',
            '/runtime/python -B observer','/runtime/python','a'*64,'/runtime/backend',('/runtime/python','-B','observer'))
        self.samples[role]=o; row=asdict(o); row['argv']=list(row['argv'])
        launch,lh=self.doc('LAUNCH',dict(role=role,owner_parent=self.topology['owners'][role],observation=row))
        startup,sh=self.doc('STARTUP',dict(role=role,launch_parent=lh,observation=row))
        return o,launch,lh,startup,sh

    def startup(self):
        for role in ROLES:
            o,l,lh,s,sh=self.launch(role)
            self.adapter.register(role,(o,o,o),l,lh,s,sh,now=self.now)
            listener,h=self.doc('LISTENER',dict(role=role,startup_parent=sh,
                owner_parent=self.topology['owners'][role],pid=o.pid,listener_match=True))
            result=self.adapter.ack(role,listener,h,now=self.now)
            self.assertFalse(result['execution_authorized'])
        tls,h=self.doc('TLS',dict(peer_parent='b'*64,trust_parent='c'*64,verified=True))
        self.adapter.verify_tls(tls,h,peer_parent='b'*64,trust_parent='c'*64,now=self.now)

    def reserve(self,slot):
        row=self.topology['rows'][slot]
        d,h=self.doc('RESERVATION',dict(slot=slot,row_parent=content_hash(row),tls_parent=self.adapter.tls,
            previous=self.adapter.completions[-1] if slot else None))
        self.adapter.reserve(slot,d,h,now=self.start+timedelta(seconds=60*slot)); return h

    def requests(self):
        for slot in range(3):
            h=self.reserve(slot); now=self.start+timedelta(seconds=60*slot+1)
            self.adapter.before_send(slot,h,now=now)
            rh=content_hash(['response',slot])
            d,ch=self.doc('COMPLETION',dict(slot=slot,reservation_parent=h,response_parent=rh,coverage='COMPLETE',freshness='VERIFIED'))
            self.adapter.complete(slot,d,ch,response_parent=rh,now=now)

    def cleanup(self,inspect=None,stop=None,exit=None):
        def owned(role): self.stops.append(role); return 'COOPERATIVE'
        return self.adapter.cleanup(inspect or self.samples.get,stop or owned,exit or (lambda _:True))

    def finish(self,clear=(True,True,True)):
        d,h=self.doc('RECONCILIATION',dict(reservations=self.adapter.reservations,
            completions=self.adapter.completions,observed_at=(self.start+timedelta(seconds=150)).isoformat()))
        return self.adapter.finish(d,h,publication_parent='e'*64,listener_clear=clear,
            now=self.start+timedelta(seconds=250))

    def test_complete_path_remains_non_authorizing(self):
        self.startup();self.requests();self.cleanup(); result=self.finish()
        self.assertEqual(result['result'],'ADAPTER_COMPLETE');self.assertEqual(len(self.adapter.completions),3)
        self.assertEqual(result['provider_requests'],0);self.assertFalse(result['production_qualified'])
        self.assertTrue(all(v is False for v in result['authority'].values()))
        from alpha_session_runner import validate_package
        with self.assertRaises(ValueError):validate_package(result,content_hash(result))

    def test_receipt_health_never_grants_market_readiness(self):
        from alpha_observation_adapter import observation_health
        self.startup();self.requests();self.cleanup();r=self.finish()
        h=observation_health(r,content_hash(r),topology_parent=content_hash(self.topology))
        self.assertTrue(h['adapter_complete']);self.assertFalse(h['market_ready'])
        r['scope']='LIVE_QUALIFICATION'
        with self.assertRaises(ValueError):observation_health(r,content_hash(r),topology_parent=content_hash(self.topology))

    def test_three_independent_inspections_and_late_registration(self):
        o,l,lh,s,sh=self.launch(ROLES[0]); calls=[]
        self.adapter.collect_registration(ROLES[0],lambda role:(calls.append(role) or o),l,lh,s,sh,clock=lambda:self.now)
        self.assertEqual(calls,[ROLES[0]]*3)
        o,l,lh,s,sh=self.launch(ROLES[1]);times=iter((self.now,self.start))
        with self.assertRaisesRegex(ValueError,'DEADLINE'):self.adapter.collect_registration(ROLES[1],lambda _:o,l,lh,s,sh,clock=lambda:next(times))
        self.assertNotIn(ROLES[1],self.adapter.owners)

    def test_every_identity_field_and_pid_reuse(self):
        for field,value in [('pid',555),('parent_pid',88),('start_time','2026-09-14T13:00:01+00:00'),
            ('executable','other'),('executable_hash','f'*64),('argv',('python','other')),('cwd','elsewhere'),('command','other')]:
            self.setUp();o,l,lh,s,sh=self.launch(ROLES[0])
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.adapter.register(ROLES[0],(o,replace(o,**{field:value}),o),l,lh,s,sh,now=self.now)
            self.assertFalse(self.adapter.owners)

    def test_forged_startup_parent_and_relabel(self):
        for mutation in ('payload','scope','generation','authority'):
            self.setUp();o,l,lh,s,sh=self.launch(ROLES[0])
            if mutation=='payload':s['payload']['launch_parent']='f'*64
            elif mutation=='authority':s['authority']['live_execution']=True
            else:s[mutation]='OTHER'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                self.adapter.register(ROLES[0],(o,o,o),l,lh,s,content_hash(s),now=self.now)

    def test_duplicate_startup(self):
        o,l,lh,s,sh=self.launch(ROLES[0]);self.adapter.register(ROLES[0],(o,o,o),l,lh,s,sh,now=self.now)
        with self.assertRaises(ValueError):self.adapter.register(ROLES[0],(o,o,o),l,lh,s,sh,now=self.now)

    def test_ack_requires_owner_and_listener(self):
        o,l,lh,s,sh=self.launch(ROLES[0]);self.adapter.register(ROLES[0],(o,o,o),l,lh,s,sh,now=self.now)
        d,h=self.doc('LISTENER',dict(role=ROLES[0],startup_parent=sh,owner_parent=self.topology['owners'][ROLES[0]],pid=999,listener_match=True))
        with self.assertRaises(ValueError):self.adapter.ack(ROLES[0],d,h,now=self.now)
        self.assertFalse(self.adapter.acknowledged)

    def test_tls_before_registration_and_mismatch(self):
        d,h=self.doc('TLS',dict(peer_parent='f'*64,trust_parent='c'*64,verified=True))
        with self.assertRaises(ValueError):self.adapter.verify_tls(d,h,peer_parent='b'*64,trust_parent='c'*64,now=self.now)

    def test_no_request_before_tls_or_reservation(self):
        with self.assertRaises(ValueError):self.reserve(0)
        self.setUp();self.startup()
        with self.assertRaises(ValueError):self.adapter.before_send(0,'f'*64,now=self.start)

    def test_deadline_checked_again_before_send_preserves_reservation(self):
        self.startup();h=self.reserve(0)
        with self.assertRaises(ValueError):self.adapter.before_send(0,h,now=instant(self.topology['rows'][0]['dispatch_before']))
        self.assertEqual(self.adapter.reservations,[h]);self.assertFalse(self.adapter.completions)

    def test_duplicate_send_no_retry_and_ambiguous_stop(self):
        self.startup();h=self.reserve(0);self.adapter.before_send(0,h,now=self.start)
        with self.assertRaises(ValueError):self.adapter.before_send(0,h,now=self.start)
        self.assertEqual(len(self.adapter.reservations),1)
        self.adapter.stop('AMBIGUOUS_REQUEST');self.assertTrue(self.adapter.failed)

    def test_response_binding_and_missing_coverage(self):
        self.startup();h=self.reserve(0);self.adapter.before_send(0,h,now=self.start)
        d,ch=self.doc('COMPLETION',dict(slot=0,reservation_parent=h,response_parent='f'*64,coverage='MISSING',freshness='VERIFIED'))
        with self.assertRaises(ValueError):self.adapter.complete(0,d,ch,response_parent='f'*64,now=self.start)
        self.assertFalse(self.adapter.completions)

    def test_role_failure_continues_cleanup_without_signalling_unknown(self):
        self.startup();self.requests()
        def inspect(role):
            if role==ROLES[0]:raise OSError('not retained')
            return self.samples[role]
        results=self.cleanup(inspect=inspect)
        self.assertEqual(results[ROLES[0]],'UNVERIFIED');self.assertEqual(set(self.stops),set(ROLES[1:]))
        self.assertEqual(self.finish()['result'],'ADAPTER_BLOCKED')

    def test_pid_mismatch_no_stop(self):
        self.startup()
        self.cleanup(inspect=lambda role:replace(self.samples[role],pid=999))
        self.assertFalse(self.stops)

    def test_partial_startup_unregistered_cleanup_not_green(self):
        self.cleanup();self.assertEqual(set(self.adapter.cleanup_results.values()),{'UNREGISTERED'})

    def test_forced_exit_distinct_from_cooperative_and_clear_ports(self):
        self.startup();self.requests();self.cleanup(stop=lambda _:'VERIFIED_FORCED')
        self.assertEqual(self.finish()['result'],'ADAPTER_BLOCKED')
        with self.assertRaises(ValueError):self.finish((True,False,True))

    def test_cleanup_exception_and_exit_unverified_continue(self):
        self.startup();calls=[]
        def stop(role):
            calls.append(role)
            if role==ROLES[2]:raise OSError('not retained')
            return 'COOPERATIVE'
        self.cleanup(stop=stop,exit=lambda _:False)
        self.assertEqual(set(calls),set(ROLES));self.assertEqual(set(self.adapter.cleanup_results.values()),{'UNVERIFIED'})

    def test_final_receipt_tamper_and_extra_request(self):
        self.startup();self.requests();self.cleanup()
        with self.assertRaises(ValueError):self.adapter.reserve(3,{},'f'*64,now=self.start)
        self.assertEqual(len(self.adapter.reservations),3)
        d,h=self.doc('RECONCILIATION',dict(reservations=[],completions=[],observed_at=self.start.isoformat()))
        with self.assertRaises(ValueError):self.adapter.finish(d,h,publication_parent='e'*64,listener_clear=(True,True,True),now=self.start+timedelta(seconds=250))


if __name__=='__main__':unittest.main()
