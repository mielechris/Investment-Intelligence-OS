from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from governed_paper_authorization import (
    _canonical_binding,
    create_paper_authorization,
)
from ledger import (
    latest_object,
    paper_authorization_consumed,
)
from live_invalidation_mapper import (
    build_live_invalidation_status,
)
from paper_capital_gate import (
    assess_paper_capital,
)


router = APIRouter()


def assess_authorization_readiness(
    *,
    qualification: dict[str, Any],
    thesis: dict[str, Any],
    capital: dict[str, Any],
    sizing: dict[str, Any],
    entry_watch: dict[str, Any],
) -> dict[str, Any]:

    try:
        sizing_entry = float(
            sizing.get("entry_price")
        )
        capital_entry = float(
            capital.get("current_price")
        )
        watch_entry = float(
            entry_watch.get("current_price")
        )

        quote_match = (
            abs(
                sizing_entry
                - capital_entry
            )
            <= 0.01
            and abs(
                watch_entry
                - capital_entry
            )
            <= 0.01
        )
    except (TypeError, ValueError):
        quote_match = False

    checks = {
        "qualified_candidate": (
            qualification.get(
                "qualified_buy_candidate"
            )
            is True
        ),

        "thesis_active": (
            thesis.get("status")
            in {
                "ACTIVE_CLEAR",
                "ACTIVE_WITH_WATCHES",
            }
            and thesis.get(
                "thesis_invalidated"
            )
            is False
            and not (
                thesis.get(
                    "breached_rules"
                )
                or []
            )
        ),

        "capital_approved": (
            capital.get("decision")
            == "APPROVED"
        ),

        "entry_watch_ready": (
            entry_watch.get("stage")
            == "READY_FOR_POSITION_SIZING"
        ),

        "sizing_ready": (
            sizing.get("decision")
            == "SIZE_READY"
        ),

        "positive_shares": (
            int(
                sizing.get(
                    "proposed_shares"
                )
                or 0
            )
            > 0
        ),

        "positive_notional": (
            float(
                sizing.get(
                    "proposed_notional"
                )
                or 0.0
            )
            > 0
        ),

        "quote_binding_current":
            quote_match,

        "sizing_execution_locked": (
            sizing.get(
                "paper_order_permission"
            )
            is False
            and sizing.get(
                "trade_execution_permission"
            )
            is False
        ),
    }

    failed = [
        key
        for key, passed
        in checks.items()
        if not passed
    ]

    return {
        "ready": not failed,
        "checks": checks,
        "failed_checks": failed,

        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
    }


def _current_state(
    case_id: str,
) -> dict[str, Any]:

    qualification = latest_object(
        "qualification_assessment",
        case_id=case_id,
    ) or {}

    hunt = latest_object(
        "gap_hunt",
        case_id=case_id,
    ) or {}

    risk = hunt.get("risk") or {}

    stress = latest_object(
        "cycle_valuation_stress",
        case_id=case_id,
    ) or {}

    entry_watch = latest_object(
        "capital_entry_watch",
        case_id=case_id,
    ) or {}

    sizing = latest_object(
        "automatic_paper_sizing",
        case_id=case_id,
    ) or {}

    if not qualification:
        raise HTTPException(
            status_code=409,
            detail="Qualification state unavailable",
        )

    if not risk:
        raise HTTPException(
            status_code=409,
            detail="Risk state unavailable",
        )

    if not stress:
        raise HTTPException(
            status_code=409,
            detail="Cycle valuation state unavailable",
        )

    thesis = (
        build_live_invalidation_status(
            case_id
        )
    )

    capital = assess_paper_capital(
        qualification=qualification,
        risk=risk,
        stress=stress,
        thesis_status=thesis,
    )

    readiness = (
        assess_authorization_readiness(
            qualification=qualification,
            thesis=thesis,
            capital=capital,
            sizing=sizing,
            entry_watch=entry_watch,
        )
    )

    return {
        "qualification":
            qualification,
        "thesis":
            thesis,
        "capital":
            capital,
        "sizing":
            sizing,
        "entry_watch":
            entry_watch,
        "readiness":
            readiness,
    }


@router.get(
    "/paper-authorization/{case_id}/status"
)
def paper_authorization_status(
    case_id: str,
):
    state = _current_state(
        case_id
    )

    latest_auth = latest_object(
        "paper_authorization",
        case_id=case_id,
    ) or {}

    auth_id = latest_auth.get(
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
        "case_id": case_id,

        "authorization_ready":
            state["readiness"]["ready"],

        "checks":
            state["readiness"]["checks"],

        "failed_checks":
            state["readiness"][
                "failed_checks"
            ],

        "latest_authorization": {
            "authorization_id":
                auth_id,

            "decision":
                latest_auth.get(
                    "decision"
                ),

            "consumed":
                consumed,

            "authorized_shares":
                latest_auth.get(
                    "authorized_shares"
                ),

            "authorized_notional":
                latest_auth.get(
                    "authorized_notional"
                ),
        },

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,

        "paper_mode":
            True,
    }


@router.post(
    "/paper-authorization/{case_id}/prepare"
)
def prepare_paper_authorization(
    case_id: str,
):
    state = _current_state(
        case_id
    )

    readiness = state[
        "readiness"
    ]

    if not readiness["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "reason":
                    "AUTHORIZATION_NOT_READY",
                "failed_checks":
                    readiness[
                        "failed_checks"
                    ],
            },
        )

    current_binding = (
        _canonical_binding(
            case_id=case_id,
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
    )

    # Prevent duplicate active authorizations
    # for the identical governed state.
    existing = latest_object(
        "paper_authorization",
        case_id=case_id,
    ) or {}

    existing_id = existing.get(
        "paper_authorization_id"
    )

    if (
        existing_id
        and existing.get(
            "binding"
        )
        == current_binding
        and paper_authorization_consumed(
            existing_id
        )
        is False
    ):
        return {
            "decision":
                "ALREADY_PREPARED",

            "paper_authorization_id":
                existing_id,

            "authorized_shares":
                existing.get(
                    "authorized_shares"
                ),

            "authorized_notional":
                existing.get(
                    "authorized_notional"
                ),

            "single_use":
                True,

            "paper_order_permission":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        }

    authorization = (
        create_paper_authorization(
            case_id=case_id,

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
    )

    if (
        authorization.get(
            "decision"
        )
        != "AUTHORIZED_FOR_PAPER_HANDOFF"
    ):
        raise HTTPException(
            status_code=409,
            detail=authorization,
        )

    return authorization
