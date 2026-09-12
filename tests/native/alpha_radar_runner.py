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
    'DIAGNOSTIC_PUBLICATION_FAILED', 'DIAGNOSTIC_OVERFLOW', 'DIAGNOSTIC_PIPE_FAILED'))


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

    def register(self, role, child, *, argv, cwd, executable, executable_hash, launcher=None,
                 stderr=None, launch_parent=None):
        require(role in ('worker', 'fixture') and role not in self.children, 'CHILD_ROLE')
        entry = {'child': child, 'expected': {'pid': child.pid, 'parent_pid': os.getpid(),
            'argv': tuple(argv), 'cwd': str(cwd), 'executable': str(executable),
            'executable_hash': executable_hash}, 'observation': None, 'launcher': launcher, 'launch_parent': launch_parent}
        self.children[role] = entry  # Keep partial startup registered even on failure.
        try:
            entry['capture'] = StderrCapture(stderr, profile=self.profile, profile_path=self.profile_path)
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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--descriptor', required=True)
    parser.add_argument('--expected-descriptor', required=True)
    parser.add_argument('--child', choices=('fixture', 'worker'))
    args = parser.parse_args()
    early_diagnostic('DESCRIPTOR_READ')
    d = read_descriptor(args.descriptor, args.expected_descriptor)
    early_diagnostic('DESCRIPTOR_VERIFIED')
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
