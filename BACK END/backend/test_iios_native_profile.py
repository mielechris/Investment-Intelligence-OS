"""Pinned profile and lifecycle report regressions; no native effects."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from iios_native_conductor import QualificationFailure,canonical
from iios_native_profile import template_bytes,reviewed_profile
from iios_native_lifecycle import decode_functional

class ProfileTests(unittest.TestCase):
    def fixture(self,root,template=None):
        raw=template_bytes() if template is None else template
        def bind(name,data):
            path=root/name;path.write_bytes(data);return {'path':str(path),'sha256':hashlib.sha256(data).hexdigest()}
        tools=dict.fromkeys(('/bin/ps','/usr/sbin/lsof','/usr/bin/sandbox-exec'),'a'*64)
        review={'template_sha256':hashlib.sha256(raw).hexdigest(),'scope':'DISPOSABLE_NATIVE_QUALIFICATION_ONLY',
            'default_deny':True,'network':['127.0.0.1:38493'],'credentials':False,'providers':False,'inspection_tools':tools,
            'substitutions':sorted(('@PROCESS_IMAGE@','@RUNTIME@','@RELEASE@','@CONTROL@','@OUTPUT@','@CONFIG@','@DRIVER@','@INTERPRETER@','@ENDPOINT@'))}
        m={'tool_pins':tools,'native':{'runtime_acceptance':{'image_relative':'Python.framework/Python'}}}
        d={'profile_template':bind('profile',raw),'profile_review':bind('review',canonical(review))}
        roots={k:str(root/k) for k in ('runtime','release','control','output')}
        return m,d,roots
    def test_exact_profile_only_substitutes_pinned_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            m,d,roots=self.fixture(Path(directory));raw,parent=reviewed_profile(m,d,roots)
            self.assertNotIn(b'@',raw);self.assertIn(b'(deny default)',raw)
            self.assertIn(b'(literal "/bin/ps")',raw);self.assertEqual(len(parent),64)
    def test_rehashed_broadened_profiles_fail(self):
        for suffix in (b'\n(allow default)',b'\n(allow network*)',b'\n(allow process-exec)',b'\n(allow file-read*)'):
            with self.subTest(suffix=suffix),tempfile.TemporaryDirectory() as directory:
                m,d,roots=self.fixture(Path(directory),template_bytes()+suffix)
                with self.assertRaises(QualificationFailure) as c:reviewed_profile(m,d,roots)
                self.assertEqual(c.exception.detail['predicate'],'LIFECYCLE_PROFILE_OPERATION_ALLOWLIST')
    def test_changed_tool_image_escape_and_template_mutation_fail(self):
        for mutation in ('tool','image','template'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                m,d,roots=self.fixture(Path(directory))
                if mutation=='tool':m['tool_pins']['/bin/ps']='b'*64
                if mutation=='image':m['native']['runtime_acceptance']['image_relative']='../outside'
                if mutation=='template':Path(d['profile_template']['path']).write_bytes(b'changed')
                with self.assertRaises(QualificationFailure):reviewed_profile(m,d,roots)

class LifecycleReportTests(unittest.TestCase):
    def fixture(self):
        from provider_gateway_contract import locked_authority
        f={'scope':'DISPOSABLE_NATIVE_QUALIFICATION_ONLY','production_qualified':False,'provider_access':False,
           'credential_access':False,'seeded':True,'requests_attempted':0,'broker_connected':False,
           'paper_order_permission':False,'trade_execution_permission':False,'live_execution':False}
        return dict(f,schema='iios-disposable-functional-result-v1',status='FUNCTIONAL_PASS',admission_parent='a'*64,
            primary_failure=None,provider_requests=0,seed_records=3,authority=locked_authority(),
            confinement='UNQUALIFIED_UNTIL_CONTROLLED_COMPARISONS',
            http=[dict(f,method=m,status=200,tls_verified=True,provider_requests=0) for m in ('GET','HEAD')],
            cleanup=dict(f,verified=True,cooperative=True,roles=['scheduler','publisher','backend'],listener_owner_reconciled=True,port_clear=[True]*3,failures=[]))
    def test_complete_functional_is_not_confinement_attestation(self):
        value=self.fixture();self.assertEqual(decode_functional(canonical(value),'a'*64),value)
    def test_altered_scope_parent_tls_cleanup_or_authority_rejected(self):
        for kind in ('scope','parent','tls','cleanup','authority','confinement','extra','partial'):
            value=self.fixture()
            if kind=='scope':value['production_qualified']=True
            if kind=='parent':value['admission_parent']='b'*64
            if kind=='tls':value['http'][0]['tls_verified']=False
            if kind=='cleanup':value['cleanup']['verified']=False
            if kind=='authority':value['authority']['provider_access']=True
            if kind=='confinement':value['confinement']='GREEN'
            if kind=='extra':value['unreviewed']='VALUE'
            if kind=='partial':value['cleanup']['roles'].pop()
            with self.subTest(kind=kind),self.assertRaises(QualificationFailure):decode_functional(canonical(value),'a'*64)
    def test_overflow_duplicate_nonfinite_rejected(self):
        for raw in (b'x'*(4*1024*1024+1),b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.assertRaises(QualificationFailure):decode_functional(raw,'a'*64)
