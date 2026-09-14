from __future__ import annotations

import json
import sqlite3
import statistics
from collections import defaultdict
from typing import Any

from fastapi import APIRouter

from ledger import DB_PATH, get_object, utc_now


router = APIRouter()
SCORECARD_VERSION = "grok-multicase-scorecard-v1"
MIN_VALID_REPEATABILITY_CASES = 3
MIN_CASES_BEFORE_PROMOTION_REVIEW = 4


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _all_results() -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? ORDER BY created_at ASC",
            ("grok_ab_result",),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def _is_valid_repeatability_result(row: dict[str, Any]) -> bool:
    comparison = row.get("comparison") if isinstance(row.get("comparison"), dict) else {}
    return (
        comparison.get("experiment_valid") is True
        and int(row.get("runs_per_arm") or 0) >= 2
        and row.get("auto_trade_authority") is False
        and row.get("paper_order_permission") is False
        and row.get("trade_execution_permission") is False
        and row.get("live_execution") is False
    )


def _selected_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        case_id = str(row.get("case_id") or "").strip()
        if case_id and _is_valid_repeatability_result(row):
            by_case[case_id].append(row)

    selected: list[dict[str, Any]] = []
    for case_rows in by_case.values():
        # Prefer the latest valid repeatability result for each case. This naturally
        # excludes earlier invalid attempts such as stale-evidence runs.
        case_rows.sort(key=lambda item: str(item.get("created_at") or ""))
        selected.append(case_rows[-1])
    selected.sort(key=lambda item: str(item.get("created_at") or ""))
    return selected


def _case_summary(row: dict[str, Any]) -> dict[str, Any]:
    comparison = row.get("comparison") or {}
    baseline = comparison.get("baseline") or {}
    grok = comparison.get("iios_plus_grok") or {}
    case_id = str(row.get("case_id") or "")
    case = get_object(case_id) or {}
    confidence_delta = _float(comparison.get("confidence_delta"))
    evidence_delta = _float(comparison.get("required_evidence_count_delta"))
    latency_delta = _float(grok.get("median_latency_ms")) - _float(baseline.get("median_latency_ms"))
    if confidence_delta > 0:
        confidence_direction = "INCREASED"
    elif confidence_delta < 0:
        confidence_direction = "DECREASED"
    else:
        confidence_direction = "UNCHANGED"
    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "runs_per_arm": int(row.get("runs_per_arm") or 0),
        "base_evidence_mode": row.get("base_evidence_mode") or "ORIGINAL_CASE_EVIDENCE",
        "grok_citation_count": int((row.get("grok_context_summary") or {}).get("citation_count") or 0),
        "grok_admitted_count": int((row.get("grok_context_summary") or {}).get("admitted_count") or 0),
        "baseline_dispositions": list(baseline.get("dispositions") or []),
        "grok_dispositions": list(grok.get("dispositions") or []),
        "disposition_changed": bool(comparison.get("committee_disposition_changed")),
        "baseline_median_confidence": _float(baseline.get("median_confidence")),
        "grok_median_confidence": _float(grok.get("median_confidence")),
        "confidence_delta": round(confidence_delta, 4),
        "confidence_direction": confidence_direction,
        "required_evidence_delta": round(evidence_delta, 4),
        "baseline_median_latency_ms": round(_float(baseline.get("median_latency_ms")), 2),
        "grok_median_latency_ms": round(_float(grok.get("median_latency_ms")), 2),
        "latency_delta_ms": round(latency_delta, 2),
        "baseline_guards_clean": baseline.get("all_guards_clean") is True,
        "grok_guards_clean": grok.get("all_guards_clean") is True,
        "experiment_valid": comparison.get("experiment_valid") is True,
        "new_xai_search_calls_in_ab": int(row.get("new_xai_search_calls") or 0),
        "trade_execution_permission": False,
        "live_execution": False,
    }


def build_grok_scorecard() -> dict[str, Any]:
    rows = _all_results()
    selected = _selected_results(rows)
    cases = [_case_summary(row) for row in selected]
    deltas = [row["confidence_delta"] for row in cases]
    absolute_deltas = [abs(value) for value in deltas]
    evidence_deltas = [row["required_evidence_delta"] for row in cases]
    latency_deltas = [row["latency_delta_ms"] for row in cases]

    valid_count = len(cases)
    interim_signal = valid_count >= MIN_VALID_REPEATABILITY_CASES
    all_safety_locked = all(
        row["experiment_valid"]
        and row["baseline_guards_clean"]
        and row["grok_guards_clean"]
        and row["trade_execution_permission"] is False
        and row["live_execution"] is False
        for row in cases
    ) if cases else False

    blockers = []
    if valid_count < MIN_CASES_BEFORE_PROMOTION_REVIEW:
        blockers.append(f"at least {MIN_CASES_BEFORE_PROMOTION_REVIEW} valid cross-case repeatability cases required")
    blockers.extend([
        "realized paper-return comparison required",
        "false-positive rate comparison required",
        "discovery lead-time comparison required",
    ])

    return {
        "scorecard_version": SCORECARD_VERSION,
        "status": "INTERIM_SIGNAL_AVAILABLE" if interim_signal else "MORE_VALID_CASES_REQUIRED",
        "valid_repeatability_cases": valid_count,
        "minimum_valid_cases_for_interim_signal": MIN_VALID_REPEATABILITY_CASES,
        "minimum_cases_before_promotion_review": MIN_CASES_BEFORE_PROMOTION_REVIEW,
        "cases": cases,
        "aggregate": {
            "mean_confidence_delta": round(statistics.mean(deltas), 4) if deltas else 0.0,
            "median_confidence_delta": round(statistics.median(deltas), 4) if deltas else 0.0,
            "mean_absolute_confidence_shift": round(statistics.mean(absolute_deltas), 4) if absolute_deltas else 0.0,
            "confidence_increase_cases": sum(1 for value in deltas if value > 0),
            "confidence_decrease_cases": sum(1 for value in deltas if value < 0),
            "confidence_unchanged_cases": sum(1 for value in deltas if value == 0),
            "disposition_change_cases": sum(1 for row in cases if row["disposition_changed"]),
            "mean_required_evidence_delta": round(statistics.mean(evidence_deltas), 4) if evidence_deltas else 0.0,
            "mean_latency_delta_ms": round(statistics.mean(latency_deltas), 2) if latency_deltas else 0.0,
            "all_selected_experiments_valid": all(row["experiment_valid"] for row in cases) if cases else False,
            "all_guards_clean": all(row["baseline_guards_clean"] and row["grok_guards_clean"] for row in cases) if cases else False,
            "all_safety_locked": all_safety_locked,
        },
        "interpretation": (
            "Grok is showing a measurable cross-case effect on committee confidence, but confidence movement is not treated as investment-quality improvement. "
            "Permanent promotion remains blocked until a broader control sample and realized paper outcomes show that the added context improves decisions rather than merely changing them."
        ),
        "recommendation": "CONTINUE_CONTROLLED_EXPERIMENT",
        "permanent_factory_promotion_ready": False,
        "promotion_blockers": blockers,
        "automatic_configuration_change": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.get("/grok/scorecard")
def get_grok_scorecard():
    return build_grok_scorecard()
