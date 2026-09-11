"""Strict 3.8D boundary tests: individually registered, retained synthetic files."""
import json
import os
from pathlib import Path
import sqlite3
import unittest
import ast
from contextvars import Context
from dataclasses import replace
from unittest.mock import patch

import truth_spine_adapters as adapters
from truth_spine_contract import canonical, seal
from truth_spine_lineage import copy_pinned, file_hash, working_sqlite_receipt, write_new
from test_truth_spine_lineage import retained_root, pin


class StrictSQLiteTests(unittest.TestCase):
    def test_legacy_missing_schema_remains_legacy_but_clean_run_cannot_downgrade(self):
        from truth_spine_integration import historical_topology
        self.assertFalse(historical_topology({'event_ledger_path':self.event.path}))
        for key in ('root','event_ledger_path'):
            with self.assertRaisesRegex(ValueError,'STRICT_TOPOLOGY_REQUIRED'):
                historical_topology({key:'/private/tmp/iios-truth-spine-3-acceptance-sb38d-clean-synthetic/state/event.db'})
    def test_explicit_capability_survives_absent_ambient_context(self):
        self.assertIsNone(adapters.active_sqlite_policy())
        cap=self.capabilities['L7_WORKING_COPY']
        db=adapters.connect_strict_sqlite(cap)
        try:self.assertIs(adapters.verify_strict_connection(db,cap),db)
        finally:db.close()

    def test_raw_legacy_connection_cannot_be_substituted(self):
        cap=self.capabilities['L7_WORKING_COPY']
        # Mock substitution before any SQLite open, preserving the native boundary.
        for replacement in (None,object()):
            with patch.object(adapters,'connect_strict_sqlite',return_value=replacement):
                with self.assertRaisesRegex(ValueError,'STRICT_CONNECTION_RESULT_REQUIRED'):
                    adapters.read_strict_ledger(adapters.source(Path(cap.path),'operational'),cap)
        with patch.object(adapters.sqlite3,'connect') as native:
            with self.assertRaises(ValueError):adapters.read_strict_ledger({},None)
            native.assert_not_called()

    def test_telemetry_requires_exact_three_role_target_set(self):
        caps=[*self.capabilities.values(),self.event]
        links=[]
        for cap in caps:
            db=adapters.connect_strict_sqlite(cap);links.append(db.telemetry);db.close()
        self.assertTrue(adapters.verify_sqlite_targets(caps,links))
        with self.assertRaisesRegex(ValueError,'SQLITE_TARGET_SET_MISMATCH'):
            adapters.verify_sqlite_targets(caps,links[:-1])
        with self.assertRaisesRegex(ValueError,'SQLITE_TARGET_SET_MISMATCH'):
            adapters.verify_sqlite_targets(caps[:-1],links)

    def test_strict_reader_call_graph_has_no_legacy_dispatch(self):
        source=Path(adapters.__file__).read_text();tree=ast.parse(source)
        functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
        pending=['read_strict_ledger'];seen=set()
        while pending:
            name=pending.pop()
            if name in seen:continue
            self.assertNotEqual(name,'read_ledger');seen.add(name)
            for node in ast.walk(functions[name]):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in functions:
                    pending.append(node.func.id)
        self.assertIn('connect_strict_sqlite',seen);self.assertIn('verify_strict_connection',seen)

    def setUp(self):
        self.root=retained_root('strict-sqlite')
        for name in ('state','admission','working-inputs'):(self.root/name).mkdir(mode=0o700)
        self.policy=adapters.SQLitePolicy(str(self.root),'1'*64,'2'*64,'synthetic',os.getpid(),
                                          os.environ['IIOS_SB38D_TEST_ROOT'])
        self.event=adapters.create_run_event_store(self.policy,'3'*64)
        with adapters.strict_sqlite_scope(self.policy):
            db=adapters.connect_strict_sqlite(self.event)
            try:
                db.execute('CREATE TABLE ledger_objects(object_id TEXT,object_type TEXT,payload_json TEXT,created_at TEXT)')
                db.execute('INSERT INTO ledger_objects VALUES (?,?,?,?)',
                           ('synthetic','case','{"classification":"HISTORICAL"}','2020-01-01T00:00:00Z'))
                db.commit()
            finally:db.close()
        self.copies={role:copy_pinned(pin(Path(self.event.path)),self.root,'working-inputs/'+name)
                     for role,name in [('L7_WORKING_COPY','l7.db'),('L8_WORKING_COPY','l8.db')]}
        expected=working_sqlite_receipt(self.policy,self.copies)
        self.capabilities={role:adapters.SQLiteCapability(role,row['canonical_path'],'ro-immutable',
            str(self.root/'admission/sqlite-working-copies.json'),expected,policy=self.policy) for role,row in self.copies.items()}

    def assertDenied(self,capability,policy=None):
        with adapters.strict_sqlite_scope(policy or self.policy):
            with self.assertRaises((ValueError,PermissionError,FileNotFoundError)):
                adapters.connect_strict_sqlite(capability)

    def test_valid_l7_and_l8_shared_adapter(self):
        with adapters.strict_sqlite_scope(self.policy):
            for role,kind in [('L7_WORKING_COPY','operational'),('L8_WORKING_COPY','historical')]:
                cap=self.capabilities[role]
                rows=adapters.read_strict_ledger(adapters.source(Path(cap.path),kind),capability=cap)
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['classification'],'HISTORICAL')

    def test_missing_capability_and_legacy_mode_rejected(self):
        self.assertDenied(None)
        with adapters.strict_sqlite_scope(self.policy):
            with self.assertRaisesRegex(PermissionError,'LEGACY_SQLITE_UNREACHABLE'):
                adapters.read_ledger({})
            with self.assertRaises(ValueError):
                adapters.read_strict_ledger({},capability={'mode':'LEGACY'})

    def test_unregistered_direct_sqlite_open_detected(self):
        with adapters.strict_sqlite_scope(self.policy):
            with self.assertRaisesRegex(PermissionError,'UNREGISTERED_SQLITE_CONNECTION'):
                sqlite3.connect(self.event.path)
            with self.assertRaisesRegex(PermissionError,'UNREGISTERED_SQLITE_CONNECTION'):
                sqlite3.Connection(self.event.path)

    def test_sb38d_path_cannot_select_legacy_without_a_policy(self):
        with self.assertRaisesRegex(PermissionError,'LEGACY_SQLITE_UNREACHABLE'):
            adapters.read_ledger({'path':'/private/tmp/iios-truth-spine-3-acceptance-sb38d-clean-synthetic/working-inputs/l7.db'})

    def test_process_policy_blocks_a_fresh_worker_context(self):
        with patch.object(adapters,'_process_policy',None):
            adapters.activate_strict_sqlite(self.policy)
            with self.assertRaisesRegex(PermissionError,'UNREGISTERED_SQLITE_CONNECTION'):
                Context().run(sqlite3.connect,self.event.path)
            with self.assertRaisesRegex(ValueError,'POLICY_REPLACEMENT'):
                adapters.activate_strict_sqlite(replace(self.policy,run_identity='f'*64))

    def test_preserved_permanent_and_arbitrary_tmp_paths_rejected_before_open(self):
        cap=self.capabilities['L7_WORKING_COPY']
        for path in ['/private/tmp/arbitrary.db',
                     '/private/tmp/iios-northstar-owner-snapshots-sb37-attempt2/l7/snapshot.db',
                     '/private/tmp/iios-northstar-owner-snapshots-sb37-attempt2/l8/snapshot.db',
                     '/Users/crm/Library/Application Support/IIOS/l7/ledger.db']:
            with patch.object(adapters.sqlite3,'connect',side_effect=AssertionError('UNAUTHORIZED_OPEN')):
                self.assertDenied(replace(cap,path=path))

    def test_unregistered_working_file_and_wrong_role_hash_root_receipt(self):
        cap=self.capabilities['L7_WORKING_COPY']
        other=self.root/'working-inputs/unregistered.db';other.write_bytes(b'UNREGISTERED')
        for bad in [replace(cap,path=str(other)),replace(cap,role='RUN_EVENT_STORE'),
                    replace(cap,role='UNKNOWN'),replace(cap,receipt_hash='0'*64),replace(cap,mode='rw')]:
            self.assertDenied(bad)
        wrong=replace(self.policy,run_identity='3'*64)
        self.assertDenied(cap,wrong)
        wrong_root=self.root/'another';wrong_root.mkdir()
        self.assertDenied(cap,replace(self.policy,root=str(wrong_root)))

    def forged_receipt(self,change,name):
        cap=self.capabilities['L7_WORKING_COPY']
        doc=json.loads(Path(cap.receipt_path).read_bytes());change(doc)
        target='admission/'+name+'.json';expected=write_new(self.root,target,canonical(seal(doc)))
        return replace(cap,receipt_path=str(self.root/target),receipt_hash=expected)

    def test_valid_self_hash_wrong_inode_hash_and_parent_rejected(self):
        for field,value in [('inode',0),('copied_hash','0'*64),('source_hash','0'*64),('role','L8_WORKING_COPY')]:
            cap=self.forged_receipt(lambda d:d['databases'][0].update({field:value}),field)
            self.assertDenied(cap)
        self.assertDenied(self.forged_receipt(lambda d:d.update(package_identity='f'*64),'parent'))

    def test_symlink_and_hardlink_substitution_rejected(self):
        cap=self.capabilities['L7_WORKING_COPY']
        link=self.root/'working-inputs/link.db';link.symlink_to(cap.path)
        self.assertDenied(replace(cap,path=str(link)))
        hard=self.root/'working-inputs/hard.db';os.link(cap.path,hard)
        self.assertDenied(cap)

    def test_event_existing_outside_state_and_alias_rejected(self):
        for target in ['state/canonical-events.db','working-inputs/other.db','../outside.db']:
            with self.assertRaises(ValueError):adapters.create_run_event_store(self.policy,'3'*64,target)
        self.assertDenied(replace(self.event,path=self.capabilities['L7_WORKING_COPY'].path))
        self.assertDenied(replace(self.event,parent_package_hash='f'*64))

    def test_event_read_write_attach_and_sidecar_escape(self):
        with adapters.strict_sqlite_scope(self.policy):
            db=adapters.connect_strict_sqlite(self.event)
            try:
                self.assertEqual(db.execute('SELECT count(*) FROM ledger_objects').fetchone(),(1,))
                with self.assertRaises(sqlite3.DatabaseError):db.execute("ATTACH DATABASE ':memory:' AS escape")
                with self.assertRaisesRegex(PermissionError,'SQLITE_EXTENSION_FORBIDDEN'):
                    adapters.sqlite_audit('sqlite3.enable_load_extension',(db,True))
            finally:db.close()
        target=self.root/'external';target.write_bytes(b'NOT_A_SIDECAR')
        Path(self.event.path+'-wal').symlink_to(target)
        self.assertDenied(self.event)

    def test_synthetic_policy_requires_exact_authorized_test_root(self):
        with self.assertRaises(ValueError):replace(self.policy,synthetic_root='/private/tmp').validate()

    def test_legacy_call_cannot_execute_inside_strict_scope(self):
        cap=self.capabilities['L7_WORKING_COPY'];spec=adapters.source(Path(cap.path),'operational')
        # Legacy dispatch remains available outside 3.8D; mock its connection so
        # this proof creates no unregistered database or external process.
        with patch.object(adapters.sqlite3,'connect',side_effect=RuntimeError('LEGACY_DISPATCH')):
            with self.assertRaisesRegex(RuntimeError,'LEGACY_DISPATCH'):adapters.read_ledger(spec)
        with adapters.strict_sqlite_scope(self.policy):
            with self.assertRaisesRegex(PermissionError,'LEGACY_SQLITE_UNREACHABLE'):
                adapters.read_ledger(spec,mode=adapters.LEGACY_MODE)

    def test_reachable_sqlite_calls_are_explicitly_inventoried(self):
        root=Path(__file__).resolve().parents[2]
        files=['BACK END/backend/truth_spine_adapters.py','BACK END/backend/truth_spine_lineage.py',
               'BACK END/backend/truth_spine_integration.py','BACK END/backend/truth_spine_integration_service.py',
               'scripts/truth_spine_integration_acceptance.py','scripts/truth_spine_integration_runner.py']
        calls=[]
        for name in files:
            tree=ast.parse((root/name).read_text())
            for fn in ast.walk(tree):
                if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
                for node in ast.walk(fn):
                    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
                        if node.func.value.id=='sqlite3' and node.func.attr in {'connect','Connection'}:
                            calls.append((name,fn.name,node.func.attr))
        self.assertEqual(sorted(calls),sorted([
            ('BACK END/backend/truth_spine_adapters.py','connect_strict_sqlite','connect'),
            ('BACK END/backend/truth_spine_adapters.py','read_ledger','connect'),
            ('BACK END/backend/truth_spine_integration.py','connect_event','connect'),
            ('BACK END/backend/truth_spine_integration.py','snapshot','connect')]))

    def test_legacy_integration_branch_cannot_open_under_strict_policy(self):
        from truth_spine_integration import connect_event
        with adapters.strict_sqlite_scope(self.policy):
            with self.assertRaisesRegex(PermissionError,'UNREGISTERED_SQLITE_CONNECTION'):
                connect_event({'schema':'iios-readonly-topology-v2','event_ledger_path':self.event.path})

    def test_legacy_generation_store_is_blocked_in_strict_process(self):
        from truth_spine_generations import GenerationStore
        store=object.__new__(GenerationStore)
        store.root=self.root;store.path=Path(self.event.path);store.readonly=True
        with adapters.strict_sqlite_scope(self.policy):
            with self.assertRaisesRegex(PermissionError,'UNREGISTERED_SQLITE_CONNECTION'):
                store.connect(readonly=True)

    def test_readonly_event_role_cannot_write_and_other_role_cannot_own_writer(self):
        with adapters.strict_sqlite_scope(self.policy):
            db=adapters.connect_strict_sqlite(replace(self.event,mode='ro'))
            try:
                with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM ledger_objects')
                with self.assertRaises(sqlite3.DatabaseError):db.execute('PRAGMA temp_store=FILE')
            finally:db.close()
        with self.assertRaises(ValueError):replace(self.policy,owner_pid=os.getpid()+1).validate()
