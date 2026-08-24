from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ledger import (
    get_object,
    latest_object,
    list_objects,
    record_event,
    record_object,
    utc_now,
)
from valuation_market_micron_filing_fallback import micron_ttm_eps


router = APIRouter()

DEFAULT_ASP_DECLINES = (-0.10, -0.20)
DEFAULT_EARNINGS_ELASTICITIES = (1.0, 1.5, 2.0)
DEFAULT_VALUATION_MULTIPLES = (12.0, 15.0, 18.0)


def _positive(value: float, name: str) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build_cycle_normalized_stress(
    *,
    current_price: float,
    forward_eps: float,
    ttm_eps: float,
    diluted_shares_m: float,
    asp_declines: tuple[float, ...] = DEFAULT_ASP_DECLINES,
    earnings_elasticities: tuple[float, ...] = DEFAULT_EARNINGS_ELASTICITIES,
    valuation_multiples: tuple[float, ...] = DEFAULT_VALUATION_MULTIPLES,
) -> dict[str, Any]:
    """
    Transparent scenario engine.

    Verified inputs:
      - current market price
      - current forward EPS consensus
      - filing-backed TTM EPS
      - filed diluted share count

    Model assumptions:
      - ASP decline scenarios
      - earnings elasticity to ASP
      - valuation multiple scenarios

    This engine does NOT claim the elasticity assumptions are observed facts.
    """

    current_price = _positive(current_price, "current_price")
    forward_eps = _positive(forward_eps, "forward_eps")
    ttm_eps = _positive(ttm_eps, "ttm_eps")
    diluted_shares_m = _positive(
        diluted_shares_m,
        "diluted_shares_m",
    )

    normalized_low = min(ttm_eps, forward_eps)
    normalized_high = max(ttm_eps, forward_eps)
    normalized_mid = round(
        (normalized_low + normalized_high) / 2.0,
        4,
    )

    baseline = {
        "current_price": round(current_price, 4),
        "forward_eps": round(forward_eps, 4),
        "ttm_eps": round(ttm_eps, 4),
        "diluted_shares_m": round(diluted_shares_m, 4),
        "forward_pe": round(
            current_price / forward_eps,
            4,
        ),
        "ttm_pe": round(
            current_price / ttm_eps,
            4,
        ),
        "forward_net_income_b": round(
            forward_eps * diluted_shares_m / 1000.0,
            4,
        ),
    }

    normalized_cycle = {
        "method": (
            "MECHANICAL_RANGE_BETWEEN_FILED_TTM_"
            "AND_CURRENT_FORWARD_CONSENSUS"
        ),
        "low_eps": round(normalized_low, 4),
        "mid_eps": normalized_mid,
        "high_eps": round(normalized_high, 4),
        "mid_pe_at_current_price": round(
            current_price / normalized_mid,
            4,
        ),
        "forecast_claim": False,
    }

    scenarios: list[dict[str, Any]] = []

    for asp_decline in asp_declines:
        decline = abs(float(asp_decline))

        if decline <= 0 or decline >= 1:
            raise ValueError(
                "ASP decline assumptions must be between 0 and 1"
            )

        for elasticity in earnings_elasticities:
            elasticity = _positive(
                elasticity,
                "earnings_elasticity",
            )

            earnings_haircut = min(
                0.95,
                decline * elasticity,
            )

            stressed_eps = max(
                0.01,
                forward_eps * (1.0 - earnings_haircut),
            )

            stressed_income_b = (
                stressed_eps
                * diluted_shares_m
                / 1000.0
            )

            price_targets = {
                f"{multiple:g}x": round(
                    stressed_eps * float(multiple),
                    4,
                )
                for multiple in valuation_multiples
            }

            scenarios.append(
                {
                    "asp_decline_pct": round(
                        decline * 100.0,
                        2,
                    ),
                    "earnings_elasticity_to_asp": round(
                        elasticity,
                        2,
                    ),
                    "earnings_haircut_pct": round(
                        earnings_haircut * 100.0,
                        2,
                    ),
                    "stressed_eps": round(
                        stressed_eps,
                        4,
                    ),
                    "stressed_net_income_b": round(
                        stressed_income_b,
                        4,
                    ),
                    "pe_at_current_price": round(
                        current_price / stressed_eps,
                        4,
                    ),
                    "price_targets": price_targets,
                    "assumption_only": True,
                    "observed_fact": False,
                }
            )

    return {
        "model": "MU_CYCLE_NORMALIZED_DOWNSIDE_STRESS_V1",
        "model_type": "SCENARIO_NOT_FORECAST",
        "baseline": baseline,
        "normalized_cycle": normalized_cycle,
        "scenarios": scenarios,
        "governance": {
            "verified_input_fields": [
                "current_price",
                "forward_eps",
                "ttm_eps",
                "diluted_shares_m",
            ],
            "model_assumption_fields": [
                "asp_decline_pct",
                "earnings_elasticity_to_asp",
                "valuation_multiple",
            ],
            "may_resolve_primary_fact": False,
            "may_authorize_trade": False,
            "paper_buy_enabled": False,
        },
    }


def _latest_primary_record(
    case_id: str,
    lane: str,
    fact_key: str,
) -> dict[str, Any] | None:
    for row in reversed(
        list_objects(case_id, "primary_evidence_record")
    ):
        if row.get("lane") != lane:
            continue
        if row.get("fact_key") != fact_key:
            continue
        if row.get("gap_resolution_eligible") is False:
            continue
        return row
    return None


def _forward_eps_from_claim(claim: str) -> float | None:
    match = re.search(
        r"\bEPS\s*=\s*([0-9]+(?:\.[0-9]+)?)",
        str(claim or ""),
        flags=re.I,
    )
    return float(match.group(1)) if match else None


def _diluted_shares_from_claim(claim: str) -> float | None:
    match = re.search(
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s+million\s+diluted\s+shares",
        str(claim or ""),
        flags=re.I,
    )
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _latest_analyst_revision_record(
    case_id: str,
) -> dict[str, Any] | None:
    for row in reversed(
        list_objects(case_id, "institutional_signal_record")
    ):
        if row.get("lane") != "analyst_revisions":
            continue
        if not row.get("fresh"):
            continue
        return row
    return None


def _effective_quote(
    snapshot: dict[str, Any],
    quote_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(quote_override, dict):
        return quote_override
    return snapshot.get("quote") or {}


def build_live_cycle_stress(
    case_id: str,
    *,
    quote_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case = get_object(case_id)

    if not case:
        raise ValueError(f"Unknown case: {case_id}")

    snapshot = latest_object(
        "monitor_snapshot",
        case_id=case_id,
    ) or {}

    quote = _effective_quote(
        snapshot,
        quote_override,
    )

    try:
        current_price = float(quote.get("current_price"))
    except (TypeError, ValueError):
        raise ValueError(
            "Current live quote required before cycle stress"
        )

    consensus_record = _latest_primary_record(
        case_id,
        "valuation_market",
        "consensus",
    )

    if not consensus_record:
        raise ValueError(
            "Governed forward EPS consensus required"
        )

    forward_eps = _forward_eps_from_claim(
        str(consensus_record.get("claim") or "")
    )

    if forward_eps is None:
        raise ValueError(
            "Could not parse governed forward EPS consensus"
        )

    share_record = _latest_primary_record(
        case_id,
        "valuation_market",
        "diluted_shares",
    )

    if not share_record:
        raise ValueError(
            "Filed diluted share count required"
        )

    diluted_shares_m = _diluted_shares_from_claim(
        str(share_record.get("claim") or "")
    )

    if diluted_shares_m is None:
        raise ValueError(
            "Could not parse filed diluted share count"
        )

    result = build_cycle_normalized_stress(
        current_price=current_price,
        forward_eps=forward_eps,
        ttm_eps=micron_ttm_eps(),
        diluted_shares_m=diluted_shares_m,
    )

    revisions = _latest_analyst_revision_record(case_id)

    stress_id = f"cycle_valuation_{uuid4().hex}"

    payload = {
        **result,
        "cycle_valuation_stress_id": stress_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "input_lineage": {
            "quote_origin": (
                "GAP_HUNTER_EXACT_QUOTE"
                if quote_override is not None
                else "MONITOR_SNAPSHOT"
            ),
            "quote_snapshot_id": snapshot.get(
                "monitor_snapshot_id"
            ),
            "quote_source": quote.get("provider"),
            "quote_timestamp": (
                ((quote.get("items") or [{}])[0]).get(
                    "timestamp"
                )
                if quote.get("items")
                else None
            ),
            "consensus_record_id": consensus_record.get(
                "primary_evidence_id"
            ),
            "consensus_source": consensus_record.get(
                "source_name"
            ),
            "diluted_share_record_id": share_record.get(
                "primary_evidence_id"
            ),
            "diluted_share_source": share_record.get(
                "source_name"
            ),
        },
        "analyst_revisions": {
            "status": (
                "CURRENT"
                if revisions
                else "NO_CURRENT_RECORD"
            ),
            "summary": (
                revisions.get("summary")
                if revisions
                else None
            ),
            "directional_context": (
                revisions.get("directional_context")
                if revisions
                else None
            ),
            "data_as_of": (
                revisions.get("data_as_of")
                if revisions
                else None
            ),
            "institutional_signal_id": (
                revisions.get("institutional_signal_id")
                if revisions
                else None
            ),
        },
        "analysis_type":
            "MU_CYCLE_NORMALIZED_DOWNSIDE_STRESS_V1",
        "governed_analysis": True,
        "verified_inputs_complete": True,
        "assumptions_explicit": True,
        "gap_resolution_eligible": False,
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }

    record_object(
        stress_id,
        "cycle_valuation_stress",
        case_id,
        payload,
        topic=case.get("topic"),
    )

    record_event(
        case_id,
        "CYCLE_NORMALIZED_VALUATION_COMPLETE",
        entity_id=stress_id,
        payload={
            "model": payload["model"],
            "current_price": payload["baseline"][
                "current_price"
            ],
            "forward_eps": payload["baseline"][
                "forward_eps"
            ],
            "normalized_mid_eps": payload[
                "normalized_cycle"
            ]["mid_eps"],
            "analyst_revisions_status": payload[
                "analyst_revisions"
            ]["status"],
            "trade_execution_permission": False,
        },
    )

    return payload


def cycle_normalized_evidence(
    case_id: str,
) -> list[dict[str, Any]]:
    stress = latest_object(
        "cycle_valuation_stress",
        case_id=case_id,
    )

    if not stress:
        return []

    baseline = stress.get("baseline") or {}
    cycle = stress.get("normalized_cycle") or {}

    scenarios = stress.get("scenarios") or []

    downside_10x15 = next(
        (
            row for row in scenarios
            if row.get("asp_decline_pct") == 10.0
            and row.get(
                "earnings_elasticity_to_asp"
            ) == 1.5
        ),
        None,
    )

    downside_20x20 = next(
        (
            row for row in scenarios
            if row.get("asp_decline_pct") == 20.0
            and row.get(
                "earnings_elasticity_to_asp"
            ) == 2.0
        ),
        None,
    )

    claim = (
        "Governed MU cycle-normalized downside scenario. "
        f"Verified current price={baseline.get('current_price')}; "
        f"forward EPS={baseline.get('forward_eps')}; "
        f"filed TTM EPS={baseline.get('ttm_eps')}; "
        f"diluted shares={baseline.get('diluted_shares_m')} million. "
        f"Mechanical normalized EPS range="
        f"{cycle.get('low_eps')} to {cycle.get('high_eps')} "
        f"with midpoint={cycle.get('mid_eps')}. "
    )

    if downside_10x15:
        claim += (
            "MODEL ASSUMPTION: 10% ASP decline at 1.5x "
            f"earnings elasticity produces stressed EPS="
            f"{downside_10x15.get('stressed_eps')}. "
        )

    if downside_20x20:
        claim += (
            "MODEL ASSUMPTION: 20% ASP decline at 2.0x "
            f"earnings elasticity produces stressed EPS="
            f"{downside_20x20.get('stressed_eps')}. "
        )

    claim += (
        "Elasticity and valuation-multiple assumptions are "
        "scenario inputs, not observed facts. This analysis "
        "cannot resolve a primary evidence fact or authorize "
        "a trade."
    )

    return [
        {
            "source":
                "IIOS Governed Cycle-Normalized Valuation Engine",
            "source_type": "governed_analysis",
            "evidence_type": "cycle_stress",
            "url": "iios://cycle-normalized-valuation",
            "title":
                "MU governed cycle-normalized downside stress",
            "claim": claim,
            "timestamp": stress.get("created_at"),
            "reliability_score": 0.90,
            "gap_resolution_eligible": False,
            "analysis_type":
                "MU_CYCLE_NORMALIZED_DOWNSIDE_STRESS_V1",
            "governed_analysis": True,
            "verified_inputs_complete": True,
            "assumptions_explicit": True,
            "may_resolve_primary_fact": False,
            "may_authorize_trade": False,
            "paper_buy_enabled": False,
            "cycle_valuation_stress_id": stress.get(
                "cycle_valuation_stress_id"
            ),
            "analyst_revisions_status": (
                stress.get("analyst_revisions") or {}
            ).get("status"),
        }
    ]


@router.post("/cycle-valuation/{case_id}/run")
def run_cycle_valuation(case_id: str):
    try:
        return build_live_cycle_stress(case_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


@router.get("/cycle-valuation/{case_id}")
def get_cycle_valuation(case_id: str):
    stress = latest_object(
        "cycle_valuation_stress",
        case_id=case_id,
    )
    if not stress:
        raise HTTPException(
            status_code=404,
            detail="No cycle valuation stress exists",
        )
    return stress
