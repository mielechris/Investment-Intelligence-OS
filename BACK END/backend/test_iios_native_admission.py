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
        from iios_native_evidence import build_closed_inventory
        index=self.root/'index.json';index.write_bytes(b'');m['closed_input_roots']=[str(self.root)];m['execution_inventory']={'path':str(index),'sha256':'a'*64}
        raw=canonical(build_closed_inventory(m));index.write_bytes(raw);m['execution_inventory']['sha256']=hashlib.sha256(raw).hexdigest()
        self.assertTrue(admit_source(m));m['source']['commit']='b'*40
        with self.assertRaises(QualificationFailure) as ctx:admit_source(m)
        self.assertEqual(ctx.exception.detail['predicate'],'CI_EXACT_COMMIT')
    def test_source_hash_mutation(self):
        path,h=self.put('input',b'old');Path(path).write_bytes(b'new')
        with self.assertRaises(QualificationFailure) as ctx:pin_file(path,h)
        self.assertEqual(ctx.exception.detail['predicate'],'INPUT_HASH')
    def test_detailed_inspection_denial(self):
        from iios_native_dispatcher import NativeContext
        from unittest.mock import MagicMock
        context=NativeContext({},'a'*64,self.root,audit=MagicMock());context.deadline=100
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


class NoAliasInputTests(unittest.TestCase):
    def test_versioned_regular_input_admitted_aliases_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();version=root/'SDK26';version.mkdir();p=version/'header';p.write_bytes(b'pin')
            h=hashlib.sha256(b'pin').hexdigest()
            self.assertEqual(pin_file(p,h)['size'],3)
            for name,target in [('relative','SDK26'),('absolute',str(version))]:
                alias=root/name;alias.symlink_to(target)
                with self.subTest(name=name),self.assertRaises(QualificationFailure) as ctx:pin_file(alias/'header',h)
                self.assertEqual(ctx.exception.detail['predicate'],'INPUT_ANCESTOR_DIRECTORY')
    def test_ancestor_replacement_during_read_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();version=root/'SDK26';version.mkdir();p=version/'header';p.write_bytes(b'pin')
            read=os.read;swapped=False
            def race(fd,size):
                nonlocal swapped
                data=read(fd,size)
                if not swapped:
                    swapped=True;version.rename(root/'old');version.mkdir();(version/'header').write_bytes(b'pin')
                return data
            with patch('iios_native_conductor.os.read',side_effect=race),self.assertRaises(QualificationFailure) as ctx:pin_file(p,hashlib.sha256(b'pin').hexdigest())
            self.assertEqual(ctx.exception.detail['predicate'],'INPUT_ANCESTOR_MUTATION')
    def test_changed_bytes_and_unapproved_leaf_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();p=root/'header';p.write_bytes(b'altered');h=hashlib.sha256(b'pin').hexdigest()
            with self.assertRaises(QualificationFailure) as ctx:pin_file(p,h)
            self.assertEqual(ctx.exception.detail['predicate'],'INPUT_HASH')
            alias=root/'alias';alias.symlink_to(p)
            with self.assertRaises(OSError):pin_file(alias,h)
    def test_relative_and_traversal_inputs_rejected(self):
        for p in ['relative','/fixture/root/../input']:
            with self.subTest(path=p),self.assertRaises(QualificationFailure) as ctx:pin_file(p,'0'*64)
            self.assertEqual(ctx.exception.detail['predicate'],'INPUT_ABSOLUTE_PATH')

class UnresolvedChildTests(unittest.TestCase):
    def run_case(self,values,deadline=100):
        from unittest.mock import patch
        from iios_native_ownership import reconcile_unresolved
        old='11111111-1111-1111-1111-111111111111'
        with patch('iios_native_ownership.unresolved_binding',return_value=({'report':'fixture'},old)):
            return reconcile_unresolved({},lambda:next(values),deadline=deadline,clock=lambda:10)
    def test_changed_boot_three_fresh_observations(self):
        new='22222222-2222-2222-2222-222222222222';r=self.run_case(iter([new]*3))
        self.assertEqual(len(r['observations']),3);self.assertEqual(r['historical_cleanup'],'NOT_ESTABLISHED')
        self.assertFalse(r['historical_cleanup_upgraded']);self.assertEqual(r['signals'],0)
        self.assertEqual(r['observation_kind'],'HOST_BOOT_SESSION_NOT_PID_QUERY')
    def test_same_boot_unknown_pid_never_admitted(self):
        old='11111111-1111-1111-1111-111111111111'
        with self.assertRaises(QualificationFailure) as e:self.run_case(iter([old]*3))
        self.assertEqual(e.exception.detail['predicate'],'UNRESOLVED_CHILD_PID_REQUIRED')
        self.assertEqual(len(e.exception.detail['reconciliation_observations']),3)
    def test_incomplete_unstable_malformed_and_expired(self):
        new='22222222-2222-2222-2222-222222222222'
        for values,deadline in (([new],100),([new,'11111111-1111-1111-1111-111111111111'],100),(['bad'],100),([new]*3,1)):
            with self.subTest(values=values),self.assertRaises(QualificationFailure):self.run_case(iter(values),deadline)
    def test_denial_retains_category_and_completed_observations(self):
        from unittest.mock import patch
        from iios_native_ownership import reconcile_unresolved
        with patch('iios_native_ownership.unresolved_binding',return_value=({},'11111111-1111-1111-1111-111111111111')):
            for code in (1,13):
                with self.subTest(code=code),self.assertRaises(QualificationFailure) as e:
                    reconcile_unresolved({},lambda:(_ for _ in ()).throw(PermissionError(code,'not retained')),deadline=100,clock=lambda:10)
                self.assertEqual(e.exception.detail['exception_subtype'],'PermissionError')
                self.assertNotIn('not retained',str(e.exception.detail));self.assertEqual(e.exception.detail['historical_cleanup'],'NOT_ESTABLISHED')
    def test_missing_binding_fails_before_observation(self):
        from iios_native_ownership import reconcile_unresolved
        with self.assertRaises(QualificationFailure) as e:reconcile_unresolved({},lambda:self.fail('query'),deadline=100,clock=lambda:10)
        self.assertEqual(e.exception.detail['predicate'],'UNRESOLVED_CHILD_BINDING')
    def test_exported_evidence_binding_and_tamper(self):
        from iios_native_ownership import unresolved_binding
        from iios_native_conductor import Journal,digest
        from iios_native_evidence import export
        import tempfile,json,hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();parent='a'*64;j=Journal(root,parent)
            j.append('BEGIN','CONDUCTOR',{'clock_identity':'11111111-1111-1111-1111-111111111111'})
            report={'manifest':parent,'status':'RED','cleanup_receipt':None,'cleanup_failures':[{'predicate':'REGISTERED_OWNERSHIP'}]}
            j.append('FINAL','PRIVATE_RUNTIME_ASSEMBLY',report);export(root,report,100,lambda:1)
            def pin(name):return {'path':str(root/name),'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()}
            binding=dict(report=pin('REPORT.json'),begin=pin('checkpoint-0000.json'),export=pin('EXPORT.json'),inventory=pin('INVENTORY.json'),history_key='consumed',pid=None)
            m={'unresolved_child':binding,'history':{'consumed':'NOT_ESTABLISHED'},'historical_records':[binding[k] for k in ('report','begin','export','inventory')]}
            m.update(source={'root':str(root),'commit':'a'*40,'inventory':[]},inputs=[],closed_input_roots=[str(root)])
            from iios_native_evidence import build_closed_inventory
            m['historical_records']=[pin(p.name) for p in root.iterdir()]
            index_path=root/'closed-index.json';index_path.write_bytes(b'')
            m['execution_inventory']={'path':str(index_path),'sha256':'a'*64}
            raw=__import__('iios_native_conductor').canonical(build_closed_inventory(m));index_path.write_bytes(raw);m['execution_inventory']['sha256']=hashlib.sha256(raw).hexdigest()
            with patch.object(os,'scandir',side_effect=AssertionError('NO_ENUMERATION')),patch.object(os,'listdir',side_effect=AssertionError('NO_ENUMERATION')),patch.object(Path,'glob',side_effect=AssertionError('NO_ENUMERATION')),patch.object(Path,'rglob',side_effect=AssertionError('NO_ENUMERATION')):
                self.assertEqual(unresolved_binding(m)[1],'11111111-1111-1111-1111-111111111111')
            m['history']['consumed']='VERIFIED_TERMINATION'
            with self.assertRaises(QualificationFailure):unresolved_binding(m)
            m['history']['consumed']='NOT_ESTABLISHED';(root/'checkpoint-0000.json').write_text('{}')
            with self.assertRaises(QualificationFailure):unresolved_binding(m)
    def test_source_controlled_launcher_exact_authority(self):
        from iios_native_admission import render_terminal_launcher
        args=['/fixture/python','-I','-B','/fixture/main.py','--manifest','/fixture/manifest','--manifest-sha256','a'*64,'--authorize-manifest','a'*64]
        pins=[{'path':p,'sha256':'a'*64} for p in (args[0],args[3],args[5])]
        text=render_terminal_launcher(args,'/fixture/cwd',pins).decode()
        self.assertIn('Apple_Terminal',text);self.assertEqual(text.count('\nexec '),1);self.assertNotIn('retry',text)
        args[-1]='b'*64
        with self.assertRaises(QualificationFailure):render_terminal_launcher(args,'/fixture/cwd',pins)

    def test_launch_pid_survives_preinspection_failure(self):
        import tempfile,json
        from unittest.mock import patch,MagicMock
        from iios_native_dispatcher import NativeContext
        from iios_native_ownership import LaunchBinding
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();env={'LC_ALL':'C','TZ':'UTC','__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'}
            context=NativeContext({'environment':env,'cwd':str(root)},'a'*64,root,audit=MagicMock())
            context.stage='PRIVATE_RUNTIME_ASSEMBLY';context.deadline=100;context.clock=lambda:1
            child=MagicMock();child.pid=12345
            binding=LaunchBinding('/fixture/python','a'*64,'/fixture/python','a'*64,'/fixture/child.py','b'*64,('/fixture/python','/fixture/child.py'),('/fixture/python','/fixture/child.py'),1)
            with patch.object(context,'spawn',return_value=child),patch.object(context,'check'),patch.object(LaunchBinding,'verify',return_value=()),patch.object(LaunchBinding,'reverify'),patch('iios_native_dispatcher.os.set_blocking',side_effect=OSError(13,'fixture')):
                with self.assertRaises(OSError):context.execute_owned(binding,20,100)
            record=json.loads((root/'OWNED-CHILD-0001-LAUNCH.json').read_bytes())
            self.assertEqual(record['pid'],12345);self.assertEqual(record['manifest'],'a'*64)
            self.assertFalse(record['ownership_verified']);self.assertEqual(record['cleanup'],'NOT_ESTABLISHED')
            self.assertEqual(len(context.children),1);self.assertIs(context.children[0].child,child)

    def test_current_pid_present_denied_and_partial_receipts(self):
        from iios_native_ownership import reconcile_pid
        from types import SimpleNamespace
        values=iter([None,SimpleNamespace(parent_pid=1,start_time='fixture',executable='/fixture',executable_hash='a'*64,argv=('fixture',),command='fixture',cwd='/fixture'),None])
        with self.assertRaises(QualificationFailure) as e:reconcile_pid(35731,lambda pid:next(values),stage='HISTORICAL_PROCESS_RECONCILIATION',deadline=100,clock=lambda:10)
        self.assertEqual(len(e.exception.detail['current_process_observations']),3)
        self.assertEqual(e.exception.detail['current_process_observations'][1]['existence'],'PRESENT')
        self.assertFalse(e.exception.detail['historical_ownership']);self.assertNotIn('/fixture',str(e.exception.detail))
        with self.assertRaises(QualificationFailure) as e:reconcile_pid(35731,lambda pid:(_ for _ in ()).throw(PermissionError(13,'unretained')),stage='HISTORICAL_PROCESS_RECONCILIATION',deadline=100,clock=lambda:10)
        self.assertEqual(e.exception.detail['errno_category'],'EACCES');self.assertEqual(e.exception.detail['current_process_observations'],[])

class ClosedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.data=self.root/'data';self.data.mkdir();self.a=self.data/'a.py';self.b=self.data/'b.py';self.a.write_bytes(b'A');self.b.write_bytes(b'B')
        self.m={'source':{'root':str(self.data),'commit':'a'*40,'inventory':[{'relative':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (self.a,self.b)]},'inputs':[],'historical_records':[],'closed_input_roots':[str(self.data)],'execution_inventory':{'path':str(self.root/'index.json'),'sha256':'a'*64}}
        from iios_native_evidence import build_closed_inventory
        self.index=build_closed_inventory(self.m);self.write_index()
    def write_index(self):
        raw=canonical(self.index);Path(self.m['execution_inventory']['path']).write_bytes(raw);self.m['execution_inventory']['sha256']=hashlib.sha256(raw).hexdigest()
    def verify(self):
        from iios_native_evidence import verify_closed_inventory
        return verify_closed_inventory(self.m)
    def test_direct_checks_never_enumerate(self):
        with patch.object(os,'scandir',side_effect=AssertionError('ENUMERATION')),patch.object(os,'listdir',side_effect=AssertionError('ENUMERATION')),patch.object(Path,'glob',side_effect=AssertionError('ENUMERATION')),patch.object(Path,'rglob',side_effect=AssertionError('ENUMERATION')):
            self.assertEqual(self.verify(),self.index)
    def test_missing_additional_duplicate_reordered_and_outside_rows(self):
        for mode in ('missing','additional','duplicate','reordered','outside'):
            original=copy.deepcopy(self.index)
            with self.subTest(mode=mode):
                if mode=='missing':self.index['files'].pop()
                elif mode=='additional':self.index['files'].append(dict(self.index['files'][0],path=str(self.data/'extra')))
                elif mode=='duplicate':self.index['files'].append(self.index['files'][0])
                elif mode=='reordered':self.index['files'].reverse()
                else:self.index['files'][0]['path']='/unadmitted/escape'
                self.write_index()
                with self.assertRaises(QualificationFailure) as e:self.verify()
                self.assertEqual(e.exception.detail['predicate'],'CLOSED_INPUT_SEQUENCE')
            self.index=original;self.write_index()
    def test_metadata_owner_size_mode_and_containment_pins(self):
        for key,offset in (('identity',2),('identity',3),('identity',0),('identity',1),('identity',5)):
            old=copy.deepcopy(self.index);self.index['files'][0][key][offset]+=1;self.write_index()
            with self.assertRaises(QualificationFailure) as e:self.verify()
            self.assertIn('closed_input',e.exception.detail);self.assertLess(len(json.dumps(e.exception.detail)),1800)
            self.index=old
        self.index['files'][0]['size']+=1;self.write_index()
        with self.assertRaises(QualificationFailure):self.verify()
    def test_same_bytes_replacement_missing_and_new_entries_fail(self):
        self.a.unlink();self.a.write_bytes(b'A')
        with self.assertRaises(QualificationFailure):self.verify()
    def test_additional_physical_entry_in_sealed_root_fails(self):
        (self.data/'additional').write_bytes(b'X')
        with self.assertRaises(QualificationFailure) as e:self.verify()
        self.assertEqual(e.exception.detail['predicate'],'CLOSED_DIRECTORY_MUTATION')
    def test_altered_file_and_symlink_fail(self):
        self.a.write_bytes(b'X')
        with self.assertRaises(QualificationFailure):self.verify()
        self.a.unlink();self.a.symlink_to(self.b)
        with self.assertRaises(QualificationFailure):self.verify()
    def test_post_verification_directory_race_fails(self):
        from iios_native_evidence import pin_file as original
        def mutate(*args,**kwargs):
            result=original(*args,**kwargs)
            if str(args[0])==str(self.b):(self.data/'race').write_bytes(b'X')
            return result
        with patch('iios_native_evidence.pin_file',side_effect=mutate),self.assertRaises(QualificationFailure) as e:self.verify()
        self.assertEqual(e.exception.detail['predicate'],'CLOSED_DIRECTORY_MUTATION')
    def test_directory_symlink_and_source_traversal_fail(self):
        self.m['source']['inventory'][0]['relative']='../escape'
        from iios_native_evidence import closed_paths,directory_identity
        with self.assertRaises(QualificationFailure):closed_paths(self.m)
        link=self.root/'alias';link.symlink_to(self.data,target_is_directory=True)
        with self.assertRaises(QualificationFailure):directory_identity(str(link))
    def test_missing_input_is_not_absence_success(self):
        self.a.unlink()
        with self.assertRaises(QualificationFailure):self.verify()
