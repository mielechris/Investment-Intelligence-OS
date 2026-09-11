from __future__ import annotations

import ast
import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from truth_spine_adapters import admit_lesson, normalize_record, read_document, read_ledger, reconcile, source, universe_version
from truth_spine_authority import CAPABILITIES, disabled_document, gateway, require_capability, validate_authority
from truth_spine_contract import canonical, seal
from truth_spine_integration import DAY_CHAIN, atomic, derived_bindings, museum_adapter
from truth_spine_integration_service import Lease, heartbeat, probe, health


class HistoricalLineageTests(unittest.TestCase):
    def test_package_view_is_derived_from_admitted_records_and_keeps_original_clocks(self):
        from truth_spine_lineage import historical_generation
        from truth_spine_integration_service import historical_view
        from truth_spine_contract import verified
        at='2026-09-11T03:00:00+00:00'
        original='2020-01-02T00:00:00+00:00'
        files={name:{'source_sha256':str(i)*64} for i,name in enumerate(
            ('manifest.json','completion-receipt.json','l7/snapshot.db','l8/snapshot.db'),1)}
        admission=seal({'common_watermark':original,'files':files})
        record={'record_id':'retained-case','source_store_identity':'history:test','record_type':'case',
                'original_content_hash':'a'*64,'classification':'REPLAY','event_time':original,
                'observation_time':original,'publication_time':original}
        with patch('truth_spine_adapters.read_document',return_value=[record]):
            generation,events=historical_generation([{'kind':'research','store_id':'history:test','sha256':'b'*64}],admission,'c'*64)
        manifest={'lineage':{'package_generation':'c'*64,'initial_cycle':{'sha256':'d'*64}},
                  'source_base':'e'*40,'dependency_hash':'f'*64,'frontend_content_hash':'a'*64}
        topology={'root':'/synthetic','release_manifest_hash':'b'*64,
                  'identities':{'scheduler_owner':'scheduler','publisher_owner':'publisher'}}
        with patch('truth_spine_lineage.verify_chain',return_value={'admission':admission,'generation':generation,'events':events}):
            view=historical_view(topology,manifest,{'content_hash':'f'*64},at)
        verified(view['factory'])
        self.assertEqual(view['sources'][0]['event_time'],original)
        self.assertEqual(view['lineage']['common_watermark'],original)
        self.assertEqual(view['published_at'],at)
        self.assertEqual(view['phase'],'SESSION_CLOSED')
        self.assertEqual(view['source_generation'],generation['content_hash'])
        self.assertEqual(view['lineage']['projection_hash'],view['factory']['content_hash'])
        self.assertEqual(len(view['factory']['rooms']),24)
        self.assertTrue(all(x is False for x in view['capabilities'].values()))

    def test_unhealthy_actual_backend_cannot_serve_historical_success(self):
        from truth_spine_integration_service import historical_response
        with patch('truth_spine_integration_service.topology',return_value=({'schema':'iios-historical-topology-v3'},{})), \
             patch('truth_spine_integration_service.health',return_value=(503,{'status':'NOT_READY'})), \
             patch('truth_spine_integration_service.historical_view',side_effect=AssertionError('NO_FALLBACK')):
            self.assertEqual(historical_response(Path('/synthetic'),'/truth-spine/full-session',{}),
                             (503,{'status':'NOT_READY'}))


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,9,20,tzinfo=timezone.utc)
        self.doc=disabled_document('binding','release','scheduler','publisher',self.now.isoformat(),(self.now+timedelta(hours=1)).isoformat())

    def validate(self,doc=None,now=None):
        return validate_authority(doc or self.doc,binding='binding',release='release',owners={'scheduler':'scheduler','publisher':'publisher'},now=now or self.now)

    def test_all_capabilities_default_false(self):
        self.validate();self.assertEqual(set(self.doc['capabilities']),set(CAPABILITIES))
        self.assertTrue(all(v is False for v in self.doc['capabilities'].values()))

    def test_each_missing_capability_denied(self):
        for cap in CAPABILITIES:
            with self.subTest(cap=cap),self.assertRaises(PermissionError):require_capability(cap)

    def test_each_true_authority_rejected(self):
        for cap in CAPABILITIES:
            d=copy.deepcopy(self.doc);d['capabilities'][cap]=True
            with self.subTest(cap=cap),self.assertRaises(PermissionError):self.validate(seal(d))

    def test_expired_future_and_naive(self):
        for now in [self.now-timedelta(seconds=1),self.now+timedelta(hours=2),self.now.replace(tzinfo=None)]:
            with self.subTest(now=now),self.assertRaises(PermissionError):self.validate(now=now)

    def test_wrong_binding_release_owner_and_schema(self):
        for key,val in [('binding','wrong'),('release_id','wrong'),('owners',{}),('schema','wrong')]:
            d={**self.doc,key:val}
            with self.subTest(key=key),self.assertRaises(PermissionError):self.validate(seal(d))

    def test_tamper_not_resealed(self):
        self.doc['activation']='YES'
        with self.assertRaises(ValueError):self.validate()

    def test_unknown_provider_not_implemented(self):
        fields={'provider','selector_identity','capability','endpoint','entitlement','retention','request_identity','rate_policy','cost_budget','source_binding','session_binding','classification','receipt_schema','citation_policy'}
        for provider in ('ALPACA','ALPHA_VANTAGE','BIGDATA'):
            request=dict.fromkeys(fields,'test');request['provider']=provider
            with self.subTest(provider=provider),self.assertRaisesRegex(PermissionError,'NOT_IMPLEMENTED'):gateway(request)

    def test_no_secret_field_allowed(self):
        with self.assertRaises(PermissionError):gateway({'api_key':'never-a-real-key'})

    def test_every_guarded_entrypoint_rejects_before_body(self):
        root=Path(__file__).parent;inventory=json.loads((root/'truth_spine_entrypoints.json').read_bytes())
        for rel,name,cap in inventory:
            with self.subTest(file=rel,function=name):
                tree=ast.parse((root/rel).read_text())
                matches=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name
                         and not (len(n.body)==1 and isinstance(n.body[0],ast.Expr)
                                  and isinstance(n.body[0].value,ast.Constant) and n.body[0].value.value is Ellipsis)]
                self.assertTrue(matches)
                for original in matches:
                    body=original.body
                    if isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str):body=body[1:]
                    self.assertIsInstance(body[0],ast.ImportFrom);self.assertEqual(body[0].module,'truth_spine_authority')
                    self.assertEqual(ast.literal_eval(body[1].value.args[0]),cap)
                    # Execute the actual first statements, with the rest replaced by a
                    # tripwire: no production module import/startup or credential lookup.
                    fn=copy.deepcopy(original);fn.decorator_list=[];fn.returns=None;fn.body=body[:2]+ast.parse("raise AssertionError('SIDE_EFFECT_REACHED')").body
                    for arg in fn.args.posonlyargs+fn.args.args+fn.args.kwonlyargs:arg.annotation=None
                    fn.args.defaults=[ast.Constant(None) for _ in fn.args.defaults]
                    fn.args.kw_defaults=[ast.Constant(None) for _ in fn.args.kw_defaults]
                    module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));ns={};exec(compile(module,rel,'exec'),ns)
                    args=[None for _ in fn.args.posonlyargs+fn.args.args]
                    kwargs={a.arg:True if a.arg=='allow_paper_execution' else None for a in fn.args.kwonlyargs}
                    with self.assertRaises(PermissionError):ns[name](*args,**kwargs)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        from test_truth_spine_lineage import retained_root
        from truth_spine_adapters import SQLitePolicy, create_run_event_store, strict_sqlite_scope, connect_strict_sqlite
        import os
        self.root=retained_root('legacy-adapter-regression')
        (self.root/'state').mkdir();(self.root/'admission').mkdir()
        policy=SQLitePolicy(str(self.root),'a'*64,'b'*64,'synthetic',os.getpid(),os.environ['IIOS_SB38D_TEST_ROOT'])
        capability=create_run_event_store(policy,'c'*64,'state/legacy.db');self.db=Path(capability.path)
        with strict_sqlite_scope(policy):
            db=connect_strict_sqlite(capability)
            try:
                # An individually registered synthetic store supplies legacy
                # behavior tests; no old evidence database is ever a fixture.
                db.execute('PRAGMA journal_mode=OFF')
                db.execute('CREATE TABLE ledger_objects(object_id TEXT,object_type TEXT,payload_json TEXT,created_at TEXT)')
                db.execute('INSERT INTO ledger_objects VALUES (?,?,?,?)',('same-id','case','{"case_id":"same-id"}','2026-09-08T20:00:00Z'));db.commit()
            finally:db.close()

    def test_ledger_is_readonly_and_namespaced(self):
        before=self.db.read_bytes();a=read_ledger(source(self.db,'operational'));b=read_ledger(source(self.db,'historical'))
        self.assertNotEqual(a[0]['record_id'],b[0]['record_id']);self.assertEqual(reconcile(a+b)['records'],2)
        self.assertEqual(self.db.read_bytes(),before)

    def test_collision_rejected(self):
        a=read_ledger(source(self.db,'operational'))[0];b=seal({**a,'classification':'SIMULATED'})
        with self.assertRaises(ValueError):reconcile([a,b])

    def test_source_hash_mismatch(self):
        s=source(self.db,'operational');self.db.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):read_ledger(s)

    def test_symlink_and_relative_rejected(self):
        p=self.root/'link';p.symlink_to(self.db)
        for path in (p,Path('legacy.db')):
            with self.assertRaises(ValueError):source(path,'operational')

    def test_empty_ledger_rejected(self):
        db=sqlite3.connect(self.db);db.execute('PRAGMA journal_mode=MEMORY');db.execute('DELETE FROM ledger_objects');db.commit();db.close()
        with self.assertRaises(ValueError):read_ledger(source(self.db,'operational'))

    def test_active_wal_not_ignored(self):
        Path(str(self.db)+'-wal').write_bytes(b'not-a-real-wal')
        with self.assertRaisesRegex(ValueError,'SNAPSHOT'):read_ledger(source(self.db,'operational'))

    def test_private_shadow_rejected(self):
        p=self.root/'private.json';p.write_bytes(canonical({'schema_version':'private-strategy','strategy':'PRIVATE_SENTINEL'}))
        with self.assertRaisesRegex(ValueError,'PRIVATE_9I'):read_document(source(p,'shadow_9i'))

    def test_public_summary_never_exports_private_content(self):
        p=self.root/'summary.json';p.write_bytes(canonical({'schema_version':'batch9i-browser-shadow-strategy-v1','strategy':'PRIVATE_SENTINEL'}))
        rows=read_document(source(p,'shadow_9i'));self.assertNotIn('PRIVATE_SENTINEL',json.dumps(rows));self.assertEqual(rows[0]['classification'],'SIMULATED')

    def test_memory_categories_not_promoted(self):
        spec=source(self.db,'historical')
        for kind in ('professional_judgment','historical_pattern_review','judgment_bank_review_queue','narrative'):
            row=normalize_record(spec,'id',kind,b'{}',None)
            self.assertNotEqual(row['memory_class'],'VALIDATED_LESSON')
            with self.assertRaises(ValueError):admit_lesson(row,case=seal({}),evidence=seal({}),decision=seal({}),outcome=seal({}),admission=seal({}))

    def test_observation_event_publication_are_separate(self):
        x={'observed_at':'2026-09-08T12:00:00Z','created_at':'2026-09-08T13:00:00Z','generated_at':'2026-09-09T12:00:00Z'}
        row=normalize_record(source(self.db,'historical'),'id','case',canonical(x),'2026-09-08T13:00:00Z')
        self.assertEqual(len({row['observation_time'],row['event_time'],row['publication_time']}),3)

    def test_dynamic_universes_preserve_518_and_517(self):
        prior=None;hashes=[]
        for count in (518,517):
            p=self.root/f'u{count}.json';p.write_bytes(canonical({'symbols':[f'T{i}' for i in range(count)],'symbol_count':count,'verified_complete':True,'created_at':'2026-09-09T13:30:00Z','source_lineage':[{'source_mode':'GOVERNED_INDEX_TRACKER_MIRROR','verified_complete':True}]}))
            v=universe_version(source(p,'universe'),previous=prior);self.assertEqual(v['count'],count);self.assertFalse(v['direct_official_membership']);hashes.append(v['member_hash']);prior=v['capture_id']
        self.assertNotEqual(*hashes)

    def test_one_owner_only(self):
        lease=Lease(self.root,'scheduler')
        try:
            with self.assertRaises(BlockingIOError):Lease(self.root,'scheduler')
        finally:lease.close()
        lease=Lease(self.root,'scheduler');lease.close()

    def test_day_trading_chain_has_no_execution_grant(self):
        self.assertEqual(len(DAY_CHAIN),15);self.assertIn('SEPARATE_PAPER_AUTHORIZATION',DAY_CHAIN)
        with self.assertRaisesRegex(PermissionError,'MISSING'):require_capability('paper_order')

    def test_stale_unavailable_and_replay_not_current(self):
        for state in ('STALE','UNAVAILABLE','FAILED_CLOSED'):
            row=normalize_record(source(self.db,'historical'),'id','case',canonical({'state':state,'classification':'REPLAY'}),None)
            self.assertEqual(row['freshness'],state);self.assertEqual(row['classification'],'REPLAY')

    def test_memory_admission_requires_all_bound_measured_inputs(self):
        case=seal({'case_id':'case'});evidence=seal({'case_id':'case','kind':'evidence'})
        decision=seal({'case_id':'case','kind':'decision'})
        outcome=seal({'case_id':'case','classification':'MEASURED','measurement_horizon':'one-session',
                      'evidence_hash':evidence['content_hash'],'decision_hash':decision['content_hash']})
        admission=seal({'case_id':'case','decision':'ADMIT','human_validated':True})
        record=seal({'case_id':'case','memory_class':'VALIDATED_LESSON','evidence_hash':evidence['content_hash'],
                     'decision_hash':decision['content_hash'],'outcome_hash':outcome['content_hash'],
                     'admission_hash':admission['content_hash']})
        kwargs=dict(case=case,evidence=evidence,decision=decision,outcome=outcome,admission=admission)
        # Self-consistent hashes alone no longer qualify as independent provenance.
        with self.assertRaisesRegex(ValueError, 'INSUFFICIENT_PROVENANCE'):
            admit_lesson(record,**kwargs)
        for key in ('case','evidence','decision','outcome','admission'):
            changed={**kwargs,key:seal({**kwargs[key],'case_id':'wrong'})}
            with self.subTest(key=key),self.assertRaises(ValueError):admit_lesson(record,**changed)

    def test_actual_lease_heartbeat_and_stale_rejection(self):
        t={'root':str(self.root),'content_hash':'topology','identities':{'scheduler_owner':'owner','release':'release',
            'executor_generation':'generation','source_cycle':'source'}}
        now=datetime.now(timezone.utc);lease=Lease(self.root,'scheduler')
        try:
            heartbeat(t,'scheduler',now);self.assertEqual(probe(t,'scheduler',now)['owner'],'owner')
            self.assertEqual(probe(t,'scheduler')['owner'],'owner')
            for field in ('owner','release','executor_generation','source_cycle','topology_identity','pid'):
                heartbeat(t,'scheduler',now);p=self.root/'scheduler-heartbeat.json';h=json.loads(p.read_bytes())
                h[field]=1 if field=='pid' else 'wrong';atomic(p,seal(h))
                with self.subTest(field=field),self.assertRaises((ValueError,OSError)):probe(t,'scheduler',now)
            heartbeat(t,'scheduler',now)
            with self.assertRaises(ValueError):probe(t,'scheduler',now+timedelta(seconds=16))
        finally:lease.close()
        with self.assertRaisesRegex(ValueError,'OWNER_NOT_RUNNING'):probe(t,'scheduler',now)

    def test_production_heartbeat_clock_is_sampled_after_atomic_read(self):
        import truth_spine_integration_service as service
        t={'root':str(self.root),'content_hash':'topology','identities':{'scheduler_owner':'owner','release':'release',
            'executor_generation':'generation','source_cycle':'source'}}
        lease=Lease(self.root,'scheduler');original=service.read_json;order=[]
        now=datetime.now(timezone.utc);heartbeat(t,'scheduler',now)
        def read(p):order.append('read');return original(p)
        class Clock:
            @staticmethod
            def now(tz):order.append('clock');return now
        try:
            with patch.object(service,'read_json',read),patch.object(service,'datetime',Clock):probe(t,'scheduler')
            self.assertEqual(order,['read','clock'])
        finally:lease.close()

    def test_liveness_is_not_dependency_readiness(self):
        absent=self.root/'absent.json'
        self.assertEqual(health(absent,'live')[0],200)
        for kind in ('ready','market-readiness','research-readiness'):
            self.assertEqual(health(absent,kind)[0],503)

    def test_process_guard_allows_source_hashing_not_credential_or_network(self):
        p=self.root/'keychain_adapter.py';p.write_text('# source, not a credential')
        program="""
import sys
from truth_spine_integration_service import deny_external_io
deny_external_io()
assert open(sys.argv[1]).read().startswith('# source')
for event,args in [('open',('/synthetic/login.keychain-db','r',0)),
                   ('open',('/synthetic/.env','r',0)),
                   ('socket.connect',(None,('127.0.0.1',1))),
                   ('subprocess.Popen',('security',[],None,None))]:
    try: sys.audit(event,*args)
    except PermissionError: pass
    else: raise AssertionError('CAPABILITY_ESCAPED')
"""
        result=subprocess.run([sys.executable,'-B','-c',program,str(p)],cwd=Path(__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_runtime_receipt_frontend_publisher_have_derived_bindings(self):
        runtime=self.root/'runtime';runtime.mkdir();inputs=self.root/'inputs';inputs.mkdir()
        atomic(runtime/'runtime-manifest.json',seal({'runtime_id':'verified-runtime'}))
        receipt=inputs/'accepted-receipt.json';receipt.write_bytes(b'accepted-evidence')
        manifest={'runtime_root':str(runtime),'release_id':'release','files':[
            {'path':'backend/truth_spine_integration_service.py','sha256':'publisher-code'},
            {'path':'frontend/index.html','sha256':'frontend-code'}]}
        bindings=derived_bindings(self.root,manifest,[])
        self.assertEqual(bindings['runtime'],'verified-runtime');self.assertEqual(bindings['publisher'],'publisher-code')
        receipt.write_bytes(b'changed-evidence')
        changed=derived_bindings(self.root,manifest,[])
        self.assertNotEqual(bindings['evidence_receipt'],changed['evidence_receipt'])
        manifest['files'][1]['sha256']='changed-frontend'
        self.assertNotEqual(changed['frontend'],derived_bindings(self.root,manifest,[])['frontend'])


if __name__=='__main__':unittest.main()
