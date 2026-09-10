"""Permanent-capable read-only topology and persisted adapter projection.

Does not import the legacy app (whose startup schedules work). Canonical writes
are limited to a distinct observer event ledger, never an operational ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from truth_spine_adapters import file_bytes, read_document, read_ledger, reconcile, universe_version, validate_source
from truth_spine_authority import validate_authority
from truth_spine_contract import canonical, digest, seal, utc, verified

IDENTITIES = {"release", "runtime", "interpreter", "dependencies", "operational_ledger",
              "historical_ledger", "event_ledger", "executor_generation", "source_cycle",
              "evidence_receipt", "case_namespace", "projection_generation", "publisher",
              "frontend", "scheduler_owner", "publisher_owner", "rollback_parent"}
DAY_CHAIN = ("ELIGIBLE_ROOMS", "INTRADAY_SCANNER", "CATALYST", "MARKET_STRUCTURE",
             "POINT_IN_TIME_HISTORY", "GOVERNED_CASE", "INDEPENDENT_SKEPTIC", "COMMITTEE",
             "INTRADAY_RISK", "SEPARATE_PAPER_AUTHORIZATION", "POSITION_MONITORING", "CLOSE",
             "POSTMORTEM", "MEASURED_OUTCOME", "VALIDATED_MEMORY_ADMISSION")


def read_json(path: Path, expected: str | None = None) -> dict:
    x = json.loads(file_bytes(path, expected)); verified(x); return x


def atomic(path: Path, value: dict) -> None:
    """Only called for isolated/canonical observer output, not source adapters."""
    tmp = path.with_name(path.name+".staging")
    fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if tmp.exists(): tmp.unlink()


def derived_bindings(root: Path, manifest: dict, sources: list[dict]) -> dict:
    """Identity labels must match independently hash-verified artifact inputs."""
    runtime=read_json(Path(manifest['runtime_root'])/'runtime-manifest.json')
    release=manifest['release_id']
    publisher=next((row['sha256'] for row in manifest['files'] if row['path']=='backend/truth_spine_integration_service.py'),None)
    if not publisher:raise ValueError('PUBLISHER_ARTIFACT_MISSING')
    return {
        'runtime':runtime['runtime_id'],
        'event_ledger':release+'-canonical-events',
        'evidence_receipt':hashlib.sha256(file_bytes(root/'inputs/accepted-receipt.json')).hexdigest(),
        'case_namespace':'SOURCE_STORE_AND_OBJECT',
        'projection_generation':release+'-projection',
        'publisher':publisher,
        'frontend':digest({'files':[r for r in manifest['files'] if r['path'].startswith('frontend/')]}),
        'scheduler_owner':release+'-scheduler','publisher_owner':release+'-publisher',
        'rollback_parent':digest({'sources':sources}),
    }


def validate_frontend_provenance(manifest: dict) -> None:
    """Reconcile the pre-copy attestation with the immutable installed assets.

    This path never reaches back into the developer checkout or build toolchain.
    Preparation independently verifies those inputs before creating the package.
    """
    h = lambda value: hashlib.sha256(canonical(value)).hexdigest()
    try:
        p = manifest['frontend_provenance']; i = p['inputs']
        northstar = i['policy'].get('entry') == 'northstar-session.html'
        if northstar:
            from truth_spine_frontend_graph import NORTHSTAR_ENV
            if i['policy']['environment'] != NORTHSTAR_ENV or i['policy'].get('base') != '/review/':
                raise ValueError('NORTHSTAR_BUILD_POLICY_INVALID')
        if (manifest['source_state'] != 'CLEAN_COMMITTED_SOURCE'
                or p['schema'] != 'iios-truth-frontend-build-v1'
                or p['content_hash'] != h({k:v for k,v in p.items() if k != 'content_hash'})
                or i['source_commit'] != manifest['source_base']
                or p['input_hash'] != h(i) or manifest['frontend_input_hash'] != p['input_hash']
                or i['source_inventory_hash'] != h(i['source_inventory'])
                or i['policy']['mode'] != 'production'
                or (not northstar and i['policy']['environment'].get('VITE_TRUTH_INTEGRATION_PREVIEW') != '1')
                or i['policy']['sourcemap'] is not False
                or i['toolchain']['versions']['vite'] != '8.2.2'):
            raise ValueError('FRONTEND_PROVENANCE_INVALID')
        rows = [{**r, 'path': r['path'].removeprefix('frontend/')} for r in manifest['files'] if r['path'].startswith('frontend/')]
        if (rows != p['outputs'] or (not northstar and len(rows) != 6) or p['output_hash'] != h(rows)
                or manifest['frontend_content_hash'] != p['output_hash']
                or manifest['source_inventory_hash'] != digest({'files': [r for r in manifest['files'] if r['path'].startswith('backend/')]})):
            raise ValueError('FRONTEND_PACKAGE_BINDING_INVALID')
    except (KeyError, TypeError, AttributeError):
        raise ValueError('FRONTEND_PROVENANCE_REQUIRED') from None


def topology(path: Path, *, now: datetime | None = None) -> tuple[dict, dict]:
    t = read_json(path)
    required = {"schema", "mode", "root", "identities", "sources", "authority_path", "authority_hash",
                "release_manifest", "release_manifest_hash", "event_ledger_path", "selected_state",
                "selected_state_hash", "selector_path", "selector_hash", "source_cycle_path", "source_cycle_hash",
                "phase", "content_hash"}
    if (set(t) != required or t["schema"] != "iios-readonly-topology-v2"
            or t["mode"] not in {"ISOLATED_SHADOW", "PERMANENT_READ_ONLY"}
            or set(t["identities"]) != IDENTITIES
            or any(not isinstance(v, str) or not v for v in t["identities"].values())):
        raise ValueError("TOPOLOGY_INVALID")
    ids = t["identities"]
    if len({ids[k] for k in ("release", "executor_generation", "source_cycle", "projection_generation")}) != 4:
        raise ValueError("IDENTITY_COLLAPSE")
    root = Path(t["root"])
    if not root.is_absolute() or root.is_symlink() or path.parent != root:
        raise ValueError("TOPOLOGY_ROOT_INVALID")
    manifest = read_json(Path(t["release_manifest"]), t["release_manifest_hash"])
    if manifest["release_id"] != ids["release"]: raise ValueError("RELEASE_MISMATCH")
    package = Path(t["release_manifest"]).parent
    if manifest["schema"] != "iios-readonly-package-v1": raise ValueError("RELEASE_SCHEMA_INVALID")
    validate_frontend_provenance(manifest)
    expected = {r["path"] for r in manifest["files"]}
    actual = {str(p.relative_to(package)) for p in package.rglob('*') if p.is_file() and p.name != 'manifest.json'}
    if actual != expected: raise ValueError("RELEASE_INVENTORY_INVALID")
    for row in manifest["files"]:
        p = package/row["path"]
        if ".." in Path(row["path"]).parts or Path(row["path"]).is_absolute(): raise ValueError("RELEASE_PATH_INVALID")
        if len(file_bytes(p, row["sha256"])) != row["bytes"]: raise ValueError("RELEASE_SIZE_INVALID")
    if ids["interpreter"] != manifest["interpreter_hash"] or ids["dependencies"] != manifest["dependency_hash"]:
        raise ValueError("RUNTIME_BINDING_INVALID")
    runtime=Path(manifest['runtime_root'])
    expected_runtime={r['path'] for r in manifest['runtime_files']}
    actual_runtime={str(p.relative_to(runtime)) for p in runtime.rglob('*') if p.is_file()}
    if expected_runtime!=actual_runtime:raise ValueError('RUNTIME_INVENTORY_INVALID')
    for row in manifest['runtime_files']:
        rel=Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('RUNTIME_PATH_INVALID')
        if len(file_bytes(runtime/rel,row['sha256']))!=row['bytes']:raise ValueError('RUNTIME_FILE_INVALID')
    if any(ids[k]!=v for k,v in derived_bindings(root,manifest,t['sources']).items()):
        raise ValueError('DERIVED_IDENTITY_MISMATCH')
    owners = {k: ids[k+"_owner"] for k in ("scheduler", "publisher")}
    authority = read_json(Path(t["authority_path"]), t["authority_hash"])
    validate_authority(authority, binding=digest(ids), release=ids["release"], owners=owners,
                       now=now or datetime.now(timezone.utc))
    kinds = [s["kind"] for s in t["sources"]]
    if kinds.count("operational") != 1 or kinds.count("historical") != 1:
        raise ValueError("EXPLICIT_LEDGERS_REQUIRED")
    if len({s["path"] for s in t["sources"]}) != len(t["sources"]): raise ValueError("SOURCE_PATH_COLLISION")
    for spec in t["sources"]:
        validate_source(spec)
        if spec["kind"] in {"operational", "historical"} and ids[spec["kind"]+"_ledger"] != spec["store_id"]:
            raise ValueError("LEDGER_BINDING_INVALID")
    event = Path(t["event_ledger_path"])
    if event.parent != root or event.name != "canonical-events.db" or str(event) in {s["path"] for s in t["sources"]}:
        raise ValueError("CANONICAL_LEDGER_PATH_INVALID")
    state = read_json(Path(t["selected_state"]), t["selected_state_hash"])
    plan = read_json(Path(t['selected_state']).parent/'request-plan.json')
    selector = read_json(Path(t['selector_path']), t['selector_hash'])
    cycle = json.loads(file_bytes(Path(t['source_cycle_path']),t['source_cycle_hash']))
    selected_relative = Path(selector.get('selected_root',''))
    if selected_relative.is_absolute() or '..' in selected_relative.parts:
        raise ValueError('SELECTOR_PATH_INVALID')
    if (Path(t['selected_state']).parent != Path(t['selector_path']).parent/selected_relative
            or selected_relative.name != ids['executor_generation']
            or selector.get('plan_identity') != state.get('plan_identity')
            or plan.get('plan_identity') != state.get('plan_identity')
            or cycle.get('source_cycle_id') != ids['source_cycle'] or state.get("phase") != t["phase"]
            or state.get("released_credits") != 0
            or any(state.get(k) != "LOCKED" for k in ("stage_a", "stage_b", "stage_c"))):
        raise ValueError("SELECTED_STATE_INVALID")
    if (state.get('schema_version')!='iios-operational-market-executor-v1'
            or plan.get('schema_version')!='iios-operational-market-request-plan-v1'
            or not isinstance(state.get('authority'),dict) or any(v is not False for v in state['authority'].values())):
        raise ValueError('EXECUTOR_AUTHORITY_INVALID')
    counts=('planned','dispatched','completed','ambiguous','failed','confirmed_credits','ambiguous_credits','keychain_accesses','released_credits')
    if any(type(state.get(k)) is not int or state[k]<0 for k in counts):raise ValueError('ACCOUNTING_INVALID')
    if (state['completed']!=state['confirmed_credits'] or state['ambiguous']!=state['ambiguous_credits']
            or len(state['requests'])!=state['planned'] or len(plan['rows'])!=state['planned']):
        raise ValueError('ACCOUNTING_RECONCILIATION_INVALID')
    return t, authority


def connect_event(t: dict, *, write: bool = False):
    p = Path(t["event_ledger_path"])
    if p.is_symlink(): raise ValueError("EVENT_LEDGER_SYMLINK")
    db = sqlite3.connect(p.as_uri()+('?mode=rwc' if write else '?mode=ro'), uri=True)
    if write: db.execute('PRAGMA synchronous=FULL')
    else: db.execute('PRAGMA query_only=ON')
    return db


def ingest(t: dict) -> dict:
    records = []; universes = []; prior = None
    for spec in t["sources"]:
        if spec["kind"] == "universe":
            u = universe_version(spec, previous=prior); universes.append(u); prior = u["capture_id"]
        elif spec["kind"] in {"operational", "historical"}: records.extend(read_ledger(spec))
        else: records.extend(read_document(spec))
    result = reconcile(records)
    db = connect_event(t, write=True)
    try:
        db.executescript('''CREATE TABLE IF NOT EXISTS identity (id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS universes (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS records_no_update BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
        CREATE TRIGGER IF NOT EXISTS records_no_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;''')
        with db:
            identity = db.execute('SELECT id FROM identity').fetchall()
            if identity and identity != [(t['content_hash'],)]: raise ValueError('EVENT_LEDGER_IDENTITY_INVALID')
            db.execute('INSERT OR IGNORE INTO identity VALUES (?)', (t['content_hash'],))
            for row in records:
                encoded = canonical(row).decode(); existing = db.execute('SELECT payload FROM records WHERE id=?',(row['record_id'],)).fetchone()
                if existing and existing[0] != encoded: raise ValueError('EVENT_ID_COLLISION')
                db.execute('INSERT OR IGNORE INTO records VALUES (?,?)',(row['record_id'],encoded))
            for row in universes:
                existing=db.execute('SELECT payload FROM universes WHERE id=?',(row['capture_id'],)).fetchone()
                if existing and existing[0]!=canonical(row).decode():raise ValueError('UNIVERSE_ID_COLLISION')
                db.execute('INSERT OR IGNORE INTO universes VALUES (?,?)',(row['capture_id'],canonical(row).decode()))
    finally: db.close()
    Path(t['event_ledger_path']).chmod(0o600)
    return result


def snapshot(t: dict, authority: dict, *, now: datetime) -> dict:
    # Re-derive provenance from hash-pinned originals. A re-sealed event-row edit
    # must never upgrade simulation/replay/narrative into verified evidence.
    originals = {}
    for spec in t['sources']:
        if spec['kind'] == 'universe': continue
        rows = read_ledger(spec) if spec['kind'] in {'operational', 'historical'} else read_document(spec)
        for row in rows:
            if row['record_id'] in originals and originals[row['record_id']] != row:
                raise ValueError('SOURCE_ID_COLLISION')
            originals[row['record_id']] = row
    db = connect_event(t)
    try:
        if db.execute('SELECT id FROM identity').fetchall() != [(t['content_hash'],)]:
            raise ValueError('EVENT_LEDGER_IDENTITY_INVALID')
        counts = Counter(); types = Counter(); freshness = {}; classifications = Counter()
        seen = set()
        for raw, in db.execute('SELECT payload FROM records'):
            row = json.loads(raw); verified(row)
            if originals.get(row['record_id']) != row:
                raise ValueError('RECORD_PROVENANCE_MISMATCH')
            seen.add(row['record_id'])
            counts[row['source_store_identity']] += 1; types[row['record_type']] += 1
            freshness.setdefault(row['source_store_identity'],set()).add(row['freshness'])
            classifications[row['classification']]+=1
        if seen != set(originals): raise ValueError('SOURCE_RECORDS_MISSING')
        universes = [json.loads(raw) for raw, in db.execute('SELECT payload FROM universes ORDER BY id')]
        for u in universes: verified(u)
    finally: db.close()
    selected = read_json(Path(t['selected_state']),t['selected_state_hash'])
    spec = next(s for s in t['sources'] if s['kind']=='operational')
    db = sqlite3.connect(Path(spec['path']).as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        row=db.execute("SELECT payload_json FROM ledger_objects WHERE object_type='paper_portfolio_snapshot' ORDER BY created_at DESC LIMIT 1").fetchone()
        paper=json.loads(row[0]) if row else {}
    finally: db.close()
    safe_paper={k:paper.get(k) for k in ('nav','cash','position_count','paper_order_permission','live_execution')}
    if safe_paper['paper_order_permission'] is not False or safe_paper['live_execution'] is not False:
        raise ValueError('PAPER_AUTHORITY_UNVERIFIED')
    accounting={k:selected.get(k) for k in ('planned','dispatched','completed','ambiguous','failed','confirmed_credits','ambiguous_credits','keychain_accesses','released_credits')}
    return seal({'schema':'iios-readonly-projection-v2','topology_identity':t['content_hash'],
                 'identities':t['identities'],'authority':authority['capabilities'],'owners':authority['owners'],
                 'phase':selected['phase'],'published_at':now.isoformat(),
                 'observation_time':selected.get('observed_at'),'event_time':selected.get('updated_at'),
                 'counts_by_source':dict(counts),'record_types':dict(types),
                 'universes':[{k:v for k,v in u.items() if k!='members'} for u in universes],
                 'executor':accounting,'paper':safe_paper,
                 'classification':'HISTORICAL','decision':'NO_PAPER_AUTHORITY','execution':'ABSTAINED',
                 'labels':['LIVE_VERIFIED','REPLAY','HISTORICAL','SIMULATED','NARRATIVE','UNAVAILABLE','STALE'],
                 'retention_context':'RETAINED_READ_ONLY',
                 'live_research_ready':False,'validated_lessons':0,
                 'day_trading':{'chain':list(DAY_CHAIN),'terminal':'NO_PAPER_AUTHORITY'},
                 'source_status':{s['store_id']: {'kind':s['kind'],'states':sorted(freshness.get(s['store_id'],{'UNAVAILABLE'})),
                                                'hash':s['sha256']} for s in t['sources']},
                 'classification_counts':dict(classifications),
                 'activity_scope':'PERSISTED_EXECUTOR_HISTORY_NOT_CANDIDATE_ACTIVITY',
                 'narrative':{'classification':'NARRATIVE','creates_events':False}})


def museum_adapter(p: dict) -> dict:
    verified(p)
    if p.get('schema') != 'iios-readonly-projection-v2' or any(v is not False for v in p['authority'].values()):
        raise ValueError('MUSEUM_PROJECTION_INVALID')
    return {'canonical_url':'http://127.0.0.1:5176/','classification':p['classification'],
            'phase':p['phase'],'event_time':p['event_time'],'observation_time':p['observation_time'],
            'publication_time':p['published_at'],'universe_versions':p['universes'],
            'decision':p['decision'],'execution':p['execution'],'paper':p['paper'],
            'narrative_classification':'NARRATIVE','counts_by_source':p['counts_by_source'],
            'classification_counts':p['classification_counts'],'retention_context':p['retention_context']}
