from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

import ledger
from governed_paper_execution_bridge import (
    create_governed_paper_order,
)
from ledger import (
    latest_object,
    paper_authorization_consumed,
    utc_now,
)
from paper_authorization_api import (
    _current_state,
)
from paper_portfolio_core import (
    build_performance_history,
    build_portfolio_state,
)


router = APIRouter()

OBSERVATION_CASE_ID = "observation_operations"
PAPER_TRADING_CASE_ID = "paper_trading_operations"
OBSERVATION_STATE_TYPE = "observation_operations_state"
PAPER_TRADING_STATE_TYPE = "governed_paper_trading_state"
DEFAULT_WORKER_CADENCE_MINUTES = 15


def _authorization_id(
    payload: dict[str, Any],
) -> str:
    authorization_id = str(
        payload.get(
            "paper_authorization_id"
        )
        or ""
    ).strip()

    if not authorization_id:
        raise ValueError(
            "paper_authorization_id is required"
        )

    if not authorization_id.startswith(
        "paper_auth_"
    ):
        raise ValueError(
            "paper_authorization_id must be "
            "a governed paper_auth_* token"
        )

    return authorization_id


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rows_by_type(
    object_type: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(
        ledger.DB_PATH,
        timeout=30,
    )
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
            (
                object_type,
                max(1, min(int(limit), 100)),
            ),
        ).fetchall()
    finally:
        connection.close()

    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            output.append(
                {
                    **payload,
                    "_ledger_created_at": row["created_at"],
                }
            )
    return output


def _worker_summary(
    *,
    worker: str,
    state: dict[str, Any],
    completed_key: str,
    cadence_minutes: int,
) -> dict[str, Any]:
    cadence = max(1, int(cadence_minutes or 0))
    completed = _parse_time(state.get(completed_key))
    now = datetime.now(timezone.utc)

    if completed is None:
        return {
            "worker": worker,
            "availability": "NO_STATE",
            "cadence_minutes": cadence,
            "last_completed_at": None,
            "next_due_at": None,
            "seconds_until_next_cycle": None,
            "seconds_since_last_cycle": None,
            "cadence_state": "UNKNOWN",
        }

    next_due = completed + timedelta(minutes=cadence)
    seconds_until = int((next_due - now).total_seconds())
    seconds_since = max(
        0,
        int((now - completed).total_seconds()),
    )
    grace_seconds = 5 * 60
    cadence_state = (
        "ON_CADENCE"
        if now <= next_due + timedelta(seconds=grace_seconds)
        else "OVERDUE"
    )

    return {
        "worker": worker,
        "availability": "AVAILABLE",
        "cadence_minutes": cadence,
        "last_completed_at": completed.isoformat(),
        "next_due_at": next_due.isoformat(),
        "seconds_until_next_cycle": max(0, seconds_until),
        "seconds_since_last_cycle": seconds_since,
        "cadence_state": cadence_state,
    }


def _paper_trading_funnel(
    state: dict[str, Any],
) -> dict[str, Any]:
    rows = state.get("case_results")
    rows = rows if isinstance(rows, list) else []

    research_blocked = 0
    capital_path = 0
    waiting_session = 0
    opened = 0
    errors = 0

    research_stages = {
        "MISSING_COMMITTEE",
        "COMMITTEE_NOT_WATCH",
        "WAITING_FOR_QUALIFICATION",
        "RESEARCH_NOT_QUALIFIED",
    }
    error_stages = {
        "DEEPENING_ERROR",
        "CAPITAL_STATE_BLOCKED",
        "PAPER_AUTHORIZATION_BLOCKED",
        "PAPER_EXECUTION_BLOCKED",
    }

    for row in rows:
        if not isinstance(row, dict):
            continue
        stage = str(row.get("stage") or "UNKNOWN").upper()
        if stage == "GOVERNED_PAPER_POSITION_OPENED":
            opened += 1
        elif stage == "WAITING_FOR_REGULAR_SESSION":
            waiting_session += 1
            capital_path += 1
        elif stage in error_stages:
            errors += 1
            capital_path += 1
        elif stage in research_stages:
            research_blocked += 1
        elif (
            stage.startswith("PAPER_")
            or stage.startswith("CAPITAL_")
            or stage.startswith("BLOCKED_")
            or stage == "CYCLE_EXECUTION_LIMIT_REACHED"
        ):
            capital_path += 1

    return {
        "inspected": len(rows),
        "research_blocked_or_waiting": research_blocked,
        "capital_or_authorization_path": capital_path,
        "waiting_for_regular_session": waiting_session,
        "paper_positions_opened": opened,
        "errors_or_fail_closed": errors,
    }


def _clean_case_results(
    state: dict[str, Any],
    limit: int = 12,
) -> list[dict[str, Any]]:
    rows = state.get("case_results")
    rows = rows if isinstance(rows, list) else []
    output: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        output.append(
            {
                "case_id": row.get("case_id"),
                "ticker": row.get("ticker"),
                "stage": row.get("stage") or "UNKNOWN",
                "committee_disposition": row.get(
                    "committee_disposition"
                ),
                "committee_confidence": row.get(
                    "committee_confidence"
                ),
                "capital_stage": row.get("capital_stage"),
                "capital_decision": row.get(
                    "capital_decision"
                ),
                "sizing_decision": row.get(
                    "sizing_decision"
                ),
                "failed_checks": row.get(
                    "failed_checks"
                )
                or [],
                "unmet_requirements": row.get(
                    "unmet_requirements"
                )
                or [],
                "execution_id": row.get("execution_id"),
                "shares": row.get("shares"),
                "entry_price": row.get("entry_price"),
                "notional": row.get("notional"),
            }
        )
    return output


def build_paper_fund_operations() -> dict[str, Any]:
    portfolio = build_portfolio_state()
    performance = build_performance_history()

    observation = latest_object(
        OBSERVATION_STATE_TYPE,
        case_id=OBSERVATION_CASE_ID,
    ) or {}
    paper_trading = latest_object(
        PAPER_TRADING_STATE_TYPE,
        case_id=PAPER_TRADING_CASE_ID,
    ) or {}

    observation_worker = _worker_summary(
        worker="BATCH_9A_OBSERVATION",
        state=observation,
        completed_key="last_cycle_completed_at",
        cadence_minutes=int(
            observation.get("cycle_minutes")
            or DEFAULT_WORKER_CADENCE_MINUTES
        ),
    )
    paper_trading_worker = _worker_summary(
        worker="BATCH_9B_PAPER_TRADING",
        state=paper_trading,
        completed_key="cycle_completed_at",
        cadence_minutes=DEFAULT_WORKER_CADENCE_MINUTES,
    )

    recent_orders = [
        {
            "execution_id": row.get("execution_id"),
            "case_id": row.get("case_id"),
            "status": row.get("status"),
            "execution": row.get("execution"),
            "shares": row.get("shares"),
            "entry_price": row.get("entry_price"),
            "notional": row.get("notional"),
            "created_at": row.get("created_at")
            or row.get("_ledger_created_at"),
        }
        for row in _rows_by_type(
            "governed_paper_execution",
            10,
        )
        if row.get("execution") == "PAPER_ORDER_CREATED"
    ]

    latest_gap_hunt = (
        _rows_by_type("gap_hunt", 1) or [{}]
    )[0]
    gap_plan = latest_gap_hunt.get("plan")
    gap_plan = gap_plan if isinstance(gap_plan, dict) else {}

    observation_promotions = observation.get("promotions")
    observation_promotions = (
        observation_promotions
        if isinstance(observation_promotions, list)
        else []
    )

    latest_promotion = (
        observation_promotions[0]
        if observation_promotions
        and isinstance(observation_promotions[0], dict)
        else {}
    )

    portfolio_view = {
        "starting_cash": portfolio.get("starting_cash"),
        "nav": portfolio.get("nav"),
        "cash": portfolio.get("cash"),
        "market_value": portfolio.get("market_value"),
        "realized_pnl": portfolio.get("realized_pnl"),
        "unrealized_pnl": portfolio.get("unrealized_pnl"),
        "total_pnl": portfolio.get("total_pnl"),
        "gross_exposure": portfolio.get("gross_exposure"),
        "position_count": portfolio.get("position_count"),
        "transaction_count": portfolio.get("transaction_count"),
        "positions": portfolio.get("positions") or [],
        "snapshot_count": performance.get("snapshot_count"),
        "cumulative_return_pct": performance.get(
            "cumulative_return_pct"
        ),
        "current_drawdown_pct": performance.get(
            "current_drawdown_pct"
        ),
        "max_drawdown_pct": performance.get(
            "max_drawdown_pct"
        ),
    }

    return {
        "name": "IIOS Paper Fund Operations",
        "generated_at": utc_now(),
        "refresh_seconds": 5,
        "portfolio": portfolio_view,
        "observation": {
            **observation_worker,
            "market_phase": observation.get("market_phase"),
            "last_scan_status": observation.get(
                "last_scan_status"
            ),
            "last_scan_count": observation.get(
                "last_scan_count"
            ),
            "last_queue_count": observation.get(
                "last_queue_count"
            ),
            "promoted_case_count": observation.get(
                "promoted_case_count"
            ),
            "snapshot_count": (
                observation.get("paper_portfolio")
                or {}
            ).get("snapshot_count"),
            "latest_promoted_case": {
                "case_id": latest_promotion.get("case_id"),
                "ticker": latest_promotion.get("ticker"),
                "score": latest_promotion.get("score"),
            },
        },
        "paper_trading": {
            **paper_trading_worker,
            "market_phase": paper_trading.get("market_phase"),
            "paper_execution_window_open": (
                paper_trading.get(
                    "paper_execution_window_open"
                )
                is True
            ),
            "case_count_inspected": paper_trading.get(
                "case_count_inspected"
            ),
            "gap_hunts_run": paper_trading.get(
                "gap_hunts_run"
            ),
            "paper_executions_created": paper_trading.get(
                "paper_executions_created"
            ),
            "cycle_duration_seconds": paper_trading.get(
                "cycle_duration_seconds"
            ),
            "funnel": _paper_trading_funnel(
                paper_trading
            ),
            "case_results": _clean_case_results(
                paper_trading
            ),
        },
        "latest_deepened_case": {
            "case_id": latest_gap_hunt.get("case_id"),
            "ticker": gap_plan.get("ticker"),
            "topic": latest_gap_hunt.get("topic"),
            "qualified": (
                (
                    latest_gap_hunt.get("qualification")
                    or {}
                ).get("qualified_buy_candidate")
                is True
            ),
            "created_at": latest_gap_hunt.get(
                "_ledger_created_at"
            ),
        },
        "recent_paper_orders": recent_orders,
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
        "read_only": True,
        "unknown_state_semantics": True,
    }


@router.get(
    "/paper-fund/operations"
)
def paper_fund_operations():
    """
    Read-only operating feed for the browser Paper Fund board.

    It aggregates existing governed state only. It cannot deepen a case,
    create an authorization, submit a paper order, connect a broker, or
    change live-capital authority.
    """
    return build_paper_fund_operations()


@router.get(
    "/governed-paper-execution/{case_id}/status"
)
def governed_paper_execution_status(
    case_id: str,
):
    latest_execution = latest_object(
        "governed_paper_execution",
        case_id=case_id,
    ) or {}

    latest_authorization = latest_object(
        "paper_authorization",
        case_id=case_id,
    ) or {}

    auth_id = latest_authorization.get(
        "paper_authorization_id"
    )

    consumed = (
        paper_authorization_consumed(
            auth_id
        )
        if auth_id
        else None
    )

    return {
        "case_id":
            case_id,

        "latest_authorization": {
            "paper_authorization_id":
                auth_id,

            "consumed":
                consumed,

            "authorized_shares":
                latest_authorization.get(
                    "authorized_shares"
                ),

            "authorized_notional":
                latest_authorization.get(
                    "authorized_notional"
                ),
        },

        "latest_paper_execution": {
            "execution_id":
                latest_execution.get(
                    "execution_id"
                ),

            "status":
                latest_execution.get(
                    "status"
                ),

            "execution":
                latest_execution.get(
                    "execution"
                ),

            "shares":
                latest_execution.get(
                    "shares"
                ),

            "notional":
                latest_execution.get(
                    "notional"
                ),

            "entry_price":
                latest_execution.get(
                    "entry_price"
                ),
        },

        "paper_mode":
            True,

        "live_execution":
            False,

        "trade_execution_permission":
            False,
    }


@router.post(
    "/governed-paper-execution/{case_id}/submit"
)
def submit_governed_paper_order(
    case_id: str,
    payload: dict[str, Any],
):
    """
    Final API bridge into PAPER execution only.

    This endpoint NEVER:
      - creates an authorization,
      - changes sizing,
      - connects to a broker,
      - submits live capital.
    """

    try:
        authorization_id = (
            _authorization_id(
                payload
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    # Submission always refreshes current market,
    # Capital and sizing state before token verification.
    state = _current_state(
        case_id,
        refresh_market=True,
    )

    result = create_governed_paper_order(
        case_id=case_id,

        authorization_id=
            authorization_id,

        qualification=state[
            "qualification"
        ],

        thesis_status=state[
            "thesis"
        ],

        capital_gate=state[
            "capital"
        ],

        sizing=state[
            "sizing"
        ],
    )

    if (
        result.get("execution")
        != "PAPER_ORDER_CREATED"
    ):
        raise HTTPException(
            status_code=409,
            detail=result,
        )

    return result
