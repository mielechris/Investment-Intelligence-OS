import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
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
    def test_source_binding_requires_commit_inventory_origin_and_detached_head(self):
        expected={'repository':'mielechris/Investment-Intelligence-OS','commit':'a'*40,'inventory_sha256':'b'*64}
        identity={'commit':'a'*40,'inventory':[{'path':'x','sha256':'c'*64,'bytes':1,'mode':420}],'inventory_sha256':'b'*64}
        with patch('iios_qualification_v2.runtime.source_identity',return_value=identity),patch('iios_qualification_v2.runtime.command',side_effect=['https://github.com/mielechris/Investment-Intelligence-OS.git\n','HEAD\n']):
            self.assertEqual(source_binding(self.root,expected)['repository'],expected['repository'])
        changed=dict(expected,commit='d'*40)
        with patch('iios_qualification_v2.runtime.source_identity',return_value=identity):
            with self.assertRaisesRegex(ValueError,'MISMATCH'):source_binding(self.root,changed)
    def test_source_identity_accepts_owner_only_executable_mode(self):
        script=self.root/'script';script.write_text('#!/bin/sh\n');script.chmod(0o700)
        staged='100755 '+'a'*40+' 0\tscript\0'
        with patch('iios_qualification_v2.runtime.command',side_effect=['','a'*40+'\n',staged]):
            value=source_identity(self.root)
        self.assertEqual(value['inventory'][0]['mode'],0o755)

    def codesign_success(self):
        return [SimpleNamespace(returncode=0,stdout=b'',stderr=b''),
                SimpleNamespace(returncode=0,stdout=b'',stderr=b'TeamIdentifier=BMM5U3QVKW\n')]

    def test_vendor_signature_targets_are_fixed_and_psf_bound(self):
        for target in ('launcher','app_image','framework_library'):
            with self.subTest(target=target),patch('iios_qualification_v2.runtime.subprocess.run',side_effect=self.codesign_success()) as run:
                receipt=codesign_vendor_target('/fixed/vendor/image',target=target,resolved='FRAMEWORK_3_14')
            self.assertEqual(receipt,{'target':target,'resolved':'FRAMEWORK_3_14','signer':'MATCHED'})
            self.assertIn('-R='+VENDOR_REQUIREMENT,run.call_args_list[0].args[0])
            self.assertEqual(run.call_args_list[1].args[0][:3],['/usr/bin/codesign','-d','--verbose=4'])

    def test_vendor_codesign_nonzero_exit_is_sanitized(self):
        result=SimpleNamespace(returncode=1,stdout=b'',stderr=b'raw diagnostic')
        with patch('iios_qualification_v2.runtime.subprocess.run',return_value=result):
            with self.assertRaisesRegex(ValueError,'target=launcher;resolved=FRAMEWORK_3_14;action=verify;outcome=NONZERO_EXIT;exit=EXIT_NONZERO;stderr=TEXT;stderr_sha256=[0-9a-f]{64};signer=NOT_EVALUATED'):
                codesign_vendor_target('/fixed/vendor/image',target='launcher',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_timeout_is_sanitized(self):
        timeout=subprocess.TimeoutExpired(['/usr/bin/codesign'],10,stderr=b'late')
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=timeout):
            with self.assertRaisesRegex(ValueError,'outcome=TIMEOUT;exit=NOT_AVAILABLE;stderr=TEXT;stderr_sha256=[0-9a-f]{64}'):
                codesign_vendor_target('/fixed/vendor/image',target='launcher',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_malformed_output_is_sanitized(self):
        results=[SimpleNamespace(returncode=0,stdout=b'',stderr=b''),SimpleNamespace(returncode=0,stdout=b'',stderr=b'no team')]
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=results):
            with self.assertRaisesRegex(ValueError,'action=describe;outcome=MALFORMED_OUTPUT;exit=EXIT_ZERO;stderr=TEXT;stderr_sha256=[0-9a-f]{64};signer=MALFORMED'):
                codesign_vendor_target('/fixed/vendor/image',target='app_image',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_wrong_signer_is_sanitized(self):
        results=[SimpleNamespace(returncode=0,stdout=b'',stderr=b''),SimpleNamespace(returncode=0,stdout=b'',stderr=b'TeamIdentifier=WRONG\n')]
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=results):
            with self.assertRaisesRegex(ValueError,'outcome=WRONG_SIGNER;exit=EXIT_ZERO;.*signer=MISMATCH'):
                codesign_vendor_target('/fixed/vendor/image',target='framework_library',resolved='FRAMEWORK_3_14')

    def test_vendor_codesign_tool_launch_failure_is_sanitized(self):
        with patch('iios_qualification_v2.runtime.subprocess.run',side_effect=OSError(2,'missing')):
            with self.assertRaisesRegex(ValueError,'outcome=TOOL_LAUNCH_FAILURE;exit=NOT_AVAILABLE;stderr=TEXT;stderr_sha256=[0-9a-f]{64}'):
                codesign_vendor_target('/fixed/vendor/image',target='launcher',resolved='FRAMEWORK_3_14')

    def test_vendor_missing_target_is_sanitized(self):
        config={'vendor_python':'/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14','python_version':'3.14.7'}
        with patch.object(Path,'resolve',side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError,'target=launcher;resolved=MISSING;action=verify;outcome=MISSING_TARGET;exit=NOT_RUN;stderr=EMPTY;stderr_sha256=NONE;signer=NOT_EVALUATED'):
                verify_vendor(config)
