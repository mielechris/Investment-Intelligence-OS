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
    if root.name.startswith('iios-truth-spine-3-acceptance-sb38d-clean-'):
        from truth_spine_lineage import write_new
        from truth_spine_contract import canonical
        write_new(root,name,canonical(value))
        return
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
                 monotonic=time.monotonic, pause=time.sleep, stabilization_seconds=10,
                 service_module='truth_spine_integration_service'):
        if not 0 < timeout <= 30:
            raise ValueError('STOP_TIMEOUT_INVALID')
        self.root = Path(root)
        if service_module not in {'truth_spine_integration_service', 'truth_spine_full_day_service'}:
            raise ValueError('CHILD_SERVICE_MODULE_INVALID')
        self.service_module = service_module
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
        expected = [argv[0], '-B', '-m', self.service_module, '--config',
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
        report['result'] = ('BACKEND_CLEANUP_ONLY' if report.get('requires_package_browser') else 'GREEN') if report['clean_shutdown'] and primary is None else 'RED'
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


def stable_port_clear(port, *, probe=port_is_clear, pause=time.sleep, listeners=None):
    def query():
        result=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:'+str(port),'-sTCP:LISTEN','-Fpn'],
                              capture_output=True,text=True,timeout=2)
        if result.returncode!=1 or result.stdout.strip() or result.stderr.strip():
            raise RunnerFailure('LISTENER_CLEAR_NOT_PROVEN')
        return []
    query=listeners or query
    samples=[]
    for i in range(2):
        if i:pause(.25)
        sample={'tcp_clear':probe(port),'listeners':query()}
        if sample!={'tcp_clear':True,'listeners':[]}:raise RunnerFailure('STABLE_PORT_CLEAR_NOT_PROVEN')
        samples.append(sample)
    return {'schema':'iios-stable-port-clear-v1','port':port,'samples':samples}


def protected_processes(expected, *, census=None, inspector=inspect_macos):
    if census is None:
        p=subprocess.run(['/bin/ps','-ww','-axo','pid=,comm='],capture_output=True,text=True,timeout=5,
                         env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        if p.returncode:raise RunnerFailure('PROTECTED_CENSUS_FAILED')
        census=[]
        for line in p.stdout.splitlines():
            parts=line.strip().split(None,1)
            if len(parts)!=2 or not parts[0].isdigit():raise RunnerFailure('PROTECTED_CENSUS_INVALID')
            census.append((int(parts[0]),parts[1]))
    # Membership scope is independently pinned executable + working directory.
    scopes={(r['executable'],r['cwd']) for r in expected}
    expected_pids={r['pid'] for r in expected}
    observations={}
    for pid,executable in census:
        if executable in {r['executable'] for r in expected} or pid in expected_pids:
            observation=inspector(pid)
            if observation is None:raise RunnerFailure('PROTECTED_CENSUS_UNRESOLVED')
            if (observation.executable,observation.cwd) in scopes or pid in expected_pids:
                observations[pid]=observation
    if set(observations)!=expected_pids:raise RunnerFailure('PROTECTED_PROCESS_MEMBERSHIP_CHANGED')
    result=[]
    for row in expected:
        observation=observations[row['pid']]
        if observation is None:raise RunnerFailure('PROTECTED_PROCESS_MISSING')
        data=asdict(observation)
        data['argv']=list(data['argv'])
        result.append({k:data[k] for k in row})
    return result


def protected_listeners(expected):
    owners=sorted({r['pid'] for r in expected})
    census=subprocess.run(['/usr/sbin/lsof','-a','-p',','.join(map(str,owners)),'-nP','-iTCP','-sTCP:LISTEN','-Fpn'],
                          capture_output=True,text=True,timeout=5)
    if census.returncode or census.stderr.strip():raise RunnerFailure('PROTECTED_LISTENER_CENSUS_FAILED')
    seen=[];pid=None
    for line in census.stdout.splitlines():
        if line.startswith('p'):pid=int(line[1:])
        elif line.startswith('n'):seen.append((pid,line[1:]))
    if sorted(seen)!=sorted((r['pid'],r['address']+':'+str(r['port'])) for r in expected):
        raise RunnerFailure('PROTECTED_LISTENER_MEMBERSHIP_CHANGED')
    result=[]
    for row in expected:
        if set(row)!={'address','port','pid'} or row['address']!='127.0.0.1':
            raise RunnerFailure('LISTENER_PIN_INVALID')
        p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:'+str(row['port']),'-sTCP:LISTEN','-Fpn'],capture_output=True,text=True,timeout=5)
        lines=p.stdout.splitlines()
        if (p.returncode or [s for s in lines if s.startswith('p')]!=['p'+str(row['pid'])] or
                [s for s in lines if s.startswith('n')]!=['n'+row['address']+':'+str(row['port'])]):
            raise RunnerFailure('PROTECTED_LISTENER_CHANGED')
        result.append(row)
    return result


def verify_browser_tools(path, expected):
    from truth_spine_lineage import file_hash, require, check_pin, contained
    require(file_hash(path)==expected,'BROWSER_TOOLCHAIN_PIN_MISMATCH')
    tools=json.loads(path.read_bytes())
    require(set(tools)=={'node','cache','harness'},'BROWSER_TOOLCHAIN_SCHEMA')
    check_pin(tools['node'])
    for name in ('cache','harness'):
        tree=tools[name];require(tree['files'],'COMPLETE_BROWSER_INVENTORY_REQUIRED')
        root=Path(tree['root']);names=set()
        for row in tree['files']:
            p=contained(root,row['relative']);check_pin(row['pin'])
            require(row['pin']['path']==str(p),'BROWSER_PIN_PATH_MISMATCH');names.add(row['relative'])
        actual={str(p.relative_to(root)) for p in root.rglob('*') if not p.is_dir()}
        require(names==actual and len(names)==len(tree['files']),'BROWSER_INVENTORY_MISMATCH')
    return {**tools,'spec_file':str(path),'spec_hash':expected}


def cleanup_browser_wrapper(process, expected, receipt_hash, root, *, inspector=inspect_macos):
    """Never signal from a PID alone; retain each attempt even when another fails."""
    from truth_spine_lineage import file_hash, write_new
    from truth_spine_contract import canonical, verified
    errors=[]
    for number, action in enumerate(('terminate','kill')):
        result='ALREADY_EXITED'
        try:
            if process.poll() is None:
                path=root/'browser/wrapper-startup.json'
                if file_hash(path)!=receipt_hash:raise RunnerFailure('WRAPPER_RECEIPT_CHANGED')
                receipt=json.loads(path.read_bytes());verified(receipt)
                if receipt!=expected:raise RunnerFailure('WRAPPER_PARENT_CHANGED')
                observed=inspector(process.pid)
                data=asdict(observed) if observed else None
                if data is not None:data['argv']=list(data['argv'])
                if data!=expected['observation']:raise RunnerFailure('WRAPPER_IDENTITY_CHANGED')
                getattr(process,action)()
                process.wait(timeout=15 if action=='terminate' else 5)
                result='EXIT_CONFIRMED'
        except BaseException:
            errors.append('WRAPPER_'+action.upper()+'_UNRESOLVED');result='FAILED_CLOSED'
        try:
            write_new(root,'browser/wrapper-cleanup-'+str(number)+'.json',canonical({'action':action,'result':result}))
        except BaseException:errors.append('WRAPPER_CLEANUP_EVIDENCE_FAILED')
    return {'errors':errors,'remaining':process.poll() is None}


def run_package_browser(root, package_hash, spec, tools, children):
    from truth_spine_lineage import require, file_hash
    backend=children.active['backend']['fingerprint']
    require(backend is not None,'VERIFIED_BACKEND_REQUIRED')
    children.verify(children.active['backend'])
    protected_listeners([{'address':'127.0.0.1','port':spec['port'],'pid':backend.pid}])
    # Startup content identity, not a PID-only label.
    startup=json.loads((root/'state/backend-instance.json').read_bytes())
    node=tools['node']['path'];harness=Path(tools['harness']['root'])
    contract=root/'browser/contract.json'
    env={'PATH':'/usr/bin:/bin','TMPDIR':str(root/'browser'),'PLAYWRIGHT_BROWSERS_PATH':tools['cache']['root']}
    code="import {makeContract,newJSON} from './package-contract.mjs';newJSON(process.argv[1],makeContract(...process.argv.slice(2)));"
    subprocess.run([node,'--input-type=module','-e',code,str(contract),str(root),package_hash,
                    startup['content_hash'],'http://127.0.0.1:'+str(spec['port']),spec['source_commit'],tools['spec_file'],tools['spec_hash']],
                   cwd=harness,env=env,check=True,timeout=30)
    value=json.loads(contract.read_bytes())
    from truth_spine_lineage import write_new
    from truth_spine_contract import canonical, seal
    argv=[node,str(harness/'package-run.mjs'),str(contract),value['content_hash'],str(root/'browser/run'),str(min(spec['duration_seconds'],1800))]
    # The exclusive log exists before launch and retains partial output on timeout.
    with (root/'logs/browser-wrapper.log').open('xb') as output:
        process=subprocess.Popen(argv,cwd=harness,env=env,stdout=output,stderr=subprocess.STDOUT)
        expected=None;expected_hash=None
        try:
            observed=inspect_macos(process.pid)
            require(observed is not None and observed.parent_pid==os.getpid() and
                    observed.argv==tuple(argv) and observed.cwd==str(harness) and
                    observed.executable==str(Path(node).resolve()) and
                    observed.executable_hash==tools['node']['sha256'],'BROWSER_WRAPPER_IDENTITY_INVALID')
            data=asdict(observed);data['argv']=list(data['argv'])
            expected=seal({'schema':'iios-browser-wrapper-startup-v1','observation':data,
                           'root':str(root),'port':spec['port'],'package_hash':package_hash,
                           'contract_hash':value['content_hash'],'backend_hash':startup['content_hash']})
            expected_hash=write_new(root,'browser/wrapper-startup.json',canonical(expected))
            process.wait(timeout=min(spec['duration_seconds'],1800)+40)
        except BaseException:
            cleanup=cleanup_browser_wrapper(process,expected,expected_hash,root) if expected_hash else {
                'errors':['UNVERIFIED_WRAPPER_NOT_SIGNALED'],'remaining':process.poll() is None}
            write_new(root,'browser/wrapper-failure.json',canonical({'result':'FAILED','cleanup':cleanup,'pid':process.pid}))
            raise RunnerFailure('BROWSER_WRAPPER_FAILED') from None
        finally:
            output.flush();os.fsync(output.fileno())
    require(process.returncode==0,'PACKAGE_BROWSER_FAILED')
    children.verify(children.active['backend'])
    verify_browser_tools(Path(tools['spec_file']),tools['spec_hash'])
    receipt=root/'browser/run/browser-receipt.json'
    return {'path':'browser/run/browser-receipt.json','sha256':file_hash(receipt),'contract':value['content_hash'],
            'backend_instance_hash':startup['content_hash'],'tools_hash':tools['spec_hash']}


def consolidate(root, package_hash, spec_hash, report, before, after):
    from truth_spine_lineage import require, file_hash, contained
    from truth_spine_contract import seal, verified
    require(before==after and report.get('clean_shutdown') is True and report.get('port_clear') is True and
            report.get('cleanup_errors')==[] and report.get('unresolved_children')==[] and
            all(report.get(k) is True for k in ('rollback','input_preservation','source_preservation')),
            'ACCEPTANCE_PRESERVATION_GATE')
    link=report.get('browser');require(isinstance(link,dict),'PACKAGE_BROWSER_REQUIRED')
    path=contained(root,link['path']);require(file_hash(path)==link['sha256'],'BROWSER_EVIDENCE_PIN_MISMATCH')
    browser=json.loads(path.read_bytes());verified(browser)
    require(browser['fixtureOnly'] is False and browser['result']=='PACKAGE_BROWSER_PASSED' and
            browser['package_hash']==package_hash and browser['contract']==link['contract'] and
            browser['backend_instance_hash']==link['backend_instance_hash'], 'BROWSER_PACKAGE_MISMATCH')
    contract=json.loads((root/'browser/contract.json').read_bytes());verified(contract)
    require(contract['content_hash']==link['contract'] and contract['fixtureOnly'] is False and
            contract['expected']['package_hash']==package_hash and contract['expected']['backend_instance_hash']==link['backend_instance_hash'] and
            contract['toolsHash']==link['tools_hash'],'CONTRACT_PARENT_MISMATCH')
    require(browser['stats']=={'expected':9,'unexpected':0,'skipped':0,'flaky':0} and
            all(type(v) is int for v in browser['stats'].values()) and browser['cleanup']['exitCode']==0 and
            browser['cleanup']['errors']==[] and browser['cleanup']['remaining']==[] and
            browser['cleanup']['listenersStable'] is True,'BROWSER_CLEANUP_OR_TOTALS_INVALID')
    port_link=report.get('port_clear_receipt');require(isinstance(port_link,dict),'STABLE_PORT_RECEIPT_REQUIRED')
    port_path=contained(root,port_link['path']);require(file_hash(port_path)==port_link['sha256'],'PORT_RECEIPT_PIN_MISMATCH')
    port_record=json.loads(port_path.read_bytes())
    require(port_record['schema']=='iios-stable-port-clear-v1' and port_record['package_hash']==package_hash and
            port_record['port']==int(contract['origin'].rsplit(':',1)[1]) and
            port_record['samples']==[{'tcp_clear':True,'listeners':[]}]*2,'PORT_PRESERVATION_GATE')
    for row in browser['files']:
        p=contained(path.parent,row['path'])
        require(p.stat().st_size==row['bytes'] and file_hash(p)==row['sha256'],'BROWSER_ARTIFACT_CHANGED')
    require(file_hash(root/'release/manifest.json')==package_hash and
            file_hash(root/'admission/input-spec.json')==spec_hash,'FINAL_PACKAGE_PIN_MISMATCH')
    from truth_spine_integration import bound_working_capability, event_capability
    from truth_spine_adapters import verify_sqlite_targets
    from truth_spine_lineage import write_new
    from truth_spine_contract import canonical
    t=json.loads((root/'topology.json').read_bytes())
    caps=[bound_working_capability(t,s) for s in t['sources'] if s['kind'] in {'operational','historical'}]
    caps.append(event_capability(t,write=False))
    links=[{'path':str(p),'sha256':file_hash(p)} for p in sorted((root/'admission').glob('sqlite-open-*.json'))]
    verify_sqlite_targets(caps,links)
    telemetry_hash=write_new(root,'receipts/sqlite-targets.json',canonical(seal({
        'schema':'iios-strict-sqlite-target-set-v1','package_hash':package_hash,'opens':links})))
    return seal({'schema':'iios-consolidated-historical-acceptance-v1','result':'GREEN',
                 'scope':'PACKAGE_BACKED_HISTORICAL_ONLY','package_hash':package_hash,'input_spec_hash':spec_hash,
                 'backend_evidence_hash':file_hash(root/'acceptance.json'),'browser_receipt_hash':link['sha256'],
                 'sqlite_target_receipt_hash':telemetry_hash,
                 'baseline_before':file_hash(root/'baselines/before.json'),'baseline_after':file_hash(root/'baselines/after.json'),
                 'owner_scope':'SIX_PINNED_OWNER_FILES','permanent_promotion':False})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True,type=Path);parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--review-seconds',type=int,default=0)
    parser.add_argument('--package-sha256',required=True)
    parser.add_argument('--input-spec-sha256',required=True)
    parser.add_argument('--browser-tools',required=True,type=Path)
    parser.add_argument('--browser-tools-sha256',required=True)
    a=parser.parse_args();root=a.root.resolve()
    if root.parent!=Path('/private/tmp') or not root.name.startswith('iios-truth-spine-3-acceptance-') or a.port in {5176,5177,5184,5185,5186,8002}:raise ValueError('ISOLATED_ROOT_REQUIRED')
    from truth_spine_lineage import require, file_hash, check_pin, write_new
    from truth_spine_contract import canonical
    from truth_spine_integration import topology
    from truth_spine_noninterference import load_baseline, observe
    require(root.name.startswith('iios-truth-spine-3-acceptance-sb38d-clean-'),'NEW_LINEAGE_RUN_REQUIRED')
    require(not (root/'runner-incidents.json').exists() and not (root/'baselines/before.json').exists(),'RUN_ALREADY_ATTEMPTED')
    require(file_hash(root/'release/manifest.json')==a.package_sha256 and
            file_hash(root/'admission/input-spec.json')==a.input_spec_sha256,'INDEPENDENT_RUN_PIN_MISMATCH')
    spec=json.loads((root/'admission/input-spec.json').read_bytes())
    require(spec['port']==a.port and spec['run_root']==str(root),'RUN_CONFIGURATION_MISMATCH')
    from truth_spine_integration import activate_topology_sqlite
    activate_topology_sqlite(json.loads((root/'topology.json').read_bytes()),'acceptance')
    topology(root/'topology.json')
    baseline=load_baseline(root/'admission/baseline-spec.json',spec['baseline']['sha256'])
    browser_tools=verify_browser_tools(a.browser_tools,a.browser_tools_sha256)
    before=observe(baseline,process_inventory=protected_processes,listener_inventory=protected_listeners)
    require(before==json.loads((root/'baselines/before-preparation.json').read_bytes())==
            json.loads((root/'baselines/after-preparation.json').read_bytes()),'PREPARATION_BASELINE_MISMATCH')
    write_new(root,'baselines/before.json',canonical(before))
    t=json.loads((root/'topology.json').read_bytes());backend=root/'release/backend';python=root/'runtime/bin/python'
    env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(backend),'PYTHONUNBUFFERED':'1'}
    def port_clear():
        value=stable_port_clear(a.port)
        value['package_hash']=a.package_sha256
        name='receipts/port-clear-'+str(len(port_checks))+'.json'
        expected=write_new(root,name,canonical(value))
        port_checks.append({'path':name,'sha256':expected})
        report['port_clear_receipt']=port_checks[-1]
        return True
    port_checks=[]
    children=OwnedChildren(root,port_clear=port_clear)
    report={'readiness_transitions':[], 'duplicate_owner_tests':[], 'requires_package_browser':True}
    command=[str(python),'-B','-m','truth_spine_integration_service','--config',str(root/'topology.json'),'--strict-lineage']
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
        from truth_spine_integration import connect_event
        db=connect_event(t)
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
        p=root/'working-inputs/owner/l7/snapshot.db';restored=root/'rollback/operational.db'
        from truth_spine_lineage import copy_pinned
        copy_pinned({'path':str(p),'sha256':file_hash(p),'bytes':p.stat().st_size,'mode':0o400},root,'rollback/operational.db')
        report['rollback']=hashlib.sha256(p.read_bytes()).hexdigest()==hashlib.sha256(restored.read_bytes()).hexdigest()
        preservation=json.loads((root/'preservation.json').read_bytes());report['input_preservation']=all(hashlib.sha256((root/name).read_bytes()).hexdigest()==h for name,h in preservation['input_hashes'].items())
        report['source_preservation']=bool(preservation['source_files']) and all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==h for name,h in preservation['source_files'].items())
        if not all(report[k] for k in ['rollback','input_preservation','source_preservation']):raise ValueError('PRESERVATION_FAILED')
        report['browser']=run_package_browser(root,a.package_sha256,spec,browser_tools,children)
        report['result']='BACKEND_GREEN_BROWSER_SEPARATE';print(json.dumps(report),flush=True)
        # Read-only browser work occurs during this bounded interval; cleanup remains automatic.
        until=time.monotonic()+min(max(a.review_seconds,0),600)
        while time.monotonic()<until:time.sleep(1)
    except BaseException as exc:
        primary=exc
    finally:
        children.cleanup(report,primary)
        print(json.dumps(report),flush=True)
    if primary is not None or not report['clean_shutdown']:return 1
    after=observe(baseline,process_inventory=protected_processes,listener_inventory=protected_listeners)
    require(before==after,'NONINTERFERENCE_FAILED')
    write_new(root,'baselines/after.json',canonical(after))
    for pin in spec['owner_files'].values():check_pin(pin)
    consolidated=consolidate(root,a.package_sha256,a.input_spec_sha256,report,before,after)
    write_new(root,'consolidated-acceptance.json',canonical(consolidated))
    return 0


if __name__=='__main__':sys.exit(main())
