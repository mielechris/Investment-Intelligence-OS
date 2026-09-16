"""Disposable non-executable input bytes; never runs an assembled interpreter."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from provider_gateway_contract import content_hash
from deployment_contract import digest, RUNTIME_MANIFEST_SCHEMA
from test_alpha_session_evidence import write, seal_directories

path = Path(__file__).resolve().parents[2] / 'scripts/alpha_production_runtime.py'
loader = importlib.util.spec_from_file_location('alpha_production_runtime', path)
runtime = importlib.util.module_from_spec(loader); loader.loader.exec_module(runtime)


class RuntimeAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='iios-provider-connection-source-tests-assembly-')
        self.base = Path(self.temp.name).resolve(); self.base.chmod(0o700)
        self.inputs = self.base/'inputs'; self.inputs.mkdir()
        self.output = self.base/'output'; self.output.mkdir(mode=0o700)
        self.rows = [write(self.inputs, 'bin/python3.14', b'NOT EXECUTABLE TEST DATA', 0o500),
                     write(self.inputs, 'lib/python3.14/site-packages/example-1.0.dist-info/METADATA', b'Name: example\nVersion: 1.0\n'),
                     write(self.inputs, 'tls/ca.pem', b'SYNTHETIC PUBLIC CERTIFICATE PLACEHOLDER')]
        seal_directories(self.inputs)
        self.lock = b'example==1.0\n'; self.lock_hash = hashlib.sha256(self.lock).hexdigest()
        self.spec = dict(schema=runtime.SCHEMA, source_commit='a'*40, input_root=str(self.inputs),
            output_parent=str(self.output), output_name='runtime-test', files=self.rows, interpreter='bin/python3.14',
            tls_bundle='tls/ca.pem', platform_dependencies=[], provenance=dict.fromkeys(runtime.PROVENANCE, 'b'*64),
            lock_sha256=self.lock_hash, python_version='3.14.7', system='Darwin', architecture='arm64')
        self.args = dict(source_commit='a'*40, approved_input_root=str(self.inputs),
            approved_output_parent=str(self.output), approved_platform_paths=(), lock_bytes=self.lock,
            expected_lock_hash=self.lock_hash)

    def tearDown(self):
        for p in self.base.rglob('*'):
            if p.is_dir() and not p.is_symlink(): p.chmod(0o700)
        self.temp.cleanup()

    def build(self): return runtime.assemble(self.spec, content_hash(self.spec), **self.args)

    def test_exact_manifest_bytes_sealed_and_no_execution(self):
        with patch('subprocess.run', side_effect=AssertionError('NO_NATIVE')):
            result = self.build()
        m = result['manifest']; out = self.output/'runtime-test'
        self.assertEqual(m['schema'], RUNTIME_MANIFEST_SCHEMA); self.assertEqual(m['content_hash'], digest(m))
        self.assertEqual(m['release_commit'], 'a'*40); self.assertEqual(m['file_inventory'], sorted(self.rows, key=lambda r:r['path']))
        self.assertEqual(hashlib.sha256((out/'runtime-manifest.json').read_bytes()).hexdigest(), result['manifest_sha256'])
        self.assertEqual(out.stat().st_mode & 0o777, 0o500)
        self.assertFalse(result['execution_authorized']); self.assertFalse(result['production_qualified'])
        self.assertTrue(all(v is False for v in result['authority'].values()))

    def test_independent_pin_and_source_required(self):
        with self.assertRaises(ValueError): runtime.assemble(self.spec, 'f'*64, **self.args)
        self.args['source_commit'] = 'c'*40
        with self.assertRaisesRegex(ValueError, 'BUILD_SOURCE'): self.build()
        self.assertFalse(list(self.output.iterdir()))

    def test_schema_target_provenance_lock_mutations(self):
        original = deepcopy(self.spec)
        for k,v in [('schema','iios-fresh-historical-runtime-v1'),('python_version','3.13.15'),
                    ('architecture','x86_64'),('provenance',{}),('lock_sha256','f'*64),('interpreter','bin/other')]:
            self.spec = original | {k:v}
            with self.subTest(k=k), self.assertRaises(ValueError): self.build()
        self.assertFalse(list(self.output.iterdir()))

    def test_lexical_roots_and_traversal_before_io(self):
        for path in ('/Users/example/Library/Keychains', '/protected/L7', '/bad//path', '/bad/../escape', '~', '/bad\x00path'):
            self.spec['input_root'] = path; self.args['approved_input_root'] = path
            with self.subTest(path=path), patch('os.open',side_effect=AssertionError('NO_IO')):
                with self.assertRaises(ValueError): self.build()

    def test_unapproved_root_before_io(self):
        self.args['approved_input_root'] = str(self.base/'different')
        with patch('os.open',side_effect=AssertionError('NO_IO')):
            with self.assertRaisesRegex(ValueError,'BUILD_ROOT_APPROVAL'): self.build()

    def test_existing_destination_preserved(self):
        out=self.output/'runtime-test';out.mkdir();(out/'kept').write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):self.build()
        self.assertEqual((out/'kept').read_bytes(),b'preserve')

    def test_output_symlink_parent_rejected(self):
        alias=self.base/'alias';alias.symlink_to(self.output,target_is_directory=True)
        self.spec['output_parent']=str(alias);self.args['approved_output_parent']=str(alias)
        with self.assertRaises(OSError):self.build()

    def test_input_symlink_hardlink_missing_extra(self):
        self.inputs.chmod(0o700);write(self.inputs,'extra',b'unlisted');self.inputs.chmod(0o500)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_EXTRA_FILE'):self.build()
        self.inputs.chmod(0o700);(self.inputs/'extra').unlink();self.inputs.chmod(0o500)
        os.link(self.inputs/'tls/ca.pem',self.base/'link')
        with self.assertRaisesRegex(ValueError,'EVIDENCE_FILE_IDENTITY'):self.build()

    def test_writable_or_wrong_owner_rejected(self):
        (self.inputs/'bin/python3.14').chmod(0o700)
        with self.assertRaises(ValueError): self.build()
        (self.inputs/'bin/python3.14').chmod(0o500)
        with patch('os.getuid',return_value=-1):
            with self.assertRaises(ValueError):self.build()

    def test_changed_size_hash_mode_and_duplicate(self):
        original=deepcopy(self.rows)
        for key,value in [('size',True),('size',64*1024*1024+1),('sha256','f'*64),('mode',0o777)]:
            self.spec['files']=deepcopy(original);self.spec['files'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.build()
        self.spec['files']=original+original[:1]
        with self.assertRaises(ValueError):self.build()

    def test_dependency_mismatch_and_duplicate_lock(self):
        self.args['lock_bytes']=b'example==2.0\n';self.args['expected_lock_hash']=hashlib.sha256(self.args['lock_bytes']).hexdigest()
        self.spec['lock_sha256']=self.args['expected_lock_hash']
        with self.assertRaisesRegex(ValueError,'BUILD_DEPENDENCIES'):self.build()
        with self.assertRaisesRegex(ValueError,'BUILD_LOCK_DUPLICATE'):runtime.lock_versions(b'a_b==1\na-b==1\n')

    def test_platform_independent_paths_and_immutable_checks(self):
        p=self.base/'platform';p.write_bytes(b'fake platform');p.chmod(0o400)
        row=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,mode=0o400)
        self.spec['platform_dependencies']=[row]
        with self.assertRaisesRegex(ValueError,'BUILD_PLATFORM_APPROVAL'):self.build()
        self.args['approved_platform_paths']=(str(p),);p.chmod(0o600)
        with self.assertRaises(ValueError):self.build()

    def test_interrupted_copy_preserved_without_manifest(self):
        real=runtime.copy_row;calls=[]
        def broken(*args):
            if calls:raise OSError('synthetic failure')
            calls.append(1);return real(*args)
        with patch.object(runtime,'copy_row',side_effect=broken):
            with self.assertRaises(OSError):self.build()
        out=self.output/'runtime-test'
        self.assertTrue((out/'bin/python3.14').exists());self.assertFalse((out/'runtime-manifest.json').exists())
        with self.assertRaises(FileExistsError):self.build()

    def test_manifest_publication_failure_never_returns_success(self):
        real=os.open
        def fail(name,*args,**kwargs):
            if name=='runtime-manifest.json':raise OSError('synthetic publish failure')
            return real(name,*args,**kwargs)
        with patch('os.open',side_effect=fail):
            with self.assertRaises(OSError):self.build()
        self.assertFalse((self.output/'runtime-test/runtime-manifest.json').exists())

    def test_source_mutation_during_copy_fails(self):
        real=runtime.copy_row
        def change(source,dest,row):
            real(source,dest,row)
            p=self.inputs/row['path'];p.chmod(0o600);p.write_bytes(b'changed');p.chmod(row['mode'])
        with patch.object(runtime,'copy_row',side_effect=change):
            with self.assertRaises(ValueError):self.build()
        self.assertFalse((self.output/'runtime-test/runtime-manifest.json').exists())


if __name__=='__main__':unittest.main()
