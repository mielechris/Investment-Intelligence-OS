"""Source-only adversarial ownership tests. Never examines historical/permanent PIDs."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import truth_spine_process_identity as identity
from test_truth_spine_runner import Child, runner


class StabilizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='iios-identity-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root/'topology.json').write_text('{}')
        (self.root/'authority.json').write_text('{}')
        self.tick = 0
        self.receipts, self.written, self.observations = {}, {}, []
        self.current = None
        self.owner = runner.OwnedChildren(self.root, inspector=self.inspect,
            receipt_reader=lambda root, instance:self.receipts.get(instance),
            writer=lambda root, name, value:self.written.update({name:json.loads(json.dumps(value))}),
            parent_pid=900000, port_clear=lambda:True, monotonic=lambda:self.tick,
            pause=self.advance, stabilization_seconds=.5, timeout=1)
        self.pins = {'/test/launcher':'a'*64, '/test/framework':'b'*64}

    def advance(self, seconds):
        self.tick += seconds

    def inspect(self, pid):
        if self.observations:
            self.current = self.observations.pop(0)
        return self.current

    def launch(self, role='scheduler'):
        port = 45678 if role == 'backend' else None
        argv = ['/test/launcher','-B','-m','truth_spine_integration_service','--config',
                str(self.root/'topology.json'),'--role',role]+(['--port',str(port)] if port else [])
        launch = self.owner.prepare_launch(role,argv,executable_hashes=self.pins,
                                          port=port,final_executable='/test/framework')
        obs = identity.ProcessObservation(900001,900000,'Wed Sep 9 10:00:00 2026',
            ' '.join(launch.argv),'/test/framework','b'*64,str(self.root/'release/backend'),launch.argv)
        doc = {**dict(launch.values),'observation':identity.normalized(obs,self.root)}
        doc['content_hash']=identity.digest(doc)
        self.receipts[doc['instance_id']]=doc
        return launch,obs

    def register(self,launch,observations):
        self.observations=list(observations)
        self.child=Child(900001)
        return self.owner.register(launch.role,self.child,launch.argv,self.root/'release/backend',
            dict(launch.values)['port'],executable_hashes=self.pins,launch=launch)

    def rejected(self,launch,observations):
        with self.assertRaises(runner.RunnerFailure):self.register(launch,observations)
        result=self.owner.cleanup({})
        self.assertEqual(self.child.signals,[])
        self.assertEqual(result['result'],'RED')
        self.assertTrue(result['identity_diagnostics'])
        self.assertIn('runner-incidents.json',self.written)
        return result

    def test_all_roles_immediately_stable_require_three_plus_reverification(self):
        for role in runner.ROLES:
            launch,obs=self.launch(role)
            fp=self.register(launch,[obs]*4)
            self.assertEqual(fp.instance_id,dict(launch.values)['instance_id'])
            self.assertGreaterEqual(self.tick,.1)
            self.assertTrue(self.owner.stop(role))

    def test_exact_observed_launcher_transition_preserves_pid_start_and_parent(self):
        launch,final=self.launch()
        initial=replace(final,executable='/test/launcher',executable_hash='a'*64)
        fp=self.register(launch,[initial,final,final,final,final])
        self.assertEqual(fp.observed,final)
        sequence=self.owner.observation_sequences
        self.assertEqual(len({x['observation']['pid'] for x in sequence}),1)
        self.assertEqual(len({x['observation']['start_time'] for x in sequence}),1)
        self.assertNotEqual(sequence[0]['observation']['executable'],sequence[1]['observation']['executable'])
        self.assertTrue(self.owner.stop('scheduler'))
        self.assertEqual(self.child.signals,['terminate'])

    def test_only_launcher_never_accepted_as_final(self):
        launch,obs=self.launch()
        result=self.rejected(launch,[replace(obs,executable='/test/launcher',executable_hash='a'*64)])
        self.assertTrue(any(x['classification']=='STABILIZATION_TIMEOUT' for x in result['identity_diagnostics']))

    def test_oscillation_rejected(self):
        launch,obs=self.launch()
        self.rejected(launch,[obs,replace(obs,executable='/test/launcher',executable_hash='a'*64)])

    def test_process_exit_during_stabilization(self):
        launch,obs=self.launch();self.rejected(launch,[obs,None])

    def test_different_script_role_root_port_instance_and_arg_boundaries(self):
        for field,value in [('-m','wrong_module'),('--role','publisher'),('--config','/unrelated/topology.json'),
                            ('--port','45679'),('--instance-id','shadow-child-'+'9'*32)]:
            with self.subTest(field=field):
                launch,obs=self.launch('backend');argv=list(obs.argv);argv[argv.index(field)+1]=value
                self.rejected(launch,[replace(obs,argv=tuple(argv),command=' '.join(argv))])
                self.owner.active.clear()  # Fake child only; no real process exists.
        launch,obs=self.launch();argv=list(obs.argv);argv[-1]='two words'
        bad=replace(obs,argv=tuple(argv),command=' '.join(argv))
        self.rejected(launch,[bad])

    def test_command_field_disagreement_rejected(self):
        launch,obs=self.launch();result=self.rejected(launch,[replace(obs,command='/private/secret other command')])
        self.assertNotIn('/private/secret',json.dumps(self.written))
        self.assertTrue(any(row['field']=='command' for row in result['identity_diagnostics']))
        self.assertTrue(result['launch_observations'][0]['normalization_failed'])

    def test_invalid_start_time_preserves_sanitized_observation_and_exact_field(self):
        launch,obs=self.launch();result=self.rejected(launch,[replace(obs,start_time='invalid time')])
        self.assertTrue(any(row['field']=='start_time' for row in result['identity_diagnostics']))
        self.assertTrue(result['launch_observations'][0]['normalization_failed'])

    def test_pid_reuse_rejected(self):
        launch,obs=self.launch();self.rejected(launch,[replace(obs,pid=900009)])

    def test_start_time_changes_between_samples_rejected(self):
        launch,obs=self.launch();self.rejected(launch,[obs,replace(obs,start_time='Wed Sep 9 10:00:01 2026')])

    def test_ppid_change_even_during_launcher_transition_rejected(self):
        launch,obs=self.launch();self.rejected(launch,[replace(obs,parent_pid=1)])

    def test_arbitrary_executable_or_hash_rejected(self):
        for changes in [{'executable':'/other/python'},{'executable_hash':'c'*64}]:
            launch,obs=self.launch();self.rejected(launch,[replace(obs,**changes)]);self.owner.active.clear()

    def test_missing_receipt_timeout(self):
        launch,obs=self.launch();self.receipts.clear();self.rejected(launch,[obs])

    def test_malformed_receipt(self):
        launch,obs=self.launch();self.receipts[dict(launch.values)['instance_id']]=[]
        self.rejected(launch,[obs])

    def test_forged_receipt_or_wrong_instance_rejected(self):
        for field,value in [('instance_id','shadow-child-'+'9'*32),('runner_identity','shadow-runner-'+'8'*32),
                            ('content_hash','0'*64),('topology_hash','1'*64),('authority_hash','2'*64),('port',45678)]:
            launch,obs=self.launch();doc=self.receipts[dict(launch.values)['instance_id']]
            doc[field]=value
            if field!='content_hash':doc['content_hash']=identity.digest({k:v for k,v in doc.items() if k!='content_hash'})
            self.rejected(launch,[obs]);self.owner.active.clear()

    def test_receipt_os_disagreement_fields_recorded(self):
        launch,obs=self.launch();doc=self.receipts[dict(launch.values)['instance_id']]
        doc['observation']['pid']=900007
        result=self.rejected(launch,[obs])
        diff=next(x for x in result['identity_diagnostics'] if x['field']=='pid')
        self.assertEqual(diff['expected'],900001);self.assertEqual(diff['observed'],900007)
        self.assertEqual(diff['source'],'STARTUP_RECEIPT')
        self.assertIn('observed_at',diff);self.assertIn('normalization',diff)

    def test_stale_receipt_from_prior_child_rejected(self):
        first,obs=self.launch();old=self.receipts[dict(first.values)['instance_id']]
        replacement,obs=self.launch();self.receipts[dict(replacement.values)['instance_id']]=old
        self.rejected(replacement,[obs])

    def test_change_after_stabilization_never_signaled(self):
        launch,obs=self.launch();self.register(launch,[obs]*4)
        self.current=replace(obs,start_time='Wed Sep 9 10:00:01 2026')
        self.assertFalse(self.owner.stop('scheduler'));self.assertEqual(self.child.signals,[])
        self.assertTrue(any(x['field']=='start_time' for x in self.owner.diagnostics))

    def test_receipt_mutation_before_shutdown_never_signaled(self):
        launch,obs=self.launch();self.register(launch,[obs]*4)
        self.receipts[dict(launch.values)['instance_id']]['content_hash']='0'*64
        self.assertFalse(self.owner.stop('scheduler'));self.assertEqual(self.child.signals,[])

    def test_configuration_mutation_before_shutdown_never_signaled(self):
        launch,obs=self.launch();self.register(launch,[obs]*4)
        (self.root/'authority.json').write_text('{"changed":true}')
        self.assertFalse(self.owner.stop('scheduler'));self.assertEqual(self.child.signals,[])

    def test_diagnostics_never_include_private_command_values(self):
        self.owner.diagnostic('scheduler','command','/Users/private/expected','secret command value','PROCESS_IDENTITY_MISMATCH')
        row=self.owner.diagnostics[0]
        self.assertIn('sanitized_sha256',row['observed'])
        self.assertNotIn('/Users/',json.dumps(row));self.assertNotIn('secret command',json.dumps(row))

    def test_bounds_required(self):
        for value in [0,11,-1]:
            with self.assertRaises(ValueError):runner.OwnedChildren(self.root,stabilization_seconds=value)

    def test_persistence_failure_during_acquisition_still_cleans_other_verified_owner(self):
        launch,obs=self.launch();self.register(launch,[obs]*4)
        old=self.current
        other,obs=self.launch('publisher');bad=replace(obs,parent_pid=1)
        self.owner.writer=Mock(side_effect=OSError('private failure'))
        with self.assertRaises(runner.RunnerFailure):self.register(other,[bad])
        self.current=old
        result=self.owner.cleanup({})
        self.assertEqual(result['result'],'RED')
        self.assertTrue(any(x['role']=='scheduler' for x in result['completed_processes']))
        self.assertTrue(any(x['role']=='publisher' for x in result['unresolved_children']))

    def test_unknown_single_argument_is_hashed_not_logged(self):
        launch,obs=self.launch();argv=list(obs.argv);argv[3]='private-token-without-spaces'
        result=self.rejected(launch,[replace(obs,argv=tuple(argv),command=' '.join(argv))])
        self.assertNotIn('private-token-without-spaces',json.dumps(result))

    def test_launch_observation_preserves_prespawn_instance_and_initial_os(self):
        launch,obs=self.launch();self.register(launch,[obs]*4)
        record=self.owner.launch_records[0]
        self.assertEqual(record['pid'],900001)
        self.assertEqual(record['expected_parent_pid'],900000)
        self.assertIsNotNone(record['initial_observation'])
        self.assertIn(dict(launch.values)['instance_id'],json.dumps(record))
        self.assertEqual(self.written['runner-incidents.json']['launch_records'],[record])

    def test_argv_whitespace_boundaries_are_not_collapsed(self):
        launch,obs=self.launch();argv=list(obs.argv)
        # A one-argument value containing whitespace is never equivalent to
        # two arguments, even if a human-rendered command would look alike.
        argv[3]='truth_spine_integration_service --role scheduler'
        self.rejected(launch,[replace(obs,argv=tuple(argv),command=' '.join(argv))])

    def test_shutdown_force_reverification_requires_unchanged_receipt(self):
        launch,obs=self.launch();self.register(launch,[obs]*4)
        def timed_out():
            self.receipts[dict(launch.values)['instance_id']]['authority_hash']='f'*64
            raise subprocess.TimeoutExpired('fake',1)
        self.child.waits=[timed_out]
        self.assertFalse(self.owner.stop('scheduler'))
        self.assertEqual(self.child.signals,['terminate'])

    def test_startup_receipt_reader_exception_records_field(self):
        launch,obs=self.launch();self.owner.receipt_reader=Mock(side_effect=PermissionError('private'))
        result=self.rejected(launch,[obs])
        self.assertTrue(any(x['field']=='startup_receipt' for x in result['identity_diagnostics']))

    def test_symlink_executable_representation_normalizes_only_pinned_target(self):
        launch,obs=self.launch();alias=self.root/'python-alias';alias.symlink_to('/test/framework')
        altered=replace(obs,executable=str(alias))
        fp=self.register(launch,[altered]*4)
        self.assertEqual(identity.normalized(fp.observed,self.root),identity.normalized(obs,self.root))

    def test_normalization_utc_whitespace_and_symlink_paths(self):
        launch,obs=self.launch()
        alias=self.root/'alias';alias.symlink_to(self.root/'release/backend')
        changed=replace(obs,cwd=str(alias),start_time='Wed  Sep  9 10:00:00 2026')
        self.assertEqual(identity.normalized(obs,self.root),identity.normalized(changed,self.root))
        with self.assertRaises(ValueError):identity.utc_stamp('2026-09-09T10:00:00-07:00')

    def test_no_stabilization_authority_from_instance_id(self):
        import truth_spine_integration_service as service
        import inspect
        source=inspect.getsource(service.main)
        self.assertLess(source.index('topology(a.config)'),source.index('write_startup(Path'))
        self.assertLess(source.index('deny_external_io()'),source.index('serve(a.config'))
        launch,_=self.launch();self.assertNotIn('capabilities',dict(launch.values))


class ReceiptTests(unittest.TestCase):
    def test_kernel_argv_preserves_boundaries_and_does_not_return_environment(self):
        import ctypes
        argv=[b'/test/python',b'-c',b'two words']
        raw=(len(argv)).to_bytes(4,sys.byteorder)+b'/test/python\0\0'+b'\0'.join(argv)+b'\0SECRET_ENV=not-returned\0'
        def sysctl(mib,count,buffer,size,*rest):
            ctypes.memmove(buffer,raw,len(raw));size._obj.value=len(raw);return 0
        library=Mock();library.sysctl.side_effect=sysctl
        with patch.object(identity.ctypes,'CDLL',return_value=library):
            actual=identity.kernel_argv(900001)
        self.assertEqual(actual,('/test/python','-c','two words'))
        self.assertNotIn('SECRET_ENV',repr(actual))

    def test_reader_rejects_modes_symlink_hash_and_size(self):
        with tempfile.TemporaryDirectory(prefix='iios-receipt-unit-') as temp:
            root=Path(temp).resolve();instance='shadow-child-'+'a'*32;p=identity.receipt_path(root,instance)
            p.write_text('{}');p.chmod(0o600)
            with self.assertRaises(identity.IdentityFailure):identity.read_receipt(root,instance)
            value={'example':True};value['content_hash']=identity.digest(value);p.write_bytes(identity.encoded(value));p.chmod(0o644)
            with self.assertRaises(identity.IdentityFailure):identity.read_receipt(root,instance)
            p.chmod(0o600);self.assertEqual(identity.read_receipt(root,instance),value)
            p.unlink();p.symlink_to(root/'missing')
            with self.assertRaises(identity.IdentityFailure):identity.read_receipt(root,instance)

    def test_startup_receipt_atomic_owner_only_no_replacement(self):
        with tempfile.TemporaryDirectory(prefix='iios-startup-unit-') as temp:
            root=Path(temp).resolve();(root/'topology.json').write_text('{}');(root/'authority.json').write_text('{}')
            obs=identity.ProcessObservation(os.getpid(),os.getppid(),'2026-09-10T00:00:00+00:00',
                '/test/python -B','/test/python','a'*64,str(root/'release/backend'),('/test/python','-B'))
            args=(root,'shadow-child-'+'a'*32,'shadow-runner-'+'b'*32,'scheduler',None,datetime.now(timezone.utc).isoformat())
            with patch.object(identity,'inspect_macos',return_value=obs):
                record=identity.write_startup(*args)
                p=identity.receipt_path(root,args[1]);before=p.read_bytes()
                self.assertEqual(p.stat().st_mode&0o777,0o600)
                self.assertEqual(identity.read_receipt(root,args[1]),record)
                with self.assertRaises(identity.IdentityFailure):identity.write_startup(*args)
                self.assertEqual(p.read_bytes(),before)
            self.assertFalse(list(root.glob('*.staging')))


@unittest.skipUnless(sys.platform=='darwin' and os.environ.get('IIOS_EPHEMERAL_IDENTITY_TEST')=='1',
                     'opt-in own-child macOS process inspection only; no services or network')
class EphemeralMacOSTests(unittest.TestCase):
    def test_actual_launcher_stabilizes_with_actual_self_receipt(self):
        with tempfile.TemporaryDirectory(prefix='iios-identity-ephemeral-') as temp:
            root=Path(temp).resolve();backend=root/'release/backend';backend.mkdir(parents=True)
            (root/'topology.json').write_text('{}');(root/'authority.json').write_text('{}')
            # Only the startup boundary is exercised. No service or historical
            # replay is started; the owned child exits naturally after 2 seconds.
            (backend/'truth_spine_integration_service.py').write_text('''
import argparse,time
from pathlib import Path
from truth_spine_process_identity import write_startup
p=argparse.ArgumentParser()
for x in ('config','role','instance-id','runner-id','created-at'):p.add_argument('--'+x,required=True)
a=p.parse_args()
write_startup(Path(a.config).parent,a.instance_id,a.runner_id,a.role,None,a.created_at)
time.sleep(2)
''')
            python=str(Path(sys.executable).resolve())
            framework=Path(sys.base_prefix)/'Resources/Python.app/Contents/MacOS/Python'
            pins={python:identity.file_hash(python),str(framework):identity.file_hash(framework)}
            owner=runner.OwnedChildren(root,port_clear=lambda:True)
            base=[python,'-B','-m','truth_spine_integration_service','--config',str(root/'topology.json'),'--role','scheduler']
            launch=owner.prepare_launch('scheduler',base,executable_hashes=pins,final_executable=str(framework))
            child=subprocess.Popen(launch.argv,cwd=backend,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1',
                'PYTHONPATH':str(Path(__file__).parent)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                fp=owner.register('scheduler',child,launch.argv,backend,executable_hashes=pins,launch=launch)
                self.assertEqual(fp.observed.executable,str(framework))
                self.assertGreaterEqual(len(owner.observation_sequences),4)
            finally:
                child.wait(timeout=15)  # No signal even if acquisition failed.
                owner.cleanup({})
            self.assertEqual(child.returncode,0)
            self.assertEqual(owner.finished['result'],'GREEN')


if __name__=='__main__':unittest.main()
