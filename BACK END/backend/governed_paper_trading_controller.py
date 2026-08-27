from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

import ledger
from ledger import get_object, latest_object, record_event, record_object, utc_now


POLICY_VERSION = "batch9b-governed-paper-trading-v1"
OPERATIONS_CASE_ID = "paper_trading_operations"
LATEST_STATE_ID = "governed_paper_trading_state_v1"
LATEST_STATE_TYPE = "governed_paper_trading_state"

MAX_CASES_PER_CYCLE = 20
MAX_GAP_HUNTS_PER_CYCLE = 1
MAX_PAPER_EXECUTIONS_PER_CYCLE = 1
GAP_RETRY_MINUTES = 240


def _progress_default(message: str) -> None:
    print(message, flush=True)


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


def market_phase(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    eastern = now.astimezone(ZoneInfo("America/New_York"))
    if eastern.weekday() >= 5:
        return "WEEKEND"
    minute = eastern.hour * 60 + eastern.minute
    if 570 <= minute < 960:
        return "REGULAR_SESSION"
    if 240 <= minute < 570:
        return "PRE_MARKET"
    if 960 <= minute < 1200:
        return "AFTER_HOURS"
    return "OVERNIGHT"


def paper_execution_window_open(now: datetime | None = None) -> bool:
    """
    Batch 9B v1 only creates paper entries during the regular U.S. equity
    clock window. Provider freshness and the existing authorization price
    window still fail closed if the market is actually closed or data is stale.
    """
    return market_phase(now) == "REGULAR_SESSION"


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


def _latest_event_time(case_id: str, event_type: str) -> datetime | None:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT created_at
            FROM audit_events
            WHERE case_id = ? AND event_type = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (case_id, event_type),
        ).fetchone()
    finally:
        connection.close()
    return _parse_time(row["created_at"]) if row else None


def _gap_retry_due(case_id: str, now: datetime) -> bool:
    last = _latest_event_time(case_id, "EVIDENCE_GAP_HUNT_COMPLETE")
    if last is None:
        return True
    return (now - last).total_seconds() >= GAP_RETRY_MINUTES * 60


def _safe_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail is not None:
        try:
            return f"{type(exc).__name__}: {json.dumps(detail, default=str)}"
        except Exception:
            return f"{type(exc).__name__}: {detail}"
    return f"{type(exc).__name__}: {exc}"


def _ticker_for_case(case_id: str) -> str | None:
    try:
        from factory_genericization import resolve_case_profile

        profile = resolve_case_profile(case_id)
        ticker = str(profile.get("ticker") or "").strip().upper()
        return ticker or None
    except Exception:
        return None


def _existing_position(portfolio: dict[str, Any], ticker: str) -> dict[str, Any] | None:
    wanted = str(ticker or "").strip().upper()
    for row in portfolio.get("positions") or []:
        if str(row.get("ticker") or "").strip().upper() == wanted:
            return row
    return None


def cash_guard(
    *,
    available_cash: float,
    authorized_max_notional: float,
) -> dict[str, Any]:
    cash = max(0.0, float(available_cash or 0.0))
    max_notional = max(0.0, float(authorized_max_notional or 0.0))
    passed = max_notional > 0 and max_notional <= cash + 0.005
    return {
        "passed": passed,
        "available_cash": round(cash, 2),
        "authorized_max_notional": round(max_notional, 2),
        "remaining_cash_floor": round(cash - max_notional, 2),
    }


def _case_sort_key(case: dict[str, Any]) -> tuple[int, float, float, str]:
    case_id = str(case.get("case_id") or "")
    qualification = latest_object("qualification_assessment", case_id=case_id) or {}
    committee = latest_object("committee_decision", case_id=case_id) or {}
    qualified = 1 if qualification.get("qualified_buy_candidate") is True else 0
    confidence = float(committee.get("confidence") or 0.0)
    opportunity_score = float(case.get("opportunity_score") or 0.0)
    created = str(case.get("_ledger_created_at") or "")
    return (qualified, confidence, opportunity_score, created)


def governed_case_queue(limit: int = MAX_CASES_PER_CYCLE) -> list[dict[str, Any]]:
    rows = _rows_by_type("case", max(limit * 3, limit))
    latest_by_case: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "").strip()
        if not case_id.startswith("case_"):
            continue
        latest_by_case.setdefault(case_id, row)
    ranked = sorted(latest_by_case.values(), key=_case_sort_key, reverse=True)
    return ranked[: max(1, min(int(limit), MAX_CASES_PER_CYCLE))]


def _already_governed_executed(case_id: str) -> dict[str, Any] | None:
    execution = latest_object("governed_paper_execution", case_id=case_id) or {}
    if (
        execution.get("status") == "COMPLETE"
        and execution.get("execution") == "PAPER_ORDER_CREATED"
    ):
        return execution
    return None


def _case_row(
    *,
    case_id: str,
    ticker: str | None,
    stage: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "ticker": ticker,
        "stage": stage,
        **extra,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "broker_connected": False,
    }


def run_governed_paper_trading_cycle(
    *,
    allow_deepening: bool = True,
    allow_paper_execution: bool = True,
    now: datetime | None = None,
    progress: Callable[[str], None] = _progress_default,
) -> dict[str, Any]:
    """
    Advance governed cases toward the existing paper-execution bridge.

    This controller never invents qualification, Risk, Capital, sizing, or
    authorization state. It can only invoke the already-governed modules and
    consumes at most one valid paper authorization per cycle.
    """
    from paper_portfolio_core import (
        build_performance_history,
        build_portfolio_state,
        reconcile_governed_executions,
        record_live_portfolio_snapshot,
    )

    started = now or datetime.now(timezone.utc)
    phase = market_phase(started)
    execution_window = allow_paper_execution and paper_execution_window_open(started)

    progress(
        f"=== IIOS BATCH 9B PAPER-TRADING CYCLE START · phase={phase} · "
        f"paper_execution_window={'OPEN' if execution_window else 'CLOSED'} ==="
    )

    portfolio_start = build_portfolio_state()
    progress(
        "[PORTFOLIO] "
        f"NAV={portfolio_start.get('nav')} cash={portfolio_start.get('cash')} "
        f"positions={portfolio_start.get('position_count')}"
    )

    queue = governed_case_queue()
    progress(f"[QUEUE] Inspecting {len(queue)} governed cases")

    results: list[dict[str, Any]] = []
    gap_hunts = 0
    paper_executions = 0

    for case in queue:
        case_id = str(case.get("case_id") or "")
        ticker = _ticker_for_case(case_id)
        if not ticker:
            results.append(
                _case_row(case_id=case_id, ticker=None, stage="BLOCKED_TICKER_UNRESOLVED")
            )
            continue

        prior_execution = _already_governed_executed(case_id)
        if prior_execution:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="ALREADY_PAPER_EXECUTED",
                    execution_id=prior_execution.get("execution_id"),
                )
            )
            continue

        portfolio_now = build_portfolio_state()
        existing = _existing_position(portfolio_now, ticker)
        if existing:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="BLOCKED_DUPLICATE_TICKER_POSITION",
                    existing_position={
                        "quantity": existing.get("quantity"),
                        "market_value": existing.get("market_value"),
                    },
                )
            )
            continue

        committee = latest_object("committee_decision", case_id=case_id) or {}
        if not committee:
            results.append(
                _case_row(case_id=case_id, ticker=ticker, stage="WAITING_FOR_COMMITTEE")
            )
            continue

        if committee.get("disposition") != "WATCH":
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="COMMITTEE_NOT_WATCH",
                    committee_disposition=committee.get("disposition"),
                    committee_confidence=committee.get("confidence"),
                )
            )
            continue

        qualification = latest_object("qualification_assessment", case_id=case_id) or {}

        if qualification.get("qualified_buy_candidate") is not True:
            if (
                allow_deepening
                and gap_hunts < MAX_GAP_HUNTS_PER_CYCLE
                and _gap_retry_due(case_id, started)
            ):
                progress(
                    f"[DEEPEN] {ticker} {case_id} — running governed Evidence Gap Hunt"
                )
                try:
                    from evidence_gap_hunter import run_gap_hunt

                    hunt = run_gap_hunt(case_id)
                    gap_hunts += 1
                    qualification = latest_object(
                        "qualification_assessment", case_id=case_id
                    ) or {}
                    progress(
                        f"[DEEPEN] {ticker} complete · "
                        f"qualified={qualification.get('qualified_buy_candidate') is True}"
                    )
                except Exception as exc:
                    gap_hunts += 1
                    results.append(
                        _case_row(
                            case_id=case_id,
                            ticker=ticker,
                            stage="DEEPENING_ERROR",
                            error=_safe_error(exc),
                        )
                    )
                    continue
            else:
                results.append(
                    _case_row(
                        case_id=case_id,
                        ticker=ticker,
                        stage=(
                            "RESEARCH_NOT_QUALIFIED"
                            if qualification
                            else "WAITING_FOR_QUALIFICATION"
                        ),
                        unmet_requirements=qualification.get("unmet_requirements") or [],
                        gap_retry_due=_gap_retry_due(case_id, started),
                    )
                )
                continue

        if qualification.get("qualified_buy_candidate") is not True:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="RESEARCH_NOT_QUALIFIED",
                    unmet_requirements=qualification.get("unmet_requirements") or [],
                )
            )
            continue

        if not execution_window:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage=(
                        "DRY_RUN_EXECUTION_DISABLED"
                        if not allow_paper_execution
                        else "WAITING_FOR_REGULAR_SESSION"
                    ),
                    qualification_id=qualification.get("qualification_assessment_id"),
                )
            )
            continue

        if paper_executions >= MAX_PAPER_EXECUTIONS_PER_CYCLE:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="CYCLE_EXECUTION_LIMIT_REACHED",
                )
            )
            continue

        progress(f"[CAPITAL] {ticker} — refreshing governed Capital / sizing state")
        try:
            from paper_capital_api import paper_capital_status
            from paper_authorization_api import _current_state, prepare_paper_authorization

            capital_view = paper_capital_status(case_id)
            current_state = _current_state(case_id, refresh_market=True)
        except Exception as exc:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="CAPITAL_STATE_BLOCKED",
                    error=_safe_error(exc),
                )
            )
            continue

        readiness = current_state.get("readiness") or {}
        sizing = current_state.get("sizing") or {}
        capital = current_state.get("capital") or {}

        if readiness.get("ready") is not True:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="PAPER_AUTHORIZATION_NOT_READY",
                    capital_stage=capital_view.get("stage"),
                    capital_decision=capital.get("decision"),
                    sizing_decision=sizing.get("decision"),
                    failed_checks=readiness.get("failed_checks") or [],
                )
            )
            continue

        progress(f"[AUTH] {ticker} — preparing single-use governed paper authorization")
        try:
            authorization = prepare_paper_authorization(case_id)
        except Exception as exc:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="PAPER_AUTHORIZATION_BLOCKED",
                    error=_safe_error(exc),
                )
            )
            continue

        auth_id = str(authorization.get("paper_authorization_id") or "").strip()
        auth_object = get_object(auth_id) if auth_id else None
        if not auth_id or not auth_object:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="PAPER_AUTHORIZATION_MISSING",
                )
            )
            continue

        # Re-read portfolio after authorization preparation. This makes the cash
        # and duplicate-position guard contemporaneous with submission.
        portfolio_pre_submit = build_portfolio_state()
        existing_pre_submit = _existing_position(portfolio_pre_submit, ticker)
        if existing_pre_submit:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="BLOCKED_DUPLICATE_TICKER_POSITION",
                    paper_authorization_id=auth_id,
                )
            )
            continue

        guard = cash_guard(
            available_cash=float(portfolio_pre_submit.get("cash") or 0.0),
            authorized_max_notional=float(auth_object.get("authorized_max_notional") or 0.0),
        )
        if not guard["passed"]:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="BLOCKED_INSUFFICIENT_PAPER_CASH",
                    paper_authorization_id=auth_id,
                    cash_guard=guard,
                )
            )
            continue

        progress(
            f"[PAPER ORDER] {ticker} — submitting through existing governed execution bridge"
        )
        try:
            from governed_paper_execution_api import submit_governed_paper_order

            execution = submit_governed_paper_order(
                case_id,
                {"paper_authorization_id": auth_id},
            )
        except Exception as exc:
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="PAPER_EXECUTION_BLOCKED",
                    paper_authorization_id=auth_id,
                    error=_safe_error(exc),
                )
            )
            continue

        if (
            execution.get("status") != "COMPLETE"
            or execution.get("execution") != "PAPER_ORDER_CREATED"
        ):
            results.append(
                _case_row(
                    case_id=case_id,
                    ticker=ticker,
                    stage="PAPER_EXECUTION_BLOCKED",
                    paper_authorization_id=auth_id,
                    execution=execution,
                )
            )
            continue

        reconciliation = reconcile_governed_executions()
        snapshot = record_live_portfolio_snapshot()
        performance = build_performance_history()
        paper_executions += 1

        progress(
            f"[PAPER ORDER] {ticker} COMPLETE · shares={execution.get('shares')} "
            f"notional={execution.get('notional')} · NAV={snapshot.get('nav')}"
        )

        results.append(
            _case_row(
                case_id=case_id,
                ticker=ticker,
                stage="GOVERNED_PAPER_POSITION_OPENED",
                paper_authorization_id=auth_id,
                execution_id=execution.get("execution_id"),
                shares=execution.get("shares"),
                entry_price=execution.get("entry_price"),
                notional=execution.get("notional"),
                cash_guard=guard,
                reconciliation=reconciliation,
                portfolio_snapshot_id=snapshot.get("paper_portfolio_snapshot_id"),
                portfolio_nav=snapshot.get("nav"),
                portfolio_cash=snapshot.get("cash"),
                portfolio_position_count=snapshot.get("position_count"),
                portfolio_snapshot_count=performance.get("snapshot_count"),
            )
        )

    completed = datetime.now(timezone.utc)
    portfolio_end = build_portfolio_state()

    cycle_id = f"paper_trading_cycle_{uuid4().hex}"
    state = {
        "governed_paper_trading_state_id": LATEST_STATE_ID,
        "latest_cycle_id": cycle_id,
        "policy_version": POLICY_VERSION,
        "mode": "GOVERNED_PAPER_TRADING",
        "market_phase": phase,
        "paper_execution_window_open": execution_window,
        "allow_deepening": bool(allow_deepening),
        "allow_paper_execution": bool(allow_paper_execution),
        "case_count_inspected": len(queue),
        "gap_hunts_run": gap_hunts,
        "paper_executions_created": paper_executions,
        "case_results": results,
        "portfolio_before": {
            "nav": portfolio_start.get("nav"),
            "cash": portfolio_start.get("cash"),
            "positions": portfolio_start.get("position_count"),
        },
        "portfolio_after": {
            "nav": portfolio_end.get("nav"),
            "cash": portfolio_end.get("cash"),
            "positions": portfolio_end.get("position_count"),
        },
        "limits": {
            "max_cases_per_cycle": MAX_CASES_PER_CYCLE,
            "max_gap_hunts_per_cycle": MAX_GAP_HUNTS_PER_CYCLE,
            "max_paper_executions_per_cycle": MAX_PAPER_EXECUTIONS_PER_CYCLE,
            "gap_retry_minutes": GAP_RETRY_MINUTES,
        },
        "authority": {
            "broker_connected": False,
            "auto_live_trade_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "paper_execution_requires_governed_single_use_authorization": True,
        },
        "paper_mode": True,
        "cycle_started_at": started.isoformat(),
        "cycle_completed_at": completed.isoformat(),
        "cycle_duration_seconds": round((completed - started).total_seconds(), 2),
        "updated_at": utc_now(),
    }

    record_object(
        cycle_id,
        "governed_paper_trading_cycle",
        OPERATIONS_CASE_ID,
        {**state, "governed_paper_trading_cycle_id": cycle_id},
        topic="IIOS Governed Paper Trading",
    )
    record_object(
        LATEST_STATE_ID,
        LATEST_STATE_TYPE,
        OPERATIONS_CASE_ID,
        state,
        topic="IIOS Governed Paper Trading",
    )
    record_event(
        OPERATIONS_CASE_ID,
        "PAPER_TRADING_CYCLE_COMPLETE",
        entity_id=cycle_id,
        payload={
            "market_phase": phase,
            "case_count_inspected": len(queue),
            "gap_hunts_run": gap_hunts,
            "paper_executions_created": paper_executions,
            "nav": portfolio_end.get("nav"),
            "cash": portfolio_end.get("cash"),
            "positions": portfolio_end.get("position_count"),
            "broker_connected": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )

    progress(
        "=== 9B CYCLE COMPLETE · "
        f"deepened={gap_hunts} paper_orders={paper_executions} "
        f"NAV={portfolio_end.get('nav')} cash={portfolio_end.get('cash')} "
        f"positions={portfolio_end.get('position_count')} ==="
    )

    return state
