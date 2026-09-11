"""Explicit, hash-bound legacy readers. No app/ledger imports and no write connection."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import sys
import uuid

from truth_spine_contract import canonical, digest, seal, utc, verified

STRICT_MODE = 'SB38D_STRICT'
LEGACY_MODE = 'LEGACY_UNSCOPED'
_sqlite_policy = ContextVar('sb38d_sqlite_policy', default=None)
_sqlite_permit = ContextVar('sb38d_sqlite_permit', default=None)
_process_policy = None
_audit_installed = False


@dataclass(frozen=True)
class SQLitePolicy:
    root: str
    run_identity: str
    package_identity: str
    process_role: str
    owner_pid: int
    synthetic_root: str | None = None

    def validate(self):
        from truth_spine_lineage import safe_path, require, hex_hash
        root=safe_path(self.root)
        require(hex_hash(self.run_identity) and hex_hash(self.package_identity), 'SQLITE_RUN_IDENTITY_REQUIRED')
        if self.synthetic_root is None:
            require(root.parent==Path('/private/tmp') and root.name.startswith('iios-truth-spine-3-acceptance-sb38d-clean-'),
                    'SQLITE_RUN_ROOT_REQUIRED')
            require(self.process_role in {'preparation','scheduler','publisher','backend','acceptance'}, 'SQLITE_PROCESS_ROLE')
        else:
            test=safe_path(self.synthetic_root)
            require(str(test)==os.environ.get('IIOS_SB38D_TEST_ROOT') and test.parent==Path('/private/tmp') and
                    test.name.startswith('iios-sb38d-source-tests-') and root.is_relative_to(test) and root!=test and
                    self.process_role=='synthetic', 'EXACT_SYNTHETIC_REGISTRATION_REQUIRED')
        require(type(self.owner_pid) is int and self.owner_pid==os.getpid(), 'SQLITE_PROCESS_OWNER')
        for directory in (root,root/'state',root/'working-inputs',root/'admission'):
            if directory.exists():
                info=directory.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and not info.st_mode & 0o022,
                        'SQLITE_DIRECTORY_NOT_OWNED')
        return root


@dataclass(frozen=True)
class SQLiteCapability:
    policy: SQLitePolicy = field(kw_only=True)
    role: str
    path: str
    mode: str
    receipt_path: str
    receipt_hash: str
    parent_package_hash: str | None = None


def active_sqlite_policy():
    return _process_policy or _sqlite_policy.get()


def sqlite_audit(event, args):
    """Audit applies only to this strict process or an explicitly scoped test."""
    if active_sqlite_policy() is not None and event in {'sqlite3.enable_load_extension','sqlite3.load_extension'}:
        raise PermissionError('SQLITE_EXTENSION_FORBIDDEN')
    if event!='sqlite3.connect' or active_sqlite_policy() is None:
        return
    permit=_sqlite_permit.get()
    if permit is None or len(args)!=1 or args[0]!=permit:
        raise PermissionError('UNREGISTERED_SQLITE_CONNECTION')


def install_sqlite_audit():
    global _audit_installed
    if not _audit_installed:
        sys.addaudithook(sqlite_audit)
        _audit_installed=True


@contextmanager
def strict_sqlite_scope(policy):
    if not isinstance(policy,SQLitePolicy): raise ValueError('STRICT_SQLITE_POLICY_REQUIRED')
    policy.validate()
    if _process_policy is not None and _process_policy!=policy:
        raise ValueError('STRICT_SQLITE_POLICY_REPLACEMENT')
    install_sqlite_audit()
    token=_sqlite_policy.set(policy)
    try: yield policy
    finally: _sqlite_policy.reset(token)


def activate_strict_sqlite(policy):
    """Irreversible run scope, including HTTP worker threads; never called by imports."""
    global _process_policy
    policy.validate()
    if _process_policy is not None and _process_policy!=policy:
        raise ValueError('STRICT_SQLITE_POLICY_REPLACEMENT')
    install_sqlite_audit()
    _process_policy=policy


def validate_sqlite_capability(capability):
    from truth_spine_lineage import safe_path, contained, regular, file_hash, require, hex_hash, OWNER_ROOT
    require(type(capability) is SQLiteCapability,'STRICT_SQLITE_CAPABILITY_REQUIRED')
    policy=capability.policy
    require(type(policy) is SQLitePolicy,'STRICT_SQLITE_POLICY_REQUIRED')
    ambient=active_sqlite_policy()
    require(ambient is None or ambient==policy,'STRICT_SQLITE_POLICY_MISMATCH')
    root=policy.validate()
    # Reject protected names before any filesystem operation on the target.
    raw=Path(capability.path)
    require(not raw.is_relative_to(OWNER_ROOT) and 'Application Support' not in raw.parts and
            not any(p.startswith('iios-northstar-owner-snapshots-') for p in raw.parts), 'PROTECTED_SQLITE_PATH')
    path=safe_path(raw)
    role=capability.role
    require(role in {'L7_WORKING_COPY','L8_WORKING_COPY','RUN_EVENT_STORE'},'SQLITE_ROLE_INVALID')
    subtree=root/('state' if role=='RUN_EVENT_STORE' else 'working-inputs')
    require(path!=subtree and path.is_relative_to(subtree),'SQLITE_SUBTREE_MISMATCH')
    receipt=safe_path(capability.receipt_path)
    require(receipt.is_relative_to(root/'admission') and receipt!=root/'admission' and
            hex_hash(capability.receipt_hash),'SQLITE_RECEIPT_REQUIRED')
    require(file_hash(receipt)==capability.receipt_hash,'SQLITE_RECEIPT_PIN_MISMATCH')
    document=json.loads(receipt.read_bytes());verified(document)
    require(document['root']==str(root) and document['run_identity']==policy.run_identity and
            document['package_identity']==policy.package_identity,'SQLITE_PARENT_IDENTITY_MISMATCH')
    rows=document['databases']
    require(isinstance(rows,list) and len({r['path'] for r in rows})==len(rows),'SQLITE_MEMBERSHIP_INVALID')
    matches=[r for r in rows if r['path']==str(path)]
    require(len(matches)==1,'UNREGISTERED_WORKING_DATABASE')
    row=matches[0]
    require(row['role']==role,'SQLITE_ROLE_MISMATCH')
    info=regular(path)
    require(info.st_nlink==1 and info.st_dev==row['device'] and info.st_ino==row['inode'], 'SQLITE_INODE_MISMATCH')
    if role=='RUN_EVENT_STORE':
        require(document['schema']=='iios-run-state-creation-v1' and row['creation']=='EXCLUSIVE_EMPTY_FILE' and
                capability.mode in {'ro','rw'} and hex_hash(capability.parent_package_hash) and
                document['parent_package_hash']==capability.parent_package_hash, 'EVENT_CREATION_RECEIPT_REQUIRED')
        if capability.mode=='rw':
            require(policy.process_role in {'scheduler','synthetic'},'EVENT_WRITER_NOT_OWNED')
        for suffix in ('-wal','-shm','-journal'):
            side=contained(root,'state/'+path.relative_to(root/'state').as_posix()+suffix)
            if side.exists():
                require(regular(side).st_nlink==1,'EVENT_SIDECAR_ALIAS')
    else:
        require(document['schema']=='iios-working-sqlite-admission-v1' and capability.mode=='ro-immutable' and
                row['creation']=='VERIFIED_BYTE_COPY' and hex_hash(row['source_hash']) and
                row['source_hash']==row['copied_hash']==row['source_after_hash'] and
                file_hash(path)==row['copied_hash'],'WORKING_SQLITE_PIN_MISMATCH')
    return path


_CONNECTION_PROOF=object()


class StrictConnection:
    def __init__(self, native, capability, receipt, proof):
        if proof is not _CONNECTION_PROOF:raise ValueError('STRICT_CONNECTION_PROOF_REQUIRED')
        self.__native=native
        self.capability=capability
        self.telemetry=receipt
        self.__proof=proof
    def execute(self, *args):return self.__native.execute(*args)
    def executescript(self, *args):return self.__native.executescript(*args)
    def commit(self):return self.__native.commit()
    def rollback(self):return self.__native.rollback()
    def close(self):return self.__native.close()
    def __enter__(self):self.__native.__enter__();return self
    def __exit__(self,*args):return self.__native.__exit__(*args)
    def verified_for(self,capability):
        return self.__proof is _CONNECTION_PROOF and self.capability==capability


def verify_strict_connection(connection, capability):
    validate_sqlite_capability(capability)
    if type(connection) is not StrictConnection or not connection.verified_for(capability):
        raise ValueError('STRICT_CONNECTION_RESULT_REQUIRED')
    from truth_spine_lineage import file_hash
    if file_hash(connection.telemetry['path'])!=connection.telemetry['sha256']:
        raise ValueError('SQLITE_TELEMETRY_CHANGED')
    return connection


def strict_target(capability):
    path=validate_sqlite_capability(capability)
    return {'path':str(path),'role':capability.role,'receipt_hash':capability.receipt_hash,
            'run_identity':capability.policy.run_identity,'package_identity':capability.policy.package_identity}


def verify_sqlite_targets(capabilities, telemetry):
    """Caller supplies the complete independently expected capability membership."""
    expected={canonical(strict_target(c)) for c in capabilities}
    actual=set()
    from truth_spine_lineage import file_hash
    for link in telemetry:
        if file_hash(link['path'])!=link['sha256']:raise ValueError('SQLITE_TELEMETRY_CHANGED')
        doc=json.loads(Path(link['path']).read_bytes());verified(doc)
        if doc['schema']!='iios-strict-sqlite-open-v1':raise ValueError('SQLITE_TELEMETRY_SCHEMA')
        actual.add(canonical(doc['target']))
    if actual!=expected:raise ValueError('SQLITE_TARGET_SET_MISMATCH')
    return True


def connect_strict_sqlite(capability):
    path=validate_sqlite_capability(capability)
    query='?mode=ro&immutable=1' if capability.mode=='ro-immutable' else '?mode='+capability.mode
    uri=path.as_uri()+query
    token=_sqlite_permit.set(uri)
    try: db=sqlite3.connect(uri,uri=True)
    finally: _sqlite_permit.reset(token)
    try:
        validate_sqlite_capability(capability)
        if db.execute('PRAGMA database_list').fetchall()!=[(0,'main',str(path))]:
            raise ValueError('SQLITE_NATIVE_TARGET_MISMATCH')
        db.execute('PRAGMA query_only='+('OFF' if capability.mode=='rw' else 'ON'))
        db.execute('PRAGMA temp_store=MEMORY')
        if capability.mode=='rw': db.execute('PRAGMA journal_mode=PERSIST')
        # ATTACH would open a second database without a connect audit event.
        def authorize(action, _arg1, _arg2, _database, _trigger):
            forbidden=action in {sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH} or (
                action==sqlite3.SQLITE_PRAGMA and str(_arg1).lower() in {'temp_store_directory','data_store_directory','temp_store'})
            return sqlite3.SQLITE_DENY if forbidden else sqlite3.SQLITE_OK
        db.set_authorizer(authorize)
    except BaseException:
        db.close();raise
    from truth_spine_lineage import write_new
    target=strict_target(capability)
    relative='admission/sqlite-open-'+uuid.uuid4().hex+'.json'
    try:
        h=write_new(Path(capability.policy.root),relative,canonical(seal({
            'schema':'iios-strict-sqlite-open-v1','target':target,'mode':capability.mode,
            'device':path.stat().st_dev,'inode':path.stat().st_ino})))
    except BaseException:
        db.close();raise
    return StrictConnection(db,capability,{'path':str(Path(capability.policy.root)/relative),'sha256':h},_CONNECTION_PROOF)


def create_run_event_store(policy, parent_package_hash, relative='state/canonical-events.db'):
    """Exclusive byte creation precedes any SQLite open; no copy or replacement."""
    from truth_spine_lineage import contained, regular, require, write_new, hex_hash
    require(hex_hash(parent_package_hash),'EVENT_PARENT_PACKAGE_REQUIRED')
    root=policy.validate();path=contained(root,relative)
    require(path.is_relative_to(root/'state') and path!=root/'state','EVENT_STATE_SUBTREE_REQUIRED')
    require(not any(Path(str(path)+s).exists() for s in ('','-wal','-shm','-journal')),'EVENT_STORE_ALREADY_EXISTS')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try: os.fsync(fd)
    finally: os.close(fd)
    info=regular(path)
    row={'role':'RUN_EVENT_STORE','path':str(path),'device':info.st_dev,'inode':info.st_ino,'creation':'EXCLUSIVE_EMPTY_FILE'}
    doc=seal({'schema':'iios-run-state-creation-v1','root':str(root),'run_identity':policy.run_identity,
              'package_identity':policy.package_identity,'parent_package_hash':parent_package_hash,'databases':[row]})
    receipt='admission/event-state-creation.json'
    expected=write_new(root,receipt,canonical(doc))
    return SQLiteCapability('RUN_EVENT_STORE',str(path),'rw',str(root/receipt),expected,parent_package_hash,policy=policy)

ADAPTER_VERSION = "iios-legacy-readonly-v1"
KINDS = {"operational", "historical", "executor", "archive", "research", "event_reconstruction",
         "macro_regime", "patterns", "professional_judgment", "validation_9h", "shadow_9i",
         "outcomes_9j", "universe", "price_archive"}
MEMORY_TYPES = {"professional_judgment": "PROFESSIONAL_JUDGMENT", "historical_pattern_review": "REVIEW_CANDIDATE",
                "judgment_bank_review_queue": "REVIEW_CANDIDATE", "outcome_measurement_receipt": "MEASURED_OUTCOME",
                "shadow_strategy": "COUNTERFACTUAL", "narrative": "NARRATIVE"}
EVIDENCE_CLASSIFICATIONS = frozenset({"REPLAY", "HISTORICAL", "SIMULATED", "NARRATIVE",
    "LIVE_VERIFIED", "UNAVAILABLE", "STALE", "FAILED_CLOSED", "DELAYED", "CACHED"})
EXECUTOR_SESSION_SCHEMAS = frozenset({'iios-operational-market-executor-v1',
                                    'iios-operational-market-request-plan-v1'})
SESSION_CLASSIFICATIONS = frozenset({'FULL_SESSION_50', 'PARTIAL_SESSION_LATE_START',
    'SPY_SNAPSHOT_CANARY_1', 'POST_0930_PARTIAL_SESSION', 'SEPTEMBER_9_MARKET_OPEN_50',
    'SEPTEMBER_9_INTRADAY_RECOVERY'})


def session_classification(data: dict, kind: str) -> str | None:
    """Executor/session archives use classification for plan type, not evidence."""
    schema = data.get('schema_version', data.get('schema'))
    if not ((kind == 'executor' and schema in EXECUTOR_SESSION_SCHEMAS)
            or (kind == 'archive' and schema == 'iios-operational-market-session-archive-v1')):
        return None
    value = data.get('classification')
    if not isinstance(value, str) or value not in SESSION_CLASSIFICATIONS:
        raise ValueError('SESSION_CLASSIFICATION_INVALID')
    return value


def evidence_classification(data: dict, kind: str, object_type: str) -> tuple[str, str]:
    """Provenance is not age. Missing provenance is unavailable, never historical."""
    session = session_classification(data, kind)
    keys = ('evidence_classification',) if session is not None else ('evidence_classification', 'classification')
    declared = [data[k] for k in keys if k in data]
    if any(not isinstance(v, str) or v not in EVIDENCE_CLASSIFICATIONS for v in declared):
        raise ValueError('EVIDENCE_CLASSIFICATION_INVALID')
    if len(set(declared)) > 1:
        raise ValueError('EVIDENCE_CLASSIFICATION_CONFLICT')
    constrained = 'SIMULATED' if kind == 'shadow_9i' else 'NARRATIVE' if object_type == 'narrative' else None
    if constrained and declared and declared[0] != constrained:
        raise ValueError('EVIDENCE_CLASSIFICATION_UPGRADE')
    return (declared[0] if declared else constrained or 'UNAVAILABLE',
            'SOURCE_DECLARED' if declared else 'SOURCE_TYPE_BOUND' if constrained else 'MISSING_CLASSIFICATION')


def file_bytes(path: Path, expected_hash: str | None = None) -> bytes:
    if not path.is_absolute() or ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("SOURCE_PATH_INVALID")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("SOURCE_FILE_INVALID")
    data = path.read_bytes()
    if expected_hash is not None and hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("SOURCE_HASH_MISMATCH")
    return data


def validate_source(source: dict) -> Path:
    verified(source)
    if (set(source) != {"schema", "store_id", "kind", "path", "sha256", "content_hash"}
            or source["schema"] != "iios-readonly-source-v1" or source["kind"] not in KINDS
            or not source["store_id"] or source["store_id"] != source["kind"]+":"+source["sha256"]):
        raise ValueError("SOURCE_BINDING_INVALID")
    p = Path(source["path"])
    file_bytes(p, source["sha256"])
    return p


def source(path: Path, kind: str) -> dict:
    h = hashlib.sha256(file_bytes(path)).hexdigest()
    return seal({"schema": "iios-readonly-source-v1", "store_id": kind+":"+h,
                 "kind": kind, "path": str(path), "sha256": h})


def coverage_metadata(data: dict, record_type: str) -> dict:
    """Allowlisted explicit references only; never infer agents/rooms from totals."""
    def identity(keys):
        supplied = [data[k] for k in keys if data.get(k) is not None]
        if any(not isinstance(v, str) or not re.fullmatch(r"[a-z0-9_]{1,80}", v) for v in supplied):
            return None
        if len(set(supplied)) > 1:
            raise ValueError("COVERAGE_IDENTITY_CONFLICT")
        return supplied[0] if supplied else None
    def money(key):
        value = data.get(key)
        if value is None or isinstance(value, bool):
            return None
        try:
            number = Decimal(str(value))
            return format(number, 'f') if number.is_finite() and 0 <= number <= Decimal('1e15') else None
        except (InvalidOperation, ValueError):
            return None
    positions = data.get("position_count")
    return {"product_id": identity(("product_id", "room_id")),
            "agent_id": identity(("agent_key", "agent_id")),
            "result_state": data.get("status") if data.get("status") in
                {"complete", "failed", "failed_closed", "suppressed", "idle", "invoked"} else None,
            "paper": {"nav": money("nav"), "cash": money("cash"),
                      "positions": positions if type(positions) is int and positions >= 0 else None}
                if record_type == "paper_portfolio_snapshot" else None}


def normalize_record(spec: dict, object_id: str, object_type: str, raw: bytes,
                     original_timestamp: str | None) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict) or not object_id:
        raise ValueError("LEGACY_RECORD_INVALID")
    classification, classification_basis = evidence_classification(data, spec['kind'], object_type)
    original_state=data.get('freshness',data.get('state',data.get('status')))
    freshness=original_state if original_state in {'STALE','UNAVAILABLE','FAILED_CLOSED'} else 'HISTORICAL'
    if classification in {'STALE', 'UNAVAILABLE', 'FAILED_CLOSED'}:
        freshness = classification
    # Original text stays in the owner-only source. Only references cross this boundary.
    return seal({"schema": "iios-adapted-record-v1", "adapter_version": ADAPTER_VERSION,
                 "source_store_identity": spec["store_id"], "source_object_identity": object_id,
                 "record_id": digest({"store": spec["store_id"], "object": object_id}),
                 "original_content_hash": hashlib.sha256(raw).hexdigest(),
                 "original_timestamp": original_timestamp,
                 "source_schema": data.get("schema_version", data.get("schema", "legacy:"+object_type)),
                 "record_type": object_type, "classification": classification,
                 "evidence_classification": classification, "classification_basis": classification_basis,
                 "record_origin": spec['kind'], "retention_context": 'RETAINED_READ_ONLY',
                 "session_classification": session_classification(data, spec['kind']),
                 "freshness": freshness,
                 "memory_class": MEMORY_TYPES.get(object_type, "HISTORICAL_RECORD"),
                 "observation_time": data.get("observed_at", data.get("provider_timestamp")),
                 "event_time": data.get("created_at", original_timestamp),
                 "publication_time": data.get("generated_at"),
                 "provenance_reference": {"source_file_hash": spec["sha256"],
                                          "source_payload_hash": hashlib.sha256(raw).hexdigest()},
                 "coverage": coverage_metadata(data, object_type),
                 "evidence_available": None, "operational_fill": False})


def read_ledger(spec: dict, *, mode=LEGACY_MODE, capability=None) -> list[dict]:
    """Legacy API. Never accepts a strict request or selects strict dispatch."""
    if active_sqlite_policy() is not None or any(
            p.startswith('iios-truth-spine-3-acceptance-sb38d-clean-') for p in Path(spec.get('path','')).parts):
        raise PermissionError('LEGACY_SQLITE_UNREACHABLE_IN_STRICT_RUN')
    if mode!=LEGACY_MODE or capability is not None:raise ValueError('EXPLICIT_LEGACY_MODE_REQUIRED')
    path=validate_source(spec)
    if any(Path(str(path)+suffix).exists() for suffix in ('-wal','-journal')):
        raise ValueError('CONSISTENT_SNAPSHOT_REQUIRED')
    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
    return _ledger_records(spec,db)


def read_strict_ledger(spec: dict, capability: SQLiteCapability) -> list[dict]:
    path=validate_sqlite_capability(capability)
    role={'operational':'L7_WORKING_COPY','historical':'L8_WORKING_COPY'}.get(spec.get('kind'))
    if capability.role!=role or str(path)!=spec.get('path'):
        raise ValueError('STRICT_LEDGER_ROLE_OR_PATH_MISMATCH')
    validate_source(spec)
    db=connect_strict_sqlite(capability)
    verify_strict_connection(db,capability)
    return _ledger_records(spec,db)


def _ledger_records(spec, db):
    path = validate_source(spec)
    if spec["kind"] not in {"operational", "historical"}:
        raise ValueError("LEDGER_ROLE_INVALID")
    # Explicitly pinned snapshot only. WAL-bearing live ledgers require an independently
    # authorized consistent snapshot; immutable=1 must never ignore an active WAL.
    if any(Path(str(path)+suffix).exists() for suffix in ("-wal", "-journal")):
        raise ValueError("CONSISTENT_SNAPSHOT_REQUIRED")
    try:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("LEDGER_INTEGRITY_INVALID")
        rows = db.execute("""SELECT object_id,object_type,payload_json,created_at FROM ledger_objects
            WHERE object_type IN ('case','evidence_packet','agent_result','committee_decision','risk_authorization',
            'execution','historical_pattern_review','professional_judgment','judgment_entry','outcome_measurement_receipt',
            'jesse_outcome_attribution','paper_portfolio_snapshot','opportunity_candidate') ORDER BY object_id""").fetchall()
        if not rows: raise ValueError("EMPTY_LEDGER_NOT_OPERATIONAL_TRUTH")
        result = [normalize_record(spec, oid, kind, raw.encode(), stamp) for oid, kind, raw, stamp in rows]
    finally:
        db.close()
    file_bytes(path, spec["sha256"])
    return result


def read_document(spec: dict) -> list[dict]:
    p = validate_source(spec); raw = file_bytes(p, spec["sha256"]); x = json.loads(raw)
    if not isinstance(x, dict): raise ValueError("SOURCE_SCHEMA_INVALID")
    if 'content_hash' in x: verified(x)
    if x.get('schema_version') == 'iios-operational-market-evidence-receipt-v1':
        evidence=p.parent.parent/'evidence'/p.name
        file_bytes(evidence,x['evidence_hash'])
    if spec['kind']=='archive':
        for row in x.get('files',[]):
            relative=Path(row['path'])
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('ARCHIVE_PATH_INVALID')
            if len(file_bytes(p.parent/relative,row['sha256']))!=row['bytes']:raise ValueError('ARCHIVE_SIZE_INVALID')
    if spec["kind"] == "shadow_9i":
        if x.get("schema_version") != "batch9i-browser-shadow-strategy-v1":
            raise ValueError("PRIVATE_9I_PROJECTION_REJECTED")
    schema = x.get("schema_version", x.get("schema"))
    if not isinstance(schema, str) or not schema: raise ValueError("SOURCE_SCHEMA_MISSING")
    # Even an approved summary is represented by metadata, never copied into public output.
    return [normalize_record(spec, spec["sha256"], spec["kind"], raw,
                             x.get("created_at", x.get("generated_at")))]


def reconcile(records: list[dict]) -> dict:
    seen = {}; bare = {}
    for row in records:
        verified(row)
        expected = digest({"store": row["source_store_identity"], "object": row["source_object_identity"]})
        if row["record_id"] != expected: raise ValueError("NAMESPACE_BINDING_INVALID")
        if expected in seen and seen[expected] != row["content_hash"]:
            raise ValueError("SOURCE_ID_COLLISION")
        seen[expected] = row["content_hash"]
        bare.setdefault(row["source_object_identity"], set()).add(row["source_store_identity"])
    return {"records": len(seen), "cross_store_ids_preserved": sum(len(v)>1 for v in bare.values()),
            "merged_by_bare_id": False}


def universe_version(spec: dict, *, previous: str | None = None) -> dict:
    p = validate_source(spec); x = json.loads(file_bytes(p, spec["sha256"]))
    rows = x.get("symbols"); lineage = x.get("source_lineage")
    if (not isinstance(rows, list) or not rows or any(not isinstance(s, str) or not s for s in rows)
            or len(set(rows)) != len(rows) or x.get("symbol_count") != len(rows)
            or x.get("verified_complete") is not True or not isinstance(lineage, list) or not lineage
            or any(r.get('verified_complete') is not True or r.get('source_mode') not in {'GOVERNED_INDEX_TRACKER_MIRROR','OFFICIAL_WEB_SOURCE'} for r in lineage)):
        raise ValueError("UNIVERSE_CAPTURE_INVALID")
    stamp = x.get("official_capture_created_at", x.get("created_at")); utc(stamp)
    modes = sorted({r["source_mode"] for r in lineage})
    return seal({"schema": "iios-universe-version-v1", "capture_id": spec["sha256"],
                 "member_hash": hashlib.sha256(canonical(sorted(rows))).hexdigest(),
                 "count": len(rows), "members": sorted(rows), "capture_time": stamp,
                 "source_classes": modes, "provenance_hash": digest({"lineage": lineage}),
                 "direct_official_membership": False, "previous_capture": previous})


@dataclass(frozen=True)
class MemoryTrustAnchor:
    """Bootstrap-only pins, never populated from a proposed lesson or browser input.

    The registry must already exist as an independently reviewed immutable input.
    This module has no registry builder, admission writer or operational route.
    An unconfigured deployment cannot admit memory. Reopening validates all pins.
    """
    registry_path: Path
    registry_sha256: str
    topology_identity: str
    authority_identity: str
    admission_policy_version: str

    def resolve(self, admission_id: str) -> dict[str, dict]:
        import re
        pins = (self.registry_sha256, self.topology_identity, self.authority_identity)
        if (any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in pins)
                or not self.admission_policy_version or not isinstance(admission_id, str)):
            raise ValueError('INSUFFICIENT_PROVENANCE')
        parent = self.registry_path.parent
        if parent.is_symlink() or parent.stat().st_uid != os.getuid() or stat.S_IMODE(parent.stat().st_mode) != 0o700:
            raise ValueError('INSUFFICIENT_PROVENANCE')

        def read(path: Path, expected: str) -> bytes:
            data = file_bytes(path, expected)
            if stat.S_IMODE(path.stat().st_mode) not in {0o400, 0o600}:
                raise ValueError('INSUFFICIENT_PROVENANCE')
            return data

        registry = json.loads(read(self.registry_path, self.registry_sha256))
        verified(registry)
        if (set(registry) != {'schema', 'topology_identity', 'authority_identity',
                'admission_policy_version', 'entries', 'content_hash'}
                or registry['schema'] != 'iios-memory-source-registry-v1'
                or registry['topology_identity'] != self.topology_identity
                or registry['authority_identity'] != self.authority_identity
                or registry['admission_policy_version'] != self.admission_policy_version
                or not isinstance(registry['entries'], dict)):
            raise ValueError('INSUFFICIENT_PROVENANCE')
        entry = registry['entries'].get(admission_id)
        kinds = {'record', 'case', 'evidence', 'decision', 'committee', 'risk',
                 'measurement', 'outcome', 'admission'}
        if not isinstance(entry, dict) or set(entry) != kinds | {'raw_evidence'}:
            raise ValueError('INSUFFICIENT_PROVENANCE')
        resolved = {}
        paths = set()
        for kind, ref in entry.items():
            if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
                raise ValueError('INSUFFICIENT_PROVENANCE')
            relative = Path(ref['path'])
            if relative.is_absolute() or '..' in relative.parts or str(relative) in paths:
                raise ValueError('INSUFFICIENT_PROVENANCE')
            paths.add(str(relative))
            raw = read(self.registry_path.parent / relative, ref['sha256'])
            if kind == 'raw_evidence':
                raw_hash = hashlib.sha256(raw).hexdigest()
            else:
                resolved[kind] = json.loads(raw)
                verified(resolved[kind])
        common = ('source_store_identity', 'source_object_identity', 'case_id', 'generation', 'ticker',
                  'topology_identity', 'authority_identity', 'evidence_classification')
        case = resolved['case']
        if (any(not isinstance(case.get(k), str) or not case[k] for k in common)
                or case['case_id'] != digest({'store': case['source_store_identity'],
                                              'object': case['source_object_identity']})
                or case['topology_identity'] != self.topology_identity
                or case['authority_identity'] != self.authority_identity
                or case['evidence_classification'] not in {'HISTORICAL', 'LIVE_VERIFIED'}
                or any(any(item.get(k) != case[k] for k in common) for item in resolved.values())):
            raise ValueError('INSUFFICIENT_PROVENANCE')
        for kind, item in resolved.items():
            if item.get('schema') != f'iios-memory-{kind}-v1' or not isinstance(item.get('identity'), str) or not item['identity']:
                raise ValueError('INSUFFICIENT_PROVENANCE')
        if len({item['identity'] for item in resolved.values()}) != len(resolved):
            raise ValueError('INSUFFICIENT_PROVENANCE')
        evidence, decision, outcome, admission = (resolved[k] for k in ('evidence', 'decision', 'outcome', 'admission'))
        measurement = resolved['measurement']
        if (evidence.get('original_evidence_hash') != raw_hash
                or not evidence.get('receipt_identity')
                or not isinstance(measurement.get('definition'), str) or not measurement['definition']
                or not isinstance(measurement.get('horizon'), str) or not measurement['horizon']
                or outcome.get('classification') != 'MEASURED'
                or outcome.get('measurement_horizon') != measurement['horizon']
                or not outcome.get('receipt_identity')
                or admission.get('identity') != admission_id
                or admission.get('decision') != 'ADMIT' or admission.get('human_validated') is not True
                or admission.get('admission_policy_version') != self.admission_policy_version
                or resolved['record'].get('memory_class') != 'VALIDATED_LESSON'):
            raise ValueError('INSUFFICIENT_PROVENANCE')
        # Every material relationship is independently pinned, not just a child hash.
        links = {'decision': ('evidence', 'committee', 'risk'),
                 'outcome': ('evidence', 'decision', 'measurement'),
                 'admission': ('case', 'evidence', 'decision', 'committee', 'risk', 'measurement', 'outcome'),
                 'record': ('evidence', 'decision', 'outcome', 'admission')}
        for kind, targets in links.items():
            for target in targets:
                if (resolved[kind].get(target+'_hash') != resolved[target]['content_hash']
                        or resolved[kind].get(target+'_identity') != resolved[target]['identity']):
                    raise ValueError('INSUFFICIENT_PROVENANCE')
        read(self.registry_path, self.registry_sha256)
        return resolved


def admit_lesson(record: dict, *, case: dict, evidence: dict, decision: dict,
                 outcome: dict, admission: dict, trusted: MemoryTrustAnchor | None = None) -> dict:
    """Read-only eligibility verification. No admission side effects, even on success.

    Concurrent calls and restart cannot create duplicates or partially admitted rows:
    this function writes nothing. Persisting validated memory remains unauthorized.
    """
    if not isinstance(trusted, MemoryTrustAnchor):
        raise ValueError('INSUFFICIENT_PROVENANCE')
    try:
        originals = trusted.resolve(admission.get('identity'))
        submitted = dict(record=record, case=case, evidence=evidence, decision=decision,
                         outcome=outcome, admission=admission)
        for kind, item in submitted.items():
            verified(item)
            if canonical(item) != canonical(originals[kind]):
                raise ValueError('INSUFFICIENT_PROVENANCE')
    except (OSError, KeyError, TypeError, AttributeError, ValueError):
        raise ValueError('INSUFFICIENT_PROVENANCE') from None
    return json.loads(canonical(originals['record']))
