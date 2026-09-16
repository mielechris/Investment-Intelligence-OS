"""Offline launch binding regressions; all process and socket effects are mocked."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import os
import subprocess
import unittest
from unittest.mock import Mock, patch

import alpha_observation_launch as launch
import alpha_observation_child as child
from provider_gateway_contract import content_hash, locked_authority
from truth_spine_process_identity import ProcessObservation


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.roots={k:'/disposable/'+k for k in ('runtime','release','control','output')}
        def row(name):return dict(path=name,size=1,mode=0o400,sha256='a'*64)
        self.spec=dict(schema='iios-observation-launch-v1',scope=launch.SCOPE,source='b'*40,
            topology_parent='c'*64,roots=self.roots,inventories={
                'runtime':[row('bin/python3.14')],'release':[row(launch.CHILD)],
                'control':[row(n) for n in ('profile.sb','loopback.crt','loopback.pem')]},
            interpreter=self.roots['runtime']+'/bin/python3.14',interpreter_hash='a'*64,
            sandbox_hash='d'*64,host='127.0.0.1',port=38493,peer_hash='e'*64,parent_pid=99,
            start_ns=1_000_000_000,startup_ns=121_000_000_000,stop_ns=661_000_000_000,
            final_ns=901_000_000_000,authority=locked_authority())
        self.now=2_000_000_000
        with patch.object(launch.time,'monotonic_ns',return_value=self.now),patch.object(launch.os,'getpid',return_value=99):
            self.owner=launch.LaunchOwner(self.spec,content_hash(self.spec),roots=self.roots,
                source='b'*40,topology_parent='c'*64)
        self.owner.fd=20; self.owner.descriptor_hash='f'*64; self.owner.descriptor_size=1000

    def validate(self,spec=None,**changes):
        s=spec or self.spec
        return launch.validate_spec(s,content_hash(s),roots=self.roots,source='b'*40,
            topology_parent='c'*64,now_ns=self.now,**changes)

    def process(self,role):
        p=Mock(pid=100+launch.ROLES.index(role),returncode=0)
        p.poll.return_value=None
        p.stdout.fileno.return_value=21;p.stderr.fileno.return_value=22
        self.owner.children[role]={'process':p,'counts':{'stdout':0,'stderr':0}}
        argv=launch.command(self.spec,role,self.owner.descriptor_hash,self.owner.descriptor_size)
        obs=ProcessObservation(p.pid,99,'2026-09-16T00:00:00+00:00',' '.join(argv),self.spec['interpreter'],
            'a'*64,self.roots['release'],tuple(argv))
        return p,obs

    def test_valid_component_never_production(self):
        self.assertEqual(self.validate()['scope'],launch.SCOPE)
        from alpha_session_runner import validate_package
        with self.assertRaises(ValueError):validate_package(self.spec,content_hash(self.spec))

    def test_scope_source_topology_and_authority_mutations(self):
        for key,value in [('scope','LIVE_QUALIFICATION'),('source','a'*40),('topology_parent','a'*64),
            ('authority',{**locked_authority(),'live_execution':True})]:
            s=deepcopy(self.spec);s[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(s)

    def test_independent_hash_required(self):
        with self.assertRaises(ValueError):
            launch.validate_spec(self.spec,'0'*64,roots=self.roots,
                source='b'*40,topology_parent='c'*64,now_ns=self.now)

    def test_lexical_rejection_before_filesystem(self):
        denied=['/disposable/output/../Keychains','/disposable//output','relative','/disposable/~owner',
            '/disposable/ledger/x','/disposable/Keychains/x','/disposable/a\x00b']
        for value in denied:
            with (self.subTest(value=value),patch.object(launch.os,'open',side_effect=AssertionError('IO')),
                self.assertRaises(ValueError)):
                launch.lexical(value)

    def test_root_approval_and_overlap(self):
        s=deepcopy(self.spec);s['roots']['output']='/elsewhere'
        with self.assertRaises(ValueError):self.validate(s)
        s=deepcopy(self.spec);s['roots']['output']=s['roots']['runtime']+'/output'
        with self.assertRaises(ValueError):
            launch.validate_spec(s,content_hash(s),roots=s['roots'],
                source='b'*40,topology_parent='c'*64,now_ns=self.now)

    def test_no_dns_public_address_proxy_or_arbitrary_environment(self):
        for host in ('localhost','alpha.example','192.0.2.1','::1'):
            s=deepcopy(self.spec);s['host']=host
            with self.assertRaises(ValueError):self.validate(s)
        for key in ('env','proxy','credential_selector'):
            s=deepcopy(self.spec);s[key]={}
            with self.assertRaises(ValueError):self.validate(s)
        self.assertEqual(launch.ENV,{'LANG':'C','LC_ALL':'C','TZ':'UTC'})

    def test_canonical_deadlines_and_reserves(self):
        for key,value in [('start_ns',float('nan')),('startup_ns',self.now),('final_ns',2**63),
            ('stop_ns',900_000_000_000),('final_ns',902_000_000_000),('startup_ns',122_000_000_000)]:
            s=deepcopy(self.spec);s[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(s)

    def test_clock_rollback_and_expiry(self):
        for now in (0,self.spec['startup_ns']):
            with patch.object(launch.time,'monotonic_ns',return_value=now),self.assertRaises(ValueError):
                self.owner.clock(self.spec['startup_ns'])

    def test_fixed_child_command_cannot_select_worker(self):
        argv=launch.command(self.spec,'backend','f'*64,1000)
        self.assertEqual(argv[:4],[self.spec['interpreter'],'-I','-B',self.roots['release']+'/'+launch.CHILD])
        with self.assertRaises(ValueError):launch.command(self.spec,'worker','f'*64,1000)

    def test_exact_three_observations_one_full_admission(self):
        p,obs=self.process('scheduler');calls=[]
        with (patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs') as admission,
            patch.object(self.owner,'sample',side_effect=lambda role:(calls.append(role) or obs)),
            patch.object(self.owner,'evidence',return_value='9'*64)):
            self.owner.register('scheduler')
        self.assertEqual(calls,['scheduler']*3);admission.assert_called_once()
        self.assertEqual(self.owner.owners['scheduler']['pid'],p.pid)

    def test_each_identity_field_rejected(self):
        _,obs=self.process('scheduler')
        mutations=dict(pid=999,parent_pid=999,start_time='bad',command='wrong',executable='/other',
            executable_hash='f'*64,cwd='/other',argv=('other',))
        for key,value in mutations.items():
            with (self.subTest(key=key),patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs'),
                patch.object(self.owner,'sample',return_value=replace(obs,**{key:value})),self.assertRaises(ValueError)):
                self.owner.register('scheduler')

    def test_pid_reuse_and_unstable_samples(self):
        _,obs=self.process('scheduler')
        with (patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs'),
            patch.object(self.owner,'sample',side_effect=[obs,replace(obs,parent_pid=33),obs]),self.assertRaises(ValueError)):
            self.owner.register('scheduler')
        self.owner.owners['backend']=launch.observed(obs)
        with (patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs'),
            patch.object(self.owner,'sample',return_value=obs),self.assertRaises(ValueError)):
            self.owner.register('scheduler')

    def test_publication_failure_preserves_owner(self):
        _,obs=self.process('scheduler')
        with (patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs'),
            patch.object(self.owner,'sample',return_value=obs),patch.object(self.owner,'evidence',side_effect=OSError),
            self.assertRaises(OSError)):
            self.owner.register('scheduler')
        self.assertIn('scheduler',self.owner.owners)

    def test_exited_child_does_not_establish_ownership(self):
        p,_=self.process('scheduler');p.poll.return_value=1
        with patch.object(self.owner,'drain'),patch.object(launch,'inspect_macos') as inspect,self.assertRaises(ValueError):
            self.owner.sample('scheduler')
        inspect.assert_not_called()

    def test_bounded_raw_output_discarded(self):
        self.process('scheduler')
        with patch.object(launch.os,'read',return_value=b'not a safe diagnostic'),self.assertRaisesRegex(ValueError,'UNEXPECTED_OUTPUT'):
            self.owner.drain('scheduler')
        self.owner.children['scheduler']['counts']['stdout']=4096
        with patch.object(launch.os,'read',return_value=b'x'),self.assertRaisesRegex(ValueError,'OVERFLOW'):
            self.owner.drain('scheduler')
        self.assertNotIn('not a safe diagnostic',str(self.owner.children['scheduler']['counts']))

    def test_nonblocking_empty_stream(self):
        self.process('scheduler')
        with patch.object(launch.os,'read',side_effect=BlockingIOError):self.owner.drain('scheduler')
        self.assertEqual(self.owner.children['scheduler']['counts'],{'stdout':0,'stderr':0})

    def test_duplicate_start_blocked(self):
        self.process('scheduler')
        with self.assertRaises(ValueError):
            self.owner.startup()

    def test_startup_uses_pipes_and_closes_stdin_before_inspection(self):
        p,obs=self.process('scheduler');self.owner.children={};seen=[]
        ready={'scope':launch.SCOPE,'launch_parent':self.owner.parent,'role':'scheduler','pid':p.pid,
            'parent_pid':99,'startup_ns':self.spec['startup_ns'],'authority':locked_authority()}
        def register(role):
            self.assertTrue(p.stdin.close.called);seen.append(role);raise ValueError('STOP_TEST')
        with (patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs'),patch.object(launch.subprocess,'Popen',return_value=p) as spawn,
            patch.object(launch.os,'set_blocking'),patch.object(self.owner,'drain'),patch.object(launch,'read_record',return_value=ready),
            patch.object(self.owner,'register',side_effect=register),self.assertRaises(ValueError)):
            self.owner.startup()
        self.assertEqual(seen,['scheduler']);kwargs=spawn.call_args.kwargs
        self.assertEqual([kwargs[x] for x in ('stdin','stdout','stderr')],[subprocess.PIPE]*3)
        self.assertEqual(kwargs['env'],launch.ENV)
        self.assertEqual(spawn.call_args.args[0][:3],['/usr/bin/sandbox-exec','-f',self.roots['control']+'/profile.sb'])

    def test_forged_startup_cannot_ack(self):
        p,_=self.process('scheduler');self.owner.children={}
        with (patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs'),patch.object(launch.subprocess,'Popen',return_value=p),
            patch.object(launch.os,'set_blocking'),patch.object(self.owner,'drain'),patch.object(launch,'read_record',return_value={}),
            patch.object(self.owner,'evidence') as evidence,self.assertRaises(ValueError)):
            self.owner.startup()
        evidence.assert_not_called()

    def cleanup(self,fail_role=None):
        for role in launch.ROLES:
            _,obs=self.process(role);self.owner.owners[role]=launch.observed(obs)
        calls=[]
        def reverify(role):
            calls.append(role)
            if role==fail_role:raise ValueError('IDENTITY')
        def read(fd,name):
            role=name.split('-')[0]
            return dict(scope=launch.SCOPE,launch_parent=self.owner.parent,role=role,
                pid=self.owner.children[role]['process'].pid,stop_parent='f'*64,authority=locked_authority())
        probe=Mock();probe.__enter__=Mock(return_value=probe);probe.__exit__=Mock(return_value=False)
        import errno
        probe.connect_ex.return_value=errno.ECONNREFUSED
        with (patch.object(self.owner,'clock'),patch.object(self.owner,'reverify',side_effect=reverify),
            patch.object(self.owner,'evidence',return_value='f'*64),patch.object(self.owner,'drain'),
            patch.object(launch,'read_record',side_effect=read),patch.object(launch,'listener_pids',return_value=[]),
            patch.object(launch.socket,'socket',return_value=probe),patch.object(launch.time,'sleep')):
            result=self.owner.cleanup()
        for value in self.owner.children.values():
            value['process'].terminate.assert_not_called();value['process'].kill.assert_not_called()
        return calls,result

    def test_cleanup_each_role_independent_identity_failure(self):
        for role in launch.ROLES:
            self.setUp();calls,result=self.cleanup(role)
            self.assertEqual(calls,list(reversed(launch.ROLES)));self.assertFalse(result['verified'])
            self.assertEqual(result['roles'][role],'UNVERIFIED')
            self.assertEqual(result['port_samples'],[True]*3)

    def test_cleanup_success_needs_every_role_and_exit(self):
        calls,result=self.cleanup();self.assertTrue(result['verified'])
        self.assertEqual(len(calls),3)

    def test_unregistered_child_never_signalled(self):
        p,_=self.process('scheduler')
        with self.assertRaises(ValueError):self.owner.reverify('scheduler')
        p.terminate.assert_not_called();p.kill.assert_not_called()

    def test_listener_parser_rejects_unknown_or_multiple(self):
        for code,out,err in [(0,b'path-secret\n',b''),(1,b'p1\n',b''),(0,b'',b''),(0,b'p1\n',b'error')]:
            r=Mock(returncode=code,stdout=out,stderr=err)
            with patch.object(launch.subprocess,'run',return_value=r),self.assertRaises(ValueError):launch.listener_pids(38493)
        with patch.object(launch.subprocess,'run',return_value=Mock(returncode=0,stdout=b'p123\n',stderr=b'')):
            self.assertEqual(launch.listener_pids(38493),[123])

    def test_child_deadline_missing_ack(self):
        with patch.object(child,'read_record',side_effect=FileNotFoundError),self.assertRaises(ValueError):
            child.wait_record(20,'ack',10,clock=iter([1,2,10]).__next__,pause=lambda _:None)

    def test_child_role_and_environment_fail_before_io(self):
        with (patch.object(child.os,'environ',{'API_KEY':'synthetic'}),patch.object(child,'directory') as opened,
            self.assertRaises(ValueError)):
            child.run_child(self.spec,'backend')
        opened.assert_not_called()

    def test_child_main_suppresses_exception_text(self):
        with (patch.object(child,'load',side_effect=ValueError('private arbitrary detail')),
            patch('sys.stdout',new_callable=io.StringIO) as output):
            self.assertEqual(child.main(['--descriptor','/unused','--sha256','a'*64,'--bytes','1','--role','backend']),1)
        self.assertEqual(output.getvalue(),'')

    def full_startup(self,*,bad_listener=False,bad_tls=False,expired=False):
        processes={};observations={}
        for role in launch.ROLES:
            processes[role],observations[role]=self.process(role)
        self.owner.children={};active=[];events=[]
        def spawn(*args,**kwargs):
            role=args[0][-1];active.append(role);events.append(('spawn',role));return processes[role]
        def ready(fd,name):
            role=name.split('-')[0]
            return dict(scope=launch.SCOPE,launch_parent=self.owner.parent,role=role,pid=processes[role].pid,
                parent_pid=99,startup_ns=self.spec['startup_ns'],authority=locked_authority())
        def sample(role):events.append(('inspect',role));return observations[role]
        def listeners(port):
            events.append(('listener',active[-1]))
            return [999] if bad_listener else ([processes['backend'].pid] if active[-1]=='backend' else [])
        def evidence(stage,payload):events.append(('publish',stage));return '9'*64
        peer=b'public dummy certificate';self.spec['peer_hash']=hashlib.sha256(peer).hexdigest()
        self.owner.spec['peer_hash']=self.spec['peer_hash']
        tls=Mock();tls.__enter__=Mock(return_value=tls);tls.__exit__=Mock(return_value=False)
        tls.getpeercert.return_value=b'wrong' if bad_tls else peer
        tls.recv.side_effect=[b'OBSERVATION_',b'COMPONENT_ONLY\n']
        raw=Mock();raw.__enter__=Mock(return_value=raw);raw.__exit__=Mock(return_value=False)
        context=Mock();context.wrap_socket.return_value=tls
        def clock(deadline):
            if expired:raise ValueError('LAUNCH_DEADLINE')
            return self.now
        with (patch.object(self.owner,'clock',side_effect=clock),patch.object(launch,'verify_inputs'),
            patch.object(launch.subprocess,'Popen',side_effect=spawn),patch.object(launch.os,'set_blocking'),
            patch.object(self.owner,'drain'),patch.object(self.owner,'sample',side_effect=sample),
            patch.object(launch,'read_record',side_effect=ready),patch.object(launch,'listener_pids',side_effect=listeners),
            patch.object(self.owner,'evidence',side_effect=evidence),patch.object(launch.ssl,'create_default_context',return_value=context),
            patch.object(launch.socket,'socket',return_value=raw),patch.object(launch.time,'monotonic_ns',return_value=self.now)):
            try:self.owner.startup();failure=None
            except ValueError as exc:failure=str(exc)
        return events,failure

    def test_full_mock_startup_order_and_tls(self):
        events,failure=self.full_startup();self.assertIsNone(failure);self.assertTrue(self.owner.tls)
        for role in launch.ROLES:
            ack=events.index(('publish',role+'-ack'))
            self.assertLess(events.index(('publish',role+'-ownership')),ack)
            self.assertLess(events.index(('listener',role)),ack)
            self.assertEqual(events.count(('inspect',role)),4)
        self.assertEqual(events[-1],('publish','tls'))

    def test_listener_mismatch_prevents_ack_and_tls(self):
        events,failure=self.full_startup(bad_listener=True)
        self.assertEqual(failure,'LAUNCH_LISTENER_OWNER');self.assertFalse(self.owner.tls)
        self.assertFalse(any(e[1].endswith('-ack') for e in events))

    def test_tls_mismatch_cannot_complete(self):
        events,failure=self.full_startup(bad_tls=True)
        self.assertEqual(failure,'LAUNCH_TLS_PIN');self.assertFalse(self.owner.tls)
        self.assertNotIn(('publish','tls'),events)

    def test_expired_budget_blocks_creation(self):
        events,failure=self.full_startup(expired=True)
        self.assertEqual(failure,'LAUNCH_DEADLINE');self.assertEqual(events,[])

    def test_cleanup_failure_preserves_primary_and_final_receipt(self):
        self.owner.fd=None;captured=[]
        def prepared():self.owner.fd=20
        with (patch.object(self.owner,'prepare',side_effect=prepared),
            patch.object(self.owner,'startup',side_effect=ValueError('unrestricted detail')),
            patch.object(self.owner,'cleanup',return_value={'verified':False,'roles':{'backend':'UNVERIFIED'}}),
            patch.object(self.owner,'evidence',side_effect=lambda stage,payload:captured.append((stage,payload))),
            patch.object(launch.os,'close')):
            result=self.owner.run()
        self.assertEqual(result['primary_failure'],'STARTUP_FAILED');self.assertFalse(result['cleanup']['verified'])
        self.assertNotIn('unrestricted detail',str(captured))
        self.assertFalse(captured[0][1]['component_complete'])

    def test_immutable_runtime_and_profile_checked_before_spawn(self):
        self.owner.children={}
        with (patch.object(self.owner,'clock'),patch.object(launch,'verify_inputs',side_effect=ValueError('CHANGED')),
            patch.object(launch.subprocess,'Popen') as spawn,self.assertRaises(ValueError)):
            self.owner.startup()
        spawn.assert_not_called()

    def test_every_cleanup_wait_has_independent_bound(self):
        self.cleanup()
        for row in self.owner.children.values():self.assertLessEqual(row['process'].wait.call_args.kwargs['timeout'],30)

    def child_case(self,*,ack_scope=None,stop_scope=None,listener=False):
        startup=dict(scope=launch.SCOPE,launch_parent=content_hash(self.spec),role='scheduler',pid=123,
            parent_pid=99,startup_ns=self.spec['startup_ns'],authority=locked_authority())
        ack=dict(schema='iios-observation-launch-receipt-v1',scope=ack_scope or launch.SCOPE,
            launch_parent=content_hash(self.spec),stage='scheduler-ack',authority=locked_authority(),
            production_qualified=False,payload=dict(startup_parent=content_hash(startup),listener_verified=not listener))
        stop=dict(schema='iios-observation-launch-receipt-v1',scope=stop_scope or launch.SCOPE,
            launch_parent=content_hash(self.spec),stage='scheduler-stop',authority=locked_authority(),
            production_qualified=False,payload=dict(owner_parent='f'*64))
        records=[]
        with (patch.object(child.os,'environ',dict(launch.ENV)),patch.object(child,'directory',return_value=20),
            patch.object(child.os,'getpid',return_value=123),patch.object(child.os,'getppid',return_value=99),
            patch.object(child.os,'close'),patch.object(child,'verify_destination'),
            patch.object(child,'publish',side_effect=lambda fd,name,value:records.append((name,value))),
            patch.object(child,'wait_record',return_value=ack),patch.object(child,'read_record',return_value=stop),
            patch.object(child.time,'monotonic_ns',return_value=self.now),patch.object(child.socket,'socket') as sockets):
            try:child.run_child(self.spec,'scheduler');failure=None
            except ValueError as exc:failure=str(exc)
        sockets.assert_not_called()
        return records,failure

    def test_child_receipt_handshake_and_cooperative_exit(self):
        records,failure=self.child_case();self.assertIsNone(failure)
        self.assertEqual([name for name,_ in records],['scheduler-startup.json','scheduler-exit.json'])
        self.assertEqual(records[1][1]['scope'],launch.SCOPE)

    def test_child_rejects_cross_scope_ack_and_stop(self):
        for scope in ('LIVE_QUALIFICATION','SYNTHETIC_NATIVE_QUALIFIED'):
            for field in ('ack_scope','stop_scope'):
                records,failure=self.child_case(**{field:scope})
                self.assertIsNotNone(failure);self.assertEqual(len(records),1)

    def test_child_ack_requires_listener_proof(self):
        records,failure=self.child_case(listener=True)
        self.assertEqual(failure,'CHILD_ACK');self.assertEqual(len(records),1)
