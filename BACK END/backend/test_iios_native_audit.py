"""Audit callbacks exercised without installing hooks or native effects."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch
import iios_native_audit as a
from iios_native_conductor import STAGES,QualificationFailure


def manifest():
    return dict(source=dict(root='/bound/source',inventory=[dict(relative='module.py',sha256='a'*64)]),
        inputs=[dict(path='/bound/input',sha256='a'*64)],historical_records=[],tool_pins={'/bin/ps':'a'*64},
        ci=dict(path='/bound/ci',sha256='a'*64),dispatcher=dict(path='/bound/dispatcher.py',sha256='a'*64),
        output_parent='/exclusive',output_name='qualification-nonce')


class NativeAuditTests(unittest.TestCase):
    def setUp(self):
        self.guard=a.NativeAudit(manifest(),'a'*64);self.original_finders=list(a.sys.meta_path);self.original_no_bytecode=a.sys.dont_write_bytecode
    def tearDown(self):
        a.sys.meta_path=self.original_finders;a.sys.dont_write_bytecode=self.original_no_bytecode
    def reject(self,event,args,predicate):
        with self.assertRaises(QualificationFailure) as c:self.guard(event,args)
        self.assertEqual(c.exception.detail['predicate'],predicate)
        self.assertEqual(c.exception.detail['errno_category'],'AUDIT_POLICY')
    def test_every_stage_has_explicit_operations(self):
        self.assertEqual(set(a.OPERATIONS),set(STAGES)|{'CLEANUP','EXPORT'})
        for stage in STAGES:
            self.guard.stage=stage
            for event in ('socket.connect','socket.getaddrinfo','os.kill','os.killpg','os.system','os.posix_spawn'):
                self.reject(event,(),'AUDIT_FORBIDDEN_EFFECT')
    def test_source_and_lazy_import_paths_exact(self):
        self.guard('import',('module','/bound/source/module.py',None,None,None))
        self.reject('import',('module','/elsewhere/module.py',None,None,None),'AUDIT_READ_PIN')
        self.reject('open',('/elsewhere/module.py','r',0),'AUDIT_READ_PIN')
    def test_protected_and_relative_paths(self):
        for path in ('relative','/exclusive/qualification-nonce/../bad','/exclusive/qualification-nonce/Keychains/input'):
            with self.subTest(path=path),self.assertRaises(QualificationFailure):self.guard.path(path)
    def test_stage_write_and_sealed_tree(self):
        self.guard.stage=STAGES[5]
        self.guard.path(self.guard.root+'/checkpoint-0004.json',True)
        with self.assertRaises(QualificationFailure):self.guard.path(self.guard.root+'/substitute',True)
        self.guard.stage=STAGES[4];self.guard.sealed=(self.guard.root+'/payload',)
        with self.assertRaises(QualificationFailure):self.guard.path(self.guard.root+'/payload/runtime',True)
    def test_unbound_and_bound_fd(self):
        self.reject('open',(99,'r',0),'AUDIT_UNBOUND_FD')
        self.guard.fds[99]='/bound/input';self.guard('open',(99,'r',0))
    def test_exact_single_use_command_and_exception_revocation(self):
        self.guard.stage=STAGES[1]
        args=('/bin/ps',('/bin/ps','-p','35731'),None,{'LC_ALL':'C'})
        with patch.object(self.guard,'verify',return_value='b'*64):
            with self.guard.launch(args[1],args[2],args[3]):
                self.guard('subprocess.Popen',args)
                self.reject('subprocess.Popen',args,'AUDIT_COMMAND_BINDING')
            with self.assertRaises(ValueError):
                with self.guard.launch(args[1],args[2],args[3]):raise ValueError()
        self.assertIsNone(self.guard.command);self.assertFalse(self.guard.launching)
        self.reject('subprocess.Popen',args,'AUDIT_COMMAND_BINDING')
    def test_inspection_scope_and_symbols(self):
        self.guard.stage=STAGES[2]
        self.reject('ctypes.dlopen',('/usr/lib/libSystem.B.dylib',),'AUDIT_INSPECTOR_SCOPE')
        with patch.object(self.guard,'verify',return_value='b'*64):
            with self.guard.inspection():
                self.guard('ctypes.dlopen',('/usr/lib/libSystem.B.dylib',))
                self.guard('ctypes.dlsym',(object(),'sysctl'))
                self.reject('ctypes.dlsym',(object(),'system'),'AUDIT_SYMBOL_BINDING')
        self.assertFalse(self.guard.inspecting)
    def test_uninstalled_receipt_cannot_authorize(self):
        with self.assertRaises(QualificationFailure):self.guard.verify()
    def test_no_installation_ack_is_failure(self):
        with patch.object(a.os,'open'),patch.object(a.os,'close'),patch.object(a.os,'dup'),patch.object(a.sys,'addaudithook'),patch.object(a.sys,'audit'):
            with self.assertRaises(QualificationFailure):self.guard.install()
        self.assertFalse(self.guard.installed)
    def test_installation_ack_receipt_and_manifest(self):
        with patch.object(a.os,'open'),patch.object(a.os,'close'),patch.object(a.os,'dup'),patch.object(a.sys,'addaudithook'),patch.object(a.sys,'audit',side_effect=lambda e,*v:self.guard(e,v)):
            receipt=self.guard.install();self.guard.verify()
            self.assertTrue(receipt['installed_before_dispatcher_import'])
            self.guard.receipt['manifest']='b'*64
            with self.assertRaises(QualificationFailure):self.guard.verify()
    def test_handoff_installs_before_dispatcher_resolution(self):
        source=(Path(__file__).parents[2]/'scripts/iios_native_qualification.py').read_text()
        tree=ast.parse(source);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(main) if isinstance(n,ast.Call)]
        install=next(n.lineno for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='install')
        execute=next(n.lineno for n in calls if isinstance(n.func,ast.Name) and n.func.id=='exec')
        self.assertLess(install,execute)
    def test_metadata_read_never_grants_attribute_writes(self):
        self.guard.stage=STAGES[5]
        with patch.object(self.guard,'verify',return_value='b'*64):
            with self.guard.metadata():
                for name in a.METADATA_SYMBOLS:self.guard('ctypes.dlsym',(object(),name))
                self.guard('ctypes.set_errno',(0,))
                self.reject('ctypes.dlsym',(object(),'fsetxattr'),'AUDIT_SYMBOL_BINDING')
                self.reject('ctypes.set_errno',(13,),'AUDIT_ERRNO_RESET')
        self.assertFalse(self.guard.metadata_read)
    def test_failed_process_constructor_retains_cleanup_uncertainty(self):
        from unittest.mock import MagicMock
        from iios_native_dispatcher import NativeContext
        context=NativeContext({},'a'*64,'/fixture',audit=MagicMock());context.deadline=100
        with patch('iios_native_dispatcher.clock',return_value=1),patch('iios_native_dispatcher.subprocess.Popen',side_effect=PermissionError(13,'not retained')):
            with self.assertRaises(PermissionError):context.spawn(['/bound/tool'],env={})
            result=context.cleanup(200)
        self.assertEqual({k:result[k] for k in ('verified','outstanding')},{'verified':False,'outstanding':1})
        self.assertEqual(result['workload_cleanup'],'UNVERIFIED')
    def test_lazy_compile_bytes_and_bytecode_bypass_rejected(self):
        self.reject('compile',(b'changed','/bound/source/module.py'),'AUDIT_COMPILED_SOURCE_MUTATION')
        self.reject('compile',(b'changed','/bound/source/unknown.py'),'AUDIT_UNBOUND_SOURCE_COMPILE')
        self.reject('open',('/bound/source/__pycache__/module.pyc','r',0),'AUDIT_UNREVIEWED_BYTECODE')
    def test_unknown_effect_rejected(self):self.reject('os.unknown_mutation',(),'AUDIT_STAGE_OPERATION')

if __name__=='__main__':unittest.main()

class ReviewedSourceLoadingTests(unittest.TestCase):
    def test_source_categories_never_probe_or_write_cache(self):
        import tempfile,hashlib,sys
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            for category in ('repository','packaged','stdlib','third_party'):
                directory=root/category;directory.mkdir();source=directory/'reviewed_fixture.py';source.write_bytes(b'VALUE = 42\n')
                finder=a.ReviewedSourceFinder({str(source):hashlib.sha256(source.read_bytes()).hexdigest()})
                with patch.object(sys,'path',[str(directory)]):spec=finder.find_spec('reviewed_fixture')
                with patch.object(a.importlib.machinery.SourceFileLoader,'get_data',side_effect=AssertionError('CACHE_OR_UNBOUND_READ')):
                    code=spec.loader.get_code('reviewed_fixture')
                namespace={};exec(code,namespace);self.assertEqual(namespace['VALUE'],42)
                self.assertFalse((directory/'__pycache__').exists())
                with self.assertRaises(QualificationFailure):spec.loader.set_data('ignored',b'ignored')
    def test_altered_and_out_of_root_source_rejected(self):
        import tempfile,hashlib,sys
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp).resolve()/'reviewed_fixture.py';source.write_bytes(b'VALUE=1')
            finder=a.ReviewedSourceFinder({str(source):hashlib.sha256(source.read_bytes()).hexdigest()})
            with patch.object(sys,'path',[str(source.parent)]):spec=finder.find_spec('reviewed_fixture')
            source.write_bytes(b'VALUE=2')
            with self.assertRaises(QualificationFailure):spec.loader.get_code('reviewed_fixture')
            with patch.object(sys,'path',[str(source.parent)]),self.assertRaises(QualificationFailure):a.ReviewedSourceFinder({}).find_spec('reviewed_fixture')
    def test_all_bytecode_formats_and_sourceless_origins_rejected(self):
        import importlib.machinery,hashlib
        for category in ('repository_cache','packaged','stdlib','third_party','stale','altered','cross_version','sourceless'):
            path='/bound/'+category+'.pyc';loader=importlib.machinery.SourcelessFileLoader(category,path)
            spec=importlib.machinery.ModuleSpec(category,loader,origin=path)
            with self.subTest(category=category),patch.object(importlib.machinery.PathFinder,'find_spec',return_value=spec),self.assertRaises(QualificationFailure) as ctx:
                a.ReviewedSourceFinder({path:hashlib.sha256(category.encode()).hexdigest()}).find_spec(category)
            self.assertEqual(ctx.exception.detail['predicate'],'MODULE_BYTECODE_OR_CUSTOM_LOADER_FORBIDDEN')
    def test_diagnostic_binds_only_reviewed_source_origin(self):
        import importlib.util
        guard=a.NativeAudit(manifest(),'a'*64);path=importlib.util.cache_from_source('/bound/source/module.py')
        with self.assertRaises(QualificationFailure) as ctx:guard('open',(path,'r',0))
        self.assertEqual(ctx.exception.detail['bytecode_attempt']['source'],'/bound/source/module.py')
        with self.assertRaises(QualificationFailure) as ctx:guard('open',('/unrelated/private_name.pyc','r',0))
        self.assertEqual(ctx.exception.detail['bytecode_attempt']['path'],'UNADMITTED_PATH')
    def test_audit_failures_are_exported_with_verifiable_chain(self):
        import tempfile,json
        import test_iios_native_conductor as fixtures
        from iios_native_conductor import Conductor,digest
        from iios_native_evidence import export,verify_export
        for category in ('repository','packaged','stdlib','third_party','stale','substituted'):
            with self.subTest(category=category),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();m=fixtures.manifest();parent=digest(m)
                def denied(*args):
                    guard=a.NativeAudit(manifest(),'a'*64);guard.stage=STAGES[2]
                    guard('open',('/bound/'+category+'.pyc','r',0))
                def passed(row,*args):return {'stage':row['id'],'status':'GREEN','manifest':parent,'history':m['history'],'authority':m['authority'],'predicates':dict.fromkeys(row['predicates'],True),'artifacts':[]}
                adapters=dict.fromkeys(STAGES,passed);adapters[STAGES[2]]=denied
                clock=lambda:100
                engine=Conductor(m,parent,root,adapters,clock=clock,wall=lambda:1,verify_receipt=lambda r:None,
                    cleanup=lambda d:{'verified':True,'outstanding':0,'workload_children':0},export=lambda r,d:export(root,r,d,clock))
                result=engine.run();verified=verify_export(root,parent)
                self.assertEqual(result,verified);self.assertEqual(result['primary_failure']['predicate'],'AUDIT_UNREVIEWED_BYTECODE')
                self.assertEqual(result['cleanup_receipt']['workload_children'],0)
    def test_installed_loader_policy_cannot_be_removed_or_mutated(self):
        import os,sys
        guard=a.NativeAudit(manifest(),'a'*64)
        with patch.object(sys,'meta_path',list(sys.meta_path)),patch.object(sys,'dont_write_bytecode',True),patch.object(sys,'addaudithook'),patch.object(sys,'audit',side_effect=lambda event,*args:guard(event,args)),patch.object(os,'open',os.open),patch.object(os,'close',os.close),patch.object(os,'dup',os.dup):
            receipt=guard.install();self.assertIn('source_loader_parent',receipt);guard.verify()
            sys.meta_path.append(object())
            with self.assertRaises(QualificationFailure):guard.verify()
            sys.meta_path=list(guard.finders);sys.dont_write_bytecode=False
            with self.assertRaises(QualificationFailure):guard.verify()
            sys.dont_write_bytecode=True;guard.finder.hashes['/unbound']='a'*64
            with self.assertRaises(QualificationFailure):guard.verify()
    def test_early_audit_failure_exports_without_native_effects_or_overwrite(self):
        import tempfile,os
        from iios_native_evidence import export_admission_failure,verify_export
        from iios_native_conductor import digest
        import test_iios_native_conductor as fixtures
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve();st=parent.stat();m=fixtures.manifest()
            m.update(output_parent=str(parent),output_name='qualification-failure',output_parent_identity=[st.st_dev,st.st_ino,st.st_uid,0o700])
            detail=QualificationFailure(STAGES[0],'AUDIT_UNREVIEWED_BYTECODE','ADMITTED','UNDECLARED',exception='PermissionError',errno_category='AUDIT_POLICY').detail
            result=export_admission_failure(m,digest(m),detail,100,lambda:101)
            self.assertEqual(result,verify_export(parent/m['output_name'],digest(m)))
            before={p.name:p.read_bytes() for p in (parent/m['output_name']).iterdir()}
            with self.assertRaises(FileExistsError):export_admission_failure(m,digest(m),detail,100,lambda:101)
            self.assertEqual(before,{p.name:p.read_bytes() for p in (parent/m['output_name']).iterdir()})
            self.assertEqual(result['cleanup_classification'],'NOT_ESTABLISHED')
