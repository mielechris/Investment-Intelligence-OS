from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Callable

from .multi_asset_projection import AUTHORITY, LANES
from .projection_bindings import Binding, SourceArtifact
from .projection_source_registry import SOURCE_ENVELOPE_SCHEMA, content_hash, source_registry

ABSENT_TIMESTAMP = "1970-01-01T00:00:00+00:00"
ABSENT_HASH = hashlib.sha256(b"OPTIONAL_SOURCE_ABSENT").hexdigest()


def _time(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("ADAPTER_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise ValueError("ADAPTER_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _schema(artifact: SourceArtifact, binding: Binding) -> dict[str, Any]:
    value = artifact.value
    if value.get("schema_version") != binding.source_schema:
        raise ValueError("ADAPTER_SOURCE_SCHEMA_INVALID")
    return value


def _telemetry(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding)
    generated = _time(value.get("generated_at"))
    return value, generated, generated


def _factory(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value, generated, effective = _telemetry(artifact, binding)
    health, cadence = value.get("health"), value.get("cadence")
    if not isinstance(health, dict) or not isinstance(cadence, dict):
        raise ValueError("FACTORY_HEALTH_SOURCE_INVALID")
    components = []
    for key in ("observation", "paper_trading", "radar"):
        row = cadence.get(key)
        if not isinstance(row, dict) or not isinstance(row.get("last_completed_at"), str):
            raise ValueError("FACTORY_HEALTH_SOURCE_INVALID")
        components.append({"component": key.upper(), "state": str(row.get("availability") or "UNAVAILABLE"),
                           "last_completed_at": _time(row["last_completed_at"])})
    state = "AVAILABLE" if health.get("state") == "HEALTHY" else "FAILED_CLOSED"
    return {"state": state, "components": components}, generated, effective


def _session(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value, generated, effective = _telemetry(artifact, binding)
    moment = datetime.fromisoformat(generated)
    if moment.weekday() >= 5:
        state, approved = "MARKET_CLOSED_WEEKEND", True
    else:
        state, approved = "UNKNOWN", False
    return {"state": state, "session_date": moment.date().isoformat(), "calendar_approved": approved}, generated, effective


def _radar(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value, generated, _ = _telemetry(artifact, binding)
    radar = value.get("radar")
    if not isinstance(radar, dict) or not isinstance(radar.get("last_cycle_id"), str):
        raise ValueError("RADAR_SOURCE_INVALID")
    effective = _time(radar.get("last_cycle_completed_at"))
    cycle_id = radar["last_cycle_id"]
    failed = "failed_closed" in cycle_id.lower()
    return {"state": "FAILED_CLOSED" if failed else "AVAILABLE",
            "cycle_id": cycle_id, "cycle_complete": not failed,
            "source_artifact_hash": artifact.content_hash}, generated, effective


def _candidate(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = artifact.value
    allowed = {"state", "reason", "source_cycle_id", "source_artifact_hash", "candidate_batch",
               "promotion_candidate_count", "authority"}
    if set(value) != allowed or value.get("state") not in {"CURRENT", "AVAILABLE_EMPTY"} or value.get("authority") != {
            "automatic_promotion":False,"paper_order":False,"ledger_write":False,"broker":False,"live_execution":False}:
        raise ValueError("CANDIDATE_LINEAGE_SOURCE_INVALID")
    batch = value.get("candidate_batch")
    if (not isinstance(batch, dict) or set(batch) != {"schema_version","batch_id","generated_at","originating_scanner","candidates"} or
            batch.get("schema_version") != "iios-sanitized-scanner-batch-v1" or
            batch.get("originating_scanner") != "EXISTING_IIOS_519_SYMBOL_SCANNER" or
            not isinstance(batch.get("candidates"), list) or len(batch["candidates"]) > 5):
        raise ValueError("CANDIDATE_LINEAGE_SOURCE_INVALID")
    candidates=[]
    for row in batch["candidates"]:
        if not isinstance(row,dict) or set(row)!={"candidate_id","ticker","discovered_at","missing_fields"}:
            raise ValueError("CANDIDATE_LINEAGE_SOURCE_INVALID")
        candidates.append({"candidate_id":row["candidate_id"],"instrument_id":row["ticker"],"asset_lane":"us_equities",
            "originating_scanner":"EXISTING_IIOS_519_SYMBOL_SCANNER","discovered_at":row["discovered_at"],
            "source_cycle_id":value["source_cycle_id"],"completeness":"INCOMPLETE" if row["missing_fields"] else "COMPLETE",
            "missing_fields":row["missing_fields"],"verification_state":"PRIMARY_SOURCE_REQUIRED",
            "promotion_state":"BLOCKED","blocked_reason":"PRIMARY_SOURCE_REQUIRED"})
    generated=_time(batch["generated_at"])
    return {"state":"AVAILABLE" if candidates else "AVAILABLE_EMPTY","cycle_id":value["source_cycle_id"],
            "source_artifact_hash":value["source_artifact_hash"],"candidates":candidates},generated,generated


def _benchmark(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding); generated = _time(value.get("generated_at"))
    meta = value.get("benchmark_meta")
    if not isinstance(meta, dict) or not isinstance(value.get("session_id"), str):
        raise ValueError("BENCHMARK_SOURCE_INVALID")
    expected, observed = meta.get("expected_sample_count"), meta.get("sample_count")
    errors = meta.get("provider_error_count")
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in (expected, observed, errors)):
        raise ValueError("BENCHMARK_SOURCE_INVALID")
    return {"state": "AVAILABLE" if value.get("benchmark_complete") is True else "INCOMPLETE",
            "session_date": value["session_id"], "full_session_complete": value.get("benchmark_complete") is True,
            "expected_snapshots": expected, "observed_snapshots": observed,
            "coverage_pct": meta.get("coverage_pct"), "error_count": errors}, generated, generated


def _shadow(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding); generated = _time(value.get("generated_at"))
    if any(value.get(key) is not False for key in ("automatic_threshold_changes", "automatic_weight_changes",
            "judgment_bank_auto_write", "ledger_write", "trade_execution_permission", "broker_connected", "live_execution")):
        raise ValueError("SHADOW_AUTHORITY_INVALID")
    if value.get("observational_only") is not True:
        raise ValueError("SHADOW_AUTHORITY_INVALID")
    return {"state": str(value.get("truth_state") or "UNAVAILABLE"), "source_session": value.get("source_session"),
            "consumed_naturally": bool(value.get("complete_sessions", 0) >= value.get("required_sessions", 5)),
            "observational_only": True}, generated, generated


def _outcomes(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding); generated = _time(value.get("generated_at")); safety = value.get("safety")
    if not isinstance(safety, dict) or safety.get("auto_write_judgment_bank") is not False or any(
            safety.get(key) is not False for key in ("trade_execution_permission", "live_execution")):
        raise ValueError("OUTCOMES_AUTHORITY_INVALID")
    complete = value.get("complete_session_count")
    if not isinstance(complete, int) or isinstance(complete, bool):
        raise ValueError("OUTCOMES_SOURCE_INVALID")
    return {"state": "AVAILABLE" if value.get("status") else "UNAVAILABLE", "source_session": None,
            "advanced": complete > 0}, generated, generated


def _professional(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding)
    allowed = {"schema_version", "generated_at", "effective_at", "observation_count",
               "primary_verification_state", "agreement_state"}
    if set(value) != allowed or not isinstance(value["observation_count"], int):
        raise ValueError("PROFESSIONAL_SOURCE_INVALID")
    return {"state": "AVAILABLE" if value["observation_count"] else "AVAILABLE_EMPTY",
            "observation_count": value["observation_count"],
            "primary_verification_state": value["primary_verification_state"],
            "agreement_state": value["agreement_state"]}, _time(value["generated_at"]), _time(value["effective_at"])


def _lanes(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding)
    if set(value.get("lanes", {})) != LANES:
        raise ValueError("LANE_SOURCE_INVALID")
    return {"state": "AVAILABLE", "session_date": value.get("session_date"), "lanes": value["lanes"]}, \
        _time(value["generated_at"]), _time(value["effective_at"])


def _sleeves(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding)
    count = value.get("sleeve_count")
    if (not isinstance(count, int) or isinstance(count, bool) or count < 0 or
            value.get("operational_position_count") != 0):
        raise ValueError("SLEEVE_SOURCE_INVALID")
    return {"state": "AVAILABLE_EMPTY" if count == 0 else "AVAILABLE", "sleeve_count": count,
            "operational_position_count": value["operational_position_count"]}, _time(value["generated_at"]), _time(value["effective_at"])


def _paper(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value, generated, _ = _telemetry(artifact, binding); fund = value.get("paper_fund")
    if not isinstance(fund, dict): raise ValueError("PAPER_SOURCE_INVALID")
    orders, fills = value.get("recent_paper_orders"), value.get("recent_paper_fills")
    payload = {"state": "AVAILABLE_EMPTY", "nav": fund.get("nav"), "cash": fund.get("cash"),
        "positions": fund.get("position_count"), "transactions": fund.get("transaction_count"),
        "orders": len(orders) if isinstance(orders, list) else None, "fills": len(fills) if isinstance(fills, list) else None}
    if payload != {"state": "AVAILABLE_EMPTY", "nav": 10_000.0, "cash": 10_000.0,
                   "positions": 0, "transactions": 0, "orders": 0, "fills": 0}:
        raise ValueError("PAPER_TRUTH_MISMATCH")
    effective = _time(fund.get("snapshot_as_of"))
    return payload, generated, effective


def _provider(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value = _schema(artifact, binding)
    allowed = {"schema_version", "generated_at", "effective_at", "confirmed_credits", "ambiguous_credits", "remaining_ceiling"}
    if set(value) != allowed: raise ValueError("PROVIDER_SOURCE_INVALID")
    return {"state": "AVAILABLE", "confirmed_credits": value["confirmed_credits"],
            "ambiguous_credits": value["ambiguous_credits"], "remaining_ceiling": value["remaining_ceiling"]}, \
        _time(value["generated_at"]), _time(value["effective_at"])


def _authority(artifact: SourceArtifact, binding: Binding) -> tuple[dict[str, Any], str, str]:
    value, generated, effective = _telemetry(artifact, binding); safety = value.get("safety")
    if not isinstance(safety, dict): raise ValueError("AUTHORITY_SOURCE_INVALID")
    payload = {"provider_contact": False, "credential_access": False, "automatic_promotion": False,
               "paper_order": False, "ledger_write": False, "broker": safety.get("broker_connected"),
               "live_execution": safety.get("live_execution")}
    if payload != AUTHORITY or safety.get("trade_execution_permission") is not False or safety.get("telemetry_read_only") is not True:
        raise ValueError("AUTHORITY_SOURCE_INVALID")
    return payload, generated, effective


ADAPTERS: dict[str, Callable[[SourceArtifact, Binding], tuple[dict[str, Any], str, str]]] = {
    "factory_health": _factory, "market_session": _session, "radar_cycle": _radar,
    "candidate_lineage": _candidate, "benchmark_9h": _benchmark, "shadow_9i": _shadow,
    "outcomes_9j": _outcomes, "professional_research": _professional, "lane_evidence": _lanes,
    "research_sleeves": _sleeves, "paper_fund": _paper, "provider_credit": _provider,
    "authority_locks": _authority,
}


def _absent_payload(name: str) -> dict[str, Any]:
    if name == "candidate_lineage": return {"state":"UNAVAILABLE","cycle_id":None,"source_artifact_hash":None,"candidates":[]}
    if name == "professional_research": return {"state":"UNAVAILABLE","observation_count":None,"primary_verification_state":"UNAVAILABLE","agreement_state":"UNAVAILABLE"}
    if name == "lane_evidence":
        lanes = {lane: {"state":"UNAVAILABLE","freshness":"UNAVAILABLE","candidate_count":None,
            "research_eligible":False,"paper_eligible":False,"missing_evidence":"LICENSED_EVIDENCE_UNAVAILABLE",
            "instrument_basis":"REFERENCE_ONLY" if lane=="crypto_reference" else "EXPLICIT_PROXY" if lane in {"treasury_rates","bond_proxies","commodity_proxies","fx_proxies","relative_value"} else "DIRECT",
            "session_evidence":"UNAVAILABLE","last_trustworthy_timestamp":None} for lane in LANES}
        return {"state":"UNAVAILABLE","session_date":None,"lanes":lanes}
    if name == "research_sleeves": return {"state":"UNAVAILABLE","sleeve_count":None,"operational_position_count":0}
    if name == "provider_credit": return {"state":"UNAVAILABLE","confirmed_credits":None,"ambiguous_credits":None,"remaining_ceiling":None}
    if name == "benchmark_9h": return {"state":"UNAVAILABLE","session_date":None,"full_session_complete":False,"expected_snapshots":None,"observed_snapshots":None,"coverage_pct":None,"error_count":None}
    if name == "shadow_9i": return {"state":"UNAVAILABLE","source_session":None,"consumed_naturally":False,"observational_only":True}
    if name == "outcomes_9j": return {"state":"UNAVAILABLE","source_session":None,"advanced":False}
    raise ValueError("REQUIRED_SOURCE_ABSENT")


def adapt_source(name: str, binding: Binding, artifact: SourceArtifact | None) -> dict[str, Any]:
    if artifact is None:
        if not binding.availability_envelope_allowed:
            raise ValueError("REQUIRED_SOURCE_ABSENT")
        payload, generated, effective, source_hash = _absent_payload(name), ABSENT_TIMESTAMP, ABSENT_TIMESTAMP, ABSENT_HASH
    else:
        payload, generated, effective = ADAPTERS[name](artifact, binding)
        source_hash = artifact.content_hash
    contract = source_registry()[name]
    return {"schema_version": SOURCE_ENVELOPE_SCHEMA, "source_identifier": name,
        "source_schema": contract.source_schema, "artifact_identity": contract.artifact_identity,
        "adapter_identity": binding.adapter_identity, "adapter_version": binding.adapter_version,
        "source_content_hash": source_hash, "generated_at": generated, "effective_at": effective,
        "immutable_hash": content_hash(payload), "payload": payload}
