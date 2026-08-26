from __future__ import annotations

from typing import Any
from uuid import uuid4

from ledger import (
    record_event,
    record_object,
    utc_now,
)

from paper_portfolio_core import (
    ACCOUNT_ID,
    PORTFOLIO_CASE_ID,
    _ticker_for_case,
    build_portfolio_state,
)

from paper_trade_postmortem import (
    build_trade_postmortem,
)


POLICY_VERSION = "governed-paper-exit-v1"


def create_governed_paper_exit(
    *,
    case_id: str,
    exit_price: float,
    reason: str,
    quantity: int | None = None,
    human_approved: bool = False,
) -> dict[str, Any]:

    if human_approved is not True:
        return {
            "status": "BLOCKED",
            "reason":
                "HUMAN_EXIT_APPROVAL_REQUIRED",
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    reason = str(
        reason or ""
    ).strip()

    if not reason:
        return {
            "status": "BLOCKED",
            "reason":
                "EXIT_REASON_REQUIRED",
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    try:
        price = float(
            exit_price
        )
    except (TypeError, ValueError):
        price = 0.0

    if price <= 0:
        return {
            "status": "BLOCKED",
            "reason":
                "VALID_EXIT_PRICE_REQUIRED",
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    ticker = _ticker_for_case(
        case_id
    )

    if not ticker:
        return {
            "status": "BLOCKED",
            "reason":
                "TICKER_NOT_RESOLVED",
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    state = build_portfolio_state()

    position = next(
        (
            row
            for row in (
                state.get(
                    "positions"
                )
                or []
            )
            if str(
                row.get(
                    "ticker"
                )
                or ""
            ).upper()
            == ticker.upper()
        ),
        None,
    )

    if not position:
        return {
            "status": "BLOCKED",
            "reason":
                "OPEN_POSITION_NOT_FOUND",
            "ticker":
                ticker,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    open_quantity = int(
        position.get(
            "quantity"
        )
        or 0
    )

    requested_quantity = (
        open_quantity
        if quantity is None
        else int(quantity)
    )

    if (
        requested_quantity <= 0
        or requested_quantity
        > open_quantity
    ):
        return {
            "status": "BLOCKED",
            "reason":
                "INVALID_EXIT_QUANTITY",
            "open_quantity":
                open_quantity,
            "requested_quantity":
                requested_quantity,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    average_cost = float(
        position.get(
            "average_cost"
        )
        or 0.0
    )

    notional = (
        requested_quantity
        * price
    )

    released_cost = (
        requested_quantity
        * average_cost
    )

    realized_pnl = (
        notional
        - released_cost
    )

    exit_id = (
        f"paper_exit_{uuid4().hex}"
    )

    transaction_id = (
        f"portfolio_exit_txn_"
        f"{exit_id}"
    )

    transaction = {
        "paper_portfolio_transaction_id":
            transaction_id,

        "paper_portfolio_account_id":
            ACCOUNT_ID,

        "source_execution_id":
            exit_id,

        "source_case_id":
            case_id,

        "ticker":
            ticker,

        "side":
            "SELL",

        "direction":
            "LONG",

        "quantity":
            requested_quantity,

        "price":
            round(
                price,
                6,
            ),

        "notional":
            round(
                notional,
                2,
            ),

        "cash_delta":
            round(
                notional,
                2,
            ),

        "realized_pnl_delta":
            round(
                realized_pnl,
                2,
            ),

        "transaction_source":
            "GOVERNED_PAPER_EXIT_ONLY",

        "exit_reason":
            reason,

        "human_approved":
            True,

        "created_at":
            utc_now(),

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }

    record_object(
        transaction_id,
        "paper_portfolio_transaction",
        PORTFOLIO_CASE_ID,
        transaction,
        parent_id=exit_id,
        topic=ticker,
    )

    exit_record = {
        "paper_exit_id":
            exit_id,

        "policy_version":
            POLICY_VERSION,

        "case_id":
            case_id,

        "ticker":
            ticker,

        "status":
            "COMPLETE",

        "execution":
            "PAPER_EXIT_RECORDED",

        "quantity":
            requested_quantity,

        "exit_price":
            round(
                price,
                4,
            ),

        "exit_notional":
            round(
                notional,
                2,
            ),

        "realized_pnl":
            round(
                realized_pnl,
                2,
            ),

        "reason":
            reason,

        "human_approved":
            True,

        "paper_mode":
            True,

        "auto_trade_authority":
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
        exit_id,
        "governed_paper_exit",
        case_id,
        exit_record,
        topic=ticker,
    )

    record_event(
        case_id,
        "GOVERNED_PAPER_EXIT_RECORDED",
        entity_id=exit_id,
        payload={
            "ticker":
                ticker,

            "quantity":
                requested_quantity,

            "exit_price":
                price,

            "realized_pnl":
                realized_pnl,

            "human_approved":
                True,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },
    )

    remaining = (
        open_quantity
        - requested_quantity
    )

    postmortem = None

    if remaining == 0:
        postmortem = (
            build_trade_postmortem(
                case_id
            )
        )

    return {
        **exit_record,

        "remaining_quantity":
            remaining,

        "postmortem":
            postmortem,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }
