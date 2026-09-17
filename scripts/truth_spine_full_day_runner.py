"""Future owner-authorized full-day runner. NOT executed by source acceptance.

No compressed clock or environment clock override is accepted. Package creation
and owner approval are separate steps. The exact topology pin is an explicit
owner input, never derived from an edited JSON file as an authorization shortcut.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

from truth_spine_integration_runner import OwnedChildren, port_is_clear


def run(root, topology_pin, *, owner_session):
    # Package-local imports only. Never fall back to the authoritative checkout.
    if (root != root.resolve() or root.parent != Path('/private/tmp') or not
            (root.name.startswith('iios-truth-spine-full-day-') or root.name == 'iios-northstar-installed-shadow-sb37')):
        raise ValueError('NEW_OWNER_AUTHORIZED_ISOLATED_ROOT_REQUIRED')
    if Path(__file__).resolve().parent != root/'release/backend' or Path(sys.executable) != root/'runtime/bin/python':
        raise ValueError('INSTALLED_PACKAGE_RUNNER_REQUIRED')
    raw = (root/'topology.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != topology_pin:
        raise ValueError('OWNER_TOPOLOGY_PIN_MISMATCH')
    backend = root/'release/backend'
    sys.path.insert(0, str(backend))
    from truth_spine_full_day_service import load_config
    from truth_spine_generations import GenerationStore, owner_path, immutable_file
    from truth_spine_integration import atomic
    from truth_spine_integration_service import Lease
    from truth_spine_contract import seal, canonical
    from truth_spine_session_package import RuntimeProbeReader, capacity_budget
    from truth_spine_session_supervisor import SessionSupervisor
    from truth_spine_sqlite_capture import launch_capture
    owner_path(root, root, directory=True)
    c, session, manifest, authority, registry = load_config(root/'topology.json')
    from truth_spine_session import HistoricalSession
    if isinstance(session, HistoricalSession) != (root.name == 'iios-northstar-installed-shadow-sb37'):
        raise ValueError('HISTORICAL_ROOT_SCOPE_MISMATCH')
    if owner_session != session.identity or not port_is_clear(c['port']):
        raise ValueError('SESSION_OR_PORT_PREFLIGHT_FAILED')
    if (root/'shutdown-receipt.json').exists():
        raise ValueError('COMPLETED_ROOT_NOT_REUSABLE')
    if shutil.disk_usage(root).free < capacity_budget(session, registry)['required_free_bytes']:
        raise ValueError('SESSION_DISK_RESERVATION_INSUFFICIENT')
    # A previous parent's surviving child is never adopted or signaled.
    barriers = []
    try:
        for role in ('runner', 'scheduler', 'publisher', 'backend'):
            barriers.append(Lease(root, role))
    except BaseException:
        for lease in reversed(barriers): lease.close()
        raise
    runner_lease = barriers[0]
    for lease in reversed(barriers[1:]): lease.close()
    children = OwnedChildren(root, port_clear=lambda: port_is_clear(c['port']),
                             service_module='truth_spine_full_day_service')
    supervisor = None
    report = {}
    try:
        runtime = json.loads((root/'runtime/runtime-manifest.json').read_bytes())
        python = root/'runtime/bin/python'
        hashes = {str(python): runtime['interpreter_sha256']}
        if runtime.get('process_executable'):
            hashes[runtime['process_executable']] = runtime['process_executable_hash']
        for name, expected in hashes.items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
                raise ValueError('INTERPRETER_IDENTITY_INVALID')
        store = GenerationStore(root, session.identity, registry, c['registry_hash'],
                                require_isolated_capture=True)
        isolated_root = root/'captures'/'isolated-attempts'
        isolated_root.mkdir(mode=0o700, exist_ok=True)
        def isolated_capture(source, *, timeout_seconds, permit):
            if source not in {Path(s['path']) for s in registry['sources'] if s['kind'] in {'operational','historical'}}:
                raise ValueError('ISOLATED_SOURCE_NOT_REGISTERED')
            if permit is not None: permit()
            output = isolated_root/('attempt-'+os.urandom(16).hex())
            receipt = launch_capture(source, output, evidence_root=root/'receipts',
                                     timeout=min(120, max(1, timeout_seconds)), probe=False)
            if permit is not None: permit()
            snapshot = output/'snapshot.db'
            if receipt.get('snapshot_sha256') is None or not snapshot.is_file():
                raise ValueError('ISOLATED_SNAPSHOT_MISSING')
            return snapshot
        def start(role):
            load_config(root/'topology.json')
            if hashlib.sha256((root/'topology.json').read_bytes()).hexdigest() != topology_pin:
                raise ValueError('TOPOLOGY_CHANGED')
            args = [str(python), '-B', '-m', 'truth_spine_full_day_service', '--config', str(root/'topology.json'), '--role', role]
            if role == 'backend': args += ['--port', str(c['port'])]
            launch = children.prepare_launch(role, args, executable_hashes=hashes,
                final_executable=runtime.get('process_executable', str(python)), port=c['port'] if role == 'backend' else None)
            owner_path(root/'logs', root, directory=True)
            log_path = root/'logs'/(role+'.log')
            if log_path.exists(): owner_path(log_path, root)
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            handle = os.fdopen(fd, 'ab'); children.logs.append(handle)
            process = subprocess.Popen(launch.argv, cwd=backend,
                env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(backend)},
                stdout=handle, stderr=handle)
            children.register(role, process, launch.argv, backend, c['port'] if role == 'backend' else None,
                              executable_hashes=hashes, launch=launch)
        reader = RuntimeProbeReader(root=root, manifest=manifest, manifest_pin=c['manifest_hash'],
                                    children=children, session=session, store=store)
        def probes(now, generation, watermark):
            try:
                evidence = reader.collect(now, generation, watermark)
            except (OSError, ValueError, KeyError, TypeError):
                evidence = {}
            atomic(root/'runtime-probes.json', seal({'probes': evidence, 'at': now.isoformat()}))
            return evidence
        supervisor = SessionSupervisor(session=session, store=store, children=children, authority=authority,
            approved_authority_hash=c['authority_hash'], release=manifest['release'], owners=c['owners'],
            topology_hash=c['content_hash'], start_child=start, probe_runtime=probes,
            capture_fn=isolated_capture)
        interrupted = False
        def stop(*_):
            nonlocal interrupted
            interrupted = True
        signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
        until = time.monotonic() + max(0, (session.shutdown_end-datetime.now(timezone.utc)).total_seconds())
        while not supervisor.closed:
            if any(p.stat().st_size > 1024*1024 for p in (root/'logs').glob('*.log')):
                supervisor.lifecycle.fail('LOG_GROWTH_LIMIT')
                supervisor.finish(datetime.now(timezone.utc))
                break
            if interrupted or time.monotonic() >= until:
                supervisor.lifecycle.fail('RUNNER_STOP_OR_MONOTONIC_DEADLINE')
                supervisor.finish(datetime.now(timezone.utc))
                break
            supervisor.cycle()
            if not supervisor.closed: time.sleep(5)
        return 0 if supervisor.lifecycle.state.get('session_result') == 'COMPLETE' else 1
    finally:
        try:
            if supervisor is not None and not supervisor.closed:
                supervisor.finish(datetime.now(timezone.utc))
            else:
                children.cleanup(report)
            immutable_file(root/'shutdown-receipt.json', canonical(seal({
                'schema': 'iios-full-day-shadow-shutdown-v1', 'session': session.identity,
                'authority_hash': c['authority_hash'], 'release_manifest_hash': c['manifest_hash'],
                'cleanup': children.finished, 'at': datetime.now(timezone.utc).isoformat(),
                'lifecycle_hash': supervisor.lifecycle.state['content_hash'] if supervisor else None})))
        finally:
            runner_lease.close()


class ObservationLifecycle:
    """Fixed observation adapter using the existing Truth Spine process owner.

    No injected process, credential or network effects are exposed by the native
    entrypoint. Offline tests substitute those boundaries with mocks.
    """
    def __init__(self, config, capability):
        from alpha_session_contract import require
        from alpha_observation_lifecycle import ObservationExecution
        require(type(capability) is ObservationExecution, 'OBSERVATION_CAPABILITY_REQUIRED')
        self._initialize(config,capability)

    @classmethod
    def for_disposable(cls,config,capability):
        from truth_spine_observation_roles import disposable
        if not disposable(capability):raise ValueError('DISPOSABLE_CAPABILITY_REQUIRED')
        value=object.__new__(cls);value._initialize(config,capability);return value

    def _initialize(self,config,capability):
        from truth_spine_observation_roles import disposable,MODULE
        self.config,self.capability=config,capability
        self.document=capability.document();self.root=Path(self.document['roots']['output'])
        self.launch=self.document['launch'];self.started=False;self.closed=False;self.fd=None
        self.last_ns=self.launch['start_ns'];self.streams={};self.acks={};self.lease=None
        self.children=OwnedChildren(self.root,service_module=MODULE if disposable(capability) else 'truth_spine_full_day_service',
            observation=capability,port_clear=lambda:port_is_clear(self.launch['port']))
        self.result=None;self.response_pins=self.document['seed_parents'][:] if disposable(capability) else []

    def check(self, deadline):
        from alpha_session_contract import require
        ns=time.monotonic_ns()
        require(self.last_ns<=ns<deadline, 'OBSERVATION_MONOTONIC_DEADLINE')
        self.last_ns=ns

    def drain(self):
        from alpha_session_contract import require
        for streams in self.streams.values():
            for name,(stream,count) in list(streams.items()):
                try:data=os.read(stream.fileno(),min(512,4097-count))
                except BlockingIOError:continue
                streams[name]=(stream,count+len(data))
                require(count+len(data)<=4096, 'OBSERVATION_OUTPUT_OVERFLOW')
                # Fixed failure only. Raw child output is never persisted.
                require(not data, 'OBSERVATION_UNEXPECTED_CHILD_OUTPUT')

    def start(self):
        from alpha_session_contract import require,instant
        from alpha_session_execution import safe_root,publish
        from alpha_observation_launch import listener_pids
        from alpha_observation_lifecycle import verify_observation_execution
        from provider_gateway_contract import content_hash,locked_authority
        from truth_spine_integration_service import Lease
        import platform
        require(not self.started, 'OBSERVATION_DUPLICATE_START');self.started=True
        self.check(self.launch['startup_ns'])
        require(instant(self.config['plan']['startup_not_before']) <= datetime.now(timezone.utc) <
            instant(self.config['plan']['startup_deadline']), 'OBSERVATION_UTC_STARTUP_WINDOW')
        from truth_spine_observation_roles import disposable,record
        if disposable(self.capability):self.capability.recheck(datetime.now(timezone.utc))
        else:verify_observation_execution(self.capability,self.capability.identity,now=datetime.now(timezone.utc))
        require(self.launch['host_identity']==dict(system=platform.system(),release=platform.release(),
            version=platform.version(),machine=platform.machine(),uid=os.getuid()), 'OBSERVATION_SELECTED_HOST')
        runtime=self.config['requests'][0]['runtime'];python=Path(runtime['root'])/runtime['interpreter']
        require(Path(sys.executable).resolve()==python and Path(__file__).resolve()==
            Path(self.document['roots']['release'])/'truth_spine_full_day_runner.py', 'OBSERVATION_RUNNING_RELEASE')
        require(hashlib.sha256(Path('/usr/bin/sandbox-exec').read_bytes()).hexdigest()==self.launch['sandbox_hash'],
            'OBSERVATION_SANDBOX_IDENTITY')
        require(listener_pids(self.launch['port'])==[] and port_is_clear(self.launch['port']),
            'OBSERVATION_PORT_OCCUPIED')
        self.fd=safe_root(str(self.root));self.lease=Lease(self.root,'runner')
        # Mandatory fresh output/config created by run_observation only.
        require(set(os.listdir(self.fd))=={'topology.json','requests','runner.lock'}, 'OBSERVATION_OUTPUT_REUSE')
        pins={str(python):next(r['sha256'] for r in runtime['files'] if r['path']==runtime['interpreter'])}
        for role in ('scheduler','publisher','backend'):
            self.check(self.launch['startup_ns'])
            args=[str(python),'-B','-m',self.children.service_module,'--config',str(self.root/'topology.json'),
                '--role',role,'--observation-admission',self.capability.identity]
            from truth_spine_observation_roles import disposable,invocation_pins
            if disposable(self.capability):args+=invocation_pins(self.capability)
            port=self.launch['port'] if role=='backend' else None
            if port is not None:args+=['--port',str(port)]
            launch=self.children.prepare_launch(role,args,executable_hashes=pins,port=port,final_executable=str(python))
            child=subprocess.Popen(['/usr/bin/sandbox-exec','-f',self.document['roots']['control']+'/profile.sb',*launch.argv],
                cwd=self.document['roots']['release'],env={'LANG':'C','LC_ALL':'C','TZ':'UTC'},
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
            self.children.retain_observation_child(role,child,launch)
            child.stdin.close()
            for name in ('stdout','stderr'):os.set_blocking(getattr(child,name).fileno(),False)
            self.streams[role]={name:(getattr(child,name),0) for name in ('stdout','stderr')}
            # Existing owner retains a child even if registration fails.
            fp=self.children.register(role,child,launch.argv,self.document['roots']['release'],port,
                executable_hashes=pins,launch=launch)
            self.check(self.launch['startup_ns']);self.drain()
            if role=='backend':
                require(listener_pids(port)==[child.pid], 'OBSERVATION_LISTENER_OWNER')
            self.acks[role]=self.children.acknowledge_observation(role,self.fd)
        self.check(self.launch['startup_ns']);self.verify_tls()
        # Wait only for first functional heartbeat/projection, under SAME startup deadline.
        while True:
            self.check(self.launch['startup_ns']);self.drain()
            try:self.publish_probes();break
            except FileNotFoundError:time.sleep(.05)
        return True

    def verify_tls(self):
        import socket,ssl
        from alpha_session_contract import require
        from alpha_observation_launch import listener_pids
        require(listener_pids(self.launch['port'])==[self.children.active['backend']['child'].pid],
            'OBSERVATION_LISTENER_OWNER')
        context=ssl.create_default_context(cafile=self.document['roots']['control']+'/loopback.crt')
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            sock.settimeout(2);sock.connect(('127.0.0.1',self.launch['port']))
            with context.wrap_socket(sock,server_hostname='127.0.0.1') as secured:
                require(hashlib.sha256(secured.getpeercert(binary_form=True)).hexdigest()==self.launch['peer_hash'],
                    'OBSERVATION_TLS_PEER')
        self.check(self.launch['startup_ns'])

    def observe_receipt(self, slot, receipt, pins, completion):
        from alpha_session_contract import require
        from alpha_session_execution import publish
        from provider_gateway_contract import content_hash,locked_authority
        from truth_spine_observation_roles import disposable
        require(not disposable(self.capability),'DISPOSABLE_PROVIDER_FORBIDDEN')
        require(slot==len(self.response_pins) and receipt['scope']=='LIVE_QUALIFICATION' and
            receipt['request_id']==pins['manifest'] and completion['receipt']==content_hash(receipt),
            'OBSERVATION_DISPATCHER_RECEIPT')
        from alpha_observation_execution import publish_observation_checkpoint
        publish_observation_checkpoint(self.fd,slot,dict(schema='iios-observation-dispatcher-receipt-v1',
            admission_parent=self.capability.identity,slot=slot,parents=pins,receipt_parent=content_hash(receipt),
            completion_parent=content_hash(completion),authority=locked_authority()))
        self.response_pins.append(content_hash(receipt))
        from alpha_session_execution import read_record
        # Readiness waits only for a positively bound publication ACK. No
        # provider retry, window extension or malformed-evidence recovery occurs.
        deadline=datetime.fromisoformat(self.config['plan']['rows'][slot]['expires_at'])
        while True:
            self.check(self.launch['stop_ns'])
            require(datetime.now(timezone.utc)<deadline,'OBSERVATION_PUBLICATION_DEADLINE')
            try:ack=read_record(self.fd,'publisher-slot-'+str(slot)+'.json')
            except FileNotFoundError:time.sleep(.05);continue
            require(ack==dict(schema='iios-observation-publication-ack-v1',admission_parent=self.capability.identity,
                slot=slot,response_parents=self.response_pins,completion_parent=content_hash(completion),
                authority=locked_authority()),'OBSERVATION_PUBLICATION_ACK')
            self.verify_ready();break

    def publish_probes(self):
        from truth_spine_session_package import ObservationProbeReader
        from truth_spine_integration import atomic
        p=ObservationProbeReader(root=self.root,capability=self.capability,plan=self.config['plan'],
            requests=self.config['requests'],request_pins=self.config['request_pins'],children=self.children,expected_responses=self.response_pins).collect(
                datetime.now(timezone.utc))
        atomic(self.root/'observation-probes.json',p)
        return p

    def verify_ready(self):
        from alpha_session_contract import require
        from alpha_session_execution import read_record
        from provider_gateway_contract import content_hash
        require(self.started and not self.closed and len(self.acks)==3, 'OBSERVATION_STARTUP_INCOMPLETE')
        self.check(self.launch['stop_ns']);self.capability.recheck(datetime.now(timezone.utc));self.drain()
        for role,parent in self.acks.items():
            self.children.verify(self.children.active[role])
            require(content_hash(read_record(self.fd,role+'-observation-ack.json'))==parent, 'OBSERVATION_ACK_CHANGED')
        self.publish_probes()
        return True

    def cleanup(self):
        from alpha_session_contract import require
        from alpha_session_execution import read_record,publish
        from alpha_observation_launch import listener_pids
        from provider_gateway_contract import locked_authority
        if self.closed:return self.result
        from truth_spine_observation_roles import record
        self.closed=True;report={};cooperative=True;exit_parents={}
        try:
            self.check(self.launch['final_ns'])
            try:
                entry=self.children.active['backend'];self.children.verify(entry)
                require(listener_pids(self.launch['port'])==[entry['child'].pid],'OBSERVATION_LISTENER_OWNER')
            except Exception:
                cooperative=False;self.children.error('OBSERVATION_LISTENER_OWNER','backend')
            if self.fd is not None:
                publish(self.fd,'observation-stop.json',record(self.capability,{'admission_parent':self.capability.identity,
                    'authority':locked_authority()}))
            # Every role is independent; one failure never prevents another cleanup.
            for role,entry in list(self.children.active.items()):
                try:
                    fp=self.children.verify(entry)
                    remaining=(self.launch['final_ns']-time.monotonic_ns())/1e9
                    require(remaining>0,'OBSERVATION_CLEANUP_DEADLINE')
                    entry['child'].wait(timeout=min(5,remaining))
                    e=read_record(self.fd,role+'-observation-exit.json')
                    require(e==record(self.capability,{'schema':'iios-observation-exit-v1','admission_parent':self.capability.identity,
                        'role':role,'pid':entry['child'].pid,'startup_parent':fp.startup_receipt_hash,
                        'cooperative':True,'authority':locked_authority()}) and entry['child'].poll()==0,
                        'OBSERVATION_COOPERATIVE_EXIT')
                    exit_parents[role]=e['startup_parent']
                except Exception:
                    cooperative=False;self.children.error('OBSERVATION_COOPERATIVE_CLEANUP_FAILED',role)
        except Exception:
            cooperative=False;self.children.error('OBSERVATION_STOP_PUBLICATION_FAILED')
        finally:
            # Existing owner re-verifies before each fallback signal; forced exit
            # can never be classified as cooperative success.
            self.children.cleanup(report)
            clear=[]
            for _ in range(3):
                try:
                    self.check(self.launch['final_ns'])
                    clear.append(listener_pids(self.launch['port'])==[] and port_is_clear(self.launch['port']))
                except Exception:clear.append(False)
                time.sleep(.05)
            for streams in self.streams.values():
                for stream,_ in streams.values():stream.close()
            self.result=record(self.capability,{'verified':bool(report.get('clean_shutdown')) and all(clear) and len(exit_parents)==3,
                'cooperative':cooperative and len(exit_parents)==3,'roles':['scheduler','publisher','backend'],
                'listener_owner_reconciled':not self.children.active and all(clear),'port_clear':clear})
            if self.lease is not None:self.lease.close()
            if self.fd is not None:os.close(self.fd);self.fd=None
        return self.result


def run_observation(config, expected, *, approved_roots, qualification_pins):
    """Explicit independently pinned entrypoint; no shadow state is repurposed."""
    from alpha_observation_lifecycle import admit_observation_execution
    from alpha_observation_launch import lexical,directory
    from alpha_session_contract import require
    from alpha_session_execution import publish
    from alpha_observation_execution import run_admitted_observation
    from provider_gateway_contract import pin
    pin(config,expected)
    cap=admit_observation_execution(config['admission'],config['admission_parent'],
        approved_roots=approved_roots,approved_qualification_pins=qualification_pins,now=datetime.now(timezone.utc))
    require(config['roots']==approved_roots and config['qualification_pins']==qualification_pins,
        'OBSERVATION_INVOCATION_PINS')
    root=lexical(approved_roots['output']);fd=directory(str(root.parent))
    try:
        os.mkdir(root.name,0o700,dir_fd=fd)
        out=os.open(root.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
    finally:os.close(fd)
    try:
        publish(out,'topology.json',config);os.mkdir('requests',0o700,dir_fd=out)
        req=os.open('requests',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=out)
        try:
            for row in config['plan']['rows']:
                require(row['root']==str(root/'requests'/row['id']),'OBSERVATION_REQUEST_ROOT')
                os.mkdir(row['id'],0o700,dir_fd=req)
        finally:os.close(req)
    finally:os.close(out)
    lifecycle=ObservationLifecycle(config,cap)
    return run_admitted_observation(cap,cap.identity,config['plan'],config['plan_parent'],config['requests'],
        config['request_pins'],lifecycle=lifecycle)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode',choices=('SHADOW','BOUNDED_REAL_PROVIDER_OBSERVATION'),default='SHADOW')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--owner-topology-sha256')
    parser.add_argument('--owner-session-identity')
    parser.add_argument('--observation-config',type=Path)
    parser.add_argument('--observation-config-sha256')
    parser.add_argument('--observation-roots-json')
    parser.add_argument('--observation-qualification-pins-json')
    a = parser.parse_args()
    from alpha_session_contract import require
    if a.mode=='SHADOW':
        require(a.root is not None and a.owner_topology_sha256 and a.owner_session_identity and
            all(getattr(a,n) is None for n in ('observation_config','observation_config_sha256',
                'observation_roots_json','observation_qualification_pins_json')), 'SHADOW_ARGUMENTS_REQUIRED')
        return run(a.root, a.owner_topology_sha256, owner_session=a.owner_session_identity)
    require(a.root is a.owner_topology_sha256 is a.owner_session_identity is None and
        all(getattr(a,n) is not None for n in ('observation_config','observation_config_sha256',
            'observation_roots_json','observation_qualification_pins_json')), 'OBSERVATION_ARGUMENTS_REQUIRED')
    from alpha_observation_launch import lexical
    from alpha_session_evidence import json_document
    from alpha_session_execution import read_record,safe_root
    lexical(str(a.observation_config));fd=safe_root(str(a.observation_config.parent))
    try:config=read_record(fd,a.observation_config.name,expected_hash=a.observation_config_sha256)
    finally:os.close(fd)
    # Canonical module identity also when this file executes as __main__.
    from truth_spine_full_day_runner import run_observation as admitted_run
    result=admitted_run(config,a.observation_config_sha256,
        approved_roots=json_document(a.observation_roots_json.encode()),
        qualification_pins=json_document(a.observation_qualification_pins_json.encode()))
    return 0 if result['result']=='OBSERVATION_COMPLETE' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'status': 'FAILED_CLOSED', 'category': type(exc).__name__}))
        sys.exit(4)
