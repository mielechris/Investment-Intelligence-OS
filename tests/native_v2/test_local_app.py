import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'BACK END/backend'))
from iios_qualification_v2 import native,runtime
from iios_qualification_v2.state import AUTHORITY,Store
from iios_qualification_v2.cli import execute

ROOT=Path(__file__).resolve().parents[2]

class LocalAppTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.root.chmod(0o700)
    def tearDown(self):
        for path in self.root.rglob('*'):
            if path.is_dir() and not path.is_symlink():path.chmod(0o700)
        self.temp.cleanup()
    def host(self,home):
        bundle=home/'Applications/IIOS Native Qualification.app';exe=bundle/'Contents/MacOS/IIOSNativeQualification'
        exe.parent.mkdir(parents=True);exe.write_bytes(b'app');exe.chmod(0o700)
        for path in (bundle,bundle/'Contents',bundle/'Contents/MacOS'):path.chmod(0o700)
        return {'schema':4,'launch_mode':'local_app','repository':'mielechris/Investment-Intelligence-OS',
                'commit':'a'*40,'branch':'feature/iios-native-qualification-v2','inventory_sha256':'b'*64,
                'app_bundle':str(bundle),'app_executable':str(exe),'app_executable_sha256':'c'*64,
                'app_identifier':'com.miele.iios-native-qualification','app_cdhash':'d'*40,
                'signing_method':'adhoc','hardware_uuid':'00000000-0000-0000-0000-000000000000','uid':os.getuid()}
    def test_local_host_binds_signed_direct_parent_and_hardware(self):
        host=self.host(self.root);exe=host['app_executable']
        verify=SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        describe=SimpleNamespace(returncode=0,stdout='',stderr='Identifier=com.miele.iios-native-qualification\nCDHash='+('d'*40)+'\nSignature=adhoc\n')
        parent=SimpleNamespace(executable=exe,executable_hash='c'*64)
        ioreg='"IOPlatformUUID" = "00000000-0000-0000-0000-000000000000"\n'
        with patch.object(native.Path,'home',return_value=self.root),patch.object(native,'file_hash',return_value='c'*64),\
             patch.object(native.subprocess,'run',side_effect=[verify,describe]),\
             patch('truth_spine_process_identity.inspect_macos',return_value=parent),patch.object(native,'command',return_value=ioreg):
            issuer,source=native.local_selected_host(host)
        self.assertEqual(issuer['launch_mode'],'local_app');self.assertEqual(source['commit'],'a'*40)
    def test_local_host_rejects_substituted_parent(self):
        host=self.host(self.root);verify=SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        describe=SimpleNamespace(returncode=0,stdout='',stderr='Identifier=com.miele.iios-native-qualification\nCDHash='+('d'*40)+'\nSignature=adhoc\n')
        parent=SimpleNamespace(executable='/tmp/fake',executable_hash='c'*64)
        with patch.object(native.Path,'home',return_value=self.root),patch.object(native,'file_hash',return_value='c'*64),\
             patch.object(native.subprocess,'run',side_effect=[verify,describe]),patch('truth_spine_process_identity.inspect_macos',return_value=parent):
            with self.assertRaisesRegex(ValueError,'PARENT'):native.local_selected_host(host)
    def test_local_source_binding_requires_exact_branch(self):
        expected={'repository':'mielechris/Investment-Intelligence-OS','commit':'a'*40,
                  'branch':'feature/iios-native-qualification-v2','inventory_sha256':'b'*64}
        identity={'commit':'a'*40,'inventory':[],'inventory_sha256':'b'*64}
        with patch.object(runtime,'source_identity',return_value=identity),patch.object(runtime,'command',side_effect=['wrong\n']):
            with self.assertRaisesRegex(ValueError,'BRANCH'):runtime.source_binding_local(self.root,expected)
    def test_stage_status_is_ordered_and_failure_is_exported(self):
        calls=[]
        def fail():raise ValueError('CONTROLLED')
        from iios_qualification_v2.state import STAGES
        stages={name:(fail if name=='ownership' else lambda:{'verified':True}) for name in STAGES[:-1]}
        result=execute(Store(self.root/'state'),stages,source='s',boot='b',resume=False,
                       issuer={'launch_mode':'local_app'},evidence=self.root/'evidence',status=lambda a,b:calls.append((a,b)))
        self.assertEqual(result['status'],'RED');self.assertTrue(result['export'])
        self.assertIn(('ownership','FAILED'),calls);self.assertEqual(result['authority'],AUTHORITY)
    def test_native_ui_has_fixed_command_and_only_confirmation_choices(self):
        text=(ROOT/'native-app/IIOSNativeQualification.m.in').read_text()
        for value in ('@"Run Qualification"','@"Cancel"','@"--profile",@"observation"','provider_requests','Open Evidence',
                      '[value[@"inventory_sha256"] isEqual:SourceInventory]'):
            self.assertIn(value,text)
        for forbidden in ('NSSearchField','NSOpenPanel','shell -c','/bin/zsh','system('):
            self.assertNotIn(forbidden,text)
    def test_builder_is_adhoc_and_never_queries_keychain(self):
        text=(ROOT/'scripts/build-iios-native-app.py').read_text()
        self.assertIn("'--sign','-'",text);self.assertIn("'--options','runtime'",text)
        self.assertGreaterEqual(text.count("'--verify','--deep','--strict','--all-architectures'"),2)
        self.assertIn('SELECTED_HOST_EXCLUSIVE',text)
        self.assertIn("bound=binding();qualification=contained",text)
        self.assertNotIn('/usr/bin/security',text);self.assertNotIn('find-identity',text)

if __name__=='__main__':unittest.main()
