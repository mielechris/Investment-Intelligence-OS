"""Test-only positive admission. No production selectors or account admission."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat

from alpha_market_baseline import RADAR_SCHEMA, require, verify_plan
from alpha_session_execution import read_pinned, safe_root, verify_destination, publish, read_record
from provider_gateway_contract import canonical, content_hash, pin, safe_document

SCOPE = 'SYNTHETIC_TEST_ONLY'
AUTHORITY = dict.fromkeys(('broker_connected', 'paper_order_permission',
                           'trade_execution_permission', 'live_execution'), False)
PINS = {'package', 'runtime', 'plan', 'universe', 'schedule', 'fixture', 'confinement'}


def exact_root(path):
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p and not p.is_symlink(), 'ROOT_ALIAS')
    require(p.parent == Path('/private/tmp') and
            p.name.startswith('iios-provider-connection-source-tests-'), 'TEST_ROOT_REQUIRED')
    st = p.stat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and
            not st.st_mode & 0o077, 'TEST_ROOT_OWNERSHIP')
    return p


def contained(root, path):
    p = Path(path)
    require(p.is_absolute() and p != root and p.resolve() == p and
            p.is_relative_to(root) and not p.is_symlink(), 'PATH_NOT_ADMITTED')
    for parent in (p, *p.parents):
        if parent == root:
            break
        require(not parent.is_symlink(), 'PATH_ALIAS')
    return p


def synthetic_document(value):
    safe_document(value)
    def walk(v):
        if isinstance(v, dict):
            require(not {'selectors', 'selector', 'service', 'account', 'credentials',
                         'network_addresses', 'host', 'url'} & set(v), 'REAL_BINDING_REJECTED')
            for child in v.values():
                walk(child)
        elif isinstance(v, (tuple, list)):
            for child in v:
                walk(child)
        elif isinstance(v, str):
            require('IIOS_' not in v and v != 'iios-provider' and
                    'Application Support' not in v and 'Keychains' not in v and
                    'https://' not in v, 'REAL_BINDING_REJECTED')
    walk(value)


@dataclass(frozen=True)
class SyntheticCapability:
    package_bytes: bytes
    runtime_bytes: bytes
    pins_bytes: bytes
    authorized_root: str
    runtime_identities: tuple
    output_identity: tuple

    def documents(self):
        return json.loads(self.package_bytes), json.loads(self.runtime_bytes), json.loads(self.pins_bytes)

    def recheck(self):
        p, r, pins = self.documents()
        identities = verify_inputs(p, r, pins, self.authorized_root)
        require(identities == self.runtime_identities, 'RUNTIME_IDENTITY_CHANGED')
        st = Path(p['root']).stat(follow_symlinks=False)
        require((st.st_dev, st.st_ino) == self.output_identity, 'OUTPUT_REPLACED')
        fd = safe_root(p['root'])
        os.close(fd)
        return p, r, pins


def verify_inputs(p, r, expected, authorized_root):
    root = exact_root(authorized_root)
    require(set(expected) == PINS, 'INDEPENDENT_PINS_REQUIRED')
    synthetic_document(p)
    synthetic_document(r)
    for name, doc in (('package', p), ('runtime', r), ('plan', p['plan']),
                      ('universe', p['plan']['universe']),
                      ('schedule', p['plan']['opportunity_schedule']), ('fixture', p['fixture'])):
        pin(doc, expected[name])
    require(set(p) == {'schema', 'scope', 'source_commit', 'runtime_parent', 'plan',
            'plan_parent', 'fixture', 'fixture_parent', 'confinement_parent',
            'root', 'authority'}, 'SYNTHETIC_PACKAGE_SCHEMA')
    require(p['schema'] == 'iios-alpha-radar-synthetic-package-v1' and
            p['scope'] == SCOPE and p['authority'] == AUTHORITY and all(v is False for v in p['authority'].values()), 'SYNTHETIC_SCOPE')
    require(re.fullmatch('[a-f0-9]{40}', p['source_commit']) is not None, 'SOURCE_PIN')
    require(p['runtime_parent'] == expected['runtime'] and p['plan_parent'] == expected['plan'] and
            p['fixture_parent'] == expected['fixture'] and
            p['confinement_parent'] == expected['confinement'], 'PARENT_MISMATCH')
    verify_plan(p['plan'], expected['plan'])
    require(p['plan']['schema'] == RADAR_SCHEMA and p['plan']['universe_parent'] == expected['universe'] and
            p['plan']['schedule_parent'] == expected['schedule'], 'RADAR_BINDING')
    out = contained(root, p['root'])
    require(p['plan']['root'] == str(out / 'journal'), 'JOURNAL_ROOT')
    for row in p['plan']['rows']:
        contained(out, row['root'])
    require(set(r) == {'scope', 'source_commit', 'root', 'files', 'interpreter',
                       'tls', 'source_files', 'confinement'}, 'RUNTIME_SCHEMA')
    require(r['scope'] == SCOPE and r['source_commit'] == p['source_commit'], 'RUNTIME_SCOPE')
    runtime = contained(root, r['root'])
    require(not out.is_relative_to(runtime) and not runtime.is_relative_to(out), 'ROOT_OVERLAP')
    rows = r['files']
    require(rows and len({v['path'] for v in rows}) == len(rows), 'RUNTIME_MEMBERSHIP')
    names = {v['path'] for v in rows}
    require(r['interpreter'] in names and r['tls'] in names and r['confinement'] in names and
            r['source_files'] and set(r['source_files']) <= names, 'RUNTIME_COMPONENTS')
    required_sources = {'alpha_session_execution.py', 'provider_gateway_https.py',
        'alpha_market_baseline.py', 'alpha_session_readiness.py', 'opportunity_spine_contract.py',
        'provider_gateway_contract.py', 'truth_spine_contract.py', 'truth_spine_process_identity.py',
        'alpha_radar_admission.py', 'alpha_radar_runner.py', 'alpha_radar_fixture.py', 'alpha_radar.sb.in'}
    require(len(r['source_files']) == len(required_sources) and
            {Path(n).name for n in r['source_files']} == required_sources, 'SOURCE_CLOSURE')
    # Credential/production adapters are deliberately absent from this closure.
    forbidden = {'provider_gateway_credentials.py', 'provider_gateway_qualification.py',
                 'provider_gateway_transport.py', 'alpha_session_runner.py'}
    require(not any(Path(n).name in forbidden for n in names), 'PRODUCTION_MODULE_REJECTED')
    actual = set()
    for path in (runtime, *runtime.rglob('*')):
        require(not path.is_symlink(), 'RUNTIME_ALIAS')
        st = path.stat(follow_symlinks=False)
        require(st.st_uid == os.getuid() and not st.st_mode & 0o222, 'RUNTIME_WRITABLE')
        if path.is_dir():
            continue
        actual.add(path.relative_to(runtime).as_posix())
    require(actual == names, 'RUNTIME_MEMBERSHIP')
    identities = tuple((v['path'], *read_pinned(runtime, v)) for v in rows)
    profile = next(v for v in rows if v['path'] == r['confinement'])
    require(profile['sha256'] == expected['confinement'], 'CONFINEMENT_PIN')
    f = p['fixture']
    require(set(f) == {'scope', 'address', 'port', 'server_name', 'certificate',
                      'certificate_sha256', 'private_key', 'responses', 'responses_sha256'}, 'FIXTURE_SCHEMA')
    require(f['scope'] == SCOPE and f['address'] == f['server_name'] == '127.0.0.1' and
            type(f['port']) is int and 1024 <= f['port'] <= 65535, 'LOOPBACK_PIN_REQUIRED')
    for key in ('certificate', 'private_key', 'responses'):
        require(f[key] in names, 'FIXTURE_FILE_PIN')
    for key in ('certificate', 'responses'):
        require(next(v for v in rows if v['path'] == f[key])['sha256'] == f[key + '_sha256'], 'FIXTURE_FILE_PIN')
    require(r['tls'] == f['certificate'], 'FIXTURE_TLS_PIN')
    return identities


def admit(p, r, *, expected, authorized_root):
    identities = verify_inputs(p, r, expected, authorized_root)
    out = Path(p['root'])
    # No exist_ok, recovery reuse, aliases or arbitrary temporary-root allowance.
    out.mkdir(mode=0o700)
    st = out.stat()
    return SyntheticCapability(canonical(p), canonical(r), canonical(expected),
                               str(authorized_root), identities, (st.st_dev, st.st_ino))


def envelope(value, parents):
    synthetic_document(value)
    doc = {'schema': 'iios-radar-synthetic-receipt-v1', 'scope': SCOPE,
           'authority': AUTHORITY, 'parents': parents, 'value': value}
    return {**doc, 'content_hash': content_hash(doc)}


def verify_envelope(doc, expected, *, parents):
    pin(doc, expected)
    require(set(doc) == {'schema', 'scope', 'authority', 'parents', 'value', 'content_hash'}, 'RECEIPT_SCHEMA')
    require(doc['schema'] == 'iios-radar-synthetic-receipt-v1' and doc['scope'] == SCOPE and
            doc['authority'] == AUTHORITY and all(v is False for v in doc['authority'].values()) and doc['parents'] == parents, 'RECEIPT_AUTHORITY')
    require(content_hash({k:v for k,v in doc.items() if k != 'content_hash'}) == doc['content_hash'], 'RECEIPT_HASH')
    synthetic_document(doc['value'])
    return doc['value']


def store(cap, name, value):
    # Incident persistence must survive runtime tampering. Revalidate only the
    # already-admitted output identity; never grant dispatch from this function.
    require(type(cap) is SyntheticCapability, 'SYNTHETIC_CAPABILITY_REQUIRED')
    p, _, pins = cap.documents()
    root = exact_root(cap.authorized_root)
    out = contained(root, p['root'])
    fd = safe_root(out)
    try:
        st = os.fstat(fd)
        require((st.st_dev, st.st_ino) == cap.output_identity, 'OUTPUT_REPLACED')
        verify_destination(fd, out)
        return publish(fd, name, envelope(value, pins))
    finally:
        os.close(fd)
