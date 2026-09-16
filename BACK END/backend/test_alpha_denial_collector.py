import json
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch
import alpha_denial_collector as c
from provider_gateway_contract import content_hash, locked_authority


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.spec=dict(schema='iios-bounded-os-denial-v1',scope='DISPOSABLE_DENIAL_ONLY',pid=123,
            name='python3.14',executable='/disposable/runtime/python',operation='file-read-data',
            target='/disposable/dummy',start='2026-09-16T13:00:00+00:00',end='2026-09-16T13:00:10+00:00',
            cwd='/disposable',log_sha256='1'*64,launch_parent='2'*64,host_parent='3'*64,profile_parent='4'*64,
            owner_parent='5'*64,authority=locked_authority())
    def event(self):
        s=self.spec
        return dict(subsystem='com.apple.sandbox.reporting',category='violation',
            processImagePath='/usr/libexec/sandboxd',timestamp='2026-09-16 13:00:05+00:00',
            eventMessage=f"Sandbox: {s['name']}({s['pid']}) deny(1) {s['operation']} {s['target']}\n"
                f"Violation: deny(1) {s['operation']} {s['target']}\nProcess: {s['name']} [{s['pid']}]\nPath: {s['executable']}")
    def reduce(self,e=None):return c.reduce_events(json.dumps(e or self.event()).encode(),self.spec)
    def test_exact_documented_fields_correlate_without_policy_acceptance(self):
        self.assertEqual(self.reduce(),dict(category='OS_DENIAL_REPORT_MATCH',matches=1))
    def test_errno_and_misleading_prefix_never_match(self):
        for msg in ('EACCES','EPERM','Operation not permitted','prefix '+self.event()['eventMessage'],
                    self.event()['eventMessage']+'\nPath: /another'):
            e=self.event();e['eventMessage']=msg;self.assertEqual(self.reduce(e)['category'],'UNKNOWN')
    def test_wrong_process_operation_target_source_and_time(self):
        e=self.event()
        for key,value in [('subsystem','forged'),('category','fake'),('processImagePath','/disposable/fake'),
                          ('timestamp','2026-09-16T14:00:00+00:00')]:
            b={**e,key:value};self.assertEqual(self.reduce(b)['category'],'UNKNOWN')
        for old,new in [('(123)','(124)'),('file-read-data','file-write-create'),('/disposable/dummy','/disposable/other')]:
            b={**e,'eventMessage':e['eventMessage'].replace(old,new)}
            self.assertEqual(self.reduce(b)['category'],'UNKNOWN')
    def test_unknown_tail_and_sensitive_text_are_not_retained(self):
        e=self.event();e['eventMessage']+='\nThread 0: arbitrary sensitive text'
        result=self.reduce(e);self.assertNotIn('sensitive',json.dumps(result));self.assertNotIn('disposable',json.dumps(result))
    def test_duplicate_events_reject_ambiguous_correlation(self):
        raw=(json.dumps(self.event())+'\n'+json.dumps(self.event())).encode()
        self.assertEqual(c.reduce_events(raw,self.spec),dict(category='UNKNOWN',matches=2))
    def test_malformed_duplicate_keys_control_and_bounds(self):
        for raw in (b'',b'{',b'{"timestamp":1,"timestamp":2}',b'\x01',b'\xff'):
            self.assertEqual(c.reduce_events(raw,self.spec)['category'],'UNKNOWN')
        self.assertEqual(c.reduce_events(b'x'*4097,self.spec)['category'],'OVERFLOW')
    def test_fixed_query_no_free_form_flags(self):
        argv=c.query(self.spec,content_hash(self.spec))
        self.assertEqual(argv[:4],['/usr/bin/log','show','--style','ndjson'])
        self.assertNotIn('collect',argv);self.assertNotIn('stream',argv)
        self.assertIn('com.apple.sandbox.reporting',argv[-1]);self.assertIn('(123)',argv[-1])
    def test_spec_mutations_rejected(self):
        for key,value in [('pid',True),('pid',0),('name','x\" OR true'),('scope','LIVE'),('operation','anything'),
            ('target','/outside'),('cwd','/disposable/../other'),('end','2026-09-16T13:00:11+00:00'),
            ('log_sha256','bad'),('authority',dict.fromkeys(locked_authority(),True))]:
            b={**self.spec,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):c.query(b,content_hash(b))
    def test_no_io_before_spec_hash_admission(self):
        with patch.object(c,'inspect_macos') as inspect,patch.object(c.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):c.collect(self.spec,'0'*64,owner={},expected_owner='0'*64)
            inspect.assert_not_called();spawn.assert_not_called()

class CaptureTests(unittest.TestCase):
    setUp = CollectorTests.setUp
    event = CollectorTests.event
    def capture(self, raw, *, expiry=False, overflow=False, changed=False):
        from dataclasses import asdict, replace
        from io import BytesIO
        import hashlib
        from truth_spine_process_identity import ProcessObservation
        obs=ProcessObservation(123,99,'2026-09-16T12:59:59+00:00','python3.14',
            self.spec['executable'],'a'*64,'/disposable',('python3.14',))
        owner=asdict(obs);owner['argv']=list(owner['argv'])
        self.spec['owner_parent']=content_hash(owner)
        self.spec['log_sha256']=hashlib.sha256(b'public fake log executable').hexdigest()
        child=Mock(pid=456);child.poll.return_value=None if expiry or overflow else 0
        child.stdout.fileno.return_value=10;child.stderr.fileno.return_value=11
        chunks=[raw,b'']
        def read(fd,n):
            if fd==11:return b''
            if overflow:return b'x'*min(n,512)
            return chunks.pop(0)
        observations=[obs,replace(obs,parent_pid=100) if changed else obs]
        with (patch.object(c,'inspect_macos',side_effect=observations),
            patch('builtins.open',return_value=BytesIO(b'public fake log executable')),
            patch.object(c.subprocess,'Popen',return_value=child) as spawn,
            patch.object(c.os,'set_blocking'),patch.object(c.os,'read',side_effect=read),
            patch.object(c.time,'monotonic_ns',side_effect=[1,6_000_000_000] if expiry else None,return_value=1),
            patch.object(c.time,'sleep')):
            result=c.collect(self.spec,content_hash(self.spec),owner=owner,expected_owner=content_hash(owner))
        self.assertEqual(spawn.call_count,1);child.stdin.close.assert_called_once()
        child.kill.assert_not_called();child.terminate.assert_not_called()
        self.assertNotIn('eventMessage',json.dumps(result));self.assertNotIn('disposable',json.dumps(result))
        return result
    def test_bounded_collection_keeps_only_correlated_fields(self):
        result=self.capture(json.dumps(self.event()).encode())
        self.assertEqual(result['category'],'OS_DENIAL_REPORT_MATCH')
        self.assertTrue(result['collector_exit_verified']);self.assertFalse(result['confinement_qualified'])
    def test_capture_deadline_does_not_signal_unverified_collector(self):
        result=self.capture(b'',expiry=True)
        self.assertEqual(result['category'],'CAPTURE_DEADLINE');self.assertFalse(result['collector_exit_verified'])
    def test_capture_overflow_never_retains_raw(self):
        result=self.capture(b'',overflow=True)
        self.assertEqual(result['category'],'OVERFLOW');self.assertFalse(result['collector_exit_verified'])
    def test_pid_reuse_invalidates_even_matching_report(self):
        result=self.capture(json.dumps(self.event()).encode(),changed=True)
        self.assertEqual(result['category'],'IDENTITY_CHANGED')
