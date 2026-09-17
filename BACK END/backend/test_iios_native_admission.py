"""Offline contracts only; no native tools, inspectors or stage executors run."""
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from iios_native_conductor import *
from iios_native_admission import *
from iios_native_ownership import LaunchBinding
import test_iios_native_conductor as fixtures
manifest=fixtures.manifest


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
    def tearDown(self):self.temp.cleanup()
    def put(self,name,data):
        path=self.root/name;path.write_bytes(data);return str(path),hashlib.sha256(data).hexdigest()
    def binding(self):
        a,ah=self.put('launcher',b'launcher');b,bh=self.put('image',b'image');c,ch=self.put('script',b'script')
        return LaunchBinding(a,ah,b,bh,c,ch,(a,'-I','-B','-S',c),(b,'-I','-B','-S',c),4)
    def test_framework_image_distinct_from_launcher(self):
        binding=self.binding();before=binding.verify();binding.reverify(before)
    def test_swapped_hashes_rejected(self):
        from dataclasses import replace
        b=self.binding()
        with self.assertRaises(QualificationFailure):replace(b,launcher_hash=b.image_hash,image_hash=b.launcher_hash).verify()
    def test_changed_launcher_image_and_script_rejected(self):
        for name in ('launcher','image','script'):
            with self.subTest(name=name):
                b=self.binding();Path(getattr(b,name)).write_bytes(b'changed')
                with self.assertRaises(QualificationFailure):b.verify()
    def test_reordered_argv_rejected(self):
        from dataclasses import replace
        b=self.binding()
        with self.assertRaises(QualificationFailure):replace(b,observed_argv=(b.image,b.script,'-I','-B','-S')).verify()
    def test_symlink_rejected(self):
        from dataclasses import replace
        b=self.binding();link=self.root/'alias';link.symlink_to(b.launcher)
        with self.assertRaises(QualificationFailure):replace(b,launcher=str(link),command=(str(link),)+b.command[1:]).verify()
    def test_replacement_with_same_bytes_rejected(self):
        b=self.binding();before=b.verify();p=Path(b.script);copy_path=self.root/'replacement';copy_path.write_bytes(p.read_bytes());copy_path.replace(p)
        with self.assertRaises(QualificationFailure):b.reverify(before)
    def test_terminal_category_matrix(self):
        host={'system':'Darwin','release':'fixture','machine':'arm64','uid':1}
        self.assertTrue(terminal_categories('Apple_Terminal',[True]*3,False,host,host))
        for term,tty,marker,observed,predicate in (
            ('vscode',[True]*3,False,host,'TERMINAL_APPLICATION'),
            ('Apple_Terminal',[True]*3,True,host,'TERMINAL_FORBIDDEN_MARKERS'),
            ('Apple_Terminal',[True,False,True],False,host,'TERMINAL_TTY'),
            ('Apple_Terminal',[True]*3,False,{},'HOST_BINDING')):
            with self.subTest(predicate=predicate),self.assertRaises(QualificationFailure) as ctx:terminal_categories(term,tty,marker,observed,host)
            self.assertEqual(ctx.exception.detail['predicate'],predicate)
    def test_missing_all_four_native_adapters_is_blocked(self):
        m=manifest();rows=review_bindings(m)
        self.assertEqual([r['stage'] for r in rows if r['predicate']=='NATIVE_ADAPTER_BINDING_REQUIRED'],list(REQUIRED_NATIVE))
        with self.assertRaises(QualificationFailure):require_execution_ready(m)
    def test_malformed_adapter_is_blocked(self):
        m=manifest();m['stages'][4]['native_binding']={'command':['old-consumed-command']}
        self.assertEqual(review_bindings(m)[0]['predicate'],'NATIVE_ADAPTER_SCHEMA')
    def test_source_and_ci_binding(self):
        path,h=self.put('ci.json',json.dumps({'source':'a'*40,'status':'GREEN','artifact_hashes_verified':True,'native_execution':False}).encode())
        name,parent=self.put('source.py',b'fixture')
        m={'source':{'commit':'a'*40,'root':str(self.root),'inventory':[{'relative':'source.py','sha256':parent}]},'ci':{'commit':'a'*40,'path':path,'sha256':h},'inputs':[],'historical_records':[]}
        self.assertTrue(admit_source(m));m['source']['commit']='b'*40
        with self.assertRaises(QualificationFailure) as ctx:admit_source(m)
        self.assertEqual(ctx.exception.detail['predicate'],'CI_EXACT_COMMIT')
    def test_source_hash_mutation(self):
        path,h=self.put('input',b'old');Path(path).write_bytes(b'new')
        with self.assertRaises(QualificationFailure) as ctx:pin_file(path,h)
        self.assertEqual(ctx.exception.detail['predicate'],'INPUT_HASH')
    def test_detailed_inspection_denial(self):
        from iios_native_dispatcher import NativeContext
        context=NativeContext({},'a'*64,self.root);context.deadline=100
        def denied(pid,diagnostic):
            diagnostic({'query':'PS_START','failure':'INSPECTION_EXCEPTION'})
            raise PermissionError(errno.EACCES,'sensitive text')
        with patch('iios_native_dispatcher.clock',return_value=1),patch('truth_spine_process_identity.inspect_macos',side_effect=denied):
            with self.assertRaises(QualificationFailure) as ctx:context.inspect(35731)
        self.assertEqual(ctx.exception.detail['predicate'],'PS_START');self.assertEqual(ctx.exception.detail['errno_category'],'EACCES');self.assertNotIn('sensitive',str(ctx.exception.detail))
    def test_no_adapter_loading_before_admission(self):
        # Execution readiness fails before root creation or any adapter code load.
        from iios_native_dispatcher import run
        with patch('iios_native_dispatcher.fresh_root') as create:
            with self.assertRaises(QualificationFailure):run(manifest(),'a'*64)
        create.assert_not_called()


class AdditionalCoreTests(unittest.TestCase):
    setUp=fixtures.CoreTests.setUp
    tearDown=fixtures.CoreTests.tearDown
    receipt=fixtures.CoreTests.receipt
    adapter=fixtures.CoreTests.adapter
    engine=fixtures.CoreTests.engine
    prefix=fixtures.CoreTests.prefix
    def test_resume_reboot_rejected(self):
        j=self.prefix();r=self.engine(clock_identity=lambda:'OTHER_BOOT').run(resume=True,resume_tip=j.records[-1]['hash'])
        self.assertEqual(r['primary_failure']['predicate'],'RESUME_CLOCK_IDENTITY');self.assertEqual(self.calls,[])
    def test_cleanup_multiple_failures_retained(self):
        def clean(*a):
            first=QualificationFailure('CLEANUP','FIRST_CHILD','ABSENT','PRESENT')
            first.secondary_cleanup=[QualificationFailure('CLEANUP','SECOND_CHILD','ABSENT','DENIED',exception='PermissionError',errno_category='EPERM').detail]
            raise first
        r=self.engine(cleanup=clean).run();self.assertEqual([x['predicate'] for x in r['cleanup_failures']],['FIRST_CHILD','SECOND_CHILD'])
    def test_interrupt_checkpoint_at_every_state_not_replayed(self):
        for i,stage in enumerate(STAGES):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as root:
                self.root=Path(root).resolve();self.calls=[];j=self.prefix(i);j.append('START',stage,{})
                r=self.engine().run(resume=True,resume_tip=j.records[-1]['hash'])
                self.assertEqual(r['primary_failure']['predicate'],'INTERRUPTED_STAGE_NO_REPLAY');self.assertEqual(self.calls,[])
    def test_interrupt_retains_failure_and_attempts_cleanup(self):
        def interrupted(*a):raise KeyboardInterrupt()
        r=self.engine({STAGES[4]:interrupted}).run()
        self.assertEqual(r['primary_failure']['exception_subtype'],'KeyboardInterrupt');self.assertEqual(len(self.clean),1)
    def test_manifest_mutation_in_adapter(self):
        def adapter(*args):engine.m['history']['attempt10']='VERIFIED_TERMINATION';return self.receipt(STAGES[0])
        engine=self.engine({STAGES[0]:adapter});r=engine.run();self.assertEqual(r['primary_failure']['predicate'],'MANIFEST_MUTATION')
        self.assertEqual(r['history']['attempt10'],'UNVERIFIED')

if __name__=='__main__':unittest.main()

class ResumeIntegrityTests(unittest.TestCase):
    setUp=fixtures.CoreTests.setUp
    tearDown=fixtures.CoreTests.tearDown
    receipt=fixtures.CoreTests.receipt
    adapter=fixtures.CoreTests.adapter
    engine=fixtures.CoreTests.engine
    prefix=fixtures.CoreTests.prefix
    def test_rejected_resume_has_no_root_effects(self):
        j=self.prefix(4);j.append('START',STAGES[4],{})
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        r=self.engine().run(resume=True,resume_tip=j.records[-1]['hash'])
        self.assertEqual(r['primary_failure']['predicate'],'INTERRUPTED_STAGE_NO_REPLAY')
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},before)
        self.assertFalse(self.clean);self.assertFalse(self.exported)
    def test_trusted_tip_cannot_promote_incomplete_receipt(self):
        j=Journal(self.root,digest(self.m));b=Budget.create(self.now,self.m['limits'])
        j.append('BEGIN','CONDUCTOR',{'budget':b.__dict__,'history':self.m['history'],'nonce':self.m['nonce'],'clock_identity':'FIXTURE_BOOT'})
        j.append('START',STAGES[0],{});r=self.receipt(STAGES[0]);r['predicates']['EXACT_INPUT']=False;j.append('GREEN',STAGES[0],r)
        result=self.engine().run(resume=True,resume_tip=j.records[-1]['hash'])
        self.assertEqual(result['primary_failure']['predicate'],'RESUME_RECEIPT_PREDICATES');self.assertFalse(self.calls)

class OutputRaceTests(unittest.TestCase):
    def test_parent_replacement_after_exclusive_mkdir(self):
        from iios_native_evidence import fresh_root
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve();parent=base/'parent';parent.mkdir(mode=0o700);old=base/'old';st=parent.stat();real=os.mkdir
            def swapped(name,mode=0o777,*,dir_fd=None):
                result=real(name,mode,dir_fd=dir_fd)
                if name=='qualification-new':parent.rename(old);real(str(parent),0o700)
                return result
            with patch('iios_native_evidence.os.mkdir',side_effect=swapped),self.assertRaises(QualificationFailure) as ctx:
                fresh_root(parent,'qualification-new',[st.st_dev,st.st_ino,st.st_uid,0o700])
            self.assertEqual(ctx.exception.detail['predicate'],'OUTPUT_PARENT_REPLACED')
    def test_wrong_owner_fails(self):
        from iios_native_evidence import owned_directory
        with tempfile.TemporaryDirectory() as tmp,patch('iios_native_evidence.os.getuid',return_value=os.getuid()+1):
            with self.assertRaises(QualificationFailure):owned_directory(str(Path(tmp).resolve()))
    def test_parent_symlink_fails(self):
        from iios_native_evidence import owned_directory
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve();target=base/'parent';target.mkdir(mode=0o700);alias=base/'alias';alias.symlink_to(target)
            with self.assertRaises(OSError):owned_directory(str(alias))
