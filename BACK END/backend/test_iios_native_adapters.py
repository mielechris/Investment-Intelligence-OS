"""Substituted native boundaries only. These tests never spawn a process."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch,Mock
from iios_native_conductor import STAGES,QualificationFailure,digest,canonical,Budget
from iios_native_dispatcher import NativeContext
import iios_native_runtime_adapter as runtime
import iios_native_assembly as assembly
from test_iios_native_image_policy import inputs
from iios_native_image_policy import build_policy,PRODUCTION


class RuntimeAdapterTests(unittest.TestCase):
    def test_requires_reference_green(self):
        c=NativeContext({},'a'*64,'/fixture');c.stage=STAGES[7]
        with patch.object(runtime,'generate_child') as child,self.assertRaises(QualificationFailure):runtime.run_stage(c,{},1,None)
        child.assert_not_called()
    def test_replayed_static_parent(self):
        c=NativeContext({},'a'*64,'/fixture');c.stage=STAGES[7]
        parent={'detail':{'scope':PRODUCTION,'static_receipt_parent':'a'*64}}
        with patch.object(c,'require_completed',side_effect=[parent,{}]),patch.object(runtime,'generate_child') as child,self.assertRaises(QualificationFailure) as caught:runtime.run_stage(c,{},1,None)
        self.assertEqual(caught.exception.detail['predicate'],'RUNTIME_REFERENCE_RECEIPT_PARENT');child.assert_not_called()
    def test_bootstrap_receipt_cannot_satisfy_runtime(self):
        c=NativeContext({},'a'*64,'/fixture');c.stage=STAGES[7]
        parent={'detail':{'scope':'BOOTSTRAP_IMAGE_REFERENCE_V1','static_receipt_parent':digest({})}}
        with patch.object(c,'require_completed',side_effect=[parent,{}]),self.assertRaises(QualificationFailure) as caught:runtime.run_stage(c,{},1,None)
        self.assertEqual(caught.exception.detail['predicate'],'RUNTIME_REFERENCE_RECEIPT_PARENT')
    def test_generator_rejects_unreviewed_import_plan(self):
        policy=build_policy(**inputs())
        with self.assertRaises(QualificationFailure):runtime.generate_child(b"APPROVED_IMPORTS=('os','_tkinter')",policy,destination='/fixture/child.py',discovery=())
    def test_generator_uses_accepted_functions_and_removes_tk(self):
        policy=build_policy(**inputs());policy['imports']=['ssl'];policy['module_files']=[]
        names=('ROOT','PREP','CA','APPROVED_IMPORTS','REQUIRED_IMPORTS','MODULE_FILES','IMAGE_MAXIMUM','IMAGE_REFERENCE_PARENT','EXPECTED_CACHE_UUID','SCOPE','SEALED_IMPORT_NAMES','IMAGE_PATHS','IMAGE_UUIDS')
        text='\n'.join(n+"=None" for n in names if n!='APPROVED_IMPORTS')+"\nAPPROVED_IMPORTS=('ssl','_tkinter')\ndef collect_inventory(*a):pass\ndef main():\n    ssl=import_one('ssl')\n    tk=import_one('_tkinter')\n"
        result=runtime.generate_child(text.encode(),policy,destination='/fixture/child.py',discovery=())
        tree=ast.parse(result);self.assertNotIn('_tkinter',result.decode());compile(tree,'child','exec')
        self.assertIn('PRODUCTION_RUNTIME_IMAGE_POLICY_V1',result.decode());self.assertIn('_dyld_get_image_uuid',result.decode())
    def test_tls_report_scope_and_identity(self):
        policy=build_policy(**inputs());images=[{'path':r['path'],'uuid':r['uuid']} for r in policy['rows']]
        scan={'complete':True,'count':len(images),'images':images}
        value={'scope':PRODUCTION,'policy_parent':digest(policy),'imports':policy['imports'],'scans':[scan,scan],'origins':[{'module':'ssl','file':'lib/_ssl.so'}],
               'cache_uuids':[policy['cache_uuid']]*2,'stage':'COMPLETE','ca_sha256':'9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f','ca_count':121,'tls_context_only':True}
        self.assertEqual(runtime.decode_acceptance(canonical(value),policy)['scans'],2)
        for name,altered in [('scope','BOOTSTRAP_IMAGE_REFERENCE_V1'),('ca_count',120),('tls_context_only',False)]:
            changed=copy.deepcopy(value);changed[name]=altered
            with self.subTest(name=name),self.assertRaises(QualificationFailure):runtime.decode_acceptance(canonical(changed),policy)


class AssemblyAdapterTests(unittest.TestCase):
    def test_no_assembly_before_prerequisites(self):
        c=NativeContext({},'a'*64,'/fixture');c.stage=STAGES[4]
        with patch.object(assembly,'prepare') as prepare,self.assertRaises(QualificationFailure):assembly.run_stage(c,{},1,None)
        prepare.assert_not_called()
    def test_pid_result_cannot_be_inferred(self):
        c=NativeContext({'historical_pids':[35731]},'a'*64,'/fixture');c.stage=STAGES[4]
        safety={'detail':{'observations':[{'status':'UNKNOWN'}]}}
        with patch.object(c,'require_completed',side_effect=[{},safety]),patch.object(assembly,'prepare') as prepare,self.assertRaises(QualificationFailure) as caught:assembly.run_stage(c,{},1,None)
        self.assertEqual(caught.exception.detail['predicate'],'ASSEMBLY_PID_SAFETY_PARENT');prepare.assert_not_called()
    def test_existing_output_parent_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            boundary=Path(tmp).resolve();value=assembly.output_parent(boundary)
            self.assertEqual(value['mode'],0o700);self.assertFalse(Path(value['execution_path']).exists())
            with self.assertRaises(FileExistsError):assembly.output_parent(boundary)
    def test_migrated_child_has_no_alarm_or_fixed_source(self):
        path=Path(assembly.__file__).with_name('iios_native_assembly_child.py');tree=ast.parse(path.read_bytes())
        calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertNotIn('signal.alarm',calls);self.assertNotIn('signal.signal',calls)
        text=path.read_text();self.assertIn('PASS_BOTTOM_UP_RESOURCE_SEAL_ONLY',text)
        self.assertIn("receipt['seal_kind']=='IIOS_BOTTOM_UP_ADHOC_RESOURCE_SEAL'",text)
    def test_migrated_sealer_preserves_type_and_order(self):
        import iios_native_sealer as sealer
        self.assertEqual(sealer.DERIVED_CODE[-1],'lib/python3.14/site-packages/grpc/_cython/cygrpc.cpython-314-darwin.so')
        with patch('alpha_assembly_file_type.inspect_file_type',side_effect=ValueError('DERIVED_FILE_TYPE')) as identity,self.assertRaises(ValueError):
            sealer.image_identity(Path('/fixture'),'relative','MACH_O_BUNDLE','UNSIGNED',1,{}, {},'a'*64)
        identity.assert_called_once()


class TransportTests(unittest.TestCase):
    def test_no_spawn_on_changed_binding(self):
        c=NativeContext({},'a'*64,'/fixture');c.stage=STAGES[7]
        binding=Mock();binding.verify.side_effect=ValueError('INPUT_HASH')
        with patch('iios_native_dispatcher.subprocess.Popen') as popen,self.assertRaises(ValueError):c.execute_owned(binding,1,2)
        popen.assert_not_called()
    def test_runtime_deadline_never_borrows(self):
        c=NativeContext({'native':{'runtime_acceptance':{'launcher_relative':'Python','image_relative':'Python','clock_contract':'fixture'}}},'a'*64,'/fixture');c.stage=STAGES[7];c.clock=lambda:1
        p=build_policy(**inputs())
        with patch.object(c,'execute_owned') as execute,self.assertRaises(QualificationFailure) as caught:c.run_owned_runtime('/fixture/child','a'*64,p,1,90_000_000_001)
        self.assertEqual(caught.exception.detail['predicate'],'RUNTIME_EXISTING_DEADLINE_CONTRACT');execute.assert_not_called()

class FailureAndBudgetTests(unittest.TestCase):
    def test_file_type_failure_survives_conductor_translation(self):
        from alpha_assembly_file_type import validate_file_type,DerivedFileTypeError,PATHS
        from iios_native_conductor import failure
        try:validate_file_type(sorted(PATHS)[0],'MACH_O_BUNDLE',1,b'unknown',b'',b'bad','a'*64)
        except DerivedFileTypeError as error:
            result=failure(error,STAGES[4],'ASSEMBLY_EXCEPTION')
            self.assertEqual(result['predicate'],'DERIVED_FILE_TYPE');self.assertEqual(result['file_type_failure'],error.file_type_failure)
            self.assertNotIn('unknown',str(result))
    def test_untrusted_file_evidence_not_exported(self):
        from alpha_assembly_file_type import DerivedFileTypeError
        from iios_native_conductor import failure
        result=failure(DerivedFileTypeError({'path':'sensitive'}),STAGES[4],'ASSEMBLY_EXCEPTION')
        self.assertNotIn('file_type_failure',result);self.assertNotIn('sensitive',str(result))
    def test_root_creation_time_charged_to_outer_budget(self):
        from test_iios_native_conductor import CoreTests
        fixture=CoreTests();fixture.setUp()
        try:
            result=fixture.engine(initial_start=-1000).run()
            self.assertEqual(result['primary_failure']['predicate'],'OUTER_WORK_DEADLINE');self.assertEqual(fixture.calls,[])
        finally:fixture.tearDown()
