from __future__ import annotations

from typing import Any
from uuid import uuid4

from automatic_paper_sizing import calculate_automatic_paper_sizing
from cycle_normalized_valuation import (
    build_live_cycle_stress,
)
from ledger import (
    latest_object,
    record_event,
    record_object,
    utc_now,
)
from live_invalidation_mapper import (
    build_live_invalidation_status,
)
from paper_capital_gate import (
    assess_paper_capital,
)
from provider_hardening import (
    fetch_market_quote,
)
from generic_public_company_capital import (
    _ticker_for_case,
    assess_generic_public_company_capital,
    build_generic_public_company_stress,
)
from generic_public_company_thesis import (
    build_generic_thesis_status,
)
from generic_position_sizing import (
    calculate_generic_position_sizing,
)


def classify_entry_state(
    *,
    capital: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Convert the governed Capital Gate decision into
    an automatic entry-watch state.

    This function has ZERO authorization or execution
    authority.
    """

    decision = str(
        capital.get("decision") or ""
    )

    current_price = capital.get(
        "current_price"
    )

    maximum_entry = capital.get(
        "maximum_qualifying_entry"
    )

    if decision == "APPROVED":
        stage = "READY_FOR_POSITION_SIZING"

    elif decision == "WAIT_FOR_ENTRY":
        stage = "WAIT_FOR_ENTRY"

    elif decision == "REJECTED":
        stage = "CAPITAL_REJECTED"

    else:
        stage = "UNKNOWN"

    entry_gap = None
    entry_gap_pct = None

    if (
        current_price is not None
        and maximum_entry is not None
    ):
        current = float(current_price)
        maximum = float(maximum_entry)

        entry_gap = max(
            0.0,
            current - maximum,
        )

        if current > 0:
            entry_gap_pct = (
                entry_gap / current
            ) * 100.0

    previous_stage = str(
        (previous or {}).get("stage")
        or ""
    )

    crossed_into_ready = (
        previous_stage == "WAIT_FOR_ENTRY"
        and stage
        == "READY_FOR_POSITION_SIZING"
    )

    return {
        "stage": stage,
        "capital_decision": decision,

        "current_price":
            current_price,

        "maximum_qualifying_entry":
            maximum_entry,

        "entry_gap":
            (
                round(entry_gap, 4)
                if entry_gap is not None
                else None
            ),

        "entry_gap_pct":
            (
                round(entry_gap_pct, 4)
                if entry_gap_pct is not None
                else None
            ),

        "reward_risk":
            capital.get("reward_risk"),

        "minimum_reward_risk":
            capital.get(
                "minimum_reward_risk"
            ),

        "previous_stage":
            previous_stage or None,

        "crossed_into_ready":
            crossed_into_ready,

        # Hard safety locks.
        "position_sizing_ready": (
            stage
            == "READY_FOR_POSITION_SIZING"
        ),

        "paper_authorization_ready":
            False,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def refresh_capital_entry_watch(
    case_id: str,
    *,
    quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Refresh capital-entry readiness using the newest
    governed quote.

    Safe to run automatically from the monitor scheduler.
    """

    qualification = latest_object(
        "qualification_assessment",
        case_id=case_id,
    ) or {}

    # Do not waste network/model work on cases that
    # have not passed research qualification.
    if (
        qualification.get(
            "qualified_buy_candidate"
        )
        is not True
    ):
        return {
            "case_id": case_id,
            "stage":
                "RESEARCH_NOT_QUALIFIED",
            "position_sizing_ready":
                False,
            "paper_authorization_ready":
                False,
            "paper_order_permission":
                False,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        }

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
        return {
            "case_id": case_id,
            "stage":
                "RISK_STATE_UNAVAILABLE",
            "position_sizing_ready":
                False,
            "paper_authorization_ready":
                False,
            "paper_order_permission":
                False,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        }

    try:
        ticker = _ticker_for_case(case_id)
    except Exception:
        ticker = ""

    if quote is None:
        if not ticker:
            return {
                "case_id": case_id,
                "stage":
                    "TICKER_UNAVAILABLE",
                "position_sizing_ready":
                    False,
                "paper_authorization_ready":
                    False,
                "paper_order_permission":
                    False,
                "trade_execution_permission":
                    False,
                "live_execution":
                    False,
            }

        quote = fetch_market_quote(
            ticker
        )

    if (
        quote.get("status") != "ok"
        or quote.get("current_price")
        is None
    ):
        return {
            "case_id": case_id,
            "stage":
                "QUOTE_UNAVAILABLE",
            "quote_status":
                quote.get("status"),
            "quote_error":
                quote.get("error"),
            "position_sizing_ready":
                False,
            "paper_authorization_ready":
                False,
            "paper_order_permission":
                False,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        }

    case = latest_object(
        "case",
        case_id=case_id,
    ) or {}

    topic = str(
        case.get("topic") or ""
    ).lower()

    ticker_upper = str(
        ticker or ""
    ).upper()

    is_micron = (
        ticker_upper in {"MU", "MU.US"}
        or "micron" in topic
    )

    if is_micron:
        capital_profile = (
            "MICRON_SEMICONDUCTOR_CYCLE"
        )

        thesis = (
            build_live_invalidation_status(
                case_id
            )
        )

        stress = build_live_cycle_stress(
            case_id,
            quote_override=quote,
        )

        capital = assess_paper_capital(
            qualification=qualification,
            risk=risk,
            stress=stress,
            thesis_status=thesis,
        )

    else:
        capital_profile = (
            "GENERIC_PUBLIC_COMPANY"
        )

        thesis = (
            build_generic_thesis_status(
                case_id
            )
        )

        stress = (
            build_generic_public_company_stress(
                case_id,
                quote_override=quote,
            )
        )

        capital = (
            assess_generic_public_company_capital(
                qualification=qualification,
                risk=risk,
                stress=stress,
                thesis_status=thesis,
            )
        )

    previous = latest_object(
        "capital_entry_watch",
        case_id=case_id,
    )

    classified = classify_entry_state(
        capital=capital,
        previous=previous,
    )

    # Sizing may run only after the deterministic
    # Capital Gate reaches APPROVED.
    if (
        classified.get("stage")
        == "READY_FOR_POSITION_SIZING"
        and capital_profile
        == "MICRON_SEMICONDUCTOR_CYCLE"
    ):
        automatic_sizing = (
            calculate_automatic_paper_sizing(
                case_id=case_id,
                capital_gate=capital,
            )
        )

    elif (
        classified.get("stage")
        == "READY_FOR_POSITION_SIZING"
    ):
        automatic_sizing = (
            calculate_generic_position_sizing(
                case_id=case_id,
                capital_gate=capital,
            )
        )

    else:
        automatic_sizing = {
            "decision": "NOT_RUN",
            "reason":
                "ENTRY_GATE_NOT_REACHED",
            "proposed_shares": 0,
            "proposed_notional": 0.0,
            "paper_authorization_ready":
                False,
            "paper_order_permission":
                False,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        }

    watch_id = (
        f"capital_entry_watch_"
        f"{uuid4().hex}"
    )

    item = (
        (quote.get("items") or [{}])[0]
        if quote.get("items")
        else {}
    )

    payload = {
        "capital_entry_watch_id":
            watch_id,

        "case_id":
            case_id,

        **classified,

        "ticker":
            ticker,

        "capital_profile":
            capital_profile,

        "quote_provider":
            quote.get("provider"),

        "quote_timestamp":
            item.get("timestamp"),

        "thesis_status":
            thesis.get("status"),

        "thesis_invalidated":
            thesis.get(
                "thesis_invalidated"
            ),

        "capital_failed_hard_checks":
            capital.get(
                "failed_hard_checks"
            )
            or [],

        "automatic_sizing":
            automatic_sizing,

        "created_at":
            utc_now(),

        "paper_mode":
            True,
    }

    record_object(
        watch_id,
        "capital_entry_watch",
        case_id,
        payload,
    )

    record_event(
        case_id,
        "CAPITAL_ENTRY_WATCH_REFRESHED",
        entity_id=watch_id,
        payload={
            "stage":
                payload["stage"],
            "current_price":
                payload["current_price"],
            "maximum_qualifying_entry":
                payload[
                    "maximum_qualifying_entry"
                ],
            "crossed_into_ready":
                payload[
                    "crossed_into_ready"
                ],
            "trade_execution_permission":
                False,
        },
    )

    if payload["crossed_into_ready"]:
        record_event(
            case_id,
            "CAPITAL_ENTRY_GATE_REACHED",
            entity_id=watch_id,
            payload={
                "current_price":
                    payload[
                        "current_price"
                    ],
                "maximum_qualifying_entry":
                    payload[
                        "maximum_qualifying_entry"
                    ],

                # Reaching the gate does NOT authorize
                # or execute anything.
                "paper_authorization_ready":
                    False,
                "paper_order_permission":
                    False,
                "trade_execution_permission":
                    False,
            },
        )

    return payload
