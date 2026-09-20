import copy
import importlib.machinery
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'BACK END/backend'))
from iios_qualification_v2 import cli, provenance as p, runtime
from iios_qualification_v2.state import Store, STAGES, digest, file_hash, sanitized

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.root.chmod(0o700)
        self.binding=dict(commit='a'*40,inventory_sha256='b'*64,inventory=[
            dict(path=str(f.relative_to(ROOT)),sha256=file_hash(f))
            for f in (ROOT/'BACK END/backend/iios_qualification_v2').glob('*.py')])
        self.context=dict(source='a'*40,boot='boot',previous='c'*64,issuer_sha256='d'*64,output_root=str(self.root))
    def tearDown(self):
        for f in self.root.rglob('*'):
            if f.is_dir():f.chmod(0o700)
        self.temp.cleanup()
    def modules(self):return {n:m for n,m in sys.modules.items() if n==p.PREFIX or n.startswith(p.PREFIX+'.')}
    def test_source_only_loader_compiles_source_and_ignores_cache(self):
        source=self.root/'example.py';source.write_text('value=17\n')
        cache=self.root/'__pycache__';cache.mkdir();(cache/'example.cpython-314.pyc').write_bytes(b'untrusted-bytecode')
        loader=cli._QualificationSourceLoader('example',str(source));namespace={}
        exec(loader.get_code('example'),namespace)
        self.assertEqual(namespace['value'],17);self.assertEqual(loader.source_sha256,file_hash(source))
        self.assertEqual((cache/'example.cpython-314.pyc').read_bytes(),b'untrusted-bytecode')
    def test_ordinary_loader_cannot_assert_source_only(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_ONLY_LOADER_REQUIRED'):
            p.module_inventory(ROOT,self.binding,source_only=True)
    def test_actual_loaded_module_inventory(self):
        rows=p.module_inventory(ROOT,self.binding)
        self.assertTrue(rows);self.assertTrue(all(r['loader_origin']=='SOURCE_FILE' for r in rows))
        self.assertTrue(all(len(r['loaded_code_sha256'])==64 for r in rows))
    def test_alternate_root_and_module_path_rejected(self):
        with self.assertRaisesRegex(ValueError,'ROOT'):p.module_inventory(self.root,self.binding)
        module=types.ModuleType(p.PREFIX+'.runtime');module.__dict__.update(vars(runtime));module.__file__=str(self.root/'runtime.py')
        modules=self.modules();modules[p.PREFIX+'.runtime']=module
        with self.assertRaisesRegex(ValueError,'ROOT'):p.module_inventory(ROOT,self.binding,modules)
    def test_bytecode_loader_and_existing_cache_rejected(self):
        modules=self.modules();m=types.ModuleType(p.PREFIX+'.runtime');m.__dict__.update(vars(runtime));modules[p.PREFIX+'.runtime']=m
        m.__loader__=importlib.machinery.SourcelessFileLoader(m.__name__,str(self.root/'runtime.pyc'))
        with self.assertRaisesRegex(ValueError,'BYTECODE_OR_LOADER'):p.module_inventory(ROOT,self.binding,modules)
        m.__loader__=runtime.__loader__;cache=self.root/'runtime.pyc';cache.write_bytes(b'cached');m.__cached__=str(cache)
        with self.assertRaisesRegex(ValueError,'BYTECODE_CACHE'):p.module_inventory(ROOT,self.binding,modules)
    def test_source_hash_and_loader_origin_substitution_rejected(self):
        binding=copy.deepcopy(self.binding)
        for row in binding['inventory']:
            if row['path'].endswith('/runtime.py'):row['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'MODULE_HASH'):p.module_inventory(ROOT,binding)
        modules=self.modules();m=types.ModuleType(p.PREFIX+'.runtime');m.__dict__.update(vars(runtime));modules[p.PREFIX+'.runtime']=m
        m.__spec__=types.SimpleNamespace(origin=str(self.root/'runtime.py'),loader=m.__loader__)
        with self.assertRaisesRegex(ValueError,'LOADER_ORIGIN'):p.module_inventory(ROOT,self.binding,modules)
    def test_in_memory_function_substitution_rejected(self):
        modules=self.modules();m=types.ModuleType(p.PREFIX+'.runtime');m.__dict__.update(vars(runtime));modules[p.PREFIX+'.runtime']=m
        def substituted():return 'altered'
        substituted.__module__=m.__name__;m.source_identity=substituted
        with self.assertRaisesRegex(ValueError,'LOADED_CODE_SUBSTITUTION'):p.module_inventory(ROOT,self.binding,modules)
    def test_imported_function_cannot_replace_defined_module_function(self):
        modules=self.modules();m=types.ModuleType(p.PREFIX+'.runtime');m.__dict__.update(vars(runtime));modules[p.PREFIX+'.runtime']=m
        m.source_identity=lambda:None
        with self.assertRaisesRegex(ValueError,'MODULE_SUBSTITUTION'):p.module_inventory(ROOT,self.binding,modules)
    def test_fresh_nonce_stale_future_replay_and_pid_reuse(self):
        obs={'process':{'pid':123,'start_time':'first'},'bytecode_disabled':True}
        receipt=p.launch_receipt(obs,context=self.context)
        self.assertNotEqual(receipt['nonce'],p.launch_receipt(obs,context=self.context)['nonce'])
        p.validate_launch(receipt,obs,context=self.context,records=[])
        for now in (receipt['monotonic_ns']-1,receipt['monotonic_ns']+60_000_000_001):
            with self.assertRaisesRegex(ValueError,'STALE'):p.validate_launch(receipt,obs,context=self.context,records=[],now_ns=now)
        with self.assertRaisesRegex(ValueError,'REPLAY'):
            p.validate_launch(receipt,obs,context=self.context,records=[dict(event='CONTROLLER_LAUNCH',data=receipt)])
        changed=copy.deepcopy(obs);changed['process']['start_time']='reused'
        with self.assertRaisesRegex(ValueError,'BINDING'):p.validate_launch(receipt,changed,context=self.context,records=[])
        for key in self.context:
            changed=dict(self.context);changed[key]='other'
            with self.assertRaisesRegex(ValueError,'BINDING'):p.validate_launch(receipt,obs,context=changed,records=[])
    def test_scrubbed_environment_never_hashes_secrets(self):
        a=p.environment_projection({'API_KEY':'SECRET_ONE','PATH':'secret-path','PYTHONPATH':'secret-value'})
        b=p.environment_projection({'API_KEY':'SECRET_TWO','PATH':'other-secret','PYTHONPATH':'other-value'})
        self.assertEqual(digest(a),digest(b));self.assertNotIn('SECRET',json.dumps(a));self.assertEqual(a['PATH'],'OTHER')
    def interpreter_fixture(self):
        config=dict(vendor_python=str(p.LAUNCHER),vendor_framework_inventory_sha256='c'*64,
            vendor_framework_inventory_entries=[
                dict(path=str(p.LAUNCHER.relative_to(p.FRAMEWORK)),type='file',sha256='a'*64),
                dict(path=str(p.IMAGE.relative_to(p.FRAMEWORK)),type='file',sha256='b'*64)])
        process=types.SimpleNamespace(pid=os.getpid(),parent_pid=os.getppid(),start_time='2026-09-20T20:00:00+00:00',cwd=str(ROOT),
            argv=(str(p.IMAGE),'-I','-B','-S',str(ROOT/'BACK END/backend/iios_qualification_v2/cli.py'),'--profile','observation','--resume'),
            executable=str(p.IMAGE),executable_hash='b'*64)
        return config,process
    def test_framework_launcher_and_process_image_are_distinct_and_both_pinned(self):
        config,process=self.interpreter_fixture()
        self.assertNotEqual(str(p.LAUNCHER),process.executable)
        with patch.object(sys,'executable',str(p.LAUNCHER)),patch.object(Path,'resolve',lambda path,strict=False:path),\
                patch.object(p,'file_hash',side_effect=lambda path:{p.LAUNCHER:'a'*64,p.IMAGE:'b'*64}[path]):
            result=p.controller_interpreter(config,process)
        self.assertEqual(result['launcher_sha256'],'a'*64);self.assertEqual(result['image_sha256'],'b'*64)
        self.assertEqual(result['framework_inventory_sha256'],config['vendor_framework_inventory_sha256'])
    def test_controller_rejects_unpinned_launcher_image_hash_and_kernel_argv(self):
        for mutation,predicate in (
            ('launcher_path','CONTROLLER_LAUNCHER_PATH'),('launcher_hash','CONTROLLER_LAUNCHER_HASH'),
            ('image_path','CONTROLLER_IMAGE_PATH'),('image_hash','CONTROLLER_IMAGE_HASH'),
            ('image_disk_hash','CONTROLLER_IMAGE_HASH'),('argv0','CONTROLLER_ARGV_IMAGE'),
            ('duplicate_pin','CONTROLLER_INTERPRETER_PIN'),('missing_pin','CONTROLLER_INTERPRETER_PIN')):
            with self.subTest(mutation=mutation):
                config,process=self.interpreter_fixture();hashes={p.LAUNCHER:'a'*64,p.IMAGE:'b'*64};executable=str(p.LAUNCHER)
                if mutation=='launcher_path':executable='/alternate/python3.14'
                if mutation=='launcher_hash':hashes[p.LAUNCHER]='d'*64
                if mutation=='image_path':process.executable='/alternate/Python'
                if mutation=='image_hash':process.executable_hash='d'*64
                if mutation=='image_disk_hash':hashes[p.IMAGE]='d'*64
                if mutation=='argv0':process.argv=(str(p.LAUNCHER),*process.argv[1:])
                if mutation=='duplicate_pin':config['vendor_framework_inventory_entries']*=2
                if mutation=='missing_pin':config['vendor_framework_inventory_entries']=[]
                with patch.object(sys,'executable',executable),patch.object(Path,'resolve',lambda path,strict=False:path),\
                        patch.object(p,'file_hash',side_effect=lambda path:hashes[path]):
                    with self.assertRaisesRegex(ValueError,predicate):p.controller_interpreter(config,process)
    def test_observation_binds_kernel_argv_flags_environment_and_process(self):
        config,obs=self.interpreter_fixture()
        flags=types.SimpleNamespace(dont_write_bytecode=1,isolated=1,no_site=1,ignore_environment=1,optimize=0)
        env={'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC','HOME':str(Path.home()),'PYTHONDONTWRITEBYTECODE':'1'}
        with patch.object(sys,'flags',flags),patch.object(sys,'dont_write_bytecode',True),patch.dict(os.environ,env,clear=True),\
                patch.object(p,'module_inventory',return_value=[]),patch.object(sys,'executable',str(p.LAUNCHER)),\
                patch.object(Path,'resolve',lambda path,strict=False:path),\
                patch.object(p,'file_hash',side_effect=lambda path:{p.LAUNCHER:'a'*64,p.IMAGE:'b'*64}.get(path,'e'*64)):
            result=p.observe(ROOT,self.binding,lambda _:obs,config=config)
            self.assertEqual(result['argv_category'],'ISOLATED_OBSERVATION_RESUME')
            self.assertEqual(result['interpreter']['image'],str(p.IMAGE))
            for field,value,predicate in [('pid',-1,'CONTROLLER_PID'),('parent_pid',-1,'CONTROLLER_PARENT_PID'),
                    ('start_time','','CONTROLLER_START_TIME'),('cwd','/alternate','CONTROLLER_CWD')]:
                before=getattr(obs,field);setattr(obs,field,value)
                with self.assertRaisesRegex(ValueError,predicate):p.observe(ROOT,self.binding,lambda _:obs,config=config)
                setattr(obs,field,before)
            with self.assertRaisesRegex(ValueError,'CONTROLLER_PROCESS_PRESENT'):p.observe(ROOT,self.binding,lambda _:None,config=config)
            flags.dont_write_bytecode=0
            with self.assertRaisesRegex(ValueError,'BYTECODE_FLAGS'):p.observe(ROOT,self.binding,lambda _:obs,config=config)
            flags.dont_write_bytecode=1;obs.argv=obs.argv+('--unknown',)
            with self.assertRaisesRegex(ValueError,'ARGV'):p.observe(ROOT,self.binding,lambda _:obs,config=config)
    def test_controller_predicate_is_preserved_in_chain_and_sanitized_export(self):
        store=Store(self.root/'controller-predicate');calls=[]
        def failed_observation():
            p.require(False,'CONTROLLER_IMAGE_HASH')
        stages={name:(lambda:calls.append('stage') or {}) for name in STAGES[:-1]}
        result=cli.execute(store,stages,source='a'*40,boot='b',resume=False,issuer={'launch_mode':'local_app'},
            evidence=self.root/'evidence',controller=failed_observation)
        self.assertEqual(calls,['stage']) # cleanup only; no runtime or child operation
        self.assertEqual(result['failure']['predicate'],'CONTROLLER_IMAGE_HASH')
        self.assertEqual(result['failure']['exception']['predicate'],'CONTROLLER_IMAGE_HASH')
        self.assertEqual(next(r['data'] for r in store.load() if r['event']=='STAGE_FAILED'),result['failure'])
        exported=json.loads((Path(result['export'])/'summary.json').read_text())
        self.assertEqual(exported['failure'],result['failure']);self.assertIsNone(exported['controller_launch'])
    def test_predicate_export_accepts_only_exact_known_builtin_codes(self):
        for message in ('password=SECRET','CONTROLLER_IMAGE_HASH password=SECRET','CONTROLLER_UNREVIEWED'):
            error=ValueError(message)
            self.assertEqual(p.exception_predicate(error),'BOUNDED_EXCEPTION_EVIDENCE')
            self.assertNotIn('SECRET',json.dumps(p.exception_evidence(error,ROOT,stage='controller_launch')))
        class Custom(ValueError):pass
        self.assertEqual(p.exception_predicate(Custom('CONTROLLER_IMAGE_HASH')),'BOUNDED_EXCEPTION_EVIDENCE')
    def test_uncaught_exception_is_chained_and_exported_without_secrets(self):
        store=Store(self.root/'state');calls=[]
        def runtime_failure():
            calls.append('runtime');raise FileNotFoundError(2,'password=SECRET',str(ROOT/'bazel-out'))
        stages={name:(lambda:{'verified':True}) for name in STAGES[:-1]};stages['runtime']=runtime_failure
        result=cli.execute(store,stages,source='a'*40,boot='b',resume=False,issuer={'launch_mode':'local_app'},
            evidence=self.root/'evidence',controller=lambda:{'fixture':True})
        self.assertEqual(result['status'],'RED');self.assertEqual(calls,['runtime'])
        records=store.load();launch=next(r for r in records if r['event']=='CONTROLLER_LAUNCH')
        failure=next(r for r in records if r['event']=='STAGE_FAILED')
        self.assertLess(launch['sequence'],failure['sequence']);self.assertEqual(digest(sanitized(launch['data'])),result['controller_sha256'])
        self.assertEqual(failure['data'],result['failure'])
        detail=result['failure']['exception'];self.assertEqual(detail['target_category'],'GENERATED_SOURCE_BAZEL_OUT')
        self.assertEqual(detail['controller_sha256'],result['controller_sha256']);self.assertIsNotNone(detail['call_site'])
        export=json.loads((Path(result['export'])/'summary.json').read_text())
        self.assertEqual(digest(export['controller_launch']),export['controller_sha256'])
        self.assertEqual(export,sanitized({k:v for k,v in result.items() if k!='export'}))
        self.assertNotIn('SECRET',json.dumps(records));self.assertNotIn('password=',json.dumps(export))
    def test_missing_or_changed_controller_blocks_runtime(self):
        for changed in (False,True):
            calls=[];stages={name:(lambda:calls.append('stage') or {}) for name in STAGES[:-1]}
            observations=iter([{'value':1},{'value':2}])
            result=cli.execute(Store(self.root/str(changed)),stages,source='s',boot='b',resume=False,
                issuer={'launch_mode':'local_app'},evidence=self.root/'evidence',controller=(lambda:next(observations)) if changed else None)
            self.assertEqual(result['failure']['stage'],'controller_launch');self.assertEqual(calls,['stage']) # cleanup only
    def test_traceback_is_bounded_and_exact_for_external_frame(self):
        def recurse(n):
            if n:return recurse(n-1)
            raise RuntimeError('bearer SECRET')
        try:recurse(60)
        except RuntimeError as error:detail=p.exception_evidence(error,ROOT,stage='runtime')
        self.assertTrue(detail['truncated']);self.assertEqual(len(detail['frames']),32)
        self.assertEqual(detail['call_site']['path'],'EXTERNAL');self.assertEqual(detail['call_site_sha256'],digest(detail['call_site']))
        self.assertNotIn('SECRET',json.dumps(detail))
