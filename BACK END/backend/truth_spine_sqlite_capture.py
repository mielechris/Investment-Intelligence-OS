"""One-shot Seatbelt-confined SQLite acquisition; no implicit operational paths.

This module is deliberately stdlib-only so the capture process need not read
the repository, a user home, credentials, or an operational runtime tree.
The launcher pins the exact profile in argv, independently observes the child,
and admits a snapshot only after exit and independent immutable verification.
No retry, raw-copy fallback, source cleanup, or authority is provided here.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
import platform
from pathlib import Path
import select
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid
import re


SCHEMA = 'iios-os-isolated-sqlite-capture-v1'
SANDBOX = Path('/usr/bin/sandbox-exec')
ENVIRONMENT = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}


def source_metadata(path):
    """Metadata-only source observation; never opens the ledger."""
    info = path.lstat()
    return {'device': info.st_dev, 'inode': info.st_ino,
            'owner_uid': info.st_uid, 'mode': stat.S_IMODE(info.st_mode),
            'file_type': stat.S_IFMT(info.st_mode), 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns}


class CaptureAttempt:
    """Durable parent-owned evidence outside the disposable output lifetime."""
    def __init__(self, evidence_root, source, output, source_role=None):
        path_identity(evidence_root, directory=True)
        if (stat.S_IMODE(evidence_root.stat().st_mode) != 0o700 or
                evidence_root.is_relative_to(output) or output.is_relative_to(evidence_root) or
                evidence_root.is_relative_to(source.parent)):
            raise ValueError('INDEPENDENT_OWNER_ONLY_EVIDENCE_REQUIRED')
        self.identity = 'capture-attempt-'+uuid.uuid4().hex
        self.root = evidence_root/self.identity
        self.root.mkdir(mode=0o700); fsync_dir(evidence_root)
        self.source_role = source_role or "UNKNOWN"
        self.aliases = {str(source.parent): '{SOURCE_PARENT}', str(source): '{SOURCE}',
                        str(output): '{OUTPUT}', str(evidence_root): '{EVIDENCE}'}
        self.value = {'schema': 'iios-capture-attempt-v1', 'attempt': self.identity,
            'start_utc': datetime.now(timezone.utc).isoformat(), 'start_monotonic': time.monotonic(),
            'source_alias': '{SOURCE}', 'destination_alias': '{OUTPUT}',
            'source_role': self.source_role,
            'environment': dict(ENVIRONMENT), 'mechanism': 'macOS_Seatbelt', 'pid': None,
            'source_metadata_before': source_metadata(source),
            'source_companions_before': companion_metadata(source),
            'original_failure': None, 'cleanup_errors': [], 'readiness': [], 'stdout': '', 'stderr': ''}
        # If durable evidence cannot be created, no subprocess may be launched.
        write_new(self.root/'started.json', encoded(sealed(self.value)))

    def sanitized(self, value):
        if isinstance(value, bytes): value = value.decode('utf-8', errors='backslashreplace')
        if isinstance(value, str):
            for raw, alias in sorted(self.aliases.items(), key=lambda item: -len(item[0])):
                value = value.replace(raw, alias)
            value = re.sub(r'/(?:Users|private|home)/[^\s"\)\n]+', '{PRIVATE_PATH}', value)
            return value
        if isinstance(value, dict): return {k: self.sanitized(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)): return [self.sanitized(v) for v in value]
        return value

    def failure(self, error):
        return {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
                'category': self.sanitized(str(error))[:2048]}

    def finish(self, error):
        self.value['original_failure'] = self.failure(error) if error else None
        self.value.update(end_utc=datetime.now(timezone.utc).isoformat(), end_monotonic=time.monotonic())
        record = sealed(self.sanitized(self.value))
        write_new(self.root/'incident.json', encoded(record))
        if checked(json.loads((self.root/'incident.json').read_bytes())) != record:
            raise ValueError('DURABLE_INCIDENT_VERIFICATION_FAILED')
        return record


class CapturePipes:
    """Bounded concurrent drains; decoding failures cannot erase startup evidence."""
    def __init__(self, process):
        self.data = {'stdout': bytearray(), 'stderr': bytearray()}
        self.errors = []; self.ready = threading.Event(); self.overflow = False
        self.lock = threading.Lock(); self.threads = []
        for name in self.data:
            thread = threading.Thread(target=self.drain, args=(name, getattr(process, name)), daemon=True)
            self.threads.append(thread); thread.start()

    def drain(self, name, stream):
        try:
            while True:
                chunk = os.read(stream.fileno(), 4096)
                if not chunk: break
                with self.lock:
                    remaining = 65536-len(self.data[name])
                    self.data[name].extend(chunk[:remaining])
                    if len(chunk) > remaining: self.overflow = True
                    if name == 'stdout' and b'\n' in self.data[name]: self.ready.set()
        except BaseException as error:
            self.errors.append(type(error).__name__)
        finally:
            if name == 'stdout': self.ready.set()

    def collect(self, attempt):
        for thread in self.threads: thread.join(timeout=2)
        attempt.value.update({name: bytes(data) for name, data in self.data.items()})
        attempt.value['pipe_errors'] = list(self.errors)
        attempt.value['pipe_overflow'] = self.overflow
        if any(t.is_alive() for t in self.threads):
            raise RuntimeError('CAPTURE_PIPE_CLEANUP_UNRESOLVED')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def sealed(value):
    return {**value, 'content_hash': sha(encoded(value))}


def checked(value):
    if value != sealed({k: v for k, v in value.items() if k != 'content_hash'}):
        raise ValueError('CAPTURE_HASH_INVALID')
    return value


def path_identity(path, *, directory=False):
    if (not path.is_absolute() or path != path.resolve() or
            any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError('CAPTURE_PATH_INVALID')
    info = path.lstat()
    if (info.st_uid != os.getuid() or not
            (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError('CAPTURE_OWNER_OR_TYPE_INVALID')
    return {'device': info.st_dev, 'inode': info.st_ino}


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, data, mode=0o600):
    path_identity(path.parent, directory=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    fsync_dir(path.parent)


def profile(source, output, executable, helper, runtime):
    """Fixed policy, never a caller-supplied profile or broader write allowlist.

    Runtime reads are allowed so the pinned interpreter can load its signed
    framework libraries. Writes remain denied everywhere except the exact output
    and the two source-side WAL/SHM coordination paths. Keychain reads, Mach
    lookup (including securityd), networking, external exec and POSIX shared-
    memory access are denied. Filesystem SHM used by SQLite is governed by the
    same exact-path rule.
    """
    q = lambda p: json.dumps(str(p), ensure_ascii=True)
    return ('(version 1)\n(allow default)\n'
            '(deny file-write*)\n'
            '(deny file-read-data (subpath "/Library/Keychains")'
            ' (subpath "/Users/crm/Library/Keychains")'
            ' (literal '+q(source.parent/'credential-fixture.dat')+')'
            ' (literal "/Library/Keychains/System.keychain"))\n'
            '(deny network*)\n'
            '(deny mach-lookup)\n(deny ipc-posix-shm*)\n(deny process-exec)\n'
            '(allow process-exec (literal '+q(executable)+'))\n'
            # SQLite may coordinate a read transaction only through the two
            # exact companions belonging to this source.  The main database,
            # journals, sibling names and every other path remain denied.
            '(allow file-write* (literal '+q(Path(str(source)+'-wal'))+') '
            '(literal '+q(Path(str(source)+'-shm'))+') (subpath '+q(output)+'))\n')


def companion_metadata(source):
    """Return metadata-only observations for SQLite's exact WAL/SHM paths."""
    result = {}
    for suffix in ('-wal', '-shm'):
        path = Path(str(source) + suffix)
        try:
            info = path.lstat()
        except FileNotFoundError:
            result[suffix] = {'exists': False}
            continue
        result[suffix] = {
            'exists': True,
            'file_type': stat.S_IFMT(info.st_mode),
            'mode': stat.S_IMODE(info.st_mode),
            'owner_uid': info.st_uid,
            'device': info.st_dev,
            'inode': info.st_ino,
            'size': info.st_size,
            'mtime_ns': info.st_mtime_ns,
        }
    return result


def coordination_profile_attestation(source, output, policy):
    """Statically attest the narrowly scoped source-side write capability.

    ``sandbox_check`` cannot distinguish an absent, but permitted, WAL/SHM
    path from a denied path on macOS.  The generated profile is therefore
    checked as data: it must deny writes globally and contain exactly the two
    source-specific companion literals plus the isolated destination subtree.
    The actual sandboxed SQLite transaction remains the runtime proof.
    """
    source, output = Path(source), Path(output)
    wal = json.dumps(str(Path(str(source) + '-wal')), ensure_ascii=True)
    shm = json.dumps(str(Path(str(source) + '-shm')), ensure_ascii=True)
    destination = json.dumps(str(output), ensure_ascii=True)
    required = [
        '(deny file-write*)',
        '(allow file-write* (literal ' + wal + ') (literal ' + shm +
        ') (subpath ' + destination + '))',
    ]
    if any(policy.count(fragment) != 1 for fragment in required):
        raise PermissionError('OS_CAPTURE_COORDINATION_PROFILE_INVALID')
    # No source-parent, home, wildcard, journal, rename, unlink or metadata
    # write allowance may be smuggled into the generated profile.
    forbidden = [
        '(allow file-write* (subpath ' + json.dumps(str(source.parent), ensure_ascii=True),
        '(allow file-write* (literal ' + json.dumps(str(source), ensure_ascii=True),
        '(allow file-write* (literal ' + json.dumps(str(Path(str(source) + '-journal')), ensure_ascii=True),
        'file-write-unlink', 'file-write-mode', 'file-write-owner',
        'file-write-flags', 'file-write-xattr', 'file-write-security',
    ]
    if any(token in policy for token in forbidden):
        raise PermissionError('OS_CAPTURE_COORDINATION_PROFILE_BROADENED')
    allowed_clause = required[1]
    if policy.count('(allow file-write*') != 1 or policy.count(allowed_clause) != 1:
        raise PermissionError('OS_CAPTURE_COORDINATION_PROFILE_AMBIGUOUS')
    return {
        'method': 'PROFILE_EXACT_LITERALS_AND_SQLITE_SEQUENCE',
        'allowed_suffixes': ['-wal', '-shm'],
        'destination': '{OUTPUT}',
        'main_database_writes': False,
        'rollback_journal': False,
        'source_parent_writes': False,
        'unrelated_writes': False,
    }


def sqlite_runtime_metadata():
    """Describe the pinned runtime without touching either source ledger."""
    db = sqlite3.connect(':memory:')
    try:
        options = [row[0] for row in db.execute('PRAGMA compile_options').fetchall()]
    finally:
        db.close()
    return {
        'python': platform.python_version(),
        'python_implementation': platform.python_implementation(),
        'sqlite_module_version': getattr(sqlite3, 'version', None),
        'sqlite_runtime_version': sqlite3.sqlite_version,
        'compile_options': options,
    }


def kernel_denials(job):
    """Query this process's kernel policy, without touching a credential value."""
    lib = ctypes.CDLL('/usr/lib/libsandbox.dylib', use_errno=True)
    lib.sandbox_check.restype = ctypes.c_int
    source, output = Path(job['source']), Path(job['output'])
    policy = profile(source, output, Path(job['executable']), Path(job['helper']), Path(job['runtime']))
    coordination = coordination_profile_attestation(source, output, policy)
    checks = {}
    for name, operation, target in (
        ('database_write', 'file-write-data', source),
        ('parent_create', 'file-write-create', source.parent/'capture-forbidden'),
        ('source_unlink', 'file-write-unlink', source),
        ('source_metadata', 'file-write-mode', source),
        ('outside_output', 'file-write-create', output.parent/'capture-forbidden'),
        ('credential_read', 'file-read-data', Path('/Library/Keychains/System.keychain')),
    ):
        # SANDBOX_FILTER_PATH=1; only a permission query, never open/read.
        result = lib.sandbox_check(os.getpid(), operation.encode(), 1, str(target).encode())
        # sandbox_check returns 0 when permitted and a non-zero value (on
        # macOS this is -1) when denied. Treat every non-zero result as the
        # required denial; never assume a particular errno representation.
        checks[name] = result != 0
    checks['network'] = lib.sandbox_check(os.getpid(), b'network-outbound', 0) != 0
    required_denials = list(checks)
    if not all(checks[name] for name in required_denials):
        missing = ','.join(sorted(name for name in required_denials if not checks[name]))
        raise PermissionError('OS_CAPTURE_POLICY_NOT_ENFORCED:'+missing)
    checks['coordination_profile'] = coordination
    return checks


def validate_job(job):
    checked(job)
    required = {'schema', 'source', 'source_identity', 'output', 'output_identity',
                'executable', 'executable_sha256', 'helper', 'helper_sha256',
                'runtime', 'profile_sha256', 'sandbox_sha256', 'timeout', 'probe', 'content_hash'}
    required.add('source_role')
    if (set(job) != required or job['schema'] != SCHEMA or
            job['source_role'] not in {'L7', 'L8', 'L7_OPERATIONAL', 'L8_HISTORICAL', 'DISPOSABLE'} or
            type(job['probe']) is not bool
            or not 1 <= job['timeout'] <= 120):
        raise ValueError('CAPTURE_JOB_INVALID')
    source, output = Path(job['source']), Path(job['output'])
    if source.is_relative_to(output) or output.is_relative_to(source.parent):
        raise ValueError('CAPTURE_SOURCE_OUTPUT_OVERLAP')
    if (path_identity(source) != job['source_identity'] or
            path_identity(output, directory=True) != job['output_identity']):
        raise ValueError('CAPTURE_PATH_REPLACED')
    if stat.S_IMODE(output.stat().st_mode) != 0o700:
        raise ValueError('CAPTURE_OUTPUT_MODE_INVALID')
    for kind in ('executable', 'helper'):
        p = Path(job[kind])
        if p.is_symlink() or not p.is_file() or sha(p.read_bytes()) != job[kind+'_sha256']:
            raise ValueError('CAPTURE_EXECUTABLE_CHANGED')
    if Path(job['helper']) != Path(__file__).resolve():
        raise ValueError('CAPTURE_EXECUTABLE_BINDING')
    expected = profile(source, output, Path(job['executable']), Path(job['helper']), Path(job['runtime']))
    if sha(expected.encode()) != job['profile_sha256']:
        raise ValueError('CAPTURE_PROFILE_CHANGED')
    return expected


def negative_proof(job):
    """Only called for explicit disposable qualification, never live capture."""
    source, output = Path(job['source']), Path(job['output'])
    results = {}
    def deny(name, operation):
        try:
            result = operation()
        except OSError as error:
            if error.errno not in (errno.EPERM, errno.EACCES):
                raise
            results[name] = {'denied': True, 'errno': error.errno}
        else:
            if isinstance(result, int): os.close(result)
            raise PermissionError('NEGATIVE_CAPABILITY_FAILED:'+name)
    deny('open_wronly', lambda: os.open(source, os.O_WRONLY))
    deny('open_rdwr', lambda: os.open(source, os.O_RDWR))
    # Exact WAL/SHM coordination is the sole source-side write capability.
    for suffix in ('-wal', '-shm'):
        p = Path(str(source)+suffix)
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except OSError as error:
            raise PermissionError('NEGATIVE_CAPABILITY_MISSING:'+suffix) from error
        results['coordinate'+suffix] = {'allowed': True, 'path': suffix}
        if p.exists():
            with p.open('rb') as f: f.read(1)
            results['read'+suffix] = True
    deny('rollback_journal', lambda: os.open(Path(str(source)+'-journal'), os.O_WRONLY | os.O_CREAT, 0o600))
    deny('truncate', lambda: os.truncate(source, 0))
    deny('rename', lambda: os.rename(source, output/'renamed-source'))
    deny('unlink', lambda: os.unlink(source))
    deny('chmod', lambda: os.chmod(source, 0o777))
    deny('parent_create', lambda: os.open(source.parent/'forbidden', os.O_CREAT | os.O_WRONLY, 0o600))
    deny('outside_create', lambda: os.open(output.parent/'forbidden', os.O_CREAT | os.O_WRONLY, 0o600))
    # Reserved documentation address: OS denial occurs before any transmission.
    with socket.socket() as connection:
        connection.settimeout(0.2)
        deny('network_connect', lambda: connection.connect(('192.0.2.1', 443)))
    # Synthetic Keychain fixture only. No real credential store is opened.
    deny('credential_fixture', lambda: os.open(source.parent/'credential-fixture.dat', os.O_RDONLY))
    with source.open('rb') as f: results['read_database'] = bool(f.read(16))
    write_new(output/'proof-write', b'OUTPUT_ONLY\n')
    write_new(output/'proof-log', b'NO_SECRET\n')
    results['destination_write'] = True
    link = output/'escape'
    link.symlink_to(source.parent)
    deny('symlink_escape', lambda: os.open(link/'forbidden', os.O_CREAT | os.O_WRONLY, 0o600))
    deny('traversal_escape', lambda: os.open(output/'..'/'forbidden', os.O_CREAT | os.O_WRONLY, 0o600))
    # fork inherits the same kernel policy; no interpreter/script escape.
    child = os.fork()
    if child == 0:
        try:
            kernel_denials(job)
            os.open(source, os.O_RDWR)
        except PermissionError:
            os._exit(0)
        except BaseException:
            os._exit(3)
        os._exit(2)
    _, status = os.waitpid(child, 0)
    if status != 0: raise PermissionError('CHILD_SANDBOX_ESCAPE')
    results['child_inherits_denials'] = True
    return results


def capture_transaction(job, deadline):
    source, output = Path(job['source']), Path(job['output'])
    target = output/'snapshot.incomplete.db'
    def check(*_):
        if time.monotonic() >= deadline: raise TimeoutError('CAPTURE_DEADLINE')
        if path_identity(source) != job['source_identity']:
            raise ValueError('SOURCE_REPLACED_DURING_CAPTURE')
    live = copy = None
    try:
        check()
        live = sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, isolation_level=None, timeout=0.25)
        live.execute('PRAGMA query_only=ON')
        if live.execute('PRAGMA query_only').fetchone() != (1,):
            raise PermissionError('QUERY_ONLY_REQUIRED')
        live.execute('BEGIN')
        live.execute('SELECT count(*) FROM sqlite_schema').fetchone()
        check()
        if Path(live.execute('PRAGMA database_list').fetchone()[2]).resolve() != source:
            raise ValueError('DATABASE_BINDING_INVALID')
        write_new(target, b'')
        copy = sqlite3.connect(target)
        live.backup(copy, pages=256, progress=check, sleep=0.025)
        quick = copy.execute('PRAGMA quick_check').fetchall()
        integrity = copy.execute('PRAGMA integrity_check').fetchall()
        foreign_keys = copy.execute('PRAGMA foreign_key_check').fetchall()
        if quick != [('ok',)] or integrity != [('ok',)] or foreign_keys:
            raise ValueError('SNAPSHOT_INTEGRITY_INVALID')
        schema = copy.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
        check()
        return {'quick_check': 'ok', 'integrity_check': 'ok', 'foreign_key_violations': 0,
                'schema_sha256': sha(encoded(schema))}
    finally:
        if copy is not None: copy.close()
        if live is not None:
            try: live.rollback()
            finally: live.close()


def worker(job, pin):
    os.umask(0o077)
    if sha(encoded(job)) != pin: raise ValueError('CAPTURE_JOB_PIN_INVALID')
    validate_job(job)
    if Path(job['executable']) != Path(sys.executable).resolve():
        raise ValueError('CAPTURE_RUNNING_EXECUTABLE_INVALID')
    output = Path(job['output'])
    runtime = sqlite_runtime_metadata()
    started = datetime.now(timezone.utc).isoformat()

    def persist_failure(error):
        """Persist one sanitized preflight/runtime failure before re-raising."""
        record = sealed({'schema': SCHEMA, 'status': 'FAILED_CLOSED',
            'job': pin, 'source_role': job['source_role'],
            'error_type': type(error).__name__,
            'sqlite_code': getattr(error, 'sqlite_errorcode', None),
            'coordination': {'before': companion_metadata(Path(job['source'])),
                             'after': companion_metadata(Path(job['source']))},
            'runtime': runtime, 'start': started,
            'end': datetime.now(timezone.utc).isoformat()})
        write_new(output/'failure.json', encoded(record))
        return record

    try:
        # Before any source DB handle or success receipt.  Static profile
        # attestation replaces unreliable sandbox_check queries for absent
        # WAL/SHM paths; SQLite itself proves the allowed capability later.
        policy = kernel_denials(job)
    except BaseException as error:
        persist_failure(error)
        raise
    print(json.dumps({'stage': 'OS_ENFORCED', 'pid': os.getpid(), 'job': pin}), flush=True)
    if not select.select([sys.stdin], [], [], 10)[0]: raise TimeoutError('PARENT_BINDING_TIMEOUT')
    parent = checked(json.loads(sys.stdin.readline(65536)))
    if parent['pid'] != os.getpid() or parent['parent_pid'] != os.getppid() or parent['job'] != pin:
        raise ValueError('CAPTURE_PARENT_BINDING_INVALID')
    write_new(output/'startup.json', encoded(sealed({'schema': SCHEMA, 'policy_denials': policy, 'process': parent})))
    try:
        if job['probe']:
            result = {'negative_capabilities': negative_proof(job)}
        else:
            coordination_before = companion_metadata(Path(job['source']))
            result = capture_transaction(job, time.monotonic()+job['timeout'])
            result['coordination'] = {'before': coordination_before,
                                      'after': companion_metadata(Path(job['source']))}
            target = output/'snapshot.incomplete.db'
            with target.open('rb') as stream: os.fsync(stream.fileno())
            target.chmod(0o400)
            os.rename(target, output/'snapshot.db'); fsync_dir(output)
            result.update(snapshot_sha256=sha((output/'snapshot.db').read_bytes()), bytes=(output/'snapshot.db').stat().st_size)
        validate_job(job)
        write_new(output/'receipt.json', encoded(sealed({'schema': SCHEMA, 'status': 'VERIFIED',
            'job': pin, 'start': started, 'end': datetime.now(timezone.utc).isoformat(), **result})))
        return 0
    except BaseException as error:
        # Bounded sanitized diagnostics; never exception text, SQL, raw rows or paths.
        write_new(output/'failure.json', encoded(sealed({'schema': SCHEMA, 'status': 'FAILED_CLOSED',
            'job': pin, 'source_role': job['source_role'],
            'error_type': type(error).__name__, 'sqlite_code': getattr(error, 'sqlite_errorcode', None),
            'coordination': {'before': companion_metadata(Path(job['source'])),
                             'after': companion_metadata(Path(job['source']))},
            'runtime': runtime, 'start': started, 'end': datetime.now(timezone.utc).isoformat()})))
        raise


def launch_capture(source, output, *, evidence_root, timeout=120, probe=False,
                   source_role='DISPOSABLE',
                   on_child_started=None):
    """Create exactly one output directory and one OS-confined child, no retry."""
    attempt = CaptureAttempt(evidence_root, source, output, source_role)
    error = None
    try:
        return _launch_capture(source, output, attempt, timeout=timeout, probe=probe,
                               source_role=source_role,
                               on_child_started=on_child_started)
    except BaseException as exc:
        error = exc
        raise
    finally:
        try:
            attempt.finish(error)
        except BaseException as persistence_error:
            if error is None: raise
            # The original failure remains primary even when evidence storage
            # itself fails. No success/installation can follow either failure.
            error.add_note('INCIDENT_PERSISTENCE_FAILED:'+type(persistence_error).__name__)


def _launch_capture(source, output, attempt, *, timeout, probe, source_role,
                    on_child_started=None):
    if sys.platform != 'darwin' or not SANDBOX.is_file():
        raise PermissionError('OS_CAPTURE_ISOLATION_UNAVAILABLE')
    if not 1 <= timeout <= 120 or type(probe) is not bool:
        raise ValueError('CAPTURE_ARGUMENT_INVALID')
    source_id = path_identity(source)
    path_identity(output.parent, directory=True)
    if output.exists() or output.is_symlink() or output != output.resolve() or output.is_relative_to(source.parent):
        raise ValueError('NEW_SEPARATE_CAPTURE_OUTPUT_REQUIRED')
    helper = Path(__file__).resolve()
    attempt.aliases[str(helper)] = '{HELPER}'
    runtime = Path(sys.base_prefix).resolve()
    if runtime != Path('/Library/Frameworks/Python.framework/Versions/3.14'):
        raise ValueError('PINNED_PYTHON_314_REQUIRED')
    executable = runtime/'Resources/Python.app/Contents/MacOS/Python'
    attempt.value['executable_sha256'] = sha(executable.read_bytes())
    attempt.value['executable'] = str(executable)
    os.umask(0o077); output.mkdir(mode=0o700); fsync_dir(output.parent)
    policy = profile(source, output, executable, helper, runtime)
    job = sealed({'schema': SCHEMA, 'source': str(source), 'source_identity': source_id,
        'output': str(output), 'output_identity': path_identity(output, directory=True),
        'executable': str(executable), 'executable_sha256': sha(executable.read_bytes()),
        'helper': str(helper), 'helper_sha256': sha(helper.read_bytes()), 'runtime': str(runtime),
        'profile_sha256': sha(policy.encode()), 'sandbox_sha256': sha(SANDBOX.read_bytes()),
        'timeout': timeout, 'probe': probe, 'source_role': source_role})
    pin = sha(encoded(job))
    write_new(output/'job.json', encoded(job), 0o400)
    write_new(output/'profile.sb', policy.encode(), 0o400)
    argv = [str(SANDBOX), '-p', policy, str(executable), '-I', '-B', str(helper), '--job', str(output/'job.json'), '--pin', pin]
    from truth_spine_process_identity import inspect_macos
    attempt.value.update(profile_sha256=job['profile_sha256'], profile=policy, job=job,
                         argv_sha256=sha(encoded(argv)), sanitized_argv_sha256=sha(encoded(attempt.sanitized(argv))),
                         cwd_identity=job['output_identity'], cwd='{OUTPUT}', sandbox_sha256=job['sandbox_sha256'])
    write_new(attempt.root/'launch.json', encoded(sealed(attempt.sanitized(attempt.value))))
    process = None; admitted = None; pipes = None; original = None
    try:
        if ENVIRONMENT != {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}:
            raise ValueError('CAPTURE_ENVIRONMENT_INVALID')
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=output, env=dict(ENVIRONMENT))
        attempt.value.update(pid=process.pid, parent_pid=os.getpid())
        pipes = CapturePipes(process)
        if not pipes.ready.wait(10): raise TimeoutError('CAPTURE_START_TIMEOUT')
        first = bytes(pipes.data['stdout']).split(b'\n', 1)[0]
        if not first: raise RuntimeError('CAPTURE_START_FAILED')
        ready = json.loads(first)
        attempt.value['readiness'].append(ready)
        observed = inspect_macos(process.pid)
        expected_argv = tuple(argv[3:])
        if (observed is None or ready != {'stage': 'OS_ENFORCED', 'pid': process.pid, 'job': pin}
                or observed.parent_pid != os.getpid() or observed.argv != expected_argv
                or observed.executable_hash != job['executable_sha256'] or observed.cwd != str(output)):
            raise ValueError('CAPTURE_PROCESS_IDENTITY_INVALID')
        admitted = observed
        parent = sealed({'pid': observed.pid, 'parent_pid': observed.parent_pid, 'start_time': observed.start_time,
            'argv_sha256': sha(encoded(list(observed.argv))), 'executable_sha256': observed.executable_hash,
            'profile_sha256': job['profile_sha256'], 'job': pin})
        attempt.value['process'] = parent
        process.stdin.write(encoded(parent)); process.stdin.flush()
        if on_child_started is not None:
            # Parent-only test hook: production callers leave this unset.  It
            # lets disposable-process tests exercise interruption after the
            # child has passed identity admission without weakening teardown.
            on_child_started(process.pid, output)
        process.wait(timeout=timeout+15)
        if process.returncode != 0: raise RuntimeError('CAPTURE_CHILD_FAILED_CLOSED')
        if pipes.overflow or pipes.errors: raise RuntimeError('CAPTURE_OUTPUT_INVALID')
        validate_job(job)
        receipt = checked(json.loads((output/'receipt.json').read_bytes()))
        if receipt['job'] != pin or receipt['status'] != 'VERIFIED':
            raise ValueError('CAPTURE_RECEIPT_INVALID')
        if not probe:
            verify_snapshot(output/'snapshot.db', receipt)
        return receipt
    except BaseException as exc:
        original = exc
        if process is None: attempt.value['creation_exception'] = attempt.failure(exc)
        raise
    finally:
        try:
            attempt.value['source_metadata_after'] = source_metadata(source)
            attempt.value['source_companions_after'] = companion_metadata(source)
        except BaseException as metadata_error:
            attempt.value['post_failure_metadata_error'] = type(metadata_error).__name__
        def cleanup(action):
            try: action()
            except BaseException as error:
                attempt.value['cleanup_errors'].append(attempt.failure(error))
        def stop():
            if process.poll() is None:
                current = inspect_macos(process.pid)
                if admitted is not None and current == admitted:
                    process.terminate(); process.wait(timeout=5)
                else:
                    # Worker times out without acknowledgement; do not signal an
                    # unverified identity. Surface unresolved ownership instead.
                    process.wait(timeout=12)
        if process is not None:
            cleanup(stop)
            attempt.value['exit_status'] = process.poll()
            attempt.value['signal'] = -process.returncode if process.returncode is not None and process.returncode < 0 else None
            if pipes is not None: cleanup(lambda: pipes.collect(attempt))
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None: cleanup(stream.close)
            attempt.value['child_exited'] = process.poll() is not None
        if attempt.value['cleanup_errors'] and original is None:
            raise RuntimeError('CAPTURE_CLEANUP_FAILED')


def verify_snapshot(path, receipt):
    path_identity(path)
    if stat.S_IMODE(path.stat().st_mode) != 0o400 or sha(path.read_bytes()) != receipt['snapshot_sha256']:
        raise ValueError('SNAPSHOT_PIN_INVALID')
    # immutable is allowed ONLY for the completed isolated snapshot, never source.
    db = sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)
    try:
        if (db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or
                db.execute('PRAGMA foreign_key_check').fetchall()):
            raise ValueError('SNAPSHOT_INDEPENDENT_CHECK_FAILED')
    finally:
        db.close()
    if sha(path.read_bytes()) != receipt['snapshot_sha256']: raise ValueError('SNAPSHOT_CHANGED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--pin', required=True)
    args = parser.parse_args()
    try:
        sys.exit(worker(json.loads(args.job.read_bytes()), args.pin))
    except BaseException as error:
        if isinstance(error, SystemExit): raise
        # The category is bounded and contains only fixed capability labels;
        # never emit exception text, paths, SQL, or provider material.
        category = str(error)
        if not category.startswith(('OS_CAPTURE_POLICY_NOT_ENFORCED:', 'CAPTURE_', 'QUERY_ONLY_REQUIRED',
                                    'NEGATIVE_CAPABILITY_FAILED:', 'CHILD_SANDBOX_ESCAPE')):
            category = type(error).__name__
        print(json.dumps({'status': 'FAILED_CLOSED', 'error_type': type(error).__name__, 'category': category}), flush=True)
        sys.exit(4)
