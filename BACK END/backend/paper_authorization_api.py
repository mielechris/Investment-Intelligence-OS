from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
)

from capital_entry_watch import (
    refresh_capital_entry_watch,
)

from generic_position_sizing import (
    calculate_generic_position_sizing,
)

from generic_public_company_capital import (
    _ticker_for_case,
    assess_generic_public_company_capital,
)

from generic_public_company_thesis import (
    build_generic_thesis_status,
)

from governed_paper_authorization import (
    _canonical_binding,
    create_paper_authorization,
    paper_authorization_expired,
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

MAX_AUTH_QUOTE_AGE_MINUTES = 30


def _parse_time(
    value: Any,
) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def _quote_is_fresh(
    entry_watch: dict[str, Any],
) -> bool:
    timestamp = _parse_time(
        entry_watch.get(
            "quote_timestamp"
        )
    )

    if timestamp is None:
        return False

    age_minutes = (
        (
            datetime.now(
                timezone.utc
            )
            - timestamp
        ).total_seconds()
        / 60.0
    )

    return (
        0
        <= age_minutes
        <= MAX_AUTH_QUOTE_AGE_MINUTES
    )


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
            entry_watch.get(
                "current_price"
            )
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
            ==
            "READY_FOR_POSITION_SIZING"
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

        "quote_fresh_for_authorization":
            _quote_is_fresh(
                entry_watch
            ),

        "sizing_execution_locked": (
            sizing.get(
                "paper_order_permission"
            )
            is False
            and sizing.get(
                "trade_execution_permission"
            )
            is False
            and sizing.get(
                "live_execution"
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
        "ready":
            not failed,

        "checks":
            checks,

        "failed_checks":
            failed,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def _is_micron(
    case_id: str,
) -> bool:
    try:
        ticker = (
            _ticker_for_case(
                case_id
            )
            .upper()
        )
    except Exception:
        ticker = ""

    return ticker in {
        "MU",
        "MU.US",
    }


def _current_state(
    case_id: str,
    *,
    refresh_market: bool = False,
) -> dict[str, Any]:

    qualification = latest_object(
        "qualification_assessment",
        case_id=case_id,
    ) or {}

    if not qualification:
        raise HTTPException(
            status_code=409,
            detail=
                "Qualification state unavailable",
        )

    risk = latest_object(
        "risk_authorization",
        case_id=case_id,
    ) or {}

    if not risk:
        hunt = latest_object(
            "gap_hunt",
            case_id=case_id,
        ) or {}

        risk = hunt.get("risk") or {}

    if not risk:
        raise HTTPException(
            status_code=409,
            detail=
                "Risk state unavailable",
        )

    if refresh_market:
        refresh_capital_entry_watch(
            case_id
        )

    entry_watch = latest_object(
        "capital_entry_watch",
        case_id=case_id,
    ) or {}

    if _is_micron(case_id):
        stress = latest_object(
            "cycle_valuation_stress",
            case_id=case_id,
        ) or {}

        if not stress:
            raise HTTPException(
                status_code=409,
                detail=
                    "Cycle valuation state unavailable",
            )

        thesis = (
            build_live_invalidation_status(
                case_id
            )
        )

        capital = assess_paper_capital(
            qualification=
                qualification,

            risk=
                risk,

            stress=
                stress,

            thesis_status=
                thesis,
        )

        sizing = latest_object(
            "automatic_paper_sizing",
            case_id=case_id,
        ) or {}

        profile = (
            "MICRON_SEMICONDUCTOR_CYCLE"
        )

    else:
        stress = latest_object(
            "generic_capital_stress",
            case_id=case_id,
        ) or {}

        if not stress:
            raise HTTPException(
                status_code=409,
                detail=
                    "Generic capital state unavailable",
            )

        thesis = latest_object(
            "generic_thesis_status",
            case_id=case_id,
        ) or {}

        if not thesis:
            thesis = (
                build_generic_thesis_status(
                    case_id
                )
            )

        capital = (
            assess_generic_public_company_capital(
                qualification=
                    qualification,

                risk=
                    risk,

                stress=
                    stress,

                thesis_status=
                    thesis,
            )
        )

        sizing = latest_object(
            "generic_position_sizing",
            case_id=case_id,
        ) or {}

        # If Capital is ready but sizing was not yet
        # materialized, calculate it now.
        if (
            capital.get("decision")
            == "APPROVED"
            and sizing.get("decision")
            != "SIZE_READY"
        ):
            sizing = (
                calculate_generic_position_sizing(
                    case_id=case_id,
                    capital_gate=capital,
                )
            )

        profile = (
            "GENERIC_PUBLIC_COMPANY"
        )

    # Bind authorization to the exact Risk state that
    # helped produce Capital approval.
    capital = {
        **capital,

        "_risk_authorization_id":
            risk.get(
                "risk_authorization_id"
            )
            or risk.get(
                "decision_id"
            ),
    }

    readiness = (
        assess_authorization_readiness(
            qualification=
                qualification,

            thesis=
                thesis,

            capital=
                capital,

            sizing=
                sizing,

            entry_watch=
                entry_watch,
        )
    )

    return {
        "profile":
            profile,

        "qualification":
            qualification,

        "risk":
            risk,

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
        "case_id":
            case_id,

        "profile":
            state["profile"],

        "authorization_ready":
            state[
                "readiness"
            ]["ready"],

        "checks":
            state[
                "readiness"
            ]["checks"],

        "failed_checks":
            state[
                "readiness"
            ][
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

            "expired": (
                paper_authorization_expired(
                    latest_auth
                )
                if latest_auth
                else None
            ),

            "authorized_shares":
                latest_auth.get(
                    "authorized_shares"
                ),

            "minimum_order_price":
                latest_auth.get(
                    "minimum_order_price"
                ),

            "maximum_order_price":
                latest_auth.get(
                    "maximum_order_price"
                ),

            "expires_at":
                latest_auth.get(
                    "expires_at"
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
    # Preparation always refreshes the market gate first.
    state = _current_state(
        case_id,
        refresh_market=True,
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

            qualification=
                state[
                    "qualification"
                ],

            thesis_status=
                state[
                    "thesis"
                ],

            capital_gate=
                state[
                    "capital"
                ],

            sizing=
                state[
                    "sizing"
                ],
        )
    )

    existing = latest_object(
        "paper_authorization",
        case_id=case_id,
    ) or {}

    existing_id = existing.get(
        "paper_authorization_id"
    )

    if (
        existing_id
        and existing.get("binding")
        == current_binding
        and paper_authorization_consumed(
            existing_id
        )
        is False
        and not paper_authorization_expired(
            existing
        )
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

            "minimum_order_price":
                existing.get(
                    "minimum_order_price"
                ),

            "maximum_order_price":
                existing.get(
                    "maximum_order_price"
                ),

            "expires_at":
                existing.get(
                    "expires_at"
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

            qualification=
                state[
                    "qualification"
                ],

            thesis_status=
                state[
                    "thesis"
                ],

            capital_gate=
                state[
                    "capital"
                ],

            sizing=
                state[
                    "sizing"
                ],
        )
    )

    if (
        authorization.get(
            "decision"
        )
        !=
        "AUTHORIZED_FOR_PAPER_HANDOFF"
    ):
        raise HTTPException(
            status_code=409,
            detail=authorization,
        )

    return authorization
