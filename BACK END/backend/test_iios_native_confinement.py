"""Offline confinement orchestration; every process/OS boundary is substituted."""
import ast
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
from iios_native_conductor import QualificationFailure,canonical
from iios_native_confinement import PROBE,CHECKS,OPERATIONS,trial,SandboxBinding
from iios_native_assembly import publish
from truth_spine_process_identity import ProcessObservation


def owner_rows():
    return [{'sample':x,'matches':dict.fromkeys(('pid','parent_pid','start_time_present','executable','executable_hash','argv','command','cwd','stable'),True)} for x in (1,2,3)]
def owner_cleanup():return {'verified':True,'outstanding':0,'exit_code':0,'reaped':True,'independently_absent':True,'signals':0}


class ConfinementTests(unittest.TestCase):
    def test_probe_is_fixed_dummy_operations(self):
        tree=ast.parse(PROBE.replace('__DESCRIPTOR__','{}'));compile(tree,'probe','exec')
        self.assertEqual(set(CHECKS),{'filesystem','network','subprocess','credential_boundary'})
        self.assertEqual(OPERATIONS['network'],'network-inbound')
        self.assertNotIn('192.0.2.1',PROBE);self.assertNotIn('kill',PROBE)
        self.assertIn("('127.0.0.1',38494)",PROBE)
    def test_wrapper_keeps_complete_final_argv(self):
        inner=types.SimpleNamespace(command=('/runtime/launcher','-I','-B','-S','/root/script'),observed_argv=('/runtime/image','-I','-B','-S','/root/script'),image='/runtime/image',image_hash='a'*64)
        wrapper=SandboxBinding(inner,'/usr/bin/sandbox-exec','b'*64,'/root/profile','c'*64)
        self.assertEqual(wrapper.command,('/usr/bin/sandbox-exec','-f','/root/profile')+inner.command)
        self.assertEqual(wrapper.observed_argv,inner.observed_argv)
        self.assertEqual(wrapper.image_hash,inner.image_hash)
    def exercise(self,root,kind,confined,*,allowed=None,denial='OS_DENIAL_REPORT_MATCH',cleanup=True):
        c=types.SimpleNamespace(root=root,manifest={'nonce':'a'*64,'cwd':str(root),'terminal_binding':{'host':{'system':'Darwin'}},'tool_pins':{'/usr/bin/sandbox-exec':'b'*64,'/usr/bin/log':'c'*64}},clock=lambda:1,check=lambda *a:None)
        label=kind+('-confined' if confined else '-baseline')
        def execute(binding,startup,deadline,on_tick):
            text=(root/(label+'.py')).read_text();tree=ast.parse(text)
            descriptor=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='D' for t in n.targets)))
            publish(Path(descriptor['record']),canonical({'nonce':'a'*64,'descriptor_parent':descriptor['parent'],'outcome':'DENIED' if confined else 'ALLOWED','errno':13 if confined else None}))
            pid=202 if confined else 201
            observed=ProcessObservation(pid,100,'2026-09-17T00:00:00+00:00','/runtime/image','/runtime/image','d'*64,str(root),('/runtime/image',))
            owner=types.SimpleNamespace(registered=observed,child=types.SimpleNamespace(pid=pid),verify=Mock())
            on_tick(owner);owner.verify.assert_called()
            self.assertTrue(Path(descriptor['release']).exists())
            return {'report':canonical({'status':'PROBE_COMPLETE','descriptor_parent':descriptor['parent']}),'ownership':owner_rows(),'cleanup':dict(owner_cleanup(),verified=cleanup)}
        c.execute_owned=execute
        target='127.0.0.1:38494' if kind=='network' else str(root/'dummy')
        if kind!='network' and not Path(target).exists():publish(Path(target),b'IIOS_DISPOSABLE_DUMMY\n')
        result={'category':denial,'matches':1 if denial=='OS_DENIAL_REPORT_MATCH' else 0,'collector_exit_verified':True,'collector_exit':0}
        # collect_comparison's transport installation is tested separately; here
        # use the real controlled comparison validator with only OS collection substituted.
        def collect(context,a,d,spec,owner):
            from alpha_observation_qualification import controlled_denial
            from provider_gateway_contract import content_hash
            with patch('alpha_denial_collector.collect',return_value=result):
                return controlled_denial(a,d,spec,content_hash(spec),owner=owner,owner_parent=content_hash(owner),comparison_parent=content_hash({'allowed':a,'denied':d}))
        with patch('iios_native_confinement.collect_comparison',side_effect=collect):
            return trial(c,kind=kind,confined=confined,launcher={'path':'/runtime/launcher','sha256':'a'*64},image={'path':'/runtime/image','sha256':'d'*64},profile={'path':str(root/'profile'),'sha256':'e'*64},root=root,target=target,deadline=1000,allowed=allowed)
    def test_all_four_real_comparison_validators(self):
        for kind in CHECKS:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();baseline=self.exercise(root,kind,False)
                confined=self.exercise(root,kind,True,allowed=baseline['trial'])
                self.assertEqual(confined['correlation']['attribution'],'CONTROLLED_CORRELATED_DENIAL')
                self.assertFalse(confined['correlation']['confinement_qualified'])
    def test_errno_without_os_report_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();baseline=self.exercise(root,'filesystem',False)
            with self.assertRaises(QualificationFailure) as caught:self.exercise(root,'filesystem',True,allowed=baseline['trial'],denial='UNKNOWN')
            self.assertEqual(caught.exception.detail['predicate'],'CONFINEMENT_ATTRIBUTED_DENIAL')
            self.assertFalse((root/'filesystem-confined-release.json').exists())
    def test_owner_receipt_rejects_incomplete_and_boolean_counts(self):
        from iios_native_ownership import verify_execution
        good={'ownership':owner_rows(),'cleanup':owner_cleanup()}
        self.assertTrue(verify_execution(good,'DISPOSABLE_CONFINEMENT_AND_LIFECYCLE'))
        import copy
        for mutate in (lambda x:x['ownership'].pop(),lambda x:x['ownership'][0]['matches'].update(argv=False),
                       lambda x:x['ownership'][0].update(sample=True),lambda x:x['cleanup'].update(signals=False),
                       lambda x:x['cleanup'].update(independently_absent=False)):
            value=copy.deepcopy(good);mutate(value)
            with self.assertRaises(QualificationFailure):verify_execution(value,'DISPOSABLE_CONFINEMENT_AND_LIFECYCLE')
    def test_partial_cleanup_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(QualificationFailure) as caught:self.exercise(Path(directory).resolve(),'filesystem',False,cleanup=False)
            self.assertEqual(caught.exception.detail['predicate'],'OWNERSHIP_COMPLETE_CLEANUP')

if __name__=='__main__':unittest.main()
