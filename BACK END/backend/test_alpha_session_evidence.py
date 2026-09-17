"""Disposable synthetic files only. No executable is run or provider contacted."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alpha_session_evidence import verify_files, verify_candidate_evidence, json_document
from deployment_contract import digest, RUNTIME_MANIFEST_SCHEMA
from provider_gateway_contract import canonical, content_hash
from provider_gateway_live_contract import CLAIMS
import test_alpha_session_package as fixtures


def write(root,name,body,mode=0o400):
    path=root/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(body); path.chmod(mode)
    return dict(path=name,size=len(body),mode=mode,sha256=hashlib.sha256(body).hexdigest())


def seal_directories(root):
    for path in root.rglob('*'):
        if path.is_dir(): path.chmod(0o500)
    root.chmod(0o500)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='iios-provider-connection-source-tests-evidence-')
        self.base=Path(self.temp.name).resolve()
        self.root=self.base/'runtime'; self.root.mkdir()
        self.rows=[write(self.root,'bin/python',b'synthetic non-executable fixture',0o500),
                   write(self.root,'source.py',b'# synthetic source\n')]
        seal_directories(self.root)

    def tearDown(self):
        for path in self.base.rglob('*'):
            if path.is_dir() and not path.is_symlink(): path.chmod(0o700)
        self.temp.cleanup()

    def check(self): return verify_files(str(self.root),self.rows,approved_root=str(self.root))

    def test_exact_files_and_no_execution(self):
        with patch('subprocess.run',side_effect=AssertionError('NO_PROCESS')):
            self.assertEqual(self.check(),{})

    def test_unapproved_root_rejected_before_open(self):
        with patch('os.open',side_effect=AssertionError('NO_FILESYSTEM')):
            with self.assertRaisesRegex(ValueError,'EVIDENCE_ROOT_NOT_APPROVED'):
                verify_files('/not-approved',self.rows,approved_root=str(self.root))

    def test_traversal_rejected_before_open(self):
        self.rows[0]['path']='../outside'
        with patch('os.open',side_effect=AssertionError('NO_FILESYSTEM')):
            with self.assertRaises(ValueError): self.check()

    def test_symlink_file_rejected(self):
        self.root.chmod(0o700)
        (self.root/'source.py').unlink()
        (self.root/'source.py').symlink_to(self.root/'bin/python')
        self.root.chmod(0o500)
        with self.assertRaises(ValueError): self.check()

    def test_symlink_parent_rejected(self):
        alias=self.base/'alias'; alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError): verify_files(str(alias),self.rows,approved_root=str(alias))

    def test_hardlink_rejected(self):
        os.link(self.root/'source.py',self.base/'extra-link')
        with self.assertRaises(ValueError): self.check()

    def test_missing_and_extra_inventory(self):
        self.root.chmod(0o700)
        write(self.root,'extra',b'extra'); self.root.chmod(0o500)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_EXTRA_FILE'): self.check()

    def test_missing_file(self):
        self.root.chmod(0o700); (self.root/'source.py').unlink(); self.root.chmod(0o500)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_MISSING_FILE'): self.check()

    def test_altered_bytes_and_writable_file(self):
        p=self.root/'source.py'; p.chmod(0o600)
        with self.assertRaises(ValueError): self.check()
        p.write_bytes(b'x'*self.rows[1]['size']); p.chmod(0o400)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_HASH'): self.check()

    def test_file_bounds_before_io(self):
        for size in (True,-1,64*1024*1024+1):
            self.rows[0]['size']=size
            with patch('os.open',side_effect=AssertionError('NO_FILESYSTEM')):
                with self.assertRaises(ValueError): self.check()

    def test_duplicate_json_rejected(self):
        with self.assertRaisesRegex(ValueError,'EVIDENCE_DUPLICATE_KEY'):
            json_document(b'{"claim":"feed","claim":"rate"}')

    def test_modified_during_read_rejected(self):
        original=os.read; changed=[False]
        def read(fd,count):
            data=original(fd,count)
            if data and not changed[0]:
                changed[0]=True
                os.utime(self.root/'bin/python',ns=(1,1))
            return data
        with patch('os.read',side_effect=read),self.assertRaisesRegex(ValueError,'EVIDENCE_FILE_CHANGED'):
            self.check()


class CandidateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='iios-provider-connection-source-tests-admission-')
        self.base=Path(self.temp.name).resolve()
        self.runtime_root=self.base/'runtime'; self.runtime_root.mkdir()
        self.claims_root=self.base/'claims'; self.claims_root.mkdir()
        self.fixture=fixtures.PackageTests(); self.fixture.setUp()
        f=self.fixture
        rows=[write(self.runtime_root,'bin/python',b'not an actual interpreter',0o500),
              write(self.runtime_root,'source.py',b'# disposable source\n')]
        m=dict(schema=RUNTIME_MANIFEST_SCHEMA,runtime_id='synthetic-runtime',release_commit='a'*40,
               runtime_root=str(self.runtime_root),interpreter=str(self.runtime_root/'bin/python'),
               interpreter_sha256=rows[0]['sha256'],python_version='3.14.7',dependency_inventory=[],
               file_inventory=rows,platform_dependencies=[])
        m['content_hash']=digest(m); self.runtime_manifest=m
        write(self.runtime_root,'runtime-manifest.json',canonical(m))
        f.runtime.update(runtime_manifest_sha256=content_hash(m),interpreter_sha256=rows[0]['sha256'],
                         platform_manifest_sha256=content_hash([]))
        names,claims_rows={},[]
        for claim in CLAIMS:
            doc={k:f.account[k] for k in ('account_identity','tier_identity','provider','endpoint','feed',
                                         'source_commit','session','valid_from','expires_at')}
            doc.update(schema='iios-alpha-reviewed-account-claim-v1',claim=claim,
                       symbols_parent=content_hash(f.account['symbols']),review_parent='b'*64)
            f.account['claim_parents'][claim]=content_hash(doc)
            names[claim]=claim+'.json'
            claims_rows.append(write(self.claims_root,names[claim],canonical(doc)))
        f.repin()
        self.claims_manifest=dict(schema='iios-alpha-reviewed-claim-files-v1',account_parent=f.pins['account'],
                                  root=str(self.claims_root),files=claims_rows,claims=names)
        self.claims_pin=content_hash(self.claims_manifest)
        self.candidate=f.build()
        seal_directories(self.runtime_root); seal_directories(self.claims_root)

    def tearDown(self):
        for p in self.base.rglob('*'):
            if p.is_dir() and not p.is_symlink(): p.chmod(0o700)
        self.temp.cleanup()

    def check(self):
        f=self.fixture
        return verify_candidate_evidence(self.candidate,content_hash(self.candidate),f.plan,f.account,f.runtime,f.allowance,
            runtime_manifest=self.runtime_manifest,claims_manifest=self.claims_manifest,claims_manifest_hash=self.claims_pin,
            approved_runtime_root=str(self.runtime_root),approved_claims_root=str(self.claims_root),**f.kwargs())

    def test_read_only_end_to_end_remains_unqualified(self):
        with patch('subprocess.run',side_effect=AssertionError('NO_EXECUTION')):
            result=self.check()
        self.assertEqual(result['status'],'FILES_AND_BINDINGS_VERIFIED_ONLY')
        self.assertFalse(result['production_qualified']); self.assertFalse(result['execution_authorized'])
        self.assertIn('PLATFORM_AND_RUNNING_INTERPRETER',result['pending'])

    def test_changed_runtime_manifest_rejected(self):
        self.runtime_manifest['release_commit']='f'*40
        with self.assertRaises(ValueError): self.check()

    def test_changed_claim_bytes_rejected(self):
        p=self.claims_root/'feed.json'; p.chmod(0o600); p.write_bytes(b'{}'); p.chmod(0o400)
        with self.assertRaises(ValueError): self.check()

    def test_wrong_account_parent_even_with_rehashed_manifest(self):
        self.claims_manifest['account_parent']='f'*64; self.claims_pin=content_hash(self.claims_manifest)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_CLAIMS_MANIFEST'): self.check()

    def test_semantic_claim_mismatch_even_with_new_file_pin(self):
        doc=json_document((self.claims_root/'feed.json').read_bytes()); doc['account_identity']='wrong-account'
        self.claims_root.chmod(0o700); p=self.claims_root/'feed.json'; p.chmod(0o600)
        row=write(self.claims_root,'feed.json',canonical(doc)); self.claims_root.chmod(0o500)
        self.claims_manifest['files']=[row if r['path']=='feed.json' else r for r in self.claims_manifest['files']]
        f=self.fixture; f.account['claim_parents']['feed']=content_hash(doc); f.repin(); self.candidate=f.build()
        self.claims_manifest['account_parent']=f.pins['account']; self.claims_pin=content_hash(self.claims_manifest)
        with self.assertRaisesRegex(ValueError,'EVIDENCE_CLAIM_BINDING'): self.check()


if __name__ == '__main__': unittest.main()

from test_alpha_runtime_files import TreeCase


class FrameworkCandidateTests(TreeCase):
    def test_v2_actual_manifest_files_and_claims_remain_unqualified(self):
        from test_alpha_production_runtime import framework_spec,runtime as assembler
        spec,args=framework_spec(self);m=assembler.assemble(spec,content_hash(spec),**args)['manifest']
        h=CandidateEvidenceTests();h.setUp()
        try:
            h.runtime_manifest=m;h.runtime_root=Path(m['runtime_root']);f=h.fixture
            f.runtime.update(runtime_manifest_sha256=content_hash(m),interpreter_sha256=m['interpreter_sha256'])
            f.repin();h.candidate=f.build()
            result=h.check();self.assertEqual(result['status'],'FILES_AND_BINDINGS_VERIFIED_ONLY')
            self.assertFalse(result['production_qualified']);self.assertFalse(result['execution_authorized'])
            # Updating bytes requires new independently pinned evidence, not relabeling.
            m['layout_parent']='0'*64
            with self.assertRaises(ValueError):h.check()
        finally:h.tearDown()
