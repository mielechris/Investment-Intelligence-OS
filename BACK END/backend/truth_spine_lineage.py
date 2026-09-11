"""Historical lineage admission. Preserved databases are byte sources, never SQLite inputs.

Receipts are exclusive-create. Only the six accepted files have owner provenance;
siblings in their quarantined directory are neither opened nor admitted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import closing
from pathlib import Path

from truth_spine_contract import canonical, digest, seal, verified, utc

OWNER_ROOT = Path('/private/tmp/iios-northstar-owner-snapshots-sb37-attempt2')
OWNER_PINS = {
    'manifest.json': ('88bb82aebaa661978a4f03e8d4b0c926f2dd4fa3717a47938fa44883ed1b3ba9', 3729),
    'completion-receipt.json': ('b3db70d1ff84f88c7aa6fcadead513dd618697b945511dbeed332abcf1d8cc48', 749),
    'l7/snapshot.db': ('89f03e445149d06b3bff1030df2d647edddeafa8561734126cfcd358aa6ad27e', 351170560),
    'l8/snapshot.db': ('bb2e8b1223af91b1813a4502d6c2d694beec3b8393f03b1a29474ce737d354c9', 1351712768),
    'l7/receipt.json': ('21a2f07a0ccdcfbdac7e35d1e39e91394946ea1dac0ffe3e41d1a4e5b2444681', 1184),
    'l8/receipt.json': ('69b50545db38a2dd1fe958ada956395547fd6601e106a9f544eea2ecc80ff457', 945),
}
WATERMARK = '2026-09-11T02:13:28.480261Z'
CAPTURE_COMMIT = 'c7525bc54efc40d4771bf0d1fe25409fa5c7e5ca'
SCOPE = 'SIX_PINNED_OWNER_FILES'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def hex_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def safe_path(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_PATH_REQUIRED')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK_REJECTED')
    require(path == path.resolve(), 'CANONICAL_PATH_REQUIRED')
    return path


def contained(root, relative):
    root = safe_path(root)
    rel = Path(relative)
    require(not rel.is_absolute() and '..' not in rel.parts and rel.parts, 'RELATIVE_PATH_REQUIRED')
    path = safe_path(root / rel)
    require(path != root and path.is_relative_to(root), 'ROOT_ESCAPE')
    return path


def regular(path):
    path = safe_path(path)
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid(), 'OWNER_REGULAR_REQUIRED')
    require(not s.st_mode & 0o022, 'WRITABLE_INPUT_REJECTED')
    return s


def fingerprint(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def file_hash(path):
    before = regular(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before), 'INPUT_REPLACED')
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
        require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before), 'INPUT_CHANGED')
    require(fingerprint(regular(path)) == fingerprint(before), 'INPUT_CHANGED')
    return h.hexdigest()


def check_pin(row):
    require(set(row) == {'path', 'sha256', 'bytes', 'mode'}, 'FILE_PIN_SCHEMA')
    require(hex_hash(row['sha256']) and type(row['bytes']) is int and row['bytes'] >= 0,
            'INDEPENDENT_PIN_REQUIRED')
    s = regular(row['path'])
    require(s.st_size == row['bytes'] and stat.S_IMODE(s.st_mode) == row['mode'], 'FILE_METADATA_MISMATCH')
    require(file_hash(row['path']) == row['sha256'], 'FILE_HASH_MISMATCH')
    return row


def write_new(root, relative, data, mode=0o400):
    """No replace, unlink, chmod of existing files, or implicit directory creation."""
    path = contained(root, relative)
    require(path.parent.is_dir(), 'DESTINATION_PARENT_REQUIRED')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(data).hexdigest()


def copy_pinned(row, root, relative):
    check_pin(row)
    original = regular(row['path'])
    dest = contained(root, relative)
    require(dest != Path(row['path']) and not dest.exists(), 'NEW_WORKING_COPY_REQUIRED')
    source_fd = os.open(row['path'], os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(source_fd, 'rb') as source:
        require(fingerprint(os.fstat(source.fileno())) == fingerprint(original), 'INPUT_REPLACED')
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, 'wb') as target:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                target.write(block)
            target.flush()
            os.fsync(target.fileno())
        require(fingerprint(os.fstat(source.fileno())) == fingerprint(original), 'INPUT_CHANGED')
    copied = regular(dest)
    require(copied.st_nlink == 1 and (copied.st_dev, copied.st_ino) !=
            (original.st_dev, original.st_ino), 'WORKING_COPY_ALIAS')
    require(file_hash(dest) == row['sha256'] and copied.st_size == row['bytes'], 'COPY_HASH_MISMATCH')
    require(fingerprint(regular(row['path'])) == fingerprint(original), 'INPUT_CHANGED')
    require(file_hash(row['path']) == row['sha256'], 'SOURCE_AFTER_COPY_MISMATCH')
    directory=os.open(dest.parent,os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)
    return {'source_sha256': row['sha256'], 'working_sha256': row['sha256'],
            'source_after_sha256': row['sha256'], 'bytes': copied.st_size, 'path': relative,
            'canonical_path':str(dest),'device':copied.st_dev,'inode':copied.st_ino,'creation':'VERIFIED_BYTE_COPY'}


def working_sqlite_receipt(policy, copies):
    """Register only the two individually admitted byte copies, never a directory."""
    root=policy.validate();rows=[]
    require(set(copies)=={'L7_WORKING_COPY','L8_WORKING_COPY'},'EXACT_WORKING_ROLES_REQUIRED')
    for role,copy in copies.items():
        path=contained(root,copy['path']);info=regular(path)
        require(path.is_relative_to(root/'working-inputs') and str(path)==copy['canonical_path'] and
                copy['creation']=='VERIFIED_BYTE_COPY' and info.st_nlink==1 and
                info.st_dev==copy['device'] and info.st_ino==copy['inode'] and
                copy['source_sha256']==copy['working_sha256']==copy['source_after_sha256']==file_hash(path),
                'VERIFIED_COPY_REQUIRED')
        rows.append({'role':role,'path':str(path),'device':info.st_dev,'inode':info.st_ino,
                     'creation':'VERIFIED_BYTE_COPY','source_hash':copy['source_sha256'],
                     'copied_hash':copy['working_sha256'],'source_after_hash':copy['source_after_sha256']})
    doc=seal({'schema':'iios-working-sqlite-admission-v1','root':str(root),'run_identity':policy.run_identity,
              'package_identity':policy.package_identity,'databases':rows})
    return write_new(root,'admission/sqlite-working-copies.json',canonical(doc))


def check_working_sqlite(root, relative, expected, *, capability=None):
    from truth_spine_adapters import connect_strict_sqlite, validate_sqlite_capability, verify_strict_connection
    path = contained(root, relative)
    require(path.is_relative_to(contained(root, 'working-inputs')), 'WORKING_SQLITE_ONLY')
    require(validate_sqlite_capability(capability)==path,'WORKING_CAPABILITY_PATH_MISMATCH')
    require(regular(path).st_nlink == 1 and file_hash(path) == expected, 'WORKING_PIN_MISMATCH')
    # These are already complete pinned snapshots. No preserved WAL is consulted.
    with closing(verify_strict_connection(connect_strict_sqlite(capability),capability)) as db:
        require(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'SQLITE_QUICK_CHECK')
        require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'SQLITE_INTEGRITY')
        require(db.execute('PRAGMA foreign_key_check').fetchall() == [], 'SQLITE_FOREIGN_KEYS')
    require(file_hash(path) == expected, 'WORKING_DATABASE_CHANGED')


def working_capability(admission, expected_admission_hash, role):
    from truth_spine_adapters import SQLiteCapability, active_sqlite_policy
    require(hex_hash(expected_admission_hash) and hashlib.sha256(canonical(admission)).hexdigest()==expected_admission_hash,
            'INDEPENDENT_ADMISSION_HASH_REQUIRED')
    verified(admission)
    policy=active_sqlite_policy()
    require(policy is not None,'STRICT_SQLITE_POLICY_REQUIRED')
    root=policy.validate()
    name={'L7_WORKING_COPY':'l7/snapshot.db','L8_WORKING_COPY':'l8/snapshot.db'}.get(role)
    require(name is not None,'WORKING_ROLE_REQUIRED')
    row=admission['files'][name]
    return SQLiteCapability(role,str(contained(root,row['path'])),'ro-immutable',
                            str(root/'admission/sqlite-working-copies.json'),admission['sqlite_admission_hash'],policy=policy)


def load_spec(path, expected, commit):
    require(hex_hash(expected) and file_hash(path) == expected, 'INPUT_SPEC_PIN_REQUIRED')
    spec = json.loads(Path(path).read_bytes())
    require(set(spec) == {'schema', 'source_commit', 'owner_files', 'common_watermark',
                         'auxiliary', 'runtime', 'baseline', 'run_root', 'port', 'duration_seconds'}, 'INPUT_SPEC_SCHEMA')
    require(spec['schema'] == 'iios-historical-lineage-inputs-v1' and
            spec['source_commit'] == commit and re.fullmatch('[0-9a-f]{40}', commit), 'SOURCE_PIN_MISMATCH')
    require(spec['common_watermark'] == WATERMARK and set(spec['owner_files']) == set(OWNER_PINS), 'OWNER_SCOPE_MISMATCH')
    for name, (h, size) in OWNER_PINS.items():
        row = spec['owner_files'][name]
        require(row['path'] == str(OWNER_ROOT/name) and row['sha256'] == h and row['bytes'] == size,
                'ACCEPTED_OWNER_PIN_MISMATCH')
        check_pin(row)
    manifest = json.loads((OWNER_ROOT/'manifest.json').read_bytes())
    completion = json.loads((OWNER_ROOT/'completion-receipt.json').read_bytes())
    require(manifest['source_commit'] == CAPTURE_COMMIT and manifest['common_reconciliation_watermark_utc'] == WATERMARK
            and completion['manifest_hash'] == manifest['content_hash'] and completion['status'] == 'VERIFIED',
            'OWNER_RECEIPT_BINDING_MISMATCH')
    verified(manifest)
    root = safe_path(spec['run_root'])
    require(root.parent == Path('/private/tmp') and root.name.startswith('iios-truth-spine-3-acceptance-sb38d-clean-')
            and not root.exists(), 'FRESH_LINEAGE_ROOT_REQUIRED')
    require(type(spec['port']) is int and 1024 < spec['port'] < 65536 and
            spec['port'] not in {5176,5177,5184,5185,5186,5291,5292,8002}, 'ISOLATED_PORT_REQUIRED')
    require(type(spec['duration_seconds']) is int and 1 <= spec['duration_seconds'] <= 3600, 'BOUNDED_DURATION_REQUIRED')
    names = [r['target'] for r in spec['auxiliary']]
    required = {'universe-current.json', 'research.json', 'event_reconstruction.json', 'macro_regime.json',
                'validation_9h.json', 'shadow_9i.json', 'outcomes_9j.json', 'executor/selected-session.json'}
    require(required <= set(names) and len(set(names)) == len(names), 'COMPLETE_AUXILIARY_PINS_REQUIRED')
    for item in spec['auxiliary']:
        contained(root/'working-inputs', item['target'])
        require(item['target'] in required or item['target'].startswith('executor/'), 'AUXILIARY_TARGET_REJECTED')
        p = Path(item['pin']['path'])
        require('Application Support' not in p.parts and not any('acceptance-sb' in s for s in p.parts), 'RETAINED_INPUT_FALLBACK_REJECTED')
        check_pin(item['pin'])
    verify_executor_inputs({r['target']:r['pin'] for r in spec['auxiliary'] if r['target'].startswith('executor/')})
    return spec


def verify_executor_inputs(pins):
    """Verify the retained graph without instantiating an executor or any provider."""
    documents={};used=set();visiting=set();done=set()
    for target,pin in pins.items():
        rel=Path(target)
        require(not rel.is_absolute() and '..' not in rel.parts and rel.parts[0]=='executor','EXECUTOR_PATH_INVALID')
        check_pin(pin)
        raw=Path(pin['path']).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==pin['sha256'],'EXECUTOR_INPUT_PIN_MISMATCH')
        value=json.loads(raw)
        if '/evidence/' not in target: verified(value)
        documents[target]=value
    def take(target):
        require(target in documents,'EXECUTOR_DEPENDENCY_NOT_PINNED');used.add(target);return documents[target]
    selector=take('executor/selected-session.json')
    selected=Path(selector['selected_root'])
    require(selected.parts and not selected.is_absolute() and '..' not in selected.parts,'EXECUTOR_SELECTED_PATH_INVALID')
    base='executor/'+selected.as_posix()
    state=take(base+'/executor-state.json');plan=take(base+'/request-plan.json')
    require(state.get('schema_version')=='iios-operational-market-executor-v1' and
            plan.get('schema_version')=='iios-operational-market-request-plan-v1' and
            selector.get('schema') in {'iios-operational-market-session-selector-v'+str(i) for i in range(1,5)},
            'EXECUTOR_SCHEMA_INVALID')
    plan_hash=hashlib.sha256(json.dumps(plan['rows'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if plan['rows'] and plan['rows'][0].get('session_date')=='2026-09-09' and plan['rows'][0].get('provider') and plan['rows'][0].get('plan')=='SEPTEMBER_9_MARKET_OPEN_50':
        from expansion_wing.september_9_canonical_plan import canonical_plan_identity, validate_canonical_plan
        plan_hash=canonical_plan_identity(validate_canonical_plan(tuple(plan['rows'])))
    require(plan_hash==selector['plan_identity']==plan['plan_identity']==state['plan_identity'],'EXECUTOR_PLAN_PARENT_MISMATCH')
    rows={r['identity']:r for r in plan['rows']}
    require(len(rows)==len(plan['rows']) and set(rows)==set(state['requests']),'EXECUTOR_REQUEST_MEMBERSHIP_MISMATCH')
    for identity,item in state['requests'].items():
        require(isinstance(identity,str) and re.fullmatch('[A-Za-z0-9_-]{1,160}',identity),'EXECUTOR_REQUEST_ID_INVALID')
        lifecycle=item['lifecycle']
        require(lifecycle in {'PLANNED','CONFIRMED','AMBIGUOUS','FAILED_PRETRANSMISSION'},'EXECUTOR_UNRESOLVED_LIFECYCLE')
        if lifecycle=='PLANNED':continue
        receipt=take(base+'/receipts/'+identity+'.json')
        require(receipt['request_identity']==identity and receipt['status']==lifecycle and
                all(receipt[k]==rows[identity][k] for k in ('ticker','endpoint','window')),'EXECUTOR_RECEIPT_PARENT_MISMATCH')
        if lifecycle=='CONFIRMED':
            evidence=base+'/evidence/'+identity+'.json';take(evidence)
            require(receipt['evidence_hash']==pins[evidence]['sha256'] and receipt['response_bytes']==pins[evidence]['bytes'],
                    'EXECUTOR_EVIDENCE_PARENT_MISMATCH')
    # Optional retained parent links must resolve independently. No missing
    # supersession/archive/adoption parent is filled from another directory.
    def parents(target):
        require(target not in visiting,'EXECUTOR_PARENT_CYCLE')
        if target in done:return
        visiting.add(target)
        doc=documents[target]
        if '/evidence/' not in target:
            for key,value in doc.items():
                if not key.endswith('_hash') or key in {'content_hash','normalized_hash','evidence_hash'}:continue
                require(hex_hash(value),'EXECUTOR_PARENT_HASH_INVALID')
                matches=[name for name,d in documents.items() if name!=target and
                         (pins[name]['sha256']==value or isinstance(d,dict) and d.get('content_hash')==value)]
                require(len(matches)==1,'EXECUTOR_UNRESOLVED_PARENT')
                used.add(matches[0]);parents(matches[0])
        visiting.remove(target);done.add(target)
    for target in list(used):parents(target)
    require(used==set(pins),'EXECUTOR_EXTRA_UNBOUND_INPUT')
    return {'selector_hash':pins['executor/selected-session.json']['sha256'],
            'state_hash':pins[base+'/executor-state.json']['sha256'],'plan_hash':pins[base+'/request-plan.json']['sha256'],
            'files':{name:pins[name]['sha256'] for name in sorted(used)}}


def admit(spec, root, spec_hash):
    """Caller completes every external-input/runtime/baseline check first."""
    root = safe_path(root)
    from truth_spine_adapters import active_sqlite_policy
    policy=active_sqlite_policy()
    require(policy is not None and policy.root==str(root) and policy.run_identity==spec_hash,'ADMISSION_RUN_POLICY_REQUIRED')
    root.mkdir(mode=0o700)
    for name in ('admission', 'working-inputs', 'receipts', 'state', 'browser', 'baselines', 'rollback', 'logs'):
        (root/name).mkdir(mode=0o700)
    rows = {}
    for name, pin in spec['owner_files'].items():
        target = 'working-inputs/owner/' + name
        (root/target).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        rows[name] = copy_pinned(pin, root, target)
    for item in spec['auxiliary']:
        target = 'working-inputs/' + item['target']
        (root/target).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        copy_pinned(item['pin'], root, target)
    from truth_spine_adapters import active_sqlite_policy
    policy=active_sqlite_policy()
    require(policy is not None and policy.root==str(root) and policy.run_identity==spec_hash,'ADMISSION_RUN_POLICY_REQUIRED')
    sqlite_pin=working_sqlite_receipt(policy,{'L7_WORKING_COPY':rows['l7/snapshot.db'],'L8_WORKING_COPY':rows['l8/snapshot.db']})
    receipt = seal({'schema':'iios-working-admission-v1', 'scope':SCOPE,'sqlite_admission_hash':sqlite_pin,
                    'input_spec_sha256':spec_hash, 'source_commit':spec['source_commit'],
                    'common_watermark':spec['common_watermark'], 'files':rows})
    admission_pin=write_new(root, 'admission/working-copies.json', canonical(receipt))
    for name in ('l7/snapshot.db', 'l8/snapshot.db'):
        role='L7_WORKING_COPY' if name.startswith('l7/') else 'L8_WORKING_COPY'
        check_working_sqlite(root, rows[name]['path'], rows[name]['working_sha256'],
                             capability=working_capability(receipt,admission_pin,role))
    return receipt


def historical_generation(sources, admission, intent, *, admission_hash=None):
    """Pure normalized-event adapter. Source paths must already be working-only."""
    from truth_spine_adapters import read_strict_ledger, read_document, universe_version
    events, files, universes = [], [], []
    for spec in sources:
        if spec['kind'] == 'universe':
            u = universe_version(spec, previous=universes[-1]['capture_id'] if universes else None)
            universes.append(u)
            continue
        if spec['kind'] in {'operational','historical'}:
            role='L7_WORKING_COPY' if spec['kind']=='operational' else 'L8_WORKING_COPY'
            rows=read_strict_ledger(spec,capability=working_capability(admission,admission_hash,role))
        else: rows=read_document(spec)
        clocks = {k:sorted({r[k] for r in rows if r.get(k)}) for k in ('event_time','observation_time','publication_time')}
        files.append({'store':spec['store_id'], 'kind':spec['kind'], 'sha256':spec['sha256'],
                      'records':len(rows), 'capture_end':admission['common_watermark'],
                      'classifications':sorted({r['classification'] for r in rows}), 'clocks':clocks})
        for r in rows:
            events.append(seal({'id':r['record_id'], 'store':r['source_store_identity'], 'type':r['record_type'],
                                'payload_hash':r['original_content_hash'], 'classification':r['classification'],
                                **{k:r.get(k) for k in clocks}, 'coverage':r.get('coverage',{})}))
    require(len({e['id'] for e in events}) == len(events), 'DUPLICATE_HISTORICAL_IDENTITY')
    watermark = {'count':len(events), 'identity':digest({'events':sorted(e['id'] for e in events)})}
    generation = seal({'schema':'iios-admitted-historical-generation-v1', 'session':'historical-'+intent[:16],
                       'identity':admission['content_hash'], 'files':files, 'universes':universes,
                       'original_common_watermark':admission['common_watermark'], 'watermark':watermark,
                       'events_hash':digest({'events':events}), 'package_generation':intent})
    return generation, events


def historical_cycle(generation, admission, intent, commit, at, package_hash=None):
    from truth_spine_generations import cycle_identity
    utc(at)
    value = {'schema':'iios-historical-publisher-cycle-v1', 'session':generation['session'],
             'generation':generation['content_hash'], 'phase':'SESSION_CLOSED', 'stores':generation['files'],
             'admission_hash':admission['content_hash'], 'owner_files':{k:v['source_sha256'] for k,v in admission['files'].items()},
             'common_watermark':admission['common_watermark'], 'record_watermark':generation['watermark'],
             'classification':'HISTORICAL_REPLAY', 'source_commit':commit, 'package_generation':intent,
             'package_hash':package_hash, 'producer_role':'isolated_publisher', 'published_at':at}
    value['source_cycle_id'] = cycle_identity(value)
    return value


def verify_chain(root, manifest):
    """Package-local verification never reopens original owner paths."""
    root = safe_path(root)
    chain = manifest['lineage']
    expected = {'input_spec','admission','generation','events','initial_cycle','package_generation'}
    require(set(chain) == expected and hex_hash(chain['package_generation']), 'LINEAGE_SCHEMA')
    docs = {}
    for name in expected - {'package_generation'}:
        row = chain[name]
        p = contained(root, row['path'])
        require(file_hash(p) == row['sha256'], 'LINEAGE_FILE_MISMATCH')
        docs[name] = json.loads(p.read_bytes())
    a, g, c = (docs[k] for k in ('admission','generation','initial_cycle'))
    verified(a); verified(g)
    spec=docs['input_spec']
    verify_executor_inputs({r['target']:{**r['pin'],'path':str(contained(root,'working-inputs/'+r['target'])),'mode':0o400}
                            for r in spec['auxiliary'] if r['target'].startswith('executor/')})
    require(spec['source_commit']==manifest['source_base'] and spec['run_root']==str(root)
            and spec['common_watermark']==a['common_watermark']==WATERMARK, 'SPEC_PARENT_MISMATCH')
    intent=digest({'schema':'iios-package-generation-intent-v1','source_commit':manifest['source_base'],
                   'input_spec_sha256':chain['input_spec']['sha256'],'frontend_input_hash':manifest['frontend_input_hash'],
                   'frontend_output_hash':manifest['frontend_content_hash']})
    require(intent==chain['package_generation'],'PACKAGE_INTENT_MISMATCH')
    require(a['scope'] == SCOPE and a['source_commit'] == manifest['source_base'] and
            a['input_spec_sha256'] == chain['input_spec']['sha256'], 'ADMISSION_PARENT_MISMATCH')
    require(g['identity'] == a['content_hash'] and g['package_generation'] == chain['package_generation'] and
            g['events_hash'] == digest({'events':docs['events']}), 'GENERATION_PARENT_MISMATCH')
    require(c == historical_cycle(g,a,chain['package_generation'],manifest['source_base'],c['published_at']),
            'CYCLE_PARENT_MISMATCH')
    for name, row in a['files'].items():
        require(name in OWNER_PINS and row['source_sha256'] == OWNER_PINS[name][0] and
                row['source_sha256'] == row['working_sha256'] == row['source_after_sha256'] and
                row['bytes']==OWNER_PINS[name][1] and row['path']=='working-inputs/owner/'+name,
                'OWNER_PIN_CHAIN_MISMATCH')
        p = contained(root, row['path'])
        require(p.is_relative_to(root/'working-inputs') and file_hash(p) == row['working_sha256'], 'WORKING_CHAIN_MISMATCH')
    require(set(a['files']) == set(OWNER_PINS), 'OWNER_SCOPE_MISMATCH')
    return docs
