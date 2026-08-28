from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

import ledger
from ledger import get_object, latest_object
from paper_capital_api import paper_capital_status


router = APIRouter()
POLICY_VERSION = "closed-loop-lineage-v1"


def _latest(object_type: str, case_id: str) -> dict[str, Any]:
    return latest_object(object_type, case_id=case_id) or {}


def _object_id(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return None


def _stage_row(name: str, row: dict[str, Any], object_id: str | None, state: Any = None) -> dict[str, Any]:
    return {
        "stage": name,
        "present": bool(row),
        "object_id": object_id,
        "state": state,
    }


def _capital_status(case_id: str) -> dict[str, Any]:
    try:
        return paper_capital_status(case_id)
    except Exception as exc:
        return {
            "stage": "NOT_AVAILABLE",
            "error": f"{type(exc).__name__}: {exc}",
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }


def build_case_lineage(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise ValueError("Unknown case_id")

    orchestration = _latest("agent_orchestration", case_id)
    historical = _latest("historical_pattern_review", case_id)
    committee = _latest("committee_decision", case_id)
    risk = _latest("risk_authorization", case_id)
    qualification = _latest("qualification_assessment", case_id)
    gap_hunt = _latest("gap_hunt", case_id)
    portfolio = _latest("portfolio_snapshot", case_id)
    entry_watch = _latest("capital_entry_watch", case_id)
    sizing = _latest("paper_sizing_profile", case_id)
    authorization = _latest("paper_authorization", case_id)
    execution = _latest("governed_paper_execution", case_id)
    monitor = _latest("monitor_profile", case_id)
    deep_watch = _latest("deep_watch_obligation_set", case_id)
    deep_reunderwrite = _latest("deep_watch_reunderwrite", case_id)
    thesis = _latest("thesis_monitor", case_id)
    postmortem = _latest("postmortem", case_id)
    capital = _capital_status(case_id)

    committee_disposition = str(committee.get("disposition") or "")
    risk_decision = str(risk.get("decision") or (gap_hunt.get("risk") or {}).get("decision") or "")
    qualified = qualification.get("qualified_buy_candidate") is True
    execution_complete = (
        execution.get("status") == "COMPLETE"
        and execution.get("execution") == "PAPER_ORDER_CREATED"
    )
    monitored = bool(monitor and monitor.get("enabled") is True)
    deep_watch_active = bool(deep_watch)

    stages = [
        _stage_row("CASE", case, case_id, "CREATED"),
        _stage_row(
            "NINE_DESK_RESEARCH",
            orchestration,
            _object_id(orchestration, "orchestration_id"),
            orchestration.get("committee_disposition"),
        ),
        _stage_row(
            "HISTORICAL_PATTERN",
            historical,
            _object_id(historical, "historical_pattern_review_id", "agent_result_id"),
            historical.get("historical_signal") or historical.get("disposition"),
        ),
        _stage_row(
            "COMMITTEE",
            committee,
            _object_id(committee, "decision_id"),
            committee_disposition or None,
        ),
        _stage_row(
            "RISK",
            risk or (gap_hunt.get("risk") or {}),
            _object_id(risk, "risk_authorization_id") or _object_id(gap_hunt.get("risk") or {}, "risk_authorization_id"),
            risk_decision or None,
        ),
        _stage_row(
            "QUALIFICATION",
            qualification,
            _object_id(qualification, "qualification_assessment_id"),
            "QUALIFIED" if qualified else qualification.get("stage"),
        ),
        _stage_row(
            "PORTFOLIO_CONTEXT",
            portfolio,
            _object_id(portfolio, "portfolio_snapshot_id"),
            (portfolio.get("overlap") or {}).get("concentration_level"),
        ),
        _stage_row(
            "CAPITAL",
            capital if capital.get("stage") != "NOT_AVAILABLE" else {},
            _object_id(entry_watch, "capital_entry_watch_id"),
            capital.get("stage"),
        ),
        _stage_row(
            "SIZING",
            sizing,
            _object_id(sizing, "paper_sizing_profile_id"),
            sizing.get("decision") or ("CONFIGURED" if sizing else None),
        ),
        _stage_row(
            "PAPER_AUTHORIZATION",
            authorization,
            _object_id(authorization, "paper_authorization_id"),
            authorization.get("decision"),
        ),
        _stage_row(
            "PAPER_EXECUTION",
            execution,
            _object_id(execution, "execution_id"),
            execution.get("execution") or execution.get("status"),
        ),
        _stage_row(
            "MONITORING",
            monitor,
            _object_id(monitor, "monitor_profile_id"),
            "ACTIVE" if monitored else ("DISABLED" if monitor else None),
        ),
        _stage_row(
            "DEEP_WATCH",
            deep_watch,
            _object_id(deep_watch, "deep_watch_obligation_set_id"),
            f"{deep_watch.get('obligation_count', 0)} obligations" if deep_watch else None,
        ),
        _stage_row(
            "DEEP_REUNDERWRITE",
            deep_reunderwrite,
            _object_id(deep_reunderwrite, "deep_watch_reunderwrite_id"),
            (deep_reunderwrite.get("committee") or {}).get("disposition"),
        ),
        _stage_row(
            "THESIS_MONITOR",
            thesis,
            _object_id(thesis, "thesis_monitor_id"),
            thesis.get("thesis_status"),
        ),
        _stage_row(
            "OUTCOME_POSTMORTEM",
            postmortem,
            _object_id(postmortem, "postmortem_id"),
            postmortem.get("outcome"),
        ),
    ]

    if postmortem:
        current_stage = "OUTCOME_RECORDED"
    elif execution_complete:
        current_stage = "PAPER_POSITION_OPENED"
    elif authorization:
        current_stage = "PAPER_AUTHORIZED"
    elif capital.get("stage") not in {None, "", "NOT_AVAILABLE"}:
        current_stage = str(capital.get("stage"))
    elif qualified:
        current_stage = "QUALIFIED_RESEARCH_CANDIDATE"
    elif deep_watch_active:
        current_stage = "DEEP_WATCH"
    elif monitored:
        current_stage = "MONITORING"
    elif committee_disposition == "NO_TRADE":
        current_stage = "COMMITTEE_NO_TRADE"
    elif committee_disposition == "WATCH":
        current_stage = "COMMITTEE_WATCH"
    elif committee:
        current_stage = "COMMITTEE_COMPLETE"
    elif orchestration:
        current_stage = "RESEARCH_COMPLETE"
    else:
        current_stage = "CASE_CREATED"

    rejection_or_watch = committee_disposition in {"NO_TRADE", "WATCH"} and not execution_complete
    valid_no_capital_outcome = bool(
        rejection_or_watch
        and (
            deep_watch_active
            or monitored
            or postmortem
            or risk_decision in {"VETOED", "WATCH_ONLY"}
        )
    )

    if execution_complete or postmortem:
        continuity_state = "CLOSED_LOOP_CAPITAL_PATH"
    elif valid_no_capital_outcome:
        continuity_state = "CLOSED_LOOP_NO_CAPITAL_PATH"
    elif committee and rejection_or_watch:
        continuity_state = "RESEARCH_DECISION_WITHOUT_MONITORING"
    else:
        continuity_state = "IN_PROGRESS"

    missing_continuation: list[str] = []
    if committee and rejection_or_watch and not (monitored or deep_watch_active or postmortem):
        missing_continuation.append("MONITOR_OR_DEEP_WATCH")
    if execution_complete and not (monitored or thesis or postmortem):
        missing_continuation.append("POST_EXECUTION_MONITORING")

    return {
        "policy_version": POLICY_VERSION,
        "case_id": case_id,
        "topic": case.get("topic"),
        "current_stage": current_stage,
        "continuity_state": continuity_state,
        "valid_no_capital_outcome": valid_no_capital_outcome,
        "dead_end": bool(missing_continuation),
        "missing_continuation": missing_continuation,
        "committee_disposition": committee_disposition or None,
        "committee_confidence": committee.get("confidence"),
        "risk_decision": risk_decision or None,
        "qualified_buy_candidate": qualified,
        "capital_stage": capital.get("stage"),
        "paper_execution_complete": execution_complete,
        "monitoring_active": monitored,
        "deep_watch_active": deep_watch_active,
        "stage_count_present": sum(1 for row in stages if row["present"]),
        "stages": stages,
        "paper_mode": True,
        "read_only_surface": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _recent_case_ids(limit: int) -> list[str]:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT case_id
            FROM ledger_objects
            WHERE object_type = 'case'
              AND case_id LIKE 'case_%'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    finally:
        connection.close()
    return [str(row["case_id"]) for row in rows if str(row["case_id"] or "").startswith("case_")]


def build_closed_loop_overview(limit: int = 25) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case_id in _recent_case_ids(limit):
        try:
            lineage = build_case_lineage(case_id)
        except Exception as exc:
            rows.append(
                {
                    "case_id": case_id,
                    "current_stage": "ERROR_FAIL_CLOSED",
                    "continuity_state": "UNKNOWN",
                    "dead_end": True,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        rows.append(
            {
                "case_id": case_id,
                "topic": lineage.get("topic"),
                "current_stage": lineage.get("current_stage"),
                "continuity_state": lineage.get("continuity_state"),
                "committee_disposition": lineage.get("committee_disposition"),
                "qualified_buy_candidate": lineage.get("qualified_buy_candidate"),
                "paper_execution_complete": lineage.get("paper_execution_complete"),
                "monitoring_active": lineage.get("monitoring_active"),
                "deep_watch_active": lineage.get("deep_watch_active"),
                "valid_no_capital_outcome": lineage.get("valid_no_capital_outcome"),
                "dead_end": lineage.get("dead_end"),
                "missing_continuation": lineage.get("missing_continuation"),
            }
        )

    return {
        "policy_version": POLICY_VERSION,
        "case_count": len(rows),
        "closed_loop_capital_paths": sum(1 for row in rows if row.get("continuity_state") == "CLOSED_LOOP_CAPITAL_PATH"),
        "closed_loop_no_capital_paths": sum(1 for row in rows if row.get("continuity_state") == "CLOSED_LOOP_NO_CAPITAL_PATH"),
        "dead_end_count": sum(1 for row in rows if row.get("dead_end") is True),
        "cases": rows,
        "paper_mode": True,
        "read_only_surface": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/closed-loop/{case_id}/status")
def closed_loop_case_status(case_id: str):
    try:
        return build_case_lineage(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/closed-loop/overview")
def closed_loop_overview(limit: int = 25):
    return build_closed_loop_overview(limit)
