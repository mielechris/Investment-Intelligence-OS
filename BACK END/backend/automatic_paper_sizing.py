from __future__ import annotations

from typing import Any
from uuid import uuid4

from ledger import (
    latest_object,
    record_event,
    record_object,
    utc_now,
)
from paper_position_sizing import (
    size_paper_position,
)


def _blocked(
    *,
    case_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "decision": "BLOCKED",
        "reason": reason,
        "proposed_shares": 0,
        "proposed_notional": 0.0,
        "paper_authorization_ready": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def calculate_automatic_paper_sizing(
    *,
    case_id: str,
    capital_gate: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate a governed proposed paper position.

    This function may size only after Capital Gate APPROVED.

    It cannot:
      - invent NAV,
      - invent an invalidation level,
      - create an authorization,
      - create an order,
      - execute live capital.
    """

    if capital_gate.get("decision") != "APPROVED":
        return _blocked(
            case_id=case_id,
            reason="CAPITAL_GATE_NOT_APPROVED",
        )

    profile = latest_object(
        "paper_sizing_profile",
        case_id=case_id,
    ) or {}

    if not profile:
        return _blocked(
            case_id=case_id,
            reason="SIZING_PROFILE_REQUIRED",
        )

    if profile.get("enabled") is not True:
        return _blocked(
            case_id=case_id,
            reason="SIZING_PROFILE_DISABLED",
        )

    if profile.get("inputs_complete") is not True:
        return _blocked(
            case_id=case_id,
            reason="SIZING_INPUTS_INCOMPLETE",
        )

    portfolio = latest_object(
        "portfolio_snapshot",
        case_id=case_id,
    )

    if not portfolio:
        return _blocked(
            case_id=case_id,
            reason="PORTFOLIO_SNAPSHOT_REQUIRED",
        )

    try:
        sizing = size_paper_position(
            capital_gate=capital_gate,
            portfolio_snapshot=portfolio,
            portfolio_nav=float(
                profile["portfolio_nav"]
            ),
            invalidation_price=float(
                profile["invalidation_price"]
            ),
            invalidation_basis=str(
                profile["invalidation_basis"]
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return {
            **_blocked(
                case_id=case_id,
                reason="SIZING_INPUT_INVALID",
            ),
            "error": str(exc),
        }

    sizing_id = (
        f"automatic_paper_sizing_"
        f"{uuid4().hex}"
    )

    result = {
        **sizing,

        "automatic_paper_sizing_id":
            sizing_id,

        "case_id":
            case_id,

        "paper_sizing_profile_id":
            profile.get(
                "paper_sizing_profile_id"
            ),

        "portfolio_snapshot_id":
            portfolio.get(
                "portfolio_snapshot_id"
            ),

        "created_at":
            utc_now(),

        "paper_mode":
            True,

        # Calculating size never unlocks these.
        "paper_authorization_ready":
            False,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
    }

    record_object(
        sizing_id,
        "automatic_paper_sizing",
        case_id,
        result,
        parent_id=profile.get(
            "paper_sizing_profile_id"
        ),
    )

    record_event(
        case_id,
        "AUTOMATIC_PAPER_SIZING_CALCULATED",
        entity_id=sizing_id,
        payload={
            "decision":
                result.get("decision"),

            "proposed_shares":
                result.get(
                    "proposed_shares"
                ),

            "proposed_notional":
                result.get(
                    "proposed_notional"
                ),

            "binding_constraint":
                result.get(
                    "binding_constraint"
                ),

            "paper_authorization_ready":
                False,

            "paper_order_permission":
                False,

            "trade_execution_permission":
                False,
        },
    )

    return result
