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
    def setUp(self):self.guard=a.NativeAudit(manifest(),'a'*64)
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
        self.assertEqual(result,{'verified':False,'outstanding':1})
    def test_lazy_compile_bytes_and_bytecode_bypass_rejected(self):
        self.reject('compile',(b'changed','/bound/source/module.py'),'AUDIT_COMPILED_SOURCE_MUTATION')
        self.reject('compile',(b'changed','/bound/source/unknown.py'),'AUDIT_UNBOUND_SOURCE_COMPILE')
        self.reject('open',('/bound/source/__pycache__/module.pyc','r',0),'AUDIT_UNREVIEWED_BYTECODE')
    def test_unknown_effect_rejected(self):self.reject('os.unknown_mutation',(),'AUDIT_STAGE_OPERATION')

if __name__=='__main__':unittest.main()
