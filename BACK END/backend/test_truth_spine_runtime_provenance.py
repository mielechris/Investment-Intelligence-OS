import unittest
import json
from copy import deepcopy
from truth_spine_contract import seal
from truth_spine_lineage import file_hash
from test_truth_spine_lineage import retained_root, pin
from truth_spine_runtime_provenance import assemble, verify_runtime, validate_inputs


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root=retained_root('runtime');self.sources=self.root/'toolchain';self.sources.mkdir()
        self.run=self.root/'fresh';self.run.mkdir()
        rows=[]
        for name,data,mode in [('python',b'SYNTHETIC_EXECUTABLE',0o500),('config',b'home = /synthetic/toolchain\n',0o400)]:
            p=self.sources/name;p.write_bytes(data);p.chmod(mode)
            rows.append({'target':'bin/python' if name=='python' else 'pyvenv.cfg','pin':pin(p),'mode':mode})
        self.spec={'files':rows,'platform_dependencies':[rows[0]['pin']],'process_executable':rows[0]['pin'],'interpreter':'bin/python'}

    def test_fresh_runtime_binds_actual_root_commit_and_interpreter(self):
        r=assemble(self.run,self.spec,'a'*40,'b'*64)
        m={'source_base':'a'*40,'lineage':{'package_generation':'b'*64},'runtime_root':str(self.run/'runtime'),'interpreter_hash':r['interpreter_sha256']}
        self.assertEqual(verify_runtime(self.run,m,r),self.run/'runtime/bin/python')
        for key,value in [('source_commit','c'*40),('installed_root','/private/tmp/another'),('interpreter_relative','../python')]:
            bad=seal({**r,key:value})
            with self.assertRaises(ValueError):verify_runtime(self.run,m,bad)

    def test_no_old_manifest_input(self):
        bad=deepcopy(self.spec);bad['files'][1]['target']='runtime-manifest.json'
        with self.assertRaises(ValueError):validate_inputs(bad)

    def test_extra_runtime_file_rejected(self):
        r=assemble(self.run,self.spec,'a'*40,'b'*64)
        (self.run/'runtime/extra').write_bytes(b'EXTRA')
        m={'source_base':'a'*40,'lineage':{'package_generation':'b'*64},'runtime_root':str(self.run/'runtime'),'interpreter_hash':r['interpreter_sha256']}
        with self.assertRaises(ValueError):verify_runtime(self.run,m,r)

    def test_missing_external_input_precedes_runtime_creation(self):
        bad=deepcopy(self.spec);bad['platform_dependencies']=[]
        with self.assertRaises(ValueError):assemble(self.run,bad,'a'*40,'b'*64)
        self.assertFalse((self.run/'runtime').exists())
