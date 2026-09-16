"""Offline design receipts only; never native/provider or production evidence."""
from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import patch

from alpha_observation_lifecycle import observation_topology, STAGES, PROOFS
from alpha_session_integration import offline_observation_join
from alpha_session_contract import instant
from provider_gateway_contract import content_hash, locked_authority
from truth_spine_session_supervisor import ROLES, REQUIRED_PROBES
import test_alpha_short_observation as short_helpers


class ObservationTopologyTests(unittest.TestCase):
    def setUp(self):
        h=short_helpers.ShortPackageTests();h.setUp();self.f=h.f
        f=self.f;self.package=h.build()
        self.bindings=dict(schema='iios-alpha-observation-bindings-v1',source_commit='a'*40,
            session=f.plan['session'],plan_parent=content_hash(f.plan),package_parent=content_hash(self.package),
            release_parent='b'*64,runtime_parent=f.runtime['runtime_manifest_sha256'],generation='c'*64,
            owners={role:content_hash(role) for role in ROLES})
        self.inputs=dict(package=self.package,package_hash=content_hash(self.package),plan=f.plan,
            account=f.account,runtime=f.runtime,allowance=f.allowance,bindings=self.bindings,
            bindings_hash=content_hash(self.bindings),observation=h.obs,**f.kwargs())

    def build(self):return observation_topology(**self.inputs)

    def chain(self,topology):
        start=instant(topology['startup_deadline']);evidence={};pins={};previous=None
        offsets=(-30,-20,-10,1,61,121,150,200,250)
        for index,stage in enumerate(STAGES):
            count=0 if index<3 else min(index-2,3)
            value=dict(schema='iios-alpha-observation-design-stage-v1',scope='OFFLINE_INTEGRATION_ONLY',
                classification='DESIGN_TEST_ONLY',stage=stage,source_commit='a'*40,session=topology['session'],
                topology_parent=content_hash(topology),previous=previous,generation=topology['generation'],
                owners=deepcopy(topology['owners']),observed_at=(start+timedelta(seconds=offsets[index])).isoformat(),
                monotonic_ns=(index+1)*1000000000,dispatch_at=(start+timedelta(seconds=(index-3)*60)).isoformat() if 3<=index<=5 else None,
                result='PASS',proofs={k:content_hash([stage,k]) for k in PROOFS[stage]},
                counts=dict.fromkeys(('reservations','responses','completions'),count),authority=locked_authority())
            evidence[stage]=value;pins[stage]=content_hash(value);previous=pins[stage]
        return evidence,pins

    def join(self,t,e,p):return offline_observation_join(t,content_hash(t),e,p,**self.inputs)

    def test_exact_reused_roles_and_probes_never_execution(self):
        with patch('subprocess.run',side_effect=AssertionError('NO_PROCESS')),patch('builtins.open',side_effect=AssertionError('NO_IO')):
            t=self.build();e,p=self.chain(t);result=self.join(t,e,p)
        self.assertEqual(t['roles'],list(ROLES));self.assertEqual(t['required_probes'],sorted(REQUIRED_PROBES))
        self.assertEqual(t['ownership_samples_per_role'],3);self.assertEqual(t['restart_count'],0)
        self.assertEqual(result['status'],'OFFLINE_COMPLETE');self.assertFalse(result['native_semantics_verified'])
        self.assertFalse(result['execution_authorized']);self.assertFalse(result['production_qualified'])
        self.assertEqual(result['provider_requests'],0)

    def test_missing_evidence_is_blocked_and_gap_rejected(self):
        t=self.build();self.assertEqual(self.join(t,{}, {})['status'],'BLOCKED')
        e,p=self.chain(t);del e['ACK'];del p['ACK']
        with self.assertRaises(ValueError):self.join(t,e,p)

    def test_source_runtime_role_and_generation_bindings(self):
        original=deepcopy(self.bindings)
        for k,v in [('source_commit','d'*40),('runtime_parent','e'*64),('owners',{'worker':'f'*64}),
                    ('generation',''),('package_parent','e'*64)]:
            self.inputs['bindings']=original|{k:v};self.inputs['bindings_hash']=content_hash(self.inputs['bindings'])
            with self.subTest(k=k),self.assertRaises(ValueError):self.build()

    def test_rehashed_topology_cannot_grant_or_relax(self):
        original=self.build()
        for k,v in [('scope','LIVE_QUALIFICATION'),('execution_authorized',True),('restart_count',1),
                    ('ownership_samples_per_role',2),('maximum_requests',475),('channel','ISOLATED_SHADOW'),
                    ('required_probes',[]),('reverify_before_signal',False),('tls_before_dispatch',False)]:
            t=original|{k:v}
            with self.subTest(k=k),self.assertRaises(ValueError):self.join(t,{}, {})

    def test_receipt_replay_and_authority_rejected(self):
        t=self.build()
        for k,v in [('scope','CI_SYNTHETIC_FULL_SESSION_ONLY'),('classification','LIVE'),('session','2026-09-14'),
                    ('generation','e'*64),('topology_parent','e'*64),('previous','e'*64),
                    ('authority',dict.fromkeys(locked_authority(),0)),('owners',{})]:
            e,p=self.chain(t);e['OWNERSHIP'][k]=v;p['OWNERSHIP']=content_hash(e['OWNERSHIP'])
            with self.subTest(k=k),self.assertRaises(ValueError):self.join(t,e,p)

    def test_startup_ack_and_tls_deadlines(self):
        t=self.build();e,p=self.chain(t)
        e['ACK']['observed_at']=t['startup_deadline'];p['ACK']=content_hash(e['ACK'])
        with self.assertRaisesRegex(ValueError,'OBSERVATION_STARTUP_DEADLINE'):self.join(t,e,p)

    def test_dispatch_not_response_deadline_enforced(self):
        t=self.build();e,p=self.chain(t);at=instant(t['rows'][0]['dispatch_before'])
        e['PREFLIGHT']['dispatch_at']=at.isoformat();e['PREFLIGHT']['observed_at']=(at+timedelta(seconds=1)).isoformat()
        p['PREFLIGHT']=content_hash(e['PREFLIGHT'])
        with self.assertRaisesRegex(ValueError,'OBSERVATION_DISPATCH_WINDOW'):self.join(t,e,p)

    def test_monotonic_rollback_noninteger_or_overflow(self):
        t=self.build()
        for value in (-1,True,1.2,2**63,1000000000):
            e,p=self.chain(t);e['ACK']['monotonic_ns']=value;p['ACK']=content_hash(e['ACK'])
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'OBSERVATION_CLOCK'):self.join(t,e,p)

    def test_counts_and_request_receipt_reuse(self):
        t=self.build();e,p=self.chain(t)
        e['PREFLIGHT']['counts']['completions']=0;p['PREFLIGHT']=content_hash(e['PREFLIGHT'])
        with self.assertRaisesRegex(ValueError,'OBSERVATION_ACCOUNTING'):self.join(t,e,p)
        e,p=self.chain(t);e['OBSERVATION_1']['proofs']['response']=e['PREFLIGHT']['proofs']['response']
        p['OBSERVATION_1']=content_hash(e['OBSERVATION_1'])
        with self.assertRaisesRegex(ValueError,'OBSERVATION_REQUEST_REPLAY'):self.join(t,e,p)

    def test_cleanup_and_reconciliation_cannot_extend_window(self):
        t=self.build()
        for stage,deadline in [('RECONCILIATION','reconciliation_deadline'),('SHUTDOWN','finalization_deadline')]:
            e,p=self.chain(t);e[stage]['observed_at']=(instant(t[deadline])+timedelta(seconds=1)).isoformat()
            p[stage]=content_hash(e[stage])
            with self.subTest(stage=stage),self.assertRaises(ValueError):self.join(t,e,p)

    def test_no_observation_after_failed_preflight(self):
        t=self.build();e,p=self.chain(t);e['PREFLIGHT']['result']='FAILED';previous=None
        for stage in STAGES:
            e[stage]['previous']=previous;p[stage]=content_hash(e[stage]);previous=p[stage]
        with self.assertRaisesRegex(ValueError,'OBSERVATION_AFTER_FAILURE'):self.join(t,e,p)

    def test_missing_proof_and_primary_failure_not_green(self):
        t=self.build();e,p=self.chain(t);e['OWNERSHIP']['proofs'].pop('scheduler');p['OWNERSHIP']=content_hash(e['OWNERSHIP'])
        with self.assertRaisesRegex(ValueError,'OBSERVATION_PROOFS'):self.join(t,e,p)
        e,p=self.chain(t);e={'OWNERSHIP':e['OWNERSHIP']};e['OWNERSHIP']['result']='FAILED'
        self.assertEqual(self.join(t,e,{'OWNERSHIP':content_hash(e['OWNERSHIP'])})['status'],'BLOCKED')

    def test_existing_runner_rejects_topology_and_join(self):
        from alpha_session_runner import validate_package
        t=self.build();e,p=self.chain(t)
        for value in (t,self.join(t,e,p)):
            with self.assertRaises(ValueError):validate_package(value,content_hash(value))

    def test_failed_startup_still_records_independent_cleanup(self):
        t=self.build();e,p=self.chain(t)
        e={k:e[k] for k in ('OWNERSHIP','SHUTDOWN','PUBLICATION')};previous=None;p={}
        e['OWNERSHIP']['result']='FAILED';e['OWNERSHIP']['proofs']={}
        for stage,item in e.items():
            item['previous']=previous;item['counts']=dict.fromkeys(item['counts'],0)
            p[stage]=content_hash(item);previous=p[stage]
        result=self.join(t,e,p)
        self.assertEqual(result['status'],'BLOCKED');self.assertEqual(result['checks']['SHUTDOWN'],'PASS')
        self.assertEqual(result['checks']['OWNERSHIP'],'FAILED')

    def test_primary_and_cleanup_failure_remain_separate(self):
        t=self.build();e,p=self.chain(t)
        e={k:e[k] for k in ('OWNERSHIP','SHUTDOWN')};previous=None;p={}
        for stage,item in e.items():
            item.update(result='FAILED',proofs={},previous=previous,counts=dict.fromkeys(item['counts'],0))
            p[stage]=content_hash(item);previous=p[stage]
        result=self.join(t,e,p)
        self.assertEqual(result['checks']['OWNERSHIP'],'FAILED');self.assertEqual(result['checks']['SHUTDOWN'],'FAILED')
        self.assertEqual(result['status'],'BLOCKED')


if __name__=='__main__':unittest.main()
