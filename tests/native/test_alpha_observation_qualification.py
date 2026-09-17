"""Offline/adversarial disposable adapter tests; no process/network effects."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from provider_gateway_contract import content_hash,locked_authority
from truth_spine_observation_roles import admit_roles,seed,seed_projection,configuration,invocation_pins,record,DisposableRoles,SCOPE


def fixture():
    base=Path(os.environ['IIOS_GATEWAY_TEST_ROOT'])/'execution-01'
    roots={k:str(base/v) for k,v in dict(runtime='output/runtime-pilot',release='release',control='control',output='disposable').items()}
    def row(name):return dict(path=name,size=1,mode=0o400,sha256='a'*64)
    runtime=dict(root=roots['runtime'],interpreter='bin/python3.14',files=[dict(row('bin/python3.14'),mode=0o500)])
    files={'release':[row(n) for n in ('alpha_observation_qualification.py','truth_spine_full_day_runner.py','truth_spine_full_day_service.py')],
        'control':[row(n) for n in ('profile.sb','loopback.crt','loopback.pem')]}
    records=[];previous=None
    for i in range(3):
        value=seed(i,previous);records.append(value);previous=content_hash(value)
    now=datetime(2026,9,17,12,tzinfo=timezone.utc)
    d=dict(schema='iios-disposable-observation-roles-v1',scope=SCOPE,source_commit='a'*40,roots=roots,
        release_parent=content_hash(files['release']),control_parent=content_hash(files['control']),input_files=files,
        runtime_parent=content_hash(runtime),runtime=runtime,seed_parents=[content_hash(x) for x in records],
        valid_from=now.isoformat(),expires_at=(now+timedelta(seconds=900)).isoformat(),authority=locked_authority(),
        launch=dict(host='127.0.0.1',port=38493,peer_hash='b'*64,sandbox_hash='c'*64,
            host_identity=dict(system='Darwin',release='25.5.0',version='TEST_ONLY',machine='arm64',uid=501),
            start_ns=1_000_000_000,startup_ns=61_000_000_000,stop_ns=661_000_000_000,final_ns=781_000_000_000))
    return d,roots,now,records


class DisposableAdmissionTests(unittest.TestCase):
    def setUp(self):self.d,self.roots,self.now,self.seeds=fixture()
    def admit(self,d=None):
        d=self.d if d is None else d
        return admit_roles(d,content_hash(d),approved_roots=self.roots,now=self.now)
    def test_exact_descriptor_is_separate_immutable_capability(self):
        c=self.admit();self.assertIs(type(c),DisposableRoles)
        with self.assertRaises(TypeError):DisposableRoles()
        with self.assertRaises(AttributeError):c._parent='0'*64
        self.assertFalse(record(c,{})['production_qualified'])
    def test_reject_every_scope_and_route_mutation(self):
        for key,value in [('scope','LIVE_QUALIFICATION'),('credential_selector','anything'),('provider_url','anything')]:
            d=deepcopy(self.d);d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.admit(d)
        for host in ('localhost','::1','8.8.8.8','127.0.0.2'):
            d=deepcopy(self.d);d['launch']['host']=host
            with self.subTest(host=host),self.assertRaises(ValueError):self.admit(d)
    def test_parent_and_input_identity_mutations_rejected(self):
        for key in ('runtime_parent','release_parent','control_parent'):
            d=deepcopy(self.d);d[key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):self.admit(d)
    def test_runtime_canonical_order_duplicates_and_escape_rejected(self):
        for name in ('../escape','/outside','bin//python3.14'):
            d=deepcopy(self.d);d['runtime']['files'][0]['path']=name;d['runtime_parent']=content_hash(d['runtime'])
            with self.subTest(path=name),self.assertRaises(ValueError):self.admit(d)
    def test_protected_or_unapproved_roots_rejected_before_io(self):
        d=deepcopy(self.d);d['roots']['runtime']+='/../Keychains'
        with patch('pathlib.Path.open',side_effect=AssertionError('io')),self.assertRaises(ValueError):self.admit(d)
    def test_clock_deadline_and_authority_mutations_rejected(self):
        for key,value in [('startup_ns',self.d['launch']['start_ns']),('final_ns',2**63),('stop_ns',True)]:
            d=deepcopy(self.d);d['launch'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.admit(d)
        d=deepcopy(self.d);d['authority']['live_execution']=True
        with self.assertRaises(ValueError):self.admit(d)
    def test_expired_descriptor_rejected(self):
        with self.assertRaises(ValueError):admit_roles(self.d,content_hash(self.d),approved_roots=self.roots,now=self.now+timedelta(seconds=900))
    def test_exact_invocation_binds_full_config_and_roots(self):
        c=self.admit();args=invocation_pins(c)
        self.assertEqual(args[1],content_hash(configuration(c)))
        self.assertNotIn('LIVE_QUALIFICATION',str(configuration(c)))
    def test_runtime_matches_final_assembler_destination_not_sibling_or_staging(self):
        c=self.admit();self.assertTrue(c.document()['roots']['runtime'].endswith('/execution-01/output/runtime-pilot'))
        for suffix in ('runtime','staging','bootstrap','output/runtime-other'):
            d=deepcopy(self.d);roots=deepcopy(self.roots)
            roots['runtime']=str(Path(roots['release']).parent/suffix)
            d['roots']=roots;d['runtime']['root']=roots['runtime'];d['runtime_parent']=content_hash(d['runtime'])
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):
                admit_roles(d,content_hash(d),approved_roots=roots,now=self.now)

    def test_scope_label_and_zero_request_fields_are_permanent(self):
        c=self.admit();v=record(c,{'scope':'LIVE_QUALIFICATION','requests_attempted':3,'production_qualified':True})
        self.assertEqual(v['scope'],SCOPE);self.assertEqual(v['requests_attempted'],0);self.assertFalse(v['production_qualified'])
    def test_seeds_are_not_executed_responses(self):
        c=self.admit()
        with patch.object(DisposableRoles,'recheck',return_value=c):
            p=seed_projection(c,{'session':'DISPOSABLE','seed_parents':self.d['seed_parents']},records=self.seeds,now=self.now)
        self.assertEqual((p['reserved'],p['completed'],p['seeded_records']),(0,0,3))
        self.assertEqual(p['scope'],SCOPE)
    def test_seed_missing_reordered_changed_or_replayed_rejected(self):
        c=self.admit()
        for rows in (self.seeds[:2],list(reversed(self.seeds)),self.seeds+[self.seeds[-1]],
                     [dict(self.seeds[0],slot=1),*self.seeds[1:]]):
            with patch.object(DisposableRoles,'recheck',return_value=c),self.assertRaises(ValueError):
                seed_projection(c,{'session':'DISPOSABLE','seed_parents':self.d['seed_parents']},records=rows,now=self.now)
    def test_live_lifecycle_constructor_rejects_test_capability(self):
        from truth_spine_full_day_runner import ObservationLifecycle
        with self.assertRaises(ValueError):ObservationLifecycle({},self.admit())
    def test_live_gateway_entrypoint_rejects_test_capability(self):
        from alpha_observation_execution import run_admitted_observation
        c=self.admit()
        with self.assertRaises(ValueError):run_admitted_observation(c,c.identity,{},'0'*64,[],[],lifecycle=None)
    def test_live_projection_rejects_disposable_evidence(self):
        from truth_spine_session_package import observation_projection
        with self.assertRaises(ValueError):observation_projection(self.admit(),{},[],[],now=self.now)
    def test_live_admission_does_not_accept_disposable_descriptor(self):
        from alpha_observation_lifecycle import admit_observation_execution
        with self.assertRaises(ValueError):admit_observation_execution(self.d,content_hash(self.d),approved_roots=self.roots,approved_qualification_pins={},now=self.now)
    def test_owner_requires_distinct_test_entrypoint(self):
        from truth_spine_integration_runner import OwnedChildren,RunnerFailure
        c=self.admit()
        with self.assertRaisesRegex(RunnerFailure,'OBSERVATION_OWNER_BINDING'):OwnedChildren(Path(self.roots['output']),observation=c,service_module='truth_spine_full_day_service')

class DisposableFunctionalTests(unittest.TestCase):
    setUp=DisposableAdmissionTests.setUp
    admit=DisposableAdmissionTests.admit
    def test_release_escape_and_duplicate_rejected_before_file_verification(self):
        for value in ('../escape','bad\x00path','same'):
            d=deepcopy(self.d);rows=d['input_files']['release'];rows.append(dict(rows[0],path=value))
            if value=='same':rows.append(dict(rows[-1]))
            d['release_parent']=content_hash(rows)
            with patch('alpha_session_evidence.verify_files',side_effect=AssertionError('io')),self.assertRaises(ValueError):self.admit(d)

    def test_partial_start_always_cleans_and_keeps_primary(self):
        import alpha_observation_qualification as q
        from unittest.mock import MagicMock
        c=self.admit();owner=MagicMock();owner.start.side_effect=ValueError('DO_NOT_RETAIN')
        owner.cleanup.return_value=record(c,{'verified':False,'cooperative':False})
        with patch.object(q,'directory',return_value=10),patch.object(q.os,'mkdir'),patch.object(q.os,'open',return_value=11),patch.object(q.os,'close'),patch.object(q,'publish') as pub,patch('truth_spine_full_day_runner.ObservationLifecycle.for_disposable',return_value=owner):
            r=q.run_parent(configuration(c),c)
        owner.cleanup.assert_called_once();self.assertEqual(r['primary_failure'],{'stage':'STARTUP','category':'ValueError'})
        self.assertEqual(r['status'],'FAILED_CLOSED');self.assertNotIn('DO_NOT_RETAIN',str(pub.call_args_list))

    def test_seed_publication_failure_never_claims_three_records(self):
        import alpha_observation_qualification as q
        c=self.admit();seen=[]
        def publish(fd,name,value):
            if name=='1.seed.json':raise OSError('secret')
            seen.append(name)
        with patch.object(q,'directory',return_value=10),patch.object(q.os,'mkdir'),patch.object(q.os,'open',return_value=11),patch.object(q.os,'close'),patch.object(q,'publish',side_effect=publish),patch('truth_spine_full_day_runner.ObservationLifecycle.for_disposable') as start:
            r=q.run_parent(configuration(c),c)
        start.assert_not_called();self.assertEqual(r['seed_records'],1);self.assertEqual(r['status'],'FAILED_CLOSED')

    def test_http_failure_and_cleanup_failure_stay_separate(self):
        import alpha_observation_qualification as q
        from unittest.mock import MagicMock
        c=self.admit();owner=MagicMock();owner.cleanup.side_effect=TimeoutError('secret')
        with patch.object(q,'directory',return_value=10),patch.object(q.os,'mkdir'),patch.object(q.os,'open',return_value=11),patch.object(q.os,'close'),patch.object(q,'publish'),patch.object(q,'read_only_roundtrip',side_effect=ValueError('secret')),patch('truth_spine_full_day_runner.ObservationLifecycle.for_disposable',return_value=owner):
            r=q.run_parent(configuration(c),c)
        self.assertEqual(r['primary_failure']['stage'],'READ_ONLY_HTTP');self.assertEqual(r['cleanup']['category'],'TimeoutError')
        self.assertFalse(r['cleanup']['verified']);self.assertEqual(r['requests_attempted'],0)

    def test_functional_success_keeps_confinement_and_live_unqualified(self):
        import alpha_observation_qualification as q
        from unittest.mock import MagicMock
        c=self.admit();owner=MagicMock();owner.cleanup.return_value={'verified':True,'cooperative':True}
        with patch.object(q,'directory',return_value=10),patch.object(q.os,'mkdir'),patch.object(q.os,'open',return_value=11),patch.object(q.os,'close'),patch.object(q,'publish'),patch.object(q,'read_only_roundtrip',return_value={'status':200}) as http,patch('truth_spine_full_day_runner.ObservationLifecycle.for_disposable',return_value=owner):
            r=q.run_parent(configuration(c),c)
        self.assertEqual([x.args[1] for x in http.call_args_list],['GET','HEAD']);self.assertEqual(r['status'],'FUNCTIONAL_PASS')
        self.assertEqual(r['seed_records'],3);self.assertFalse(r['production_qualified']);self.assertIn('UNQUALIFIED',r['confinement'])

    def test_unknown_exception_class_not_persisted(self):
        import alpha_observation_qualification as q
        Evil=type('SENSITIVE_NAME',(Exception,),{})
        self.assertEqual(q.fixed_exception(Evil()),'UNCLASSIFIED_ERROR')

    def test_http_method_rejected_before_any_socket(self):
        import alpha_observation_qualification as q
        with patch.object(q.socket,'socket') as effect,self.assertRaises(ValueError):q.read_only_roundtrip(None,'POST')
        effect.assert_not_called()

    def test_disposable_cannot_accept_provider_receipt(self):
        from truth_spine_full_day_runner import ObservationLifecycle
        c=self.admit();owner=ObservationLifecycle.for_disposable(configuration(c),c)
        with self.assertRaisesRegex(ValueError,'DISPOSABLE_PROVIDER_FORBIDDEN'):owner.observe_receipt(0,{},[],{})

    def test_scope_changed_startup_receipt_fails_existing_owner(self):
        from truth_spine_process_identity import observation_binding
        c=self.admit()
        with patch('truth_spine_process_identity.file_hash',return_value='f'*64):
            v=observation_binding(Path(self.roots['output']),'observation-child-'+'a'*32,
                'observation-runner-'+'b'*32,'scheduler',None,self.now.isoformat(),c)
        self.assertEqual(v['scope'],SCOPE);self.assertFalse(v['production_qualified'])
        self.assertNotEqual(v['scope'],'BOUNDED_REAL_PROVIDER_OBSERVATION')


class ControlledComparisonTests(unittest.TestCase):
    def setUp(self):
        from test_alpha_denial_collector import CollectorTests
        # Use the collector's independently bounded fixture, not a permissive fake query.
        self.helper=CollectorTests();self.helper.setUp();self.spec=self.helper.spec
        self.allowed=dict(scope='DISPOSABLE_DENIAL_ONLY',operation=self.spec['operation'],target=self.spec['target'],
            input_parent='a'*64,host_parent=self.spec['host_parent'],uid=501,profile_parent=None,
            owner_parent='b'*64,outcome='ALLOWED',errno=None,authority=locked_authority())
        self.denied=dict(self.allowed,owner_parent=self.spec['owner_parent'],profile_parent=self.spec['profile_parent'],outcome='DENIED',errno=13)
    def evaluate(self,category='OS_DENIAL_REPORT_MATCH'):
        from alpha_observation_qualification import controlled_denial
        result=dict(category=category,matches=1,collector_exit_verified=True,collector_exit=0)
        with patch('alpha_denial_collector.collect',return_value=result) as collector:
            r=controlled_denial(self.allowed,self.denied,self.spec,content_hash(self.spec),owner={},
                owner_parent=self.spec['owner_parent'],comparison_parent=content_hash(dict(allowed=self.allowed,denied=self.denied)))
            self.assertEqual(collector.call_count,1)
            return r
    def test_attribution_needs_control_and_actual_collector_match(self):
        r=self.evaluate();self.assertEqual(r['attribution'],'CONTROLLED_CORRELATED_DENIAL')
        self.assertFalse(r['production_qualified']);self.assertFalse(r['confinement_qualified'])
    def test_permission_errors_without_os_match_remain_unattributed(self):
        for category in ('UNKNOWN','OVERFLOW','COLLECTION_FAILED','IDENTITY_CHANGED'):
            with self.subTest(category=category):self.assertEqual(self.evaluate(category)['attribution'],'UNATTRIBUTED')
    def test_mismatched_control_rejected_before_collector(self):
        for key,value in [('target','/different'),('uid',502),('input_parent','c'*64),('host_parent','c'*64),('outcome','DENIED')]:
            old=self.allowed[key];self.allowed[key]=value
            with self.subTest(key=key),patch('alpha_denial_collector.collect') as effect,self.assertRaises(ValueError):self.evaluate()
            effect.assert_not_called();self.allowed[key]=old
    def test_forged_scope_owner_and_profile_rejected(self):
        for key,value in [('scope','LIVE_QUALIFICATION'),('owner_parent','c'*64),('profile_parent','c'*64),('errno',True)]:
            old=self.denied[key];self.denied[key]=value
            with self.subTest(key=key),patch('alpha_denial_collector.collect') as effect,self.assertRaises(ValueError):self.evaluate()
            effect.assert_not_called();self.denied[key]=old


class DisposableProjectionTests(unittest.TestCase):
    setUp=DisposableAdmissionTests.setUp
    admit=DisposableAdmissionTests.admit
    def test_real_seed_publication_readonly_get_head_and_tamper(self):
        import tempfile,json
        from alpha_session_execution import safe_root,publish
        from truth_spine_full_day_service import publish_observation_once,observation_response
        from truth_spine_session_package import role_projection
        from truth_spine_integration import atomic
        # A fresh registered test destination; never an operational evidence root.
        temp=Path(tempfile.mkdtemp(prefix='projection-',dir=os.environ['IIOS_GATEWAY_TEST_ROOT']))
        self.roots={k:str(temp/'execution-01'/v) for k,v in dict(runtime='output/runtime-pilot',release='release',control='control',output='disposable').items()}
        # The descriptor's approved parent naming is independent of the mutable seed directory.
        temp.rename(temp.with_name('iios-provider-connection-source-tests-'+temp.name));temp=temp.with_name('iios-provider-connection-source-tests-'+temp.name)
        self.roots={k:str(temp/'execution-01'/v) for k,v in dict(runtime='output/runtime-pilot',release='release',control='control',output='disposable').items()};self.d['roots']=self.roots
        self.d['runtime']['root']=self.roots['runtime'];self.d['runtime_parent']=content_hash(self.d['runtime'])
        c=self.admit();config=configuration(c);root=Path(self.roots['output']);(root/'requests').mkdir(parents=True,mode=0o700)
        fd=safe_root(str(root/'requests'))
        try:
            for i,row in enumerate(self.seeds):publish(fd,f'{i}.seed.json',row)
        finally:os.close(fd)
        with patch.object(DisposableRoles,'recheck',return_value=c):
            projected=publish_observation_once(config,c,self.now)
            # Publisher still uses its original atomically derived evidence mechanism.
            p=json.loads((root/'observation-projection.json').read_text())
            atomic(root/'observation-probes.json',record(c,dict(schema='iios-observation-probes-v1',
                admission_parent=c.identity,projection_parent=content_hash(p),observed_at=self.now.isoformat(),
                owners=dict.fromkeys(('scheduler','publisher','backend'),'a'*64),authority=locked_authority())))
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for method in ('GET','HEAD'):
                code,value=observation_response(config,c,'/truth-spine/observation',now=self.now,method=method)
                self.assertEqual(code,200);self.assertEqual(value['completed'],0);self.assertEqual(value['seeded_records'],3)
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(observation_response(config,c,'/truth-spine/observation',now=self.now,method='POST')[0],405)
            # No seed can be replaced with a live completion or count as a dispatch.
            (root/'requests/1.seed.json').chmod(0o600)
            (root/'requests/1.seed.json').write_text(json.dumps(dict(self.seeds[1],executed_requests=1)))
            self.assertEqual(observation_response(config,c,'/truth-spine/observation',now=self.now)[0],503)


class FrameworkRoleTests(unittest.TestCase):
    def test_independent_v2_descriptor_and_recheck_no_scope_upgrade(self):
        from test_alpha_runtime_files import structural_rows,policy_fields
        from alpha_runtime_files import DESCRIPTOR_SCHEMA
        d,roots,now,_=fixture();rows,meta=structural_rows()
        d['schema']='iios-disposable-observation-roles-v2'
        d['runtime'].update(schema=DESCRIPTOR_SCHEMA,files=rows,**policy_fields(meta))
        d['runtime_parent']=content_hash(d['runtime'])
        c=admit_roles(d,content_hash(d),approved_roots=roots,now=now)
        self.assertFalse(record(c,{})['production_qualified'])
        with patch('alpha_runtime_files.verify_runtime_tree',return_value={}) as runtime,\
            patch('alpha_session_evidence.verify_files') as generic:
            self.assertEqual(c.recheck(now).identity,c.identity)
            runtime.assert_called_once();self.assertEqual(generic.call_count,2)
        with patch('alpha_runtime_files.verify_runtime_tree',side_effect=ValueError('LINK_CHANGED')):
            with self.assertRaisesRegex(ValueError,'LINK_CHANGED'):c.recheck(now)
        for key,value in [('runtime_parent','f'*64),('schema','iios-disposable-observation-roles-v1'),('scope','LIVE_QUALIFICATION')]:
            bad=deepcopy(d);bad[key]=value
            with self.assertRaises(ValueError):admit_roles(bad,content_hash(bad),approved_roots=roots,now=now)

class RuntimeHeadersRoleTests(unittest.TestCase):
    def test_real_headers_shape_reaches_disposable_runtime_admission(self):
        from test_alpha_runtime_files import structural_rows,policy_fields
        from alpha_runtime_files import DESCRIPTOR_SCHEMA
        d,roots,now,_=fixture();rows,meta=structural_rows()
        rows.append(dict(path='Headers/Python.h',size=1,mode=0o400,sha256='a'*64))
        meta.update({'Headers':{},'Headers/Python.h':{}})
        d['schema']='iios-disposable-observation-roles-v2'
        d['runtime'].update(schema=DESCRIPTOR_SCHEMA,files=rows,**policy_fields(meta))
        d['runtime_parent']=content_hash(d['runtime'])
        cap=admit_roles(d,content_hash(d),approved_roots=roots,now=now)
        self.assertFalse(record(cap,{})['production_qualified'])
        for key in ('headers','cookies','authorization','api_key'):
            bad=deepcopy(d);bad[key]='not-a-real-secret'
            with self.assertRaises(ValueError):admit_roles(bad,content_hash(bad),approved_roots=roots,now=now)
        bad=deepcopy(d);bad['runtime']['metadata']['Headers']={'token':'not-a-real-secret'}
        with self.assertRaises(ValueError):admit_roles(bad,content_hash(bad),approved_roots=roots,now=now)
