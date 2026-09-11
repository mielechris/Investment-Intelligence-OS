"""Offline synthetic tests. All files remain in the explicit retained test root."""
import json
import os
from pathlib import Path
import sqlite3
import unittest
import uuid
import hashlib
from unittest.mock import patch

import truth_spine_lineage as lineage
from truth_spine_contract import canonical, seal


def retained_root(label):
    root=Path(os.environ['IIOS_SB38D_TEST_ROOT'])
    if root.parent!=Path('/private/tmp') or not root.name.startswith('iios-sb38d-source-tests-'):
        raise RuntimeError('EXPLICIT_TEST_ROOT_REQUIRED')
    path=root/(label+'-'+uuid.uuid4().hex);path.mkdir(mode=0o700)
    return path


def pin(path):
    return {'path':str(path),'sha256':lineage.file_hash(path),'bytes':path.stat().st_size,'mode':path.stat().st_mode&0o777}


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.root=retained_root('admission')
        self.original=self.root/'preserved.db';self.original.write_bytes(b'SYNTHETIC_SNAPSHOT');self.original.chmod(0o400)
        self.work=self.root/'working-inputs';self.work.mkdir()

    def test_three_hashes_and_distinct_inode_without_sqlite(self):
        before=pin(self.original)
        with patch.object(sqlite3,'connect',side_effect=AssertionError('PRESERVED_SQLITE_OPEN')):
            row=lineage.copy_pinned(before,self.root,'working-inputs/copied.db')
        self.assertEqual(row['source_sha256'],row['working_sha256'])
        self.assertEqual(row['source_after_sha256'],before['sha256'])
        self.assertNotEqual(self.original.stat().st_ino,(self.work/'copied.db').stat().st_ino)
        self.assertEqual(pin(self.original),before)

    def test_existing_destination_is_not_overwritten(self):
        target=self.work/'copied.db';target.write_bytes(b'ORIGINAL_EVIDENCE')
        with self.assertRaises(ValueError):lineage.copy_pinned(pin(self.original),self.root,'working-inputs/copied.db')
        self.assertEqual(target.read_bytes(),b'ORIGINAL_EVIDENCE')

    def test_bad_hash_size_and_mode_fail_before_creation(self):
        for key,value in [('sha256','0'*64),('bytes',999),('mode',0o600)]:
            row={**pin(self.original),key:value}
            with self.assertRaises(ValueError):lineage.copy_pinned(row,self.root,'working-inputs/'+key)
            self.assertFalse((self.work/key).exists())

    def test_symlink_and_parent_escape_reject(self):
        link=self.root/'link';link.symlink_to(self.original)
        with self.assertRaises(ValueError):lineage.file_hash(link)
        for name in ('../escape','/absolute'):
            with self.assertRaises(ValueError):lineage.contained(self.root,name)

    def test_receipt_exclusive_create(self):
        lineage.write_new(self.root,'receipt.json',b'first')
        with self.assertRaises(FileExistsError):lineage.write_new(self.root,'receipt.json',b'changed')
        self.assertEqual((self.root/'receipt.json').read_bytes(),b'first')

    def test_sqlite_checks_only_new_working_copy(self):
        from test_truth_spine_adapters import StrictSQLiteTests
        from truth_spine_adapters import strict_sqlite_scope
        registered=StrictSQLiteTests();registered.setUp()
        capability=registered.capabilities['L7_WORKING_COPY'];dbpath=Path(capability.path)
        expected=lineage.file_hash(dbpath)
        with strict_sqlite_scope(registered.policy):
            lineage.check_working_sqlite(registered.root,'working-inputs/l7.db',expected,capability=capability)
        self.assertEqual(lineage.file_hash(dbpath),expected)
        with patch.object(sqlite3,'connect',side_effect=AssertionError('MUST_NOT_OPEN')):
            with self.assertRaises(ValueError):lineage.check_working_sqlite(self.root,'preserved.db',pin(self.original)['sha256'])

    def test_contaminated_siblings_are_not_copied(self):
        (self.root/'preserved.db-wal').write_bytes(b'UNACCEPTED')
        lineage.copy_pinned(pin(self.original),self.root,'working-inputs/copied.db')
        self.assertEqual([p.name for p in self.work.iterdir()],['copied.db'])

    def test_hardlink_destination_rejected(self):
        os.link(self.original,self.work/'alias.db')
        with self.assertRaises(ValueError):lineage.copy_pinned(pin(self.original),self.root,'working-inputs/alias.db')

    def test_missing_spec_pin_never_creates_acceptance(self):
        spec=self.root/'spec.json';spec.write_bytes(b'{}')
        with self.assertRaises(ValueError):lineage.load_spec(spec,'','a'*40)


class CycleTests(unittest.TestCase):
    def test_historical_cycle_preserves_original_watermark_and_parents(self):
        admission=seal({'common_watermark':'2020-01-02T00:00:00Z','files':{'l7':{'source_sha256':'1'*64},'l8':{'source_sha256':'2'*64}}})
        generation=seal({'session':'historical-test','files':[],'watermark':{'count':0,'identity':'3'*64}})
        cycle=lineage.historical_cycle(generation,admission,'4'*64,'5'*40,'2026-09-11T00:00:00Z')
        self.assertEqual(cycle['classification'],'HISTORICAL_REPLAY')
        self.assertEqual(cycle['common_watermark'],admission['common_watermark'])
        self.assertEqual(cycle['admission_hash'],admission['content_hash'])
        for key,value in [('package_hash','6'*64),('source_commit','7'*40),('package_generation','8'*64)]:
            changed=dict(cycle);changed[key]=value
            from truth_spine_generations import cycle_identity
            self.assertNotEqual(cycle_identity(changed),cycle['source_cycle_id'])

    def test_canonical_cross_language_vector(self):
        self.assertEqual(canonical({'z':'·','a':{'b':1,'a':False}}),b'{"a":{"a":false,"b":1},"z":"\\u00b7"}\n')
        with self.assertRaises(ValueError):canonical({'x':float('nan')})

    def test_normalized_generation_has_no_synthetic_fill(self):
        a=seal({'common_watermark':'2020-01-02T00:00:00Z'})
        with patch('truth_spine_adapters.read_document',return_value=[]) as read:
            g,events=lineage.historical_generation([{'kind':'research','store_id':'research:empty','sha256':'1'*64}],a,'2'*64)
        self.assertEqual(events,[]);self.assertEqual(g['watermark']['count'],0)
        self.assertEqual(g['files'][0]['records'],0);read.assert_called_once()


class ExecutorDependencyTests(unittest.TestCase):
    def documents(self):
        rows=[{'identity':'synthetic-request','ticker':'SYNTHETIC','endpoint':'SYNTHETIC','window':'CLOSED'}]
        identity=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        prefix='executor/sessions/synthetic/'
        evidence={'synthetic':True};raw=canonical(evidence)
        return {
            'executor/selected-session.json':seal({'schema':'iios-operational-market-session-selector-v4','selected_root':'sessions/synthetic','plan_identity':identity}),
            prefix+'executor-state.json':seal({'schema_version':'iios-operational-market-executor-v1','plan_identity':identity,'requests':{'synthetic-request':{'lifecycle':'CONFIRMED'}}}),
            prefix+'request-plan.json':seal({'schema_version':'iios-operational-market-request-plan-v1','plan_identity':identity,'rows':rows}),
            prefix+'receipts/synthetic-request.json':seal({'request_identity':'synthetic-request','ticker':'SYNTHETIC','endpoint':'SYNTHETIC',
                'window':'CLOSED','status':'CONFIRMED','evidence_hash':hashlib.sha256(raw).hexdigest(),'response_bytes':len(raw)}),
            prefix+'evidence/synthetic-request.json':evidence}

    def pins(self,docs):
        root=retained_root('executor-dependencies');result={}
        for i,(target,doc) in enumerate(docs.items()):
            p=root/(str(i)+'.json');p.write_bytes(canonical(doc));result[target]=pin(p)
        return result

    def test_complete_independently_pinned_graph(self):
        docs=self.documents();result=lineage.verify_executor_inputs(self.pins(docs))
        self.assertEqual(set(result['files']),set(docs))

    def test_each_missing_dependency_and_extra_orphan_rejected(self):
        for target in self.documents():
            docs=self.documents();del docs[target]
            with self.assertRaises(ValueError):lineage.verify_executor_inputs(self.pins(docs))
        docs=self.documents();docs['executor/orphan.json']=seal({'schema':'ORPHAN'})
        with self.assertRaisesRegex(ValueError,'EXTRA_UNBOUND'):lineage.verify_executor_inputs(self.pins(docs))

    def test_resealed_receipt_with_wrong_parent_and_unresolved_parent_rejected(self):
        for field,value in [('request_identity','substituted'),('evidence_hash','0'*64),('ticker','OTHER')]:
            docs=self.documents();target='executor/sessions/synthetic/receipts/synthetic-request.json'
            docs[target]=seal({**docs[target],field:value})
            with self.assertRaises(ValueError):lineage.verify_executor_inputs(self.pins(docs))
        docs=self.documents();target='executor/selected-session.json'
        docs[target]=seal({**docs[target],'supersession_hash':'f'*64})
        with self.assertRaisesRegex(ValueError,'UNRESOLVED_PARENT'):lineage.verify_executor_inputs(self.pins(docs))
