from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter

from ledger import DB_PATH, latest_object, utc_now


router = APIRouter()
POLICY_VERSION = "grok-paper-value-readiness-v2"


def _rows(object_type: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? ORDER BY created_at ASC",
            (object_type,),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row[0]) for row in rows]


def _valid_repeatability_results() -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in _rows("grok_ab_result"):
        comparison = row.get("comparison") if isinstance(row.get("comparison"), dict) else {}
        case_id = str(row.get("case_id") or "").strip()
        if not case_id or comparison.get("experiment_valid") is not True or int(row.get("runs_per_arm") or 0) < 2:
            continue
        current = selected.get(case_id)
        if current is None or str(row.get("created_at") or "") > str(current.get("created_at") or ""):
            selected[case_id] = row
    return list(selected.values())


def build_paper_value_report() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    realized_count = 0
    monitored_count = 0

    for result in _valid_repeatability_results():
        case_id = str(result.get("case_id") or "")
        postmortem = latest_object("postmortem", case_id=case_id) or {}
        position = latest_object("position_monitor", case_id=case_id) or {}
        realized_return = postmortem.get("realized_return_pct")
        observed_return = position.get("return_pct")
        if realized_return is not None:
            realized_count += 1
        if observed_return is not None:
            monitored_count += 1
        comparison = result.get("comparison") or {}
        cases.append({
            "case_id": case_id,
            "baseline_disposition": comparison.get("baseline_disposition"),
            "grok_disposition": comparison.get("grok_disposition"),
            "committee_disposition_changed": comparison.get("committee_disposition_changed") is True,
            "observed_shadow_return_pct": observed_return,
            "realized_return_pct": realized_return,
            "postmortem_outcome": postmortem.get("outcome"),
            "paper_outcome_available": realized_return is not None or observed_return is not None,
            "arm_specific_pnl_available": False,
            "trade_execution_permission": False,
            "live_execution": False,
        })

    shadow_pairs = _rows("grok_shadow_paper_pair")
    shadow_snapshots = _rows("grok_shadow_paper_snapshot")
    differentiated = sum(1 for row in shadow_pairs if row.get("differentiated_action") is True)
    blockers = [
        "arm-specific governed paper positions required before P&L can be claimed",
        "benchmark and drawdown attribution required",
    ]
    if differentiated == 0:
        blockers.append("at least one valid A/B case with differentiated committee action required for comparative paper value")

    return {
        "policy_version": POLICY_VERSION,
        "status": "OUTCOME_OBSERVATIONS_AVAILABLE" if (realized_count or monitored_count or shadow_snapshots) else "WAITING_FOR_PAPER_OUTCOMES",
        "valid_ab_case_count": len(cases),
        "cases_with_position_monitor": monitored_count,
        "cases_with_realized_return": realized_count,
        "shadow_pair_count": len(shadow_pairs),
        "shadow_snapshot_count": len(shadow_snapshots),
        "differentiated_action_pair_count": differentiated,
        "cases": cases,
        "shadow_measurement_ledger_ready": len(shadow_pairs) > 0,
        "return_comparison_ready": False,
        "arm_specific_pnl_available": False,
        "permanent_promotion_value_proof_ready": False,
        "blockers": blockers,
        "interpretation": "The shadow ledger can track cash/no-position versus watch-only decisions and underlying asset movement, but IIOS-only versus IIOS+Grok P&L is not claimed until governed arm-specific paper positions actually exist.",
        "automatic_promotion": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.get("/grok/value/paper-outcomes")
def get_grok_paper_value_report():
    return build_paper_value_report()
