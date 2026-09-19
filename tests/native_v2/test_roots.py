import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from iios_qualification_v2 import roots
from iios_qualification_v2.state import Store, decode, export

class DurableRootsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.parent=Path(self.temp.name);self.root=self.parent/'IIOS'
        self.mock=patch.object(roots,'expected_root',return_value=self.root);self.mock.start()
    def tearDown(self):
        self.mock.stop()
        for p in self.parent.rglob('*'):
            if p.is_dir() and not p.is_symlink():p.chmod(0o700)
        self.temp.cleanup()
    def test_exact_enrollment_and_child_modes(self):
        b=roots.binding(initialize=True);self.assertEqual(b,roots.binding())
        self.assertEqual(set(b['directories']),set(roots.CHILDREN))
    def test_no_silent_adoption(self):
        self.root.mkdir(mode=0o700)
        with self.assertRaises(FileExistsError):roots.binding(initialize=True)
        with self.assertRaises(FileNotFoundError):roots.binding()
    def test_symlink_rejected(self):
        roots.binding(initialize=True);p=self.root/'runtime';p.rename(self.root/'old');p.symlink_to(self.root/'old')
        with self.assertRaisesRegex(ValueError,'ALIAS'):roots.binding()
    def test_writable_child_rejected_without_chmod(self):
        roots.binding(initialize=True);p=self.root/'runtime';p.chmod(0o755)
        with self.assertRaisesRegex(ValueError,'OWNER_MODE'):roots.binding()
        self.assertEqual(p.stat().st_mode&0o777,0o755)
    def test_substituted_child_rejected(self):
        roots.binding(initialize=True);p=self.root/'runtime';p.rename(self.root/'old');p.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError,'IDENTITY'):roots.binding()
    def test_wrong_uid_rejected(self):
        roots.binding(initialize=True)
        with patch.object(roots.os,'getuid',return_value=os.getuid()+1):
            with self.assertRaisesRegex(ValueError,'OWNER_MODE'):roots.binding()
    def test_escape_rejected(self):
        b=roots.binding(initialize=True)
        for p in (self.parent/'outside',self.root/'runtime/../escape'):
            with self.assertRaisesRegex(ValueError,'ESCAPE'):roots.contained(p,b)
    def test_checkpoint_and_export_bind_root(self):
        b=roots.binding(initialize=True);s=Store(roots.contained(self.root/'qualification/state',b),root_binding=b)
        s.begin('source','boot',resume=False)
        self.assertEqual(s.load()[0]['data']['root_binding'],b)
        out=Path(export(s,self.root/'evidence',{'native_qualified':False}))
        self.assertEqual(decode((out/'manifest.json').read_bytes())['root_binding'],b)
