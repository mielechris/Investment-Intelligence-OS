import tempfile,unittest,types
from pathlib import Path
from unittest.mock import patch
from iios_native_conductor import STAGES,QualificationFailure
from iios_native_dispatcher import NativeContext
import iios_native_static as static

class StaticAdapterTests(unittest.TestCase):
    def test_cannot_reach_verifier_without_assembly_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            c=NativeContext({},'a'*64,root);c.stage=STAGES[5]
            with patch.object(static,'verify') as verifier,self.assertRaises(QualificationFailure):static.run_stage(c,{'id':STAGES[5]},100,None)
            verifier.assert_not_called()
    def test_exact_existing_verifier_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            c=NativeContext({'native':{'static_descriptor':{'source':'a'*40}},'history':{},'authority':{}},'a'*64,root)
            parent={'detail':{'execution':str(Path(root)/'payload/assembly-output/execution-01')}}
            with patch.object(c,'require_completed',return_value=parent) as prerequisite,patch.object(static,'verify',return_value={'status':'PASS_STATIC_FINAL_LOCATION_ONLY'}) as verifier:
                r=static.run_stage(c,{'id':STAGES[5],'predicates':['STATIC']},100,None)
            prerequisite.assert_called_once_with(STAGES[4]);self.assertEqual(verifier.call_args.kwargs['execution'],parent['detail']['execution']);self.assertEqual(r['status'],'GREEN')
    def test_changed_execution_parent_rejects_before_tools(self):
        c=NativeContext({},'a'*64,'/fresh');c.stage=STAGES[5]
        with patch.object(c,'require_completed',return_value={'detail':{'execution':'/consumed'}}),patch.object(static,'verify') as verifier,self.assertRaises(QualificationFailure):static.run_stage(c,{},100,None)
        verifier.assert_not_called()

if __name__=='__main__':unittest.main()
