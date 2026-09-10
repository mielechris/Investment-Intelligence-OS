"""Explicit, hash-bound legacy readers. No app/ledger imports and no write connection."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from truth_spine_contract import canonical, digest, seal, utc, verified

ADAPTER_VERSION = "iios-legacy-readonly-v1"
KINDS = {"operational", "historical", "executor", "archive", "research", "event_reconstruction",
         "macro_regime", "patterns", "professional_judgment", "validation_9h", "shadow_9i",
         "outcomes_9j", "universe"}
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
                 "evidence_available": None, "operational_fill": False})


def read_ledger(spec: dict) -> list[dict]:
    path = validate_source(spec)
    if spec["kind"] not in {"operational", "historical"}:
        raise ValueError("LEDGER_ROLE_INVALID")
    # Explicitly pinned snapshot only. WAL-bearing live ledgers require an independently
    # authorized consistent snapshot; immutable=1 must never ignore an active WAL.
    if any(Path(str(path)+suffix).exists() for suffix in ("-wal", "-journal")):
        raise ValueError("CONSISTENT_SNAPSHOT_REQUIRED")
    db = sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("LEDGER_INTEGRITY_INVALID")
        rows = db.execute("""SELECT object_id,object_type,payload_json,created_at FROM ledger_objects
            WHERE object_type IN ('case','evidence_packet','agent_result','committee_decision','risk_authorization',
            'execution','historical_pattern_review','professional_judgment','judgment_entry','outcome_measurement_receipt',
            'jesse_outcome_attribution','paper_portfolio_snapshot') ORDER BY object_id""").fetchall()
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
