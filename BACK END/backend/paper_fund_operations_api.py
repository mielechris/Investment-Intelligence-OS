from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import ledger
from ledger import get_object, latest_object, utc_now
from paper_portfolio_core import build_performance_history, build_portfolio_state


OBSERVATION_CASE_ID = "observation_operations"
OBSERVATION_STATE_TYPE = "observation_operations_state"
PAPER_TRADING_CASE_ID = "paper_trading_operations"
PAPER_TRADING_STATE_TYPE = "governed_paper_trading_state"
DEFAULT_CADENCE_MINUTES = 15


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rows_by_type(object_type: str, limit: int = 100) -> list[dict[str, Any]]:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT payload_json, created_at
            FROM ledger_objects
            WHERE object_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (object_type, max(1, min(int(limit), 500))),
        ).fetchall()
    finally:
        connection.close()

    output: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict):
            output.append({**payload, "_ledger_created_at": row["created_at"]})
    return output


def _latest_event_case(event_type: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT case_id, created_at
            FROM audit_events
            WHERE event_type = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (event_type,),
        ).fetchone()
    finally:
        connection.close()

    if not row:
        return None
    return {
        "case_id": row["case_id"],
        "created_at": row["created_at"],
    }


def _worker_view(
    state: dict[str, Any],
    *,
    completed_key: str,
    cadence_minutes: int = DEFAULT_CADENCE_MINUTES,
) -> dict[str, Any]:
    cadence = max(1, int(cadence_minutes or DEFAULT_CADENCE_MINUTES))
    completed_at = _parse_time(state.get(completed_key)) if state else None
    now = datetime.now(timezone.utc)

    next_due_at: str | None = None
    seconds_until_next_cycle: int | None = None
    cadence_state = "UNKNOWN"

    if completed_at is not None:
        due = completed_at + timedelta(minutes=cadence)
        next_due_at = due.isoformat()
        seconds_until_next_cycle = max(0, int((due - now).total_seconds()))
        age_seconds = max(0.0, (now - completed_at).total_seconds())
        cadence_state = (
            "ON_CADENCE"
            if age_seconds <= cadence * 60 * 2
            else "OVERDUE"
        )

    return {
        "availability": "AVAILABLE" if state else "NO_STATE",
        "cadence_minutes": cadence,
        "last_completed_at": completed_at.isoformat() if completed_at else None,
        "next_due_at": next_due_at,
        "seconds_until_next_cycle": seconds_until_next_cycle,
        "cadence_state": cadence_state,
        "market_phase": state.get("market_phase") if state else None,
    }


def _latest_promoted_case(observation: dict[str, Any]) -> dict[str, Any]:
    for row in observation.get("promotions") or []:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id") or "").strip()
        if case_id:
            return {
                "case_id": case_id,
                "ticker": row.get("ticker"),
                "score": row.get("score"),
            }

    # If the latest 9A cycle had no promotion, keep the display truthful by
    # reading the most recent persisted opportunity candidate that was promoted.
    for candidate in _rows_by_type("opportunity_candidate", 250):
        case_id = str(candidate.get("promoted_case_id") or "").strip()
        if case_id:
            return {
                "case_id": case_id,
                "ticker": candidate.get("ticker"),
                "score": candidate.get("score"),
            }

    return {"case_id": None, "ticker": None, "score": None}


def _ticker_for_case(case_id: str, case_results: list[dict[str, Any]]) -> str | None:
    for row in case_results:
        if str(row.get("case_id") or "") == case_id:
            ticker = str(row.get("ticker") or "").strip().upper()
            if ticker:
                return ticker

    case = get_object(case_id) or {}
    candidate_id = str(case.get("source_candidate_id") or "").strip()
    if candidate_id:
        candidate = get_object(candidate_id) or {}
        ticker = str(candidate.get("ticker") or "").strip().upper()
        if ticker:
            return ticker
    return None


def _latest_deepened_case(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    event = _latest_event_case("EVIDENCE_GAP_HUNT_COMPLETE")
    if not event:
        return {
            "case_id": None,
            "ticker": None,
            "topic": None,
            "qualified": False,
            "created_at": None,
        }

    case_id = str(event.get("case_id") or "").strip()
    case = get_object(case_id) or {}
    qualification = latest_object(
        "qualification_assessment",
        case_id=case_id,
    ) or {}
    return {
        "case_id": case_id or None,
        "ticker": _ticker_for_case(case_id, case_results) if case_id else None,
        "topic": case.get("topic"),
        "qualified": qualification.get("qualified_buy_candidate") is True,
        "created_at": event.get("created_at"),
    }


def _recent_paper_orders(limit: int = 10) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in _rows_by_type("governed_paper_execution", 100):
        if (
            row.get("status") != "COMPLETE"
            or row.get("execution") != "PAPER_ORDER_CREATED"
        ):
            continue
        output.append(
            {
                "execution_id": row.get("execution_id"),
                "case_id": row.get("case_id"),
                "status": row.get("status"),
                "execution": row.get("execution"),
                "shares": row.get("shares"),
                "entry_price": row.get("entry_price"),
                "notional": row.get("notional"),
                "created_at": row.get("created_at") or row.get("_ledger_created_at"),
            }
        )
        if len(output) >= max(1, int(limit)):
            break
    return output


def _paper_funnel(case_results: list[dict[str, Any]]) -> dict[str, int]:
    stages = [str(row.get("stage") or "UNKNOWN").upper() for row in case_results]

    def count_where(*needles: str) -> int:
        return sum(1 for stage in stages if any(needle in stage for needle in needles))

    return {
        "inspected": len(case_results),
        "research_blocked_or_waiting": count_where(
            "WAITING_FOR_COMMITTEE",
            "COMMITTEE_NOT_WATCH",
            "QUALIFICATION",
            "RESEARCH_NOT_QUALIFIED",
            "DEEPENING",
        ),
        "capital_or_authorization_path": count_where(
            "CAPITAL",
            "AUTHORIZATION",
            "EXECUTION",
            "POSITION_OPENED",
        ),
        "waiting_for_regular_session": sum(
            1 for stage in stages if stage == "WAITING_FOR_REGULAR_SESSION"
        ),
        "paper_positions_opened": sum(
            1 for stage in stages if stage == "GOVERNED_PAPER_POSITION_OPENED"
        ),
        "errors_or_fail_closed": count_where("ERROR", "BLOCKED"),
    }


def build_paper_fund_operations() -> dict[str, Any]:
    """Aggregate existing governed state for the read-only command surfaces.

    This function creates no case, recommendation, authorization, or order. It
    only reads the persisted 9A/9B state and the existing governed paper
    portfolio accounting functions. Missing state remains explicit.
    """

    observation = latest_object(
        OBSERVATION_STATE_TYPE,
        case_id=OBSERVATION_CASE_ID,
    ) or {}
    paper_trading = latest_object(
        PAPER_TRADING_STATE_TYPE,
        case_id=PAPER_TRADING_CASE_ID,
    ) or {}

    portfolio = build_portfolio_state()
    performance = build_performance_history()
    case_results = [
        row
        for row in (paper_trading.get("case_results") or [])
        if isinstance(row, dict)
    ]

    observation_worker = _worker_view(
        observation,
        completed_key="last_cycle_completed_at",
        cadence_minutes=int(observation.get("cycle_minutes") or DEFAULT_CADENCE_MINUTES),
    )
    paper_worker = _worker_view(
        paper_trading,
        completed_key="cycle_completed_at",
        cadence_minutes=DEFAULT_CADENCE_MINUTES,
    )

    return {
        "generated_at": utc_now(),
        "refresh_seconds": 5,
        "portfolio": {
            **portfolio,
            "snapshot_count": performance.get("snapshot_count"),
            "cumulative_return_pct": performance.get("cumulative_return_pct"),
            "current_drawdown_pct": performance.get("current_drawdown_pct"),
            "max_drawdown_pct": performance.get("max_drawdown_pct"),
        },
        "observation": {
            **observation_worker,
            "last_scan_status": observation.get("last_scan_status"),
            "last_scan_count": observation.get("last_scan_count"),
            "last_queue_count": observation.get("last_queue_count"),
            "promoted_case_count": observation.get("promoted_case_count"),
            "snapshot_count": (observation.get("paper_portfolio") or {}).get("snapshot_count"),
            "latest_promoted_case": _latest_promoted_case(observation),
        },
        "paper_trading": {
            **paper_worker,
            "paper_execution_window_open": paper_trading.get("paper_execution_window_open") is True,
            "case_count_inspected": paper_trading.get("case_count_inspected"),
            "gap_hunts_run": paper_trading.get("gap_hunts_run"),
            "paper_executions_created": paper_trading.get("paper_executions_created"),
            "cycle_duration_seconds": paper_trading.get("cycle_duration_seconds"),
            "funnel": _paper_funnel(case_results),
            "case_results": case_results,
        },
        "latest_deepened_case": _latest_deepened_case(case_results),
        "recent_paper_orders": _recent_paper_orders(),
        "safety": {
            "paper_mode": True,
            "broker_connected": False,
            "live_capital_locked": True,
            "committee_override": False,
            "risk_override": False,
            "capital_override": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
        "authority": {
            "read_only_surface": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
