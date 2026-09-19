import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'BACK END/backend'))
from iios_qualification_v2.state import *

class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.root.chmod(0o700)
    def tearDown(self):
        for p in self.root.rglob('*'):
            if p.is_dir():p.chmod(0o700)
        self.temp.cleanup()
    def test_chain_resume_and_invalidation(self):
        s=Store(self.root/'state');s.begin('one','boot',resume=False);s.append('STAGE_FAILED',{'stage':'runtime'})
        with self.assertRaisesRegex(ValueError,'EXPLICIT_RESUME'):s.begin('two','boot',resume=False)
        row=s.begin('two','boot',resume=True);self.assertEqual(row['invalidates'],list(STAGES));self.assertEqual(len(s.load()),3)
    def test_tamper_fails(self):
        s=Store(self.root/'state');s.append('BEGIN',{});p=s.events/'00000000.json';p.chmod(0o600);p.write_text('{}');p.chmod(0o400)
        with self.assertRaises(ValueError):s.load()
    def test_sequence_gap_fails(self):
        s=Store(self.root/'state');s.append('BEGIN',{});(s.events/'00000000.json').rename(s.events/'00000001.json')
        with self.assertRaisesRegex(ValueError,'SEQUENCE'):s.load()
    def test_duplicate_json_key_fails(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):decode('{"a":1,"a":2}')
    def test_projection_not_authority(self):
        s=Store(self.root/'state');s.append('BEGIN',{});(s.root/'state.json').chmod(0o600);(s.root/'state.json').write_text('corrupt')
        self.assertEqual(len(s.load()),1)
    def test_symlink_root_rejected(self):
        link=self.root/'link';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):Store(link/'state')
    def test_owner_only_root_required(self):
        p=self.root/'bad';p.mkdir(mode=0o755);p.chmod(0o755)
        with self.assertRaises(ValueError):Store(p)
    def test_lock_exclusion(self):
        s=Store(self.root/'state')
        with s.locked():
            with self.assertRaises(BlockingIOError):
                with Store(s.root).locked():pass
    def test_reboot_exception_never_upgrades_cleanup(self):
        h={'boot':'old','cleanup':'NOT_ESTABLISHED'};v=historical_exception(h,'new')
        self.assertFalse(v['cleanup_upgraded']);self.assertEqual(h['cleanup'],'NOT_ESTABLISHED')
        with self.assertRaises(ValueError):historical_exception(h,'old')
    def test_export_is_closed_and_content_addressed(self):
        s=Store(self.root/'state');s.append('BEGIN',{});p=Path(export(s,self.root/'evidence',{'status':'OFFLINE_PASS'}));verify_export(p)
        with self.assertRaises(FileExistsError):export(s,self.root/'evidence',{})
        p.chmod(0o700);(p/'extra').write_text('x');p.chmod(0o500)
        with self.assertRaises(ValueError):verify_export(p)
    def test_export_hash_mutation(self):
        s=Store(self.root/'state');s.append('BEGIN',{});p=Path(export(s,self.root/'evidence',{}));f=p/'summary.json';f.chmod(0o600);f.write_text('{}');f.chmod(0o400)
        with self.assertRaises(ValueError):verify_export(p)
    def test_evidence_sanitizes_machine_identity_and_home(self):
        value={'runner_name':'secret-runner','hardware_uuid':'secret-uuid','uid':501,
               'device':42,'inode':99,'path':str(Path.home()/'Library/IIOS'),'authority':AUTHORITY}
        projected=sanitized(value)
        self.assertNotIn('runner_name',projected);self.assertNotIn('hardware_uuid',projected)
        self.assertNotIn('uid',projected);self.assertNotIn('device',projected);self.assertNotIn('inode',projected)
        self.assertEqual(projected['path'],'$USER_HOME/Library/IIOS');self.assertEqual(projected['authority'],AUTHORITY)
    def test_evidence_rejects_credential_patterns(self):
        with self.assertRaisesRegex(ValueError,'SECRET'):sanitized({'error':'Bearer credential'})
        with self.assertRaisesRegex(ValueError,'SECRET'):sanitized({'token=secret':False})
    def test_export_manifest_sanitizes_root_binding(self):
        s=Store(self.root/'state');s.append('BEGIN',{})
        p=Path(export(s,self.root/'evidence',{}))
        manifest=json.loads((p/'manifest.json').read_text())
        rendered=json.dumps(manifest,sort_keys=True)
        self.assertNotIn(str(Path.home()),rendered)
        self.assertNotIn('"device"',rendered);self.assertNotIn('"inode"',rendered);self.assertNotIn('"uid"',rendered)
