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
        execute=next(n.lineno for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='load')
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
            self.assertEqual(ctx.exception.detail['predicate'],'MODULE_ORIGIN_REQUIRED')
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
            m.update(source={'commit':'a'*40},output_parent=str(parent),output_name='qualification-failure',output_parent_identity=[st.st_dev,st.st_ino,st.st_uid,0o700])
            detail=QualificationFailure(STAGES[0],'AUDIT_UNREVIEWED_BYTECODE','ADMITTED','UNDECLARED',exception='PermissionError',errno_category='AUDIT_POLICY').detail
            result=export_admission_failure(m,digest(m),detail,100,lambda:101)
            self.assertEqual(result,verify_export(parent/m['output_name'],digest(m)))
            before={p.name:p.read_bytes() for p in (parent/m['output_name']).iterdir()}
            with self.assertRaises(FileExistsError):export_admission_failure(m,digest(m),detail,100,lambda:101)
            self.assertEqual(before,{p.name:p.read_bytes() for p in (parent/m['output_name']).iterdir()})
            self.assertEqual(result['cleanup_classification'],'NOT_ESTABLISHED')

class ExactSourceModuleTests(unittest.TestCase):
    def setUp(self):
        import tempfile,sys
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.patch=patch.dict(sys.modules);self.patch.start();self.addCleanup(self.patch.stop)
        self.bytecode=patch.object(sys,'dont_write_bytecode',True);self.bytecode.start();self.addCleanup(self.bytecode.stop)
    def fixture(self,text='VALUE=42\n',name='reviewed_exact_fixture',scope='REVIEWED_SOURCE'):
        import hashlib
        source=self.root/(name+'.py');source.write_text(text);parent=hashlib.sha256(source.read_bytes()).hexdigest()
        finder=a.ReviewedSourceFinder({str(source):parent},roots=[{'path':str(self.root),'scope':scope}])
        return finder,name,source,parent
    def test_complete_metadata_and_closed_discovery(self):
        finder,name,path,parent=self.fixture()
        with patch.object(a.importlib.machinery.PathFinder,'find_spec',side_effect=AssertionError('DISCOVERY_FORBIDDEN')):
            module=finder.load(name,str(path),parent)
        self.assertEqual(module.VALUE,42);self.assertEqual(module.__spec__.origin,str(path));self.assertEqual(module.__file__,str(path))
        self.assertIs(module.__loader__,module.__spec__.loader);self.assertEqual(module.__package__,'')
        self.assertIsNone(module.__cached__);self.assertIsNone(module.__spec__.cached)
        self.assertEqual(module.__reviewed_source_parent__,a.digest(finder.registry[name]));self.assertFalse((self.root/'__pycache__').exists())
    def test_metadata_mutation_in_source_rejected(self):
        for text in ("__file__='altered'", "__package__='altered'", "__loader__=None", "__spec__.origin='altered'", "__cached__='altered'", "__reviewed_source_parent__='altered'", "del __spec__", "del __file__", "del __loader__", "del __package__"):
            with self.subTest(text=text):
                finder,name,path,parent=self.fixture(text)
                with self.assertRaises(QualificationFailure):finder.load(name,str(path),parent)
                self.assertNotIn(name,a.sys.modules)
    def test_duplicate_existing_and_cross_scope(self):
        import types
        finder,name,path,parent=self.fixture();a.sys.modules[name]=types.ModuleType(name)
        with self.assertRaises(QualificationFailure):finder.load(name,str(path),parent)
        a.sys.modules.pop(name);module=finder.load(name,str(path),parent)
        other=a.ReviewedSourceFinder({str(path):parent},roots=[{'path':str(self.root),'scope':'OTHER_SCOPE'}])
        with self.assertRaises(QualificationFailure):other.load(name,str(path),parent)
        with self.assertRaises(QualificationFailure):finder.load(name,str(path),'b'*64)
    def test_duplicate_origins_and_out_of_root(self):
        finder,name,path,parent=self.fixture();other=self.root/'other';other.mkdir();sub=other/path.name;sub.write_bytes(path.read_bytes())
        with self.assertRaises(QualificationFailure):a.ReviewedSourceFinder({str(path):parent,str(sub):parent},roots=[{'path':str(self.root),'scope':'A'},{'path':str(other),'scope':'B'}])
        finder=a.ReviewedSourceFinder({str(path):parent},roots=[{'path':'/fixture/elsewhere','scope':'A'}])
        with self.assertRaises(QualificationFailure):finder.load(name,str(path),parent)
    def test_symlink_traversal_and_changed_bytes(self):
        finder,name,path,parent=self.fixture();alias=self.root/'alias.py';alias.symlink_to(path)
        linked=a.ReviewedSourceFinder({str(alias):parent})
        with self.assertRaises((QualificationFailure,OSError)):linked.load('alias',str(alias),parent)
        with self.assertRaises(QualificationFailure):a.ReviewedSourceFinder({str(path):parent},roots=[{'path':str(self.root)+'/../escape','scope':'A'}])
        path.write_text('VALUE=43\n')
        with self.assertRaises(QualificationFailure):finder.load(name,str(path),parent)
    def test_same_bytes_replacement_and_post_execution_mutation(self):
        finder,name,path,parent=self.fixture();real=a.pin_file;calls=[]
        def replace(*args,**kwargs):
            record=real(*args,**kwargs);calls.append(1)
            if len(calls)==2:
                swap=self.root/'swap';swap.write_bytes(path.read_bytes());swap.replace(path)
            return record
        with patch.object(a,'pin_file',side_effect=replace),self.assertRaises(QualificationFailure):finder.load(name,str(path),parent)
    def test_optional_absence_only_exact_bootstrap_caller(self):
        finder,name,path,parent=self.fixture('try:\n import _wmi\nexcept ImportError:\n VALUE=42\n','platform','BOOTSTRAP_CONTROLLER')
        a.sys.modules.pop(name,None)
        with patch.object(a.sys,'meta_path',[a.importlib.machinery.BuiltinImporter,a.importlib.machinery.FrozenImporter,finder]):
            module=finder.load(name,str(path),parent)
        self.assertEqual(module.VALUE,42)
        with self.assertRaises(QualificationFailure):finder.find_spec('_wmi')
        with self.assertRaises(QualificationFailure):finder.find_spec('unapproved_missing')
    def test_package_search_parent_and_relative_source_import(self):
        import hashlib
        directory=self.root/'reviewed_pkg';directory.mkdir();init=directory/'__init__.py';child=directory/'child.py'
        init.write_text('from .child import VALUE\n');child.write_text('VALUE=42\n')
        hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (init,child)}
        finder=a.ReviewedSourceFinder(hashes,roots=[{'path':str(self.root),'scope':'A'}])
        with patch.object(a.sys,'meta_path',[finder]):module=finder.load('reviewed_pkg',str(init),hashes[str(init)])
        self.assertEqual(module.VALUE,42);self.assertEqual(module.__path__,[str(directory)])
        with self.assertRaises(QualificationFailure):finder.find_spec('reviewed_pkg.child',['/fixture/substituted'])
    def test_early_receipt_authenticates_failure_and_separates_cleanup(self):
        import json
        from iios_native_evidence import export_admission_failure,verify_export
        import test_iios_native_conductor as fixtures
        m=fixtures.manifest();st=self.root.stat();m.update(source={'commit':'a'*40},output_parent=str(self.root),output_name='qualification-early',output_parent_identity=[st.st_dev,st.st_ino,st.st_uid,0o700])
        detail=QualificationFailure(STAGES[0],'MODULE_ORIGIN_REQUIRED','PINNED','MISSING').detail
        report=export_admission_failure(m,a.digest(m),detail,100,lambda:101,before_dispatcher=True,audit_receipt={'installed':True})
        self.assertEqual(report['workload_cleanup'],'NOT_APPLICABLE_NO_CHILD_CREATED');self.assertEqual(report['helper_cleanup'],'NOT_ESTABLISHED')
        self.assertEqual(report['cleanup_classification'],'NOT_ESTABLISHED')
        root=self.root/m['output_name'];receipt=json.loads((root/'ADMISSION-STAGE-RECEIPT.json').read_bytes())
        self.assertEqual(a.digest(receipt),report['admission_stage_receipt']['sha256']);self.assertEqual(receipt['failure'],detail)
        self.assertEqual(report,verify_export(root,a.digest(m)))
        (root/'ADMISSION-STAGE-RECEIPT.json').write_text('{}')
        with self.assertRaises(QualificationFailure):verify_export(root,a.digest(m))
