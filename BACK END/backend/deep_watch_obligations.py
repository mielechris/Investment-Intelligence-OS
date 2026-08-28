from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from evidence_engine import build_packet
from ledger import get_object, latest_object, record_event, record_object
from primary_evidence_contracts import contract_for_requirement


router = APIRouter()

OBJECT_TYPE = "deep_watch_obligation_set"
REUNDERWRITE_TYPE = "deep_watch_reunderwrite"
PRIMARY_CAPTURE_MINUTES = 240
CONTEXT_MIN_QUALITY = 0.75
CONTEXT_MIN_TOKEN_HITS = 3

_primary_module: Any | None = None

_STOPWORDS = {
    "about", "after", "against", "along", "also", "and", "are", "around",
    "before", "current", "data", "determine", "evidence", "for", "from", "fresh",
    "including", "into", "latest", "market", "more", "that", "the", "their", "this",
    "through", "under", "using", "with", "would",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _key(requirement: str) -> str:
    return hashlib.sha1(_norm(requirement).encode("utf-8")).hexdigest()[:16]


def _tokens(requirement: str) -> set[str]:
    tokens = {
        token.strip(".,:;()[]{}+-/\"")
        for token in _norm(requirement).split()
    }
    return {
        token
        for token in tokens
        if len(token) >= 4 and token not in _STOPWORDS
    }


def _is_portfolio_requirement(requirement: str) -> bool:
    text = _norm(requirement)
    terms = (
        "portfolio holdings", "portfolio overlap", "factor exposure", "factor exposures",
        "correlation", "risk-budget", "risk budget", "marginal diversification",
        "position sizing",
    )
    return any(term in text for term in terms)


def classify_requirement(requirement: str) -> dict[str, Any]:
    lane, contract = contract_for_requirement(requirement)
    if lane and contract:
        return {
            "kind": "PRIMARY_EVIDENCE",
            "lane": lane,
            "lane_label": contract.get("label"),
        }
    if _is_portfolio_requirement(requirement):
        return {
            "kind": "PORTFOLIO_CONTEXT",
            "lane": "portfolio_context",
            "lane_label": "Portfolio Context",
        }
    return {
        "kind": "CONTEXT_EVIDENCE",
        "lane": None,
        "lane_label": "Context Evidence",
    }


def _requirements(case_id: str) -> tuple[dict[str, Any], list[str]]:
    decision = latest_object("committee_decision", case_id=case_id) or {}
    requirements = [
        str(item).strip()
        for item in decision.get("required_evidence") or []
        if str(item).strip()
    ]
    return decision, requirements


def _raw_item(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("raw")
    return raw if isinstance(raw, dict) else item


def _monitor_items(case_id: str) -> list[dict[str, Any]]:
    snapshot = latest_object("monitor_snapshot", case_id=case_id) or {}
    packet = snapshot.get("evidence_packet") if isinstance(snapshot.get("evidence_packet"), dict) else {}
    return [
        item
        for item in packet.get("items") or []
        if isinstance(item, dict)
    ]


def _primary_lane_snapshot(primary_module: Any, case_id: str, lane: str) -> dict[str, Any]:
    status = primary_module.primary_evidence_status(case_id)
    row = (status.get("lanes") or {}).get(lane) or {}
    facts = row.get("facts") if isinstance(row.get("facts"), list) else []
    covered = sorted(
        str(fact.get("key"))
        for fact in facts
        if isinstance(fact, dict) and fact.get("covered") is True
    )
    missing = sorted(
        str(fact.get("key"))
        for fact in facts
        if isinstance(fact, dict) and fact.get("covered") is not True
    )
    latest_ids = sorted(
        str(record.get("primary_evidence_id"))
        for record in row.get("latest_records") or []
        if isinstance(record, dict) and record.get("primary_evidence_id")
    )
    return {
        "kind": "PRIMARY_EVIDENCE",
        "lane": lane,
        "status": row.get("status") or "OPEN",
        "coverage_pct": int(row.get("coverage_pct") or 0),
        "covered_fact_keys": covered,
        "missing_fact_keys": missing,
        "current_high_quality_records": int(row.get("current_high_quality_records") or 0),
        "source_count": int(row.get("source_count") or 0),
        "latest_record_ids": latest_ids,
    }


def _portfolio_snapshot(case_id: str) -> dict[str, Any]:
    snapshot = latest_object("portfolio_snapshot", case_id=case_id) or {}
    overlap = snapshot.get("overlap") if isinstance(snapshot.get("overlap"), dict) else {}
    return {
        "kind": "PORTFOLIO_CONTEXT",
        "status": "CURRENT" if snapshot else "MISSING",
        "portfolio_snapshot_id": snapshot.get("portfolio_snapshot_id"),
        "as_of": snapshot.get("as_of"),
        "combined_overlap_weight_pct": _safe_float(overlap.get("combined_overlap_weight_pct")),
        "concentration_level": overlap.get("concentration_level"),
    }


def _context_snapshot(case_id: str, requirement: str) -> dict[str, Any]:
    required_tokens = _tokens(requirement)
    matched: list[dict[str, Any]] = []
    for item in _monitor_items(case_id):
        quality = _safe_float(item.get("quality_score")) or 0.0
        if quality < CONTEXT_MIN_QUALITY or item.get("stale") is True:
            continue
        raw = _raw_item(item)
        blob = _norm(
            " ".join(
                str(raw.get(key) or "")
                for key in ("claim", "title", "source", "url")
            )
        )
        hits = sorted(token for token in required_tokens if token in blob)
        if len(hits) < min(CONTEXT_MIN_TOKEN_HITS, max(1, len(required_tokens))):
            continue
        matched.append(
            {
                "evidence_id": item.get("evidence_id"),
                "claim": str(raw.get("claim") or raw.get("title") or "")[:300],
                "quality_score": round(quality, 4),
                "token_hits": hits,
            }
        )
    matched.sort(key=lambda row: str(row.get("evidence_id") or row.get("claim") or ""))
    return {
        "kind": "CONTEXT_EVIDENCE",
        "status": "MATCHED_CURRENT_CONTEXT" if matched else "NO_MATERIAL_CONTEXT_MATCH",
        "matched_count": len(matched),
        "matched_items": matched,
    }


def obligation_snapshot(primary_module: Any, case_id: str, requirement: str) -> dict[str, Any]:
    classification = classify_requirement(requirement)
    if classification["kind"] == "PRIMARY_EVIDENCE":
        return _primary_lane_snapshot(primary_module, case_id, str(classification["lane"]))
    if classification["kind"] == "PORTFOLIO_CONTEXT":
        return _portfolio_snapshot(case_id)
    return _context_snapshot(case_id, requirement)


def material_change(prior: dict[str, Any] | None, current: dict[str, Any]) -> tuple[bool, list[str]]:
    if not prior:
        return False, ["BASELINE_CREATED"]

    reasons: list[str] = []
    kind = str(current.get("kind") or "")
    if kind == "PRIMARY_EVIDENCE":
        if prior.get("status") != current.get("status"):
            reasons.append("COVERAGE_STATE_CHANGED")
        if prior.get("covered_fact_keys") != current.get("covered_fact_keys"):
            reasons.append("FACT_COVERAGE_CHANGED")
        prior_pct = int(prior.get("coverage_pct") or 0)
        current_pct = int(current.get("coverage_pct") or 0)
        if abs(current_pct - prior_pct) >= 10:
            reasons.append("COVERAGE_MOVED_10PCT")
    elif kind == "PORTFOLIO_CONTEXT":
        if prior.get("portfolio_snapshot_id") != current.get("portfolio_snapshot_id"):
            prior_weight = _safe_float(prior.get("combined_overlap_weight_pct"))
            current_weight = _safe_float(current.get("combined_overlap_weight_pct"))
            if prior.get("status") != current.get("status"):
                reasons.append("PORTFOLIO_STATE_CHANGED")
            elif prior_weight is None or current_weight is None or abs(current_weight - prior_weight) >= 5.0:
                reasons.append("PORTFOLIO_OVERLAP_CHANGED")
            elif prior.get("concentration_level") != current.get("concentration_level"):
                reasons.append("PORTFOLIO_CONCENTRATION_CHANGED")
    else:
        prior_ids = {
            str(item.get("evidence_id") or item.get("claim") or "")
            for item in prior.get("matched_items") or []
            if isinstance(item, dict)
        }
        current_ids = {
            str(item.get("evidence_id") or item.get("claim") or "")
            for item in current.get("matched_items") or []
            if isinstance(item, dict)
        }
        if current_ids - prior_ids:
            reasons.append("NEW_HIGH_QUALITY_CONTEXT_MATCH")

    return bool(reasons), reasons


def _micron_case(case: dict[str, Any], case_id: str) -> bool:
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or case.get("ticker") or "").strip().upper()
    topic = _norm(case.get("topic"))
    return ticker in {"MU", "MU.US"} or "micron" in topic


def _primary_capture_due(case_id: str) -> bool:
    latest = latest_object("primary_evidence_snapshot", case_id=case_id) or {}
    created = _parse_time(latest.get("created_at"))
    if not created:
        return True
    return (datetime.now(timezone.utc) - created).total_seconds() >= PRIMARY_CAPTURE_MINUTES * 60


def _maybe_capture_primary(primary_module: Any, case_id: str, case: dict[str, Any], requirements: list[str]) -> dict[str, Any]:
    mapped = any(classify_requirement(req)["kind"] == "PRIMARY_EVIDENCE" for req in requirements)
    if not mapped or not _micron_case(case, case_id):
        return {"attempted": False, "reason": "NOT_REQUIRED_OR_NOT_MICRON"}
    if not _primary_capture_due(case_id):
        return {"attempted": False, "reason": "CAPTURE_NOT_DUE"}
    try:
        result = primary_module.auto_capture_primary(case_id)
        return {"attempted": True, "result": result}
    except Exception as exc:
        return {"attempted": True, "error": f"{type(exc).__name__}: {exc}"}


def sync_obligations(
    primary_module: Any,
    case_id: str,
    *,
    suppress_changes: bool = False,
) -> dict[str, Any]:
    case = get_object(case_id)
    if not case:
        raise ValueError(f"Unknown case: {case_id}")
    decision, requirements = _requirements(case_id)
    prior_set = latest_object(OBJECT_TYPE, case_id=case_id) or {}
    prior_rows = {
        str(row.get("obligation_key")): row
        for row in prior_set.get("obligations") or []
        if isinstance(row, dict) and row.get("obligation_key")
    }

    rows: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for requirement in requirements:
        obligation_key = _key(requirement)
        classification = classify_requirement(requirement)
        current = obligation_snapshot(primary_module, case_id, requirement)
        prior_row = prior_rows.get(obligation_key) or {}
        prior_snapshot = prior_row.get("snapshot") if isinstance(prior_row.get("snapshot"), dict) else None
        changed, reasons = material_change(prior_snapshot, current)
        if suppress_changes:
            changed = False
            reasons = ["BASELINE_RESET_AFTER_REUNDERWRITE"]
        row = {
            "obligation_key": obligation_key,
            "requirement": requirement,
            "classification": classification,
            "snapshot": current,
            "material_change": changed,
            "change_reasons": reasons,
        }
        rows.append(row)
        if changed:
            changes.append(
                {
                    "obligation_key": obligation_key,
                    "requirement": requirement,
                    "classification": classification,
                    "change_reasons": reasons,
                    "prior_snapshot": prior_snapshot,
                    "current_snapshot": current,
                }
            )

    object_id = str(prior_set.get("deep_watch_obligation_set_id") or f"deep_watch_obligations_{case_id}")
    payload = {
        "deep_watch_obligation_set_id": object_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "source_decision_id": decision.get("decision_id"),
        "committee_disposition": decision.get("disposition"),
        "committee_confidence": decision.get("confidence"),
        "obligation_count": len(rows),
        "material_change_count": len(changes),
        "obligations": rows,
        "material_changes": changes,
        "checked_at": utc_now(),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(object_id, OBJECT_TYPE, case_id, payload, parent_id=decision.get("decision_id"), topic=case.get("topic"))
    record_event(
        case_id,
        "DEEP_WATCH_OBLIGATIONS_REFRESHED",
        entity_id=object_id,
        payload={
            "obligation_count": len(rows),
            "material_change_count": len(changes),
            "trade_execution_permission": False,
        },
    )
    return payload


def _dedupe_raw(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = _raw_item(item)
        key = (
            str(raw.get("url") or "").strip().lower(),
            str(raw.get("claim") or raw.get("title") or "").strip().lower(),
            str(raw.get("timestamp") or raw.get("published_at") or raw.get("observed_at") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(raw)
    return output


def _reunderwrite(primary_module: Any, case_id: str, obligation_set: dict[str, Any]) -> dict[str, Any]:
    import evidence_gap_hunter
    import main
    from eight_agent_orchestrator import run_eight_agent_orchestration
    from paper_capital_api import paper_capital_status

    case = get_object(case_id) or {}
    raw: list[dict[str, Any]] = [
        _raw_item(item)
        for item in case.get("evidence") or []
        if isinstance(item, dict)
    ]
    raw.extend(primary_module.primary_evidence_evidence(case_id))
    raw.extend(_raw_item(item) for item in _monitor_items(case_id))
    combined = _dedupe_raw(raw)
    packet = build_packet(combined)

    packet_id = f"packet_deep_watch_{uuid4().hex}"
    persisted_packet = {
        **packet,
        "evidence_packet_id": packet_id,
        "case_id": case_id,
        "purpose": "DEEP_WATCH_MATERIAL_CHANGE_REUNDERWRITE",
        "triggered_obligations": obligation_set.get("material_changes") or [],
    }
    record_object(packet_id, "evidence_packet", case_id, persisted_packet, topic=case.get("topic"))

    refreshed_case = {
        **case,
        "evidence_packet_id": packet_id,
        "evidence": packet.get("items") or [],
        "evidence_summary": packet.get("summary") or {},
        "updated_at": utc_now(),
        "paper_mode": True,
    }
    record_object(case_id, "case", case_id, refreshed_case, topic=case.get("topic"))

    nine = run_eight_agent_orchestration(case_id)
    committee = nine.get("committee") or {}
    risk = main.evaluate_decision(committee)
    latest_hunt = latest_object("gap_hunt", case_id=case_id) or {}
    assessment = evidence_gap_hunter._qualification_assessment(
        committee,
        risk,
        latest_hunt.get("resolution_matrix") or [],
    )
    assessment_id = f"qualification_{uuid4().hex}"
    qualification = {
        **assessment,
        "qualification_assessment_id": assessment_id,
        "case_id": case_id,
        "decision_id": committee.get("decision_id"),
        "evidence_packet_id": packet_id,
        "deep_watch_reunderwrite": True,
        "created_at": utc_now(),
    }
    record_object(
        assessment_id,
        "qualification_assessment",
        case_id,
        qualification,
        parent_id=committee.get("decision_id"),
        topic=case.get("topic"),
    )

    try:
        capital = paper_capital_status(case_id)
    except Exception as exc:
        capital = {"stage": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}

    reunderwrite_id = f"deep_watch_reunderwrite_{uuid4().hex}"
    payload = {
        "deep_watch_reunderwrite_id": reunderwrite_id,
        "case_id": case_id,
        "triggered_obligations": obligation_set.get("material_changes") or [],
        "evidence_packet_id": packet_id,
        "evidence_summary": packet.get("summary") or {},
        "nine_desk_orchestration": nine.get("orchestration") or {},
        "historical_pattern": nine.get("historical_pattern") or {},
        "committee": committee,
        "risk": risk,
        "qualification": qualification,
        "capital": capital,
        "created_at": utc_now(),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(
        reunderwrite_id,
        REUNDERWRITE_TYPE,
        case_id,
        payload,
        parent_id=assessment_id,
        topic=case.get("topic"),
    )
    record_event(
        case_id,
        "DEEP_WATCH_MATERIAL_CHANGE_REUNDERWRITE_COMPLETE",
        entity_id=reunderwrite_id,
        payload={
            "material_change_count": len(obligation_set.get("material_changes") or []),
            "committee_disposition": committee.get("disposition"),
            "committee_confidence": committee.get("confidence"),
            "qualification_stage": qualification.get("stage"),
            "qualified_buy_candidate": qualification.get("qualified_buy_candidate"),
            "capital_stage": capital.get("stage"),
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )

    # The fresh Committee may rewrite its requirements. Seed those new obligations as a
    # baseline so the next monitor tick cannot recursively re-underwrite the same state.
    sync_obligations(primary_module, case_id, suppress_changes=True)
    return payload


def run_obligation_cycle(
    primary_module: Any,
    case_id: str,
    *,
    allow_reunderwrite: bool = True,
) -> dict[str, Any]:
    case = get_object(case_id)
    if not case:
        raise ValueError(f"Unknown case: {case_id}")
    decision, requirements = _requirements(case_id)
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    if not decision or profile.get("enabled") is not True:
        return {
            "case_id": case_id,
            "state": "NOT_ACTIVE_DEEP_WATCH",
            "reason": "COMMITTEE_DECISION_AND_ENABLED_MONITOR_REQUIRED",
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    capture = _maybe_capture_primary(primary_module, case_id, case, requirements)
    obligation_set = sync_obligations(primary_module, case_id)
    reunderwrite = None
    if allow_reunderwrite and obligation_set.get("material_change_count", 0) > 0:
        reunderwrite = _reunderwrite(primary_module, case_id, obligation_set)

    return {
        "case_id": case_id,
        "state": "REUNDERWRITTEN" if reunderwrite else "WATCHING",
        "primary_capture": capture,
        "obligation_set": obligation_set,
        "reunderwrite": reunderwrite,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def install_deep_watch_obligation_engine(primary_module: Any, monitoring_module: Any) -> None:
    global _primary_module
    _primary_module = primary_module
    prior_refresh = monitoring_module.refresh_profile

    def refresh_profile_with_deep_watch(profile: dict[str, Any]):
        result = prior_refresh(profile)
        case_id = str(profile.get("case_id") or "")
        try:
            result["deep_watch_obligations"] = run_obligation_cycle(
                primary_module,
                case_id,
                allow_reunderwrite=True,
            )
        except Exception as exc:
            record_event(
                case_id,
                "DEEP_WATCH_OBLIGATION_CYCLE_FAILED",
                payload={
                    "error": f"{type(exc).__name__}: {exc}",
                    "trade_execution_permission": False,
                    "live_execution": False,
                },
            )
            result["deep_watch_obligations"] = {
                "state": "ERROR_FAIL_CLOSED",
                "error": f"{type(exc).__name__}: {exc}",
                "paper_mode": True,
                "trade_execution_permission": False,
                "live_execution": False,
            }
        return result

    monitoring_module.refresh_profile = refresh_profile_with_deep_watch


@router.get("/deep-watch/{case_id}/status")
def deep_watch_status(case_id: str):
    if not get_object(case_id):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return {
        "case_id": case_id,
        "obligation_set": latest_object(OBJECT_TYPE, case_id=case_id),
        "latest_reunderwrite": latest_object(REUNDERWRITE_TYPE, case_id=case_id),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/deep-watch/{case_id}/run")
def deep_watch_run(case_id: str, request: dict[str, Any] = Body(default={})):
    if _primary_module is None:
        raise HTTPException(status_code=503, detail="Deep watch engine is not installed")
    try:
        return run_obligation_cycle(
            _primary_module,
            case_id,
            allow_reunderwrite=bool(request.get("allow_reunderwrite", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
