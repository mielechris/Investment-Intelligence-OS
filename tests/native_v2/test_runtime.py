import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'BACK END/backend'))
from iios_qualification_v2.runtime import *

class RuntimeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def wheel(self, extras=None):
        data={'sample.py':b'x=1\n',**(extras or {})};record='sample-1.dist-info/RECORD';out=io.StringIO();w=csv.writer(out)
        for n,b in data.items():w.writerow([n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).rstrip(b'=').decode(),len(b)])
        w.writerow([record,'','']);data[record]=out.getvalue().encode();p=self.root/'sample-1-py3-none-any.whl'
        with zipfile.ZipFile(p,'w') as z:
            for n,b in data.items():z.writestr(n,b)
        return p,{'filename':p.name,'size':p.stat().st_size,'sha256':file_hash(p)}
    def test_record_hashes_pass(self):p,pin=self.wheel();verify_wheel(p,pin)
    def test_wheel_hash_reject(self):
        p,pin=self.wheel();pin['sha256']='0'*64
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_traversal_reject(self):
        p,pin=self.wheel({'../escape':b'x'})
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_site_hooks_reject(self):
        p,pin=self.wheel({'hook.pth':b'import bad'})
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_wrong_platform_reject(self):
        p,pin=self.wheel();pin['filename']='sample-1-cp314-cp314-win_amd64.whl'
        with self.assertRaises(ValueError):verify_wheel(p,pin)
    def test_lock_exact_and_artifact_closure(self):
        lock=self.root/'lock';lock.write_text('sample==1\n');pins=self.root/'pins';value={'schema':2,'lock_sha256':file_hash(lock),'wheels':[{'name':'sample','version':'1','filename':'sample-1-py3-none-any.whl','size':1,'sha256':'a'*64}]};pins.write_text(json.dumps(value));lock_binding(lock,pins)
        lock.write_text('sample>=1\n')
        with self.assertRaises(ValueError):lock_binding(lock,pins)
    def test_inventory_detects_added_file(self):
        p=self.root/'x';p.write_text('x');snapshot=environment_tree(self.root);(self.root/'added').write_text('y')
        with self.assertRaises(ValueError):verify_environment_tree(self.root,snapshot)
    def test_inventory_rejects_escape_symlink(self):
        (self.root/'link').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):environment_tree(self.root)
    def test_no_package_network_or_install_into_system(self):
        import inspect
        text=inspect.getsource(environment)
        for flag in ('--no-index','--require-hashes','--no-deps','--only-binary=:all:'):self.assertIn(flag,text)
        self.assertNotIn('sudo',text)
    def test_unresolved_native_rpath_fails(self):
        with patch('iios_qualification_v2.runtime.command',side_effect=['x:\n\t@rpath/missing.dylib (compatibility version 1)\n','']):
            with self.assertRaisesRegex(ValueError,'RPATH'):native_dependencies(self.root/'image.so',self.root)
    def test_foreign_native_dependency_fails(self):
        with patch('iios_qualification_v2.runtime.command',side_effect=['x:\n\t/etc/passwd (compatibility version 1)\n','']):
            with self.assertRaisesRegex(ValueError,'ESCAPE'):native_dependencies(self.root/'image.so',self.root)
