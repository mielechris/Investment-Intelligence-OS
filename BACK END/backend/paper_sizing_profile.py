from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ledger import (
    get_object,
    latest_object,
    record_event,
    record_object,
    utc_now,
)


router = APIRouter()

PROFILE_VERSION = "PAPER_SIZING_PROFILE_V1"


def _positive(
    value: Any,
    name: str,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{name} must be numeric"
        )

    if result <= 0:
        raise ValueError(
            f"{name} must be positive"
        )

    return result


def validate_sizing_profile(
    *,
    portfolio_nav: Any,
    invalidation_price: Any,
    invalidation_basis: Any,
) -> dict[str, Any]:
    """
    Validate deliberate user/governance inputs.

    This function does NOT:
      - infer an invalidation level,
      - calculate a position,
      - authorize capital,
      - create a paper order.
    """

    nav = _positive(
        portfolio_nav,
        "portfolio_nav",
    )

    invalidation = _positive(
        invalidation_price,
        "invalidation_price",
    )

    basis = str(
        invalidation_basis or ""
    ).strip()

    if len(basis) < 10:
        raise ValueError(
            "invalidation_basis must explain "
            "the governed reason for the level"
        )

    return {
        "portfolio_nav":
            round(nav, 2),

        "invalidation_price":
            round(invalidation, 4),

        "invalidation_basis":
            basis,

        "inputs_complete":
            True,

        "governance": {
            "portfolio_nav_explicit":
                True,

            "invalidation_price_explicit":
                True,

            "invalidation_price_inferred":
                False,

            "sizing_authority":
                False,

            "paper_authorization_ready":
                False,

            "paper_order_permission":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },
    }


def save_sizing_profile(
    case_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    case = get_object(case_id)

    if (
        not case
        or not case_id.startswith("case_")
    ):
        raise ValueError(
            "Unknown case_id"
        )

    validated = validate_sizing_profile(
        portfolio_nav=payload.get(
            "portfolio_nav"
        ),
        invalidation_price=payload.get(
            "invalidation_price"
        ),
        invalidation_basis=payload.get(
            "invalidation_basis"
        ),
    )

    profile_id = (
        f"paper_sizing_profile_{case_id}"
    )

    existing = latest_object(
        "paper_sizing_profile",
        case_id=case_id,
    ) or {}

    profile = {
        "paper_sizing_profile_id":
            profile_id,

        "profile_version":
            PROFILE_VERSION,

        "case_id":
            case_id,

        **validated,

        "enabled":
            bool(
                payload.get(
                    "enabled",
                    True,
                )
            ),

        "created_at":
            existing.get(
                "created_at"
            )
            or utc_now(),

        "updated_at":
            utc_now(),

        "paper_mode":
            True,
    }

    record_object(
        profile_id,
        "paper_sizing_profile",
        case_id,
        profile,
        parent_id=case_id,
    )

    record_event(
        case_id,
        "PAPER_SIZING_PROFILE_UPDATED",
        entity_id=profile_id,
        payload={
            "enabled":
                profile["enabled"],

            "portfolio_nav":
                profile[
                    "portfolio_nav"
                ],

            "invalidation_price":
                profile[
                    "invalidation_price"
                ],

            "invalidation_price_inferred":
                False,

            "trade_execution_permission":
                False,
        },
    )

    return profile


def sizing_profile_status(
    case_id: str,
) -> dict[str, Any]:
    profile = latest_object(
        "paper_sizing_profile",
        case_id=case_id,
    )

    portfolio = latest_object(
        "portfolio_snapshot",
        case_id=case_id,
    )

    ready = bool(
        profile
        and profile.get("enabled")
        and profile.get(
            "inputs_complete"
        )
        and portfolio
    )

    return {
        "case_id":
            case_id,

        "profile":
            profile,

        "portfolio_snapshot_present":
            bool(portfolio),

        "sizing_inputs_ready":
            ready,

        # Ready means inputs exist.
        # It does NOT mean Capital Gate passed.
        "position_sizing_authorized":
            False,

        "paper_authorization_ready":
            False,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,

        "paper_mode":
            True,
    }


@router.get(
    "/paper-sizing-profile/{case_id}"
)
def get_paper_sizing_profile(
    case_id: str,
):
    return sizing_profile_status(
        case_id
    )


@router.post(
    "/paper-sizing-profile/{case_id}"
)
def update_paper_sizing_profile(
    case_id: str,
    payload: dict[str, Any],
):
    try:
        return save_sizing_profile(
            case_id,
            payload,
        )
    except ValueError as exc:
        message = str(exc)

        status = (
            404
            if message
            == "Unknown case_id"
            else 422
        )

        raise HTTPException(
            status_code=status,
            detail=message,
        )
