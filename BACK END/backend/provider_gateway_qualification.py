"""Opt-in qualification only. No CLI, scheduler, installation or operational activation."""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import uuid

from provider_gateway_contract import canonical, content_hash, locked_authority, pin, safe_document, PROVIDER_ROLES
from provider_gateway_live_contract import Admission, admit, require, verify_qualification_receipt
from provider_gateway_credentials import MacKeychain, credential_scope
from provider_gateway_transport import NativeHTTPS, exchange
from provider_gateway_wire import decode


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


def verify_runtime(admission):
    require(type(admission) is Admission, 'ADMISSION_REQUIRED')
    m, _, r = admission.documents()
    require(set(r) == {'scope', 'source_commit', 'root', 'files', 'interpreter', 'tls', 'source_files', 'network_addresses'}, 'RUNTIME_SCHEMA')
    root = Path(r['root'])
    fd = safe_root(root, immutable=True)
    try:
        names = [row['path'] for row in r['files']]
        require(names and len(names) == len(set(names)), 'RUNTIME_INVENTORY')
        actual = set()
        for path in root.rglob('*'):
            require(not path.is_symlink(), 'RUNTIME_ALIAS')
            if path.is_dir():
                st = path.stat()
                require(st.st_uid == os.getuid() and not st.st_mode & 0o222, 'RUNTIME_DIRECTORY_MODE')
            else:
                actual.add(path.relative_to(root).as_posix())
        require(actual == set(names), 'RUNTIME_INVENTORY')
        identities = {row['path']: read_pinned(root, row) for row in r['files']}
        require(r['interpreter'] in identities and r['tls'] in identities and r['source_files'], 'RUNTIME_COMPONENTS')
        require(all(path in identities for path in r['source_files']), 'SOURCE_INVENTORY')
        require(next(x for x in r['files'] if x['path'] == r['interpreter'])['mode'] == 0o500, 'EXECUTABLE_MODE')
        import ipaddress
        require(m['provider'] in r['network_addresses'], 'NETWORK_ADDRESS_PIN')
        ipaddress.IPv4Address(r['network_addresses'][m['provider']])
        if m['mode'] == 'LIVE_QUALIFICATION':
            require(Path(sys.executable).resolve() == root / r['interpreter'] and Path(sys.prefix).resolve().is_relative_to(root), 'RUNNING_INTERPRETER_MISMATCH')
            required = {'provider_gateway_live_contract.py', 'provider_gateway_credentials.py', 'provider_gateway_transport.py', 'provider_gateway_wire.py', 'provider_gateway_qualification.py', 'provider_gateway_contract.py', 'provider_gateway_adapters.py', 'truth_spine_contract.py'}
            require({Path(p).name for p in r['source_files']} == required, 'SOURCE_CLOSURE')
            for name in required:
                module = sys.modules.get(name[:-3])
                require(module is not None and Path(module.__file__).resolve() in [root / p for p in r['source_files']], 'IMPORTED_SOURCE_MISMATCH')
            # Every loaded Python/extension file must belong to the pinned closure.
            for module in tuple(sys.modules.values()):
                path = getattr(module, '__file__', None)
                if path:
                    resolved = Path(path).resolve()
                    require(resolved.is_relative_to(root) and resolved.relative_to(root).as_posix() in identities, 'EXTERNAL_MODULE_REJECTED')
        return identities
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


def recover_prior(fd, admission, *, recovery, expected_recovery, existing_batch):
    """Use only caller-trusted recovery pins, never pins inferred from disk records.

    The recovery document is independently approved for this exact next request.
    It cannot grant a new request slot or clear a consumed/ambiguous reservation.
    """
    m, _, _ = admission.documents()
    names = set(os.listdir(fd))
    groups = [{name.removesuffix(suffix) for name in names if name.endswith(suffix)}
              for suffix in ('.reserved.json', '.receipt.json', '.response.json')]
    require(groups[0] == groups[1] == groups[2], 'INCOMPLETE_RECOVERY_ARTIFACT_SET')
    prior = groups[0]
    require(prior <= set(PROVIDER_ROLES) - {'YAHOO'}, 'RECOVERY_PROVIDER_SET')
    if not prior and recovery is None and expected_recovery is None:
        require(not existing_batch, 'EXISTING_BATCH_REQUIRES_RECOVERY')
        return {}
    require(isinstance(recovery, dict) and expected_recovery is not None, 'INDEPENDENT_RECOVERY_REQUIRED')
    safe_document(recovery)
    pin(recovery, expected_recovery)
    # Freeze caller data after verification; receipt fields never supply trust.
    recovery = json.loads(canonical(recovery))
    require(set(recovery) == {'schema', 'batch', 'next_request', 'entries'}, 'RECOVERY_SCHEMA')
    batch = {'batch_id': m['batch_id'], 'root': m['root'], 'scope': m['mode'],
             'source_commit': m['source_commit'], 'runtime_parent': dict(admission.parents)['runtime']}
    require(recovery['schema'] == 'iios-provider-recovery-v1' and recovery['batch'] == batch,
            'RECOVERY_BATCH_MISMATCH')
    require(recovery['next_request'] == dict(admission.parents)['manifest'], 'RECOVERY_REQUEST_REPLAY')
    entries = recovery['entries']
    require(isinstance(entries, dict) and set(entries) == prior, 'RECOVERY_MEMBERSHIP')
    verified = {}
    for provider in sorted(prior):
        entry = entries[provider]
        require(isinstance(entry, dict) and set(entry) == {'request_id', 'parents', 'reservation_sha256', 'receipt_sha256', 'response_sha256'}, 'RECOVERY_ENTRY_SCHEMA')
        parents = entry['parents']
        require(isinstance(parents, dict) and set(parents) == {'manifest', 'account', 'runtime'}, 'RECOVERY_PARENTS_REQUIRED')
        require(entry['request_id'] == parents['manifest'] and parents['runtime'] == batch['runtime_parent'], 'RECOVERY_REQUEST_PARENT')
        for value in (*parents.values(), entry['request_id'], entry['reservation_sha256'], entry['receipt_sha256'], entry['response_sha256']):
            require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'RECOVERY_PIN_REQUIRED')
        reservation = read_record(fd, provider + '.reserved.json', expected_hash=entry['reservation_sha256'])
        shared = {'provider': provider, 'role': PROVIDER_ROLES[provider], 'request_id': entry['request_id'],
                  'batch_id': m['batch_id'], 'root': m['root'], 'scope': m['mode'], 'source_commit': m['source_commit']}
        require(isinstance(reservation, dict) and reservation.get('schema') == 'iios-provider-reservation-v1', 'RESERVATION_SCHEMA')
        require(all(reservation.get(k) == v for k, v in shared.items()) and reservation.get('parents') == parents,
                'RESERVATION_IDENTITY_MISMATCH')
        require(reservation.get('attempts') == 1 and type(reservation['attempts']) is int and
                reservation.get('authority') == locked_authority() and all(v is False for v in reservation['authority'].values()), 'RESERVATION_AUTHORITY')
        receipt_parents = {**parents, 'reservation': entry['reservation_sha256']}
        receipt = read_record(fd, provider + '.receipt.json', expected_hash=entry['receipt_sha256'])
        verify_qualification_receipt(receipt, entry['receipt_sha256'], parents=receipt_parents)
        require(all(receipt.get(k) == v for k, v in shared.items()), 'RECOVERY_RECEIPT_IDENTITY')
        require(receipt.get('maximum_reserved_cost') == reservation.get('maximum_cost') and receipt.get('cost_unit') == reservation.get('cost_unit') and receipt.get('recovery_parent') == reservation.get('recovery_parent'), 'RECOVERY_BUDGET_MISMATCH')
        require(receipt.get('result') == 'OBSERVED' and receipt.get('http_status') == 200 and receipt.get('observations') is not None,
                'RECOVERY_NOT_SUCCESSFUL')
        response = read_record(fd, provider + '.response.json', expected_hash=entry['response_sha256'])
        require(isinstance(response, dict) and set(response) == {'raw_utf8', 'parents'} and response['parents'] == receipt_parents and isinstance(response['raw_utf8'], str), 'RECOVERY_RESPONSE_PARENTS')
        require(digest(response['raw_utf8'].encode('utf-8')) == receipt.get('raw_response_sha256'), 'RECOVERY_RESPONSE_HASH')
        # Recovery cannot upgrade billing, freshness or provider readiness.
        verified[provider] = receipt
    return verified


def qualify(manifest, account, runtime, *, expected, credential_backend, network, clock=None, recovery=None, expected_recovery=None):
    """All external boundaries explicit; mocks can produce OFFLINE_TEST evidence only.

    LIVE_QUALIFICATION uses wall time and exact native boundary types. A future
    owner authorization must pin the final source and complete runtime closure.
    """
    mode = manifest.get('mode')
    if mode == 'LIVE_QUALIFICATION':
        require(clock is None and type(credential_backend) is MacKeychain and type(network) is NativeHTTPS, 'LIVE_BOUNDARY_REQUIRED')
        clock = lambda: datetime.now(timezone.utc).isoformat()
    else:
        require(mode == 'OFFLINE_TEST' and callable(clock) and type(credential_backend) is not MacKeychain and type(network) is not NativeHTTPS, 'OFFLINE_BOUNDARY_REQUIRED')
    admission = admit(manifest, account, runtime, expected=expected, now=clock())
    m, a, _ = admission.documents()
    identities = verify_runtime(admission)
    fd = safe_root(m['root'])
    lock = None
    try:
        lock = os.open('batch.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        st = os.fstat(lock)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and st.st_nlink == 1 and stat.S_IMODE(st.st_mode) == 0o600, 'LOCK_IDENTITY')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binding = {'batch_id': m['batch_id'], 'root': m['root'], 'source_commit': m['source_commit'], 'runtime_parent': dict(admission.parents)['runtime'], 'scope': mode}
        existing_batch = False
        try:
            publish(fd, 'batch.json', binding)
        except FileExistsError:
            existing_batch = True
            require(read_record(fd, 'batch.json') == binding, 'BATCH_SUBSTITUTION')
        require('STOP.json' not in os.listdir(fd), 'BATCH_STOPPED')
        # Invalid recovery leaves every consumed reservation in place.
        prior = recover_prior(fd, admission, recovery=recovery, expected_recovery=expected_recovery, existing_batch=existing_batch)
        if m['provider'] in prior:
            receipt = prior[m['provider']]
            require(receipt['request_id'] == dict(admission.parents)['manifest'] and
                    receipt['parents'] == {**dict(admission.parents), 'reservation': recovery['entries'][m['provider']]['reservation_sha256']}, 'DUPLICATE_PROVIDER_REQUEST_REPLAY')
            verify_destination(fd, m['root'])
            return receipt  # Valid idempotent recovery never dispatches again.
        slot = m['provider'] + '.reserved.json'
        shared = {'provider': m['provider'], 'role': m['role'], 'request_id': dict(admission.parents)['manifest'],
                  'batch_id': m['batch_id'], 'root': m['root'], 'scope': mode, 'source_commit': m['source_commit']}
        reservation = {'schema': 'iios-provider-reservation-v1', **shared, 'parents': dict(admission.parents),
                       'maximum_cost': m['maximum_cost'], 'cost_unit': m['cost_unit'], 'attempts': 1,
                       'recovery_parent': expected_recovery, 'authority': locked_authority()}
        verify_destination(fd, m['root'])
        reservation_hash = publish(fd, slot, reservation)
        started = clock()
        result = {'schema': 'iios-provider-qualification-receipt-v1', **shared, 'recovery_parent': expected_recovery, 'scope': mode, 'provider': m['provider'], 'role': m['role'], 'parents': {**dict(admission.parents), 'reservation': reservation_hash}, 'start': started, 'end': None, 'result': 'UNVERIFIED', 'http_status': None, 'raw_response_sha256': None, 'normalized_sha256': None, 'observations': None, 'billing': 'UNVERIFIED', 'maximum_reserved_cost': m['maximum_cost'], 'cost_unit': m['cost_unit'], 'credential_selector_access_count': 0, 'retry_count': 0, 'provider_readiness': 'NOT_READY', 'authority': locked_authority()}
        failed = False
        try:
            admission.recheck(clock())
            require(verify_runtime(admission) == identities, 'RUNTIME_IDENTITY_CHANGED')
            # Retain an upper bound when a resolver fails partway through a pair.
            result['credential_selector_access_count'] = len(a['selectors'])
            result['credential_access_count_basis'] = 'ATTEMPT_UPPER_BOUND'
            with credential_scope(admission, backend=credential_backend, now=clock()) as material:
                result['credential_access_count_basis'] = 'COMPLETED_EXACT_LOOKUPS'
                verify_destination(fd, m['root'])
                response = exchange(admission, material, network=network, now=clock())
                result['http_status'] = response['status']
                require(response['body'] is not None, 'DISPATCH_UNVERIFIED')
                normalized = decode(admission, response['public'], received_at=clock())
                material.reject_echo(canonical(normalized))
                if a['retention'].get('mode') == 'EPHEMERAL_ALPHA_QUOTE':
                    # Fixed local classifications only: never persist or hash provider data.
                    result['retention_mode'] = 'EPHEMERAL_ALPHA_QUOTE'
                    result['qualification_checks'] = {
                        'authentication': 'ACCEPTED_FOR_THIS_REQUEST',
                        'endpoint_access': 'OBSERVED_VALID_MU_QUOTE',
                        'symbol': 'MU', 'price_validation': 'VALID_POSITIVE_DECIMAL',
                        'account_realtime_entitlement': 'PINNED_ACCOUNT_EVIDENCE',
                        'response_realtime_entitlement': 'UNVERIFIED',
                        'observed_quote_freshness': 'UNVERIFIED_NO_EVENT_INSTANT',
                        'timestamp_evidence': 'TRADING_DATE_ONLY' if response['public']['Global Quote'].get('07. latest trading day') else 'MISSING',
                    }
                    # Python cannot guarantee zeroization of immutable response bytes;
                    # drop references promptly, with no body/quote/hash publication.
                    del normalized, response
                else:
                    # Hash only after echo and public-schema checks, never secrets.
                    result['raw_response_sha256'] = digest(response['body'])
                    result['normalized_sha256'] = content_hash(normalized)
                    result['observations'] = normalized
                    verify_destination(fd, m['root'])
                    publish(fd, m['provider'] + '.response.json', {'raw_utf8': response['body'].decode('utf-8'), 'parents': result['parents']})
            require(verify_runtime(admission) == identities, 'RUNTIME_IDENTITY_CHANGED')
            result['result'] = 'OBSERVED'
        except Exception:
            failed = True
        result['end'] = clock()
        if failed:
            result['result'] = 'AMBIGUOUS_OR_UNVERIFIED_STOP'
            result['billing'] = 'AMBIGUOUS_MAXIMUM_RETAINED'
            publish(fd, 'STOP.json', {'provider': m['provider'], 'reservation': reservation_hash, 'reason': 'QUALIFICATION_UNVERIFIED', 'authority': locked_authority()})
        result['receipt_hash'] = content_hash(result)
        verify_destination(fd, m['root'])
        verify_qualification_receipt(result, content_hash(result), parents=result['parents'])
        publish(fd, m['provider'] + '.receipt.json', result)
        return result
    except Exception:
        # Persist a new, sanitized failure record; never overwrite earlier evidence.
        try:
            publish(fd, 'failure-' + uuid.uuid4().hex + '.json', {'reason': 'QUALIFICATION_BLOCKED', 'parents': dict(admission.parents), 'authority': locked_authority()})
        except Exception:
            pass  # The original write/path failure remains a hard error to caller.
        raise ValueError('QUALIFICATION_BLOCKED_EVIDENCE_PRESERVED_WHERE_WRITABLE') from None
    finally:
        if lock is not None:
            os.close(lock)
        os.close(fd)
