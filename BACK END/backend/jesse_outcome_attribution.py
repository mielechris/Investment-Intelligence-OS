from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from fastapi import APIRouter

import ledger
from ledger import get_object, latest_object, record_event, record_object, utc_now
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE
from thesis_integrity_v2 import assess_thesis_integrity_v2


router = APIRouter()
POLICY_VERSION = "batch10c-jesse-outcome-attribution-v1"
OBJECT_TYPE = "jesse_outcome_attribution"


def _rows_by_type(object_type: str, limit: int = 1000) -> list[dict[str, Any]]:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM ledger_objects
            WHERE object_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (object_type, max(1, min(int(limit), 5000))),
        ).fetchall()
    finally:
        connection.close()
    output: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict):
            output.append(payload)
    return output


def _candidate_for_ticker(scan: dict[str, Any], ticker: str) -> tuple[str | None, dict[str, Any]]:
    ids = [str(value) for value in scan.get("opportunity_candidate_ids") or []]
    top = [row for row in scan.get("top_three") or [] if isinstance(row, dict)]
    wanted = ticker.upper()
    for index, row in enumerate(top):
        if str(row.get("ticker") or "").upper() != wanted:
            continue
        candidate_id = ids[index] if index < len(ids) else None
        return candidate_id, row
    return None, {}


def _bridge_result(scan: dict[str, Any], *, ticker: str, candidate_id: str | None) -> dict[str, Any]:
    bridge = scan.get("bridge") if isinstance(scan.get("bridge"), dict) else {}
    for row in bridge.get("results") or []:
        if not isinstance(row, dict):
            continue
        if candidate_id and str(row.get("candidate_id") or "") == candidate_id:
            return row
        if str(row.get("ticker") or "").upper() == ticker.upper():
            return row
    return {}


def _target_assessment(recommendation: str, target_hit: bool | None) -> str:
    rec = str(recommendation or "UNKNOWN").upper()
    if target_hit is None:
        return "TARGET_OUTCOME_UNKNOWN"
    if rec == "NO_TRADE":
        return "NO_TRADE_MISSED_TARGET_UPSIDE" if target_hit else "NO_TRADE_TARGET_NOT_HIT"
    if rec in {"BUY", "WATCH"}:
        return "TARGET_HIT" if target_hit else "TARGET_MISSED"
    return "UNCLASSIFIED_TARGET_OUTCOME"


def _wrong_vs_early_label(integrity: dict[str, Any] | None, case_id: str | None) -> str:
    if not case_id:
        return "NOT_APPLICABLE_NO_GOVERNED_THESIS"
    state = str((integrity or {}).get("thesis_integrity_state") or "UNKNOWN").upper()
    if state == "THESIS_BROKEN":
        return "WRONG"
    if state == "EARLY_BUT_INTACT":
        return "EARLY"
    if state == "INTACT":
        return "INTACT"
    if state == "MATERIAL_CHANGE":
        return "REUNDERWRITE"
    if state == "CLOSED":
        return "CLOSED"
    return "UNKNOWN"


def _case_lineage(case_id: str | None) -> dict[str, Any]:
    if not case_id:
        return {
            "committee": None,
            "qualification": None,
            "paper_execution": None,
            "postmortem": None,
            "thesis_integrity": None,
            "wrong_vs_early": "NOT_APPLICABLE_NO_GOVERNED_THESIS",
            "paper_position_created": False,
            "paper_realized_return_pct": None,
        }

    committee = latest_object("committee_decision", case_id=case_id) or {}
    qualification = latest_object("qualification_assessment", case_id=case_id) or {}
    execution = latest_object("governed_paper_execution", case_id=case_id) or {}
    postmortem = (
        latest_object("paper_trade_postmortem", case_id=case_id)
        or latest_object("postmortem", case_id=case_id)
        or {}
    )
    try:
        integrity = assess_thesis_integrity_v2(case_id)
    except Exception:
        integrity = {}

    paper_position_created = bool(
        execution.get("status") == "COMPLETE"
        and execution.get("execution") == "PAPER_ORDER_CREATED"
    )
    return {
        "committee": {
            "decision_id": committee.get("decision_id"),
            "disposition": committee.get("disposition"),
            "confidence": committee.get("confidence"),
        } if committee else None,
        "qualification": {
            "qualification_assessment_id": qualification.get("qualification_assessment_id"),
            "qualified_buy_candidate": qualification.get("qualified_buy_candidate"),
            "unmet_requirements": qualification.get("unmet_requirements") or [],
        } if qualification else None,
        "paper_execution": {
            "execution_id": execution.get("execution_id"),
            "status": execution.get("status"),
            "execution": execution.get("execution"),
            "entry_price": execution.get("entry_price"),
            "notional": execution.get("notional"),
        } if execution else None,
        "postmortem": {
            "postmortem_id": postmortem.get("paper_trade_postmortem_id") or postmortem.get("postmortem_id"),
            "outcome": postmortem.get("outcome"),
            "realized_return_pct": postmortem.get("realized_return_pct"),
        } if postmortem else None,
        "thesis_integrity": integrity or None,
        "wrong_vs_early": _wrong_vs_early_label(integrity, case_id),
        "paper_position_created": paper_position_created,
        "paper_realized_return_pct": postmortem.get("realized_return_pct") if postmortem else None,
    }


def build_outcome_attribution(outcome: dict[str, Any]) -> dict[str, Any]:
    scan_id = str(outcome.get("dislocation_scan_id") or "").strip()
    ticker = str(outcome.get("ticker") or "").strip().upper()
    scan = get_object(scan_id) if scan_id else None
    scan = scan if isinstance(scan, dict) else {}

    candidate_id, top_row = _candidate_for_ticker(scan, ticker)
    candidate = get_object(candidate_id) if candidate_id else None
    candidate = candidate if isinstance(candidate, dict) else {}
    bridge_row = _bridge_result(scan, ticker=ticker, candidate_id=candidate_id)
    case_id = str(
        bridge_row.get("case_id")
        or candidate.get("promoted_case_id")
        or ""
    ).strip() or None
    lineage = _case_lineage(case_id)

    recommendation = str(
        outcome.get("original_recommendation")
        or top_row.get("recommendation")
        or "UNKNOWN"
    ).upper()
    probability = top_row.get("estimated_probability_next_day_plus_5")
    target_hit = outcome.get("target_hit")
    target_hit_value = target_hit if isinstance(target_hit, bool) else None

    attribution_id = f"jesse_attribution_{str(outcome.get('dislocation_outcome_id') or scan_id + '_' + ticker)}"
    return {
        "jesse_outcome_attribution_id": attribution_id,
        "policy_version": POLICY_VERSION,
        "dislocation_outcome_id": outcome.get("dislocation_outcome_id"),
        "dislocation_scan_id": scan_id or None,
        "candidate_id": candidate_id,
        "ticker": ticker or None,
        "company": top_row.get("company") or candidate.get("label"),
        "case_id": case_id,
        "bridge_status": bridge_row.get("status") or ("LEGACY_NO_BRIDGE" if scan and not scan.get("bridge") else "UNKNOWN"),
        "original_recommendation": recommendation,
        "original_financial_strength_score": top_row.get("financial_strength_score") or candidate.get("score"),
        "estimated_probability_next_day_plus_5": probability,
        "target_upside_pct": outcome.get("target_upside_pct") or top_row.get("target_upside_pct") or 5.0,
        "target_hit": target_hit_value,
        "next_day_return_pct": outcome.get("return_pct"),
        "baseline_price": outcome.get("baseline_price"),
        "followup_price": outcome.get("followup_price"),
        "target_assessment": _target_assessment(recommendation, target_hit_value),
        "committee": lineage["committee"],
        "qualification": lineage["qualification"],
        "paper_execution": lineage["paper_execution"],
        "postmortem": lineage["postmortem"],
        "paper_position_created": lineage["paper_position_created"],
        "paper_realized_return_pct": lineage["paper_realized_return_pct"],
        "thesis_integrity": lineage["thesis_integrity"],
        "wrong_vs_early": lineage["wrong_vs_early"],
        "learning_scope": {
            "jesse_probability_calibration_eligible": target_hit_value is not None,
            "thesis_outcome_requires_governed_thesis_evidence": True,
            "next_day_target_is_not_full_thesis_proof": True,
            "mfe_mae_after_action_available": False,
        },
        "paper_mode": True,
        "research_only": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "updated_at": utc_now(),
        "created_at": utc_now(),
    }


def persist_outcome_attribution(outcome: dict[str, Any]) -> dict[str, Any]:
    attribution = build_outcome_attribution(outcome)
    object_id = str(attribution["jesse_outcome_attribution_id"])
    case_id = str(attribution.get("case_id") or OPPORTUNITY_LEDGER_CASE)
    record_object(
        object_id,
        OBJECT_TYPE,
        case_id,
        attribution,
        topic=str(attribution.get("ticker") or "JESSE_OUTCOME"),
    )
    record_event(
        case_id,
        "JESSE_OUTCOME_ATTRIBUTED",
        entity_id=object_id,
        payload={
            "ticker": attribution.get("ticker"),
            "target_assessment": attribution.get("target_assessment"),
            "wrong_vs_early": attribution.get("wrong_vs_early"),
            "paper_position_created": attribution.get("paper_position_created"),
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )
    return attribution


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_hits = sum(1 for row in rows if row.get("target_hit") is True)
    eligible = sum(1 for row in rows if row.get("target_hit") is not None)
    returns = [float(row["next_day_return_pct"]) for row in rows if row.get("next_day_return_pct") is not None]
    target_counts = Counter(str(row.get("target_assessment") or "UNKNOWN") for row in rows)
    integrity_counts = Counter(str(row.get("wrong_vs_early") or "UNKNOWN") for row in rows)
    return {
        "observations": len(rows),
        "target_eligible_observations": eligible,
        "plus_5_hits": target_hits,
        "plus_5_hit_rate": round(target_hits / eligible, 4) if eligible else None,
        "average_next_day_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "target_assessments": dict(target_counts),
        "wrong_vs_early": dict(integrity_counts),
        "paper_positions_created": sum(1 for row in rows if row.get("paper_position_created") is True),
        "paper_realized_outcomes": sum(1 for row in rows if row.get("paper_realized_return_pct") is not None),
        "minimum_probability_calibration_observations": 30,
        "probability_calibrated": eligible >= 30,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def refresh_all_jesse_outcome_attributions(limit: int = 1000) -> dict[str, Any]:
    outcomes = _rows_by_type("dislocation_outcome", limit)
    refreshed = [persist_outcome_attribution(outcome) for outcome in outcomes]
    return {
        "refreshed_count": len(refreshed),
        "summary": _summary(refreshed),
        "attributions": refreshed,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def outcome_status(limit: int = 100) -> dict[str, Any]:
    rows = _rows_by_type(OBJECT_TYPE, limit)
    return {
        "summary": _summary(rows),
        "attributions": rows,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/intelligence/jesse-outcomes/status")
def get_outcome_status(limit: int = 100):
    return outcome_status(limit)


@router.post("/intelligence/jesse-outcomes/refresh")
def refresh_outcomes(limit: int = 1000):
    return refresh_all_jesse_outcome_attributions(limit)
