"""Test-only native harness. Never invoked or imported by the production CLI.

Native execution requires separately reviewed input and confinement pins.
Clock acceleration is explicit synthetic evidence, never real-time acceptance.
"""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlencode

from alpha_market_baseline import require, summarize
from alpha_session_execution import (execute_schedule, execute_day, safe_root, publish,
    read_record, verify_destination)
from provider_gateway_contract import canonical, content_hash, utc
from provider_gateway_https import bounded_https
from truth_spine_process_identity import inspect_macos
from alpha_radar_admission import (SCOPE, AUTHORITY, SyntheticCapability, admit,
    envelope, verify_envelope, store, verify_inputs)


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
        checked_capability(cap)
        self.cap, self.inspect, self.monotonic, self.pause = cap, inspect, monotonic, pause
        self.children, self.failures, self.counter = {}, [], 0
        self.startup_pins = {}

    def evidence(self, value):
        self.counter += 1
        store(self.cap, f'lifecycle-{self.counter:04d}.json', value)

    def register(self, role, child, *, argv, cwd, executable, executable_hash, launcher=None):
        require(role in ('worker', 'fixture') and role not in self.children, 'CHILD_ROLE')
        entry = {'child': child, 'expected': {'pid': child.pid, 'parent_pid': os.getpid(),
            'argv': tuple(argv), 'cwd': str(cwd), 'executable': str(executable),
            'executable_hash': executable_hash}, 'observation': None, 'launcher': launcher}
        self.children[role] = entry  # Keep partial startup registered even on failure.
        end = self.monotonic() + 10
        previous, stable, anchor, final_seen = None, 0, None, False
        while self.monotonic() < end:
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
                self.evidence({'event': 'OWNERSHIP', 'role': role, 'observed': observed})
                return
            self.pause(.05)
        raise ValueError('STARTUP_STABILIZATION_TIMEOUT')

    def observe(self, entry, *, allow_launcher=False):
        checked_capability(self.cap)
        observed = self.inspect(entry['child'].pid)
        require(observed is not None, 'PROCESS_ABSENT')
        actual = asdict(observed)
        require(actual['start_time'] and actual['command'] == ' '.join(actual['argv']), 'PROCESS_IDENTITY')
        expected = entry['expected']
        if allow_launcher and entry.get('launcher') and actual['executable'] == entry['launcher']['executable']:
            expected = {**expected, **entry['launcher']}
        for k, v in expected.items():
            require(actual[k] == v, 'PROCESS_IDENTITY')
        return actual

    def verify(self, role, *, require_startup=True):
        entry = self.children[role]
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
            except Exception:
                self.failures.append({'role': role, 'failure': 'CLEANUP_UNVERIFIED'})
        clear = True
        for _ in range(3):
            try:
                clear = (port_clear() is True) and clear
            except Exception:
                clear = False
            self.pause(.2)
        result = {'scope': SCOPE, 'remaining': sorted(self.children), 'failures': self.failures,
                  'port_clear': clear, 'clean': not self.children and not self.failures and clear}
        self.evidence({'event': 'CLEANUP', 'result': result})
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


def supervise(cap, descriptor, *, popen=subprocess.Popen):
    p, r, pins = checked_capability(cap)
    native_identity(cap)
    verify_tools(descriptor['native_tools'])
    require(descriptor['clock_mode'] in ('ACCELERATED_LOGICAL_TIME', 'REAL_SESSION_TIME'), 'CLOCK_MODE')
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
    failure, session, cleanup = None, None, None
    stopped = [False]
    def stop_handler(*_):
        stopped[0] = True
    previous_handlers = {sig: signal.signal(sig, stop_handler) for sig in (signal.SIGINT, signal.SIGTERM)}
    startup_hashes = {}
    fd = safe_root(out)
    lock = os.open('supervisor.lock', os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for role in ('fixture', 'worker'):
            require(not stopped[0], 'COOPERATIVE_SHUTDOWN')
            launch = {'scope': SCOPE, 'authority': AUTHORITY, 'descriptor': descriptor, 'output_identity': list(cap.output_identity),
                      'role': role, 'parent_pid': os.getpid(), 'created_at': datetime.now(timezone.utc).isoformat()}
            name = role + '-launch.json'
            launch_hash = publish(fd, name, launch)
            argv = [str(executable), '-B', str(script), '--child', role,
                    '--descriptor', str(out / name), '--expected-descriptor', launch_hash]
            command = ['/usr/bin/sandbox-exec', '-f', str(runtime / r['confinement']), *argv]
            # Child output is suppressed; only schema-validated receipts survive.
            child = popen(command, cwd=out, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, close_fds=True,
                          env={'PATH': '/usr/bin:/bin:/usr/sbin', 'LC_ALL': 'C', 'TZ': 'UTC'})
            owned.register(role, child, argv=argv, cwd=out, executable=executable,
                           executable_hash=executable_hash, launcher={'argv': tuple(command),
                               'executable': '/usr/bin/sandbox-exec',
                               'executable_hash': descriptor['native_tools']['/usr/bin/sandbox-exec']})
            deadline = time.monotonic() + 10
            while not (out / (role + '-startup.json')).exists() and time.monotonic() < deadline:
                owned.verify(role, require_startup=False)
                time.sleep(.05)
            startup_hashes[role] = read_startup(cap, role, launch_hash, owned)
            owned.startup_pins[role] = (launch_hash, startup_hashes[role])
            if role == 'fixture':
                require(listener_owners(p['fixture']['port']) == [(child.pid, '127.0.0.1:' + str(p['fixture']['port']))], 'LISTENER_OWNER_MISMATCH')
            store(cap, role + '-ack.json', {'role': role, 'launch_parent': launch_hash,
                                          'startup_parent': startup_hashes[role]})
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
    except BaseException:
        failure = 'SYNTHETIC_NATIVE_FAILED'
        try:
            store(cap, 'native-failure.json', {'failure': failure})
        except Exception:
            failure = 'FAILURE_EVIDENCE_UNAVAILABLE'
    finally:
        try:
            cleanup = owned.cleanup(lambda: not listener_owners(p['fixture']['port']))
        finally:
            os.close(lock)
            os.close(fd)
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
    result = {'classification': 'SYNTHETIC_PASS' if failure is None and cleanup['clean'] else 'SYNTHETIC_FAILED',
              'failure': failure, 'session': session, 'startup_parents': startup_hashes,
              'cleanup': cleanup, 'clock_mode': descriptor['clock_mode'],
              'live_readiness': 'NOT_QUALIFIED', 'armed': False,
              'actual_elapsed_seconds': time.monotonic() - started}
    store(cap, 'final-audit.json', result)
    return result


def descriptor_schema(d):
    require(set(d) == {'package', 'runtime', 'expected', 'authorized_root', 'native_tools',
                       'clock_mode', 'maximum_duration_seconds'}, 'DESCRIPTOR_SCHEMA')


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
    d = launch['descriptor']
    descriptor_schema(d)
    identities = verify_inputs(d['package'], d['runtime'], d['expected'], d['authorized_root'])
    cap = SyntheticCapability(canonical(d['package']), canonical(d['runtime']), canonical(d['expected']),
                              d['authorized_root'], identities, tuple(launch['output_identity']))
    native_identity(cap)
    require_confinement(cap)
    stopped = [False]
    require(type(d['maximum_duration_seconds']) is int and 1 <= d['maximum_duration_seconds'] <= 25200, 'NATIVE_DURATION')
    child_deadline = time.monotonic() + d['maximum_duration_seconds']
    def stop_handler(*_):
        stopped[0] = True
    def stop():
        return stopped[0] or time.monotonic() >= child_deadline
    def ready():
        startup(cap, role, launch_parent)
        await_parent_ack(cap, role, launch_parent)
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    if role == 'fixture':
        from alpha_radar_fixture import serve
        serve(cap, stop, ready)
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
    result = Session(cap, clock=clock, wait=wait, stop=stop).run()
    return 0 if result['classification'] == 'SYNTHETIC_PASS' else 1


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
    d = read_descriptor(args.descriptor, args.expected_descriptor)
    if args.child:
        return child_main(d, args.child, args.expected_descriptor)
    descriptor_schema(d)
    cap = admit(d['package'], d['runtime'], expected=d['expected'], authorized_root=d['authorized_root'])
    result = supervise(cap, d)
    return 0 if result['classification'] == 'SYNTHETIC_PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
