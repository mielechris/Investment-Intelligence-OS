"""Canonical, non-spending truth contracts. No runtime discovery or I/O on import."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

AUTHORITIES = ("broker", "paper_order", "promotion", "ledger_write", "live_execution")
PHASES = {"SESSION_OPEN", "SESSION_CLOSED", "INSTALLED_DISABLED", "NOT_READY", "UNAVAILABLE"}
CLASSIFICATIONS = {"LIVE_VERIFIED", "DELAYED", "CACHED", "HISTORICAL", "REPLAY", "SIMULATED", "NARRATIVE", "UNAVAILABLE", "FAILED_CLOSED"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def digest(value: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in value.items() if k != "content_hash"})).hexdigest()


def seal(value: dict) -> dict:
    return {**value, "content_hash": digest(value)}


def verified(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("content_hash") != digest(value):
        raise ValueError("CONTENT_HASH_INVALID")
    return value


def utc(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
            raise ValueError
        return result
    except (AttributeError, TypeError, ValueError):
        raise ValueError("UTC_TIMESTAMP_INVALID") from None


def locked(value: dict) -> None:
    if set(value) != set(AUTHORITIES) or any(value[k] is not False for k in AUTHORITIES):
        raise ValueError("AUTHORITY_VIOLATION")


@dataclass(frozen=True)
class Topology:
    schema: str
    mode: str
    source_commit: str
    release_id: str
    release_root: str
    release_manifest_hash: str
    runtime_id: str
    interpreter: str
    interpreter_hash: str
    runtime_manifest: str
    runtime_manifest_hash: str
    ledger_path: str
    ledger_identity: str
    ledger_schema: str
    market_date: str
    session_id: str
    plan_id: str
    generation_id: str
    publisher_id: str
    frontend_identity: str
    providers: tuple[str, ...]
    model_routes: tuple[str, ...]
    authorities: tuple[tuple[str, bool], ...]
    created_at: str
    parent_identity: str
    phase: str

    def record(self) -> dict:
        return seal(json.loads(canonical(asdict(self))))

    @classmethod
    def parse(cls, value: dict) -> Topology:
        verified(value)
        raw = {k: v for k, v in value.items() if k != "content_hash"}
        if set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("TOPOLOGY_SCHEMA_INVALID")
        for k in ("providers", "model_routes"):
            raw[k] = tuple(raw[k])
        raw["authorities"] = tuple(tuple(x) for x in raw["authorities"])
        obj = cls(**raw)
        if obj.schema != "iios-truth-topology-v1" or obj.mode not in {"DEVELOPMENT", "ISOLATED_SHADOW", "PERMANENT_PRODUCTION"}:
            raise ValueError("TOPOLOGY_MODE_INVALID")
        locked(dict(obj.authorities))
        if len(obj.authorities) != len(AUTHORITIES) or obj.ledger_schema != "ledger+truth-v1":
            raise ValueError("TOPOLOGY_SCHEMA_INVALID")
        if obj.providers != ("FINANCIAL_DATASETS:PERSISTED_ONLY",) or obj.model_routes != ("DETERMINISTIC_ACCEPTANCE_ONLY",):
            raise ValueError("REPLAY_PROVIDER_MODEL_CONTRACT_INVALID")
        if obj.phase not in PHASES or not re.fullmatch(r"[0-9a-f]{40}", obj.source_commit):
            raise ValueError("TOPOLOGY_IDENTITY_INVALID")
        for key in ("release_manifest_hash", "interpreter_hash", "runtime_manifest_hash", "ledger_identity", "frontend_identity"):
            if not re.fullmatch(r"[0-9a-f]{64}", getattr(obj, key)):
                raise ValueError("TOPOLOGY_HASH_INVALID")
        for key in ("release_id", "runtime_id", "session_id", "plan_id", "generation_id", "publisher_id", "parent_identity"):
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,180}", getattr(obj, key)):
                raise ValueError("TOPOLOGY_IDENTIFIER_INVALID")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", obj.market_date):
            raise ValueError("MARKET_DATE_INVALID")
        date.fromisoformat(obj.market_date)
        utc(obj.created_at)
        for key in ("release_root", "interpreter", "runtime_manifest", "ledger_path"):
            p = Path(getattr(obj, key))
            if not p.is_absolute() or ".." in p.parts:
                raise ValueError("TOPOLOGY_PATH_INVALID")
        if Path(obj.release_root) in Path(obj.ledger_path).parents:
            raise ValueError("LEDGER_INSIDE_RELEASE")
        return obj


def bind(value: dict, topology: Topology) -> None:
    verified(value)
    for key in ("release_id", "generation_id", "session_id"):
        if value.get(key) != getattr(topology, key):
            raise ValueError("GENERATION_BINDING_INVALID")
    if value.get("topology_identity") != topology.record()["content_hash"]:
        raise ValueError("TOPOLOGY_BINDING_INVALID")


def universe(raw: bytes, expected_hash: str, topology: Topology, *, at: datetime) -> dict:
    """Wrap a reviewed persisted benchmark capture; never fetch or silently call it direct membership."""
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("UNIVERSE_HASH_INVALID")
    x = json.loads(raw)
    if (x.get("schema_version") != "batch9h-benchmark-universe-v1"
            or x.get("source") != "OFFICIAL_SP500_PLUS_NASDAQ100_BENCHMARK_SIDECAR"
            or x.get("verified_complete") is not True or x.get("strict_membership") is not True):
        raise ValueError("UNIVERSE_PROVENANCE_INVALID")
    rows, lineage = x.get("symbols"), x.get("source_lineage")
    if (not isinstance(rows, list) or not rows or len(set(rows)) != len(rows)
            or x.get("symbol_count") != len(rows) or not isinstance(lineage, list) or len(lineage) != 2):
        raise ValueError("UNIVERSE_MEMBERSHIP_INVALID")
    accepted = {("SP500", "SP500_GOVERNED_IVV"), ("NASDAQ100", "NASDAQ100_GOVERNED_IQQ")}
    if {(r.get("index"), r.get("source_id")) for r in lineage} != accepted or any(
        r.get("verified_complete") is not True or r.get("source_mode") != "GOVERNED_INDEX_TRACKER_MIRROR"
        or r.get("trust_source") != "CERTIFI_CA" for r in lineage
    ):
        raise ValueError("UNIVERSE_SOURCE_NOT_REVIEWED")
    stamp = utc(x["official_capture_created_at"])
    age = (at - stamp).total_seconds()
    return seal({"schema": "iios-truth-universe-v1", "source_hash": expected_hash,
                 "generation_id": topology.generation_id, "as_of": stamp.isoformat(),
                 "status": "CURRENT" if 0 <= age <= 36 * 3600 else "STALE",
                 "source_classification": "GOVERNED_INDEX_TRACKER_MIRROR", "direct_membership": False,
                 "eligibility": "CAPTURED_MEMBERS_ONLY_NO_TICKER_SUBSTITUTION",
                 "delisted_policy": "UNKNOWN_REQUIRES_CURRENT_INSTRUMENT_EVIDENCE",
                 "ticker_change_policy": "NO_ALIAS_INFERENCE", "symbols": rows, "lineage": lineage})


def normalize(receipt: dict, raw: bytes, *, topology: Topology, universe_record: dict, storage_policy: str) -> dict:
    verified(receipt); verified(universe_record)
    if universe_record.get("generation_id") != topology.generation_id:
        raise ValueError("UNIVERSE_GENERATION_INVALID")
    if not storage_policy or storage_policy != "FD_REVIEWED_INTERNAL_EVIDENCE_REPLAY_V1":
        raise ValueError("ENTITLEMENT_POLICY_REQUIRED")
    if (receipt.get("schema_version") != "iios-operational-market-evidence-receipt-v1"
            or receipt.get("status") != "CONFIRMED" or receipt.get("credit_cost") != 1
            or receipt.get("endpoint") != "MARKET_SNAPSHOT"
            or hashlib.sha256(raw).hexdigest() != receipt.get("evidence_hash")):
        raise ValueError("RECEIPT_EVIDENCE_INVALID")
    ticker = receipt.get("ticker")
    # Broad index ETFs may be instruments under study without being constituents.
    # This first proof therefore uses MU, an actual captured constituent.
    if ticker not in universe_record["symbols"]:
        raise ValueError("INSTRUMENT_OUTSIDE_GOVERNED_UNIVERSE")
    body = json.loads(raw).get("snapshot", {})
    if body.get("ticker") != ticker:
        raise ValueError("EVIDENCE_INSTRUMENT_INVALID")
    stamp = utc(receipt["observed_at"]); provider_stamp = utc(receipt["provider_timestamp"])
    if utc(body.get("time")) != provider_stamp or stamp.date().isoformat() != topology.market_date:
        raise ValueError("EVIDENCE_TIME_BINDING_INVALID")
    clean = {"ticker": ticker, "provider_timestamp": receipt["provider_timestamp"],
             "freshness": receipt.get("freshness"), "field_count": len(body)}
    if receipt.get("normalized_hash") != digest(clean) or receipt.get("response_bytes") != len(raw):
        raise ValueError("NORMALIZED_RECEIPT_BINDING_INVALID")
    price = body.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        raise ValueError("EVIDENCE_PRICE_INVALID")
    identity = receipt["request_identity"]
    if not re.fullmatch(r"market-evidence-[0-9a-f]{64}", identity):
        raise ValueError("REQUEST_IDENTITY_INVALID")
    trace = "replay-" + hashlib.sha256((topology.record()["content_hash"] + identity).encode()).hexdigest()
    return seal({"schema": "iios-truth-evidence-v1", "evidence_id": identity, "trace_id": trace,
                 "parent_event_ids": [receipt["content_hash"]], "session_id": topology.session_id,
                 "cycle_id": trace, "generation_id": topology.generation_id, "release_id": topology.release_id,
                 "topology_identity": topology.record()["content_hash"], "room_id": "us_large_cap_equities",
                 "instrument_id": ticker, "provider_id": "FINANCIAL_DATASETS", "provider_request_id": identity,
                 "receipt_id": receipt["content_hash"], "raw_evidence_hash": receipt["evidence_hash"],
                 "evidence_type": "PRICE_SNAPSHOT", "observed_at": provider_stamp.isoformat(),
                 "retrieved_at": stamp.isoformat(), "valid_as_of": provider_stamp.isoformat(),
                 "freshness_class": "HISTORICAL", "direct_or_proxy": "DIRECT",
                 "source_reference": "FINANCIAL_DATASETS:/prices/snapshot", "normalized_fact": "Observed price only; not a thesis",
                 "value": price, "unit": "USD", "confidence": None, "conflict_flags": [],
                 "storage_policy": storage_policy, "cost": {"original_confirmed_credits": 1, "replay_credits": 0},
                 "status": "REPLAY"})
