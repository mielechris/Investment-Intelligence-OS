from __future__ import annotations

from datetime import datetime
from typing import Any

from ledger import (
    get_object,
    latest_object,
    record_event,
    record_object,
    utc_now,
)

from paper_portfolio_core import (
    _ticker_for_case,
    _transactions,
)


POLICY_VERSION = "paper-trade-postmortem-v1"


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _case_transactions(
    case_id: str,
    ticker: str,
) -> list[dict[str, Any]]:
    return [
        row
        for row in _transactions()
        if (
            str(
                row.get("source_case_id")
                or ""
            )
            == str(case_id)
            and str(
                row.get("ticker")
                or ""
            ).upper()
            == ticker.upper()
        )
    ]


def build_trade_postmortem(
    case_id: str,
) -> dict[str, Any]:
    ticker = _ticker_for_case(
        case_id
    )

    if not ticker:
        return {
            "status": "BLOCKED",
            "reason": "TICKER_NOT_RESOLVED",
            "live_execution": False,
        }

    rows = _case_transactions(
        case_id,
        ticker,
    )

    buys = [
        row
        for row in rows
        if str(
            row.get("side")
            or ""
        ).upper()
        == "BUY"
    ]

    sells = [
        row
        for row in rows
        if str(
            row.get("side")
            or ""
        ).upper()
        == "SELL"
    ]

    buy_qty = sum(
        int(
            row.get("quantity")
            or 0
        )
        for row in buys
    )

    sell_qty = sum(
        int(
            row.get("quantity")
            or 0
        )
        for row in sells
    )

    open_qty = (
        buy_qty - sell_qty
    )

    if (
        buy_qty <= 0
        or sell_qty <= 0
        or open_qty != 0
    ):
        return {
            "status": "OPEN_POSITION",
            "case_id": case_id,
            "ticker": ticker,
            "buy_quantity": buy_qty,
            "sell_quantity": sell_qty,
            "open_quantity": open_qty,
            "automatic_policy_rewrite": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    object_id = (
        f"paper_trade_postmortem_"
        f"{case_id}_{ticker}"
    )

    existing = get_object(
        object_id
    )

    if existing:
        return existing

    buy_notional = sum(
        _safe_float(
            row.get("notional")
        )
        for row in buys
    )

    sell_notional = sum(
        _safe_float(
            row.get("notional")
        )
        for row in sells
    )

    average_entry = (
        buy_notional / buy_qty
    )

    average_exit = (
        sell_notional / sell_qty
    )

    realized_pnl = (
        sell_notional
        - buy_notional
    )

    realized_return_pct = (
        realized_pnl
        / buy_notional
        * 100.0
        if buy_notional > 0
        else 0.0
    )

    if realized_pnl > 0:
        outcome = "WIN"
    elif realized_pnl < 0:
        outcome = "LOSS"
    else:
        outcome = "FLAT"

    qualification = latest_object(
        "qualification_assessment",
        case_id=case_id,
    ) or {}

    risk = latest_object(
        "risk_authorization",
        case_id=case_id,
    ) or {}

    committee = latest_object(
        "committee_decision",
        case_id=case_id,
    ) or {}

    entry_watch = latest_object(
        "capital_entry_watch",
        case_id=case_id,
    ) or {}

    grok = latest_object(
        "grok_experiment_scorecard",
        case_id=case_id,
    ) or {}

    postmortem = {
        "paper_trade_postmortem_id":
            object_id,

        "policy_version":
            POLICY_VERSION,

        "status":
            "COMPLETE",

        "case_id":
            case_id,

        "ticker":
            ticker,

        "outcome":
            outcome,

        "buy_quantity":
            buy_qty,

        "sell_quantity":
            sell_qty,

        "average_entry_price":
            round(
                average_entry,
                4,
            ),

        "average_exit_price":
            round(
                average_exit,
                4,
            ),

        "entry_notional":
            round(
                buy_notional,
                2,
            ),

        "exit_notional":
            round(
                sell_notional,
                2,
            ),

        "realized_pnl":
            round(
                realized_pnl,
                2,
            ),

        "realized_return_pct":
            round(
                realized_return_pct,
                4,
            ),

        "entry_context": {
            "committee_disposition":
                committee.get(
                    "disposition"
                ),

            "committee_confidence":
                committee.get(
                    "confidence"
                ),

            "qualified_buy_candidate":
                qualification.get(
                    "qualified_buy_candidate"
                ),

            "risk_decision":
                risk.get(
                    "decision"
                ),

            "capital_stage":
                entry_watch.get(
                    "stage"
                ),
        },

        "grok_context_present":
            bool(grok),

        "learning_observations": {
            "profitable":
                realized_pnl > 0,

            "loss_making":
                realized_pnl < 0,

            "entry_was_governed":
                True,

            "exit_was_paper_only":
                True,
        },

        # Learning is advisory only.
        "automatic_policy_rewrite":
            False,

        "automatic_agent_weight_change":
            False,

        "capital_authority":
            False,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,

        "created_at":
            utc_now(),
    }

    record_object(
        object_id,
        "paper_trade_postmortem",
        case_id,
        postmortem,
        topic=ticker,
    )

    record_event(
        case_id,
        "PAPER_TRADE_POSTMORTEM_COMPLETED",
        entity_id=object_id,
        payload={
            "ticker":
                ticker,

            "outcome":
                outcome,

            "realized_pnl":
                postmortem[
                    "realized_pnl"
                ],

            "automatic_policy_rewrite":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },
    )

    return postmortem
