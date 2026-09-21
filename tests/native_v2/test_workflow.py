import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'BACK END/backend'))
from iios_qualification_v2.state import *
from iios_qualification_v2.cli import execute
from iios_qualification_v2.native import (reconcile, profile, selected_host, os_denial_log_argv,
                                           os_denial_telemetry, require_os_denial_attribution,
                                           require_file_attribution_prerequisite, require_separate_network_denial)

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
        for literal in ('(deny network*)','(local tcp "*:39421")','(remote tcp "*:39421")','(deny process-fork)','(deny file-write*)','(deny file-read-data (literal "/canary"))'):self.assertIn(literal,text)
        self.assertNotIn('(subpath "/")',text)

    def test_os_denial_telemetry_counts_only_independently_returned_records(self):
        pid=2468;target='/private/tmp/iios-canary';operation='file-read-data'
        stdout=(b'info Sandbox: probe(2468) deny file-read-data '+target.encode()+b'\n'
                b'info Sandbox: probe(2468) deny file-read-data /different\n'
                b'info Sandbox: probe(9999) deny file-read-data '+target.encode()+b'\n')
        telemetry=os_denial_telemetry(pid,operation,target,tool_exit_timeout_category='EXIT_0',stdout=stdout,
                                      stderr=b'diagnostic-not-retained')
        self.assertEqual(telemetry['returned_record_count'],3)
        self.assertEqual(telemetry['pid_match_count'],2)
        self.assertEqual(telemetry['sandbox_sender_count'],3)
        self.assertEqual(telemetry['deny_action_count'],3)
        self.assertEqual(telemetry['operation_match_count'],3)
        self.assertEqual(telemetry['target_match_count'],2)
        self.assertEqual(telemetry['all_fields_attributable_count'],1)
        self.assertEqual(telemetry['expected_target']['category'],'ABSOLUTE_FILE_PATH')
        self.assertEqual(telemetry['target_representation_counts'],{'EXACT_CANONICAL':1,'OTHER':1})
        self.assertEqual(telemetry['stdout']['bytes'],len(stdout))
        self.assertEqual(len(telemetry['stdout']['sha256']),64)
        require_os_denial_attribution(telemetry)
        require_file_attribution_prerequisite(telemetry)

    def test_macos_wildcard_network_target_is_diagnosed_but_never_attributed(self):
        stdout=b'info Sandbox: Python(2468) deny(1) network-outbound remote:*:43117\n'
        telemetry=os_denial_telemetry(2468,'network-outbound','127.0.0.1:43117',
                                      tool_exit_timeout_category='EXIT_0',stdout=stdout)
        self.assertEqual(telemetry['operation_match_count'],1)
        self.assertEqual(telemetry['target_match_count'],0)
        self.assertEqual(telemetry['all_fields_attributable_count'],0)
        self.assertEqual(telemetry['expected_target']['category'],'IPV4_LOOPBACK_EXACT_PORT')
        self.assertEqual(telemetry['target_representation_counts'],{'REMOTE_WILDCARD_HOST_EXACT_PORT':1})
        representation=telemetry['target_representation_records'][0]
        self.assertEqual(representation['prefix'],'REMOTE_WILDCARD_HOST')
        self.assertEqual(representation['escaping'],'NONE')
        self.assertEqual(representation['quoting'],'NONE')
        self.assertEqual(representation['truncation'],'ABSENT')
        self.assertNotIn('remote:*:43117',json.dumps(telemetry))
        with self.assertRaisesRegex(ValueError,'OS_DENIAL_ATTRIBUTION_UNAVAILABLE'):
            require_os_denial_attribution(telemetry)
        require_separate_network_denial(telemetry)

    def test_network_denial_requires_one_joint_pid_sender_deny_operation_record(self):
        telemetry=os_denial_telemetry(2468,'network-outbound','127.0.0.1:43117',tool_exit_timeout_category='EXIT_0',
                                      stdout=(b'info Sandbox: Python(9999) deny(1) network-outbound remote:*:43117\n'
                                              b'info Python(2468) deny(1) network-outbound remote:*:43117\n'))
        self.assertEqual(telemetry['target_representation_total_count'],0)
        with self.assertRaisesRegex(ValueError,'NETWORK_DENIAL_OBSERVATION_UNAVAILABLE'):
            require_separate_network_denial(telemetry)

    def test_os_denial_attribution_never_accepts_child_denial_or_tool_failure(self):
        telemetry=os_denial_telemetry(1,'file-read-data','/canary',tool_exit_timeout_category='EXIT_0',
                                      stdout=b'child outcome DENIED errno 13\n')
        self.assertEqual(telemetry['all_fields_attributable_count'],0)
        with self.assertRaisesRegex(ValueError,'OS_DENIAL_ATTRIBUTION_UNAVAILABLE'):
            require_os_denial_attribution(telemetry)
        tool_failed=dict(telemetry,tool_exit_timeout_category='TIMEOUT',all_fields_attributable_count=1)
        with self.assertRaisesRegex(ValueError,'OS_DENIAL_TOOL_UNAVAILABLE'):
            require_os_denial_attribution(tool_failed)

    def test_os_denial_log_query_is_fixed_and_pid_bound(self):
        self.assertEqual(os_denial_log_argv(2468),['/usr/bin/log','show','--last','2m','--style','compact','--predicate',
                         'eventMessage CONTAINS "(2468)" AND eventMessage CONTAINS "deny"'])

    def test_selected_mac_prerequisite_is_synthetic_and_never_qualification(self):
        text=(Path(__file__).resolve().parents[2]/'scripts/verify-os-denial-attribution.py').read_text()
        for value in ('SYNTHETIC_MACOS_SANDBOX_DENIAL','collect_os_denial_attribution(child.pid',
                      "'file-read-data'",'require_os_denial_attribution(file_telemetry)',
                      'EXACT_FILE_REPRESENTATION_NOT_OBSERVED','exact_file_representation_regression=\'GREEN\'',
                      'REMOTE_WILDCARD_HOST_EXACT_PORT',"exact_target_proven=False",'qualification_attribution=\'RED\'',
                      "qualification_launched=False",'provider_requests=0','trade_execution=False'):
            self.assertIn(value,text)

    def test_confinement_uses_exact_file_prerequisite_and_separate_network_evidence(self):
        text=(Path(__file__).resolve().parents[2]/'BACK END/backend/iios_qualification_v2/native.py').read_text()
        self.assertIn("'OS_DENIAL_ATTRIBUTION_PREREQUISITE'",text)
        self.assertIn("canonical=target.resolve(strict=True)",text)
        self.assertIn("'OS_DENIAL_CANARY_REPLACED'",text)
        self.assertIn("'OS_DENIAL_CANARY_RETAINED'",text)
        self.assertIn('require_file_attribution_prerequisite(telemetry)',text)
        self.assertIn("event='NETWORK_DENIAL_TELEMETRY'",text)
        self.assertIn('require_separate_network_denial(telemetry)',text)
        self.assertIn("result['exact_host_attribution']=telemetry['all_fields_attributable_count']>0",text)
    def test_non_mac_cannot_issue_native_evidence(self):
        with patch('iios_qualification_v2.native.platform.system',return_value='Linux'):
            with self.assertRaisesRegex(ValueError,'SELECTED_MAC'):selected_host(self.root/'absent')
    def test_hosted_job_cannot_issue_native_evidence(self):
        host=self.root/'host';host.write_text(json.dumps({'schema':3,'control_repository':'mielechris/IIOS-Native-Control','control_repository_id':1,'control_owner_id':2,'control_ref':'refs/heads/main','workflow':'native-qualification.yml','source':{'repository':'mielechris/Investment-Intelligence-OS','commit':'a'*40,'inventory_sha256':'b'*64},'runner_name':'selected','hardware_uuid':'00000000-0000-0000-0000-000000000000','uid':os.getuid()}));host.chmod(0o600)
        with patch('iios_qualification_v2.native.platform.system',return_value='Darwin'),patch('iios_qualification_v2.native.platform.machine',return_value='arm64'),patch.dict(os.environ,{'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted'}):
            with self.assertRaisesRegex(ValueError,'SELF_HOSTED'):selected_host(host)
    def test_tag_or_pull_request_context_rejected(self):
        value={'schema':3,'control_repository':'mielechris/IIOS-Native-Control','control_repository_id':1,'control_owner_id':2,'control_ref':'refs/heads/main','workflow':'native-qualification.yml','source':{'repository':'mielechris/Investment-Intelligence-OS','commit':'a'*40,'inventory_sha256':'b'*64},'runner_name':'selected','hardware_uuid':'00000000-0000-0000-0000-000000000000','uid':os.getuid()}
        host=self.root/'host';host.write_text(json.dumps(value));host.chmod(0o600)
        env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'self-hosted','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REPOSITORY':value['control_repository'],'GITHUB_REPOSITORY_ID':'1','GITHUB_REPOSITORY_OWNER_ID':'2','RUNNER_NAME':'selected','GITHUB_WORKFLOW_REF':value['control_repository']+'/.github/workflows/native-qualification.yml@refs/heads/main','GITHUB_REF':'refs/tags/v1','GITHUB_REF_TYPE':'tag','GITHUB_HEAD_REF':'fork','GITHUB_BASE_REF':'main'}
        with patch('iios_qualification_v2.native.platform.system',return_value='Darwin'),patch('iios_qualification_v2.native.platform.machine',return_value='arm64'),patch.dict(os.environ,env,clear=True):
            with self.assertRaisesRegex(ValueError,'TRUSTED_REF'):selected_host(host)

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
