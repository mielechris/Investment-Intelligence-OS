"""Bounded isolated installed-runtime acceptance; never controls permanent services."""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'BACK END/backend'))
from truth_spine_process_identity import (IdentityFailure, ProcessObservation, binding,
    digest, inspect_macos, normalized, read_receipt, safe)

ROLES = ('scheduler', 'publisher', 'backend')


class RunnerFailure(RuntimeError):
    """Only fixed runner categories are reported, never exception messages."""


@dataclass(frozen=True)
class Launch:
    role: str
    argv: tuple[str, ...]
    values: tuple[tuple[str, object], ...]
    executable_hashes: tuple[tuple[str, str], ...]
    final_executable: str


@dataclass(frozen=True)
class ProcessFingerprint:
    role: str
    observed: ProcessObservation
    argv: tuple[str, ...]
    expected_cwd: str
    shadow_root: str
    port: int | None
    created_at: str
    runner_identity: str
    instance_id: str
    startup_receipt_hash: str
    launch: Launch


def atomic_evidence(root: Path, name: str, value: dict) -> None:
    if name not in {'acceptance.json', 'runner-incidents.json', 'emergency-incident.json'}:
        raise RunnerFailure('EVIDENCE_NAME_INVALID')
    if root != root.resolve() or any(p.is_symlink() for p in (root, *root.parents)):
        raise RunnerFailure('EVIDENCE_ROOT_INVALID')
    info = root.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RunnerFailure('EVIDENCE_ROOT_INVALID')
    target = root/name
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise RunnerFailure('EVIDENCE_TARGET_INVALID')
    temporary = root/(name+'.staging')
    data = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()+b'\n'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()  # Only the staging file successfully created above.


class OwnedChildren:
    """Tracks Popen children until exit, including unverified partial startup.

    Tests inject inspectors and fake children. No injected inspector is exposed
    through production CLI/environment. A mismatch never permits a signal.
    """
    def __init__(self, root, *, inspector=inspect_macos, writer=atomic_evidence,
                 port_clear=None, timeout=30, parent_pid=None, receipt_reader=read_receipt,
                 monotonic=time.monotonic, pause=time.sleep, stabilization_seconds=10):
        if not 0 < timeout <= 30:
            raise ValueError('STOP_TIMEOUT_INVALID')
        self.root = Path(root)
        self.inspector, self.writer, self.timeout = inspector, writer, timeout
        self.parent_pid = os.getpid() if parent_pid is None else parent_pid
        self.port_clear = port_clear or (lambda: False)
        self.identity = 'shadow-runner-'+uuid.uuid4().hex
        self.active, self.completed, self.fingerprints = {}, [], []
        self.attempts, self.errors, self.logs, self.log_results = [], [], [], []
        self.finished = None
        if not 0 < stabilization_seconds <= 10:
            raise ValueError('STABILIZATION_BOUND_INVALID')
        self.receipt_reader = receipt_reader
        self.monotonic, self.pause, self.stabilization_seconds = monotonic, pause, stabilization_seconds
        self.launches, self.observation_sequences, self.diagnostics, self.launch_records = {}, [], [], []

    def prepare_launch(self, role, argv, *, executable_hashes, port=None, final_executable=None):
        """Must run before Popen. An instance is identification, never authority."""
        instance = 'shadow-child-'+uuid.uuid4().hex
        created = datetime.now(timezone.utc).isoformat()
        values = binding(self.root, instance, self.identity, role, port, created)
        expected = [argv[0], '-B', '-m', 'truth_spine_integration_service', '--config',
                    str(self.root/'topology.json'), '--role', role]
        if port is not None:
            expected += ['--port', str(port)]
        if list(argv) != expected:
            raise RunnerFailure('CHILD_COMMAND_INVALID')
        hashes = {str(Path(k).resolve()):v for k,v in executable_hashes.items()}
        final = str(Path(final_executable or list(hashes)[-1]).resolve())
        if not 1 <= len(hashes) <= 2 or final not in hashes or str(Path(argv[0]).resolve()) not in hashes:
            raise RunnerFailure('EXECUTABLE_PINS_INVALID')
        argv = tuple(argv)+('--instance-id', instance, '--runner-id', self.identity, '--created-at', created)
        launch = Launch(role, argv, tuple(sorted(values.items())), tuple(hashes.items()), final)
        self.launches[instance] = launch
        return launch

    def diagnostic(self, role, field, expected, observed, category, source='OS'):
        if field == 'command':
            expected, observed = {'sanitized_sha256': digest(expected)}, {'sanitized_sha256': digest(observed)}
        self.diagnostics.append({'role': role, 'field': field, 'expected': safe(expected, self.root),
            'observed': safe(observed, self.root), 'observed_at': datetime.now(timezone.utc).isoformat(),
            'source': source, 'normalization': 'UTC_SECONDS_RESOLVED_PATHS_EXACT_ARGV_NO_PPID_ALIAS',
            'classification': category})

    def require_fields(self, role, expected, observed, source='OS'):
        differences = [key for key in expected if expected[key] != observed.get(key)]
        differences += [key for key in observed if key not in expected]
        for key in differences:
            self.diagnostic(role, key, expected.get(key), observed.get(key), 'PROCESS_IDENTITY_MISMATCH', source)
        if differences:
            raise RunnerFailure('PROCESS_IDENTITY_MISMATCH')

    def persist_identity(self):
        try:
            self.writer(self.root, 'runner-incidents.json', {'runner_identity': self.identity,
                'launch_records': self.launch_records,
                'launch_observations': self.observation_sequences, 'identity_diagnostics': self.diagnostics})
        except BaseException as exc:
            self.error('ACCEPTANCE_PERSISTENCE_FAILED', error=exc)
            raise RunnerFailure('IDENTITY_PERSISTENCE_FAILED') from None

    def observe(self, entry, launch):
        role = launch.role
        try:
            o = self.inspector(entry['child'].pid)
            if o is None:
                self.diagnostic(role, 'process_present', True, False, 'PROCESS_EXITED')
                raise RunnerFailure('PROCESS_EXITED')
            try:
                n = normalized(o, self.root)
            except (IdentityFailure, ValueError):
                self.observation_sequences.append({'instance_id': dict(launch.values)['instance_id'],
                    'at': datetime.now(timezone.utc).isoformat(), 'source': 'OS',
                    'normalization_failed': True, 'observation': safe(asdict(o), self.root)})
                if not o.argv or o.command != ' '.join(o.argv):
                    self.diagnostic(role, 'command', ' '.join(o.argv), o.command, 'ARGV_BOUNDARIES_INVALID')
                else:
                    self.diagnostic(role, 'start_time', 'VALID_UTC_OS_START_TIME', o.start_time, 'START_TIME_INVALID')
                raise RunnerFailure('PROCESS_INSPECTION_FAILED') from None
            self.observation_sequences.append({'instance_id': dict(launch.values)['instance_id'],
                'at': datetime.now(timezone.utc).isoformat(), 'source': 'OS', 'observation': n})
            hashes = dict(launch.executable_hashes)
            exe = str(Path(o.executable).resolve())
            expected = {'pid': entry['child'].pid, 'parent_pid': self.parent_pid,
                        'cwd': str(self.root/'release/backend'), 'argv_tail': list(launch.argv[1:]),
                        'executable_hash': hashes.get(exe), 'argv0_pinned': True, 'executable_pinned': True}
            actual = {'pid': o.pid, 'parent_pid': o.parent_pid, 'cwd': str(Path(o.cwd).resolve()),
                      'argv_tail': list(o.argv[1:]), 'executable_hash': o.executable_hash,
                      'argv0_pinned': str(Path(o.argv[0]).resolve()) in hashes, 'executable_pinned': exe in hashes}
            self.require_fields(role, expected, actual)
            return o, n
        except (RunnerFailure, KeyboardInterrupt):
            raise
        except BaseException as exc:
            self.diagnostic(role, 'observation', 'VALID_OS_OBSERVATION', type(exc).__name__, 'OBSERVATION_FAILED')
            raise RunnerFailure('PROCESS_INSPECTION_FAILED') from None

    def reconcile_receipt(self, launch, n):
        expected = dict(launch.values)
        try:
            receipt = self.receipt_reader(self.root, expected['instance_id'])
        except Exception as exc:
            self.diagnostic(launch.role, 'startup_receipt', 'HASH_VALID_OWNER_ONLY', type(exc).__name__, 'RECEIPT_INVALID', 'STARTUP_RECEIPT')
            raise RunnerFailure('STARTUP_RECEIPT_INVALID') from None
        if receipt is None:
            return None
        if not isinstance(receipt, dict) or not isinstance(receipt.get('observation'), dict):
            self.diagnostic(launch.role, 'startup_receipt', 'STRICT_STARTUP_DOCUMENT', type(receipt).__name__, 'RECEIPT_INVALID', 'STARTUP_RECEIPT')
            raise RunnerFailure('STARTUP_RECEIPT_INVALID')
        desired = {**expected, 'observation': n}
        desired['content_hash'] = digest(desired)
        # Flatten observation fields so the exact OS/receipt discrepancy survives.
        self.require_fields(launch.role, n, receipt.get('observation', {}), 'STARTUP_RECEIPT')
        self.require_fields(launch.role, desired, receipt, 'STARTUP_RECEIPT')
        return receipt['content_hash']

    def error(self, category, role=None, error=None):
        row = {'category': category, 'role': role}
        if error is not None:
            row['exception_type'] = type(error).__name__
        self.errors.append(row)

    def register(self, role, child, argv, cwd, port=None, *, executable_hashes,
                 registry_key=None, launch=None):
        key = role if registry_key is None else registry_key
        if role not in ROLES or key in self.active:
            raise RunnerFailure('CHILD_ROLE_ALREADY_TRACKED')
        entry = {'child': child, 'fingerprint': None, 'role': role}
        self.active[key] = entry  # Never lose a live child on failed verification.
        self.launch_records.append(safe({'pid': child.pid, 'expected_parent_pid': self.parent_pid,
            'role': role, 'launch': asdict(launch) if launch else None,
            'initial_observation': None}, self.root))
        launch_record = self.launch_records[-1]
        try:
            if (launch is None or self.launches.get(dict(launch.values)['instance_id']) != launch
                    or launch.role != role or tuple(argv) != launch.argv
                    or dict(launch.executable_hashes) != {str(Path(k).resolve()):v for k,v in executable_hashes.items()}
                    or Path(cwd) != self.root/'release/backend' or dict(launch.values)['port'] != port):
                self.diagnostic(role, 'launch', 'PRESPAWN_BOUND_LAUNCH', None, 'LAUNCH_INVALID')
                raise RunnerFailure('LAUNCH_INVALID')
            end = self.monotonic()+self.stabilization_seconds
            anchor, previous, stable, final_seen = None, None, 0, False
            while self.monotonic() < end:
                if child.poll() is not None:
                    self.diagnostic(role, 'process_present', True, False, 'PROCESS_EXITED')
                    raise RunnerFailure('PROCESS_EXITED')
                o, n = self.observe(entry, launch)
                if anchor is None:
                    launch_record['initial_observation'] = n
                    anchor = {key:n[key] for key in ('pid', 'parent_pid', 'start_time', 'cwd')}
                self.require_fields(role, anchor, {key:n[key] for key in anchor})
                final = str(Path(o.executable).resolve()) == launch.final_executable
                if final_seen and not final:
                    self.diagnostic(role, 'executable', launch.final_executable, o.executable, 'OSCILLATING_IDENTITY')
                    raise RunnerFailure('OSCILLATING_IDENTITY')
                final_seen |= final
                stable = stable+1 if final and n == previous else int(final)
                previous = n
                receipt_hash = self.reconcile_receipt(launch, n) if final else None
                if stable >= 3 and receipt_hash is not None:
                    break
                self.pause(.05)
            else:
                self.diagnostic(role, 'stabilization', 'THREE_FINAL_OBSERVATIONS_AND_RECEIPT',
                                {'consecutive': stable, 'final_seen': final_seen}, 'STABILIZATION_TIMEOUT')
                raise RunnerFailure('STABILIZATION_TIMEOUT')
            if self.monotonic() >= end:
                self.diagnostic(role, 'stabilization_deadline', 'WITHIN_BOUND', 'EXCEEDED', 'STABILIZATION_TIMEOUT')
                raise RunnerFailure('STABILIZATION_TIMEOUT')
            fp = ProcessFingerprint(role, o, tuple(argv), str(cwd), str(self.root), port,
                                    dict(launch.values)['created_at'], self.identity,
                                    dict(launch.values)['instance_id'], receipt_hash, launch)
            entry['fingerprint'] = fp
            self.fingerprints.append(asdict(fp))
            self.verify(entry)
            self.persist_identity()
            return fp
        except BaseException as exc:
            self.error('PROCESS_IDENTITY_MISMATCH', role, exc)
            self.persist_identity()
            raise RunnerFailure('PROCESS_IDENTITY_MISMATCH') from None

    def verify(self, entry):
        fp = entry['fingerprint']
        try:
            if (fp is None or fp.role != entry['role'] or fp.runner_identity != self.identity
                    or fp.shadow_root != str(self.root) or fp.expected_cwd != str(self.root/'release/backend')):
                self.diagnostic(entry['role'], 'fingerprint', 'STABILIZED_BOUND_CHILD', None, 'FINGERPRINT_INVALID')
                raise RunnerFailure('PROCESS_IDENTITY_MISMATCH')
            _, n = self.observe(entry, fp.launch)
            self.require_fields(fp.role, normalized(fp.observed, self.root), n)
            expected_binding = binding(self.root, fp.instance_id, self.identity, fp.role, fp.port, fp.created_at)
            self.require_fields(fp.role, dict(fp.launch.values), expected_binding, 'CONFIGURATION')
            h = self.reconcile_receipt(fp.launch, n)
            self.require_fields(fp.role, {'startup_receipt_hash': fp.startup_receipt_hash}, {'startup_receipt_hash': h}, 'STARTUP_RECEIPT')
            self.attempts.append({'role': entry['role'], 'action': 'VERIFY', 'matched': True})
            return fp
        except BaseException as exc:
            if not isinstance(exc, RunnerFailure):
                self.diagnostic(entry['role'], 'verification', 'VALID_BOUND_IDENTITY', type(exc).__name__, 'VERIFICATION_FAILED')
            self.attempts.append({'role': entry['role'], 'action': 'VERIFY', 'matched': False})
            self.persist_identity()
            raise

    def stop(self, role):
        entry = self.active[role]
        child = entry['child']
        action = 'VERIFY'
        try:
            if child.poll() is not None:
                if entry['fingerprint'] is None:
                    raise RunnerFailure('PROCESS_IDENTITY_MISMATCH')
                outcome = 'ALREADY_EXITED_VERIFIED_CHILD'
            else:
                self.verify(entry)
                action = 'TERMINATE'
                self.attempts.append({'role': role, 'action': action})
                child.terminate()
                action = 'WAIT'
                try:
                    child.wait(timeout=self.timeout)
                    outcome = 'STOPPED_CLEANLY'
                except subprocess.TimeoutExpired:
                    self.attempts.append({'role': role, 'action': 'GRACEFUL_TIMEOUT'})
                    action = 'VERIFY'
                    self.verify(entry)  # Mandatory independent reinspection before kill.
                    action = 'KILL'
                    self.attempts.append({'role': role, 'action': action})
                    child.kill()
                    action = 'FORCE_WAIT'
                    child.wait(timeout=self.timeout)
                    outcome = 'FORCE_STOPPED_AFTER_VERIFIED_TIMEOUT'
                if child.poll() is None:
                    raise RunnerFailure('EXIT_NOT_CONFIRMED')
            self.completed.append({'role': role, 'fingerprint': asdict(entry['fingerprint']),
                                   'outcome': outcome, 'returncode': child.poll()})
            del self.active[role]
            return True
        except BaseException as exc:
            category = 'PROCESS_IDENTITY_MISMATCH' if action == 'VERIFY' else 'TERMINATION_FAILED'
            self.error(category, role, exc)
            self.attempts.append({'role': role, 'action': action, 'outcome': category})
            return False

    def cleanup(self, report, primary=None):
        if self.finished is not None:
            return self.finished
        if primary is not None:
            report['primary_exception'] = {'type': type(primary).__name__}
            if isinstance(primary, RunnerFailure) and re.fullmatch(r'[A-Z_]{1,80}', str(primary)):
                report['primary_exception']['category'] = str(primary)
        try:
            for role in reversed(list(self.active)):
                try:
                    self.stop(role)
                except BaseException as exc:
                    self.error('TERMINATION_FAILED', role, exc)
        finally:
            for index, handle in enumerate(self.logs):
                try:
                    handle.close()
                    if handle.closed is not True:
                        raise RunnerFailure('LOG_CLOSURE_NOT_CONFIRMED')
                    self.log_results.append({'index': index, 'closed': True})
                except BaseException as exc:
                    self.log_results.append({'index': index, 'closed': False})
                    self.error('LOG_CLOSURE_FAILED', error=exc)
            try:
                clear = self.port_clear() is True
                if not clear:
                    self.error('PORT_REMAINED_OCCUPIED')
            except BaseException as exc:
                clear = False
                self.error('PORT_CHECK_FAILED', error=exc)
        report.update(runner_identity=self.identity, child_fingerprints=self.fingerprints,
                      launch_records=self.launch_records,
                      launch_observations=self.observation_sequences,
                      identity_diagnostics=self.diagnostics,
                      completed_processes=self.completed, stop_attempts=self.attempts,
                      cleanup_errors=self.errors, unresolved_children=[
                          {'role': r, 'pid': e['child'].pid, 'fingerprint':
                           asdict(e['fingerprint']) if e['fingerprint'] else None}
                          for r, e in self.active.items()], log_closure=self.log_results,
                      port_clear=clear)
        report['clean_shutdown'] = not self.active and clear and not self.errors
        report['result'] = 'GREEN' if report['clean_shutdown'] and primary is None else 'RED'
        # Raw process output and private paths never enter incident files.
        sanitized = safe(report, self.root)
        report.clear(); report.update(sanitized)
        persistence_failed = False
        for name in ('runner-incidents.json', 'acceptance.json'):
            try:
                self.writer(self.root, name, report)
            except BaseException as exc:
                self.error('ACCEPTANCE_PERSISTENCE_FAILED', error=exc)
                report['cleanup_errors'] = safe(self.errors, self.root)
                report.update(result='RED', clean_shutdown=False)
                persistence_failed = True
        if persistence_failed:
            try:
                self.writer(self.root, 'emergency-incident.json', {
                    'runner_identity': self.identity, 'result': 'RED',
                    'primary_exception': report.get('primary_exception'),
                    'cleanup_errors': self.errors, 'unresolved_children': report['unresolved_children'],
                    'port_clear': clear})
            except BaseException as emergency:
                self.error('EMERGENCY_PERSISTENCE_FAILED', error=emergency)
        report['cleanup_errors'] = safe(self.errors, self.root)
        self.finished = report
        return report


def get(port,path):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=60) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())


def rejected_duplicate(role, owner, argv, *, spawn, counts, lock_bytes,
                       executable_hashes, port=None, timeout=5, final_executable=None):
    """A rejected contender is never an accepted owner. Never blindly kill it.

    Fast rejected children may exit before an OS fingerprint can be captured:
    Popen.wait then proves the exact child exited, and no signal is issued.
    A contender which does not exit is returned for identity-safe cleanup.
    """
    before = counts()
    lock = lock_bytes(role)
    owner.verify(owner.active[role])
    launch = owner.prepare_launch(role, argv, executable_hashes=executable_hashes,
                                  port=port, final_executable=final_executable)
    child = spawn(launch.argv)
    key = 'duplicate-'+role
    # Fast rejected/reaped contenders are not accepted owners and are never
    # signaled. A still-live contender receives the same identity contract.
    try:
        code = child.wait(timeout=timeout)
    except BaseException:
        # A contender which exits needs no ownership or signal. A live one
        # must meet the full startup contract before cleanup may signal it.
        owner.register(role, child, launch.argv, owner.root/'release/backend', port,
                       executable_hashes=executable_hashes, registry_key=key, launch=launch)
        raise RunnerFailure('DUPLICATE_DID_NOT_EXIT') from None
    if key in owner.active and not owner.stop(key):
        raise RunnerFailure('DUPLICATE_EXIT_NOT_CONFIRMED')
    owner.verify(owner.active[role])
    if code == 0 or counts() != before or lock_bytes(role) != lock:
        raise RunnerFailure('DUPLICATE_OWNER_ACCEPTED_OR_DISTURBED')
    return {'role': role, 'pid': child.pid, 'argv': list(launch.argv), 'instance_id': dict(launch.values)['instance_id'], 'returncode': code,
            'rejected': True, 'owner_unchanged': True, 'events_unchanged': True,
            'lock_unchanged': True, 'termination_signal_sent': False,
            'classification': 'REJECTED_CONTENDER_EXIT_CONFIRMED_NOT_AN_OWNER'}


def readiness_failure(port, role, *, request=get):
    ready = request(port, '/health/ready')[0]
    market = request(port, '/health/market-readiness')[0]
    if ready != 503 or market != 503:
        raise RunnerFailure('STOPPED_OWNER_NOT_FAIL_CLOSED')
    return {'role': role, 'ready': ready, 'market': market}


def port_is_clear(port):
    with socket.socket() as check:
        check.settimeout(2)
        result = check.connect_ex(('127.0.0.1', port))
    if result == 0:
        return False
    if result == errno.ECONNREFUSED:
        return True
    raise RunnerFailure('PORT_CLEAR_NOT_PROVEN')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True,type=Path);parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--review-seconds',type=int,default=0);a=parser.parse_args();root=a.root.resolve()
    if root.parent!=Path('/private/tmp') or not root.name.startswith('iios-truth-spine-3-acceptance-') or a.port in {5176,5177,5184,5185,5186,8002}:raise ValueError('ISOLATED_ROOT_REQUIRED')
    t=json.loads((root/'topology.json').read_bytes());backend=root/'release/backend';python=root/'runtime/bin/python'
    env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(backend),'PYTHONUNBUFFERED':'1'}
    def port_clear():
        return port_is_clear(a.port)
    children=OwnedChildren(root,port_clear=port_clear)
    report={'readiness_transitions':[], 'duplicate_owner_tests':[]}
    command=[str(python),'-B','-m','truth_spine_integration_service','--config',str(root/'topology.json')]
    runtime=json.loads((root/'runtime/runtime-manifest.json').read_bytes())
    executable_hashes={str(python):runtime['interpreter_sha256']}
    if runtime.get('process_executable'):
        executable_hashes[runtime['process_executable']]=runtime['process_executable_hash']
    for name,expected_hash in executable_hashes.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected_hash:
            raise RunnerFailure('EXECUTABLE_HASH_MISMATCH')
    def start(role):
        f=(root/(role+'.log')).open('ab');children.logs.append(f);os.chmod(f.name,0o600)
        argv=command+['--role',role]+(['--port',str(a.port)] if role=='backend' else [])
        launch=children.prepare_launch(role,argv,executable_hashes=executable_hashes,
                                       port=a.port if role=='backend' else None,
                                       final_executable=runtime.get('process_executable',str(python)))
        p=subprocess.Popen(launch.argv,cwd=backend,env=env,stdout=f,stderr=f)
        children.register(role,p,launch.argv,backend,a.port if role=='backend' else None,
                          executable_hashes=executable_hashes,launch=launch)
        print(json.dumps({'role':role,'pid':p.pid,'port':a.port if role=='backend' else None}),flush=True);return p
    def wait_ready():
        until=time.monotonic()+180
        while time.monotonic()<until:
            if any(e['child'].poll() is not None for e in children.active.values()):raise RunnerFailure('CANDIDATE_PROCESS_EXITED')
            try:
                code,body=get(a.port,'/health/ready')
                if code==200:return body
            except (OSError,ValueError):pass
            time.sleep(1)
        raise RunnerFailure('CANDIDATE_READINESS_TIMEOUT')
    def stop(role):
        if not children.stop(role):raise RunnerFailure('CHILD_STOP_FAILED')
    def count():
        db=sqlite3.connect((root/'canonical-events.db').as_uri()+'?mode=ro',uri=True)
        try:return db.execute('select count(*),count(distinct id) from records').fetchone()
        finally:db.close()
    primary=None
    try:
        start('scheduler')
        until=time.monotonic()+180
        while not (root/'scheduler-heartbeat.json').exists():
            if children.active['scheduler']['child'].poll() is not None:raise RunnerFailure('SCHEDULER_FAILED')
            if time.monotonic()>until:raise RunnerFailure('INGEST_TIMEOUT')
            time.sleep(1)
        start('publisher');start('backend');report['ready']=wait_ready();report['initial_counts']=count()
        for endpoint in ['live','ready','market-readiness','research-readiness']:
            report[endpoint]=get(a.port,'/health/'+endpoint)
        if report['market-readiness'][0]!=503:raise ValueError('MARKET_AUTHORITY_NOT_DISABLED')
        def contender(argv):
            return subprocess.Popen(argv,cwd=backend,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def lock_bytes(role):
            return (root/(role+'.lock')).read_bytes() if role!='backend' else None
        for role in ROLES:
            report['duplicate_owner_tests'].append(rejected_duplicate(role,children,
                command+['--role',role]+(['--port',str(a.port)] if role=='backend' else []),spawn=contender,
                counts=count,lock_bytes=lock_bytes,executable_hashes=executable_hashes,
                port=a.port if role=='backend' else None,
                final_executable=runtime.get('process_executable',str(python))))
        report['duplicate_owner_rejected']=True
        report['readiness_transitions'].append({'role':'scheduler','ready':200,'market':503})
        stop('scheduler')
        report['readiness_transitions'].append(readiness_failure(a.port,'scheduler'))
        start('scheduler');wait_ready()
        if get(a.port,'/health/market-readiness')[0]!=503:raise RunnerFailure('MARKET_AUTHORITY_NOT_DISABLED')
        report['readiness_transitions'].append({'role':'scheduler','ready':200,'market':503})
        report['restart_counts']=count()
        if report['restart_counts']!=report['initial_counts']:raise ValueError('RESTART_DUPLICATE_EVENTS')
        stop('publisher');time.sleep(16)
        transition=readiness_failure(a.port,'publisher')
        report['readiness_transitions'].append(transition)
        report['stale_readiness']=transition['ready']
        start('publisher');wait_ready();report['recovery']='READY_WITHOUT_STATE_REPAIR'
        report['soak']=[]
        for _ in range(10):
            started=time.monotonic();code,_=get(a.port,'/health/ready');report['soak'].append({'http':code,'seconds':time.monotonic()-started})
            if code!=200:raise ValueError('SOAK_READINESS_FAILED')
        p=root/'inputs/operational.db';restored=root/'rollback-rehearsal.db';shutil.copyfile(p,restored);restored.chmod(0o400)
        report['rollback']=hashlib.sha256(p.read_bytes()).hexdigest()==hashlib.sha256(restored.read_bytes()).hexdigest()
        before=json.loads((root/'preservation.json').read_bytes());report['input_preservation']=all(hashlib.sha256((root/name).read_bytes()).hexdigest()==h for name,h in before['input_hashes'].items())
        report['source_preservation']=all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==h for name,h in before['source_files'].items())
        if not all(report[k] for k in ['rollback','input_preservation','source_preservation']):raise ValueError('PRESERVATION_FAILED')
        report['result']='BACKEND_GREEN_BROWSER_SEPARATE';print(json.dumps(report),flush=True)
        # Read-only browser work occurs during this bounded interval; cleanup remains automatic.
        until=time.monotonic()+min(max(a.review_seconds,0),600)
        while time.monotonic()<until:time.sleep(1)
    except BaseException as exc:
        primary=exc
    finally:
        children.cleanup(report,primary)
        print(json.dumps(report),flush=True)
    return 0 if report['result']=='GREEN' else 1


if __name__=='__main__':sys.exit(main())
