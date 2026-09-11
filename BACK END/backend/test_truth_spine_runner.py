"""Source-only runner proofs. No operational roots, credentials or host PIDs."""
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    'isolated_shadow_runner', Path(__file__).resolve().parents[2]/'scripts/truth_spine_integration_runner.py')
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class HistoricalAcceptanceTests(unittest.TestCase):
    def test_protected_listener_census_rejects_extra_ports_or_substituted_owner(self):
        expected=[{'pid':900001,'address':'127.0.0.1','port':6000}]
        for text in ('p900001\nn127.0.0.1:6000\nn127.0.0.1:6001\n','p900002\nn127.0.0.1:6000\n'):
            with patch.object(runner.subprocess,'run',return_value=Mock(returncode=0,stdout=text,stderr='')):
                with self.assertRaises(runner.RunnerFailure):runner.protected_listeners(expected)
        with patch.object(runner.subprocess,'run',return_value=Mock(returncode=0,stdout='p900001\nn127.0.0.1:6000\n',stderr='')):
            self.assertEqual(runner.protected_listeners(expected),expected)

    def test_protected_census_rejects_missing_extra_or_unresolved_members(self):
        observed=runner.ProcessObservation(900001,900000,'stamp','node','/synthetic/node','a'*64,'/synthetic',('node',))
        row=runner.asdict(observed);row.pop('command');row['argv']=list(row['argv'])
        self.assertEqual(runner.protected_processes([row],census=[(900001,'/synthetic/node')],inspector=lambda _:observed),[row])
        for census,inspector in [([],lambda _:observed), ([(900001,'/synthetic/node'),(900002,'/synthetic/node')],
                                  lambda pid:replace(observed,pid=pid)), ([(900001,'/synthetic/node')],lambda _:None)]:
            with self.assertRaises(runner.RunnerFailure):runner.protected_processes([row],census=census,inspector=inspector)

    def wrapper(self, **kwargs):
        from test_truth_spine_lineage import retained_root
        from truth_spine_contract import canonical,seal
        from truth_spine_lineage import write_new
        root=retained_root('browser-wrapper');(root/'browser').mkdir()
        child=Child(900001,**kwargs)
        observed=runner.ProcessObservation(child.pid,900000,'2026-09-09T00:00:00+00:00','node wrapper',
                                           '/synthetic/node','a'*64,str(root),('node','wrapper'))
        data=runner.asdict(observed);data['argv']=list(data['argv'])
        receipt=seal({'schema':'iios-browser-wrapper-startup-v1','observation':data,'root':str(root),
                      'port':6000,'package_hash':'b'*64,'contract_hash':'c'*64,'backend_hash':'d'*64})
        h=write_new(root,'browser/wrapper-startup.json',canonical(receipt))
        return root,child,observed,receipt,h

    def test_wrapper_pid_reuse_and_each_fingerprint_mismatch_never_signaled(self):
        for field,value in {'pid':900002,'parent_pid':1,'start_time':'changed','command':'changed',
                            'executable':'/other','executable_hash':'f'*64,'cwd':'/other','argv':('other',)}.items():
            root,child,observed,receipt,h=self.wrapper()
            result=runner.cleanup_browser_wrapper(child,receipt,h,root,inspector=lambda _:replace(observed,**{field:value}))
            self.assertEqual(child.signals,[]);self.assertTrue(result['remaining']);self.assertTrue(result['errors'])

    def test_wrapper_cleanup_continues_and_reverifies_after_terminate_failure(self):
        root,child,observed,receipt,h=self.wrapper(terminate_error=OSError('synthetic'))
        inspector=Mock(return_value=observed)
        result=runner.cleanup_browser_wrapper(child,receipt,h,root,inspector=inspector)
        self.assertEqual(child.signals,['terminate','kill']);self.assertEqual(inspector.call_count,2)
        self.assertFalse(result['remaining']);self.assertTrue(result['errors'])
        self.assertTrue((root/'browser/wrapper-cleanup-0.json').is_file())
        self.assertTrue((root/'browser/wrapper-cleanup-1.json').is_file())

    def test_wrapper_wrong_independent_receipt_hash_rejected(self):
        root,child,observed,receipt,_=self.wrapper()
        result=runner.cleanup_browser_wrapper(child,receipt,'e'*64,root,inspector=lambda _:observed)
        self.assertEqual(child.signals,[]);self.assertTrue(result['remaining'])

    def test_new_lineage_evidence_never_overwrites_existing_receipt(self):
        from test_truth_spine_lineage import retained_root
        root=retained_root('exclusive-runner')/'iios-truth-spine-3-acceptance-sb38d-clean-synthetic'
        root.mkdir()
        runner.atomic_evidence(root,'acceptance.json',{'first':True})
        original=(root/'acceptance.json').read_bytes()
        with self.assertRaises(FileExistsError):runner.atomic_evidence(root,'acceptance.json',{'second':True})
        self.assertEqual((root/'acceptance.json').read_bytes(),original)

    def test_stable_port_clear_requires_two_empty_owned_observations(self):
        calls=[]
        result=runner.stable_port_clear(6000,probe=lambda p:calls.append(p) or True,pause=lambda _:None,listeners=lambda:[])
        self.assertEqual(calls,[6000,6000]);self.assertEqual(len(result['samples']),2)
        with self.assertRaises(runner.RunnerFailure):
            runner.stable_port_clear(6000,probe=lambda _:True,pause=lambda _:None,listeners=lambda:[{'pid':999}])
        probes=iter([True,False])
        with self.assertRaises(runner.RunnerFailure):
            runner.stable_port_clear(6000,probe=lambda _:next(probes),pause=lambda _:None,listeners=lambda:[])

    def test_cleanup_alone_never_satisfies_consolidation(self):
        from test_truth_spine_lineage import retained_root
        root=retained_root('consolidation')
        report={'clean_shutdown':True,'port_clear':True,'cleanup_errors':[],
                'unresolved_children':[],'rollback':True,'input_preservation':True,'source_preservation':True}
        with self.assertRaisesRegex(ValueError,'PACKAGE_BROWSER_REQUIRED'):
            runner.consolidate(root,'a'*64,'b'*64,report,{}, {})
        self.assertEqual(list(root.iterdir()),[])

    def test_changed_baseline_rejects_before_browser_reads(self):
        from test_truth_spine_lineage import retained_root
        root=retained_root('consolidation')
        with self.assertRaisesRegex(ValueError,'ACCEPTANCE_PRESERVATION_GATE'):
            runner.consolidate(root,'a'*64,'b'*64,{}, {'before':1},{'after':2})
        self.assertEqual(list(root.iterdir()),[])


class Child:
    def __init__(self, pid, waits=(), terminate_error=None, kill_error=None, on_exit=None):
        self.pid, self.returncode = pid, None
        self.waits, self.signals = list(waits), []
        self.terminate_error, self.kill_error, self.on_exit = terminate_error, kill_error, on_exit

    def poll(self):
        return self.returncode

    def terminate(self):
        self.signals.append('terminate')
        if self.terminate_error:
            raise self.terminate_error

    def kill(self):
        self.signals.append('kill')
        if self.kill_error:
            raise self.kill_error

    def wait(self, timeout):
        assert 0 < timeout <= 30
        result = self.waits.pop(0) if self.waits else 0
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            return result()
        self.returncode = result
        if self.on_exit:
            self.on_exit()
        return result


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='iios-runner-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.observations, self.written = {}, {}
        self.receipts = {}
        (self.root/'topology.json').write_text('{}')
        (self.root/'authority.json').write_text('{}')
        self.port = Mock(return_value=True)
        self.owner = runner.OwnedChildren(
            self.root, inspector=lambda pid: self.observations.get(pid),
            writer=lambda root, name, value: self.written.update({name: json.loads(json.dumps(value))}),
            port_clear=self.port, parent_pid=900000, timeout=1,
            receipt_reader=lambda root, instance: self.receipts.get(instance), pause=lambda _: None)
        self.argv = lambda role: ['/isolated/python', '-B', '-m', 'truth_spine_integration_service',
                                 '--config', str(self.root/'topology.json'), '--role', role]+(['--port', '45678'] if role=='backend' else [])

    def add(self, role='scheduler', **kwargs):
        child = Child(900001+len(self.observations), **kwargs)
        port = 45678 if role == 'backend' else None
        launch = self.owner.prepare_launch(role, self.argv(role), port=port,
                                          executable_hashes={'/isolated/python': 'a'*64})
        self.observations[child.pid] = runner.ProcessObservation(
            child.pid, 900000, 'Wed Sep 9 10:00:00 2026', ' '.join(launch.argv),
            '/isolated/python', 'a'*64, str(self.root/'release/backend'), launch.argv)
        doc = {**dict(launch.values), 'observation': runner.normalized(self.observations[child.pid], self.root)}
        doc['content_hash'] = runner.digest(doc)
        self.receipts[dict(launch.values)['instance_id']] = doc
        fp = self.owner.register(role, child, launch.argv, self.root/'release/backend', port,
                                 executable_hashes={'/isolated/python': 'a'*64}, launch=launch)
        return child, fp

    def test_fingerprint_complete_frozen_and_independently_verified(self):
        child, fp = self.add()
        self.assertEqual(fp.observed.pid, child.pid)
        self.assertEqual(fp.runner_identity, self.owner.identity)
        self.assertEqual(fp.shadow_root, str(self.root))
        self.assertEqual(fp.argv, self.observations[child.pid].argv)
        self.assertTrue(datetime.fromisoformat(fp.created_at).tzinfo)
        with self.assertRaises(FrozenInstanceError):
            fp.role = 'publisher'
        self.assertTrue(self.owner.attempts[-1]['matched'])

    def mismatch(self, **changes):
        child, _ = self.add()
        self.observations[child.pid] = replace(self.observations[child.pid], **changes)
        result = self.owner.cleanup({})
        self.assertEqual(child.signals, [])
        self.assertEqual(result['result'], 'RED')
        self.assertEqual(len(result['unresolved_children']), 1)
        self.assertEqual(result['cleanup_errors'][0]['category'], 'PROCESS_IDENTITY_MISMATCH')
        self.port.assert_called_once()

    def test_reused_pid_command_not_signaled(self):
        self.mismatch(command='/unrelated/process')

    def test_reused_pid_start_time_not_signaled(self):
        self.mismatch(start_time='Wed Sep 9 10:00:01 2026')

    def test_changed_root_not_signaled(self):
        self.mismatch(cwd='/unrelated/root')

    def test_changed_executable_not_signaled(self):
        self.mismatch(executable_hash='b'*64)

    def test_changed_parent_not_signaled(self):
        self.mismatch(parent_pid=900099)

    def test_missing_process_no_signal_and_retained(self):
        child, _ = self.add()
        self.observations.pop(child.pid)
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertEqual(child.signals, [])
        self.assertIn('scheduler', self.owner.active)

    def test_inspector_exception_no_signal(self):
        child, _ = self.add()
        self.owner.inspector = Mock(side_effect=PermissionError('not reported'))
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertEqual(child.signals, [])

    def test_graceful_exit_untracks_only_after_wait(self):
        child, fp = self.add()
        def exit_now():
            self.assertIn('scheduler', self.owner.active)
            child.returncode = 0
            return 0
        child.waits = [exit_now]
        self.assertTrue(self.owner.stop('scheduler'))
        self.assertNotIn('scheduler', self.owner.active)
        self.assertEqual(child.signals, ['terminate'])
        self.assertEqual(self.owner.completed[0]['outcome'], 'STOPPED_CLEANLY')
        self.assertEqual(self.owner.completed[0]['fingerprint']['observed']['pid'], fp.observed.pid)

    def test_already_reaped_verified_child_never_signaled(self):
        child, _ = self.add()
        child.returncode = 7
        self.observations.pop(child.pid)
        self.assertTrue(self.owner.stop('scheduler'))
        self.assertEqual(child.signals, [])
        self.assertEqual(self.owner.completed[0]['outcome'], 'ALREADY_EXITED_VERIFIED_CHILD')

    def test_timeout_force_stop_reverifies(self):
        child, _ = self.add(waits=[subprocess.TimeoutExpired('fake', 1), -9])
        self.assertTrue(self.owner.stop('scheduler'))
        actions = [x['action'] for x in self.owner.attempts]
        self.assertEqual(actions[-5:], ['VERIFY', 'TERMINATE', 'GRACEFUL_TIMEOUT', 'VERIFY', 'KILL'])
        self.assertEqual(child.signals, ['terminate', 'kill'])
        self.assertEqual(self.owner.completed[0]['outcome'], 'FORCE_STOPPED_AFTER_VERIFIED_TIMEOUT')

    def test_identity_changes_after_timeout_no_force(self):
        child, _ = self.add()
        def timeout():
            self.observations[child.pid] = replace(self.observations[child.pid], start_time='changed')
            raise subprocess.TimeoutExpired('fake', 1)
        child.waits = [timeout]
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertEqual(child.signals, ['terminate'])
        self.assertIn('scheduler', self.owner.active)

    def test_terminate_exception_retains_child(self):
        child, _ = self.add(terminate_error=OSError('private exception'))
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertIn('scheduler', self.owner.active)
        self.assertNotIn('private exception', json.dumps(self.owner.errors))

    def test_wait_exception_retains_child(self):
        child, _ = self.add(waits=[OSError('wait')])
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertEqual(child.signals, ['terminate'])

    def test_force_exception_retains_child(self):
        child, _ = self.add(waits=[subprocess.TimeoutExpired('fake', 1)], kill_error=OSError('kill'))
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertEqual(child.signals, ['terminate', 'kill'])
        self.assertIn('scheduler', self.owner.active)

    def test_force_wait_timeout_retains_child(self):
        child, _ = self.add(waits=[subprocess.TimeoutExpired('fake', 1)]*2)
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertIsNone(child.poll())

    def test_reverse_cleanup_continues_after_first_child_failure(self):
        self.add('scheduler')
        self.add('publisher')
        self.add('backend', terminate_error=RuntimeError('bad'))
        result = self.owner.cleanup({})
        self.assertEqual([x['role'] for x in result['stop_attempts'] if x['action'] == 'TERMINATE'][:3],
                         ['backend', 'backend', 'publisher'])  # failed action also carries its diagnostic
        self.assertEqual([x['role'] for x in result['completed_processes']], ['publisher', 'scheduler'])
        self.assertEqual(list(self.owner.active), ['backend'])
        self.port.assert_called_once()

    def test_all_stops_fail_still_close_logs_and_check_port(self):
        for role in runner.ROLES:
            self.add(role, terminate_error=OSError('bad'))
        handles = [io.StringIO(), io.StringIO()]
        self.owner.logs.extend(handles)
        result = self.owner.cleanup({})
        self.assertEqual(len(result['unresolved_children']), 3)
        self.assertTrue(all(x.closed for x in handles))
        self.port.assert_called_once()
        self.assertEqual(result['result'], 'RED')

    def test_log_close_failure_does_not_skip_other_log(self):
        bad = Mock(); bad.close.side_effect = OSError('bad')
        good = io.StringIO()
        self.owner.logs = [bad, good]
        result = self.owner.cleanup({})
        self.assertTrue(good.closed)
        self.assertEqual(result['cleanup_errors'][0]['category'], 'LOG_CLOSURE_FAILED')
        self.assertFalse(result['clean_shutdown'])

    def test_occupied_port_is_red(self):
        self.port.return_value = False
        result = self.owner.cleanup({})
        self.assertFalse(result['port_clear'])
        self.assertFalse(result['clean_shutdown'])

    def test_port_check_exception_is_red(self):
        self.port.side_effect = OSError('private')
        result = self.owner.cleanup({})
        self.assertEqual(result['cleanup_errors'][0]['category'], 'PORT_CHECK_FAILED')

    def test_normal_persistence_failure_emergency_and_other_output_attempted(self):
        calls = []
        def writer(root, name, value):
            calls.append(name)
            if name == 'runner-incidents.json':
                raise OSError('private')
            self.written[name] = json.loads(json.dumps(value))
        self.owner.writer = writer
        result = self.owner.cleanup({})
        self.assertEqual(calls, ['runner-incidents.json', 'acceptance.json', 'emergency-incident.json'])
        self.assertEqual(result['result'], 'RED')
        self.assertEqual(self.written['emergency-incident.json']['result'], 'RED')
        self.assertNotIn('private', json.dumps(result))

    def test_all_persistence_failure_remains_red(self):
        self.owner.writer = Mock(side_effect=OSError('private'))
        result = self.owner.cleanup({})
        self.assertEqual(self.owner.writer.call_count, 3)
        self.assertEqual(result['cleanup_errors'][-1]['category'], 'EMERGENCY_PERSISTENCE_FAILED')

    def test_repeated_cleanup_has_no_extra_signals_or_writes(self):
        child, _ = self.add()
        first = self.owner.cleanup({})
        self.assertIs(self.owner.cleanup({}), first)
        self.assertEqual(child.signals, ['terminate'])
        self.port.assert_called_once()

    def test_partial_startup_unverified_child_never_signaled(self):
        self.add('scheduler')
        child = Child(999999)
        with self.assertRaises(runner.RunnerFailure):
            self.owner.register('publisher', child, self.argv('publisher'), self.root/'release/backend',
                                executable_hashes={'/isolated/python': 'a'*64})
        result = self.owner.cleanup({})
        self.assertEqual(child.signals, [])
        self.assertEqual(len(result['completed_processes']), 1)
        self.assertEqual(result['unresolved_children'][0]['role'], 'publisher')

    def test_keyboard_interrupt_still_cleans_up(self):
        child, _ = self.add()
        result = self.owner.cleanup({}, KeyboardInterrupt())
        self.assertEqual(child.signals, ['terminate'])
        self.assertEqual(result['primary_exception']['type'], 'KeyboardInterrupt')
        self.assertEqual(result['result'], 'RED')

    def test_primary_and_cleanup_exceptions_preserved_sanitized(self):
        self.add(terminate_error=OSError('PRIVATE_SECRET'))
        result = self.owner.cleanup({}, ValueError('PRIVATE_SECRET'))
        self.assertEqual(result['primary_exception'], {'type': 'ValueError'})
        self.assertEqual(result['cleanup_errors'][0]['exception_type'], 'OSError')
        self.assertNotIn('PRIVATE_SECRET', json.dumps(result))

    def test_unrestricted_runner_failure_not_persisted(self):
        result = self.owner.cleanup({}, runner.RunnerFailure('/private/secret value'))
        self.assertEqual(result['primary_exception'], {'type': 'RunnerFailure'})

    def test_complete_atomic_reports(self):
        self.owner.writer = runner.atomic_evidence
        self.add()
        self.owner.cleanup({'readiness_transitions': [200, 503, 200], 'duplicate_owner_tests': []})
        for name in ('acceptance.json', 'runner-incidents.json'):
            path = self.root/name
            record = json.loads(path.read_bytes())
            self.assertEqual(record['result'], 'GREEN')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for key in ('child_fingerprints', 'stop_attempts', 'cleanup_errors', 'unresolved_children',
                        'log_closure', 'port_clear', 'readiness_transitions', 'duplicate_owner_tests'):
                self.assertIn(key, record)
        self.assertFalse(list(self.root.glob('*.staging')))

    def test_atomic_failure_preserves_prior_bytes(self):
        runner.atomic_evidence(self.root, 'acceptance.json', {'old': True})
        prior = (self.root/'acceptance.json').read_bytes()
        with patch.object(runner.os, 'replace', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                runner.atomic_evidence(self.root, 'acceptance.json', {'new': True})
        self.assertEqual((self.root/'acceptance.json').read_bytes(), prior)
        self.assertFalse(list(self.root.glob('*.staging')))

    def test_atomic_writer_rejects_escape_and_symlink(self):
        with self.assertRaises(runner.RunnerFailure):
            runner.atomic_evidence(self.root, '../escape', {})
        (self.root/'acceptance.json').symlink_to(self.root/'not-owned')
        with self.assertRaises(runner.RunnerFailure):
            runner.atomic_evidence(self.root, 'acceptance.json', {})
        self.assertFalse((self.root/'not-owned').exists())

    def test_unknown_executable_pin_rejects_spawn(self):
        child, _ = self.add()
        self.owner.stop('scheduler')
        child.returncode = None
        with self.assertRaises(runner.RunnerFailure):
            self.owner.register('scheduler', child, self.argv('scheduler'), self.root/'release/backend',
                                executable_hashes={'/isolated/python': 'wrong'})
        child.signals.clear()
        self.owner.cleanup({})
        self.assertEqual(child.signals, [])

    def test_duplicate_reaped_rejection_preserves_owner_and_events(self):
        for role in runner.ROLES:
            with self.subTest(role=role):
                child, _ = self.add(role)
                duplicate = Child(child.pid+100); duplicate.returncode = 4; duplicate.waits = [4]
                result = runner.rejected_duplicate(
                    role, self.owner, self.argv(role), spawn=lambda argv: duplicate,
                    counts=lambda: (8, 8), lock_bytes=lambda role: b'owner',
                    executable_hashes={'/isolated/python': 'a'*64}, port=45678 if role=='backend' else None)
                self.assertTrue(result['rejected'])
                self.assertEqual(child.signals+duplicate.signals, [])

    def test_duplicate_wrong_success_is_failure(self):
        child, _ = self.add()
        duplicate = Child(child.pid+100); duplicate.returncode = 0
        with self.assertRaisesRegex(runner.RunnerFailure, 'DUPLICATE_OWNER'):
            runner.rejected_duplicate('scheduler', self.owner, self.argv('scheduler'),
                spawn=lambda argv: duplicate, counts=lambda: (0, 0), lock_bytes=lambda role: b'owner',
                executable_hashes={'/isolated/python': 'a'*64})

    def test_live_duplicate_verified_before_rejection(self):
        child, _ = self.add()
        duplicate = Child(900010, waits=[4])
        self.observations[duplicate.pid] = replace(self.observations[child.pid], pid=duplicate.pid)
        result = runner.rejected_duplicate('scheduler', self.owner, self.argv('scheduler'),
            spawn=lambda argv: duplicate, counts=lambda: (8, 8), lock_bytes=lambda role: b'owner',
            executable_hashes={'/isolated/python': 'a'*64})
        self.assertTrue(result['rejected'])
        self.assertEqual(duplicate.signals, [])
        self.assertNotIn('duplicate-scheduler', self.owner.active)
        self.assertEqual(len(self.owner.fingerprints), 1)  # Reaped contender is never an owner.

    def test_live_duplicate_timeout_retained_for_verified_cleanup(self):
        child, _ = self.add()
        duplicate = Child(900010, waits=[subprocess.TimeoutExpired('fake', 1), 0])
        def spawn(argv):
            self.observations[duplicate.pid] = replace(self.observations[child.pid], pid=duplicate.pid,
                                                       argv=argv, command=' '.join(argv))
            launch = self.owner.launches[argv[argv.index('--instance-id')+1]]
            doc = {**dict(launch.values), 'observation': runner.normalized(self.observations[duplicate.pid],self.root)}
            doc['content_hash'] = runner.digest(doc); self.receipts[doc['instance_id']] = doc
            return duplicate
        with self.assertRaisesRegex(runner.RunnerFailure, 'DUPLICATE_DID_NOT_EXIT'):
            runner.rejected_duplicate('scheduler', self.owner, self.argv('scheduler'),
                spawn=spawn, counts=lambda: (8, 8), lock_bytes=lambda role: b'owner',
                executable_hashes={'/isolated/python': 'a'*64})
        self.assertIn('duplicate-scheduler', self.owner.active)
        result = self.owner.cleanup({}, runner.RunnerFailure('DUPLICATE_DID_NOT_EXIT'))
        self.assertEqual(result['result'], 'RED')
        self.assertEqual(duplicate.signals, ['terminate'])
        self.assertFalse(result['unresolved_children'])

    def test_unverified_duplicate_never_signaled(self):
        self.add()
        duplicate = Child(900010, waits=[subprocess.TimeoutExpired('fake', 1)])
        with self.assertRaises(runner.RunnerFailure):
            runner.rejected_duplicate('scheduler', self.owner, self.argv('scheduler'),
                spawn=lambda argv: duplicate, counts=lambda: (8, 8), lock_bytes=lambda role: b'owner',
                executable_hashes={'/isolated/python': 'a'*64})
        result = self.owner.cleanup({})
        self.assertEqual(duplicate.signals, [])
        self.assertEqual(result['result'], 'RED')

    def test_duplicate_lock_or_event_mutation_rejected(self):
        self.add()
        for altered in ('lock', 'events'):
            duplicate = Child(900010, waits=[4]); duplicate.returncode = 4
            counts = Mock(side_effect=[(8, 8), (9, 9)]) if altered == 'events' else lambda: (8, 8)
            locks = Mock(side_effect=[b'owner', b'other']) if altered == 'lock' else lambda role: b'owner'
            with self.subTest(altered=altered), self.assertRaises(runner.RunnerFailure):
                runner.rejected_duplicate('scheduler', self.owner, self.argv('scheduler'),
                    spawn=lambda argv: duplicate, counts=counts, lock_bytes=locks,
                    executable_hashes={'/isolated/python': 'a'*64})

    def test_stop_keyboard_interrupt_still_attempts_other_children(self):
        self.add('scheduler')
        self.add('publisher', terminate_error=KeyboardInterrupt())
        result = self.owner.cleanup({})
        self.assertEqual(result['completed_processes'][0]['role'], 'scheduler')
        self.assertEqual(result['cleanup_errors'][0]['exception_type'], 'KeyboardInterrupt')
        self.port.assert_called_once()

    def test_bound_timeout_required(self):
        for timeout in (0, -1, 31):
            with self.assertRaises(ValueError):
                runner.OwnedChildren(self.root, timeout=timeout)

    def test_macos_inspector_fixed_bounded_commands(self):
        executable = self.root/'interpreter'; executable.write_bytes(b'isolated')
        outputs = ['Wed Sep 9 10:00:00 2026', '900000',
                   str(executable), 'p900001\nn'+str(self.root/'release/backend')]
        run = Mock(side_effect=[subprocess.CompletedProcess([], 0, x, '') for x in outputs])
        with patch.object(runner.subprocess, 'run', run), patch('truth_spine_process_identity.kernel_argv',return_value=(str(executable),'--role','scheduler')):
            observed = runner.inspect_macos(900001)
        self.assertEqual(observed.pid, 900001)
        self.assertEqual(observed.executable_hash, hashlib.sha256(b'isolated').hexdigest())
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs['timeout'], 1)
            self.assertEqual(call.kwargs['env']['TZ'], 'UTC')
            self.assertNotIn('shell', call.kwargs)

    def test_macos_missing_process_none(self):
        with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')):
            self.assertIsNone(runner.inspect_macos(900001))

    def test_macos_inspection_timeout_and_oversize_fail_closed(self):
        with patch.object(runner.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ps', 3)):
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.inspect_macos(900001)
        with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'x'*65537, '')):
            with self.assertRaises(runner.IdentityFailure):
                runner.inspect_macos(900001)

    def test_port_inspection_errors_never_mistaken_for_clear(self):
        from unittest.mock import MagicMock
        for result, expected in ((0, False), (runner.errno.ECONNREFUSED, True),
                                 (runner.errno.EPERM, None), (runner.errno.ETIMEDOUT, None)):
            with self.subTest(result=result):
                check = MagicMock(); check.__enter__.return_value = check
                check.connect_ex.return_value = result
                with patch.object(runner.socket, 'socket', return_value=check):
                    if expected is None:
                        with self.assertRaises(runner.RunnerFailure):
                            runner.port_is_clear(45678)
                    else:
                        self.assertIs(runner.port_is_clear(45678), expected)
                check.settimeout.assert_called_once_with(2)
    def test_readiness_failure_requires_both_503(self):
        for ready, market in ((200, 503), (503, 200), (200, 200)):
            with self.subTest(ready=ready, market=market), self.assertRaises(runner.RunnerFailure):
                runner.readiness_failure(0, 'scheduler', request=lambda port, path: (
                    ready if path.endswith('/ready') else market, {}))
        self.assertEqual(runner.readiness_failure(0, 'scheduler', request=lambda *args: (503, {}))['ready'], 503)

    def test_scheduler_actual_health_200_503_200_new_fingerprint(self):
        import truth_spine_integration_service as service
        from truth_spine_contract import seal
        from truth_spine_integration import atomic
        # Only unrelated package/topology/projection inputs are fixtures. Actual
        # health(), probe(), Lease and heartbeat paths decide scheduler readiness.
        backend = self.root/'release/backend'; backend.mkdir(parents=True)
        runtime = self.root/'runtime/bin'; runtime.mkdir(parents=True)
        python = runtime/'python'; python.write_bytes(b'isolated interpreter identity')
        manifest = seal({'runtime_root': str(runtime.parent),
                         'interpreter_hash': hashlib.sha256(python.read_bytes()).hexdigest()})
        manifest_path = self.root/'release/manifest.json'; atomic(manifest_path, manifest)
        t = {'root': str(self.root), 'content_hash': 'topology', 'phase': 'READ_ONLY',
             'release_manifest': str(manifest_path),
             'release_manifest_hash': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
             'identities': {'scheduler_owner': 'scheduler', 'publisher_owner': 'publisher',
                            'release': 'release', 'executor_generation': 'generation', 'source_cycle': 'source'}}
        a = {'capabilities': {'broker': False, 'paper_order': False, 'promotion': False,
                              'ledger_write': False, 'live_execution': False}}
        p = seal({'topology_identity': t['content_hash'], 'identities': t['identities'],
                  'authority': a['capabilities'], 'published_at': datetime.now(timezone.utc).isoformat()})
        atomic(self.root/'projection.json', p)
        # A canonical sentinel must not be edited to make readiness recover.
        canonical = self.root/'canonical-events.db'; canonical.write_bytes(b'8 immutable events / 8 unique identities')
        before = canonical.read_bytes()
        scheduler = service.Lease(self.root, 'scheduler')
        publisher = service.Lease(self.root, 'publisher')
        self.addCleanup(publisher.close)
        self.addCleanup(lambda: scheduler.close() if scheduler.fd >= 0 else None)
        def stop_lease():
            scheduler.close(); scheduler.fd = -1
        child, first = self.add(on_exit=stop_lease)
        old_entry = dict(self.owner.active['scheduler'])
        def emit_scheduler(fp):
            # OS lease/PID probes here use this test process; the adversarial
            # signaling child remains fake. Production receipt creation is
            # separately exercised by the self-expiring macOS integration test.
            doc = {**dict(fp.launch.values), 'observation': {'pid': os.getpid()}}
            doc['content_hash'] = runner.digest(doc)
            path = self.root/('startup-'+fp.instance_id+'.json')
            atomic(path, doc)
            service.heartbeat(t, 'scheduler', datetime.now(timezone.utc), doc)
        for role in ('scheduler', 'publisher'):
            service.heartbeat(t, role, datetime.now(timezone.utc))
        emit_scheduler(first)
        with ExitStack() as stack:
            stack.enter_context(patch.object(service, 'topology', return_value=(t, a)))
            stack.enter_context(patch.object(service, '__file__', str(backend/'truth_spine_integration_service.py')))
            stack.enter_context(patch.object(service.sys, 'executable', str(python)))
            stack.enter_context(patch.object(service, 'snapshot', return_value=p))
            def request(port, path):
                return service.health(self.root/'topology.json', path.split('/')[-1])
            ready = [request(0, '/health/ready')[0]]
            market = [request(0, '/health/market-readiness')[0]]
            self.assertTrue(self.owner.stop('scheduler'))
            failed = runner.readiness_failure(0, 'scheduler', request=request)
            ready.append(failed['ready']); market.append(failed['market'])
            scheduler = service.Lease(self.root, 'scheduler')
            replacement, second = self.add(on_exit=stop_lease)
            emit_scheduler(second)
            ready.append(request(0, '/health/ready')[0])
            market.append(request(0, '/health/market-readiness')[0])
            self.assertEqual(ready, [200, 503, 200])
            self.assertEqual(market, [503, 503, 503])
            self.assertNotEqual(first.observed.pid, second.observed.pid)
            self.assertNotEqual(first.instance_id, second.instance_id)
            self.assertEqual(json.loads((self.root/'scheduler-heartbeat.json').read_bytes())['instance_id'], second.instance_id)
            # Even simulated PID reuse cannot allow an old fingerprint to
            # control this new owner; no signal is sent on the failed verify.
            old_entry['child'] = replacement
            with self.assertRaises(runner.RunnerFailure):
                self.owner.verify(old_entry)
            self.assertEqual(replacement.signals, [])
            self.assertEqual(canonical.read_bytes(), before)
            self.assertEqual((self.root/'projection.json').read_bytes(),
                             json.dumps(p, sort_keys=True, separators=(',', ':')).encode()+b'\n')
            self.assertTrue(self.owner.stop('scheduler'))


class IsolatedOwnershipTests(unittest.TestCase):
    def test_actual_scheduler_and_publisher_duplicate_lock_rejection(self):
        from truth_spine_integration_service import Lease, heartbeat, probe
        with tempfile.TemporaryDirectory(prefix='iios-lease-unit-') as directory:
            root = Path(directory).resolve()
            t = {'root': str(root), 'content_hash': 'topology', 'identities': {
                'scheduler_owner': 'scheduler', 'publisher_owner': 'publisher',
                'release': 'release', 'executor_generation': 'generation', 'source_cycle': 'source'}}
            for role in ('scheduler', 'publisher'):
                with self.subTest(role=role):
                    lease = Lease(root, role)
                    try:
                        now = datetime.now(timezone.utc)
                        heartbeat(t, role, now)
                        before = (root/(role+'.lock')).read_bytes()
                        with self.assertRaises(BlockingIOError):
                            Lease(root, role)
                        self.assertEqual((root/(role+'.lock')).read_bytes(), before)
                        self.assertEqual(probe(t, role, now)['pid'], os.getpid())
                        with self.assertRaises(ValueError):
                            probe(t, role, now+timedelta(seconds=16))
                    finally:
                        lease.close()
                    with self.assertRaisesRegex(ValueError, 'OWNER_NOT_RUNNING'):
                        probe(t, role, now)
                    restarted = Lease(root, role)
                    try:
                        heartbeat(t, role, datetime.now(timezone.utc))
                        self.assertEqual(probe(t, role)['pid'], os.getpid())
                        with self.assertRaises(BlockingIOError):
                            Lease(root, role)
                    finally:
                        restarted.close()

    def test_actual_backend_second_bind_rejected_original_unchanged(self):
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        server = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
        try:
            address = server.server_address
            with self.assertRaises(OSError):
                ThreadingHTTPServer(address, BaseHTTPRequestHandler)
            self.assertEqual(server.socket.getsockname(), address)
        finally:
            server.server_close()


if __name__ == '__main__':
    unittest.main()
