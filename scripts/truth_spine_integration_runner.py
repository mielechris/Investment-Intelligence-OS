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


ROLES = ('scheduler', 'publisher', 'backend')


class RunnerFailure(RuntimeError):
    """Only fixed runner categories are reported, never exception messages."""


@dataclass(frozen=True)
class ProcessObservation:
    pid: int
    parent_pid: int
    start_time: str
    command: str
    executable: str
    executable_hash: str
    cwd: str


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


def inspect_macos(pid: int) -> ProcessObservation | None:
    """Bounded OS inspection; no shell, environment dump or process signals.

    ps start time is OS-observed, not the runner creation timestamp. Command,
    parent, executable bytes and cwd are independent additional bindings.
    Inspection failures are not interpreted as permission to terminate.
    """
    env = {'PATH': '/usr/bin:/bin:/usr/sbin', 'LC_ALL': 'C', 'TZ': 'UTC'}

    def read(argv):
        r = subprocess.run(argv, capture_output=True, text=True, timeout=3, env=env)
        if len(r.stdout) > 65536:
            raise RunnerFailure('PROCESS_INSPECTION_OVERSIZE')
        return r.returncode, r.stdout.strip()

    code, stamp = read(['/bin/ps', '-ww', '-p', str(pid), '-o', 'lstart='])
    if code == 1 and not stamp:
        return None
    if code != 0 or not stamp:
        raise RunnerFailure('PROCESS_INSPECTION_FAILED')
    values = []
    for field in ('ppid=', 'command=', 'comm='):
        code, value = read(['/bin/ps', '-ww', '-p', str(pid), '-o', field])
        if code != 0 or not value:
            raise RunnerFailure('PROCESS_INSPECTION_FAILED')
        values.append(value)
    code, paths = read(['/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'])
    cwd = [line[1:] for line in paths.splitlines() if line.startswith('n')]
    executable = Path(values[2])
    if code != 0 or len(cwd) != 1 or not executable.is_absolute():
        raise RunnerFailure('PROCESS_INSPECTION_FAILED')
    return ProcessObservation(pid, int(values[0]), stamp, values[1], str(executable),
                              hashlib.sha256(executable.read_bytes()).hexdigest(), cwd[0])


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
                 port_clear=None, timeout=30, parent_pid=None):
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

    def error(self, category, role=None, error=None):
        row = {'category': category, 'role': role}
        if error is not None:
            row['exception_type'] = type(error).__name__
        self.errors.append(row)

    def register(self, role, child, argv, cwd, port=None, *, executable_hashes,
                 registry_key=None):
        key = role if registry_key is None else registry_key
        if role not in ROLES or key in self.active:
            raise RunnerFailure('CHILD_ROLE_ALREADY_TRACKED')
        entry = {'child': child, 'fingerprint': None, 'role': role}
        self.active[key] = entry  # Never lose a live child on failed verification.
        try:
            o = self.inspector(child.pid)
            if (o is None or o.pid != child.pid or o.parent_pid != self.parent_pid
                    or not o.start_time or o.cwd != str(cwd)
                    or Path(cwd) != self.root/'release/backend'
                    or '--config' not in argv or argv[argv.index('--config')+1] != str(self.root/'topology.json')
                    or '--role' not in argv or argv[argv.index('--role')+1] != role):
                raise RunnerFailure('PROCESS_IDENTITY_MISMATCH')
            hashes = executable_hashes
            # macOS Python may report the verified framework executable instead
            # of the venv launcher. Only manifest-pinned aliases are accepted.
            commands = {' '.join((exe, *argv[1:])) for exe in hashes}
            if (o.command not in commands or o.executable not in hashes
                    or hashes[o.executable] != o.executable_hash
                    or (role == 'backend' and ('--port' not in argv or int(argv[argv.index('--port')+1]) != port))):
                raise RunnerFailure('PROCESS_IDENTITY_MISMATCH')
            fp = ProcessFingerprint(role, o, tuple(argv), str(cwd), str(self.root), port,
                                    datetime.now(timezone.utc).isoformat(), self.identity)
            entry['fingerprint'] = fp
            self.fingerprints.append(asdict(fp))
            self.verify(entry)
            return fp
        except BaseException as exc:
            self.error('PROCESS_IDENTITY_MISMATCH', role, exc)
            raise RunnerFailure('PROCESS_IDENTITY_MISMATCH') from None

    def verify(self, entry):
        fp = entry['fingerprint']
        o = self.inspector(entry['child'].pid)
        valid = (fp is not None and o == fp.observed and fp.role == entry['role']
                 and fp.runner_identity == self.identity and fp.shadow_root == str(self.root)
                 and fp.expected_cwd == str(self.root/'release/backend'))
        self.attempts.append({'role': entry['role'], 'action': 'VERIFY', 'matched': valid})
        if not valid:
            raise RunnerFailure('PROCESS_IDENTITY_MISMATCH')
        return fp

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
                      completed_processes=self.completed, stop_attempts=self.attempts,
                      cleanup_errors=self.errors, unresolved_children=[
                          {'role': r, 'pid': e['child'].pid, 'fingerprint':
                           asdict(e['fingerprint']) if e['fingerprint'] else None}
                          for r, e in self.active.items()], log_closure=self.log_results,
                      port_clear=clear)
        report['clean_shutdown'] = not self.active and clear and not self.errors
        report['result'] = 'GREEN' if report['clean_shutdown'] and primary is None else 'RED'
        persistence_failed = False
        for name in ('runner-incidents.json', 'acceptance.json'):
            try:
                self.writer(self.root, name, report)
            except BaseException as exc:
                self.error('ACCEPTANCE_PERSISTENCE_FAILED', error=exc)
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
        self.finished = report
        return report


def get(port,path):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=60) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())


def rejected_duplicate(role, owner, argv, *, spawn, counts, lock_bytes,
                       executable_hashes, port=None, timeout=5):
    """A rejected contender is never an accepted owner. Never blindly kill it.

    Fast rejected children may exit before an OS fingerprint can be captured:
    Popen.wait then proves the exact child exited, and no signal is issued.
    A contender which does not exit is returned for identity-safe cleanup.
    """
    before = counts()
    lock = lock_bytes(role)
    owner.verify(owner.active[role])
    child = spawn(argv)
    key = 'duplicate-'+role
    # Fast rejected/reaped contenders are not accepted owners and are never
    # signaled. A still-live contender receives the same identity contract.
    if child.poll() is None:
        owner.register(role, child, argv, owner.root/'release/backend', port,
                       executable_hashes=executable_hashes, registry_key=key)
    try:
        code = child.wait(timeout=timeout)
    except BaseException:
        raise RunnerFailure('DUPLICATE_DID_NOT_EXIT') from None
    if key in owner.active and not owner.stop(key):
        raise RunnerFailure('DUPLICATE_EXIT_NOT_CONFIRMED')
    owner.verify(owner.active[role])
    if code == 0 or counts() != before or lock_bytes(role) != lock:
        raise RunnerFailure('DUPLICATE_OWNER_ACCEPTED_OR_DISTURBED')
    return {'role': role, 'pid': child.pid, 'argv': list(argv), 'returncode': code,
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
        argv=command+['--role',role,'--port',str(a.port)]
        p=subprocess.Popen(argv,cwd=backend,env=env,stdout=f,stderr=f)
        children.register(role,p,argv,backend,a.port if role=='backend' else None,
                          executable_hashes=executable_hashes)
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
                command+['--role',role,'--port',str(a.port)],spawn=contender,
                counts=count,lock_bytes=lock_bytes,executable_hashes=executable_hashes,
                port=a.port if role=='backend' else None))
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
