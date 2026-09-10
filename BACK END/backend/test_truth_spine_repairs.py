"""SB3.2 offline adversarial tests; no credential, provider or admission writes."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from truth_spine_adapters import (EVIDENCE_CLASSIFICATIONS, MemoryTrustAnchor,
    admit_lesson, normalize_record, read_ledger, source)
from truth_spine_authority import disabled_document
from truth_spine_contract import canonical, digest, seal
from truth_spine_integration import ingest, snapshot


class ImportBoundaryTests(unittest.TestCase):
    def test_real_import_and_construction_do_not_access_provider_or_credentials(self):
        code = '''
import sys
def audit(event, args):
    if event in {'socket.connect', 'subprocess.Popen'} or (event == 'ctypes.dlopen' and args[0] is not None):
        raise AssertionError('EXTERNAL_SIDE_EFFECT')
sys.addaudithook(audit)
from expansion_wing.financial_datasets import FinancialDatasetsAdapter, FDPolicy
class Credentials:
    def retrieve(self): raise AssertionError('CREDENTIAL_ACCESS')
def transport(*args): raise AssertionError('PROVIDER_ACCESS')
adapter=FinancialDatasetsAdapter(FDPolicy(enabled=True,provider_balance=1),credentials=Credentials(),transport=transport)
assert adapter.transport_calls == 0
assert adapter.credits.consumed == 0
assert adapter.capabilities()
'''
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=Path(__file__).parent,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_expansion_discovery_imports_without_authority(self):
        # Discovery, not execution: no attempt to grant an offline test authority.
        loader = unittest.TestLoader()
        loader.discover(str(Path(__file__).parent/'expansion_wing'), top_level_dir=str(Path(__file__).parent))
        self.assertEqual(loader.errors, [])

    def test_invocation_rejections_precede_all_side_effects(self):
        from expansion_wing.financial_datasets import FinancialDatasetsAdapter, FDPolicy, FDCapability
        now = datetime(2026, 9, 9, 20, tzinfo=timezone.utc)
        owners = {'scheduler':'scheduler', 'publisher':'publisher'}
        doc = disabled_document('binding', 'release', **owners,
            issued_at=now.isoformat(), expires_at=(now+timedelta(hours=1)).isoformat())
        bad = copy.deepcopy(doc); bad['capabilities']['provider_requests'] = True
        cases = [None, doc, {}, seal(bad), seal({**doc,'binding':'wrong'}),
                 seal({**doc,'release_id':'wrong'}), seal({**doc,'owners':{}}),
                 seal({**doc,'issued_at':(now-timedelta(hours=2)).isoformat(),
                       'expires_at':(now-timedelta(hours=1)).isoformat()})]
        for document in cases:
            with self.subTest(document=document and document.get('binding')):
                credentials = Mock(); transport = Mock()
                adapter = FinancialDatasetsAdapter(FDPolicy(enabled=True, provider_balance=1),
                    credentials=credentials, transport=transport)
                with patch('truth_spine_authority.datetime') as clock:
                    clock.now.return_value = now
                    with self.assertRaises((PermissionError, ValueError)):
                        adapter.fetch(FDCapability.COMPANY_FACTS, ('MU',), authority=document,
                            authority_binding='binding', authority_release='release', authority_owners=owners)
                credentials.retrieve.assert_not_called(); transport.assert_not_called()
                self.assertEqual((adapter.transport_calls, adapter.credits.consumed), (0, 0))

    def test_direct_request_and_tls_entrypoints_cannot_bypass_fetch_guard(self):
        from expansion_wing.financial_datasets import FinancialDatasetsAdapter, ENDPOINTS, FDCapability
        from expansion_wing.financial_datasets_tls import FinancialDatasetsHTTPSTransport
        credentials=Mock(); transport=Mock(); trust=Mock(); connection=Mock()
        adapter=FinancialDatasetsAdapter(credentials=credentials,transport=transport)
        tls=FinancialDatasetsHTTPSTransport(trust,connection_factory=connection,environment={})
        for call in (lambda:adapter._request(ENDPOINTS[FDCapability.COMPANY_FACTS],('MU',)),
                     lambda:tls('',{},(),1,1),
                     lambda:tls.operational_request(path='/prices/snapshot',ticker='SPY',credential=b'')):
            with self.assertRaisesRegex(PermissionError,'AUTHORITY_MISSING'):call()
        credentials.retrieve.assert_not_called();transport.assert_not_called()
        trust.build_context.assert_not_called();connection.assert_not_called()


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.spec = {'kind':'historical','store_id':'historical:'+'a'*64,'sha256':'a'*64}

    def test_all_classifications_preserved_independent_of_age(self):
        for classification in EVIDENCE_CLASSIFICATIONS:
            with self.subTest(classification=classification):
                row = normalize_record(self.spec, 'same', 'agent_result',
                    canonical({'classification':classification}), '2000-01-01T00:00:00Z')
                self.assertEqual(row['classification'], classification)
                self.assertEqual(row['evidence_classification'], classification)
                self.assertEqual(row['retention_context'], 'RETAINED_READ_ONLY')
                self.assertEqual(row['record_origin'], 'historical')
                self.assertFalse(row['operational_fill'])
                self.assertIsNone(row['evidence_available'])

    def test_malformed_unknown_and_conflicting_values_rejected(self):
        for value in ('CURRENT', '', None, True, 0, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_record(self.spec,'same','agent_result',canonical({'classification':value}),None)
        for before, after in [('SIMULATED','HISTORICAL'),('NARRATIVE','HISTORICAL'),
                              ('REPLAY','LIVE_VERIFIED'),('UNAVAILABLE','LIVE_VERIFIED'),('STALE','LIVE_VERIFIED')]:
            with self.subTest(before=before), self.assertRaisesRegex(ValueError,'CONFLICT'):
                normalize_record(self.spec,'same','agent_result',canonical(
                    {'evidence_classification':before,'classification':after}),None)

    def test_missing_provenance_is_unavailable_not_historical(self):
        row=normalize_record(self.spec,'id','agent_result',b'{}',None)
        self.assertEqual((row['classification'],row['freshness']),('UNAVAILABLE','UNAVAILABLE'))
        self.assertEqual(row['classification_basis'],'MISSING_CLASSIFICATION')

    def test_executor_session_classification_is_not_evidence_provenance(self):
        data={'schema_version':'iios-operational-market-executor-v1','classification':'POST_0930_PARTIAL_SESSION'}
        row=normalize_record({**self.spec,'kind':'executor'},'id','executor',canonical(data),None)
        self.assertEqual(row['session_classification'],'POST_0930_PARTIAL_SESSION')
        self.assertEqual(row['evidence_classification'],'UNAVAILABLE')
        self.assertEqual(row['freshness'],'UNAVAILABLE')
        archive=normalize_record({**self.spec,'kind':'archive'},'id','archive',canonical(
            {**data,'schema_version':'iios-operational-market-session-archive-v1'}),None)
        self.assertEqual(archive['session_classification'],'POST_0930_PARTIAL_SESSION')
        self.assertEqual(archive['evidence_classification'],'UNAVAILABLE')
        with self.assertRaisesRegex(ValueError,'SESSION_CLASSIFICATION_INVALID'):
            normalize_record({**self.spec,'kind':'executor'},'id','executor',canonical({**data,'classification':'UNKNOWN'}),None)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_CLASSIFICATION_INVALID'):
            normalize_record(self.spec,'id','agent_result',canonical(data),None)

    def test_narrative_shadow_and_stale_cannot_be_upgraded(self):
        with self.assertRaisesRegex(ValueError,'UPGRADE'):
            normalize_record(self.spec,'id','narrative',canonical({'classification':'HISTORICAL'}),None)
        with self.assertRaisesRegex(ValueError,'UPGRADE'):
            normalize_record({**self.spec,'kind':'shadow_9i'},'id','agent_result',canonical({'classification':'LIVE_VERIFIED'}),None)
        row=normalize_record(self.spec,'id','agent_result',canonical({'classification':'STALE','freshness':'CURRENT'}),None)
        self.assertEqual(row['freshness'],'STALE')

    def test_resealed_persisted_upgrade_rejected_and_replay_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve(); db=root/'original.db'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE ledger_objects(object_id TEXT, object_type TEXT,payload_json TEXT,created_at TEXT)')
                conn.execute('INSERT INTO ledger_objects VALUES (?,?,?,?)',('id','agent_result',
                    json.dumps({'classification':'SIMULATED'}),'2026-09-08T12:00:00Z'))
            original=db.read_bytes(); spec=source(db,'historical')
            t={'sources':[spec],'event_ledger_path':str(root/'canonical-events.db'),'content_hash':'test-topology'}
            ingest(t); event=Path(t['event_ledger_path']); before=event.read_bytes()
            ingest(t); self.assertEqual(event.read_bytes(),before)
            # Read-only normalization across restart produces exact bytes.
            self.assertEqual(canonical(read_ledger(spec)),canonical(read_ledger(spec)))
            with sqlite3.connect(event) as conn:
                raw=conn.execute('SELECT payload FROM records').fetchone()[0]
                row=seal({**json.loads(raw),'classification':'HISTORICAL','evidence_classification':'HISTORICAL'})
                # Adversarial isolated database only, never an operational selector/evidence store.
                conn.execute('DROP TRIGGER records_no_update')
                conn.execute('UPDATE records SET payload=?',(canonical(row).decode(),))
            with self.assertRaisesRegex(ValueError,'RECORD_PROVENANCE_MISMATCH'):
                snapshot(t,{},now=datetime(2026,9,9,tzinfo=timezone.utc))
            self.assertEqual(db.read_bytes(),original)


class IndependentMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.raw=b'offline original evidence, never provider data'
        self.common={'source_store_identity':'L7:'+'1'*64,'source_object_identity':'bare-object',
            'generation':'isolated-generation','ticker':'MU','topology_identity':'a'*64,
            'authority_identity':'b'*64,'evidence_classification':'HISTORICAL'}
        self.common['case_id']=digest({'store':self.common['source_store_identity'],
                                      'object':self.common['source_object_identity']})
        self.objects={}
        for kind in ('case','evidence','committee','risk','measurement','decision','outcome','admission','record'):
            self.objects[kind]={**self.common,'schema':f'iios-memory-{kind}-v1','identity':kind+'-identity'}
        self.objects['evidence'].update(original_evidence_hash=hashlib.sha256(self.raw).hexdigest(),receipt_identity='original-evidence-receipt')
        self.objects['measurement'].update(definition='price change with fixed denominator',horizon='one-session')
        self.objects['outcome'].update(classification='MEASURED',measurement_horizon='one-session',receipt_identity='measurement-receipt')
        self.objects['admission'].update(decision='ADMIT',human_validated=True,admission_policy_version='memory-policy-v1')
        self.objects['record']['memory_class']='VALIDATED_LESSON'
        self.rebind(self.objects)
        self.pin_originals()

    @staticmethod
    def rebind(objects):
        links={'decision':('evidence','committee','risk'),'outcome':('evidence','decision','measurement'),
               'admission':('case','evidence','decision','committee','risk','measurement','outcome'),
               'record':('evidence','decision','outcome','admission')}
        for kind in ('case','evidence','committee','risk','measurement','decision','outcome','admission','record'):
            for target in links.get(kind,()):
                objects[kind][target+'_hash']=objects[target]['content_hash']
                objects[kind][target+'_identity']=objects[target]['identity']
            objects[kind]=seal(objects[kind])

    def pin_originals(self):
        # Synthetic independent registry established before any adversarial submission.
        entry={}
        for kind, value in {**self.objects,'raw_evidence':self.raw}.items():
            raw=value if isinstance(value,bytes) else canonical(value)
            path=self.root/(kind+'.json'); path.write_bytes(raw); path.chmod(0o600)
            entry[kind]={'path':path.name,'sha256':hashlib.sha256(raw).hexdigest()}
        registry=seal({'schema':'iios-memory-source-registry-v1','topology_identity':'a'*64,
            'authority_identity':'b'*64,'admission_policy_version':'memory-policy-v1',
            'entries':{'admission-identity':entry}})
        p=self.root/'registry.json';p.write_bytes(canonical(registry));p.chmod(0o600)
        self.anchor=MemoryTrustAnchor(p,hashlib.sha256(p.read_bytes()).hexdigest(),'a'*64,'b'*64,'memory-policy-v1')

    def inventory(self):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}

    def submit(self, objects=None, anchor=None):
        objects=objects or self.objects
        return admit_lesson(objects['record'],**{k:objects[k] for k in ('case','evidence','decision','outcome','admission')},
                            trusted=anchor or self.anchor)

    def reject(self, objects):
        before=self.inventory()
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT_PROVENANCE'):self.submit(objects)
        self.assertEqual(self.inventory(),before)

    def test_valid_independent_chain_is_read_only_and_restart_safe(self):
        before=self.inventory(); self.assertEqual(self.submit(),self.objects['record'])
        restarted=MemoryTrustAnchor(**vars(self.anchor))
        self.assertEqual(self.submit(anchor=restarted),self.objects['record'])
        self.assertEqual(self.inventory(),before)

    def test_cross_case_with_every_hash_recomputed(self):
        changed=copy.deepcopy(self.objects)
        for item in changed.values():item['case_id']='another-case'
        self.rebind(changed);self.reject(changed)

    def test_evidence_original_binding_cannot_follow_recomputed_children(self):
        changed=copy.deepcopy(self.objects);changed['evidence']['case_id']='different-case'
        self.rebind(changed);self.reject(changed)

    def test_ticker_namespace_generation_decision_horizon_substitution(self):
        substitutions=[('outcome','ticker','SPY'),('evidence','source_store_identity','L8:'+'1'*64),
            ('evidence','generation','different-generation'),('decision','identity','different-decision'),
            ('measurement','horizon','ten-years'),('outcome','measurement_horizon','ten-years'),
            ('record','source_store_identity','L8:'+'1'*64),('case','source_object_identity','different-object')]
        for kind,key,value in substitutions:
            with self.subTest(kind=kind,key=key):
                changed=copy.deepcopy(self.objects);changed[kind][key]=value
                self.rebind(changed);self.reject(changed)

    def test_valid_looking_narrative_simulated_replay_cannot_admit(self):
        for classification in ('NARRATIVE','SIMULATED','REPLAY','UNAVAILABLE','STALE'):
            with self.subTest(classification=classification):
                changed=copy.deepcopy(self.objects)
                for item in changed.values():item['evidence_classification']=classification
                self.rebind(changed);self.reject(changed)
        # Even a registry pinned to such a chain must reject it semantically.
        for item in self.objects.values():item['evidence_classification']='NARRATIVE'
        self.rebind(self.objects);self.pin_originals();self.reject(self.objects)

    def test_missing_original_receipt_and_unpinned_admission(self):
        (self.root/'evidence.json').unlink()  # Only this test's synthetic fixture.
        self.reject(self.objects)
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT_PROVENANCE'):
            admit_lesson(self.objects['record'],**{k:self.objects[k] for k in ('case','evidence','decision','outcome','admission')})

    def test_tampered_registry_permissions_symlink_and_raw_evidence(self):
        original=(self.root/'raw_evidence.json').read_bytes()
        (self.root/'raw_evidence.json').write_bytes(b'tampered offline fixture');self.reject(self.objects)
        (self.root/'raw_evidence.json').write_bytes(original)
        (self.root/'evidence.json').chmod(0o644);self.reject(self.objects)
        (self.root/'evidence.json').chmod(0o600)
        path=self.root/'registry.json'; original=path.read_bytes();path.write_bytes(original+b' ');self.reject(self.objects)

    def test_symlinked_original_and_wrong_anchor_rejected(self):
        path=self.root/'evidence.json'; target=self.root/'original-copy.json'
        path.rename(target);path.symlink_to(target)
        before=self.inventory()
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT_PROVENANCE'):self.submit()
        self.assertEqual(before,self.inventory())

    def test_bootstrap_pin_cannot_be_replaced_by_submission(self):
        changed=copy.deepcopy(self.objects)
        changed['record']['trusted_registry']='caller-selected'
        self.rebind(changed);self.reject(changed)
        for key,value in [('topology_identity','c'*64),('authority_identity','c'*64),
                          ('admission_policy_version','other-policy'),('registry_sha256','c'*64)]:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'INSUFFICIENT_PROVENANCE'):
                self.submit(anchor=MemoryTrustAnchor(**{**vars(self.anchor),key:value}))

    def test_rejected_admission_then_restart_and_concurrent_duplicates_write_nothing(self):
        before=self.inventory();changed=copy.deepcopy(self.objects);changed['evidence']['ticker']='SPY'
        self.rebind(changed);self.reject(changed)
        anchor=MemoryTrustAnchor(**vars(self.anchor))
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(lambda _:self.submit(anchor=anchor),range(16)))
        self.assertEqual(len({r['content_hash'] for r in rows}),1)
        self.assertEqual(self.inventory(),before)
        self.assertFalse((self.root/'validated-memory.db').exists())


if __name__ == '__main__':
    unittest.main()
