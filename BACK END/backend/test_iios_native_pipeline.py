"""Conductor integration with substituted macOS effects, never native evidence.

Actual stage adapters, journal, scope checks, runtime-policy compiler, runtime
report decoder, controlled-comparison validator and evidence exporter run here.
Assembly/signature tools, sealed-tree OS verification, and process effects are
substituted. Their lower-level contracts have separate guarded regressions.
"""
from contextlib import ExitStack
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch,Mock,MagicMock
from iios_native_conductor import STAGES,digest,canonical,QualificationFailure
from iios_native_evidence import verify_export
from iios_native_dispatcher import NativeContext,run
from iios_native_admission import ADAPTERS
from iios_native_assembly import publish
from iios_native_image_policy import build_policy
from truth_spine_process_identity import ProcessObservation
from test_iios_native_conductor import manifest
from test_iios_native_image_policy import inputs


def owner_rows():
    return [{'sample':x,'matches':dict.fromkeys(('pid','parent_pid','start_time_present','executable','executable_hash','argv','command','cwd','stable'),True)} for x in (1,2,3)]
def owner_cleanup():return {'verified':True,'outstanding':0,'exit_code':0,'reaped':True,'independently_absent':True,'signals':0}


class PipelineTests(unittest.TestCase):
    def execute(self,base,failed_stage=None):
        m=manifest();m['source']={'commit':'c'*40,'root':str(Path(__file__).parents[2]),'inventory':[]}
        m['output_parent']=str(base);m['output_name']='qualification-fixture';st=base.stat()
        m['output_parent_identity']=[st.st_dev,st.st_ino,st.st_uid,0o700]
        root=base/m['output_name'];execution=root/'payload/assembly-output/execution-01';runtime=execution/'output/runtime-pilot'
        m.update(cwd=str(base),environment={'LC_ALL':'C','TZ':'UTC','__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},historical_pids=[35731],terminal_binding={'host':{'system':'Darwin'}},tool_pins={'/usr/bin/sandbox-exec':'a'*64,'/usr/bin/log':'b'*64})
        true_hash=hashlib.sha256(Path('/usr/bin/true').read_bytes()).hexdigest();m['tool_pins']['/usr/bin/true']=true_hash
        fixture=inputs();f=fixture['manifest'];f['runtime_root']=str(runtime);f['interpreter']=str(runtime/'Python')
        fixture['plan']['runtime_root']=str(runtime)
        fixture['static']['manifest_sha256']=hashlib.sha256(canonical(f)).hexdigest()
        fixture['parents']={k:digest(v) for k,v in fixture.items() if k!='parents'}
        self.policy=build_policy(**fixture)
        def put(name,value):
            raw=canonical(value) if not isinstance(value,bytes) else value
            path=base/name;path.write_bytes(raw);return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}
        plan=put('plan.json',fixture['plan']);osref=put('os.json',fixture['os_reference']);standalone=put('standalone.json',fixture['standalone'])
        names=('ROOT','PREP','CA','APPROVED_IMPORTS','REQUIRED_IMPORTS','MODULE_FILES','IMAGE_MAXIMUM','IMAGE_REFERENCE_PARENT','EXPECTED_CACHE_UUID','SCOPE','SEALED_IMPORT_NAMES','IMAGE_PATHS','IMAGE_UUIDS')
        template='\n'.join(n+'=None' for n in names if n!='APPROVED_IMPORTS')+"\nAPPROVED_IMPORTS=('ssl','_tkinter')\ndef collect_inventory(*a):pass\ndef main():\n    ssl=import_one('ssl')\n    tk=import_one('_tkinter')\n"
        m['native']={'static_descriptor':{},'production_reference':{'plan':plan,'os_reference':osref,'standalone':standalone},
            'runtime_acceptance':{'template':put('template.py',template.encode()),'launcher_relative':'Python','image_relative':'Python','clock_contract':'FIXTURE'},
            'assembly':{'launch':{'launcher':'/fixture/launcher','launcher_hash':'a'*64,'image':'/fixture/image','image_hash':'b'*64}},
            'lifecycle':{'environment':{'LANG':'C','LC_ALL':'C','TZ':'UTC'},'dummy_executable':{'path':'/usr/bin/true','sha256':true_hash}}}
        for row in m['stages']:
            if row['id'] in ADAPTERS:
                path=Path(__file__).with_name(ADAPTERS[row['id']]);raw=path.read_bytes()
                row['native_binding']={'adapter_path':str(path),'adapter_sha256':hashlib.sha256(raw).hexdigest()}
        seen=[];audit=MagicMock();audit.verify.return_value='e'*64
        def assembly_prepare(context,budget,deadline):
            execution.mkdir(parents=True,mode=0o700)
            publish(execution/'ASSEMBLY-RESULT.json',canonical({'manifest':f,'manifest_sha256':fixture['static']['manifest_sha256'],'envelope_sha256':'f'*64,'status':'ASSEMBLED_BYTES_ONLY','scope':'PRIVATE_ASSEMBLY_BYTES_ONLY'}))
            script=root/'assembly.py';parent=publish(script,b'# substituted process entrypoint\n')
            return {},execution,script,parent,{}
        def lifecycle_prepare(context,parents,policy,deadline,budget):
            release=execution/'release';release.mkdir();control=execution/'control';control.mkdir()
            profile=control/'profile.sb';profile_hash=publish(profile,b'(version 1)\n(deny default)\n')
            config=execution/'qualification.json';publish(config,b'{}\n')
            doc={'roots':{'release':str(release),'control':str(control),'output':str(execution/'disposable')},'conductor':{'manifest':context.parent},'launch':{'startup_ns':100}}
            cap=Mock();cap.identity='c'*64;cap.document.return_value=doc
            return cap,{},config,{'path':str(profile),'sha256':profile_hash},'d'*64
        def owned(context,binding,startup,deadline,on_tick=None,environment=None):
            if context.stage==STAGES[4]:return {'report':b'{}','ownership':owner_rows(),'cleanup':owner_cleanup()}
            path=Path(binding.inner.script if hasattr(binding,'inner') else binding.script)
            text=path.read_text()
            import ast
            tree=ast.parse(text);d=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='D' for t in n.targets)))
            if 'config' in d:
                (execution/'disposable').mkdir()
                fixed={'scope':'DISPOSABLE_NATIVE_QUALIFICATION_ONLY','production_qualified':False,'provider_access':False,'credential_access':False,'seeded':True,'requests_attempted':0,'broker_connected':False,'paper_order_permission':False,'trade_execution_permission':False,'live_execution':False}
                from provider_gateway_contract import locked_authority
                result=dict(fixed,schema='iios-disposable-functional-result-v1',status='FUNCTIONAL_PASS',admission_parent='c'*64,primary_failure=None,
                    cleanup=dict(fixed,verified=True,cooperative=True,port_clear=[True]*3,listener_owner_reconciled=True,roles=['scheduler','publisher','backend'],failures=[]),
                    provider_requests=0,seed_records=3,confinement='UNQUALIFIED_UNTIL_CONTROLLED_COMPARISONS',authority=locked_authority(),
                    http=[dict(fixed,method=m,status=200,tls_verified=True,provider_requests=0) for m in ('GET','HEAD')])
            else:
                confined=hasattr(binding,'inner');pid=201 if confined else 200
                publish(Path(d['record']),canonical({'nonce':m['nonce'],'descriptor_parent':d['parent'],'outcome':'DENIED' if confined else 'ALLOWED','errno':13 if confined else None}))
                observation=ProcessObservation(pid,100,'2026-09-17T00:00:00+00:00',str(runtime/'Python'),str(runtime/'Python'),'a'*64,str(base),(str(runtime/'Python'),))
                owner=types.SimpleNamespace(registered=observation,child=types.SimpleNamespace(pid=pid),verify=Mock())
                on_tick(owner)
                result={'status':'PROBE_COMPLETE','descriptor_parent':d['parent']}
            return {'report':canonical(result),'ownership':owner_rows(),'cleanup':owner_cleanup()}
        def runtime_owned(context,*args):
            policy=args[2];images=[{k:r[k] for k in ('path','uuid')} for r in policy['rows']];scan={'complete':True,'count':len(images),'images':images}
            result={'scope':policy['scope'],'policy_parent':digest(policy),'imports':policy['imports'],'scans':[scan,scan],
                'origins':[{'module':'ssl','file':'lib/_ssl.so'}],'cache_uuids':[policy['cache_uuid']]*2,'stage':'COMPLETE',
                'ca_sha256':'9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f','ca_count':121,'tls_context_only':True}
            return {'report':canonical(result),'ownership':owner_rows(),'cleanup':owner_cleanup()}
        original_receipt=NativeContext.receipt
        def receipt(context,row,*args,**kw):
            seen.append(row['id'])
            if row['id']==failed_stage:raise QualificationFailure(row['id'],'SUBSTITUTED_EFFECT_DENIED','PASS','DENIED',exception='PermissionError',errno_category='EPERM')
            return original_receipt(context,row,*args,**kw)
        # Loading the exact adapter file still occurs. Only its effectful helper
        # globals are replaced at that boundary, preserving run_stage itself.
        original_exec=exec
        def load(code,namespace):
            original_exec(code,namespace)
            filename=Path(namespace['__file__']).name
            if filename=='iios_native_assembly.py':namespace['prepare']=assembly_prepare
            if filename=='iios_native_image_policy.py':namespace['pin_file']=lambda *a:None
            if filename=='iios_native_static.py':namespace['verify']=lambda *a,**kw:copy.deepcopy(fixture['static'])
            if filename=='iios_native_lifecycle.py':namespace['prepare']=lifecycle_prepare
        with ExitStack() as stack:
            for target,value in [('iios_native_dispatcher.require_execution_ready',None),('iios_native_dispatcher.admit_source',True),('iios_native_dispatcher.admit_terminal',True),('alpha_runtime_files.verify_manifest',True),('iios_native_image_policy.pin_file',True)]:
                stack.enter_context(patch(target,return_value=value))
            stack.enter_context(patch('iios_native_dispatcher.exec',side_effect=load,create=True))
            stack.enter_context(patch('iios_native_dispatcher.clock',return_value=10))
            stack.enter_context(patch('iios_native_dispatcher.time.time',return_value=100))
            stack.enter_context(patch.object(NativeContext,'inspect',return_value=None))
            stack.enter_context(patch.object(NativeContext,'tool',return_value=(0,b'11111111-1111-1111-1111-111111111111\n',b'')))
            stack.enter_context(patch.object(NativeContext,'execute_owned',owned))
            stack.enter_context(patch.object(NativeContext,'run_owned_runtime',runtime_owned))
            stack.enter_context(patch.object(NativeContext,'receipt',receipt))
            stack.enter_context(patch('iios_native_sealer.Sealer',return_value=types.SimpleNamespace(done=True)))
            stack.enter_context(patch('alpha_denial_collector.collect',return_value={'category':'OS_DENIAL_REPORT_MATCH','matches':1,'collector_exit_verified':True,'collector_exit':0}))
            result=run(m,digest(m),audit=audit)
        return result,seen,root,m
    def test_complete_pipeline_exports_native_receipt_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve();base.chmod(0o700)
            result,seen,root,m=self.execute(base)
            self.assertEqual(result['status'],'GREEN',result)
            self.assertEqual(seen,list(STAGES));self.assertEqual(verify_export(root,digest(m)),result)
            self.assertEqual(result['history']['attempt10'],'UNVERIFIED')
            self.assertTrue(all(v is False for v in result['authority'].values()))
    def test_every_stage_failure_stops_and_exports_exact_predicate(self):
        for index,stage in enumerate(STAGES):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as directory:
                base=Path(directory).resolve();base.chmod(0o700)
                result,seen,root,m=self.execute(base,stage)
                self.assertEqual(result['primary_failure']['predicate'],'SUBSTITUTED_EFFECT_DENIED',result)
                self.assertEqual(seen,list(STAGES[:index+1]));self.assertNotEqual(result['status'],'GREEN')
                self.assertEqual(verify_export(root,digest(m)),result)

if __name__=='__main__':unittest.main()
