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

    def copy_one(self, *, metadata=None):
        a=os.open(self.inputs,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        b=os.open(self.output,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:return runtime.copy_row(a,b,self.rows[0],metadata=metadata)
        finally:os.close(a);os.close(b)

    def test_metadata_copy_precedes_sealing_with_no_executable_temporary_mode(self):
        import alpha_runtime_files as rf
        events=[]
        def metadata(a,b,expected):
            self.assertEqual(os.fstat(a).st_mode & 0o777,0o500)
            self.assertEqual(os.fstat(b).st_mode & 0o777,0o600)
            events.append('metadata');return {}
        with patch.object(rf,'copy_runtime_metadata',side_effect=metadata):self.copy_one(metadata={})
        self.assertEqual(events,['metadata'])
        p=self.output/self.rows[0]['path']
        self.assertEqual(p.stat().st_mode & 0o777,0o500)
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),self.rows[0]['sha256'])

    def test_failed_metadata_copy_seals_closes_and_preserves_partial_file(self):
        import alpha_runtime_files as rf
        seen=[]
        def fail(a,b,m):seen.append((a,b));raise ValueError('RUNTIME_XATTR_COPY')
        with patch.object(rf,'copy_runtime_metadata',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'RUNTIME_XATTR_COPY') as caught:self.copy_one(metadata={})
        self.assertEqual(caught.exception.copy_file_identity['sha256'],self.rows[0]['sha256'])
        self.assertEqual(caught.exception.copy_file_identity['path_sha256'],hashlib.sha256(self.rows[0]['path'].encode()).hexdigest())
        self.assertNotIn('path',caught.exception.copy_file_identity)
        self.assertEqual((self.output/self.rows[0]['path']).stat().st_mode & 0o777,0o500)
        for fd in seen[0]:
            with self.assertRaises(OSError):os.fstat(fd)
        with self.assertRaises(FileExistsError):self.copy_one(metadata={})

    def test_primary_copy_failure_and_secondary_seal_failure_remain_separate(self):
        import alpha_runtime_files as rf
        real=os.fchmod;error=ValueError('RUNTIME_XATTR_COPY')
        def seal(fd,mode):
            if mode==0o500:raise OSError('untrusted cleanup detail')
            return real(fd,mode)
        with patch.object(rf,'copy_runtime_metadata',side_effect=error),patch.object(os,'fchmod',side_effect=seal):
            with self.assertRaisesRegex(ValueError,'RUNTIME_XATTR_COPY') as caught:self.copy_one(metadata={})
        self.assertIs(caught.exception,error)
        self.assertEqual(caught.exception.copy_cleanup_failure,'BUILD_COPY_SEAL')

    def test_seal_failure_never_reports_success(self):
        real=os.fchmod
        def seal(fd,mode):
            if mode==0o500:raise OSError('untrusted cleanup detail')
            return real(fd,mode)
        with patch.object(os,'fchmod',side_effect=seal):
            with self.assertRaisesRegex(ValueError,'BUILD_COPY_SEAL'):self.copy_one()

    def test_invalid_final_copy_mode_rejected_before_open(self):
        self.rows[0]['mode']=0o700
        with patch.object(os,'dup',side_effect=AssertionError('NO_DESCRIPTOR_COPY')):
            with self.assertRaisesRegex(ValueError,'BUILD_COPY_MODE'):runtime.copy_row(1,2,self.rows[0])

    def test_read_only_0400_file_also_sealed_after_metadata(self):
        import alpha_runtime_files as rf
        self.rows[0]['mode']=0o400;(self.inputs/self.rows[0]['path']).chmod(0o400)
        def metadata(a,b,m):self.assertEqual(os.fstat(b).st_mode & 0o777,0o600)
        with patch.object(rf,'copy_runtime_metadata',side_effect=metadata):self.copy_one(metadata={})
        self.assertEqual((self.output/self.rows[0]['path']).stat().st_mode & 0o777,0o400)

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

    def wheel_metadata(self, names):
        return dict(lock_sha256=self.lock_hash,rows=[dict(name='example',version='1.0',artifacts=[
            dict(filename=n,url='https://files.pythonhosted.org/packages/'+n,sha256='a'*64,bytes=100)
            for n in names])])

    def test_wheel_platform_selection_excludes_windows_arm(self):
        names=['example-1.0-cp314-cp314-win_arm64.whl','example-1.0-py3-none-any.whl',
               'example-1.0-cp314-cp314-macosx_11_0_arm64.whl']
        m=self.wheel_metadata(names)
        self.assertEqual(runtime.select_wheels(m,content_hash(m),lock_bytes=self.lock)[0]['filename'],names[-1])
        m=self.wheel_metadata(names[:1])
        with self.assertRaisesRegex(ValueError,'COMPATIBLE_MISSING'):runtime.select_wheels(m,content_hash(m),lock_bytes=self.lock)

    def test_wheel_wrong_abi_platform_and_name(self):
        for name in ('example-1.0-cp314-cp314t-macosx_11_0_arm64.whl','example-1.0-cp313-cp313-macosx_11_0_arm64.whl',
            'example-1.0-cp314-cp314-manylinux_arm64.whl','other-1.0-py3-none-any.whl'):
            m=self.wheel_metadata([name])
            with self.subTest(name=name),self.assertRaises(ValueError):runtime.select_wheels(m,content_hash(m),lock_bytes=self.lock)

    def test_wheel_origin_hash_size_and_independent_metadata(self):
        original=self.wheel_metadata(['example-1.0-py3-none-any.whl'])
        for key,value in [('url','https://untrusted.invalid/file'),('sha256',''),('bytes',True)]:
            m=deepcopy(original);m['rows'][0]['artifacts'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):runtime.select_wheels(m,content_hash(m),lock_bytes=self.lock)
        with self.assertRaises(ValueError):runtime.select_wheels(original,'f'*64,lock_bytes=self.lock)

    def test_wheel_duplicate_and_missing_distribution(self):
        m=self.wheel_metadata(['example-1.0-py3-none-any.whl']);m['rows']*=2
        with self.assertRaises(ValueError):runtime.select_wheels(m,content_hash(m),lock_bytes=self.lock)


if __name__=='__main__':unittest.main()

# The framework fixture uses inert regular bytes and mocked native metadata APIs.
from test_alpha_runtime_files import TreeCase, policy_fields
import alpha_runtime_files as runtime_files


def framework_spec(case):
    out=case.base/'output';out.mkdir(mode=0o700)
    lock=b'example==1.0\n';h=hashlib.sha256(lock).hexdigest()
    spec=dict(schema=runtime_files.BUILD_SCHEMA,source_commit='a'*40,input_root=str(case.root),
        output_parent=str(out),output_name='runtime-test',files=case.observed['files'],interpreter='bin/python3.14',
        tls_bundle='tls/ca.pem',platform_dependencies=[],provenance=dict.fromkeys(runtime.PROVENANCE,'b'*64),
        lock_sha256=h,python_version='3.14.7',system='Darwin',architecture='arm64',
        **policy_fields(case.observed['metadata']))
    spec['provenance']['distribution']=runtime_files.VENDOR
    approvals=dict(source_commit='a'*40,approved_input_root=str(case.root),approved_output_parent=str(out),
        approved_platform_paths=(),lock_bytes=lock,expected_lock_hash=h)
    return spec,approvals


class FrameworkAssemblyTests(TreeCase):
    def test_preserve_exact_links_manifest_metadata_and_no_execution(self):
        spec,args=framework_spec(self)
        with patch('subprocess.run',side_effect=AssertionError('NO_EXECUTION')):
            result=runtime.assemble(spec,content_hash(spec),**args)
        m=result['manifest'];self.assertEqual(m['schema'],runtime_files.MANIFEST_SCHEMA)
        self.assertFalse(result['production_qualified']);self.assertFalse(result['execution_authorized'])
        self.assertTrue(all(v is False for v in result['authority'].values()))
        ids=runtime_files.verify_manifest(m['runtime_root'],m,source_commit='a'*40)
        self.assertEqual(len(ids),len(spec['files'])+1)
        for name,target in runtime_files._LINKS:self.assertEqual(os.readlink(Path(m['runtime_root'])/name),target)
        self.assertIn('runtime-manifest.json',m['metadata'])
    def test_partial_copy_failure_preserves_exclusive_output(self):
        spec,args=framework_spec(self)
        with patch.object(runtime,'copy_row',side_effect=ValueError('COPY_FAILURE')):
            with self.assertRaisesRegex(ValueError,'COPY_FAILURE'):runtime.assemble(spec,content_hash(spec),**args)
        out=Path(spec['output_parent'])/spec['output_name'];self.assertTrue(out.is_dir())
        with self.assertRaises(FileExistsError):runtime.assemble(spec,content_hash(spec),**args)
    def test_unknown_policy_or_distribution_rejected_before_copy(self):
        spec,args=framework_spec(self)
        for key,value in [('layout_parent','0'*64),('schema',runtime.SCHEMA)]:
            s=deepcopy(spec);s[key]=value
            with patch.object(runtime,'copy_row',side_effect=AssertionError('NO_COPY')):
                with self.assertRaises(ValueError):runtime.assemble(s,content_hash(s),**args)
        spec['provenance']['distribution']='b'*64
        with self.assertRaises(ValueError):runtime.assemble(spec,content_hash(spec),**args)
    def test_final_location_metadata_or_byte_change_rejects(self):
        spec,args=framework_spec(self);m=runtime.assemble(spec,content_hash(spec),**args)['manifest']
        row=m['file_inventory'][0];p=Path(m['runtime_root'])/row['path'];p.chmod(0o600);p.write_bytes(b'changed');p.chmod(row['mode'])
        with self.assertRaises(ValueError):runtime_files.verify_manifest(m['runtime_root'],m,source_commit='a'*40)

    def test_source_and_destination_link_provenance_bound_separately(self):
        source_meta=runtime_files._metadata_digest({'com.apple.provenance':b'01234567890'})
        dest_meta=runtime_files._metadata_digest({'com.apple.provenance':b'abcdefghijk'})
        parents={(p.stat().st_dev,p.stat().st_ino) for p in (self.root/'Frameworks/Tcl.framework',
            self.root/'Frameworks/Tcl.framework/Versions',self.root/'Frameworks/Tk.framework',self.root/'Frameworks/Tk.framework/Versions')}
        def metadata(fd,name,st):
            parent=os.fstat(fd)
            return source_meta if (parent.st_dev,parent.st_ino) in parents else dest_meta
        with patch.object(runtime_files,'_link_metadata',side_effect=metadata),\
             patch.object(runtime_files,'_write_xattr',side_effect=AssertionError('NO_PROVENANCE_COPY')):
            self.observed=runtime_files.inventory_runtime(str(self.root),self.policy,self.parent,approved_root=str(self.root))
            spec,args=framework_spec(self);result=runtime.assemble(spec,content_hash(spec),**args);m=result['manifest']
            for name,_ in runtime_files._LINKS:
                self.assertEqual(spec['metadata'][name],source_meta);self.assertEqual(m['metadata'][name],dest_meta)
            runtime_files.verify_manifest(m['runtime_root'],m,source_commit='a'*40)
            with patch.object(runtime_files,'_link_metadata',return_value=source_meta):
                with self.assertRaisesRegex(ValueError,'TREE_MISMATCH'):
                    runtime_files.verify_manifest(m['runtime_root'],m,source_commit='a'*40)

    def test_source_link_metadata_mutation_after_copy_preserves_failed_output(self):
        value=runtime_files._metadata_digest({'com.apple.provenance':b'01234567890'})
        changed=False;real=runtime.copy_row
        def copy(*args,**kwargs):
            nonlocal changed
            real(*args,**kwargs);changed=True
        with patch.object(runtime_files,'_link_metadata',side_effect=lambda *a:value if changed else {}),\
             patch.object(runtime,'copy_row',side_effect=copy):
            spec,args=framework_spec(self)
            with self.assertRaisesRegex(ValueError,'TREE_MISMATCH'):runtime.assemble(spec,content_hash(spec),**args)
        self.assertTrue((Path(spec['output_parent'])/spec['output_name']).exists())
        self.assertFalse((Path(spec['output_parent'])/spec['output_name']/'runtime-manifest.json').exists())

class RuntimeHeadersAdmissionTests(TreeCase):
    def add_headers(self):
        self.root.chmod(0o700)
        d=self.root/'Headers';d.mkdir(mode=0o700)
        (d/'Python.h').write_bytes(b'public header fixture');(d/'Python.h').chmod(0o400)
        d.chmod(0o500);self.root.chmod(0o500)
        self.observed=runtime_files.inventory_runtime(str(self.root),self.policy,self.parent,approved_root=str(self.root))

    def test_headers_complete_build_and_manifest_keep_independent_pins(self):
        self.add_headers();spec,args=framework_spec(self)
        result=runtime.assemble(spec,content_hash(spec),**args)
        m=result['manifest'];runtime_files.safe_runtime_document(m)
        runtime_files.verify_manifest(m['runtime_root'],m,source_commit='a'*40)
        self.assertIn('Headers',m['metadata']);self.assertFalse(result['production_qualified'])
        with self.assertRaisesRegex(ValueError,'PARENT_HASH_MISMATCH'):
            runtime.admit(spec,'0'*64,**args)

    def test_headers_requires_exact_approved_root(self):
        self.add_headers();spec,args=framework_spec(self);args['approved_input_root']+='different'
        with self.assertRaisesRegex(ValueError,'ROOT_APPROVAL'):runtime.admit(spec,content_hash(spec),**args)

    def test_headers_symlink_and_replaced_payload_rejected(self):
        self.add_headers();spec,args=framework_spec(self)
        self.root.chmod(0o700);(self.root/'Headers').chmod(0o700)
        (self.root/'Headers'/'Python.h').unlink();(self.root/'Headers').rmdir()
        (self.root/'Headers').symlink_to('bin');self.root.chmod(0o500)
        with self.assertRaises(ValueError):runtime.admit(spec,content_hash(spec),**args)

    def test_header_content_substitution_rejected(self):
        self.add_headers();spec,args=framework_spec(self)
        p=self.root/'Headers'/'Python.h';p.chmod(0o600);p.write_bytes(b'changed');p.chmod(0o400)
        with self.assertRaises(ValueError):runtime.admit(spec,content_hash(spec),**args)

    def test_provider_sensitive_keys_remain_rejected(self):
        from provider_gateway_contract import safe_document
        for name in ('headers','Headers','cookies','cookie','authorization','token','api_key','credential','password'):
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'SENSITIVE_DOCUMENT_REJECTED'):
                safe_document({name:'not-a-real-secret'})

    def test_metadata_sensitive_field_injection_rejected(self):
        self.add_headers();spec,args=framework_spec(self)
        for field in ('headers','cookies','authorization','token','api_key'):
            changed=deepcopy(spec);changed['metadata']['Headers']={field:'not-a-real-secret'}
            with self.subTest(field=field),self.assertRaises(ValueError):runtime.admit(changed,content_hash(changed),**args)

    def test_case_traversal_and_outside_structure_rejected(self):
        self.add_headers();spec,args=framework_spec(self)
        for prefix in ('headers','HEADERS','other/Headers','Headers/../elsewhere','Headers/headers'):
            changed=deepcopy(spec)
            changed['files']=[dict(r,path=r['path'].replace('Headers/',prefix+'/',1)) if r['path'].startswith('Headers/') else r for r in changed['files']]
            changed['metadata']={prefix+k[len('Headers'):] if k=='Headers' or k.startswith('Headers/') else k:v for k,v in changed['metadata'].items()}
            for i in range(1,len(prefix.split('/'))):changed['metadata']['/'.join(prefix.split('/')[:i])]={}
            with self.subTest(prefix=prefix),self.assertRaises(ValueError):runtime.admit(changed,content_hash(changed),**args)

    def test_unapproved_policy_cannot_admit_headers(self):
        self.add_headers();spec,args=framework_spec(self)
        spec['layout_policy']['distribution_sha256']='0'*64
        spec['layout_parent']=content_hash(spec['layout_policy'])
        with self.assertRaisesRegex(ValueError,'LAYOUT_POLICY'):runtime.admit(spec,content_hash(spec),**args)


def completed_spec(case):
    """Synthetic seal bytes only; never native signature qualification."""
    case.root.chmod(0o700)
    (case.root/'_CodeSignature').mkdir(mode=0o700)
    (case.root/'Headers').mkdir(mode=0o700)
    (case.root/'Headers/Python.h').write_bytes(b'PUBLIC_OFFLINE_HEADER')
    (case.root/'Headers/Python.h').chmod(0o400);(case.root/'Headers').chmod(0o500)
    for name in ('Python','_CodeSignature/CodeResources'):
        p=case.root/name;p.write_bytes(b'OFFLINE-NOT-A-SIGNATURE');p.chmod(0o400)
    (case.root/'_CodeSignature').chmod(0o500);case.root.chmod(0o500)
    case.observed=runtime_files.inventory_runtime(str(case.root),case.policy,case.parent,approved_root=str(case.root))
    spec,args=framework_spec(case);spec['schema']=runtime_files.COMPLETED_BUILD_SCHEMA
    spec['completion']=dict(dependency_lock_sha256=spec['lock_sha256'],bootstrap_acceptance_sha256='b'*64,
        bootstrap_tree_sha256='c'*64,vendor_distribution_sha256=runtime_files.VENDOR,
        vendor_signature_receipt_sha256='d'*64,assembly_seal_receipt_sha256='e'*64,
        assembly_seal_kind='IIOS_ADHOC_RESOURCE_SEAL',host_contract=dict(system='Darwin',release='26',version='OFFLINE',
            machine='arm64',uid=501,host_identity_sha256='f'*64),sealed_payload_sha256=runtime_files.sealed_payload_parent(spec))
    return spec,args


class CompletedRuntimeTests(TreeCase):
    def build_completed(self):
        spec,args=completed_spec(self)
        with patch('subprocess.run',side_effect=AssertionError('NO_EXECUTION_OR_SIGNING')):
            result=runtime.assemble(spec,content_hash(spec),**args)
        return spec,args,result

    def test_external_manifest_and_detached_context_have_no_cycle(self):
        spec,args,r=self.build_completed();m=r['manifest'];root=Path(m['runtime_root'])
        self.assertFalse((root/'runtime-manifest.json').exists())
        self.assertEqual(m['file_inventory'],spec['files']);self.assertEqual(m['metadata'],spec['metadata'])
        self.assertEqual(Path(r['manifest_path']).parent,root.parent)
        self.assertEqual(Path(r['manifest_path']).read_bytes(),runtime.canonical(m))
        env=json.loads(Path(r['envelope_path']).read_bytes())
        self.assertEqual(env['manifest_sha256'],r['manifest_sha256']);self.assertEqual(env['source_commit'],args['source_commit'])
        self.assertEqual(env['completion'],spec['completion']);self.assertNotIn('envelope_sha256',m)
        self.assertEqual(set(runtime_files.verify_manifest(str(root),m,source_commit=args['source_commit'])),{x['path'] for x in spec['files']})
        self.assertFalse(r['production_qualified']);self.assertTrue(all(v is False for v in r['authority'].values()))
        self.assertEqual(self.verify().keys(),{x['path'] for x in spec['files']})

    def test_wrong_context_and_seal_kind_rejected_before_copy(self):
        spec,args=completed_spec(self)
        for key,value in [('dependency_lock_sha256','0'*64),('sealed_payload_sha256','0'*64),
                          ('assembly_seal_kind','APPLE_VENDOR_SIGNATURE'),('vendor_distribution_sha256','0'*64)]:
            bad=deepcopy(spec);bad['completion'][key]=value
            with self.subTest(key=key),patch.object(runtime,'copy_row',side_effect=AssertionError('COPY')):
                with self.assertRaises(ValueError):runtime.assemble(bad,content_hash(bad),**args)

    def test_each_host_claim_and_parent_is_pinned(self):
        spec,args,r=self.build_completed();m=r['manifest']
        for key in spec['completion']:
            bad=deepcopy(m)
            if key=='host_contract':bad['completion'][key]['uid']=502
            elif key=='assembly_seal_kind':bad['completion'][key]='APPLE_VENDOR_SIGNATURE'
            else:bad['completion'][key]='0'*64
            bad['content_hash']=runtime.digest(bad)
            with self.subTest(key=key),self.assertRaises(ValueError):runtime_files.verify_manifest(m['runtime_root'],bad,source_commit='a'*40)

    def test_missing_duplicate_reordered_and_substituted_payload_rejected(self):
        spec,args,r=self.build_completed();m=r['manifest'];rows=m['file_inventory']
        mutations=[rows[:-1],rows+[rows[-1]],list(reversed(rows)),[dict(rows[0],sha256='0'*64)]+rows[1:]]
        for values in mutations:
            bad=deepcopy(m);bad['file_inventory']=values;bad['content_hash']=runtime.digest(bad)
            with self.assertRaises(ValueError):runtime_files.verify_manifest(m['runtime_root'],bad,source_commit='a'*40)

    def test_added_payload_rejected(self):
        _,_,r=self.build_completed();root=Path(r['manifest']['runtime_root']);root.chmod(0o700)
        p=root/'extra';p.write_bytes(b'x');p.chmod(0o400);root.chmod(0o500)
        with self.assertRaises(ValueError):runtime_files.verify_manifest(str(root),r['manifest'],source_commit='a'*40)

    def test_external_manifest_mutation_rejected(self):
        _,_,r=self.build_completed();p=Path(r['manifest_path']);p.chmod(0o600);p.write_bytes(p.read_bytes()+b' ');p.chmod(0o400)
        with self.assertRaises(ValueError):runtime_files.verify_manifest(r['manifest']['runtime_root'],r['manifest'],source_commit='a'*40)

    def test_external_envelope_missing_rejected(self):
        _,_,r=self.build_completed();Path(r['envelope_path']).unlink()
        with self.assertRaises(FileNotFoundError):runtime_files.verify_manifest(r['manifest']['runtime_root'],r['manifest'],source_commit='a'*40)

    def test_external_envelope_altered_rejected(self):
        _,_,r=self.build_completed();p=Path(r['envelope_path']);v=json.loads(p.read_bytes());v['source_commit']='b'*40
        p.chmod(0o600);p.write_bytes(runtime.canonical(v));p.chmod(0o400)
        with self.assertRaises(ValueError):runtime_files.verify_manifest(r['manifest']['runtime_root'],r['manifest'],source_commit='a'*40)

    def test_external_symlink_and_writable_records_rejected(self):
        _,_,r=self.build_completed();p=Path(r['envelope_path']);p.chmod(0o600)
        with self.assertRaises(ValueError):runtime_files.verify_manifest(r['manifest']['runtime_root'],r['manifest'],source_commit='a'*40)
        p.chmod(0o400);target=p.with_suffix('.saved');p.rename(target);p.symlink_to(target.name)
        with self.assertRaises(OSError):runtime_files.verify_manifest(r['manifest']['runtime_root'],r['manifest'],source_commit='a'*40)

    def test_partial_publication_preserved_and_no_retry(self):
        spec,args=completed_spec(self);original=os.open
        def fail(path,*a,**kw):
            if path=='runtime-test.envelope.json':raise OSError('OFFLINE_PUBLICATION')
            return original(path,*a,**kw)
        with patch.object(os,'open',side_effect=fail):
            with self.assertRaises(OSError):runtime.assemble(spec,content_hash(spec),**args)
        self.assertTrue((Path(spec['output_parent'])/'runtime-test.manifest.json').exists())
        with self.assertRaises(FileExistsError):runtime.assemble(spec,content_hash(spec),**args)

    def test_unknown_or_missing_schema_cannot_select_completed_format(self):
        spec,args=completed_spec(self)
        for schema in (runtime_files.BUILD_SCHEMA,runtime.SCHEMA,'unknown',None):
            bad=deepcopy(spec)
            if schema is None:del bad['schema']
            else:bad['schema']=schema
            with self.assertRaises((ValueError,KeyError)):runtime.assemble(bad,content_hash(bad),**args)
