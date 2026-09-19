import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'BACK END/backend'))
from iios_qualification_v2.state import *
from iios_qualification_v2.cli import execute
from iios_qualification_v2.native import reconcile, profile, selected_host

class WorkflowTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.root.chmod(0o700)
    def tearDown(self):
        for p in self.root.rglob('*'):
            if p.is_dir():p.chmod(0o700)
        self.temp.cleanup()
    def run_stages(self, failure=None):
        calls=[]
        def operation(name):
            calls.append(name)
            if name==failure:raise ValueError('CONTROLLED_TEST_FAILURE')
            return {'verified':True,'outstanding':0}
        stages={name:lambda name=name:operation(name) for name in STAGES[:-1]}
        store=Store(self.root/('state-'+str(failure)))
        result=execute(store,stages,source='s',boot='b',resume=False,issuer=None,evidence=self.root/'evidence')
        return result,calls,store
    def test_offline_cannot_issue_native_green(self):
        result,calls,_=self.run_stages();self.assertEqual(result['status'],'OFFLINE_PASS');self.assertEqual(calls,list(STAGES[:-1]));self.assertEqual(result['authority'],AUTHORITY)
    def test_every_failed_stage_stops_without_retry(self):
        for name in STAGES[:-1]:
            result,calls,_=self.run_stages(name);self.assertEqual(result['status'],'RED');self.assertEqual(calls.count(name),1)
            self.assertEqual(result['failure']['stage'],name)
    def test_cleanup_failure_is_not_established(self):
        result,_,_=self.run_stages('cleanup');self.assertEqual(result['status'],'RED');self.assertIsNone(result['cleanup'])
    def test_missing_stage_rejected(self):
        with self.assertRaises(ValueError):execute(Store(self.root/'state'),{},source='s',boot='b',resume=False,issuer=None,evidence=self.root/'evidence')
    def test_current_boot_live_pid_blocks(self):
        records=[{'event':'CHILD_LAUNCHED','data':{'nonce':'n','pid':2,'boot':'b'}}]
        with self.assertRaises(ValueError):reconcile(records,'b',lambda _:object())
    def test_current_absence_does_not_rewrite_history(self):
        records=[{'event':'CHILD_LAUNCHED','data':{'nonce':'n','pid':2,'boot':'b'}}]
        rows=reconcile(records,'b',lambda _:None);self.assertEqual(rows[0]['historical_cleanup'],'NOT_ESTABLISHED')
    def test_prior_boot_never_inspects_recycled_pid(self):
        records=[{'event':'CHILD_LAUNCHED','data':{'nonce':'n','pid':2,'boot':'old'}}]
        rows=reconcile(records,'new',lambda _:self.fail('old PID queried'));self.assertEqual(rows[0]['disposition'],'PRIOR_BOOT_EXCEPTION')
    def test_interrupted_launch_intent_blocks_same_boot(self):
        records=[{'event':'LAUNCH_INTENT','data':{'nonce':'n','boot':'b'}}]
        with self.assertRaisesRegex(ValueError,'INTENT'):reconcile(records,'b',lambda _:None)
    def test_inspection_error_not_absence(self):
        def failed(_):raise PermissionError()
        with self.assertRaises(PermissionError):reconcile([{'event':'CHILD_LAUNCHED','data':{'nonce':'n','pid':2,'boot':'b'}}],'b',failed)
    def test_profile_network_is_only_selected_loopback_port(self):
        text=profile('/source','/runtime','/work','/python',39421,'/canary')
        for literal in ('(deny network*)','127.0.0.1:39421','(deny process-fork)','(deny file-write*)','(deny file-read-data (literal "/canary"))'):self.assertIn(literal,text)
        self.assertNotIn('(subpath "/")',text)
    def test_non_mac_cannot_issue_native_evidence(self):
        with patch('iios_qualification_v2.native.platform.system',return_value='Linux'):
            with self.assertRaisesRegex(ValueError,'SELECTED_MAC'):selected_host(self.root/'absent','workflow.yml')
    def test_hosted_job_cannot_issue_native_evidence(self):
        host=self.root/'host';host.write_text('{}');host.chmod(0o600)
        with patch('iios_qualification_v2.native.platform.system',return_value='Darwin'),patch('iios_qualification_v2.native.platform.machine',return_value='arm64'),patch.dict(os.environ,{'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted'}):
            with self.assertRaisesRegex(ValueError,'SELF_HOSTED'):selected_host(host,'workflow.yml')

    def test_cancel_is_red_and_cleanup_runs(self):
        calls=[]
        def cancel():raise KeyboardInterrupt()
        stages={name:(lambda: {}) for name in STAGES[:-1]};stages['ownership']=cancel
        stages['cleanup']=lambda:calls.append('cleanup') or {'verified':True}
        result=execute(Store(self.root/'cancel'),stages,source='s',boot='b',resume=False,issuer=None,evidence=self.root/'evidence')
        self.assertEqual(result['status'],'RED');self.assertEqual(calls,['cleanup'])
    def test_export_failure_cannot_issue_green(self):
        stages={name:(lambda: {}) for name in STAGES[:-1]}
        with patch('iios_qualification_v2.cli.export',side_effect=OSError('disk full')):
            result=execute(Store(self.root/'export-fail'),stages,source='s',boot='b',resume=False,issuer=None,evidence=self.root/'evidence')
        self.assertEqual(result['status'],'RED');self.assertEqual(result['failure']['stage'],'export')
