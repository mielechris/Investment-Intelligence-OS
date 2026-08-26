from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ledger import (
    get_object,
    latest_object,
    list_objects,
    record_event,
    record_object,
    utc_now,
)
from provider_hardening import fetch_market_quote


POLICY_VERSION = "generic-public-company-capital-v1"

MIN_REWARD_RISK = 1.50

# Explicit scenario assumptions — NOT observed facts.
UPSIDE_EPS_CHANGE_PCT = 15.0
DOWNSIDE_EPS_CHANGE_PCT = -25.0
UPSIDE_MULTIPLE_CHANGE_PCT = 0.0
DOWNSIDE_MULTIPLE_CHANGE_PCT = -20.0


def _ticker_for_case(case_id: str) -> str:
    profile = latest_object(
        "monitor_profile",
        case_id=case_id,
    ) or {}

    ticker = str(
        profile.get("ticker") or ""
    ).strip().upper()

    if ticker.endswith(".US"):
        ticker = ticker[:-3]

    if ticker:
        return ticker

    case = get_object(case_id) or {}

    ticker = str(
        case.get("ticker") or ""
    ).strip().upper()

    if ticker:
        return ticker

    candidate_id = str(
        case.get("source_candidate_id") or ""
    ).strip()

    if candidate_id:
        candidate = get_object(candidate_id) or {}

        ticker = str(
            candidate.get("ticker") or ""
        ).strip().upper()

        if ticker:
            return ticker

    raise ValueError("Ticker could not be resolved")


def _latest_primary(
    case_id: str,
    fact_key: str,
) -> dict[str, Any] | None:
    for row in reversed(
        list_objects(
            case_id,
            "primary_evidence_record",
        )
    ):
        if (
            row.get("fact_key") == fact_key
            and row.get("gap_resolution_eligible")
            is True
        ):
            return row

    return None


def _extract_number(
    claim: str,
    patterns: tuple[str, ...],
) -> float | None:
    for pattern in patterns:
        match = re.search(
            pattern,
            str(claim or ""),
            flags=re.I,
        )

        if not match:
            continue

        try:
            return float(
                match.group(1)
                .replace(",", "")
            )
        except (TypeError, ValueError):
            continue

    return None


def _forward_eps(
    case_id: str,
) -> tuple[float, dict[str, Any]]:
    record = _latest_primary(
        case_id,
        "consensus",
    )

    if not record:
        raise ValueError(
            "Governed consensus record missing"
        )

    eps = _extract_number(
        str(record.get("claim") or ""),
        (
            r"consensus\s+EPS\s*=\s*([0-9.,]+)",
            r"\bEPS\s*=\s*([0-9.,]+)",
        ),
    )

    if eps is None or eps <= 0:
        raise ValueError(
            "Forward EPS could not be parsed "
            "from governed consensus"
        )

    return eps, record


def required_entry_for_reward_risk(
    *,
    upside_value: float,
    downside_value: float,
    minimum_reward_risk: float,
) -> float:
    return (
        upside_value
        + minimum_reward_risk
        * downside_value
    ) / (
        1.0 + minimum_reward_risk
    )


def build_generic_public_company_stress(
    case_id: str,
    *,
    quote_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case = get_object(case_id)

    if not case:
        raise ValueError("Unknown case_id")

    ticker = _ticker_for_case(case_id)

    forward_eps, consensus_record = (
        _forward_eps(case_id)
    )

    quote = (
        quote_override
        if isinstance(quote_override, dict)
        else fetch_market_quote(ticker)
    )

    if (
        quote.get("status") != "ok"
        or quote.get("current_price") is None
    ):
        raise ValueError(
            f"Governed quote unavailable: "
            f"{quote.get('error')}"
        )

    current_price = float(
        quote["current_price"]
    )

    if current_price <= 0:
        raise ValueError(
            "Current price must be positive"
        )

    current_forward_pe = (
        current_price / forward_eps
    )

    upside_eps = (
        forward_eps
        * (
            1.0
            + UPSIDE_EPS_CHANGE_PCT
            / 100.0
        )
    )

    downside_eps = (
        forward_eps
        * (
            1.0
            + DOWNSIDE_EPS_CHANGE_PCT
            / 100.0
        )
    )

    upside_multiple = (
        current_forward_pe
        * (
            1.0
            + UPSIDE_MULTIPLE_CHANGE_PCT
            / 100.0
        )
    )

    downside_multiple = (
        current_forward_pe
        * (
            1.0
            + DOWNSIDE_MULTIPLE_CHANGE_PCT
            / 100.0
        )
    )

    upside_value = (
        upside_eps * upside_multiple
    )

    downside_value = (
        downside_eps * downside_multiple
    )

    upside_dollars = (
        upside_value - current_price
    )

    downside_dollars = (
        current_price - downside_value
    )

    reward_risk = 0.0

    if (
        upside_dollars > 0
        and downside_dollars > 0
    ):
        reward_risk = (
            upside_dollars
            / downside_dollars
        )

    maximum_qualifying_entry = (
        required_entry_for_reward_risk(
            upside_value=upside_value,
            downside_value=downside_value,
            minimum_reward_risk=MIN_REWARD_RISK,
        )
    )

    scenario_decision = (
        "ENTRY_TEST_PASSES"
        if reward_risk >= MIN_REWARD_RISK
        else "WAIT_FOR_ENTRY"
    )

    quote_item = (
        (quote.get("items") or [{}])[0]
        if quote.get("items")
        else {}
    )

    stress_id = (
        f"generic_capital_stress_"
        f"{uuid4().hex}"
    )

    result = {
        "generic_capital_stress_id":
            stress_id,

        "policy_version":
            POLICY_VERSION,

        "model":
            "GENERIC_PUBLIC_COMPANY_CAPITAL_STRESS_V1",

        "model_type":
            "SCENARIO_NOT_FORECAST",

        "case_id":
            case_id,

        "ticker":
            ticker,

        "baseline": {
            "current_price":
                round(current_price, 4),

            "forward_eps":
                round(forward_eps, 4),

            "current_forward_pe":
                round(
                    current_forward_pe,
                    4,
                ),
        },

        "upside_scenario": {
            "eps_change_pct":
                UPSIDE_EPS_CHANGE_PCT,

            "multiple_change_pct":
                UPSIDE_MULTIPLE_CHANGE_PCT,

            "scenario_eps":
                round(upside_eps, 4),

            "scenario_multiple":
                round(upside_multiple, 4),

            "reference_value":
                round(upside_value, 4),

            "assumption_only":
                True,
        },

        "downside_scenario": {
            "eps_change_pct":
                DOWNSIDE_EPS_CHANGE_PCT,

            "multiple_change_pct":
                DOWNSIDE_MULTIPLE_CHANGE_PCT,

            "scenario_eps":
                round(downside_eps, 4),

            "scenario_multiple":
                round(downside_multiple, 4),

            "reference_value":
                round(downside_value, 4),

            "assumption_only":
                True,
        },

        "capital_measurement": {
            "upside_dollars":
                round(upside_dollars, 4),

            "downside_dollars":
                round(downside_dollars, 4),

            "reward_risk":
                round(reward_risk, 4),

            "minimum_reward_risk":
                MIN_REWARD_RISK,

            "maximum_qualifying_entry":
                round(
                    maximum_qualifying_entry,
                    4,
                ),

            "scenario_decision":
                scenario_decision,
        },

        "input_lineage": {
            "quote_origin":
                "GENERIC_PUBLIC_COMPANY_EXACT_QUOTE",

            "quote_provider":
                quote.get("provider"),

            "quote_timestamp":
                quote_item.get("timestamp"),

            "consensus_primary_evidence_id":
                consensus_record.get(
                    "primary_evidence_id"
                ),

            "consensus_source":
                consensus_record.get(
                    "source_name"
                ),
        },

        "governance": {
            "verified_inputs": [
                "current_price",
                "forward_eps",
            ],

            "model_assumptions": [
                "upside_eps_change_pct",
                "downside_eps_change_pct",
                "upside_multiple_change_pct",
                "downside_multiple_change_pct",
            ],

            "forecast_claim":
                False,

            "measurement_only":
                True,

            "capital_allocation_allowed":
                False,

            "position_sizing_allowed":
                False,

            "paper_order_permission":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },

        "created_at":
            utc_now(),

        "paper_mode":
            True,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }

    record_object(
        stress_id,
        "generic_capital_stress",
        case_id,
        result,
        topic=case.get("topic"),
    )

    record_event(
        case_id,
        "GENERIC_PUBLIC_COMPANY_CAPITAL_STRESS_RECORDED",
        entity_id=stress_id,
        payload={
            "ticker": ticker,
            "reward_risk":
                result[
                    "capital_measurement"
                ]["reward_risk"],
            "scenario_decision":
                scenario_decision,
            "measurement_only":
                True,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        },
    )

    return result
