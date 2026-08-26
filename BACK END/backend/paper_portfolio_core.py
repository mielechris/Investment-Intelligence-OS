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
    accounting_flags: list[str] = []

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

        if quantity <= 0 or notional <= 0:
            accounting_flags.append(
                f"INVALID_TRANSACTION:{ticker}:{side}"
            )
            continue

        if side == "BUY":
            cash -= notional
            position["quantity"] += quantity
            position["cost_basis"] += notional

        elif side == "SELL":
            current_quantity = int(
                position.get("quantity") or 0
            )

            current_cost = _safe_float(
                position.get("cost_basis")
            )

            if (
                current_quantity <= 0
                or quantity > current_quantity
            ):
                accounting_flags.append(
                    f"OVERSELL_BLOCKED:{ticker}"
                )
                continue

            average_cost = (
                current_cost
                / current_quantity
            )

            released_cost = (
                average_cost * quantity
            )

            realized = (
                notional - released_cost
            )

            cash += notional
            realized_pnl += realized

            position["quantity"] -= quantity
            position["cost_basis"] = max(
                0.0,
                current_cost - released_cost,
            )

        else:
            accounting_flags.append(
                f"UNSUPPORTED_SIDE:{ticker}:{side}"
            )
            continue

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


# ============================================================
# Batch 8A.3 — benchmarks, exposure, risk + attribution
# ============================================================

BENCHMARKS = ("SPY", "QQQ")

# Measurement guardrails only. These DO NOT size positions,
# authorize orders, or change portfolio capital.
MAX_GROSS_EXPOSURE_PCT = 100.0
MAX_POSITION_CONCENTRATION_PCT = 25.0
MAX_DRAWDOWN_OBSERVATION_PCT = 10.0
MIN_CASH_PCT = 10.0


def record_benchmark_snapshot(ticker: str) -> dict[str, Any]:
    ticker = str(ticker or "").strip().upper()

    if ticker not in BENCHMARKS:
        return {
            "status": "BLOCKED",
            "reason": "UNSUPPORTED_BENCHMARK",
            "ticker": ticker,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    quote = fetch_market_quote(ticker)

    if (
        quote.get("status") != "ok"
        or quote.get("current_price") is None
    ):
        return {
            "status": "ERROR",
            "ticker": ticker,
            "error": quote.get("error"),
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    item = (
        (quote.get("items") or [{}])[0]
        if quote.get("items")
        else {}
    )

    snapshot_id = (
        f"paper_portfolio_benchmark_{ticker}_"
        f"{uuid4().hex}"
    )

    snapshot = {
        "paper_portfolio_benchmark_snapshot_id":
            snapshot_id,
        "paper_portfolio_account_id": ACCOUNT_ID,
        "benchmark": ticker,
        "price": round(
            _safe_float(quote.get("current_price")),
            6,
        ),
        "provider": quote.get("provider"),
        "provider_timestamp": item.get("timestamp"),
        "provider_url": item.get("url"),
        "status": "COMPLETE",
        "created_at": utc_now(),
        "measurement_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }

    record_object(
        snapshot_id,
        "paper_portfolio_benchmark_snapshot",
        PORTFOLIO_CASE_ID,
        snapshot,
        parent_id=ACCOUNT_ID,
        topic=ticker,
    )

    record_event(
        PORTFOLIO_CASE_ID,
        "PAPER_PORTFOLIO_BENCHMARK_MARKED",
        entity_id=snapshot_id,
        payload={
            "benchmark": ticker,
            "price": snapshot["price"],
            "provider": snapshot["provider"],
            "trade_execution_permission": False,
        },
    )

    return snapshot


def refresh_benchmarks() -> dict[str, Any]:
    results = {
        ticker: record_benchmark_snapshot(ticker)
        for ticker in BENCHMARKS
    }

    return {
        "status": "COMPLETE",
        "benchmarks": results,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def benchmark_snapshot_history(
    ticker: str,
) -> list[dict[str, Any]]:
    ticker = str(ticker or "").strip().upper()

    return [
        row
        for row in _rows_by_type(
            "paper_portfolio_benchmark_snapshot"
        )
        if (
            row.get("paper_portfolio_account_id")
            == ACCOUNT_ID
            and str(
                row.get("benchmark") or ""
            ).upper()
            == ticker
            and row.get("status") == "COMPLETE"
        )
    ]


def build_benchmark_performance() -> dict[str, Any]:
    output: dict[str, Any] = {}

    for ticker in BENCHMARKS:
        rows = benchmark_snapshot_history(ticker)

        if not rows:
            output[ticker] = {
                "benchmark": ticker,
                "snapshot_count": 0,
                "starting_price": None,
                "latest_price": None,
                "return_pct": None,
            }
            continue

        starting_price = _safe_float(
            rows[0].get("price")
        )
        latest_price = _safe_float(
            rows[-1].get("price")
        )

        return_pct = (
            ((latest_price / starting_price) - 1.0)
            * 100.0
            if starting_price > 0
            else None
        )

        output[ticker] = {
            "benchmark": ticker,
            "snapshot_count": len(rows),
            "starting_price":
                round(starting_price, 6),
            "latest_price":
                round(latest_price, 6),
            "return_pct":
                round(return_pct, 4)
                if return_pct is not None
                else None,
            "starting_at":
                rows[0].get("created_at"),
            "latest_at":
                rows[-1].get("created_at"),
        }

    return {
        "policy_version":
            "paper-portfolio-benchmark-v1",
        "benchmarks": output,
        "measurement_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


def build_position_attribution() -> dict[str, Any]:
    state = build_portfolio_state()

    nav = _safe_float(state.get("nav"))
    total_unrealized = _safe_float(
        state.get("unrealized_pnl")
    )

    rows: list[dict[str, Any]] = []

    for position in state.get("positions") or []:
        market_value = _safe_float(
            position.get("market_value")
        )
        unrealized = _safe_float(
            position.get("unrealized_pnl")
        )

        portfolio_weight_pct = (
            (market_value / nav) * 100.0
            if nav > 0
            else 0.0
        )

        pnl_contribution_pct = (
            (unrealized / total_unrealized) * 100.0
            if abs(total_unrealized) > 0.000001
            else None
        )

        rows.append(
            {
                "ticker": position.get("ticker"),
                "quantity": position.get("quantity"),
                "market_value":
                    round(market_value, 2),
                "portfolio_weight_pct":
                    round(portfolio_weight_pct, 4),
                "unrealized_pnl":
                    round(unrealized, 2),
                "unrealized_return_pct":
                    position.get(
                        "unrealized_return_pct"
                    ),
                "pnl_contribution_pct":
                    round(pnl_contribution_pct, 4)
                    if pnl_contribution_pct
                    is not None
                    else None,
            }
        )

    rows.sort(
        key=lambda row: abs(
            _safe_float(
                row.get("unrealized_pnl")
            )
        ),
        reverse=True,
    )

    return {
        "position_count": len(rows),
        "total_unrealized_pnl":
            round(total_unrealized, 2),
        "attribution": rows,
        "measurement_only": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def build_portfolio_risk() -> dict[str, Any]:
    state = build_portfolio_state()
    performance = build_performance_history()

    nav = _safe_float(state.get("nav"))
    cash = _safe_float(state.get("cash"))
    gross_exposure = _safe_float(
        state.get("gross_exposure")
    )
    net_exposure = _safe_float(
        state.get("net_exposure")
    )

    cash_pct = (
        (cash / nav) * 100.0
        if nav > 0
        else 0.0
    )

    gross_exposure_pct = (
        (gross_exposure / nav) * 100.0
        if nav > 0
        else 0.0
    )

    net_exposure_pct = (
        (net_exposure / nav) * 100.0
        if nav > 0
        else 0.0
    )

    concentration_rows: list[dict[str, Any]] = []

    for position in state.get("positions") or []:
        market_value = _safe_float(
            position.get("market_value")
        )

        weight_pct = (
            (market_value / nav) * 100.0
            if nav > 0
            else 0.0
        )

        concentration_rows.append(
            {
                "ticker": position.get("ticker"),
                "market_value":
                    round(market_value, 2),
                "weight_pct":
                    round(weight_pct, 4),
            }
        )

    concentration_rows.sort(
        key=lambda row: row["weight_pct"],
        reverse=True,
    )

    largest_position_pct = (
        concentration_rows[0]["weight_pct"]
        if concentration_rows
        else 0.0
    )

    current_drawdown_pct = abs(
        _safe_float(
            performance.get(
                "current_drawdown_pct"
            )
        )
    )

    breaches: list[str] = []

    if (
        gross_exposure_pct
        > MAX_GROSS_EXPOSURE_PCT
    ):
        breaches.append(
            "GROSS_EXPOSURE_OBSERVATION_LIMIT"
        )

    if (
        largest_position_pct
        > MAX_POSITION_CONCENTRATION_PCT
    ):
        breaches.append(
            "POSITION_CONCENTRATION_OBSERVATION_LIMIT"
        )

    if cash_pct < MIN_CASH_PCT:
        breaches.append(
            "MINIMUM_CASH_OBSERVATION_LIMIT"
        )

    if (
        current_drawdown_pct
        > MAX_DRAWDOWN_OBSERVATION_PCT
    ):
        breaches.append(
            "DRAWDOWN_OBSERVATION_LIMIT"
        )

    return {
        "policy_version":
            "paper-portfolio-risk-observation-v1",
        "nav": round(nav, 2),
        "cash": round(cash, 2),
        "cash_pct": round(cash_pct, 4),
        "gross_exposure":
            round(gross_exposure, 2),
        "gross_exposure_pct":
            round(gross_exposure_pct, 4),
        "net_exposure":
            round(net_exposure, 2),
        "net_exposure_pct":
            round(net_exposure_pct, 4),
        "largest_position_pct":
            round(largest_position_pct, 4),
        "current_drawdown_pct":
            round(current_drawdown_pct, 4),
        "position_concentration":
            concentration_rows,
        "observation_limits": {
            "max_gross_exposure_pct":
                MAX_GROSS_EXPOSURE_PCT,
            "max_position_concentration_pct":
                MAX_POSITION_CONCENTRATION_PCT,
            "max_drawdown_pct":
                MAX_DRAWDOWN_OBSERVATION_PCT,
            "min_cash_pct":
                MIN_CASH_PCT,
        },
        "observation_breaches": breaches,
        "risk_status":
            "OBSERVATION_BREACH"
            if breaches
            else "WITHIN_OBSERVATION_LIMITS",
        "measurement_only": True,
        "capital_allocation_allowed": False,
        "position_sizing_allowed": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


def build_portfolio_scoreboard() -> dict[str, Any]:
    portfolio_perf = build_performance_history()
    benchmark_perf = build_benchmark_performance()
    risk = build_portfolio_risk()
    attribution = build_position_attribution()

    portfolio_return = _safe_float(
        portfolio_perf.get(
            "cumulative_return_pct"
        )
    )

    benchmark_comparison: dict[str, Any] = {}

    for ticker in BENCHMARKS:
        row = (
            benchmark_perf.get("benchmarks") or {}
        ).get(ticker) or {}

        benchmark_return = row.get("return_pct")

        benchmark_comparison[ticker] = {
            **row,
            "excess_return_pct": (
                round(
                    portfolio_return
                    - _safe_float(
                        benchmark_return
                    ),
                    4,
                )
                if benchmark_return
                is not None
                else None
            ),
        }

    return {
        "policy_version":
            "paper-portfolio-scoreboard-v1",
        "portfolio": {
            "starting_nav":
                portfolio_perf.get("starting_nav"),
            "latest_nav":
                portfolio_perf.get("latest_nav"),
            "return_pct":
                portfolio_perf.get(
                    "cumulative_return_pct"
                ),
            "max_drawdown_pct":
                portfolio_perf.get(
                    "max_drawdown_pct"
                ),
            "snapshot_count":
                portfolio_perf.get(
                    "snapshot_count"
                ),
        },
        "benchmark_comparison":
            benchmark_comparison,
        "risk": risk,
        "attribution": attribution,
        "measurement_only": True,
        "capital_allocation_allowed": False,
        "position_sizing_allowed": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.post("/paper-portfolio/benchmarks/refresh")
def paper_portfolio_benchmarks_refresh():
    return refresh_benchmarks()


@router.get("/paper-portfolio/benchmarks")
def paper_portfolio_benchmarks():
    return build_benchmark_performance()


@router.get("/paper-portfolio/risk")
def paper_portfolio_risk():
    return build_portfolio_risk()


@router.get("/paper-portfolio/attribution")
def paper_portfolio_attribution():
    return build_position_attribution()


@router.get("/paper-portfolio/scoreboard")
def paper_portfolio_scoreboard():
    return build_portfolio_scoreboard()
