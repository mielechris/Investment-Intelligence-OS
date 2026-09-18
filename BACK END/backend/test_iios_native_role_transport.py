"""Every native process and pipe effect is substituted."""
import copy
import types
import unittest
from unittest.mock import Mock,patch
import iios_native_role_transport as t
from iios_native_conductor import QualificationFailure

class RoleTransportTests(unittest.TestCase):
    argv=['/bin/ps','-ww','-p','123','-o','lstart=']
    kw=dict(capture_output=True,text=True,timeout=1,env={'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC'})
    def instance(self,clock=None):return t.ReadOnlyTransport({'/bin/ps':'a'*64,'/usr/sbin/lsof':'b'*64},10**12,clock=clock or (lambda:1),popen=Mock(),self_pid=123)
    def test_exact_inspector_success_reaps_without_signals(self):
        transport=self.instance();child=Mock();child.poll.return_value=0;child.returncode=0
        child.stdout.fileno.return_value=101;child.stderr.fileno.return_value=102
        transport.popen.return_value=child
        with patch.object(t.ReadOnlyTransport,'tool_identity',return_value=(1,2)),patch.object(t.os,'set_blocking'),patch.object(t.select,'select',side_effect=lambda streams,*a:(list(streams),[],[])),patch.object(t.os,'read',return_value=b''):
            result=transport.run(self.argv,**self.kw);self.assertEqual(result.stdout,'');transport.verify_cleanup()
        child.wait.assert_called();child.kill.assert_not_called();child.terminate.assert_not_called()
    def test_wrong_command_or_environment_never_spawns(self):
        for argv,kw in [(['/bin/ps','aux'],self.kw),(self.argv,dict(self.kw,env={'LC_ALL':'C'}))]:
            transport=self.instance()
            with self.assertRaises(QualificationFailure):transport.run(argv,**kw)
            transport.popen.assert_not_called()
    def test_constructor_denial_retains_uncertainty(self):
        transport=self.instance();transport.popen.side_effect=PermissionError(13,'not retained')
        with patch.object(t.ReadOnlyTransport,'tool_identity',return_value=(1,2)),self.assertRaises(PermissionError):transport.run(self.argv,**self.kw)
        with self.assertRaises(QualificationFailure):transport.verify_cleanup()
        original={'status':'FAILED_CLOSED','primary_failure':{'predicate':'ORIGINAL'},'cleanup':None}
        result=transport.finish(copy.deepcopy(original));self.assertEqual(result['primary_failure'],original['primary_failure'])
        self.assertFalse(result['cleanup']['verified'])
    def test_timeout_retains_handle_zero_signals(self):
        clock=Mock(side_effect=[1,1,2_000_000_000]);transport=self.instance(clock);child=Mock();child.poll.return_value=None;transport.popen.return_value=child
        with patch.object(t.ReadOnlyTransport,'tool_identity',return_value=(1,2)),patch.object(t.os,'set_blocking'),self.assertRaises(QualificationFailure) as caught:transport.run(self.argv,**self.kw)
        self.assertEqual(caught.exception.detail['predicate'],'ROLE_INSPECTION_TIMEOUT');self.assertEqual(transport.handles,[child])
        child.kill.assert_not_called();child.terminate.assert_not_called()
        with self.assertRaises(QualificationFailure):transport.verify_cleanup()
    def test_only_registered_or_self_pid_admitted(self):
        transport=self.instance();argv=list(self.argv);argv[3]='456'
        with self.assertRaises(QualificationFailure) as c:transport.run(argv,**self.kw)
        self.assertEqual(c.exception.detail['predicate'],'ROLE_INSPECTION_REGISTERED_PID');transport.popen.assert_not_called()
        handle=Mock(pid=456);handle.poll.return_value=None;transport.register(handle)
        handle.pid=457
        with self.assertRaises(QualificationFailure) as c:transport.run(argv,**self.kw)
        self.assertEqual(c.exception.detail['predicate'],'ROLE_INSPECTION_HANDLE_MUTATION')
    def test_differential_argument_shell_and_tool_rejections(self):
        candidates=[['/bin/sh','-c','ps -p 123'],['/usr/bin/env','ps','-p','123'],['/bin/ps','aux'],
            ['/bin/ps','-ww','-p','123','-o','command='],['/bin/ps','-p','123','-ww','-o','lstart='],
            ['/usr/sbin/lsof','-a','-p','123','-d','cwd','-Fpn'],
            ['/usr/sbin/lsof','-nP','-iTCP:38493','-sTCP:LISTEN','-Fp'],
            ['/bin/ps','-ww','-p','123,456','-o','lstart=']]
        for argv in candidates:
            with self.subTest(argv=argv):
                transport=self.instance()
                with self.assertRaises(QualificationFailure):transport.run(argv,**self.kw)
                transport.popen.assert_not_called()
    def test_exact_templates_all_reach_only_bound_transport(self):
        for template in t.COMMAND_TEMPLATES:
            argv=[v.replace('REGISTERED_PID','123') for v in template]
            options=self.kw if template!=t.COMMAND_TEMPLATES[-1] else dict(env=t.LISTENER_ENV,stdin=t.subprocess.PIPE,stdout=t.subprocess.PIPE,stderr=t.subprocess.PIPE,timeout=2,check=False)
            transport=self.instance();transport.popen.side_effect=PermissionError(1,'sanitized')
            with patch.object(t.ReadOnlyTransport,'tool_identity',return_value=(1,2)),self.assertRaises(PermissionError):transport.run(argv,**options)
            self.assertEqual(transport.popen.call_args.args[0],argv)
    def test_missing_altered_or_extra_tool_identities(self):
        for pins in ({},{'/bin/ps':'a'*64},{'/bin/ps':'bad','/usr/sbin/lsof':'b'*64},{'/bin/ps':'a'*64,'/usr/sbin/lsof':'b'*64,'/bin/sh':'c'*64}):
            with self.assertRaises(QualificationFailure):t.ReadOnlyTransport(pins,100,self_pid=123)
        transport=self.instance()
        with patch.object(t,'pin_file',side_effect=QualificationFailure(t.STAGE,'INPUT_HASH','MATCH','MISMATCH')):
            with self.assertRaises(QualificationFailure):transport.run(self.argv,**self.kw)
        transport.popen.assert_not_called()
    def test_tool_mutation_and_expiry_stop_without_signals(self):
        transport=self.instance(clock=lambda:10**12)
        with self.assertRaises(QualificationFailure):transport.run(self.argv,**self.kw)
        transport.popen.assert_not_called()
    def test_options_cannot_expand_environment_or_shell(self):
        for change in ({'shell':True},{'cwd':'/elsewhere'},{'timeout':20},{'env':dict(t.INSPECT_ENV,EXTRA='VALUE')},{'capture_output':False}):
            transport=self.instance()
            with self.assertRaises(QualificationFailure):transport.run(self.argv,**dict(self.kw,**change))
            transport.popen.assert_not_called()
    def test_unknown_returned_bytes_overflow(self):
        transport=self.instance();child=Mock();child.poll.return_value=None;child.stdout.fileno.return_value=101;child.stderr.fileno.return_value=102;transport.popen.return_value=child
        with patch.object(t.ReadOnlyTransport,'tool_identity',return_value=(1,2)),patch.object(t.os,'set_blocking'),patch.object(t.select,'select',side_effect=lambda streams,*a:([streams[0]],[],[])),patch.object(t.os,'read',return_value=b'x'*65537),self.assertRaises(QualificationFailure) as caught:transport.run(self.argv,**self.kw)
        self.assertEqual(caught.exception.detail['predicate'],'ROLE_INSPECTION_OVERFLOW');child.kill.assert_not_called()
