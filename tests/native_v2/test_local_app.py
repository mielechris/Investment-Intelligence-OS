import io
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
from iios_qualification_v2 import native,runtime,preflight_evidence
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
        manifest=home/'Library/IIOS/qualification/local-app-aaaaaaa-01/APP-MANIFEST.json';manifest.parent.mkdir(parents=True);manifest.write_bytes(b'm');manifest.chmod(0o400)
        for path in (home/'Library',home/'Library/IIOS',home/'Library/IIOS/qualification',manifest.parent):path.chmod(0o700)
        return {'schema':4,'launch_mode':'local_app','repository':'mielechris/Investment-Intelligence-OS',
                'commit':'a'*40,'branch':'feature/iios-native-qualification-v2','inventory_sha256':'b'*64,
                'app_bundle':str(bundle),'app_executable':str(exe),'app_executable_sha256':'c'*64,
                'app_identifier':'com.miele.iios-native-qualification','app_cdhash':'d'*40,
                'signing_method':'adhoc','app_manifest':str(manifest),'app_manifest_sha256':'c'*64,
                'hardware_uuid':'00000000-0000-0000-0000-000000000000','uid':os.getuid()}
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
                       issuer={'launch_mode':'local_app'},evidence=self.root/'evidence',status=lambda a,b:calls.append((a,b)),
                       controller=lambda:{'test_observation':True})
        self.assertEqual(result['status'],'RED');self.assertTrue(result['export'])
        self.assertIn(('ownership','FAILED'),calls);self.assertEqual(result['authority'],AUTHORITY)

    def test_closed_denied_child_pipe_is_detached_before_failure_export(self):
        class BufferedPipe:
            def __init__(self):self.writes=[];self.closed=False
            def write(self,value):self.writes.append(value)
            def flush(self):raise BrokenPipeError(32,'Broken pipe')
            def close(self):self.closed=True;raise BrokenPipeError(32,'Broken pipe')
        read_fd,write_fd=os.pipe();os.close(read_fd)
        pipe=os.fdopen(write_fd,'wb');pipe.write(b'STOP n\n');child=SimpleNamespace(stdin=pipe)
        native.close_child_stdin(child)
        self.assertTrue(pipe.closed);self.assertIsNone(child.stdin)
        engine=native.Native(self.root,self.root,None,{},'boot',float('inf'))
        entry={'child':SimpleNamespace(stdin=BufferedPipe()),'config':{'nonce':'n'}}
        with self.assertRaises(BrokenPipeError):engine.stop(entry)
        self.assertIsNone(entry['child'].stdin)

    def test_closed_denied_child_pipe_cannot_block_failure_receipt_export(self):
        pipe=SimpleNamespace(write=lambda _:None,flush=lambda:(_ for _ in ()).throw(BrokenPipeError(32,'Broken pipe')),
                             close=lambda:(_ for _ in ()).throw(BrokenPipeError(32,'Broken pipe')))
        engine=native.Native(self.root,self.root,None,{},'boot',float('inf'))
        entry={'child':SimpleNamespace(stdin=pipe),'config':{'nonce':'n'}}
        def confinement():raise ValueError('CONTROLLED_DENIAL')
        def cleanup():
            with self.assertRaises(BrokenPipeError):engine.stop(entry)
            self.assertIsNone(entry['child'].stdin)
            raise ValueError('CLEANUP_FAILED:NONCOOPERATIVE_CLEANUP')
        from iios_qualification_v2.state import STAGES
        stages={name:(confinement if name=='confinement' else cleanup if name=='cleanup' else lambda:{'verified':True}) for name in STAGES[:-1]}
        result=execute(Store(self.root/'receipt-state'),stages,source='s',boot='b',resume=False,
                       issuer={'launch_mode':'local_app'},evidence=self.root/'evidence',controller=lambda:{'fixture':True})
        self.assertEqual(result['status'],'RED');self.assertTrue(result['export'])
        self.assertTrue((Path(result['export'])/'manifest.json').is_file())

    def test_confinement_profile_uses_only_parser_accepted_tcp_port_selectors(self):
        value=native.profile(self.root,self.root,self.root,self.root/'python',38493)
        self.assertIn('(allow network-inbound (local tcp "*:38493"))',value)
        self.assertIn('(allow network-outbound (remote tcp "*:38493"))',value)
        self.assertNotIn('local ip "127.0.0.1:',value);self.assertNotIn('remote ip "127.0.0.1:',value)

    def test_pre_ready_sandbox_failure_is_sanitized_and_bound_to_failure_export(self):
        child=SimpleNamespace(poll=lambda:65,stderr=io.BytesIO(b'profile diagnostic'),stdin=None)
        error=native.ChildReplyError('EOF')
        engine=native.Native(self.root,self.root,None,{},'boot',float('inf'))
        detail=engine.protocol_evidence(child,error,expected='READY',confined=True)
        self.assertEqual(detail['child_exit_category'],'EXIT_65')
        self.assertEqual(detail['expected_reply_category'],'READY')
        self.assertEqual(detail['observed_reply_category'],'EOF')
        self.assertEqual(detail['denial_stage'],'PRE_READY_SANDBOX_ADMISSION')
        self.assertNotIn('profile diagnostic',json.dumps(detail))
        error.evidence=detail
        def confinement():raise error
        from iios_qualification_v2.state import STAGES
        stages={name:(confinement if name=='confinement' else lambda:{'verified':True}) for name in STAGES[:-1]}
        result=execute(Store(self.root/'protocol-state'),stages,source='s',boot='b',resume=False,
                       issuer={'launch_mode':'local_app'},evidence=self.root/'evidence',controller=lambda:{'fixture':True})
        self.assertEqual(result['failure']['protocol'],detail)
        exported=json.loads((Path(result['export'])/'summary.json').read_text())
        self.assertEqual(exported['failure']['protocol'],detail)

    def test_reaped_pre_ready_child_keeps_cleanup_not_established(self):
        error=native.ChildCleanupError('REAPED_AFTER_PRE_READY_FAILURE',{'child_exit_category':'EXIT_65'})
        self.assertEqual(error.evidence['classification'],'REAPED_AFTER_PRE_READY_FAILURE')
        self.assertEqual(error.evidence['protocol']['child_exit_category'],'EXIT_65')
    def test_native_ui_has_fixed_command_and_only_confirmation_choices(self):
        text=(ROOT/'native-app/IIOSNativeQualification.m.in').read_text()
        for value in ('@"Run Qualification"','@"Cancel"','@"--profile",@"observation"','provider_requests','Open Evidence',
                      '[value[@"inventory_sha256"] isEqual:SourceInventory]','EVIDENCE_EXPORT_UNAVAILABLE','preflight_evidence',
                      'runtime_rebuild_required','@"--rebuild-runtime"','Runtime recovery:'):
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

    def test_every_admitted_preflight_failure_exports_a_sealed_sanitized_receipt(self):
        root=self.root/'preflight';root.mkdir();root.chmod(0o700)
        with patch.object(preflight_evidence,'contained',return_value=root):
            writer=preflight_evidence.Writer(self.root,{'root':'unused'},started=1)
            for predicate in ('DIRTY_SOURCE','LOCAL_APP_EXECUTABLE_HASH','LOCAL_SOURCE_BINDING_MISMATCH','LOCAL_HOST_SCHEMA',
                              'LOCAL_SOURCE_BRANCH','LOCAL_APP_MANIFEST_HASH','LOCAL_APP_OWNER_MODE','LOCAL_APP_PARENT'):
                result=writer.write(error=ValueError(predicate),stage='ADMISSION',parents={'source':{'commit':'a'*40}},
                                    expected={'category':'EXPECTED'},observed={'category':'OBSERVED'})
                receipt=Path(result['export'])/'receipt.json';row=json.loads(receipt.read_text())
                self.assertEqual(row['predicate'],predicate);self.assertEqual(row['provider_requests'],0)
                self.assertEqual(row['authority'],AUTHORITY);self.assertEqual(Path(result['export']).stat().st_mode&0o777,0o500)

    def test_unsafe_preflight_root_and_write_failure_never_claim_a_receipt(self):
        with patch.object(preflight_evidence,'contained',side_effect=ValueError('DURABLE_ALIAS')):
            with self.assertRaisesRegex(preflight_evidence.EvidenceUnavailable,'EVIDENCE_EXPORT_UNAVAILABLE'):
                preflight_evidence.Writer(self.root,{'root':'unused'})
        root=self.root/'preflight';root.mkdir();root.chmod(0o700)
        with patch.object(preflight_evidence,'contained',return_value=root),patch.object(preflight_evidence,'publish',side_effect=OSError(28,'full')):
            writer=preflight_evidence.Writer(self.root,{'root':'unused'})
            with self.assertRaisesRegex(preflight_evidence.EvidenceUnavailable,'EVIDENCE_EXPORT_UNAVAILABLE'):
                writer.write(error=ValueError('WRITE_FAILURE'),stage='ADMISSION',parents={},expected={},observed={})

if __name__=='__main__':unittest.main()
