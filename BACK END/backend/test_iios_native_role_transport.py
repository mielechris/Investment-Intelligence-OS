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
    def instance(self,clock=None):return t.ReadOnlyTransport({'/bin/ps':'a'*64,'/usr/sbin/lsof':'b'*64},10**12,clock=clock or (lambda:1),popen=Mock())
    def test_exact_inspector_success_reaps_without_signals(self):
        transport=self.instance();child=Mock();child.poll.return_value=0;child.returncode=0
        child.stdout.fileno.return_value=101;child.stderr.fileno.return_value=102
        transport.popen.return_value=child
        with patch.object(t,'pin_file'),patch.object(t.os,'set_blocking'),patch.object(t.select,'select',side_effect=lambda streams,*a:(list(streams),[],[])),patch.object(t.os,'read',return_value=b''):
            result=transport.run(self.argv,**self.kw);self.assertEqual(result.stdout,'');transport.verify_cleanup()
        child.wait.assert_called();child.kill.assert_not_called();child.terminate.assert_not_called()
    def test_wrong_command_or_environment_never_spawns(self):
        for argv,kw in [(['/bin/ps','aux'],self.kw),(self.argv,dict(self.kw,env={'LC_ALL':'C'}))]:
            transport=self.instance()
            with self.assertRaises(QualificationFailure):transport.run(argv,**kw)
            transport.popen.assert_not_called()
    def test_constructor_denial_retains_uncertainty(self):
        transport=self.instance();transport.popen.side_effect=PermissionError(13,'not retained')
        with patch.object(t,'pin_file'),self.assertRaises(PermissionError):transport.run(self.argv,**self.kw)
        with self.assertRaises(QualificationFailure):transport.verify_cleanup()
        original={'status':'FAILED_CLOSED','primary_failure':{'predicate':'ORIGINAL'},'cleanup':None}
        result=transport.finish(copy.deepcopy(original));self.assertEqual(result['primary_failure'],original['primary_failure'])
        self.assertFalse(result['cleanup']['verified'])
    def test_timeout_retains_handle_zero_signals(self):
        clock=Mock(side_effect=[1,1,2_000_000_000]);transport=self.instance(clock);child=Mock();child.poll.return_value=None;transport.popen.return_value=child
        with patch.object(t,'pin_file'),patch.object(t.os,'set_blocking'),self.assertRaises(QualificationFailure) as caught:transport.run(self.argv,**self.kw)
        self.assertEqual(caught.exception.detail['predicate'],'ROLE_INSPECTION_TIMEOUT');self.assertEqual(transport.handles,[child])
        child.kill.assert_not_called();child.terminate.assert_not_called()
        with self.assertRaises(QualificationFailure):transport.verify_cleanup()
    def test_unknown_returned_bytes_overflow(self):
        transport=self.instance();child=Mock();child.poll.return_value=None;child.stdout.fileno.return_value=101;child.stderr.fileno.return_value=102;transport.popen.return_value=child
        with patch.object(t,'pin_file'),patch.object(t.os,'set_blocking'),patch.object(t.select,'select',side_effect=lambda streams,*a:([streams[0]],[],[])),patch.object(t.os,'read',return_value=b'x'*65537),self.assertRaises(QualificationFailure) as caught:transport.run(self.argv,**self.kw)
        self.assertEqual(caught.exception.detail['predicate'],'ROLE_INSPECTION_OVERFLOW');child.kill.assert_not_called()
