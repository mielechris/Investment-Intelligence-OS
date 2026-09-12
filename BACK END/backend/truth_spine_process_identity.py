"""Bounded macOS process observations and non-authorizing shadow startup receipts.

KERN_PROCARGS2 yields argc and NUL-delimited argv. Only argc arguments are
decoded; the environment tail is neither decoded, returned nor persisted.
No credentials, network, service control or operational discovery occurs here.
"""
from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time


class IdentityFailure(ValueError):
    pass


@dataclass(frozen=True)
class ProcessObservation:
    pid: int
    parent_pid: int
    start_time: str
    command: str
    executable: str
    executable_hash: str
    cwd: str
    argv: tuple[str, ...] = ()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_stamp(value):
    # OS ps is explicitly invoked in UTC/C, with documented second precision.
    if re.fullmatch(r'[A-Za-z]{3} .* \d{4}', value):
        return datetime.strptime(' '.join(value.split()), '%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc).isoformat()
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise IdentityFailure('START_TIME_INVALID')
    return parsed.isoformat()


def kernel_argv(pid):
    # macOS SDK sys/sysctl.h: CTL_KERN=1, KERN_PROCARGS2=49.
    libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    size = ctypes.c_size_t(1024 * 1024)
    buffer = ctypes.create_string_buffer(size.value)
    mib = (ctypes.c_int * 3)(1, 49, pid)
    if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
        raise IdentityFailure('ARGV_OBSERVATION_FAILED')
    argc = ctypes.c_int.from_buffer(buffer).value
    if not 1 <= argc <= 128:
        raise IdentityFailure('ARGV_OBSERVATION_INVALID')
    data = buffer.raw[:size.value]
    offset = data.index(b'\0', ctypes.sizeof(ctypes.c_int)) + 1
    while offset < len(data) and data[offset] == 0:
        offset += 1
    argv = []
    for _ in range(argc):
        end = data.index(b'\0', offset)
        argv.append(data[offset:end].decode('utf-8', errors='strict'))
        offset = end + 1
    return tuple(argv)


INSPECTION_QUERIES = frozenset(('PS_START', 'PS_PARENT', 'PS_EXECUTABLE', 'LSOF_CWD',
    'KERNEL_ARGV', 'PARENT_PARSE', 'START_PARSE', 'EXECUTABLE_RESOLVE',
    'EXECUTABLE_HASH', 'CWD_RESOLVE'))
INSPECTION_FAILURES = frozenset(('NONE', 'ABSENT', 'TOOL_EXIT', 'EMPTY_OUTPUT',
    'CWD_CARDINALITY', 'EXECUTABLE_NOT_ABSOLUTE', 'OVERSIZE', 'TIMEOUT',
    'PERMISSION', 'OS_ERROR', 'INVALID_VALUE', 'OTHER'))


def validate_inspection_diagnostic(value):
    """Positive vocabulary only. No raw tool output, exception, path or hash."""
    keys = {'query', 'started_at', 'ended_at', 'monotonic_start', 'monotonic_end',
            'returncode', 'signal', 'stdout_empty', 'cwd_records', 'failure'}
    if type(value) is not dict or set(value) != keys:
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    if (type(value['query']) is not str or value['query'] not in INSPECTION_QUERIES or
            type(value['failure']) is not str or value['failure'] not in INSPECTION_FAILURES):
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    for key in ('started_at', 'ended_at'):
        stamp = value[key]
        if (type(stamp) is not str or
                re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00', stamp) is None):
            raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
        datetime.fromisoformat(stamp)
    for key in ('monotonic_start', 'monotonic_end'):
        if type(value[key]) not in (int, float) or not 0 <= value[key] < 10**12:
            raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    if value['monotonic_end'] < value['monotonic_start']:
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    code = value['returncode']
    if code is not None and (type(code) is not int or not -255 <= code <= 255):
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    if value['signal'] != (-code if code is not None and code < 0 else None):
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    if value['signal'] is not None and type(value['signal']) is not int:
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    if value['stdout_empty'] is not None and type(value['stdout_empty']) is not bool:
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    count = value['cwd_records']
    if count is not None and (type(count) is not int or not 0 <= count <= 129):
        raise IdentityFailure('INSPECTION_DIAGNOSTIC_INVALID')
    return dict(value)


def inspect_macos(pid, *, diagnostic=None):
    """Existing identity predicates; optional non-authorizing query telemetry."""
    env = {'PATH': '/usr/bin:/bin:/usr/sbin', 'LC_ALL': 'C', 'TZ': 'UTC'}
    meta = None

    def begin(query):
        nonlocal meta
        meta = {'query': query, 'started_at': datetime.now(timezone.utc).isoformat(timespec='microseconds'),
                'monotonic_start': time.monotonic(), 'returncode': None, 'signal': None,
                'stdout_empty': None, 'cwd_records': None, 'failure': 'NONE'}

    def emit(*, primary=False):
        if diagnostic is None or meta is None:
            return
        row = {**meta, 'ended_at': datetime.now(timezone.utc).isoformat(timespec='microseconds'),
               'monotonic_end': time.monotonic()}
        try:
            diagnostic(validate_inspection_diagnostic(row))
        except Exception:
            if not primary:
                raise IdentityFailure('DIAGNOSTIC_PUBLICATION_FAILED') from None

    def read(query, argv):
        begin(query)
        result = subprocess.run(argv, capture_output=True, text=True, timeout=1, env=env)
        meta['returncode'] = result.returncode
        meta['signal'] = -result.returncode if result.returncode < 0 else None
        if len(result.stdout) > 65536:
            meta['failure'] = 'OVERSIZE'
            raise IdentityFailure('PROCESS_INSPECTION_OVERSIZE')
        value = result.stdout.strip()
        meta['stdout_empty'] = not value
        return result.returncode, value

    def reject(predicate):
        meta['failure'] = predicate
        raise IdentityFailure('PROCESS_INSPECTION_FAILED')

    def step(query, call):
        begin(query)
        result = call()
        emit()
        return result

    try:
        code, stamp = read('PS_START', ['/bin/ps', '-ww', '-p', str(pid), '-o', 'lstart='])
        if code == 1 and not stamp:
            meta['failure'] = 'ABSENT'
            emit()
            return None
        if code != 0 or not stamp:
            reject('TOOL_EXIT' if code != 0 else 'EMPTY_OUTPUT')
        emit()
        values = []
        for query, field in (('PS_PARENT', 'ppid='), ('PS_EXECUTABLE', 'comm=')):
            code, value = read(query, ['/bin/ps', '-ww', '-p', str(pid), '-o', field])
            if code != 0 or not value:
                reject('TOOL_EXIT' if code != 0 else 'EMPTY_OUTPUT')
            values.append(value)
            emit()
        code, paths = read('LSOF_CWD', ['/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'])
        cwd = [line[1:] for line in paths.splitlines() if line.startswith('n')]
        meta['cwd_records'] = min(len(cwd), 129)
        executable = Path(values[1])
        if code != 0 or len(cwd) != 1 or not executable.is_absolute():
            reject('TOOL_EXIT' if code != 0 else
                   'CWD_CARDINALITY' if len(cwd) != 1 else 'EXECUTABLE_NOT_ABSOLUTE')
        emit()
        argv = step('KERNEL_ARGV', lambda: kernel_argv(pid))
        parent = step('PARENT_PARSE', lambda: int(values[0]))
        start = step('START_PARSE', lambda: utc_stamp(stamp))
        command = ' '.join(argv)
        resolved = step('EXECUTABLE_RESOLVE', lambda: str(executable.resolve()))
        hashed = step('EXECUTABLE_HASH', lambda: file_hash(executable))
        directory = step('CWD_RESOLVE', lambda: str(Path(cwd[0]).resolve()))
        return ProcessObservation(pid, parent, start, command, resolved, hashed, directory, argv)
    except BaseException as error:
        if meta is not None and meta['failure'] == 'NONE':
            meta['failure'] = ('TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else
                'PERMISSION' if isinstance(error, PermissionError) else
                'OS_ERROR' if isinstance(error, OSError) else
                'INVALID_VALUE' if isinstance(error, ValueError) else 'OTHER')
        emit(primary=True)
        raise


def safe(value, root):
    """Diagnostics never contain unrestricted command/argv or personal paths."""
    if isinstance(value, dict):
        return {k: ({'sanitized_sha256': digest(v)} if k == 'command' else safe(v, root)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(v, str) for v in value):
            return [safe_arg(v, root) for v in value]
        return [safe(v, root) for v in value]
    if isinstance(value, str):
        if value.startswith(('{SHADOW}/', '{PYTHON_FRAMEWORK}/')) or value == '{SHADOW}':
            return value
        if value.startswith(str(root)) and (value == str(root) or value.startswith(str(root)+'/')):
            return '{SHADOW}'+value[len(str(root)):]
        if value.startswith('/Library/Frameworks/Python.framework/'):
            return '{PYTHON_FRAMEWORK}/'+value.split('/Python.framework/', 1)[1]
        if '/' in value or '\\' in value or any(x.isspace() for x in value):
            return {'sanitized_sha256': hashlib.sha256(value.encode()).hexdigest()}
    return value


def safe_arg(value, root):
    fixed = {'-B', '-m', '--config', '--role', '--port', '--instance-id', '--runner-id', '--created-at',
             'truth_spine_integration_service', 'truth_spine_full_day_service', 'scheduler', 'publisher', 'backend'}
    if (value in fixed or re.fullmatch(r'shadow-(?:child|runner)-[0-9a-f]{32}', value)
            or re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+\+00:00', value)
            or re.fullmatch(r'\d{4,5}', value)):
        return value
    converted = safe(value, root)
    if converted != value or value.startswith(('{SHADOW}', '{PYTHON_FRAMEWORK}')):
        return converted
    return {'sanitized_sha256': hashlib.sha256(value.encode()).hexdigest()}


def normalized(observation, root):
    value = asdict(observation)
    value['start_time'] = utc_stamp(value['start_time'])
    value['executable'] = str(Path(value['executable']).resolve())
    value['cwd'] = str(Path(value['cwd']).resolve())
    value['argv'] = list(value['argv'])
    if not value['argv'] or observation.command != ' '.join(value['argv']):
        raise IdentityFailure('ARGV_BOUNDARIES_INVALID')
    # argv[0] is represented by the observed executable; the parent separately
    # pins BOTH kernel argv[0] and executable against its manifest. Whitespace,
    # roles, roots, ports and all other argument boundaries remain significant.
    value['argv'][0] = value['executable']
    value.pop('command')
    value['argv_hash'] = digest(value['argv'])
    return safe(value, root)


def receipt_path(root, instance):
    if not re.fullmatch(r'shadow-child-[0-9a-f]{32}', instance):
        raise IdentityFailure('INSTANCE_ID_INVALID')
    return Path(root)/('startup-'+instance+'.json')


def read_receipt(root, instance):
    path = receipt_path(root, instance)
    if path.is_symlink():
        raise IdentityFailure('STARTUP_RECEIPT_FILE_INVALID')
    if not path.exists():
        return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 32768:
        raise IdentityFailure('STARTUP_RECEIPT_FILE_INVALID')
    result = json.loads(path.read_bytes())
    if not isinstance(result, dict) or result.get('content_hash') != digest({k:v for k,v in result.items() if k != 'content_hash'}):
        raise IdentityFailure('STARTUP_RECEIPT_HASH_INVALID')
    return result


def binding(root, instance, runner, role, port, created):
    root = Path(root).resolve()
    receipt_path(root, instance)
    if not re.fullmatch(r'shadow-runner-[0-9a-f]{32}', runner) or role not in {'scheduler', 'publisher', 'backend'}:
        raise IdentityFailure('STARTUP_BINDING_INVALID')
    if (role == 'backend' and (type(port) is not int or not 1024 < port < 65536)) or (role != 'backend' and port is not None):
        raise IdentityFailure('STARTUP_PORT_INVALID')
    return {'schema': 'iios-shadow-startup-v1', 'instance_id': instance, 'runner_identity': runner,
            'role': role, 'port': port, 'created_at': utc_stamp(created), 'root_hash': digest(str(root)),
            'topology_hash': file_hash(root/'topology.json'), 'authority_hash': file_hash(root/'authority.json')}


def write_startup(root, instance, runner, role, port, created):
    """Called after topology validation, before the irreversible I/O guard.

    Fixed self-only OS probes are the sole subprocesses. This receipt grants
    no authority. Backend/service work starts only after the guard is installed.
    """
    root = Path(root).resolve()
    expected = binding(root, instance, runner, role, port, created)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise IdentityFailure('STARTUP_ROOT_INVALID')
    now = datetime.now(timezone.utc)
    if not 0 <= (now-datetime.fromisoformat(expected['created_at'])).total_seconds() <= 30:
        raise IdentityFailure('STARTUP_CREATION_TIME_INVALID')
    observation = inspect_macos(os.getpid())
    if observation is None or observation.parent_pid != os.getppid() or observation.cwd != str(root/'release/backend'):
        raise IdentityFailure('STARTUP_SELF_OBSERVATION_INVALID')
    record = {**expected, 'observation': normalized(observation, root)}
    record['content_hash'] = digest(record)
    target = receipt_path(root, instance)
    if target.exists() or target.is_symlink():
        raise IdentityFailure('STARTUP_RECEIPT_ALREADY_EXISTS')
    stage = target.with_suffix('.staging')
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(record)); stream.flush(); os.fsync(stream.fileno())
        # Hard-link publication is atomic and refuses replacement of an old ID.
        os.link(stage, target, follow_symlinks=False)
        stage.unlink()
        fd = os.open(root, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if stage.exists(): stage.unlink()
    return record
