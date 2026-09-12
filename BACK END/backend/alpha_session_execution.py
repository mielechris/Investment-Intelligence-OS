"""Shared scheduler and durable request journal; no credential or transport imports."""
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

from provider_gateway_contract import canonical, content_hash, utc
from alpha_market_baseline import require


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_root(path, *, immutable=False):
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p and not p.is_symlink() and 'Application Support' not in p.parts, 'ROOT_REJECTED')
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    st = os.fstat(fd)
    if st.st_uid != os.getuid() or st.st_mode & (0o222 if immutable else 0o022):
        os.close(fd)
        raise ValueError('ROOT_OWNERSHIP_MODE')
    return fd


def relative(name):
    p = PurePosixPath(name)
    require(bool(p.parts) and not p.is_absolute() and '..' not in p.parts and str(p) == name, 'RELATIVE_PATH_REQUIRED')
    return p


def read_pinned(root, row):
    relative(row['path'])
    p = root / row['path']
    require(p.resolve().is_relative_to(root) and p.resolve() == p, 'RUNTIME_ALIAS')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid(), 'RUNTIME_FILE_IDENTITY')
        require(stat.S_IMODE(st.st_mode) == row['mode'] and row['mode'] in (0o400, 0o500), 'IMMUTABLE_FILE_REQUIRED')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            body = stream.read()
        require(len(body) == row['size'] and digest(body) == row['sha256'], 'RUNTIME_BYTES_MISMATCH')
        after = os.stat(p, follow_symlinks=False)
        require((st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'RUNTIME_CHANGED')
        return st.st_dev, st.st_ino
    finally:
        os.close(fd)


def verify_destination(fd, root):
    before = os.fstat(fd)
    after = os.stat(root, follow_symlinks=False)
    require(Path(root).resolve() == Path(root) and stat.S_ISDIR(after.st_mode) and not after.st_mode & 0o022 and after.st_uid == os.getuid() and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), 'OUTPUT_ROOT_REPLACED')


def publish(fd, name, document):
    require('/' not in name and name not in ('.', '..'), 'RECEIPT_NAME')
    data = canonical(document)
    out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=fd)
    with os.fdopen(out, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(fd)
    return digest(data)


def read_record(fd, name, *, expected_hash=None):
    file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        st = os.fstat(file)
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o400, 'RECEIPT_IDENTITY')
        with os.fdopen(os.dup(file), 'rb') as stream:
            raw = stream.read(32_000_001)
        require(len(raw) <= 32_000_000, 'RECORD_SIZE')
        if expected_hash is not None:
            require(digest(raw) == expected_hash, 'RECORD_BYTES_MISMATCH')
        after = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require((st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'RECORD_CHANGED')
        def unique(pairs):
            value = {}
            for key, child in pairs:
                require(key not in value, 'DUPLICATE_RECORD_KEY')
                value[key] = child
            return value
        return json.loads(raw, object_pairs_hook=unique)
    finally:
        os.close(file)


def execute_day(m, a, *, clock, expected_bulk_previous, dispatch,
                verify_receipt, open_root=safe_root, write=publish, read=read_record,
                record_hash=content_hash):
    day, slot = a['bulk_plan'], a['bulk_slot']
    fd = open_root(day['root'])
    lock = None
    try:
        lock = os.open('day.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        st = os.fstat(lock)
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o600, 'DAY_LOCK_IDENTITY')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        allowed = {'day.lock'} | {row['id'] for row in day['rows']}
        allowed |= {f'{i}.{suffix}.json' for i in range(slot) for suffix in ('reserved', 'complete')}
        names = set(os.listdir(fd))
        required = {f'{i}.{suffix}.json' for i in range(slot) for suffix in ('reserved', 'complete')}
        require(names <= allowed and required <= names, 'DAY_INTERRUPTED_OR_DUPLICATE')
        previous = None
        prior_dispatches = []
        for i in range(slot):
            complete = read(fd, f'{i}.complete.json')
            reservation = read(fd, f'{i}.reserved.json')
            require(complete.get('previous') == previous and complete.get('reservation') == record_hash(reservation), 'DAY_CHAIN')
            require(reservation == {'plan': a['bulk_plan_parent'], 'slot': i, 'source_commit': m['source_commit'], 'previous': previous}, 'DAY_RESERVATION')
            require(complete.get('result') == 'OBSERVED' and complete.get('slot') == i, 'DAY_STOPPED')
            child = open_root(day['rows'][i]['root'])
            try:
                retained = read(child, 'ALPHA_VANTAGE.receipt.json', expected_hash=complete['receipt'])
                verify_receipt(retained, complete['receipt'], parents=retained['parents'])
                if day.get('requires_preflight'):
                    require(retained.get('bulk_checks', {}).get('freshness') == 'WITHIN_AGE_BOUND', 'PREFLIGHT_OR_COLLECTION_NOT_FRESH')
                    prior_dispatches.append(retained['dispatch_time'])
                require(retained['source_commit'] == m['source_commit'] and retained['root'] == day['rows'][i]['root'] and retained['role'] == m['role'] and retained['result'] == 'OBSERVED', 'DAY_RECEIPT_BINDING')
            finally:
                os.close(child)
            previous = record_hash(complete)
        require(previous == expected_bulk_previous, 'INDEPENDENT_DAY_PARENT')
        if day.get('requires_preflight'):
            from provider_gateway_contract import utc
            dispatch_now = utc(datetime.now(timezone.utc).isoformat() if clock is None else clock())
            require(all(utc(t) <= dispatch_now for t in prior_dispatches), 'CLOCK_ROLLBACK')
            require(sum(0 <= (dispatch_now - utc(t)).total_seconds() < 60 for t in prior_dispatches) < 3, 'ROLLING_RATE_GATE')
        verify_destination(fd, day['root'])
        reserved = write(fd, f'{slot}.reserved.json', {'plan': a['bulk_plan_parent'], 'slot': slot,
                           'source_commit': m['source_commit'], 'previous': previous})
        # An exception or process interruption leaves this immutable consumed slot.
        receipt = dispatch(fd, slot, reserved)
        verify_destination(fd, day['root'])
        completion = {'slot': slot, 'previous': previous, 'reservation': reserved,
                      'receipt': record_hash(receipt), 'result': receipt['result']}
        write(fd, f'{slot}.complete.json', completion)
        return receipt
    finally:
        if lock is not None:
            os.close(lock)
        os.close(fd)


def execute_schedule(plan, requests, *, clock, wait, executor, stop, verify,
                     completion_parent, checkpoint=None):
    """No admission, receipt scope conversion or live activation occurs here."""
    receipts=[];starts=[];previous=None;phase_receipts=[];reason=None
    for i,request in enumerate(requests):
        row=plan['rows'][i]
        target=utc(row['valid_from'])
        if len(starts)>=3:
            from datetime import timedelta
            target=max(target,utc(starts[-3])+timedelta(seconds=60))
        while utc(clock())<target and not stop():
            wait(min(1.0,(target-utc(clock())).total_seconds()))
        if stop():
            reason='COOPERATIVE_SHUTDOWN';break
        if utc(clock())>=utc(row['expires_at']):
            reason='MISSED_INTERVAL_NO_BACKFILL';break
        try:
            receipt=executor(request,previous)
            verify(receipt, request)
            receipts.append(content_hash(receipt));phase_receipts.append(content_hash(receipt))
            require(receipt['result']=='OBSERVED' and receipt['bulk_checks']['freshness']=='WITHIN_AGE_BOUND','OBSERVATION_FAILED')
            starts.append(receipt['dispatch_time'])
            # Completion identity is derived from the trusted executor result and
            # exact day reservation, not from an untrusted self-labeled disk file.
            previous=completion_parent(request, i, previous, receipt)
        except Exception:
            reason='AMBIGUOUS_OR_FAILED_STOP';break
        if checkpoint is not None and (i==0 or i in (6,12,18)):
            checkpoint(row['phase'].lower(),'PASS',phase_receipts);phase_receipts=[]
    return receipts, reason
