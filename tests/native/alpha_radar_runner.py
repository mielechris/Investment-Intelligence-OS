"""Test-only native harness. Never invoked or imported by the production CLI.

Native execution requires separately reviewed input and confinement pins.
Clock acceleration is explicit synthetic evidence, never real-time acceptance.
"""
import sys

# Fixed early hints precede local imports and admission. They never grant authority.
EARLY_STAGES = frozenset(('PYTHON_ENTRY', 'IMPORT_BEGIN', 'IMPORT_COMPLETE',
    'IMPORT_FAILED', 'DESCRIPTOR_READ', 'DESCRIPTOR_VERIFIED',
    'CHILD_ADMISSION_BEGIN', 'CHILD_ADMISSION_VERIFIED'))


def early_diagnostic(stage):
    if stage not in EARLY_STAGES:
        raise ValueError('EARLY_DIAGNOSTIC_STAGE')
    if __name__ == '__main__':
        sys.stderr.write('RADAR_EARLY: ' + stage + '\n')
        sys.stderr.flush()


early_diagnostic('PYTHON_ENTRY')
early_diagnostic('IMPORT_BEGIN')
try:
    from dataclasses import asdict
    from datetime import datetime, timedelta, timezone
    import fcntl
    import hashlib
    import json
    import os
    import re
    import ssl
    from pathlib import Path
    import signal
    import socket
    import subprocess
    import time
    from urllib.parse import urlencode

    from alpha_market_baseline import require, summarize
    from alpha_session_execution import (execute_schedule, execute_day, safe_root, publish,
        read_record, verify_destination)
    from provider_gateway_contract import canonical, content_hash, utc
    from provider_gateway_https import bounded_https
    from truth_spine_process_identity import inspect_macos, validate_inspection_diagnostic
    from alpha_radar_admission import (SCOPE, AUTHORITY, SyntheticCapability, admit,
        envelope, verify_envelope, store, verify_inputs)
except Exception:
    if __name__ == '__main__':
        early_diagnostic('IMPORT_FAILED')
        sys.exit(1)
    raise
early_diagnostic('IMPORT_COMPLETE')

# Diagnostics are observations only; none of these records grant authority.
STAGES = frozenset(('LAUNCH_INTENT', 'PROCESS_CREATE', 'OWNERSHIP_REGISTER',
    'STARTUP_VERIFY', 'LISTENER_VERIFY', 'PARENT_ACK', 'SESSION_WAIT',
    'RUNTIME_VERIFY', 'CONFINEMENT_CHECK', 'TLS_CONTEXT', 'TLS_LOAD',
    'SOCKET_CREATE', 'SOCKET_BIND', 'SOCKET_LISTEN', 'TLS_WRAP',
    'STARTUP_PUBLISH', 'FIXTURE_SERVE', 'WORKER_SESSION', 'TLS_HANDSHAKE'))
FAILURE_CODES = frozenset(('PROCESS_ABSENT', 'PROCESS_IDENTITY',
    'STARTUP_IDENTITY_CHANGED', 'OSCILLATING_EXECUTABLE', 'STARTUP_STABILIZATION_TIMEOUT',
    'PROCESS_INSPECTION_FAILED', 'PROCESS_INSPECTION_OVERSIZE', 'ARGV_OBSERVATION_FAILED',
    'ARGV_OBSERVATION_INVALID', 'START_TIME_INVALID', 'RUNTIME_IDENTITY_CHANGED',
    'STARTUP_RECEIPT_REQUIRED', 'STARTUP_RECEIPT_CHANGED', 'STARTUP_RECEIPT_MISMATCH',
    'PARENT_ACK_TIMEOUT', 'PARENT_ACK_MISMATCH', 'LISTENER_OWNER_MISMATCH',
    'LISTENER_INSPECTION', 'CHILD_SURVIVED', 'UNVERIFIED_PARTIAL_START',
    'COOPERATIVE_SHUTDOWN', 'NATIVE_SESSION_TIMEOUT', 'WORKER_FAILED',
    'SESSION_INCOMPLETE', 'OS_CONFINEMENT_REQUIRED', 'GENERAL_NETWORK_MUST_BE_DENIED',
    'CONFINEMENT_SENTINEL_MISSING', 'IMPORTED_CLOSURE', 'NATIVE_RUNTIME',
    'DIAGNOSTIC_PUBLICATION_FAILED', 'DIAGNOSTIC_OVERFLOW', 'DIAGNOSTIC_PIPE_FAILED',
    'LIFECYCLE_ENVIRONMENT', 'LIFECYCLE_WRITE', 'LIFECYCLE_STDIO',
    'LIFECYCLE_STDOUT_UNEXPECTED','FULL_JOB_BUDGET','FULL_INSUFFICIENT_BUDGET',
    'FULL_CANCELLED','FULL_CLEANUP_DEADLINE','FULL_VALIDATION_PARENT',
    'FULL_INDEPENDENT_PARENT'))


def failure_category(error):
    # Never stringify/hash an exception, argv, filename or stderr body.
    if error.args and type(error.args[0]) is str and error.args[0] in FAILURE_CODES:
        return error.args[0]
    if isinstance(error, subprocess.TimeoutExpired):
        return 'PROCESS_TIMEOUT'
    if isinstance(error, ssl.SSLError):
        return 'TLS_ERROR'
    if isinstance(error, PermissionError):
        return 'PERMISSION_ERROR'
    if isinstance(error, FileExistsError):
        return 'DESTINATION_EXISTS'
    if isinstance(error, OSError):
        return 'OS_ERROR'
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return 'IMPORT_ERROR'
    return 'UNCLASSIFIED_ERROR'


def launcher_hint(raw):
    """Fixed lexical observations only; never a compiler verdict or authority.

    The first hosted child exited before PS_START with six opaque stderr lines.
    Preserve recognizable error classes/symbols without returning text, paths,
    line contents, exception messages or arbitrary identifiers from those lines.
    """
    phrases = (
        (b'profile compilation failed', 'PROFILE_COMPILATION_FAILED'),
        (b'error compiling profile', 'PROFILE_COMPILATION_FAILED'),
        (b'failed to parse entitlements', 'ENTITLEMENT_PARSE_FAILED'),
        (b'unbound variable', 'UNBOUND_VARIABLE'), (b'undefined variable', 'UNBOUND_VARIABLE'),
        (b'unbound symbol', 'UNBOUND_SYMBOL'), (b'unknown operation', 'UNKNOWN_OPERATION'),
        (b'undefined operation', 'UNKNOWN_OPERATION'), (b'unsupported operation', 'UNSUPPORTED_OPERATION'),
        (b'unknown filter', 'UNKNOWN_FILTER'), (b'invalid parameter', 'INVALID_PARAMETER'),
        (b'syntax error', 'SYNTAX_ERROR'), (b'error on line', 'SOURCE_LOCATION_ERROR'),
        (b'error at line', 'SOURCE_LOCATION_ERROR'), (b'sandbox_apply', 'SANDBOX_APPLY'),
        (b'execvp()', 'EXECVP'), (b'operation not permitted', 'OPERATION_NOT_PERMITTED'),
        (b'permission denied', 'PERMISSION_DENIED'), (b'no such file', 'FILE_NOT_FOUND'))
    lowered = raw.lower()
    tags = {label for phrase, label in phrases if phrase in lowered}
    if lowered.startswith(b'sandbox-exec:'):
        tags.add('SANDBOX_EXEC')
    if not tags:
        return 'REDACTED_UNRECOGNIZED'
    # Only symbols present in the reviewed confinement language are admitted.
    # An unknown identifier stays unknown; it is never echoed or hashed.
    for symbol in (b'version', b'allow', b'deny', b'default', b'file-read-metadata',
                   b'file-read*', b'file-write*', b'subpath', b'literal', b'process-exec',
                   b'sysctl-read', b'network-outbound', b'network-inbound', b'network-bind',
                   b'remote', b'local', b'ip'):
        if re.search(rb'(?<![a-z0-9_*-])'+re.escape(symbol)+rb'(?![a-z0-9_*-])', lowered):
            tags.add('SYMBOL_'+symbol.decode('ascii').upper().replace('-', '_').replace('*', '_STAR'))
    return 'UNTRUSTED_LAUNCHER_'+'_'.join(sorted(tags))


# Reviewed lexical rules, NOT recovered macOS/compiler message templates.
# Each record separates direct byte observations from tentative interpretation.
LAUNCHER_LEXEMES = (
    (b'profile compilation failed', 'PROFILE_COMPILE'),
    (b'error compiling profile', 'PROFILE_COMPILE'),
    (b'syntax error', 'SYNTAX'), (b'unbound variable', 'UNBOUND_VARIABLE'),
    (b'unknown operation', 'UNKNOWN_OPERATION'), (b'unknown filter', 'UNKNOWN_FILTER'),
    (b'sandbox_apply', 'PROFILE_APPLY'), (b'execvp()', 'EXECVP'),
    (b'operation not permitted', 'EPERM_WORDS'),
    (b'permission denied', 'EACCES_WORDS'), (b'no such file', 'ENOENT_WORDS'))


def launcher_observation(raw, profile=b'', profile_path=b''):
    """No arbitrary text, errno claims, template claims or causal verdicts.

    Location grammars are our bounded extraction rules, not claims about an
    Apple template. Coordinates are retained only against the pinned profile.
    Forged output can produce an observation; it can never grant authority.
    """
    require(type(raw) is bytes and len(raw) <= 2048, 'DIAGNOSTIC_OVERFLOW')
    require(type(profile) is bytes and len(profile) <= 65536 and
            type(profile_path) is bytes and len(profile_path) <= 2048, 'DIAGNOSTIC_OVERFLOW')
    result = {'schema': 'launcher-observation-v1', 'basis': 'UNTRUSTED_CHILD_PIPE',
              'reporter': 'UNKNOWN', 'lexemes': [], 'location': None,
              'interpretation': 'UNKNOWN', 'proven_root_cause': 'NOT_ESTABLISHED'}
    if any(c < 32 or c > 126 for c in raw):
        return result
    if raw.startswith(b'sandbox-exec: '):
        result['reporter'] = 'SANDBOX_EXEC_PREFIX'
    elif re.match(rb'dyld\[[1-9][0-9]{0,9}\]: ', raw):
        result['reporter'] = 'DYLD_PREFIX'
    lowered = raw.lower()
    result['lexemes'] = sorted({label for word, label in LAUNCHER_LEXEMES
        if re.search(rb'(?<![a-z0-9_])'+re.escape(word)+rb'(?![a-z0-9_])', lowered)})
    lines = profile.splitlines()
    # Exact profile excerpts and exact path-prefixed coordinates are directly
    # compared in memory. Neither the excerpt nor the path leaves this function.
    matches = [i+1 for i, line in enumerate(lines) if line.strip() and raw == line]
    if len(matches) == 1:
        result['location'] = {'line': matches[0], 'column': None, 'basis': 'EXACT_PROFILE_LINE'}
    if profile_path:
        expression = (rb'(?:sandbox-exec: )?'+re.escape(profile_path)+
                      rb':([1-9][0-9]{0,3}):([1-9][0-9]{0,3}): [ -~]{1,1024}')
        match = re.fullmatch(expression, raw)
        if match:
            line, column = map(int, match.groups())
            if 1 <= line <= len(lines) and column <= len(lines[line-1])+1:
                result['location'] = {'line': line, 'column': column,
                                      'basis': 'EXACT_PROFILE_PATH_IN_RANGE'}
    tags = set(result['lexemes'])
    phases = []
    if tags & {'PROFILE_COMPILE','SYNTAX','UNBOUND_VARIABLE','UNKNOWN_OPERATION','UNKNOWN_FILTER'}:
        phases.append('PROFILE_PARSE_INDICATED')
    if 'PROFILE_APPLY' in tags:
        phases.append('PROFILE_APPLICATION_INDICATED')
    if 'EXECVP' in tags:
        phases.append('EXECUTION_INDICATED')
    # Mixed phases, bare literals, dyld and errno words stay inconclusive.
    if len(phases) == 1 and result['reporter'] == 'SANDBOX_EXEC_PREFIX':
        result['interpretation'] = phases[0]
    return result


class StderrCapture:
    """Bounded nonblocking pipe; raw bytes are never written, hashed or echoed."""
    def __init__(self, stream=None, *, profile=b'', profile_path=b''):
        self.stream, self.fd = stream, None
        self.pending = bytearray()
        self.profile, self.profile_path = profile, profile_path
        self.observations = []
        self.lines, self.received, self.retained = [], 0, 0
        self.overflow, self.discard_line, self.eof = False, False, False
        if stream is not None:
            self.fd = stream.fileno()
            require(type(self.fd) is int and self.fd >= 0, 'DIAGNOSTIC_PIPE_FAILED')
            os.set_blocking(self.fd, False)

    def line(self, raw):
        # Only fixed classifications survive. Even a forged known prefix is
        # merely an untrusted stderr hint, never a proven failure or authority.
        fixed = {
            b'sandbox-exec: sandbox_apply: Operation not permitted': 'STDERR_CONFINEMENT_DENIED',
            b'PermissionError:': 'STDERR_PERMISSION_ERROR',
            b'FileNotFoundError:': 'STDERR_FILE_NOT_FOUND',
            b'ModuleNotFoundError:': 'STDERR_IMPORT_ERROR',
            b'ImportError:': 'STDERR_IMPORT_ERROR',
            b'ssl.SSLError:': 'STDERR_TLS_ERROR',
            b'OSError:': 'STDERR_OS_ERROR',
        }
        value = fixed.get(raw, 'REDACTED_UNRECOGNIZED')
        if value == 'REDACTED_UNRECOGNIZED':
            for prefix, category in fixed.items():
                if prefix.endswith(b':') and raw.startswith(prefix + b' '):
                    value = category
                    break
        if raw.startswith(b'RADAR_DIAGNOSTIC: '):
            code = raw[len(b'RADAR_DIAGNOSTIC: '):]
            allowed = FAILURE_CODES | {'PROCESS_TIMEOUT', 'TLS_ERROR', 'PERMISSION_ERROR',
                'DESTINATION_EXISTS', 'OS_ERROR', 'IMPORT_ERROR', 'UNCLASSIFIED_ERROR'}
            if code in {v.encode('ascii') for v in allowed}:
                value = 'STDERR_' + code.decode('ascii')
        for stage in EARLY_STAGES:
            if raw == ('RADAR_EARLY: ' + stage).encode('ascii'):
                value = 'UNTRUSTED_EARLY_' + stage
                break
        if value == 'REDACTED_UNRECOGNIZED':
            value = launcher_hint(raw)
        observation = launcher_observation(raw, self.profile, self.profile_path)
        size = len(value) + 4 + len(json.dumps(observation, sort_keys=True))
        if self.retained + size <= 8192:
            self.lines.append(value)
            self.observations.append(observation)
            self.retained += size
        else:
            self.overflow = True

    def feed(self, chunk):
        require(type(chunk) is bytes, 'DIAGNOSTIC_PIPE_FAILED')
        remaining = max(0, 65536 - self.received)
        self.received += len(chunk)
        if len(chunk) > remaining:
            self.overflow = True
        for byte in chunk[:remaining]:
            if byte == 10:
                self.line(bytes(self.pending) if not self.discard_line else b'')
                self.pending.clear()
                self.discard_line = False
            elif not self.discard_line:
                if len(self.pending) < 2048:
                    self.pending.append(byte)
                else:
                    self.pending.clear()
                    self.discard_line = True
                    self.overflow = True
        if self.overflow:
            self.pending.clear()

    def drain(self):
        if self.fd is None or self.eof:
            return
        # Fixed work per tick; continue draining/discarding after overflow so
        # diagnostics do not become an unbounded buffer or a blocking read.
        for _ in range(8):
            try:
                chunk = os.read(self.fd, 8192)
            except BlockingIOError:
                return
            if not chunk:
                self.finish()
                return
            self.feed(chunk)

    def finish(self):
        if not self.eof and (self.pending or self.discard_line):
            self.line(bytes(self.pending) if not self.discard_line else b'')
        self.pending.clear()
        self.eof = True

    def snapshot(self):
        return {'untrusted_stderr_hints': list(self.lines),
                'launcher_observations': list(self.observations), 'bytes_seen': self.received,
                'overflow': self.overflow, 'eof': self.eof, 'raw_retained': False}


class LifecycleStreams:
    """Two bounded nonblocking pipes; stdout is forbidden, stderr is sanitized."""
    def __init__(self, child):
        self.stdout = StderrCapture(child.stdout)
        self.stderr = StderrCapture(child.stderr)
        for capture in (self.stdout, self.stderr):
            if capture.stream is None: capture.finish()

    @property
    def overflow(self):
        return self.stdout.overflow or self.stderr.overflow

    @property
    def eof(self):
        return self.stdout.eof and self.stderr.eof

    def drain(self):
        # Drain both even if the first stream fails. Never persist raw bytes.
        errors = []
        for capture in (self.stdout, self.stderr):
            try: capture.drain()
            except Exception: errors.append('DIAGNOSTIC_PIPE_FAILED')
        require(not errors, 'DIAGNOSTIC_PIPE_FAILED')

    def check(self):
        require(not self.overflow, 'DIAGNOSTIC_OVERFLOW')
        require(self.stdout.received == 0, 'LIFECYCLE_STDOUT_UNEXPECTED')

    def close(self):
        errors = []
        for capture in (self.stdout, self.stderr):
            capture.pending.clear()
            try:
                if capture.stream is not None: capture.stream.close()
                else: capture.finish()
            except Exception: errors.append('DIAGNOSTIC_PIPE_FAILED')
        require(not errors, 'DIAGNOSTIC_PIPE_FAILED')

    def snapshot(self):
        return {'stdout': self.stdout.snapshot(), 'stderr': self.stderr.snapshot(),
                'raw_retained': False}


def close_lifecycle_stdin(child):
    try:
        require(child.stdin is not None, 'LIFECYCLE_STDIO')
        child.stdin.close()
        require(child.stdin.closed is True, 'LIFECYCLE_STDIO')
    except Exception:
        raise ValueError('LIFECYCLE_STDIO') from None


def child_status(child):
    code = child.poll()
    require(code is None or type(code) is int, 'PROCESS_IDENTITY')
    return {'state': 'CHILD_RUNNING' if code is None else 'CHILD_EXITED',
            'returncode': code, 'exit_code': code if code is not None and code >= 0 else None,
            'signal': -code if code is not None and code < 0 else None}


def observed_diagnostic(entry, actual):
    expected = entry['expected']
    matches = {key: actual.get(key) == value for key, value in expected.items()}
    def integer(key):
        value = actual.get(key)
        return value if type(value) is int and 0 < value < 2**31 else None
    stamp = actual.get('start_time')
    if not isinstance(stamp, str) or re.fullmatch(r'[0-9T:+.Z-]{20,40}', stamp) is None:
        stamp = None
    return {'basis': 'INDEPENDENT_OS_OBSERVATION', 'pid': integer('pid'),
            'parent_pid': integer('parent_pid'), 'start_time': stamp,
            'field_matches': matches, 'unexpected_values': 'REDACTED',
            'executable_hash': expected.get('executable_hash') if matches.get('executable_hash') else None}


class ChildDiagnostics:
    def __init__(self, cap, role, launch_parent):
        require(role in ('fixture', 'worker') and re.fullmatch('[a-f0-9]{64}', launch_parent), 'CHILD_LAUNCH')
        self.cap, self.role, self.launch_parent = cap, role, launch_parent
        self.sequence, self.stage = 0, 'RUNTIME_VERIFY'

    def emit(self, stage, *, category=None):
        require(stage in STAGES, 'CHILD_DIAGNOSTIC_STAGE')
        allowed = FAILURE_CODES | {'PROCESS_TIMEOUT', 'TLS_ERROR', 'PERMISSION_ERROR',
            'DESTINATION_EXISTS', 'OS_ERROR', 'IMPORT_ERROR', 'UNCLASSIFIED_ERROR'}
        require(category is None or (type(category) is str and category in allowed), 'CHILD_DIAGNOSTIC_CATEGORY')
        self.stage = stage
        self.sequence += 1
        require(self.sequence <= 64, 'DIAGNOSTIC_OVERFLOW')
        value = {'kind': 'CHILD_DIAGNOSTIC_ONLY', 'role': self.role,
                 'launch_parent': self.launch_parent, 'sequence': self.sequence,
                 'stage': stage, 'category': category, 'pid': os.getpid(),
                 'parent_pid': os.getppid()}
        store(self.cap, f'{self.role}-diagnostic-{self.sequence:04d}.json', value)

    def failure(self, error):
        try:
            self.emit(self.stage, category=failure_category(error))
        except Exception:
            # Preserve the primary exception. The parent still captures a fixed
            # failure hint even if admitted child receipt publication failed.
            sys.stderr.write('RADAR_DIAGNOSTIC: DIAGNOSTIC_PUBLICATION_FAILED\n')


def verify_child_diagnostic(doc, expected, *, parents, role, launch_parent, pid, parent_pid):
    # Validate the positive data vocabulary before hashing any untrusted document.
    require(set(doc) == {'schema', 'scope', 'authority', 'parents', 'value', 'content_hash'} and
            doc['schema'] == 'iios-radar-synthetic-receipt-v1' and doc['scope'] == SCOPE and
            doc['parents'] == parents and doc['authority'] == AUTHORITY and
            all(v is False for v in doc['authority'].values()) and
            type(doc['content_hash']) is str and re.fullmatch('[a-f0-9]{64}', doc['content_hash']), 'CHILD_DIAGNOSTIC_SCHEMA')
    value = doc['value']
    require(set(value) == {'kind', 'role', 'launch_parent', 'sequence', 'stage',
            'category', 'pid', 'parent_pid'}, 'CHILD_DIAGNOSTIC_SCHEMA')
    require(value['kind'] == 'CHILD_DIAGNOSTIC_ONLY' and value['role'] == role and
            value['launch_parent'] == launch_parent and value['pid'] == pid and
            type(value['pid']) is int and type(pid) is int and type(value['parent_pid']) is int and
            value['parent_pid'] == parent_pid and role in ('fixture', 'worker') and
            re.fullmatch('[a-f0-9]{64}', launch_parent) is not None and
            type(value['sequence']) is int and 1 <= value['sequence'] <= 64 and
            type(value['stage']) is str and value['stage'] in STAGES, 'CHILD_DIAGNOSTIC_BINDING')
    allowed = FAILURE_CODES | {'PROCESS_TIMEOUT', 'TLS_ERROR', 'PERMISSION_ERROR',
        'DESTINATION_EXISTS', 'OS_ERROR', 'IMPORT_ERROR', 'UNCLASSIFIED_ERROR'}
    require(value['category'] is None or (type(value['category']) is str and value['category'] in allowed), 'CHILD_DIAGNOSTIC_CATEGORY')
    verify_envelope(doc, expected, parents=parents)
    return value  # Not accepted by read_startup, Session.verify or live admission.


def checked_capability(cap):
    require(type(cap) is SyntheticCapability, 'SYNTHETIC_CAPABILITY_REQUIRED')
    return cap.recheck()


def fixture_exchange(cap, slot, at):
    p, r, _ = checked_capability(cap)
    f = p['fixture']
    return bounded_https(host=f['server_name'], address=f['address'], port=f['port'],
        method='GET', target=f'/slot/{slot}?' + urlencode({'at': at}),
        headers={'Accept': 'application/json', 'Accept-Encoding': 'identity'}, body=None,
        tls_file=str(Path(r['root']) / r['tls']), timeout=20, limit=1_000_000)


class Session:
    """Shared durable journal and scheduler with separate synthetic receipt policy."""
    def __init__(self, cap, *, clock, wait, stop, exchange=fixture_exchange):
        self.p, self.r, self.pins = checked_capability(cap)
        self.cap, self.clock, self.wait, self.stop, self.exchange = cap, clock, wait, stop, exchange
        self.hashes, self.verified_records, self.descriptors = {}, {}, {}

    def hash(self, value):
        # Cache by immutable canonical bytes, never mutable object identity.
        # All disk reads still verify bytes, inode/mode and independent parents.
        key = canonical(value)
        if key not in self.hashes:
            self.hashes[key] = content_hash(envelope(value, self.pins))
        return self.hashes[key]

    def open_root(self, path):
        allowed = {self.p['plan']['root']} | {row['root'] for row in self.p['plan']['rows']}
        require(str(path) in allowed, 'JOURNAL_PATH_NOT_ADMITTED')
        fd = safe_root(path)
        st = os.fstat(fd)
        self.descriptors[fd] = (str(path), st.st_dev, st.st_ino)
        return fd

    def verify_fd(self, fd):
        require(fd in self.descriptors, 'JOURNAL_DESCRIPTOR_NOT_ADMITTED')
        path, device, inode = self.descriptors[fd]
        st = os.fstat(fd)
        require((device, inode) == (st.st_dev, st.st_ino), 'JOURNAL_DESCRIPTOR_REPLACED')
        verify_destination(fd, path)

    def write(self, fd, name, value):
        checked_capability(self.cap)
        self.verify_fd(fd)
        return publish(fd, name, envelope(value, self.pins))

    def read(self, fd, name, *, expected_hash=None):
        self.verify_fd(fd)
        doc = read_record(fd, name, expected_hash=expected_hash)
        key = canonical(doc)
        if key not in self.verified_records:
            value = verify_envelope(doc, expected_hash or content_hash(doc), parents=self.pins)
            self.verified_records[key] = canonical(value)
        return json.loads(self.verified_records[key])

    def verify(self, receipt, expected, *, parents):
        require(self.hash(receipt) == expected and receipt['parents'] == parents and
                receipt['scope'] == SCOPE and receipt['authority'] == AUTHORITY and
                receipt['source_commit'] == self.p['source_commit'], 'SYNTHETIC_RECEIPT_BINDING')

    def request(self, slot):
        row = self.p['plan']['rows'][slot]
        return {'manifest': {'source_commit': self.p['source_commit'], 'root': row['root'],
                             'role': SCOPE},
                'account': {'bulk_plan': self.p['plan'], 'bulk_slot': slot,
                            'bulk_plan_parent': self.p['plan_parent']},
                'expected': {**self.pins, 'slot': content_hash({'slot': slot, 'row': row})}}

    def execute(self, request, previous):
        checked_capability(self.cap)
        m, a = request['manifest'], request['account']
        def dispatch(day_fd, slot, reserved):
            row = self.p['plan']['rows'][slot]
            fd = self.open_root(row['root'])
            receipt = {'scope': SCOPE, 'authority': AUTHORITY, 'source_commit': m['source_commit'],
                'root': m['root'], 'role': SCOPE, 'parents': {**request['expected'], 'reservation': reserved},
                'result': 'AMBIGUOUS_OR_UNVERIFIED_STOP', 'retry_count': 0,
                'credential_selector_access_count': 0, 'billing': 'SYNTHETIC_NO_CHARGE',
                'bulk_checks': {}, 'dispatch_time': self.clock(), 'response_time': None,
                'actual_dispatch_time': None, 'actual_response_time': None}
            try:
                # The shared day journal has already consumed this slot.
                response = self.exchange(self.cap, slot, receipt['dispatch_time'])
                receipt['response_time'] = self.clock()
                receipt['actual_dispatch_time'] = response.request_start
                receipt['actual_response_time'] = response.response_end
                receipt['http_status'] = response.status
                require(response.status == 200 and len(response.body) <= 1_000_000, 'HTTP_OR_SIZE')
                def unique(pairs):
                    d = {}
                    for k, v in pairs:
                        require(k not in d, 'DUPLICATE_JSON')
                        d[k] = v
                    return d
                payload = json.loads(response.body, object_pairs_hook=unique)
                checks = summarize(payload, row['symbols'], received_at=receipt['response_time'], maximum_age_seconds=60)
                receipt['bulk_checks'] = checks
                require(checks['coverage'] == 'COMPLETE' and checks['freshness'] == 'WITHIN_AGE_BOUND', 'OBSERVATION_FAILED')
                require([v['symbol'] for v in payload['data']] == row['symbols'], 'RESPONSE_ORDER')
                start, end = utc(receipt['dispatch_time']), utc(receipt['response_time'])
                require(utc(row['valid_from']) <= start <= end < utc(row['expires_at']) and
                        (end-start).total_seconds() <= 20, 'RESPONSE_DEADLINE')
                actual_start, actual_end = utc(response.request_start), utc(response.response_end)
                require(0 <= (actual_end-actual_start).total_seconds() <= 20, 'WIRE_DEADLINE')
                receipt['result'] = 'OBSERVED'
            except Exception:
                receipt['failure'] = 'SYNTHETIC_REQUEST_UNVERIFIED'
            finally:
                # Only enums, counts and timestamps from summarize survive.
                self.write(fd, 'ALPHA_VANTAGE.receipt.json', receipt)
                os.close(fd)
            return receipt
        return execute_day(m, a, clock=self.clock, expected_bulk_previous=previous,
            dispatch=dispatch, verify_receipt=self.verify, write=self.write, read=self.read,
            record_hash=self.hash, open_root=self.open_root)

    def completion(self, request, slot, previous, receipt):
        reservation = {'plan': self.p['plan_parent'], 'slot': slot,
                       'source_commit': self.p['source_commit'], 'previous': previous}
        return self.hash({'slot': slot, 'previous': previous, 'reservation': self.hash(reservation),
                          'receipt': self.hash(receipt), 'result': receipt['result']})

    def run(self):
        checked_capability(self.cap)
        journal = Path(self.p['plan']['root'])
        journal.mkdir(mode=0o700)  # Existing/partial runs never acquire new authority.
        for row in self.p['plan']['rows']:
            Path(row['root']).mkdir(mode=0o700)
        requests = [self.request(i) for i in range(475)]
        def verify(receipt, request):
            require(receipt['parents'] == {**request['expected'], 'reservation': receipt['parents']['reservation']}, 'RECEIPT_PARENTS')
            self.verify(receipt, self.hash(receipt), parents=receipt['parents'])
        receipts, reason = execute_schedule(self.p['plan'], requests, clock=self.clock,
            wait=self.wait, executor=self.execute, stop=self.stop, verify=verify,
            completion_parent=self.completion)
        done = self.clock()
        complete = len(receipts) == 475 and reason is None and utc(done) <= utc(self.p['plan']['finalization_deadline'])
        result = {'classification': 'SYNTHETIC_PASS' if complete else 'SYNTHETIC_FAILED',
            'requests': len(receipts), 'receipts': receipts, 'stop_reason': reason,
            'logical_finished_at': done, 'actual_finished_at': datetime.now(timezone.utc).isoformat(),
            'live_readiness': 'NOT_QUALIFIED', 'armed': False, 'additional_provider_requests': 0}
        store(self.cap, 'session.json', result)
        return result


class OwnedProcesses:
    """Pinned launch records; independent OS observation before every signal."""
    def __init__(self, cap, *, inspect=inspect_macos, monotonic=time.monotonic, pause=time.sleep):
        _, runtime, pins = checked_capability(cap)
        profile_path = Path(runtime['root']) / runtime['confinement']
        self.profile = profile_path.read_bytes()
        require(hashlib.sha256(self.profile).hexdigest() == pins['confinement'], 'CONFINEMENT_PIN')
        self.profile_path = os.fsencode(profile_path)
        self.cap, self.inspect, self.monotonic, self.pause = cap, inspect, monotonic, pause
        self.children, self.failures, self.counter = {}, [], 0
        self.startup_pins = {}
        self.diagnostic_failures, self.primary_failures = [], []

    def evidence(self, value):
        self.counter += 1
        store(self.cap, f'lifecycle-{self.counter:04d}.json', {**value,
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            'monotonic_seconds': self.monotonic()})

    def safe_evidence(self, value):
        try:
            self.evidence(value)
        except Exception:
            self.diagnostic_failures.append('DIAGNOSTIC_PUBLICATION_FAILED')

    def pump(self, entry):
        capture = entry.get('capture')
        if capture is not None:
            capture.drain()

    def capture_for(self, child, stderr):
        return StderrCapture(stderr, profile=self.profile, profile_path=self.profile_path)

    def register(self, role, child, *, argv, cwd, executable, executable_hash, launcher=None,
                 stderr=None, launch_parent=None):
        require(role in ('worker', 'fixture') and role not in self.children, 'CHILD_ROLE')
        entry = {'child': child, 'expected': {'pid': child.pid, 'parent_pid': os.getpid(),
            'argv': tuple(argv), 'cwd': str(cwd), 'executable': str(executable),
            'executable_hash': executable_hash}, 'observation': None, 'launcher': launcher, 'launch_parent': launch_parent}
        self.children[role] = entry  # Keep partial startup registered even on failure.
        try:
            entry['capture'] = self.capture_for(child, stderr)
            self.evidence({'event': 'PROCESS_CREATED', 'role': role, 'pid': child.pid,
                'expected_parent_pid': os.getpid(), 'launch_parent': launch_parent,
                'identity_status': 'CHILD_CREATED_UNOBSERVED',
                'status': child_status(child)})
            end = self.monotonic() + 10
            previous, stable, anchor, final_seen = None, 0, None, False
            while self.monotonic() < end:
                self.pump(entry)
                require(not entry['capture'].overflow, 'DIAGNOSTIC_OVERFLOW')
                observed = self.observe(entry, allow_launcher=True)
                identity = {k: observed[k] for k in ('pid', 'parent_pid', 'start_time', 'cwd')}
                if anchor is None:
                    anchor = identity
                require(identity == anchor, 'STARTUP_IDENTITY_CHANGED')
                final = observed['executable'] == str(executable)
                require(not final_seen or final, 'OSCILLATING_EXECUTABLE')
                final_seen |= final
                if not final:
                    previous, stable = None, 0
                    self.pause(.05)
                    continue
                stable = stable + 1 if observed == previous else 1
                previous = observed
                if stable >= 3:
                    entry['observation'] = observed
                    self.evidence({'event': 'OWNERSHIP', 'role': role, 'observed': observed_diagnostic(entry, observed)})
                    return
                self.pause(.05)
            raise ValueError('STARTUP_STABILIZATION_TIMEOUT')
        except BaseException as error:
            primary = {'role': role, 'stage': 'OWNERSHIP_REGISTER',
                       'category': failure_category(error), 'pid': child.pid,
                       'launch_parent': launch_parent}
            self.primary_failures.append(primary)
            self.safe_evidence({'event': 'REGISTRATION_FAILED', **primary})
            raise

    def inspection_status(self, entry, phase):
        # A failed poll/publication must not replace the primary inspector error.
        try:
            require(phase in ('BEFORE', 'AFTER'), 'DIAGNOSTIC_PUBLICATION_FAILED')
            self.evidence({'event': 'INSPECTION_CHILD_STATUS', 'phase': phase,
                'pid': entry['child'].pid, 'launch_parent': entry.get('launch_parent'),
                'status': child_status(entry['child']), 'ownership_authority': False})
        except Exception:
            self.diagnostic_failures.append('DIAGNOSTIC_STATUS_UNAVAILABLE')

    def observe(self, entry, *, allow_launcher=False):
        checked_capability(self.cap)
        self.inspection_status(entry, 'BEFORE')
        require(not self.diagnostic_failures, 'DIAGNOSTIC_PUBLICATION_FAILED')
        count = 0
        def diagnostic(row):
            nonlocal count
            try:
                count += 1
                require(count <= 16, 'DIAGNOSTIC_OVERFLOW')
                value = validate_inspection_diagnostic(row)
                self.evidence({'event': 'INSPECTION_QUERY', 'pid': entry['child'].pid,
                    'launch_parent': entry.get('launch_parent'), 'diagnostic': value,
                    'ownership_authority': False})
            except Exception:
                self.diagnostic_failures.append('DIAGNOSTIC_PUBLICATION_FAILED')
                raise
        try:
            if self.inspect is inspect_macos:
                observed = self.inspect(entry['child'].pid, diagnostic=diagnostic)
            else:
                observed = self.inspect(entry['child'].pid)  # Explicit offline injection.
        finally:
            self.inspection_status(entry, 'AFTER')
        require(not self.diagnostic_failures, 'DIAGNOSTIC_PUBLICATION_FAILED')
        require(observed is not None, 'PROCESS_ABSENT')
        actual = asdict(observed)
        self.safe_evidence({'event': 'OWNERSHIP_OBSERVATION', 'observed': observed_diagnostic(entry, actual),
                            'launch_parent': entry.get('launch_parent')})
        require(not self.diagnostic_failures, 'DIAGNOSTIC_PUBLICATION_FAILED')
        require(actual['start_time'] and actual['command'] == ' '.join(actual['argv']), 'PROCESS_IDENTITY')
        expected = entry['expected']
        if allow_launcher and entry.get('launcher') and actual['executable'] == entry['launcher']['executable']:
            expected = {**expected, **entry['launcher']}
        for k, v in expected.items():
            require(actual[k] == v, 'PROCESS_IDENTITY')
        return actual

    def verify(self, role, *, require_startup=True):
        entry = self.children[role]
        self.pump(entry)
        require(not entry.get('capture') or not entry['capture'].overflow, 'DIAGNOSTIC_OVERFLOW')
        require(entry['observation'] is not None and self.observe(entry) == entry['observation'], 'PROCESS_IDENTITY')
        require(not require_startup or role in self.startup_pins, 'STARTUP_RECEIPT_REQUIRED')
        if role in self.startup_pins:
            launch, expected = self.startup_pins[role]
            require(read_startup(self.cap, role, launch, self) == expected, 'STARTUP_RECEIPT_CHANGED')
        return entry['child']

    def cleanup(self, port_clear):
        for role in reversed(list(self.children)):
            try:
                entry = self.children[role]
                child = entry['child']
                self.pump(entry)
                self.safe_evidence({'event': 'CHILD_STATUS', 'role': role,
                    'pid': child.pid, 'status': child_status(child),
                    'ownership_verified': entry['observation'] is not None})
                if child.poll() is None:
                    self.verify(role).terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.verify(role).kill()
                        child.wait(timeout=5)
                require(child.poll() is not None, 'CHILD_SURVIVED')
                require(entry['observation'] is not None, 'UNVERIFIED_PARTIAL_START')
                self.evidence({'event': 'EXIT', 'role': role, 'returncode': child.poll()})
                del self.children[role]
            except Exception as error:
                self.failures.append({'role': role, 'failure': 'CLEANUP_UNVERIFIED',
                                      'category': failure_category(error)})
            finally:
                try:
                    self.pump(entry)
                    status = child_status(child)
                    capture = entry.get('capture')
                    if capture is not None and status['state'] == 'CHILD_EXITED':
                        if capture.stream is not None:
                            if not capture.eof:
                                self.diagnostic_failures.append('DIAGNOSTIC_INCOMPLETE')
                            capture.pending.clear()
                            capture.stream.close()
                        else:
                            capture.finish()
                    if capture is not None and capture.overflow:
                        self.diagnostic_failures.append('DIAGNOSTIC_OVERFLOW')
                    self.safe_evidence({'event': 'FINAL_CHILD_STATUS', 'role': role,
                        'pid': child.pid, 'status': status,
                        'ownership_verified': entry['observation'] is not None,
                        'stderr': capture.snapshot() if capture is not None else None})
                except Exception:
                    self.diagnostic_failures.append('DIAGNOSTIC_STATUS_UNAVAILABLE')
        clear = True
        for _ in range(3):
            try:
                clear = (port_clear() is True) and clear
            except Exception:
                clear = False
            self.pause(.2)
        result = {'scope': SCOPE, 'remaining': sorted(self.children), 'failures': self.failures,
                  'port_clear': clear, 'diagnostic_failures': list(self.diagnostic_failures),
                  'clean': not self.children and not self.failures and not self.diagnostic_failures and clear}
        self.safe_evidence({'event': 'CLEANUP', 'result': result})
        result['diagnostic_failures'] = list(self.diagnostic_failures)
        result['clean'] = result['clean'] and not self.diagnostic_failures
        return result


def confinement_profile(runtime, output, interpreter, port):
    template = Path(__file__).with_name('alpha_radar.sb.in').read_text()
    values = {'RUNTIME': str(runtime), 'OUTPUT': str(output), 'INTERPRETER': str(interpreter),
              'ENDPOINT': f'127.0.0.1:{port}'}
    for key, value in values.items():
        template = template.replace('@' + key + '@', json.dumps(value))
    require('@' not in template and '(deny default)' in template and '(allow default)' not in template, 'CONFINEMENT_TEMPLATE')
    return template


def native_identity(cap):
    p, r, _ = checked_capability(cap)
    root = Path(r['root'])
    require(sys.platform == 'darwin' and Path(sys.executable).resolve() == root / r['interpreter'] and
            Path(sys.prefix).resolve().is_relative_to(root), 'NATIVE_RUNTIME')
    names = {v['path'] for v in r['files']}
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path:
            resolved = Path(path).resolve()
            require(resolved.is_relative_to(root) and resolved.relative_to(root).as_posix() in names, 'IMPORTED_CLOSURE')
    expected = confinement_profile(root, p['root'], root / r['interpreter'], p['fixture']['port'])
    require((root / r['confinement']).read_text() == expected, 'CONFINEMENT_SUBSTITUTION')


def listener_owners(port, *, run=subprocess.run):
    result = run(['/usr/sbin/lsof', '-nP', '-iTCP:' + str(port), '-sTCP:LISTEN', '-Fpn'],
                 capture_output=True, text=True, timeout=5,
                 env={'PATH': '/usr/bin:/bin:/usr/sbin', 'LC_ALL': 'C'})
    require(result.returncode in (0, 1) and not result.stderr, 'LISTENER_INSPECTION')
    if result.returncode == 1:
        require(not result.stdout.strip(), 'LISTENER_INSPECTION')
        return []
    rows, pid = [], None
    for line in result.stdout.splitlines():
        if line.startswith('p'):
            require(line[1:].isdigit(), 'LISTENER_PID')
            pid = int(line[1:])
        elif line.startswith('n'):
            require(pid is not None, 'LISTENER_PID')
            rows.append((pid, line[1:]))
    require(rows, 'LISTENER_INSPECTION')
    return rows


def startup(cap, role, launch_parent):
    p, r, _ = checked_capability(cap)
    store(cap, role + '-startup.json', {'role': role, 'launch_parent': launch_parent,
        'pid': os.getpid(), 'parent_pid': os.getppid(), 'argv': [sys.executable, '-B', *sys.argv],
        'cwd': str(Path.cwd()), 'runtime_parent': p['runtime_parent'],
        'package_parent': cap.documents()[2]['package'], 'port': p['fixture']['port']})


def read_startup(cap, role, launch_parent, owned):
    p, _, pins = checked_capability(cap)
    fd = safe_root(p['root'])
    try:
        doc = read_record(fd, role + '-startup.json')
    finally:
        os.close(fd)
    value = verify_envelope(doc, content_hash(doc), parents=pins)
    observed = owned.children[role]['observation']
    require(value == {'role': role, 'launch_parent': launch_parent,
        'pid': observed['pid'], 'parent_pid': observed['parent_pid'],
        'argv': list(observed['argv']), 'cwd': observed['cwd'],
        'runtime_parent': p['runtime_parent'], 'package_parent': pins['package'],
        'port': p['fixture']['port']}, 'STARTUP_RECEIPT_MISMATCH')
    return content_hash(doc)


def verify_tools(tools):
    require(set(tools) == {'/usr/bin/sandbox-exec', '/bin/ps', '/usr/sbin/lsof'}, 'NATIVE_TOOL_SET')
    for name, expected in tools.items():
        p = Path(name)
        st = p.stat(follow_symlinks=False)
        require(not p.is_symlink() and st.st_uid == 0 and not st.st_mode & 0o022 and
                hashlib.sha256(p.read_bytes()).hexdigest() == expected, 'NATIVE_TOOL_PIN')


STARTUP_SCHEMA = 'iios-radar-startup-only-v1'
STARTUP_MODE = 'SYNTHETIC_STARTUP_ONLY'


def startup_only(d):
    # Legacy descriptors remain unchanged. A partial or unknown version never
    # falls back to a full session. The complete descriptor is independently pinned.
    if 'schema' not in d and 'execution_mode' not in d:
        return False
    require(d.get('schema') == STARTUP_SCHEMA and d.get('execution_mode') == STARTUP_MODE,
            'DESCRIPTOR_SCHEMA')
    require(d['clock_mode'] == 'STARTUP_WALL_CLOCK' and
            type(d['maximum_duration_seconds']) is int and
            1 <= d['maximum_duration_seconds'] <= 120, 'NATIVE_DURATION')
    return True


def startup_tls(cap, owned):
    """One numeric-loopback TLS handshake, no HTTP request, DNS or redirect."""
    p, r, _ = checked_capability(cap)
    f = p['fixture']
    require(f['address'] == f['server_name'] == '127.0.0.1', 'LOOPBACK_PIN_REQUIRED')
    cert = Path(r['root']) / f['certificate']
    context = ssl.create_default_context(cafile=str(cert))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, 'FIXTURE_TLS_PIN')
    expected = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text('ascii'))).hexdigest()
    owned.verify('fixture')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw:
        raw.settimeout(5)
        raw.connect(('127.0.0.1', f['port']))
        with context.wrap_socket(raw, server_hostname='127.0.0.1') as channel:
            peer = hashlib.sha256(channel.getpeercert(binary_form=True)).hexdigest()
            require(peer == expected and channel.version() in ('TLSv1.2', 'TLSv1.3'), 'FIXTURE_TLS_PIN')
            result = {'certificate_der_sha256': peer, 'protocol': channel.version(),
                      'hostname_verified': True, 'http_requests': 0}
    owned.verify('fixture')
    return result


def verify_startup_result(value, expected_descriptor):
    """Startup evidence is never a session receipt, even with a valid self hash."""
    require(value['execution_mode'] == STARTUP_MODE and
            value['descriptor_parent'] == expected_descriptor and
            value['classification'] == 'SYNTHETIC_STARTUP_PASS' and
            value['session'] is None and value['requests'] == 0 and
            value['worker_launches'] == 0 and set(value['startup_parents']) == {'fixture'} and
            value['tls']['hostname_verified'] is True and value['tls']['http_requests'] == 0 and
            value['cleanup']['clean'] is True and value['supervisor_exit_code'] == 0 and
            value['failure'] is None and value['primary_failure'] is None and
            value['secondary_failures'] == [] and value['live_readiness'] == 'NOT_QUALIFIED' and
            value['armed'] is False, 'STARTUP_RESULT_MISMATCH')
    return value


def supervise(cap, descriptor, *, popen=subprocess.Popen):
    p, r, pins = checked_capability(cap)
    native_identity(cap)
    verify_tools(descriptor['native_tools'])
    diagnostic_only = startup_only(descriptor)
    require(diagnostic_only or descriptor['clock_mode'] in ('ACCELERATED_LOGICAL_TIME', 'REAL_SESSION_TIME'), 'CLOCK_MODE')
    maximum = descriptor['maximum_duration_seconds']
    require(type(maximum) is int and 1 <= maximum <= 25200, 'NATIVE_DURATION')
    out, runtime = Path(p['root']), Path(r['root'])
    require(not listener_owners(p['fixture']['port']), 'PORT_ALREADY_OWNED')
    executable = runtime / r['interpreter']
    script = next(runtime / name for name in r['source_files'] if Path(name).name == 'alpha_radar_runner.py')
    executable_hash = next(v['sha256'] for v in r['files'] if v['path'] == r['interpreter'])
    sentinel = Path(cap.authorized_root) / 'confinement-denied-input'
    with sentinel.open('xb') as stream:
        stream.write(b'SYNTHETIC_TEST_ONLY\n')
    sentinel.chmod(0o400)
    owned = OwnedProcesses(cap)
    started = time.monotonic()
    failure, session, cleanup, tls = None, None, None, None
    primary_failure, secondary_failures = None, []
    stage, role = 'LAUNCH_INTENT', None
    stopped = [False]
    def stop_handler(*_):
        stopped[0] = True
    previous_handlers = {sig: signal.signal(sig, stop_handler) for sig in (signal.SIGINT, signal.SIGTERM)}
    startup_hashes = {}
    fd = safe_root(out)
    lock = os.open('supervisor.lock', os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for role in (('fixture',) if diagnostic_only else ('fixture', 'worker')):
            require(not stopped[0], 'COOPERATIVE_SHUTDOWN')
            launch = {'scope': SCOPE, 'authority': AUTHORITY, 'descriptor': descriptor, 'output_identity': list(cap.output_identity),
                      'role': role, 'parent_pid': os.getpid(), 'created_at': datetime.now(timezone.utc).isoformat()}
            name = role + '-launch.json'
            stage = 'LAUNCH_INTENT'
            launch_hash = publish(fd, name, launch)
            argv = [str(executable), '-B', str(script), '--child', role,
                    '--descriptor', str(out / name), '--expected-descriptor', launch_hash]
            command = ['/usr/bin/sandbox-exec', '-f', str(runtime / r['confinement']), *argv]
            # stdout stays suppressed; only positively sanitized stderr hints survive.
            owned.evidence({'event': 'LAUNCH_INTENT', 'role': role, 'launch_parent': launch_hash,
                            'creation_state': 'NO_CHILD_CREATED'})
            stage = 'PROCESS_CREATE'
            child = popen(command, cwd=out, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, close_fds=True,
                          env={'PATH': '/usr/bin:/bin:/usr/sbin', 'LC_ALL': 'C', 'TZ': 'UTC'})
            stage = 'OWNERSHIP_REGISTER'
            owned.register(role, child, argv=argv, cwd=out, executable=executable,
                           stderr=child.stderr, launch_parent=launch_hash,
                           executable_hash=executable_hash, launcher={'argv': tuple(command),
                               'executable': '/usr/bin/sandbox-exec',
                               'executable_hash': descriptor['native_tools']['/usr/bin/sandbox-exec']})
            stage = 'STARTUP_VERIFY'
            deadline = time.monotonic() + 10
            while not (out / (role + '-startup.json')).exists() and time.monotonic() < deadline:
                owned.verify(role, require_startup=False)
                time.sleep(.05)
            startup_hashes[role] = read_startup(cap, role, launch_hash, owned)
            owned.startup_pins[role] = (launch_hash, startup_hashes[role])
            if role == 'fixture':
                stage = 'LISTENER_VERIFY'
                require(listener_owners(p['fixture']['port']) == [(child.pid, '127.0.0.1:' + str(p['fixture']['port']))], 'LISTENER_OWNER_MISMATCH')
            stage = 'PARENT_ACK'
            store(cap, role + '-ack.json', {'role': role, 'launch_parent': launch_hash,
                                          'startup_parent': startup_hashes[role]})
        if diagnostic_only:
            stage = 'TLS_HANDSHAKE'
            require(not stopped[0] and time.monotonic() - started < maximum, 'NATIVE_SESSION_TIMEOUT')
            tls = startup_tls(cap, owned)
            require(time.monotonic() - started < maximum, 'NATIVE_SESSION_TIMEOUT')
        else:
            stage = 'SESSION_WAIT'
            worker = owned.children['worker']['child']
            while worker.poll() is None:
                require(not stopped[0], 'COOPERATIVE_SHUTDOWN')
                require(time.monotonic() - started < maximum, 'NATIVE_SESSION_TIMEOUT')
                owned.verify('worker')
                owned.verify('fixture')
                time.sleep(.2)
            require(worker.returncode == 0, 'WORKER_FAILED')
            doc = read_record(fd, 'session.json')
            session = verify_envelope(doc, content_hash(doc), parents=pins)
            require(session['classification'] == 'SYNTHETIC_PASS' and session['requests'] == 475, 'SESSION_INCOMPLETE')
    except BaseException as error:
        failure = 'SYNTHETIC_NATIVE_FAILED'
        primary_failure = {'stage': stage, 'role': role, 'category': failure_category(error),
                           'creation_state': 'CHILD_CREATED' if role in owned.children else 'NO_CHILD_CREATED'}
        try:
            store(cap, 'native-failure.json', {'failure': failure, 'primary_failure': primary_failure})
        except Exception:
            secondary_failures.append('FAILURE_EVIDENCE_UNAVAILABLE')
    finally:
        try:
            cleanup = owned.cleanup(lambda: not listener_owners(p['fixture']['port']))
        except Exception as error:
            secondary_failures.append(failure_category(error))
            cleanup = {'clean': False, 'remaining': sorted(owned.children),
                       'failure': 'CLEANUP_UNVERIFIED', 'port_clear': False}
        finally:
            os.close(lock)
            os.close(fd)
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
    result = {'classification': 'SYNTHETIC_PASS' if failure is None and not secondary_failures and cleanup['clean'] else 'SYNTHETIC_FAILED',
              'failure': failure, 'primary_failure': primary_failure, 'secondary_failures': secondary_failures,
              'supervisor_exit_code': 0 if failure is None and not secondary_failures and cleanup['clean'] else 1,
              'session': session, 'startup_parents': startup_hashes,
              'cleanup': cleanup, 'clock_mode': descriptor['clock_mode'],
              'live_readiness': 'NOT_QUALIFIED', 'armed': False,
              'actual_elapsed_seconds': time.monotonic() - started}
    if diagnostic_only:
        result.update(execution_mode=STARTUP_MODE, descriptor_parent=content_hash(descriptor),
                      requests=0, worker_launches=0, tls=tls,
                      classification='SYNTHETIC_STARTUP_PASS' if result['supervisor_exit_code'] == 0 else 'SYNTHETIC_STARTUP_FAILED')
    store(cap, 'final-audit.json', result)
    return result


def descriptor_schema(d):
    fields = {'package', 'runtime', 'expected', 'authorized_root', 'native_tools',
              'clock_mode', 'maximum_duration_seconds'}
    if startup_only(d):
        fields |= {'schema', 'execution_mode'}
    require(set(d) == fields, 'DESCRIPTOR_SCHEMA')


def require_confinement(cap):
    """Read-only OS policy queries; never read credentials or probe a provider."""
    import ctypes
    p, r, _ = checked_capability(cap)
    sentinel = Path(cap.authorized_root) / 'confinement-denied-input'
    require(sentinel.is_file(), 'CONFINEMENT_SENTINEL_MISSING')
    library = ctypes.CDLL('/usr/lib/libsandbox.dylib', use_errno=True)
    library.sandbox_check.restype = ctypes.c_int
    for operation, target in (('file-read-data', sentinel),
                              ('file-write-data', sentinel),
                              ('process-exec', Path('/bin/sh'))):
        require(library.sandbox_check(os.getpid(), operation.encode(), 1,
                                      str(target).encode()) != 0, 'OS_CONFINEMENT_REQUIRED')
    require(library.sandbox_check(os.getpid(), b'network-outbound', 0) != 0,
            'GENERAL_NETWORK_MUST_BE_DENIED')


def await_parent_ack(cap, role, launch_parent, *, monotonic=time.monotonic, pause=time.sleep):
    p, _, pins = checked_capability(cap)
    fd = safe_root(p['root'])
    try:
        startup_doc = read_record(fd, role + '-startup.json')
        startup_parent = content_hash(startup_doc)
        deadline = monotonic() + 10
        while monotonic() < deadline:
            try:
                doc = read_record(fd, role + '-ack.json')
            except FileNotFoundError:
                pause(.05)
                continue
            value = verify_envelope(doc, content_hash(doc), parents=pins)
            require(value == {'role': role, 'launch_parent': launch_parent,
                              'startup_parent': startup_parent}, 'PARENT_ACK_MISMATCH')
            return
        raise ValueError('PARENT_ACK_TIMEOUT')
    finally:
        os.close(fd)


def child_main(launch, role, launch_parent):
    require(set(launch) == {'scope', 'authority', 'descriptor', 'output_identity', 'role', 'parent_pid', 'created_at'} and
            launch['scope'] == SCOPE and launch['authority'] == AUTHORITY and
            launch['role'] == role and launch['parent_pid'] == os.getppid(), 'CHILD_LAUNCH')
    early_diagnostic('CHILD_ADMISSION_BEGIN')
    d = launch['descriptor']
    descriptor_schema(d)
    require(not startup_only(d) or role == 'fixture', 'CHILD_ROLE')
    identities = verify_inputs(d['package'], d['runtime'], d['expected'], d['authorized_root'])
    cap = SyntheticCapability(canonical(d['package']), canonical(d['runtime']), canonical(d['expected']),
                              d['authorized_root'], identities, tuple(launch['output_identity']))
    early_diagnostic('CHILD_ADMISSION_VERIFIED')
    diagnostic = ChildDiagnostics(cap, role, launch_parent)
    try:
        diagnostic.emit('RUNTIME_VERIFY')
        native_identity(cap)
        diagnostic.emit('CONFINEMENT_CHECK')
        require_confinement(cap)
        stopped = [False]
        require(type(d['maximum_duration_seconds']) is int and 1 <= d['maximum_duration_seconds'] <= 25200, 'NATIVE_DURATION')
        child_deadline = time.monotonic() + d['maximum_duration_seconds']
        def stop_handler(*_):
            stopped[0] = True
        def stop():
            return stopped[0] or time.monotonic() >= child_deadline
        def ready():
            diagnostic.emit('STARTUP_PUBLISH')
            startup(cap, role, launch_parent)
            diagnostic.emit('PARENT_ACK')
            await_parent_ack(cap, role, launch_parent)
        signal.signal(signal.SIGTERM, stop_handler)
        signal.signal(signal.SIGINT, stop_handler)
        if role == 'fixture':
            from alpha_radar_fixture import serve
            serve(cap, stop, ready, stage=diagnostic.emit)
            return 0
        require(role == 'worker', 'CHILD_ROLE')
        ready()
        if d['clock_mode'] == 'ACCELERATED_LOGICAL_TIME':
            now = [utc(d['package']['plan']['rows'][0]['valid_from'])]
            clock = lambda: now[0].isoformat()
            def wait(seconds):
                now[0] += timedelta(seconds=seconds)
        else:
            require(d['clock_mode'] == 'REAL_SESSION_TIME', 'CLOCK_MODE')
            clock = lambda: datetime.now(timezone.utc).isoformat()
            wait = time.sleep
        diagnostic.emit('WORKER_SESSION')
        result = Session(cap, clock=clock, wait=wait, stop=stop).run()
        return 0 if result['classification'] == 'SYNTHETIC_PASS' else 1
    except BaseException as error:
        diagnostic.failure(error)
        raise


def read_descriptor(path, expected):
    """Walk from the exact admitted root using no-follow directory descriptors."""
    from alpha_radar_admission import exact_root, contained
    path = Path(path)
    root = next((v for v in path.parents if v.parent == Path('/private/tmp')), None)
    require(root is not None, 'DESCRIPTOR_ROOT')
    exact_root(root)
    contained(root, path)
    parts = path.relative_to(root).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        require(os.stat(parts[-1], dir_fd=fd, follow_symlinks=False).st_size <= 8_000_000, 'DESCRIPTOR_SIZE')
        return read_record(fd, parts[-1], expected_hash=expected)
    finally:
        os.close(fd)


# Explicitly separate from every confinement-qualified descriptor and receipt.
LIFECYCLE_SCOPE = 'CI_NATIVE_LIFECYCLE_ONLY'
LIFECYCLE_FLAGS = {'scope': LIFECYCLE_SCOPE, 'production_qualified': False,
    'os_confinement': 'UNQUALIFIED', 'provider_access': False, 'credential_access': False,
    'worker_launches': 0, 'requests_attempted': 0, **AUTHORITY}
LIFECYCLE_ENV = {'PATH': '/usr/bin:/bin:/usr/sbin', 'LC_ALL': 'C', 'TZ': 'UTC'}
LIFECYCLE_CONTEXT = {'GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT', 'RUNNER_OS', 'RUNNER_ARCH',
                     'GITHUB_RUN_ATTEMPT', 'GITHUB_RUN_ID', 'GITHUB_SHA', 'GITHUB_REF'}


def lifecycle_environment(context):
    require(type(context) is dict and set(context) == LIFECYCLE_CONTEXT and
            all(type(v) is str for v in context.values()), 'LIFECYCLE_ENVIRONMENT')
    require(context['GITHUB_ACTIONS'] == 'true' and context['RUNNER_ENVIRONMENT'] == 'github-hosted'
            and context['RUNNER_OS'] == 'macOS' and context['RUNNER_ARCH'] == 'ARM64'
            and context['GITHUB_RUN_ATTEMPT'] == '1' and re.fullmatch(r'[1-9][0-9]{0,19}', context['GITHUB_RUN_ID'])
            and re.fullmatch('[a-f0-9]{40}', context['GITHUB_SHA'])
            and context['GITHUB_REF'] == 'refs/heads/feature/iios-provider-gateway-superbatch-1',
            'LIFECYCLE_HOSTED_ONLY')
    # macOS initializes this field in a fresh interpreter. Pin its nonsensitive
    # value from the current UID; never inherit an ambient value or allow extras.
    return {**LIFECYCLE_ENV, '__CF_USER_TEXT_ENCODING': f'0x{os.getuid():X}:0x0:0x0', **context}


def lifecycle_descriptor(d):
    require(type(d) is dict and set(d) == {'schema', 'execution_mode', 'package', 'runtime',
        'expected', 'authorized_root', 'native_tools', 'maximum_duration_seconds', 'context'}, 'LIFECYCLE_DESCRIPTOR')
    require(d['schema'] == 'iios-ci-native-lifecycle-v1' and d['execution_mode'] == LIFECYCLE_SCOPE
            and type(d['maximum_duration_seconds']) is int and 1 <= d['maximum_duration_seconds'] <= 120,
            'LIFECYCLE_DESCRIPTOR')
    lifecycle_environment(d['context'])
    require(d['package']['source_commit'] == d['context']['GITHUB_SHA'], 'LIFECYCLE_SOURCE')
    verify_inputs(d['package'], d['runtime'], d['expected'], d['authorized_root'])
    verify_tools(d['native_tools'])  # hash only; sandbox-exec is never launched here
    return {**d['expected'], 'lifecycle_descriptor': content_hash(d)}


def lifecycle_envelope(value, parents):
    from alpha_radar_admission import synthetic_document
    synthetic_document(value)
    doc = {'schema': 'iios-ci-native-lifecycle-receipt-v1', **LIFECYCLE_FLAGS,
           'parents': parents, 'value': value}
    return {**doc, 'content_hash': content_hash(doc)}


def verify_lifecycle_receipt(doc, expected, parents):
    require(content_hash(doc) == expected and type(doc) is dict and set(doc) ==
            {'schema', 'parents', 'value', 'content_hash', *LIFECYCLE_FLAGS}, 'LIFECYCLE_RECEIPT')
    require(all(type(doc[k]) is type(v) and doc[k] == v for k, v in LIFECYCLE_FLAGS.items())
            and doc['parents'] == parents and doc['schema'] == 'iios-ci-native-lifecycle-receipt-v1',
            'LIFECYCLE_RECEIPT')
    require(doc == lifecycle_envelope(doc['value'], parents), 'LIFECYCLE_RECEIPT')
    return doc['value']


def lifecycle_store(cap, parents, name, value):
    require(type(cap) is SyntheticCapability, 'SYNTHETIC_CAPABILITY_REQUIRED')
    p, _, _ = cap.documents()
    fd = safe_root(p['root'])
    try:
        st = os.fstat(fd)
        require((st.st_dev, st.st_ino) == cap.output_identity, 'OUTPUT_REPLACED')
        verify_destination(fd, p['root'])
        return publish(fd, name, lifecycle_envelope(value, parents))
    finally:
        os.close(fd)


def lifecycle_read(cap, parents, name, expected_value):
    expected = lifecycle_envelope(expected_value, parents)
    fd = safe_root(cap.documents()[0]['root'])
    try:
        doc = read_record(fd, name, expected_hash=content_hash(expected))
    finally:
        os.close(fd)
    verify_lifecycle_receipt(doc, content_hash(expected), parents)
    return content_hash(expected)


def lifecycle_startup_value(cap, launch_parent, identity):
    p, _, pins = cap.documents()
    return {'event': 'STARTUP', 'launch_parent': launch_parent, 'pid': identity['pid'],
        'parent_pid': identity['parent_pid'], 'argv': list(identity['argv']), 'cwd': identity['cwd'],
        'runtime_parent': pins['runtime'], 'fixture_parent': pins['fixture'],
        'package_parent': pins['package'], 'port': p['fixture']['port']}


class LifecycleOwnedProcesses(OwnedProcesses):
    def __init__(self, cap, parents, **kwargs):
        super().__init__(cap, **kwargs)
        self.lifecycle_parents = parents

    def capture_for(self, child, stderr):
        return LifecycleStreams(child)

    def pump(self, entry):
        super().pump(entry)
        capture = entry.get('capture')
        if isinstance(capture, LifecycleStreams): capture.check()

    def evidence(self, value):
        self.counter += 1
        lifecycle_store(self.cap, self.lifecycle_parents, f'lc-event-{self.counter:04d}.json',
                        {**value, 'recorded_at': datetime.now(timezone.utc).isoformat()})

    def verify(self, role, *, require_startup=True):
        require(role == 'fixture', 'LIFECYCLE_WORKER_FORBIDDEN')
        entry = self.children[role]
        self.pump(entry)
        require(entry['observation'] is not None and self.observe(entry) == entry['observation'], 'PROCESS_IDENTITY')
        require(not require_startup or role in self.startup_pins, 'STARTUP_RECEIPT_REQUIRED')
        if role in self.startup_pins:
            launch, expected = self.startup_pins[role]
            require(lifecycle_read(self.cap, self.lifecycle_parents, 'lc-startup.json',
                lifecycle_startup_value(self.cap, launch, entry['observation'])) == expected, 'STARTUP_RECEIPT_CHANGED')
        return entry['child']

    def cleanup(self, port_clear):
        exits = []
        # No signals in lifecycle-only mode. A failed cooperative stop remains
        # failed; there is no unverified termination fallback.
        for role, entry in list(self.children.items()):
            child = entry['child']
            try:
                self.pump(entry)
                if child.poll() is None:
                    self.verify(role)
                    lifecycle_store(self.cap, self.lifecycle_parents, 'lc-stop.json',
                        {'event': 'STOP', 'launch_parent': entry['launch_parent']})
                    child.wait(timeout=10)
                require(child.poll() == 0 and entry['observation'] is not None, 'COOPERATIVE_SHUTDOWN')
                lifecycle_read(self.cap, self.lifecycle_parents, 'lc-child-exit.json', {'returncode': 0})
                exits.append({'pid': child.pid, 'returncode': child.poll(), 'ownership_verified': True})
                del self.children[role]
            except Exception as error:
                self.failures.append({'role': role, 'category': failure_category(error)})
            finally:
                capture = entry.get('capture')
                try:
                    self.pump(entry)
                    if capture and child.poll() is not None:
                        capture.drain()
                        if capture.overflow: self.diagnostic_failures.append('DIAGNOSTIC_OVERFLOW')
                        if isinstance(capture, LifecycleStreams):
                            if not capture.eof: self.diagnostic_failures.append('DIAGNOSTIC_INCOMPLETE')
                        elif capture.stream is not None and not capture.eof:
                            self.diagnostic_failures.append('DIAGNOSTIC_INCOMPLETE')
                except Exception as error:
                    self.diagnostic_failures.append(failure_category(error))
                finally:
                    try:
                        if isinstance(capture, LifecycleStreams): capture.close()
                        elif capture and capture.stream is not None:
                            capture.pending.clear(); capture.stream.close()
                        elif capture: capture.finish()
                    except Exception as error:
                        self.diagnostic_failures.append(failure_category(error))
                self.safe_evidence({'event': 'FINAL_CHILD_STATUS', 'status': child_status(child),
                                    'diagnostics': capture.snapshot() if capture else None})
        clear = []
        for _ in range(3):
            try: clear.append(port_clear() is True)
            except Exception: clear.append(False)
            self.pause(.2)
        return {'scope': LIFECYCLE_SCOPE, 'exits': exits, 'remaining': sorted(self.children),
            'failures': self.failures, 'diagnostic_failures': self.diagnostic_failures,
            'port_clear_observations': clear, 'signals': 0,
            'clean': bool(exits) and not self.children and not self.failures and
                     not self.diagnostic_failures and clear == [True, True, True]}


def lifecycle_audit(runtime, output, endpoint, role, *, launch_argv=None, child_pid=lambda: None, context=None):
    """Application-only guard, never evidence of OS confinement.

    Child has no subprocess or signal allowance. Supervisor inspection uses
    existing verified ownership logic; all lifecycle processes reject DNS and
    public sockets. Descriptor-relative writes are resolved by the companion
    checked-open wrapper, never by granting arbitrary relative names.
    """
    require(role in ('fixture', 'supervisor') and endpoint[0] == '127.0.0.1'
            and type(endpoint[1]) is int and 1024 <= endpoint[1] <= 65535, 'LOOPBACK_PIN_REQUIRED')
    root, out = Path(runtime).resolve(), Path(output).resolve()
    active = []; directories = {}; original = os.open; launched = [False]
    def checked_open(path, flags, mode=0o777, *, dir_fd=None):
        resolved = None
        if dir_fd is None:
            resolved = Path(path).resolve()
        else:
            require(dir_fd in directories, 'LIFECYCLE_DIRECTORY')
            parent, identity = directories[dir_fd]
            st = os.fstat(dir_fd)
            require((st.st_dev, st.st_ino) == identity, 'LIFECYCLE_DIRECTORY')
            resolved = (parent / path).resolve()
        active.append(resolved)
        try: fd = original(path, flags, mode, dir_fd=dir_fd)
        finally: active.pop()
        import stat
        st = os.fstat(fd)
        if stat.S_ISDIR(st.st_mode): directories[fd] = (resolved, (st.st_dev, st.st_ino))
        return fd
    def audit(event, args):
        if event.startswith('socket.get') or event in ('socket.sethostname', 'os.system', 'os.posix_spawn',
                'os.kill', 'os.killpg', 'os.remove', 'os.rename', 'os.rmdir', 'os.link', 'os.symlink'):
            raise PermissionError('LIFECYCLE_BOUNDARY')
        if event == 'subprocess.Popen':
            require(role == 'supervisor' and len(args) == 4, 'LIFECYCLE_BOUNDARY')
            executable, argv, cwd, env = args
            argv = tuple(argv)
            if launch_argv is not None and argv == tuple(launch_argv):
                require(not launched[0] and executable == launch_argv[0] and str(cwd) == str(out)
                        and env == lifecycle_environment(context), 'LIFECYCLE_BOUNDARY')
                launched[0] = True
            else:
                pid = child_pid()
                commands = [('/usr/sbin/lsof', '-nP', '-iTCP:'+str(endpoint[1]), '-sTCP:LISTEN', '-Fpn')]
                if type(pid) is int and pid > 0:
                    commands += [('/bin/ps', '-ww', '-p', str(pid), '-o', field)
                                 for field in ('lstart=', 'ppid=', 'comm=')]
                    commands += [('/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn')]
                require(argv in commands and executable == argv[0] and cwd is None and
                        env in (LIFECYCLE_ENV, {k:v for k,v in LIFECYCLE_ENV.items() if k != 'TZ'}),
                        'LIFECYCLE_BOUNDARY')
        if event == 'ctypes.dlopen':
            require(role == 'supervisor' and args == ('/usr/lib/libSystem.B.dylib',), 'LIFECYCLE_BOUNDARY')
        if event == 'socket.__new__':
            require(args[1] == socket.AF_INET and args[2] == socket.SOCK_STREAM and args[3] in (0, 6), 'LIFECYCLE_BOUNDARY')
        if event in ('socket.connect', 'socket.bind'):
            require(tuple(args[1]) == tuple(endpoint) and
                    ((event == 'socket.bind' and role == 'fixture') or
                     (event == 'socket.connect' and role == 'supervisor')), 'LIFECYCLE_BOUNDARY')
        if event == 'open' and not isinstance(args[0], int):
            path, mode, flags = args
            target = active[-1] if active else Path(path).resolve()
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if writing:
                require(target.parent == out and re.fullmatch(r'lc-[a-z0-9-]+\.json', target.name)
                        and flags & os.O_EXCL and flags & os.O_NOFOLLOW, 'LIFECYCLE_WRITE')
            else:
                require(target.is_relative_to(root) or target.is_relative_to(out) or
                        str(target) in ('/dev/null', '/bin/ps', '/usr/sbin/lsof', '/usr/bin/sandbox-exec'), 'LIFECYCLE_READ')
        if event in ('os.mkdir', 'os.chmod', 'os.truncate'):
            raise PermissionError('LIFECYCLE_WRITE')
    return audit, checked_open


def lifecycle_child(launch, launch_parent):
    require(set(launch) == {'descriptor', 'output_identity', 'parent_pid', *LIFECYCLE_FLAGS}
            and all(type(launch[k]) is type(v) and launch[k] == v for k, v in LIFECYCLE_FLAGS.items())
            and launch['parent_pid'] == os.getppid(), 'LIFECYCLE_LAUNCH')
    d = launch['descriptor']; parents = lifecycle_descriptor(d)
    expected_environment = lifecycle_environment(d['context'])
    require(set(os.environ) == set(expected_environment), 'LIFECYCLE_ENVIRONMENT')
    require(all(os.environ[k] == v for k,v in expected_environment.items()), 'LIFECYCLE_ENVIRONMENT')
    identities = verify_inputs(d['package'], d['runtime'], d['expected'], d['authorized_root'])
    cap = SyntheticCapability(canonical(d['package']), canonical(d['runtime']), canonical(d['expected']),
        d['authorized_root'], identities, tuple(launch['output_identity']))
    native_identity(cap)
    from alpha_radar_fixture import serve
    native_identity(cap)
    p, r, _ = cap.documents()
    audit, opened = lifecycle_audit(r['root'], p['root'], ('127.0.0.1', p['fixture']['port']), 'fixture')
    os.open = opened; sys.addaudithook(audit)
    deadline = time.monotonic() + d['maximum_duration_seconds']
    sequence = [0]
    def stage(value):
        require(value in STAGES, 'CHILD_DIAGNOSTIC_STAGE'); sequence[0] += 1
        require(sequence[0] <= 64, 'DIAGNOSTIC_OVERFLOW')
        lifecycle_store(cap, parents, f'lc-child-{sequence[0]:04d}.json', {'stage': value})
    def stop():
        if time.monotonic() >= deadline: return True
        try:
            lifecycle_read(cap, parents, 'lc-stop.json', {'event': 'STOP', 'launch_parent': launch_parent})
            return True
        except FileNotFoundError: return False
    def ready():
        value = lifecycle_startup_value(cap, launch_parent, {'pid': os.getpid(), 'parent_pid': os.getppid(),
            'argv': [sys.executable, '-B', *sys.argv], 'cwd': str(Path.cwd())})
        startup_parent = lifecycle_store(cap, parents, 'lc-startup.json', value)
        until = time.monotonic() + 10
        while time.monotonic() < until:
            try:
                lifecycle_read(cap, parents, 'lc-ack.json', {'event': 'ACK', 'launch_parent': launch_parent,
                                                         'startup_parent': startup_parent})
                return
            except FileNotFoundError: time.sleep(.05)
        raise ValueError('PARENT_ACK_TIMEOUT')
    try:
        serve(cap, stop, ready, stage=stage)
        lifecycle_store(cap, parents, 'lc-child-exit.json', {'returncode': 0})
        return 0
    except BaseException as error:
        lifecycle_store(cap, parents, 'lc-child-failure.json', {'category': failure_category(error)})
        raise


def lifecycle_supervise(cap, d, *, popen=subprocess.Popen):
    parents = lifecycle_descriptor(d); native_identity(cap)
    expected_environment = lifecycle_environment(d['context'])
    require(set(os.environ) == set(expected_environment), 'LIFECYCLE_ENVIRONMENT')
    require(all(os.environ[k] == v for k,v in expected_environment.items()), 'LIFECYCLE_ENVIRONMENT')
    p, r, _ = cap.documents(); out = Path(p['root']); runtime = Path(r['root'])
    require(not listener_owners(p['fixture']['port']), 'PORT_ALREADY_OWNED')
    owned = LifecycleOwnedProcesses(cap, parents)
    launch = {**LIFECYCLE_FLAGS, 'descriptor': d, 'output_identity': list(cap.output_identity), 'parent_pid': os.getpid()}
    fd = safe_root(out)
    try: launch_parent = publish(fd, 'lc-launch.json', launch)
    finally: os.close(fd)
    executable = runtime / r['interpreter']; script = next(runtime/name for name in r['source_files'] if Path(name).name == 'alpha_radar_runner.py')
    argv = [str(executable), '-B', str(script), '--ci-lifecycle-only', '--child', 'fixture',
            '--descriptor', str(out/'lc-launch.json'), '--expected-descriptor', launch_parent]
    child = None; primary = None; cleanup_failure = None; tls = None; startup_parent = None; listener = None
    stage = 'PROCESS_CREATE'
    audit, opened = lifecycle_audit(runtime, out, ('127.0.0.1', p['fixture']['port']), 'supervisor',
        launch_argv=argv, child_pid=lambda: child.pid if child is not None else None, context=d['context'])
    os.open = opened; sys.addaudithook(audit)
    try:
        child = popen(argv, cwd=out, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, close_fds=True, env=lifecycle_environment(d['context']))
        # Immediate EOF; no child input and no DEVNULL device permission.
        close_lifecycle_stdin(child)
        stage = 'OWNERSHIP_REGISTER'
        owned.register('fixture', child, argv=argv, cwd=out, executable=executable,
            executable_hash=next(v['sha256'] for v in r['files'] if v['path'] == r['interpreter']),
            stderr=child.stderr, launch_parent=launch_parent)
        stage = 'STARTUP_VERIFY'; until = time.monotonic()+10
        while not (out/'lc-startup.json').exists() and time.monotonic() < until:
            owned.verify('fixture', require_startup=False); time.sleep(.05)
        startup_parent = lifecycle_read(cap, parents, 'lc-startup.json',
            lifecycle_startup_value(cap, launch_parent, owned.children['fixture']['observation']))
        owned.startup_pins['fixture'] = (launch_parent, startup_parent)
        stage = 'LISTENER_VERIFY'; listener = listener_owners(p['fixture']['port'])
        require(listener == [(child.pid, '127.0.0.1:'+str(p['fixture']['port']))], 'LISTENER_OWNER_MISMATCH')
        lifecycle_store(cap, parents, 'lc-ack.json', {'event': 'ACK', 'launch_parent': launch_parent,
                                                   'startup_parent': startup_parent})
        stage = 'TLS_HANDSHAKE'; tls = startup_tls(cap, owned)
    except BaseException as error:
        primary = {'stage': stage, 'category': failure_category(error)}
    try:
        cleanup = owned.cleanup(lambda: not listener_owners(p['fixture']['port']))
        if not cleanup['clean']: cleanup_failure = 'LIFECYCLE_CLEANUP_FAILED'
    except Exception as error:
        cleanup_failure = failure_category(error); cleanup = {'clean': False}
    result = {'classification': 'LIFECYCLE_PASS' if primary is None and cleanup_failure is None and cleanup['clean'] else 'LIFECYCLE_FAILED',
        'primary_failure': primary, 'cleanup_failure': cleanup_failure, 'cleanup': cleanup,
        'fixture_status': child_status(child) if child else None, 'startup_parent': startup_parent,
        'tls': tls, 'listener': listener, 'descriptor_parent': content_hash(d)}
    lifecycle_store(cap, parents, 'lc-final.json', result)
    return result


def lifecycle_main(d, expected, child):
    if child:
        require(child == 'fixture', 'LIFECYCLE_WORKER_FORBIDDEN')
        return lifecycle_child(d, expected)
    lifecycle_descriptor(d)
    cap = admit(d['package'], d['runtime'], expected=d['expected'], authorized_root=d['authorized_root'])
    result = lifecycle_supervise(cap, d)
    return 0 if result['classification'] == 'LIFECYCLE_PASS' else 1


# This capability is deliberately not a lifecycle or confinement qualification.
FULL_SCOPE = 'CI_SYNTHETIC_FULL_SESSION_ONLY'
FULL_TIMING = 'ACCELERATED_LOGICAL_TIME_ONLY'
FULL_DEADLINE_UNIT = 'MONOTONIC_NANOSECONDS'
FULL_NANOSECONDS = 1_000_000_000
FULL_FLAGS = {'scope': FULL_SCOPE, 'production_qualified': False,
    'os_confinement': 'UNQUALIFIED', 'credential_access': False, 'provider_access': False,
    'timing_proof': FULL_TIMING, **AUTHORITY}


def full_budget(d):
    """Pinned native-job deadlines; logical market time cannot extend them."""
    import math
    b = d['budget']
    require(type(b) is dict and set(b) == {'schema','source_commit','run_id','run_attempt',
        'start_monotonic','prepared_monotonic','hard_deadline','work_deadline','cleanup_deadline',
        'cleanup_seconds','export_seconds','real_clock_seconds','work_seconds','deadline_unit',
        'prepared_monotonic_ns','startup_deadline_ns'}, 'FULL_JOB_BUDGET')
    require(b['schema'] == 'iios-native-job-budget-v2' and
        b['source_commit'] == d['context']['GITHUB_SHA'] and b['run_id'] == d['context']['GITHUB_RUN_ID']
        and type(b['run_attempt']) is int and b['run_attempt'] == 1, 'FULL_JOB_BUDGET')
    for key in ('start_monotonic','prepared_monotonic','hard_deadline','work_deadline','cleanup_deadline'):
        require(type(b[key]) in (int,float) and math.isfinite(b[key]) and b[key] > 0,'FULL_JOB_BUDGET')
    require(b['deadline_unit'] == FULL_DEADLINE_UNIT and
        type(b['prepared_monotonic_ns']) is int and type(b['startup_deadline_ns']) is int and
        0 < b['prepared_monotonic_ns'] <= 2**63-1 and
        0 < b['startup_deadline_ns'] <= 2**63-1 and
        b['prepared_monotonic_ns'] == round(b['prepared_monotonic']*FULL_NANOSECONDS) and
        b['startup_deadline_ns'] == b['prepared_monotonic_ns']+
            (b['real_clock_seconds']+300)*FULL_NANOSECONDS,
        'FULL_JOB_BUDGET')
    require(b['cleanup_seconds'] == b['export_seconds'] == 180 and b['real_clock_seconds'] == 65
        and b['work_seconds'] == d['maximum_duration_seconds'] == 3300 and
        0 <= b['prepared_monotonic']-b['start_monotonic'] <= 300 and
        b['hard_deadline'] == b['start_monotonic']+4440 and
        b['work_deadline'] == b['prepared_monotonic']+3665 and
        b['cleanup_deadline'] == b['work_deadline']+180 and
        b['cleanup_deadline']+180 <= b['hard_deadline'], 'FULL_JOB_BUDGET')
    require(type(d['validation_parent']) is str and
        re.fullmatch('[a-f0-9]{64}',d['validation_parent']), 'FULL_VALIDATION_PARENT')
    return b


def full_launch_budget(d, *, monotonic=time.monotonic):
    b = full_budget(d); now = monotonic()
    require(b['prepared_monotonic'] <= now and b['work_deadline']-now >= 3365,
            'FULL_INSUFFICIENT_BUDGET')
    return b


def full_startup_deadline(d):
    """One descriptor-bound deadline shared by child and supervisor startup."""
    b = full_budget(d)
    deadline = b['startup_deadline_ns'] / FULL_NANOSECONDS
    require(b['startup_deadline_ns'] < round(b['work_deadline']*FULL_NANOSECONDS),
            'FULL_JOB_BUDGET')
    return deadline



def full_phase(descriptor, role, *, monotonic_ns=time.monotonic_ns):
    """Fresh phase identity published inside the independently pinned launch."""
    require(role in ('fixture','worker'), 'FULL_ROLE')
    b=full_budget(descriptor); start=monotonic_ns()
    phase={'schema':'iios-full-startup-phase-v1','role':role,
        'descriptor_parent':content_hash(descriptor),'unit':FULL_DEADLINE_UNIT,
        'start_ns':start,'deadline_ns':start+100*FULL_NANOSECONDS}
    full_phase_deadline(descriptor,role,phase)
    return phase


def full_phase_deadline(descriptor, role, phase):
    b=full_budget(descriptor)
    require(type(phase) is dict and set(phase)=={
        'schema','role','descriptor_parent','unit','start_ns','deadline_ns'} and
        phase['schema']=='iios-full-startup-phase-v1' and phase['role']==role and
        role in ('fixture','worker') and phase['descriptor_parent']==content_hash(descriptor) and
        phase['unit']==FULL_DEADLINE_UNIT and
        type(phase['start_ns']) is int and type(phase['deadline_ns']) is int and
        b['prepared_monotonic_ns'] <= phase['start_ns'] < phase['deadline_ns'] <= 2**63-1 and
        phase['deadline_ns']==phase['start_ns']+100*FULL_NANOSECONDS and
        phase['deadline_ns'] < round(b['work_deadline']*FULL_NANOSECONDS),
        'FULL_STARTUP_PHASE')
    return phase['deadline_ns']/FULL_NANOSECONDS


def advance_full_clock(session, now, seconds):
    """Jump only to the scheduler's exact next eligible target; no real sleep.

    The shared scheduler still checks stop, window, order and pacing. Actual UTC,
    monotonic wire timeouts and cleanup clocks are independent of this list.
    """
    require(type(session) is FullSession and type(seconds) in (int,float) and 0 < seconds <= 1,
            'FULL_CLOCK')
    require(0 <= session.next_slot < 475, 'FULL_REQUEST_ORDER')
    target = utc(session.p['plan']['rows'][session.next_slot]['valid_from'])
    if len(session.rate.starts) >= 3:
        target = max(target,datetime.fromtimestamp(session.rate.starts[-3]+60,timezone.utc))
    gap = (target-now[0]).total_seconds()
    require(gap > 0 and seconds == min(1.0,gap), 'FULL_CLOCK')
    now[0] = target


class FullCancellation:
    """Handlers request cooperative shutdown; never send a process signal."""
    def __init__(self): self.requested = False; self.previous = {}
    def __call__(self): return self.requested
    def request(self, *_): self.requested = True
    def __enter__(self):
        import signal
        for number in (signal.SIGINT,signal.SIGTERM):
            self.previous[number] = signal.getsignal(number)
            signal.signal(number,self.request)
        return self
    def __exit__(self,*_):
        import signal
        for number,handler in self.previous.items(): signal.signal(number,handler)


def request_full_cancel(d, expected, supervisor_pid):
    """A pinned cooperative message, not authority to signal any PID."""
    require(content_hash(d) == expected and type(supervisor_pid) is int and supervisor_pid > 0,
            'FULL_CANCEL_PARENT')
    parents = full_descriptor(d); p,r = d['package'],d['runtime']
    identities = verify_inputs(p,r,d['expected'],d['authorized_root'])
    fd = safe_root(p['root'])
    try:
        st = os.fstat(fd); doc = read_record(fd,'fs-fixture-launch.json')
    finally: os.close(fd)
    launch = verify_full_receipt(doc,content_hash(doc),parents)
    require(launch['descriptor'] == d and launch['parent_pid'] == supervisor_pid and
        launch['role'] == 'fixture' and launch['output_identity'] == [st.st_dev,st.st_ino],
        'FULL_CANCEL_PARENT')
    cap = SyntheticCapability(canonical(p),canonical(r),canonical(d['expected']),
        d['authorized_root'],identities,(st.st_dev,st.st_ino))
    value = {'event':'CANCEL','supervisor_pid':supervisor_pid,'descriptor_parent':expected}
    try: full_store(cap,parents,'fs-cancel.json',value)
    except FileExistsError: full_read(cap,parents,'fs-cancel.json',value=value)


def full_descriptor(d):
    require(type(d) is dict and set(d) == {'schema', 'execution_mode', 'package', 'runtime',
        'expected', 'authorized_root', 'native_tools', 'maximum_duration_seconds', 'context',
        'session_package', 'session_package_parent', 'budget', 'validation_parent'}, 'FULL_DESCRIPTOR')
    require(d['schema'] == 'iios-ci-full-session-descriptor-v2' and d['execution_mode'] == FULL_SCOPE
        and type(d['maximum_duration_seconds']) is int and d['maximum_duration_seconds'] == 3300,
        'FULL_DESCRIPTOR')
    full_budget(d)
    lifecycle_environment(d['context'])
    require(d['package']['source_commit'] == d['context']['GITHUB_SHA'], 'FULL_SOURCE')
    verify_inputs(d['package'], d['runtime'], d['expected'], d['authorized_root'])
    verify_tools(d['native_tools'])
    expected = full_package(d['package'], d['expected'])
    require(d['session_package'] == expected and content_hash(expected) == d['session_package_parent'],
            'FULL_PACKAGE')
    require(Path(d['package']['root']).name == 'full-session-output', 'FULL_OUTPUT')
    return {**d['expected'], 'session_package': d['session_package_parent'], 'full_descriptor': content_hash(d)}


def full_package(p, pins):
    # Independently pinned synthetic membership; never market-universe proof.
    symbols = [f'S{i:03}' for i in range(517)]
    plan = p['plan']; rows = plan['rows']
    require(plan['universe'] == {'symbols': symbols} and
        content_hash(plan['universe']) == pins['universe'] and len(rows) == 475, 'FULL_UNIVERSE')
    from alpha_market_baseline import verify_plan
    from provider_gateway_contract import PILOT
    # Reconstruct the accepted schedule, including the preflight window and
    # phase/slot identities. A rehashed mutation is not an independent binding.
    verify_plan(plan, pins['plan'])
    pilot = list(PILOT)
    opening = utc(plan['calendar']['open'])
    preflight = {'slot': 0, 'id': 'PREFLIGHT-0', 'phase': 'PREFLIGHT', 'batch': 0,
        'symbols': pilot, 'symbol_hash': content_hash(pilot),
        'valid_from': (opening - timedelta(minutes=10)).isoformat(),
        'expires_at': (opening - timedelta(minutes=5)).isoformat(),
        'root': str(Path(plan['root']) / 'PREFLIGHT-0')}
    require(rows[0] == preflight and len(pilot) == len(set(pilot)) == 10 and
            not set(pilot) & set(symbols) and plan['preflight_requests'] == 1 and
            plan['maximum_requests'] == 475 and plan['collection_requests'] == 474,
            'FULL_PREFLIGHT')
    for cycle in range(79):
        chunk = rows[1+cycle*6:1+(cycle+1)*6]
        require([len(row['symbols']) for row in chunk] == [100,100,100,100,100,17] and
                [symbol for row in chunk for symbol in row['symbols']] == symbols, 'FULL_BATCH_ORDER')
    require(len({row['root'] for row in rows}) == 475 and
            len({row['id'] for row in rows}) == 475, 'FULL_SLOT_IDENTITY')
    return {'schema': 'iios-ci-synthetic-full-session-package-v1', **FULL_FLAGS,
        'source_commit': p['source_commit'], 'input_parents': dict(pins),
        'ordered_universe': symbols, 'preflight_symbols': rows[0]['symbols'],
        'preflight': {'identifier': 'PILOT', 'request_count': 1,
            'symbols': pilot, 'symbol_hash': content_hash(pilot),
            'phase': preflight['phase'], 'slot': preflight['slot'],
            'schedule_id': preflight['id'], 'row_parent': content_hash(preflight),
            'valid_from': preflight['valid_from'], 'expires_at': preflight['expires_at']},
        'cycles': 79, 'batch_sizes': [100,100,100,100,100,17], 'maximum_requests': 475,
        'starts_per_rolling_minute': 3, 'timeout_seconds': 20, 'response_limit': 1_000_000,
        'retries': 0, 'redirects': 0, 'pagination': 0, 'fallback': 0, 'backfill': 0,
        'enrichment_requests': 0, 'slot_parents': [content_hash(row) for row in rows]}


def full_envelope(value, parents, *, logical_time=None, actual_utc=None, monotonic_seconds=None):
    from alpha_radar_admission import synthetic_document
    synthetic_document(value)
    if logical_time is not None: utc(logical_time)
    actual = actual_utc if actual_utc is not None else datetime.now(timezone.utc).isoformat()
    utc(actual)
    tick = time.monotonic() if monotonic_seconds is None else monotonic_seconds
    import math
    require(type(tick) in (int, float) and math.isfinite(tick) and tick >= 0, 'FULL_CLOCK')
    doc = {'schema': 'iios-ci-full-session-receipt-v1', **FULL_FLAGS,
        'parents': parents, 'logical_time': logical_time, 'actual_utc': actual,
        'monotonic_seconds': tick, 'value': value}
    return {**doc, 'content_hash': content_hash(doc)}


def verify_full_receipt(doc, expected, parents):
    require(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected) and
            type(doc) is dict and content_hash(doc) == expected, 'FULL_RECEIPT_PIN')
    require(set(doc) == {'schema', *FULL_FLAGS, 'parents', 'logical_time', 'actual_utc',
        'monotonic_seconds', 'value', 'content_hash'} and doc['parents'] == parents and
        all(type(doc[k]) is type(v) and doc[k] == v for k,v in FULL_FLAGS.items()), 'FULL_RECEIPT_SCOPE')
    require(doc == full_envelope(doc['value'], parents, logical_time=doc['logical_time'],
        actual_utc=doc['actual_utc'], monotonic_seconds=doc['monotonic_seconds']), 'FULL_RECEIPT_HASH')
    return doc['value']


def full_store(cap, parents, name, value, *, logical_time=None):
    p, _, _ = checked_capability(cap)
    fd = safe_root(p['root'])
    try:
        st = os.fstat(fd)
        require((st.st_dev, st.st_ino) == cap.output_identity, 'OUTPUT_REPLACED')
        verify_destination(fd, p['root'])
        return publish(fd, name, full_envelope(value, parents, logical_time=logical_time))
    finally: os.close(fd)


def full_read(cap, parents, name, *, expected=None, value=None):
    fd = safe_root(cap.documents()[0]['root'])
    try: doc = read_record(fd, name, expected_hash=expected)
    finally: os.close(fd)
    # Unpinned handshakes additionally require the independently constructed value.
    require(expected is not None or value is not None, 'FULL_INDEPENDENT_PARENT')
    result = verify_full_receipt(doc, expected or content_hash(doc), parents)
    if value is not None: require(result == value, 'FULL_ACK_BINDING')
    return result, content_hash(doc)


class FullPacing:
    def __init__(self): self.starts = []; self.last = None

    def reserve(self, now):
        import math
        require(type(now) in (int,float) and math.isfinite(now) and now >= 0 and
                (self.last is None or now >= self.last), 'FULL_CLOCK_ROLLBACK')
        self.last = now
        require(sum(0 <= now-v < 60 for v in self.starts) < 3, 'FULL_ROLLING_RATE')
        self.starts.append(now)


def full_real_clock_boundary(*, monotonic=time.monotonic, pause=time.sleep):
    """Native-only caller; no networking. Offline tests inject both clock and wait."""
    gate = FullPacing(); start = monotonic(); observed = []
    for _ in range(3):
        tick = monotonic(); gate.reserve(tick); observed.append(tick)
    require(monotonic()-start < 1, 'FULL_REAL_CLOCK_START')
    try: gate.reserve(monotonic())
    except ValueError as error: require(error.args == ('FULL_ROLLING_RATE',), 'FULL_REAL_CLOCK_REJECTION')
    else: raise ValueError('FULL_FOURTH_START_ALLOWED')
    last = start
    while True:
        now = monotonic(); require(now >= last, 'FULL_CLOCK_ROLLBACK'); last = now
        if now-start >= 60: break
        pause(min(.1,60-(now-start)))
    tick = monotonic(); require(60 <= tick-start <= 65, 'FULL_REAL_CLOCK_DEADLINE'); gate.reserve(tick)
    return {'scenario': 'REAL_CLOCK_ROLLING_MINUTE_BOUNDARY', 'first_three': observed,
        'fourth_start_rejected': True, 'next_start': tick, 'elapsed_seconds': tick-start,
        'market_requests': 0, 'full_day_wall_clock_proven': False}


class FullSession(Session):
    receipt_scope = FULL_SCOPE
    def __init__(self, cap, parents, *, clock, wait, stop, exchange=fixture_exchange):
        super().__init__(cap, clock=clock, wait=wait, stop=stop, exchange=exchange)
        full_package(self.p, self.pins)
        self.full_parents = parents; self.documents = {}; self.next_slot = 0; self.rate = FullPacing()
        self.attempted = 0; self.completed = 0; self.receipt_pins = []

    def document(self, value):
        key = canonical(value)
        if key not in self.documents:
            self.documents[key] = full_envelope(value, self.full_parents, logical_time=self.clock())
        return self.documents[key]

    def hash(self, value): return content_hash(self.document(value))

    def write(self, fd, name, value):
        checked_capability(self.cap); self.verify_fd(fd)
        return publish(fd, name, self.document(value))

    def read(self, fd, name, *, expected_hash=None):
        self.verify_fd(fd)
        doc = read_record(fd, name, expected_hash=expected_hash)
        value = verify_full_receipt(doc, expected_hash or content_hash(doc), self.full_parents)
        key = canonical(value)
        # Recovery may use only records independently witnessed in this process.
        require(key in self.documents and self.documents[key] == doc, 'FULL_RECOVERY_PIN')
        return value

    def verify(self, receipt, expected, *, parents):
        require(receipt['scope'] == self.receipt_scope and receipt['authority'] == AUTHORITY and
            receipt['parents'] == parents and self.hash(receipt) == expected and
            receipt['source_commit'] == self.p['source_commit'], 'FULL_RECEIPT_BINDING')

    def request(self, slot):
        request = super().request(slot); request['manifest']['role'] = self.receipt_scope
        return request

    def execute(self, request, previous):
        slot = self.next_slot
        require(slot < 475 and request == self.request(slot), 'FULL_REQUEST_ORDER')
        checked_capability(self.cap)
        m,a = request['manifest'],request['account']
        def dispatch(day_fd, index, reserved):
            require(index == slot, 'FULL_REQUEST_ORDER')
            at = self.clock(); self.rate.reserve(utc(at).timestamp())
            row = self.p['plan']['rows'][slot]; fd = self.open_root(row['root'])
            receipt = {'scope': self.receipt_scope, 'authority': AUTHORITY, 'source_commit': m['source_commit'],
                'root': m['root'], 'role': self.receipt_scope, 'parents': {**request['expected'],'reservation':reserved},
                'result': 'AMBIGUOUS_OR_UNVERIFIED_STOP', 'retry_count': 0,
                'credential_selector_access_count': 0, 'billing': 'SYNTHETIC_NO_CHARGE',
                'bulk_checks': {}, 'dispatch_time': at, 'response_time': None,
                'actual_dispatch_time': datetime.now(timezone.utc).isoformat(), 'actual_response_time': None,
                'dispatch_monotonic': time.monotonic(), 'response_monotonic': None,
                'timing_proof': FULL_TIMING}
            self.attempted += 1
            try:
                response = self.exchange(self.cap,slot,at)
                receipt.update(response_time=self.clock(), actual_response_time=response.response_end,
                    response_monotonic=time.monotonic(), http_status=response.status)
                require(response.status == 200 and len(response.body) <= 1_000_000, 'HTTP_OR_SIZE')
                def unique(pairs):
                    out = {}
                    for k,v in pairs:
                        require(k not in out,'DUPLICATE_JSON'); out[k] = v
                    return out
                payload = json.loads(response.body,object_pairs_hook=unique)
                checks = summarize(payload,row['symbols'],received_at=receipt['response_time'],maximum_age_seconds=60)
                receipt['bulk_checks'] = checks
                require(checks['coverage'] == 'COMPLETE' and checks['freshness'] == 'WITHIN_AGE_BOUND'
                        and [v['symbol'] for v in payload['data']] == row['symbols'],'OBSERVATION_FAILED')
                start,end = utc(at),utc(receipt['response_time'])
                require(utc(row['valid_from']) <= start <= end < utc(row['expires_at']) and
                        (end-start).total_seconds() <= 20,'RESPONSE_DEADLINE')
                require(0 <= (utc(response.response_end)-utc(response.request_start)).total_seconds() <= 20
                    and 0 <= receipt['response_monotonic']-receipt['dispatch_monotonic'] <= 20,'WIRE_DEADLINE')
                receipt['result'] = 'OBSERVED'; self.completed += 1
            except Exception:
                receipt['failure'] = 'SYNTHETIC_REQUEST_UNVERIFIED'
            finally:
                try: self.write(fd,'ALPHA_VANTAGE.receipt.json',receipt)
                finally: os.close(fd)
            return receipt
        result = execute_day(m,a,clock=self.clock,expected_bulk_previous=previous,dispatch=dispatch,
            verify_receipt=self.verify,write=self.write,read=self.read,record_hash=self.hash,open_root=self.open_root)
        self.next_slot += 1; self.receipt_pins.append(self.hash(result))
        return result

    def run(self):
        journal = Path(self.p['plan']['root']); journal.mkdir(mode=0o700)
        for row in self.p['plan']['rows']: Path(row['root']).mkdir(mode=0o700)
        requests = [self.request(i) for i in range(475)]
        def verify(receipt,request):
            require(receipt['parents'] == {**request['expected'],'reservation':receipt['parents']['reservation']},'RECEIPT_PARENTS')
            self.verify(receipt,self.hash(receipt),parents=receipt['parents'])
        failure_diagnostics = []
        receipts, reason = execute_schedule(self.p['plan'],requests,clock=self.clock,wait=self.wait,
            executor=self.execute,stop=self.stop,verify=verify,completion_parent=self.completion,
            failure_diagnostics=failure_diagnostics)
        complete = reason is None and len(receipts) == self.attempted == self.completed == self.next_slot == 475 and utc(self.clock()) <= utc(self.p['plan']['finalization_deadline'])
        value = {'classification':'FULL_SYNTHETIC_PASS' if complete else 'FULL_SYNTHETIC_FAILED',
            'attempted':self.attempted,'completed':self.completed,'reservations':self.next_slot,
            'receipt_parents':self.receipt_pins,'stop_reason':reason,'worker_launches':1,
            'failure_diagnostics':failure_diagnostics,
            'provider_requests':0,'credential_accesses':0,'full_day_wall_clock_proven':False}
        parent = full_store(self.cap,self.full_parents,'fs-session.json',value,logical_time=self.clock())
        return value,parent


def full_accounting(cap, parents, session, *, check_deadline=lambda:None):
    """Reconstruct all 1,425 records against independently received session pins."""
    p,_,pins = checked_capability(cap); rows = p['plan']['rows']
    require(session['classification'] == 'FULL_SYNTHETIC_PASS' and
        session['attempted'] == session['completed'] == session['reservations'] == 475 and
        len(session['receipt_parents']) == len(set(session['receipt_parents'])) == 475,'FULL_ACCOUNTING')
    fd = safe_root(p['plan']['root']); previous = None; rate = FullPacing()
    try:
        require(set(os.listdir(fd)) == {'day.lock'} | {row['id'] for row in rows} |
            {f'{i}.{kind}.json' for i in range(475) for kind in ('reserved','complete')},'FULL_ACCOUNTING')
        for i,row in enumerate(rows):
            check_deadline()
            reservation_doc = read_record(fd,f'{i}.reserved.json')
            reservation = verify_full_receipt(reservation_doc,content_hash(reservation_doc),parents)
            require(reservation == {'plan':pins['plan'],'slot':i,'source_commit':p['source_commit'],'previous':previous},'FULL_RESERVATION')
            child = safe_root(row['root'])
            try:
                require(os.listdir(child) == ['ALPHA_VANTAGE.receipt.json'],'FULL_ACCOUNTING')
                receipt_doc = read_record(child,'ALPHA_VANTAGE.receipt.json',expected_hash=session['receipt_parents'][i])
            finally: os.close(child)
            receipt = verify_full_receipt(receipt_doc,session['receipt_parents'][i],parents)
            require(receipt['parents'] == {**pins,'slot':content_hash({'slot':i,'row':row}),
                'reservation':content_hash(reservation_doc)} and receipt['root'] == row['root'] and
                receipt['source_commit'] == p['source_commit'] and receipt['scope'] == receipt['role'] == FULL_SCOPE
                and receipt['authority'] == AUTHORITY and receipt['result'] == 'OBSERVED'
                and receipt['retry_count'] == receipt['credential_selector_access_count'] == 0,'FULL_ACCOUNTING')
            rate.reserve(utc(receipt['dispatch_time']).timestamp())
            complete_doc = read_record(fd,f'{i}.complete.json')
            complete = verify_full_receipt(complete_doc,content_hash(complete_doc),parents)
            require(complete == {'slot':i,'previous':previous,'reservation':content_hash(reservation_doc),
                'receipt':session['receipt_parents'][i],'result':'OBSERVED'},'FULL_COMPLETION')
            previous = content_hash(complete_doc)
    finally: os.close(fd)
    return {'requests':475,'reservations':475,'completions':475,'receipts':475,
        'cycles':79,'ordered_symbols':517,'last_completion_parent':previous}


def full_startup(cap, role, launch_parent, identity):
    return {**lifecycle_startup_value(cap,launch_parent,identity),'role':role}


class FullRoleInspection(OwnedProcesses):
    """Same inspector and immutable expectations, with failure state per child.

    Evidence still uses the owner's exclusive, monotonically numbered publisher.
    Prior failures for this child are never cleared or hidden; other roles cannot
    inherit them as a reason to skip their independent ownership inspection.
    """
    def __init__(self, owner, entry):
        self.cap = owner.cap
        self.inspect = owner.inspect
        self.evidence = owner.evidence
        self.diagnostic_failures = entry.setdefault('inspection_diagnostic_failures', [])


class FullOwnedProcesses(LifecycleOwnedProcesses):
    record_store = staticmethod(full_store)
    record_read = staticmethod(full_read)
    def registration_admission(self, descriptor, deadline, phase=None, role=None):
        """Pin the expensive immutable inputs once before timed observation."""
        require(type(deadline) in (int,float) and deadline == (full_startup_deadline(descriptor) if phase is None else
                    full_phase_deadline(descriptor,role,phase))
                and self.monotonic() < deadline,
                'STARTUP_STABILIZATION_TIMEOUT')
        p,r,pins = checked_capability(self.cap)
        require(p == descriptor['package'] and r == descriptor['runtime'] and
                pins == descriptor['expected'] and self.lifecycle_parents == {
                    **pins, 'session_package': descriptor['session_package_parent'],
                    'full_descriptor': content_hash(descriptor)}, 'FULL_INDEPENDENT_PARENT')
        require(content_hash(descriptor['session_package']) == descriptor['session_package_parent'],
                'FULL_INDEPENDENT_PARENT')
        fd = safe_root(p['root'])
        try:
            st = os.fstat(fd)
            require((st.st_dev,st.st_ino) == self.cap.output_identity, 'OUTPUT_REPLACED')
            verify_destination(fd,p['root'])
        except BaseException:
            os.close(fd)
            raise
        return fd

    def registration_evidence(self, fd, value):
        self.counter += 1
        return publish(fd,f'fs-event-{self.counter:06d}.json',
            full_envelope(value,self.lifecycle_parents))

    def registration_observation(self, entry, diagnostics, *, allow_launcher=False):
        """Collect one complete OS observation without disk publication or re-admission."""
        sample = {'before':child_status(entry['child']), 'queries':[]}
        count = 0
        def diagnostic(row):
            nonlocal count
            count += 1
            require(count <= 16, 'DIAGNOSTIC_OVERFLOW')
            sample['queries'].append(validate_inspection_diagnostic(row))
        try:
            if self.inspect is inspect_macos:
                observed = self.inspect(entry['child'].pid,diagnostic=diagnostic)
            else:
                observed = self.inspect(entry['child'].pid)
        finally:
            sample['after'] = child_status(entry['child'])
        require(observed is not None, 'PROCESS_ABSENT')
        actual = asdict(observed)
        sample['observed'] = observed_diagnostic(entry,actual)
        diagnostics.append(sample)
        require(actual['start_time'] and actual['command'] == ' '.join(actual['argv']),
                'PROCESS_IDENTITY')
        expected = entry['expected']
        if allow_launcher and entry.get('launcher') and actual['executable'] == entry['launcher']['executable']:
            expected = {**expected,**entry['launcher']}
        for key,value in expected.items(): require(actual[key] == value,'PROCESS_IDENTITY')
        return actual

    def register(self,role,child,*,argv,cwd,executable,executable_hash,launcher=None,
                 stderr=None,launch_parent=None,descriptor=None,deadline=None,phase=None):
        require(role in ('worker','fixture') and role not in self.children,'CHILD_ROLE')
        require(type(descriptor) is dict and deadline is not None,'FULL_INDEPENDENT_PARENT')
        entry={'child':child,'expected':{'pid':child.pid,'parent_pid':os.getpid(),
            'argv':tuple(argv),'cwd':str(cwd),'executable':str(executable),
            'executable_hash':executable_hash},'observation':None,'launcher':launcher,
            'launch_parent':launch_parent}
        self.children[role]=entry
        fd=None; diagnostics=[]
        try:
            entry['capture']=self.capture_for(child,stderr)
            fd=self.registration_admission(descriptor,deadline,phase,role)
            self.registration_evidence(fd,{'event':'PROCESS_CREATED','role':role,'pid':child.pid,
                'expected_parent_pid':os.getpid(),'launch_parent':launch_parent,
                'identity_status':'CHILD_CREATED_UNOBSERVED','status':child_status(child)})
            observations=[]
            for _ in range(3):
                require(self.monotonic()<deadline,'STARTUP_STABILIZATION_TIMEOUT')
                self.pump(entry); require(not entry['capture'].overflow,'DIAGNOSTIC_OVERFLOW')
                observations.append(self.registration_observation(entry,diagnostics,allow_launcher=True))
                require(self.monotonic()<deadline,'STARTUP_STABILIZATION_TIMEOUT')
                self.pause(.05)
            require(observations[0] == observations[1] == observations[2],
                    'STARTUP_IDENTITY_CHANGED')
            entry['observation']=observations[-1]
            self.registration_evidence(fd,{'event':'OWNERSHIP_INSPECTION_BATCH','role':role,
                'pid':child.pid,'launch_parent':launch_parent,'sample_count':3,'samples':diagnostics,
                'ownership_authority':False})
            self.registration_evidence(fd,{'event':'OWNERSHIP','role':role,
                'observed':observed_diagnostic(entry,entry['observation'])})
            require(self.monotonic()<deadline,'STARTUP_STABILIZATION_TIMEOUT')
        except BaseException as error:
            primary={'role':role,'stage':'OWNERSHIP_REGISTER','category':failure_category(error),
                'pid':child.pid,'launch_parent':launch_parent}
            self.primary_failures.append(primary)
            if fd is not None:
                try:self.registration_evidence(fd,{'event':'REGISTRATION_FAILED',**primary})
                except Exception:self.diagnostic_failures.append('DIAGNOSTIC_PUBLICATION_FAILED')
            else:self.safe_evidence({'event':'REGISTRATION_FAILED',**primary})
            raise
        finally:
            if fd is not None: os.close(fd)

    def observe(self,entry,*,allow_launcher=False):
        inspector = FullRoleInspection(self,entry)
        before = len(inspector.diagnostic_failures)
        try:
            return inspector.observe(entry,allow_launcher=allow_launcher)
        finally:
            # Aggregate for final failure classification without using one
            # child's diagnostics as another child's inspection admission gate.
            self.diagnostic_failures.extend(inspector.diagnostic_failures[before:])

    def evidence(self,value):
        self.counter += 1
        self.record_store(self.cap,self.lifecycle_parents,f'fs-event-{self.counter:06d}.json',value)

    def verify(self,role,*,require_startup=True):
        require(role in ('fixture','worker'),'FULL_ROLE')
        entry = self.children[role]; self.pump(entry)
        require(entry['observation'] is not None and self.observe(entry) == entry['observation'],'PROCESS_IDENTITY')
        require(not require_startup or role in self.startup_pins,'STARTUP_RECEIPT_REQUIRED')
        if role in self.startup_pins:
            launch,expected = self.startup_pins[role]
            self.record_read(self.cap,self.lifecycle_parents,f'fs-{role}-startup.json',expected=expected,
                value=full_startup(self.cap,role,launch,entry['observation']))
        return entry['child']

    def cleanup(self,port_clear,*,supervisor_check=None, deadline=None):
        exits = []; roles = {}; supervisor_failures = []; listener_failures = []
        # The supervisor observation is an independent gate, not permission to
        # suppress each child's own pinned ownership verification. No signals.
        if supervisor_check is not None:
            try: supervisor_check()
            except Exception as error:
                supervisor_failures.append({'stage':'SUPERVISOR_IDENTITY','category':failure_category(error)})
        for role in reversed(list(self.children)):
            entry = self.children[role]; child = entry['child']
            finding = {'ownership_verified':False, 'exit_verified':False,
                'primary_failures':[v for v in self.primary_failures if v['role']==role],
                'cleanup_failures':[], 'diagnostic_failures':[], 'signals':0}
            roles[role] = finding
            def failed(stage,error):
                category = ('DIAGNOSTIC_INCOMPLETE' if error.args == ('DIAGNOSTIC_INCOMPLETE',)
                            else failure_category(error))
                item = {'role':role,'stage':stage,'category':category}
                finding['cleanup_failures'].append(item); self.failures.append(item)
            stage = 'OWNERSHIP_VERIFY'
            try:
                self.verify(role); finding['ownership_verified'] = True
                stage = 'COOPERATIVE_STOP'
                self.record_store(self.cap,self.lifecycle_parents,f'fs-{role}-stop.json',
                    {'event':'STOP','role':role,'launch_parent':entry['launch_parent']})
                remaining=25 if deadline is None else min(25,deadline-self.monotonic())
                require(remaining>0,'FULL_CLEANUP_DEADLINE')
                child.wait(timeout=remaining)
                stage = 'EXIT_VERIFY'
                require(child.poll() == 0 and entry['observation'] is not None,'COOPERATIVE_SHUTDOWN')
                self.record_read(self.cap,self.lifecycle_parents,f'fs-{role}-exit.json',
                    value={'role':role,'returncode':0,'launch_parent':entry['launch_parent']})
                finding['exit_verified'] = True
                exits.append({'role':role,'pid':child.pid,'returncode':0,'ownership_verified':True})
                del self.children[role]
            except Exception as error: failed(stage,error)
            finally:
                capture = entry.get('capture')
                try:
                    if capture:
                        capture.drain(); capture.check()
                        require(child.poll() is not None and capture.eof,'DIAGNOSTIC_INCOMPLETE')
                except Exception as error: failed('STREAM_COMPLETION',error)
                finally:
                    if capture:
                        try: capture.close()
                        except Exception as error: failed('STREAM_CLOSE',error)
                # Snapshot/status/publication can fail independently. Preserve
                # each failure and continue with the next role in every case.
                status = None; diagnostics = None
                try: status = child_status(child)
                except Exception as error: failed('FINAL_STATUS',error)
                try: diagnostics = capture.snapshot() if capture else None
                except Exception as error: failed('DIAGNOSTIC_SNAPSHOT',error)
                try:
                    self.evidence({'event':'FINAL_CHILD_STATUS','role':role,'status':status,
                                   'diagnostics':diagnostics})
                except Exception as error: failed('FINAL_STATUS_PUBLICATION',error)
                finding['diagnostic_failures'] = list(entry.get('inspection_diagnostic_failures',[]))
        observations = []
        for ordinal in range(3):
            try: observations.append(port_clear() is True)
            except Exception as error:
                observations.append(False)
                listener_failures.append({'observation':ordinal,'category':failure_category(error)})
            try: self.pause(.2)
            except Exception as error:
                listener_failures.append({'observation':ordinal,'category':failure_category(error)})
        required = {'worker','fixture'}
        clean = (set(roles)==required and len(exits)==2 and not self.children and
            not self.failures and not self.primary_failures and not self.diagnostic_failures and
            all(v['ownership_verified'] and v['exit_verified'] and not v['cleanup_failures'] and
                not v['diagnostic_failures'] for v in roles.values()) and
            not supervisor_failures and not listener_failures and observations==[True,True,True])
        return {'exits':exits,'remaining':sorted(self.children),'failures':self.failures,
            'primary_failures':list(self.primary_failures),'role_findings':roles,
            'supervisor':{'checked':supervisor_check is not None,'failures':supervisor_failures},
            'listener':{'failures':listener_failures,'stable_clear':observations==[True,True,True]},
            'diagnostic_failures':list(self.diagnostic_failures),'port_clear_observations':observations,
            'signals':0,'clean':clean}

def full_lexical_path(path, *, roots, exact=(), parent=None):
    """Pure component admission. Never resolve, expand aliases or touch a path.

    Roots and exact files are supplied by the independently admitted run.
    Custom PathLike objects are rejected: __fspath__ could perform arbitrary IO.
    Symlinks cannot be identified from spelling; admitted directory entries are
    checked without following links by full_canonical_path before resolution.
    """
    from pathlib import PurePosixPath, PosixPath
    def spelling(value):
        require(type(value) in (str, PurePosixPath, PosixPath), 'FULL_PATH_LEXICAL')
        text = os.fspath(value)
        require(type(text) is str and text and not any(ord(c)<32 or ord(c)==127 for c in text)
                and '\\' not in text and '~' not in text and '//' not in text,
                'FULL_PATH_LEXICAL')
        parts = text.split('/')
        require(not any(v in ('.','..') for v in parts) and
                not (len(text)>1 and text.endswith('/')), 'FULL_PATH_LEXICAL')
        # No protected/home aliases, even if an untrusted caller lists a root.
        folded = tuple(v.casefold() for v in parts)
        require(not any(v in ('keychains','keychain','application support','l7','l8')
                        for v in folded) and not text.startswith(('/Users/','/home/','/var/','/tmp/')),
                'FULL_PATH_LEXICAL')
        return PurePosixPath(text)
    admitted = tuple(spelling(v) for v in roots)
    singles = tuple(spelling(v) for v in exact)
    require(admitted and all(v.is_absolute() and len(v.parts)>3 and
            v.parts[:3]==('/','private','tmp') and
            v.parts[3].startswith('iios-provider-connection-source-tests-') for v in admitted),
            'FULL_PATH_LEXICAL')
    value = spelling(path)
    if parent is not None:
        base = spelling(parent)
        require(base.is_absolute() and any(base==v or base.is_relative_to(v) for v in admitted)
                and not value.is_absolute(), 'FULL_PATH_LEXICAL')
        value = base/value
    require(value.is_absolute() and (value in singles or any(value==v or value.is_relative_to(v)
            for v in admitted)), 'FULL_PATH_LEXICAL')
    return Path(value)


def full_canonical_path(path, *, roots, exact=()):
    """Additional no-follow entry checks; only called after lexical admission."""
    import stat
    value = full_lexical_path(path, roots=roots, exact=exact)
    # Walk from the pinned admitted root, never through a substituted symlink.
    anchors = [Path(v) for v in roots if value==Path(v) or value.is_relative_to(Path(v))]
    anchor = max(anchors,key=lambda p:len(p.parts)) if anchors else value
    entries = [anchor]
    for part in value.relative_to(anchor).parts: entries.append(entries[-1]/part)
    for entry in entries:
        try: mode = os.lstat(entry).st_mode
        except FileNotFoundError: break
        require(not stat.S_ISLNK(mode), 'FULL_PATH_ALIAS')
    resolved = value.resolve()
    require(resolved==value, 'FULL_PATH_ALIAS')
    return resolved


def full_audit(runtime, output, endpoint, role, *, plan, launch_commands=None, child_pids=lambda: (), context=None):
    """Application-only guard, never evidence of OS confinement.

    Child has no subprocess or signal allowance. Supervisor inspection uses
    existing verified ownership logic; all lifecycle processes reject DNS and
    public sockets. Descriptor-relative writes are resolved by the companion
    checked-open wrapper, never by granting arbitrary relative names.
    """
    require(role in ('fixture', 'worker', 'supervisor') and endpoint[0] == '127.0.0.1'
            and type(endpoint[1]) is int and 1024 <= endpoint[1] <= 65535, 'LOOPBACK_PIN_REQUIRED')
    lexical_roots = (runtime, output)
    root = full_canonical_path(runtime, roots=lexical_roots)
    out = full_canonical_path(output, roots=lexical_roots)
    read_exact = ('/dev/null','/bin/ps','/usr/sbin/lsof','/usr/bin/sandbox-exec')
    active = []; directories = {}; original = os.open; launched = set()
    commands = {}
    require(not launch_commands or (role == 'supervisor' and set(launch_commands) == {'fixture','worker'}), 'FULL_SPAWN')
    def admit_command(name, argv):
        require(role=='supervisor' and name in ('fixture','worker') and name not in commands,'FULL_SPAWN')
        argv=tuple(argv)
        require(len(argv)==10 and Path(argv[0]).is_relative_to(root) and Path(argv[2]).is_relative_to(root)
            and Path(argv[2]).name=='alpha_radar_runner.py' and argv[1]=='-B'
            and argv[3:7]==('--ci-full-session-only','--child',name,'--descriptor')
            and argv[7]==str(out/f'fs-{name}-launch.json') and argv[8]=='--expected-descriptor'
            and re.fullmatch('[a-f0-9]{64}',argv[9]), 'FULL_SPAWN')
        commands[name]=argv
    for name,argv in (launch_commands or {}).items(): admit_command(name,argv)
    permitted_dirs = {full_lexical_path(v, roots=(out,)) for v in
                      [plan['root'], *[row['root'] for row in plan['rows']]]}
    require(all(full_canonical_path(v,roots=(out,))==v and v.is_relative_to(out)
                for v in permitted_dirs), 'FULL_WRITE_ROOT')
    def checked_open(path, flags, mode=0o777, *, dir_fd=None):
        resolved = None
        if dir_fd is None:
            resolved = full_lexical_path(path, roots=(root,out), exact=read_exact)
        else:
            require(dir_fd in directories, 'LIFECYCLE_DIRECTORY')
            parent, identity = directories[dir_fd]
            resolved = full_lexical_path(path, roots=(root,out), parent=parent)
            st = os.fstat(dir_fd)
            require((st.st_dev, st.st_ino) == identity, 'LIFECYCLE_DIRECTORY')

        # Permission admission precedes fspath resolution and the actual open.
        audit('open',(resolved,None,flags))
        resolved = full_canonical_path(resolved,roots=(root,out),exact=read_exact)
        active.append(resolved)
        try: fd = original(path, flags, mode, dir_fd=dir_fd)
        finally: active.pop()
        import stat
        st = os.fstat(fd)
        if stat.S_ISDIR(st.st_mode): directories[fd] = (resolved, (st.st_dev, st.st_ino))
        return fd
    def audit(event, args):
        if event.startswith('socket.get') or event in ('socket.sethostname', 'os.system', 'os.posix_spawn',
                'os.kill', 'os.killpg', 'os.remove', 'os.rename', 'os.rmdir', 'os.link', 'os.symlink'):
            raise PermissionError('LIFECYCLE_BOUNDARY')
        if event == 'subprocess.Popen':
            require(role == 'supervisor' and len(args) == 4, 'LIFECYCLE_BOUNDARY')
            executable, argv, cwd, env = args
            argv = tuple(argv)
            matches = [k for k,v in commands.items() if argv == v]
            if matches:
                key = matches[0]
                require(key not in launched and executable == argv[0] and str(cwd) == str(out)
                    and env == lifecycle_environment(context), 'FULL_SPAWN')
                launched.add(key)
            else:
                allowed = [('/usr/sbin/lsof','-nP','-iTCP:'+str(endpoint[1]),'-sTCP:LISTEN','-Fpn')]
                for pid in child_pids():
                    require(type(pid) is int and pid > 0,'FULL_PID')
                    allowed += [('/bin/ps','-ww','-p',str(pid),'-o',field) for field in ('lstart=','ppid=','comm=')]
                    allowed += [('/usr/sbin/lsof','-a','-p',str(pid),'-d','cwd','-Fn')]
                require(argv in allowed and executable == argv[0] and cwd is None and
                    env in (LIFECYCLE_ENV,{k:v for k,v in LIFECYCLE_ENV.items() if k!='TZ'}),'FULL_SPAWN')
        if event == 'ctypes.dlopen':
            require(role == 'supervisor' and args == ('/usr/lib/libSystem.B.dylib',), 'LIFECYCLE_BOUNDARY')
        if event == 'socket.__new__':
            require(args[1] == socket.AF_INET and args[2] == socket.SOCK_STREAM and args[3] in (0, 6), 'LIFECYCLE_BOUNDARY')
        if event in ('socket.connect', 'socket.bind'):
            require(tuple(args[1]) == tuple(endpoint) and
                    ((event == 'socket.bind' and role == 'fixture') or
                     (event == 'socket.connect' and role in ('supervisor','worker'))), 'LIFECYCLE_BOUNDARY')
        if event == 'open' and not isinstance(args[0], int):
            path, mode, flags = args
            target = active[-1] if active else full_lexical_path(path, roots=(root,out), exact=read_exact)
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if writing:
                receipt = (target.parent == out and re.fullmatch(r'fs-[a-z0-9-]+\.json',target.name)) or (
                    role == 'worker' and target.parent in permitted_dirs and (
                        re.fullmatch(r'(?:[0-9]{1,3}\.(?:reserved|complete)|ALPHA_VANTAGE\.receipt)\.json',target.name)))
                lock = role == 'worker' and target == Path(plan['root'])/'day.lock'
                require((receipt and flags & os.O_EXCL and flags & os.O_NOFOLLOW) or
                    (lock and flags in (os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,
                        os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC)),'FULL_WRITE')
            else:
                require(target.is_relative_to(root) or target.is_relative_to(out) or
                    str(target) in read_exact,'FULL_READ')
            require(full_canonical_path(target,roots=(root,out),exact=read_exact)==target,'FULL_PATH_ALIAS')
        if event == 'os.mkdir':
            target = full_lexical_path(args[0],roots=(out,))
            require(role == 'worker' and target in permitted_dirs and args[1] == 0o700,'FULL_WRITE')
            full_canonical_path(target,roots=(out,))
        if event in ('os.chmod','os.truncate'): raise PermissionError('FULL_WRITE')
    audit.admit_command=admit_command
    return audit, checked_open


def full_child(launch,launch_parent,*,cancelled=lambda:False):
    require(set(launch)=={'descriptor','output_identity','parent_pid','role','startup_phase',*FULL_FLAGS} and
        all(type(launch[k]) is type(v) and launch[k]==v for k,v in FULL_FLAGS.items()) and
        launch['parent_pid']==os.getppid() and launch['role'] in ('fixture','worker'),'FULL_LAUNCH')
    d=launch['descriptor']; parents=full_descriptor(d); role=launch['role']
    phase_deadline=full_phase_deadline(d,role,launch['startup_phase'])
    require(time.monotonic()<phase_deadline,'PARENT_ACK_TIMEOUT')
    require(dict(os.environ)==lifecycle_environment(d['context']),'FULL_ENVIRONMENT')
    identities=verify_inputs(d['package'],d['runtime'],d['expected'],d['authorized_root'])
    cap=SyntheticCapability(canonical(d['package']),canonical(d['runtime']),canonical(d['expected']),
        d['authorized_root'],identities,tuple(launch['output_identity']))
    native_identity(cap)
    from alpha_radar_fixture import serve
    native_identity(cap)
    p,r,_=cap.documents()
    audit,opened=full_audit(r['root'],p['root'],('127.0.0.1',p['fixture']['port']),role,
        plan=p['plan'],context=d['context'])
    os.open=opened; sys.addaudithook(audit)
    deadline=full_budget(d)['cleanup_deadline']; sequence=[0]
    def stage(value):
        require(value in STAGES,'CHILD_DIAGNOSTIC_STAGE'); sequence[0]+=1
        require(sequence[0]<=64,'DIAGNOSTIC_OVERFLOW')
        full_store(cap,parents,f'fs-{role}-stage-{sequence[0]:04d}.json',{'stage':value})
    def stop():
        if cancelled(): raise ValueError('FULL_CANCELLED')
        if time.monotonic()>=deadline: raise ValueError('NATIVE_SESSION_TIMEOUT')
        try:
            full_read(cap,parents,f'fs-{role}-stop.json',value={'event':'STOP','role':role,'launch_parent':launch_parent})
            return True
        except FileNotFoundError: return False
    def ready():
        value=full_startup(cap,role,launch_parent,{'pid':os.getpid(),'parent_pid':os.getppid(),
            'argv':[sys.executable,'-B',*sys.argv],'cwd':str(Path.cwd())})
        startup_parent=full_store(cap,parents,f'fs-{role}-startup.json',value)
        until=phase_deadline
        while time.monotonic()<until:
            try:
                full_read(cap,parents,f'fs-{role}-ack.json',value={'event':'ACK','role':role,
                    'launch_parent':launch_parent,'startup_parent':startup_parent})
                return
            except FileNotFoundError: time.sleep(.05)
        raise ValueError('PARENT_ACK_TIMEOUT')
    try:
        if role=='fixture': serve(cap,stop,ready,stage=stage)
        else:
            ready(); now=[utc(p['plan']['rows'][0]['valid_from'])]
            def wait(seconds): advance_full_clock(session,now,seconds)
            def work_stop():
                require(time.monotonic()<d['budget']['work_deadline'],'NATIVE_SESSION_TIMEOUT')
                return stop()
            session=FullSession(cap,parents,clock=lambda:now[0].isoformat(),wait=wait,stop=work_stop)
            value,parent=session.run()
            full_store(cap,parents,'fs-worker-complete.json',{'session_parent':parent,'launch_parent':launch_parent})
            # Stay owned/alive until the independently validating supervisor stops us.
            while not stop(): time.sleep(.05)
            require(value['classification']=='FULL_SYNTHETIC_PASS','FULL_SESSION_FAILED')
        full_store(cap,parents,f'fs-{role}-exit.json',{'role':role,'returncode':0,'launch_parent':launch_parent})
        return 0
    except BaseException as error:
        full_store(cap,parents,f'fs-{role}-failure.json',{'category':failure_category(error)})
        raise


def full_verify_startup_listener(role,child,port):
    require(role in ('fixture','worker'),'FULL_ROLE')
    if role=='fixture':
        require(listener_owners(port)==[(child.pid,'127.0.0.1:'+str(port))],
                'LISTENER_OWNER_MISMATCH')
        return True
    return None


def full_publish_startup_ack(cap,parents,role,launch_parent,startup_parent,deadline,
                             listener_verified,*,monotonic=time.monotonic):
    require(role in ('fixture','worker') and
            listener_verified is (True if role=='fixture' else None),'LISTENER_OWNER_MISMATCH')
    require(monotonic()<deadline,'PARENT_ACK_TIMEOUT')
    parent=full_store(cap,parents,f'fs-{role}-ack.json',{'event':'ACK','role':role,
        'launch_parent':launch_parent,'startup_parent':startup_parent})
    require(monotonic()<deadline,'PARENT_ACK_TIMEOUT')
    return parent


def full_supervise(cap,d,*,popen=subprocess.Popen,cancelled=lambda:False):
    budget=full_launch_budget(d)
    parents=full_descriptor(d); native_identity(cap)
    require(dict(os.environ)==lifecycle_environment(d['context']),'FULL_ENVIRONMENT')
    p,r,_=cap.documents(); out=Path(p['root']); runtime=Path(r['root'])
    require(not listener_owners(p['fixture']['port']),'PORT_ALREADY_OWNED')
    executable=runtime/r['interpreter']
    script=next(runtime/n for n in r['source_files'] if Path(n).name=='alpha_radar_runner.py')
    executable_hash=next(v['sha256'] for v in r['files'] if v['path']==r['interpreter'])
    observed=asdict(inspect_macos(os.getpid()))
    require(observed['pid']==os.getpid() and observed['parent_pid']==os.getppid() and
        observed['argv']==tuple([sys.executable,'-B',*sys.argv]) and observed['cwd']==str(Path.cwd()) and
        observed['executable']==str(executable) and observed['executable_hash']==executable_hash,'FULL_SUPERVISOR_IDENTITY')
    def verify_self():
        require(asdict(inspect_macos(os.getpid()))==observed,'FULL_SUPERVISOR_IDENTITY'); checked_capability(cap)
    owned=FullOwnedProcesses(cap,parents); commands={}; launches={}
    audit,opened=full_audit(runtime,out,('127.0.0.1',p['fixture']['port']),'supervisor',plan=p['plan'],
        launch_commands=commands,child_pids=lambda:[os.getpid(),*[v['child'].pid for v in owned.children.values()]],context=d['context'])
    os.open=opened; sys.addaudithook(audit)
    stage='REAL_CLOCK'; primary=None; cleanup_failure=None; tls=None; accounting=None; session_parent=None
    def running():
        require(not cancelled(),'FULL_CANCELLED')
        require(time.monotonic()<budget['work_deadline'],'NATIVE_SESSION_TIMEOUT')
        try:
            full_read(cap,parents,'fs-cancel.json',value={'event':'CANCEL',
                'supervisor_pid':os.getpid(),'descriptor_parent':content_hash(d)})
        except FileNotFoundError: return
        raise ValueError('FULL_CANCELLED')
    try:
        running(); verify_self(); boundary=full_real_clock_boundary()
        full_store(cap,parents,'fs-real-clock.json',boundary)
        for role in ('fixture','worker'):
            running(); verify_self()
            if role=='worker':
                owned.verify('fixture'); require(tls is not None and tls['hostname_verified'] is True,'FULL_TLS_GATE')
            phase=full_phase(d,role)
            startup_deadline=full_phase_deadline(d,role,phase)
            launch={**FULL_FLAGS,'descriptor':d,'output_identity':list(cap.output_identity),
                    'parent_pid':os.getpid(),'role':role,'startup_phase':phase}
            launches[role]=full_store(cap,parents,f'fs-{role}-launch.json',launch)
            commands[role]=[str(executable),'-B',str(script),'--ci-full-session-only','--child',role,
                '--descriptor',str(out/f'fs-{role}-launch.json'),'--expected-descriptor',launches[role]]
            audit.admit_command(role,commands[role])
            require(time.monotonic()<startup_deadline,'STARTUP_STABILIZATION_TIMEOUT')
            stage='PROCESS_CREATE'
            child=popen(commands[role],cwd=out,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,close_fds=True,env=lifecycle_environment(d['context']))
            close_lifecycle_stdin(child); stage='OWNERSHIP_REGISTER'
            owned.register(role,child,argv=commands[role],cwd=out,executable=executable,
                executable_hash=executable_hash,stderr=child.stderr,launch_parent=launches[role],
                descriptor=d,deadline=startup_deadline,phase=phase)
            stage='STARTUP_VERIFY'
            while not (out/f'fs-{role}-startup.json').exists() and time.monotonic()<startup_deadline:
                owned.verify(role,require_startup=False); time.sleep(.05)
            require(time.monotonic()<startup_deadline,'PARENT_ACK_TIMEOUT')
            _,startup=full_read(cap,parents,f'fs-{role}-startup.json',
                value=full_startup(cap,role,launches[role],owned.children[role]['observation']))
            owned.startup_pins[role]=(launches[role],startup)
            verify_self(); owned.verify(role)
            listener_verified=None
            if role=='fixture':
                stage='LISTENER_VERIFY'
                listener_verified=full_verify_startup_listener(role,child,p['fixture']['port'])
            stage='PARENT_ACK'
            full_publish_startup_ack(cap,parents,role,launches[role],startup,
                startup_deadline,listener_verified)
            if role=='fixture': stage='TLS_HANDSHAKE'; tls=startup_tls(cap,owned)
        stage='SESSION_WAIT'
        while not (out/'fs-worker-complete.json').exists():
            running()
            verify_self(); owned.verify('fixture'); owned.verify('worker'); time.sleep(.2)
        # A completion references the independently admitted worker launch. Validate
        # every journal parent before accepting its session result.
        fd=safe_root(out)
        try: completion_doc=read_record(fd,'fs-worker-complete.json')
        finally: os.close(fd)
        completion=verify_full_receipt(completion_doc,content_hash(completion_doc),parents)
        require(set(completion)=={'session_parent','launch_parent'} and completion['launch_parent']==launches['worker'],'FULL_COMPLETION')
        session_parent=completion['session_parent']
        session,_=full_read(cap,parents,'fs-session.json',expected=session_parent)
        running(); accounting=full_accounting(cap,parents,session,check_deadline=running)
        running(); verify_self(); owned.verify('fixture'); owned.verify('worker')
    except BaseException as error: primary={'stage':stage,'category':failure_category(error)}
    try:
        cleanup=owned.cleanup(lambda:not listener_owners(p['fixture']['port']),supervisor_check=verify_self,
            deadline=budget['cleanup_deadline'])
        if not cleanup['clean']: cleanup_failure='FULL_CLEANUP_FAILED'
    except Exception as error:
        cleanup_failure=failure_category(error); cleanup={'clean':False,'remaining':sorted(owned.children)}
    result={'classification':'FULL_SYNTHETIC_PASS' if primary is None and cleanup_failure is None else 'FULL_SYNTHETIC_FAILED',
        'primary_failure':primary,'cleanup_failure':cleanup_failure,'cleanup':cleanup,'tls':tls,
        'accounting':accounting,'session_parent':session_parent,'supervisor_identity':observed,'budget':budget,
        'worker_launches':int('worker' in owned.startup_pins),'provider_requests':0,'credential_accesses':0}
    full_store(cap,parents,'fs-final.json',result)
    return result


def full_main(d,expected,child):
    if child:
        value=verify_full_receipt(d,expected,full_descriptor(d['value']['descriptor']))
        require(child==value['role'],'FULL_ROLE')
        with FullCancellation() as cancelled: return full_child(value,expected,cancelled=cancelled)
    full_descriptor(d); full_launch_budget(d)
    cap=admit(d['package'],d['runtime'],expected=d['expected'],authorized_root=d['authorized_root'])
    with FullCancellation() as cancelled:
        return 0 if full_supervise(cap,d,cancelled=cancelled)['classification']=='FULL_SYNTHETIC_PASS' else 1


# Separate local diagnostic admission. Never an alternate full-session admission.
DIAG_SCOPE = 'LOCAL_SYNTHETIC_ONE_REQUEST_DIAGNOSTIC'
DIAG_FLAGS = {**FULL_FLAGS, 'scope': DIAG_SCOPE}
DIAG_ENV = {**LIFECYCLE_ENV, '__CF_USER_TEXT_ENCODING': f'0x{os.getuid():X}:0x0:0x0'}


def diagnostic_descriptor(d):
    require(type(d) is dict and set(d)=={'schema','scope','package','runtime','expected',
        'authorized_root','native_tools','source_inventory','source_parent','os_identity',
        'maximum_requests','work_deadline_ns','cleanup_deadline_ns'},'DIAGNOSTIC_DESCRIPTOR')
    require(d['schema']=='iios-local-one-request-descriptor-v1' and d['scope']==DIAG_SCOPE
        and type(d['maximum_requests']) is int and d['maximum_requests']==1,'DIAGNOSTIC_DESCRIPTOR')
    require(d['os_identity']=={'sysname':os.uname().sysname,'release':os.uname().release,
        'machine':os.uname().machine} and os.uname().sysname=='Darwin','DIAGNOSTIC_OS')
    require(type(d['work_deadline_ns']) is int and type(d['cleanup_deadline_ns']) is int and
        0<d['work_deadline_ns']<d['cleanup_deadline_ns'] and
        d['cleanup_deadline_ns']-d['work_deadline_ns']==180_000_000_000,'DIAGNOSTIC_DEADLINE')
    require(content_hash(d['source_inventory'])==d['source_parent'],'DIAGNOSTIC_SOURCE')
    rows={row['path']:row for row in d['runtime']['files']}
    require(set(d['source_inventory'])==set(d['runtime']['source_files']) and
        all(rows[n]['sha256']==h for n,h in d['source_inventory'].items()),'DIAGNOSTIC_SOURCE')
    verify_inputs(d['package'],d['runtime'],d['expected'],d['authorized_root'])
    verify_tools(d['native_tools']); full_package(d['package'],d['expected'])
    require(Path(d['package']['root']).name=='one-request-output','DIAGNOSTIC_OUTPUT')
    return {**d['expected'],'diagnostic_descriptor':content_hash(d),'diagnostic_source':d['source_parent']}


def diagnostic_envelope(value,parents,*,logical_time=None):
    doc=full_envelope(value,parents,logical_time=logical_time)
    doc.pop('content_hash');doc.update(DIAG_FLAGS)
    return {**doc,'content_hash':content_hash(doc)}


def diagnostic_verify(doc,expected,parents):
    require(content_hash(doc)==expected and doc['parents']==parents and
        doc['content_hash']==content_hash({k:v for k,v in doc.items() if k!='content_hash'}) and
        all(type(doc[k]) is type(v) and doc[k]==v for k,v in DIAG_FLAGS.items()),'DIAGNOSTIC_RECEIPT')
    require(set(doc)=={'schema',*DIAG_FLAGS,'parents','logical_time','actual_utc',
        'monotonic_seconds','value','content_hash'},'DIAGNOSTIC_RECEIPT')
    return doc['value']


def diagnostic_store(cap,parents,name,value,*,logical_time=None):
    p,_,_=checked_capability(cap);fd=safe_root(p['root'])
    try:
        st=os.fstat(fd);require((st.st_dev,st.st_ino)==cap.output_identity,'OUTPUT_REPLACED')
        verify_destination(fd,p['root'])
        return publish(fd,name,diagnostic_envelope(value,parents,logical_time=logical_time))
    finally:os.close(fd)


def diagnostic_read(cap,parents,name,*,expected=None,value=None):
    require(expected is not None or value is not None,'DIAGNOSTIC_PARENT')
    fd=safe_root(cap.documents()[0]['root'])
    try:doc=read_record(fd,name,expected_hash=expected)
    finally:os.close(fd)
    result=diagnostic_verify(doc,expected or content_hash(doc),parents)
    if value is not None:require(result==value,'DIAGNOSTIC_PARENT')
    return result,content_hash(doc)


class DiagnosticSession(FullSession):
    receipt_scope=DIAG_SCOPE

    def document(self,value):
        key=canonical(value)
        if key not in self.documents:self.documents[key]=diagnostic_envelope(value,self.full_parents,logical_time=self.clock())
        return self.documents[key]

    def execute(self,request,previous):
        require(self.next_slot==0 and previous is None,'DIAGNOSTIC_REQUEST_LIMIT')
        return super().execute(request,previous)

    def read(self,fd,name,*,expected_hash=None):
        self.verify_fd(fd);doc=read_record(fd,name,expected_hash=expected_hash)
        value=diagnostic_verify(doc,expected_hash or content_hash(doc),self.full_parents)
        require(self.documents.get(canonical(value))==doc,'FULL_RECOVERY_PIN')
        return value

    def run(self):
        # The admitted plan stays 475 rows. Only the independently bound slot zero
        # is executed; this result cannot satisfy any full-session verifier.
        Path(self.p['plan']['root']).mkdir(mode=0o700)
        Path(self.p['plan']['rows'][0]['root']).mkdir(mode=0o700)
        request=self.request(0);diagnostics=[]
        def verify(receipt,request):
            require(receipt['parents']=={**request['expected'],'reservation':receipt['parents']['reservation']},'RECEIPT_PARENTS')
            self.verify(receipt,self.hash(receipt),parents=receipt['parents'])
        receipts,reason=execute_schedule(self.p['plan'],[request],clock=self.clock,wait=self.wait,
            executor=self.execute,stop=self.stop,verify=verify,completion_parent=self.completion,
            failure_diagnostics=diagnostics)
        value={'scope':DIAG_SCOPE,'classification':'DIAGNOSTIC_PASS' if reason is None and
            self.attempted==self.completed==self.next_slot==len(receipts)==1 else 'DIAGNOSTIC_FAILED',
            'attempted':self.attempted,'completed':self.completed,'reservations':self.next_slot,
            'receipt_parents':self.receipt_pins,'stop_reason':reason,'failure_diagnostics':diagnostics,
            'provider_requests':0,'credential_accesses':0,'maximum_requests':1}
        return value,diagnostic_store(self.cap,self.full_parents,'fs-session.json',value,logical_time=self.clock())


class DiagnosticOwnedProcesses(FullOwnedProcesses):
    record_store=staticmethod(diagnostic_store)
    record_read=staticmethod(diagnostic_read)

    def registration_admission(self,descriptor,deadline,phase=None,role=None):
        require(phase is not None and phase=={'role':role,'descriptor_parent':content_hash(descriptor),
            'start_ns':phase['start_ns'],'deadline_ns':phase['deadline_ns']} and
            type(phase['start_ns']) is int and type(phase['deadline_ns']) is int and
            phase['deadline_ns']-phase['start_ns']==100_000_000_000 and
            phase['deadline_ns']<=descriptor['work_deadline_ns'] and
            deadline==phase['deadline_ns']/1e9 and self.monotonic()<deadline,'DIAGNOSTIC_PHASE')
        p,r,pins=checked_capability(self.cap)
        require(p==descriptor['package'] and r==descriptor['runtime'] and pins==descriptor['expected']
            and self.lifecycle_parents=={**pins,'diagnostic_descriptor':content_hash(descriptor),
                'diagnostic_source':descriptor['source_parent']},'DIAGNOSTIC_PARENT')
        fd=safe_root(p['root'])
        try:
            st=os.fstat(fd);require((st.st_dev,st.st_ino)==self.cap.output_identity,'OUTPUT_REPLACED')
            verify_destination(fd,p['root']);return fd
        except BaseException:os.close(fd);raise

    def registration_evidence(self,fd,value):
        self.counter+=1
        return publish(fd,f'fs-event-{self.counter:06d}.json',diagnostic_envelope(value,self.lifecycle_parents))


def diagnostic_audit(d,role,commands,child_pids):
    p=d['package'];r=d['runtime']
    base,opened=full_audit(r['root'],p['root'],('127.0.0.1',p['fixture']['port']),role,
        plan=p['plan'],child_pids=child_pids)
    launched=set()
    def audit(event,args):
        if event=='subprocess.Popen' and role=='supervisor' and len(args)==4:
            executable,argv,cwd,env=args;matches=[k for k,v in commands.items() if tuple(argv)==tuple(v)]
            if matches:
                key=matches[0]
                require(key not in launched and key in ('fixture','worker') and
                    executable==str(Path(r['root'])/r['interpreter']) and
                    argv[1:7]==['-B',str(Path(r['root'])/'source/alpha_radar_runner.py'),
                        '--local-one-request-only','--child',key,'--descriptor'] and
                    argv[7]==str(Path(p['root'])/f'fs-{key}-launch.json') and
                    argv[8]=='--expected-descriptor' and re.fullmatch('[a-f0-9]{64}',argv[9]) and
                    str(cwd)==p['root'] and env==DIAG_ENV,'DIAGNOSTIC_COMMAND')
                launched.add(key);return
        base(event,args)
    return audit,opened


def diagnostic_child(launch,launch_parent):
    require(set(launch)=={'descriptor','role','parent_pid','output_identity','phase',*DIAG_FLAGS} and
        all(launch[k]==v and type(launch[k]) is type(v) for k,v in DIAG_FLAGS.items()) and
        launch['role'] in ('fixture','worker') and launch['parent_pid']==os.getppid(),'DIAGNOSTIC_LAUNCH')
    d=launch['descriptor'];parents=diagnostic_descriptor(d);role=launch['role'];phase=launch['phase']
    require(phase['descriptor_parent']==content_hash(d) and phase['role']==role and
        type(phase['start_ns']) is int and type(phase['deadline_ns']) is int and
        phase['deadline_ns']-phase['start_ns']==100_000_000_000 and
        time.monotonic_ns()<phase['deadline_ns']<=d['work_deadline_ns'],'DIAGNOSTIC_PHASE')
    require(dict(os.environ)==DIAG_ENV,'DIAGNOSTIC_ENVIRONMENT')
    ids=verify_inputs(d['package'],d['runtime'],d['expected'],d['authorized_root'])
    cap=SyntheticCapability(canonical(d['package']),canonical(d['runtime']),canonical(d['expected']),
        d['authorized_root'],ids,tuple(launch['output_identity']))
    native_identity(cap)
    from alpha_radar_fixture import serve
    audit,opened=diagnostic_audit(d,role,{},lambda:());os.open=opened;sys.addaudithook(audit)
    def stop():
        require(time.monotonic_ns()<d['cleanup_deadline_ns'],'DIAGNOSTIC_DEADLINE')
        try:diagnostic_read(cap,parents,f'fs-{role}-stop.json',value={'event':'STOP','role':role,'launch_parent':launch_parent});return True
        except FileNotFoundError:return False
    def ready():
        value=full_startup(cap,role,launch_parent,{'pid':os.getpid(),'parent_pid':os.getppid(),
            'argv':[sys.executable,'-B',*sys.argv],'cwd':str(Path.cwd())})
        parent=diagnostic_store(cap,parents,f'fs-{role}-startup.json',value)
        while time.monotonic_ns()<phase['deadline_ns']:
            try:diagnostic_read(cap,parents,f'fs-{role}-ack.json',value={'event':'ACK','role':role,
                'launch_parent':launch_parent,'startup_parent':parent});return
            except FileNotFoundError:time.sleep(.05)
        raise ValueError('PARENT_ACK_TIMEOUT')
    try:
        if role=='fixture':serve(cap,stop,ready)
        else:
            ready();at=d['package']['plan']['rows'][0]['valid_from']
            def stopped():
                require(time.monotonic_ns()<d['work_deadline_ns'],'DIAGNOSTIC_DEADLINE');return stop()
            def no_wait(seconds):raise ValueError('DIAGNOSTIC_SCHEDULE')
            session=DiagnosticSession(cap,parents,clock=lambda:at,wait=no_wait,stop=stopped)
            value,parent=session.run()
            diagnostic_store(cap,parents,'fs-worker-complete.json',{'session_parent':parent,'launch_parent':launch_parent})
            while not stop():time.sleep(.05)
        # A failed diagnostic can still shut down cooperatively, without making
        # its failed request result successful.
        diagnostic_store(cap,parents,f'fs-{role}-exit.json',{'role':role,'returncode':0,'launch_parent':launch_parent})
        return 0
    except BaseException as error:
        from alpha_session_execution import sanitized_execution_failure
        diagnostic_store(cap,parents,f'fs-{role}-failure.json',sanitized_execution_failure(error,'EXECUTOR'))
        raise


def diagnostic_failure(error,stage):
    from alpha_session_execution import sanitized_execution_failure
    import types
    result=sanitized_execution_failure(error,'EXECUTOR')
    sites={diagnostic_supervise.__code__:'DIAGNOSTIC_SUPERVISE',
        diagnostic_child.__code__:'DIAGNOSTIC_CHILD'}
    for code in full_audit.__code__.co_consts:
        if isinstance(code,types.CodeType):sites[code]='NATIVE_FULL_AUDIT'
    trace=error.__traceback__;count=0
    while trace is not None and count<32:
        if trace.tb_frame.f_code in sites:
            result['location']={'site':sites[trace.tb_frame.f_code],'line':trace.tb_lineno}
        trace=trace.tb_next;count+=1
    return {'stage':stage,'diagnostic':result}


def diagnostic_supervise(d):
    parents=diagnostic_descriptor(d);require(dict(os.environ)==DIAG_ENV,'DIAGNOSTIC_ENVIRONMENT')
    require(time.monotonic_ns()+220_000_000_000<d['work_deadline_ns'],'DIAGNOSTIC_DEADLINE')
    cap=admit(d['package'],d['runtime'],expected=d['expected'],authorized_root=d['authorized_root'])
    native_identity(cap);p,r,_=cap.documents();out=Path(p['root']);exe=Path(r['root'])/r['interpreter']
    executable_hash=next(row['sha256'] for row in r['files'] if row['path']==r['interpreter'])
    observed=asdict(inspect_macos(os.getpid()))
    require(observed['executable']==str(exe) and observed['executable_hash']==executable_hash and
        observed['cwd']==str(out.parent),'DIAGNOSTIC_SUPERVISOR')
    def verify_self():require(asdict(inspect_macos(os.getpid()))==observed,'DIAGNOSTIC_SUPERVISOR')
    owned=DiagnosticOwnedProcesses(cap,parents);commands={};launches={};tls=None;session=None;primary=None
    audit,opened=diagnostic_audit(d,'supervisor',commands,lambda:(os.getpid(),*(e['child'].pid for e in owned.children.values())))
    os.open=opened;sys.addaudithook(audit);stage='STARTUP'
    try:
        for role in ('fixture','worker'):
            verify_self()
            if role=='worker':owned.verify('fixture');require(tls is not None,'DIAGNOSTIC_TLS')
            start=time.monotonic_ns();phase={'role':role,'descriptor_parent':content_hash(d),
                'start_ns':start,'deadline_ns':start+100_000_000_000}
            require(phase['deadline_ns']<d['work_deadline_ns'],'DIAGNOSTIC_DEADLINE')
            launch={**DIAG_FLAGS,'descriptor':d,'role':role,'parent_pid':os.getpid(),
                'output_identity':list(cap.output_identity),'phase':phase}
            parent=diagnostic_store(cap,parents,f'fs-{role}-launch.json',launch);launches[role]=parent
            argv=[str(exe),'-B',str(Path(r['root'])/'source/alpha_radar_runner.py'),
                '--local-one-request-only','--child',role,'--descriptor',str(out/f'fs-{role}-launch.json'),
                '--expected-descriptor',parent];commands[role]=argv
            stage='PROCESS_CREATE'
            child=subprocess.Popen(argv,cwd=out,env=DIAG_ENV,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,close_fds=True);close_lifecycle_stdin(child)
            stage='OWNERSHIP_REGISTER';deadline=phase['deadline_ns']/1e9
            owned.register(role,child,argv=argv,cwd=out,executable=exe,executable_hash=executable_hash,
                stderr=child.stderr,launch_parent=parent,descriptor=d,deadline=deadline,phase=phase)
            stage='STARTUP_RECEIPT'
            while not (out/f'fs-{role}-startup.json').exists():
                require(time.monotonic_ns()<phase['deadline_ns'],'PARENT_ACK_TIMEOUT')
                owned.verify(role,require_startup=False);time.sleep(.05)
            _,startup=diagnostic_read(cap,parents,f'fs-{role}-startup.json',
                value=full_startup(cap,role,parent,owned.children[role]['observation']))
            owned.startup_pins[role]=(parent,startup);owned.verify(role);verify_self()
            full_verify_startup_listener(role,child,p['fixture']['port'])
            require(time.monotonic_ns()<phase['deadline_ns'],'PARENT_ACK_TIMEOUT')
            diagnostic_store(cap,parents,f'fs-{role}-ack.json',{'event':'ACK','role':role,'launch_parent':parent,'startup_parent':startup})
            require(time.monotonic_ns()<phase['deadline_ns'],'PARENT_ACK_TIMEOUT')
            if role=='fixture':stage='TLS';tls=startup_tls(cap,owned)
        stage='SESSION'
        while not (out/'fs-worker-complete.json').exists():
            require(time.monotonic_ns()<d['work_deadline_ns'],'DIAGNOSTIC_DEADLINE')
            owned.verify('worker');owned.verify('fixture');time.sleep(.05)
        fd=safe_root(out)
        try:doc=read_record(fd,'fs-worker-complete.json')
        finally:os.close(fd)
        completion=diagnostic_verify(doc,content_hash(doc),parents)
        require(completion['launch_parent']==launches['worker'],'DIAGNOSTIC_PARENT')
        session,_=diagnostic_read(cap,parents,'fs-session.json',expected=completion['session_parent'])
        require(session['classification']=='DIAGNOSTIC_PASS' and
            session['attempted']==session['completed']==session['reservations']==len(session['receipt_parents'])==1,'DIAGNOSTIC_SESSION')
        fd=safe_root(p['plan']['root']);rf=safe_root(p['plan']['rows'][0]['root'])
        try:
            reserved=read_record(fd,'0.reserved.json');complete=read_record(fd,'0.complete.json')
            receipt=read_record(rf,'ALPHA_VANTAGE.receipt.json',expected_hash=session['receipt_parents'][0])
            rv=diagnostic_verify(reserved,content_hash(reserved),parents)
            cv=diagnostic_verify(complete,content_hash(complete),parents)
            v=diagnostic_verify(receipt,session['receipt_parents'][0],parents)
            require(rv=={'plan':d['expected']['plan'],'slot':0,'source_commit':p['source_commit'],'previous':None}
                and cv=={'slot':0,'previous':None,'reservation':content_hash(reserved),
                    'receipt':content_hash(receipt),'result':'OBSERVED'} and
                v['parents']=={**d['expected'],'slot':content_hash({'slot':0,'row':p['plan']['rows'][0]}),
                    'reservation':content_hash(reserved)} and v['result']=='OBSERVED','DIAGNOSTIC_ACCOUNTING')
            require(set(os.listdir(fd))=={'day.lock','0.reserved.json','0.complete.json','PREFLIGHT-0'} and
                os.listdir(rf)==['ALPHA_VANTAGE.receipt.json'],'DIAGNOSTIC_ACCOUNTING')
        finally:os.close(fd);os.close(rf)
    except BaseException as error:
        from alpha_session_execution import sanitized_execution_failure
        primary=diagnostic_failure(error,stage)
    cleanup=owned.cleanup(lambda:not listener_owners(p['fixture']['port']),
        supervisor_check=verify_self,deadline=d['cleanup_deadline_ns']/1e9)
    result={'classification':'DIAGNOSTIC_PASS' if primary is None and cleanup['clean'] else 'DIAGNOSTIC_FAILED',
        'primary_failure':primary,'session':session,'tls':tls,'cleanup':cleanup,
        'credential_accesses':0,'provider_requests':0,'worker_launches':int('worker' in owned.startup_pins)}
    diagnostic_store(cap,parents,'fs-final.json',result)
    return 0 if result['classification']=='DIAGNOSTIC_PASS' else 1


def diagnostic_main(d,expected,child):
    if child:
        parents=diagnostic_descriptor(d['value']['descriptor']);value=diagnostic_verify(d,expected,parents)
        require(child==value['role'],'DIAGNOSTIC_ROLE');return diagnostic_child(value,expected)
    require(content_hash(d)==expected,'DIAGNOSTIC_PARENT')
    return diagnostic_supervise(d)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--descriptor', required=True)
    parser.add_argument('--expected-descriptor', required=True)
    parser.add_argument('--child', choices=('fixture', 'worker'))
    parser.add_argument('--ci-lifecycle-only', action='store_true', default=False)
    parser.add_argument('--ci-full-session-only', action='store_true', default=False)
    parser.add_argument('--local-one-request-only', action='store_true', default=False)
    args = parser.parse_args()
    require(not args.local_one_request_only or not (args.ci_full_session_only or args.ci_lifecycle_only), 'DIAGNOSTIC_MODE')
    require(not (args.ci_full_session_only and args.ci_lifecycle_only), 'FULL_MODE_EXCLUSION')
    early_diagnostic('DESCRIPTOR_READ')
    d = read_descriptor(args.descriptor, args.expected_descriptor)
    early_diagnostic('DESCRIPTOR_VERIFIED')
    if args.local_one_request_only:
        return diagnostic_main(d, args.expected_descriptor, args.child)
    if args.ci_full_session_only:
        return full_main(d, args.expected_descriptor, args.child)
    if args.ci_lifecycle_only:
        return lifecycle_main(d, args.expected_descriptor, args.child)
    if args.child:
        return child_main(d, args.child, args.expected_descriptor)
    descriptor_schema(d)
    cap = admit(d['package'], d['runtime'], expected=d['expected'], authorized_root=d['authorized_root'])
    result = supervise(cap, d)
    if startup_only(d):
        if result['classification'] != 'SYNTHETIC_STARTUP_PASS':
            return 1
        verify_startup_result(result, args.expected_descriptor)
        return 0
    return 0 if result['classification'] == 'SYNTHETIC_PASS' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        sys.stderr.write('RADAR_DIAGNOSTIC: ' + failure_category(error) + '\n')
        sys.exit(1)
