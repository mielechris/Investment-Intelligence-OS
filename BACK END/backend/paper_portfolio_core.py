from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body

import ledger
from ledger import (
    get_object,
    latest_object,
    record_event,
    record_object,
    utc_now,
)


router = APIRouter()

POLICY_VERSION = "paper-portfolio-core-v1"
PORTFOLIO_CASE_ID = "paper_portfolio"
ACCOUNT_ID = "paper_portfolio_default"
STARTING_CASH = 10_000.00


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rows_by_type(object_type: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    try:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM ledger_objects
            WHERE object_type = ?
            ORDER BY created_at ASC
            """,
            (object_type,),
        ).fetchall()
    finally:
        connection.close()

    return [json.loads(row[0]) for row in rows]


def ensure_account() -> dict[str, Any]:
    existing = get_object(ACCOUNT_ID)
    if existing:
        return existing

    account = {
        "paper_portfolio_account_id": ACCOUNT_ID,
        "policy_version": POLICY_VERSION,
        "starting_cash": STARTING_CASH,
        "base_currency": "USD",
        "account_type": "GOVERNED_PAPER_PORTFOLIO",
        "created_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }

    record_object(
        ACCOUNT_ID,
        "paper_portfolio_account",
        PORTFOLIO_CASE_ID,
        account,
        topic="PAPER_PORTFOLIO",
    )

    record_event(
        PORTFOLIO_CASE_ID,
        "PAPER_PORTFOLIO_CREATED",
        entity_id=ACCOUNT_ID,
        payload={
            "starting_cash": STARTING_CASH,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )

    return account


def _ticker_for_case(case_id: str) -> str | None:
    profile = latest_object(
        "monitor_profile",
        case_id=case_id,
    ) or {}

    ticker = str(profile.get("ticker") or "").strip().upper()
    if ticker.endswith(".US"):
        ticker = ticker[:-3]
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


def reconcile_governed_executions() -> dict[str, Any]:
    ensure_account()

    executions = _rows_by_type("governed_paper_execution")

    created = 0
    existing = 0
    skipped: list[dict[str, Any]] = []

    for execution in executions:
        if (
            execution.get("status") != "COMPLETE"
            or execution.get("execution") != "PAPER_ORDER_CREATED"
        ):
            continue

        execution_id = str(execution.get("execution_id") or "").strip()
        case_id = str(execution.get("case_id") or "").strip()

        if not execution_id or not case_id:
            continue

        transaction_id = f"portfolio_txn_{execution_id}"

        if get_object(transaction_id):
            existing += 1
            continue

        ticker = _ticker_for_case(case_id)

        if not ticker:
            skipped.append(
                {
                    "execution_id": execution_id,
                    "case_id": case_id,
                    "reason": "TICKER_NOT_RESOLVED",
                }
            )
            continue

        quantity = int(execution.get("shares") or 0)
        price = _safe_float(execution.get("entry_price"))
        notional = _safe_float(execution.get("notional"))

        if quantity <= 0 or price <= 0 or notional <= 0:
            skipped.append(
                {
                    "execution_id": execution_id,
                    "case_id": case_id,
                    "ticker": ticker,
                    "reason": "INVALID_EXECUTION_ECONOMICS",
                }
            )
            continue

        transaction = {
            "paper_portfolio_transaction_id": transaction_id,
            "paper_portfolio_account_id": ACCOUNT_ID,
            "source_execution_id": execution_id,
            "source_case_id": case_id,
            "paper_authorization_id": execution.get(
                "paper_authorization_id"
            ),
            "ticker": ticker,
            "side": "BUY",
            "direction": "LONG",
            "quantity": quantity,
            "price": round(price, 6),
            "notional": round(notional, 2),
            "cash_delta": round(-notional, 2),
            "realized_pnl_delta": 0.0,
            "transaction_source": "GOVERNED_PAPER_EXECUTION_ONLY",
            "created_at": str(execution.get("created_at") or utc_now()),
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

        record_object(
            transaction_id,
            "paper_portfolio_transaction",
            PORTFOLIO_CASE_ID,
            transaction,
            parent_id=execution_id,
            topic=ticker,
        )

        record_event(
            PORTFOLIO_CASE_ID,
            "PAPER_PORTFOLIO_TRANSACTION_INGESTED",
            entity_id=transaction_id,
            payload={
                "source_execution_id": execution_id,
                "ticker": ticker,
                "side": "BUY",
                "quantity": quantity,
                "notional": notional,
                "trade_execution_permission": False,
            },
        )

        created += 1

    return {
        "status": "COMPLETE",
        "created_transactions": created,
        "existing_transactions": existing,
        "skipped": skipped,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _transactions() -> list[dict[str, Any]]:
    return [
        row
        for row in _rows_by_type("paper_portfolio_transaction")
        if row.get("paper_portfolio_account_id") == ACCOUNT_ID
    ]


def build_portfolio_state(
    marks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    account = ensure_account()
    reconciliation = reconcile_governed_executions()
    marks = marks if isinstance(marks, dict) else {}

    cash = _safe_float(account.get("starting_cash"), STARTING_CASH)
    realized_pnl = 0.0

    positions: dict[str, dict[str, Any]] = {}

    for transaction in _transactions():
        ticker = str(transaction.get("ticker") or "").upper()
        side = str(transaction.get("side") or "").upper()

        if not ticker:
            continue

        position = positions.setdefault(
            ticker,
            {
                "ticker": ticker,
                "quantity": 0,
                "cost_basis": 0.0,
            },
        )

        quantity = int(transaction.get("quantity") or 0)
        notional = _safe_float(transaction.get("notional"))
        cash_delta = _safe_float(transaction.get("cash_delta"))

        cash += cash_delta
        realized_pnl += _safe_float(
            transaction.get("realized_pnl_delta")
        )

        if side == "BUY":
            position["quantity"] += quantity
            position["cost_basis"] += notional

    rows: list[dict[str, Any]] = []
    total_market_value = 0.0
    total_unrealized = 0.0

    for ticker, position in sorted(positions.items()):
        quantity = int(position["quantity"])
        cost_basis = _safe_float(position["cost_basis"])

        if quantity <= 0:
            continue

        average_cost = cost_basis / quantity

        supplied_mark = _safe_float(marks.get(ticker), 0.0)

        if supplied_mark > 0:
            mark_price = supplied_mark
            mark_source = "SUPPLIED_MARK"
        else:
            mark_price = average_cost
            mark_source = "AVERAGE_COST_FALLBACK"

        market_value = quantity * mark_price
        unrealized = market_value - cost_basis

        total_market_value += market_value
        total_unrealized += unrealized

        rows.append(
            {
                "ticker": ticker,
                "direction": "LONG",
                "quantity": quantity,
                "average_cost": round(average_cost, 6),
                "cost_basis": round(cost_basis, 2),
                "mark_price": round(mark_price, 6),
                "mark_source": mark_source,
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized, 2),
                "unrealized_return_pct": (
                    round((unrealized / cost_basis) * 100.0, 4)
                    if cost_basis > 0
                    else None
                ),
            }
        )

    nav = cash + total_market_value
    gross_exposure = total_market_value

    flags: list[str] = []

    if cash < 0:
        flags.append("NEGATIVE_CASH")

    if not rows:
        flags.append("NO_OPEN_POSITIONS")

    return {
        "policy_version": POLICY_VERSION,
        "paper_portfolio_account_id": ACCOUNT_ID,
        "starting_cash": round(
            _safe_float(account.get("starting_cash")),
            2,
        ),
        "cash": round(cash, 2),
        "market_value": round(total_market_value, 2),
        "nav": round(nav, 2),
        "equity": round(nav, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "total_pnl": round(
            realized_pnl + total_unrealized,
            2,
        ),
        "gross_exposure": round(gross_exposure, 2),
        "net_exposure": round(total_market_value, 2),
        "position_count": len(rows),
        "transaction_count": len(_transactions()),
        "positions": rows,
        "portfolio_flags": flags,
        "reconciliation": reconciliation,
        "accounting_scope": "GOVERNED_PAPER_EXECUTIONS_ONLY",
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


def record_portfolio_snapshot(
    marks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = build_portfolio_state(marks)

    snapshot_id = f"paper_portfolio_snapshot_{uuid4().hex}"

    snapshot = {
        **state,
        "paper_portfolio_snapshot_id": snapshot_id,
        "created_at": utc_now(),
    }

    record_object(
        snapshot_id,
        "paper_portfolio_snapshot",
        PORTFOLIO_CASE_ID,
        snapshot,
        parent_id=ACCOUNT_ID,
        topic="PAPER_PORTFOLIO",
    )

    record_event(
        PORTFOLIO_CASE_ID,
        "PAPER_PORTFOLIO_SNAPSHOT_RECORDED",
        entity_id=snapshot_id,
        payload={
            "nav": snapshot["nav"],
            "cash": snapshot["cash"],
            "position_count": snapshot["position_count"],
            "trade_execution_permission": False,
        },
    )

    return snapshot


@router.get("/paper-portfolio/plan")
def paper_portfolio_plan():
    return {
        "policy_version": POLICY_VERSION,
        "starting_cash": STARTING_CASH,
        "accounting_source": "GOVERNED_PAPER_EXECUTIONS_ONLY",
        "supports": [
            "cash",
            "positions",
            "average_cost",
            "cost_basis",
            "mark_to_market",
            "realized_pnl_foundation",
            "unrealized_pnl",
            "nav",
            "equity_snapshots",
        ],
        "direct_trade_creation": False,
        "live_execution": False,
        "trade_execution_permission": False,
        "paper_mode": True,
    }


@router.post("/paper-portfolio/reconcile")
def paper_portfolio_reconcile():
    return reconcile_governed_executions()


@router.get("/paper-portfolio/status")
def paper_portfolio_status():
    return build_portfolio_state()


@router.post("/paper-portfolio/snapshot")
def paper_portfolio_snapshot(
    request: dict[str, Any] = Body(default={}),
):
    marks = request.get("marks")
    return record_portfolio_snapshot(
        marks if isinstance(marks, dict) else {}
    )


# ============================================================
# Batch 8A.2 — governed market marks + performance history
# ============================================================

from provider_hardening import fetch_market_quote


def fetch_governed_marks() -> dict[str, Any]:
    """
    Fetch marks only for positions that already exist in the governed
    paper portfolio. This function cannot create a position or order.
    """
    state = build_portfolio_state()

    marks: dict[str, float] = {}
    provenance: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for position in state.get("positions") or []:
        ticker = str(position.get("ticker") or "").strip().upper()

        if not ticker:
            continue

        quote = fetch_market_quote(ticker)
        price = quote.get("current_price")

        if quote.get("status") == "ok" and price is not None:
            marks[ticker] = float(price)

            item = (
                (quote.get("items") or [{}])[0]
                if quote.get("items")
                else {}
            )

            provenance[ticker] = {
                "provider": quote.get("provider"),
                "price": float(price),
                "timestamp": item.get("timestamp"),
                "url": item.get("url"),
            }
        else:
            errors[ticker] = str(
                quote.get("error")
                or "NO_GOVERNED_MARK_AVAILABLE"
            )

    return {
        "marks": marks,
        "provenance": provenance,
        "errors": errors,
        "position_count": len(state.get("positions") or []),
        "marked_position_count": len(marks),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def record_live_portfolio_snapshot() -> dict[str, Any]:
    mark_result = fetch_governed_marks()

    snapshot = record_portfolio_snapshot(
        mark_result["marks"]
    )

    enriched = {
        **snapshot,
        "mark_provenance": mark_result["provenance"],
        "mark_errors": mark_result["errors"],
        "mark_source_policy": "IIOS_GOVERNED_MARKET_QUOTE",
    }

    # Replace the just-recorded snapshot with the enriched form,
    # keeping the same immutable snapshot identity.
    record_object(
        enriched["paper_portfolio_snapshot_id"],
        "paper_portfolio_snapshot",
        PORTFOLIO_CASE_ID,
        enriched,
        parent_id=ACCOUNT_ID,
        topic="PAPER_PORTFOLIO",
    )

    return enriched


def portfolio_snapshot_history() -> list[dict[str, Any]]:
    return [
        row
        for row in _rows_by_type("paper_portfolio_snapshot")
        if row.get("paper_portfolio_account_id") == ACCOUNT_ID
    ]


def build_performance_history() -> dict[str, Any]:
    account = ensure_account()
    starting_cash = _safe_float(
        account.get("starting_cash"),
        STARTING_CASH,
    )

    snapshots = portfolio_snapshot_history()

    history: list[dict[str, Any]] = []
    prior_nav: float | None = None
    high_water_mark = starting_cash
    max_drawdown_pct = 0.0

    for snapshot in snapshots:
        nav = _safe_float(snapshot.get("nav"))

        if nav > high_water_mark:
            high_water_mark = nav

        cumulative_return_pct = (
            ((nav / starting_cash) - 1.0) * 100.0
            if starting_cash > 0
            else 0.0
        )

        period_return_pct = (
            ((nav / prior_nav) - 1.0) * 100.0
            if prior_nav and prior_nav > 0
            else 0.0
        )

        drawdown_pct = (
            ((nav / high_water_mark) - 1.0) * 100.0
            if high_water_mark > 0
            else 0.0
        )

        max_drawdown_pct = min(
            max_drawdown_pct,
            drawdown_pct,
        )

        history.append(
            {
                "paper_portfolio_snapshot_id":
                    snapshot.get(
                        "paper_portfolio_snapshot_id"
                    ),
                "created_at": snapshot.get("created_at"),
                "nav": round(nav, 2),
                "cash": round(
                    _safe_float(snapshot.get("cash")),
                    2,
                ),
                "market_value": round(
                    _safe_float(
                        snapshot.get("market_value")
                    ),
                    2,
                ),
                "realized_pnl": round(
                    _safe_float(
                        snapshot.get("realized_pnl")
                    ),
                    2,
                ),
                "unrealized_pnl": round(
                    _safe_float(
                        snapshot.get("unrealized_pnl")
                    ),
                    2,
                ),
                "total_pnl": round(
                    _safe_float(
                        snapshot.get("total_pnl")
                    ),
                    2,
                ),
                "cumulative_return_pct":
                    round(cumulative_return_pct, 4),
                "period_return_pct":
                    round(period_return_pct, 4),
                "high_water_mark":
                    round(high_water_mark, 2),
                "drawdown_pct":
                    round(drawdown_pct, 4),
            }
        )

        prior_nav = nav

    latest = history[-1] if history else None

    return {
        "policy_version":
            "paper-portfolio-performance-v1",
        "paper_portfolio_account_id": ACCOUNT_ID,
        "starting_nav": round(starting_cash, 2),
        "snapshot_count": len(history),
        "latest_nav":
            latest.get("nav")
            if latest
            else round(starting_cash, 2),
        "cumulative_return_pct":
            latest.get("cumulative_return_pct")
            if latest
            else 0.0,
        "high_water_mark":
            latest.get("high_water_mark")
            if latest
            else round(starting_cash, 2),
        "current_drawdown_pct":
            latest.get("drawdown_pct")
            if latest
            else 0.0,
        "max_drawdown_pct":
            round(max_drawdown_pct, 4),
        "history": history,
        "performance_scope":
            "GOVERNED_PAPER_PORTFOLIO_ONLY",
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.post("/paper-portfolio/mark-to-market")
def paper_portfolio_mark_to_market():
    return record_live_portfolio_snapshot()


@router.get("/paper-portfolio/performance")
def paper_portfolio_performance():
    return build_performance_history()


@router.get("/paper-portfolio/snapshots")
def paper_portfolio_snapshots():
    return {
        "snapshots": portfolio_snapshot_history(),
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
