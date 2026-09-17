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


class ExecutionAdmissionTests(unittest.TestCase):
    """Disposable documents exercise admission, never native truth or effects."""
    def setUp(self):
        from pathlib import Path
        from test_alpha_session_evidence import write, seal_directories
        from alpha_session_package import OBSERVATION_ENTRYPOINTS
        from alpha_observation_lifecycle import QUALIFICATION_KINDS, QUALIFICATION_CHECKS, EXECUTION_SCOPE
        from provider_gateway_contract import canonical
        self.helper = short_helpers.ShortReadOnlyEvidenceTests(); self.helper.setUp()
        self.addCleanup(self.helper.tearDown)
        b = self.helper.bundle; self.now = self.helper.now
        self.roots = {k:str(self.helper.e.base/k) for k in
                      ('runtime','claims','release','qualification','control','output')}
        release = Path(self.roots['release']); release.mkdir()
        names = {'alpha_observation_lifecycle.py','alpha_observation_execution.py','alpha_session_package.py',
            'alpha_short_observation.py','alpha_session_execution.py','provider_gateway_qualification.py',
            'truth_spine_process_identity.py','truth_spine_integration_runner.py','truth_spine_session_package.py',
            *OBSERVATION_ENTRYPOINTS.values()}
        rows = [write(release,n,b'# synthetic non-executable release fixture\n') for n in sorted(names)]
        seal_directories(release)
        rel = dict(schema='iios-truth-observation-release-v1',source_commit='a'*40,root=str(release),
            files=rows,entrypoints=dict(OBSERVATION_ENTRYPOINTS),module_graph={n:[] for n in sorted(names)})
        control=Path(self.roots['control']);control.mkdir()
        launch=dict(host='127.0.0.1',port=38493,peer_hash='b'*64,sandbox_hash='c'*64,
            control_files=[write(control,n,b'synthetic non-executable control fixture')
                for n in ('profile.sb','loopback.crt','loopback.pem')],
            host_identity=dict(system='Darwin',release='test',version='test',machine='arm64',uid=123),
            start_ns=1,startup_ns=60_000_000_001,stop_ns=240_000_000_001,final_ns=360_000_000_001)
        seal_directories(control)
        parents = dict(launch=content_hash(launch),package=b['candidate_hash'],release=content_hash(rel),runtime=b['runtime']['runtime_manifest_sha256'],
            claims=b['claims_manifest_hash'],roots=content_hash(self.roots),session=b['plan']['session'])
        self.pins={}; qs={}; qroot=Path(self.roots['qualification']);qroot.mkdir();qrows=[]
        for kind in ('host',*(k for k in QUALIFICATION_KINDS if k!='host')):
            q=dict(schema='iios-reviewed-observation-qualification-v1',scope=EXECUTION_SCOPE,kind=kind,
                source_commit='a'*40,parents=parents,host_parent=None if kind=='host' else self.pins['host'],
                valid_from=b['account']['valid_from'],expires_at=b['plan']['finalization_deadline'],
                checks={k:'INDEPENDENTLY_QUALIFIED' for k in QUALIFICATION_CHECKS[kind]},
                evidence_parents={k:content_hash(['synthetic',kind,k]) for k in QUALIFICATION_CHECKS[kind]},
                authority=locked_authority())
            qs[kind]=q;self.pins[kind]=content_hash(q);qrows.append(write(qroot,kind+'.json',canonical(q)))
        seal_directories(qroot)
        grant=dict(schema='iios-owner-observation-grant-v1',scope=EXECUTION_SCOPE,source_commit='a'*40,
            parents=parents,qualification_parents=dict(self.pins),valid_from=b['account']['valid_from'],
            expires_at=b['plan']['finalization_deadline'],maximum_requests=3,maximum_cost='3',cost_unit=b['allowance']['cost_unit'],
            retry_count=0,authority=locked_authority())
        self.document=dict(schema='iios-truth-observation-execution-v1',scope=EXECUTION_SCOPE,
            source_commit='a'*40,roots=self.roots,launch=launch,preflight=b,release=rel,release_parent=content_hash(rel),
            qualifications=qs,qualification_files=qrows,grant=grant,grant_parent=content_hash(grant),authority=locked_authority())
        self.expected=content_hash(self.document)

    def admit(self):
        from alpha_observation_lifecycle import admit_observation_execution
        return admit_observation_execution(self.document,self.expected,approved_roots=self.roots,
            approved_qualification_pins=self.pins,now=self.now)

    def test_complete_file_binding_is_immutable_and_not_native_execution(self):
        cap=self.admit()
        self.assertEqual(cap.identity,self.expected)
        with self.assertRaises(AttributeError):cap._expected='f'*64
        doc=cap.document();doc['authority']['live_execution']=True
        self.assertEqual(cap.document()['authority'],locked_authority())
        self.assertEqual(cap.recheck(self.now).identity,self.expected)

    def test_document_hash_and_every_independent_qualification_pin(self):
        original=self.expected;self.expected='f'*64
        with self.assertRaises(ValueError):self.admit()
        self.expected=original
        for key in self.pins:
            saved=self.pins[key];self.pins[key]='f'*64
            with self.subTest(key=key),self.assertRaises(ValueError):self.admit()
            self.pins[key]=saved

    def test_no_direct_capability_or_cross_scope_relabel(self):
        from alpha_observation_lifecycle import ObservationExecution
        with self.assertRaises(TypeError):ObservationExecution()
        for scope in ('OFFLINE_TEST','OBSERVATION_LAUNCH_COMPONENT_ONLY','CI_SYNTHETIC_FULL_SESSION_ONLY'):
            d=deepcopy(self.document);d['scope']=scope
            with self.subTest(scope=scope),self.assertRaises(ValueError):
                from alpha_observation_lifecycle import admit_observation_execution
                admit_observation_execution(d,content_hash(d),approved_roots=self.roots,
                    approved_qualification_pins=self.pins,now=self.now)

    def test_qualification_changed_bytes_cannot_be_replaced_by_inmemory_claim(self):
        from pathlib import Path
        p=Path(self.roots['qualification'])/'confinement.json';p.chmod(0o600);p.write_bytes(b'{}');p.chmod(0o400)
        with self.assertRaises(ValueError):self.admit()

    def test_rehashed_grant_budget_and_authority_mutations(self):
        for key,value in [('maximum_requests',4),('maximum_requests',True),('retry_count',1),
                          ('maximum_cost','4'),('expires_at','2099-01-01T00:00:00+00:00'),
                          ('authority',dict.fromkeys(locked_authority(),True))]:
            old=deepcopy(self.document)
            self.document['grant'][key]=value;self.document['grant_parent']=content_hash(self.document['grant'])
            self.expected=content_hash(self.document)
            with self.subTest(key=key),self.assertRaises(ValueError):self.admit()
            self.document=old;self.expected=content_hash(old)

    def test_live_clock_expiry_not_planning_clock(self):
        self.now=instant(self.document['preflight']['plan']['finalization_deadline'])
        with self.assertRaises(ValueError):self.admit()

    def test_unapproved_roots_rejected_before_filesystem(self):
        self.roots=dict(self.roots,output='/not-approved')
        with patch('os.open',side_effect=AssertionError('NO_FS')),self.assertRaises(ValueError):self.admit()

    def test_monotonic_phase_binding_rejects_one_tick_mutations(self):
        from alpha_observation_lifecycle import admit_observation_execution
        for key in ('startup_ns','stop_ns','final_ns'):
            d=deepcopy(self.document);d['launch'][key]-=1
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'OBSERVATION_(PHASE_DEADLINE_BINDING|LAUNCH_BUDGET)'):
                admit_observation_execution(d,content_hash(d),approved_roots=self.roots,
                    approved_qualification_pins=self.pins,now=self.now)

from test_alpha_runtime_files import TreeCase


class FrameworkLifecycleTests(TreeCase):
    def test_v2_runtime_does_not_replace_independent_native_qualification_parents(self):
        from pathlib import Path
        from test_alpha_production_runtime import framework_spec,runtime as assembler
        from alpha_session_package import bound_package
        from alpha_session_evidence import verify_candidate_evidence
        spec,args=framework_spec(self);m=assembler.assemble(spec,content_hash(spec),**args)['manifest']
        h=ExecutionAdmissionTests();h.setUp()
        try:
            b=h.document['preflight'];f=h.helper.e.fixture
            h.helper.e.runtime_root=Path(m['runtime_root']);h.roots['runtime']=m['runtime_root']
            b['runtime_manifest']=m;f.runtime.update(runtime_manifest_sha256=content_hash(m),interpreter_sha256=m['interpreter_sha256'])
            f.repin();b['package_inputs']=dict(f.kwargs(),observation=h.helper.obs);b['package_inputs'].pop('now')
            b['candidate']=bound_package(f.plan,f.account,f.runtime,f.allowance,observation=h.helper.obs,**f.kwargs())
            b['candidate_hash']=content_hash(b['candidate']);h.expected=content_hash(h.document)
            # Static v2 file verification passes; old native qualification/owner
            # parents cannot be relabelled for this different runtime and root.
            verified=[]
            def verify(*args,**kwargs):
                result=verify_candidate_evidence(*args,**kwargs);verified.append(result);return result
            with patch('alpha_session_evidence.verify_candidate_evidence',side_effect=verify) as evidence:
                with self.assertRaises(ValueError):h.admit()
                evidence.assert_called_once()
                self.assertEqual(verified[0]['status'],'FILES_AND_BINDINGS_VERIFIED_ONLY')
                self.assertEqual(evidence.call_args.kwargs['runtime_manifest']['schema'],'iios-immutable-python-runtime-v2')
            self.assertTrue(all(v is False for v in h.document['authority'].values()))
        finally:h.doCleanups()
