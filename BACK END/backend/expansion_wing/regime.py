from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Availability

DIMENSIONS = ("growth", "inflation", "employment", "fed_direction", "yield_curve", "liquidity",
              "credit_conditions", "volatility", "commodities", "currencies")


def direct_regime(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing = [key for key in DIMENSIONS if not signals.get(key)]
    stale = [key for key, value in signals.items() if str(value.get("freshness", "UNKNOWN")) not in {"CURRENT", "AVAILABLE"}]
    if missing:
        availability = Availability.INCOMPLETE
        state = "TRANSITIONAL"
    elif stale:
        availability = Availability.STALE
        state = "TRANSITIONAL"
    else:
        risk_score = sum(float(signals[key].get("risk_score", 0)) for key in DIMENSIONS) / len(DIMENSIONS)
        state = "RISK_OFF" if risk_score >= 0.35 else "RISK_ON" if risk_score <= -0.20 else "TRANSITIONAL"
        availability = Availability.CURRENT
    return {"state": state, "availability": availability, "dimensions": signals, "missing": missing,
            "stale": stale, "automatic_allocation_authority": False}


@dataclass(frozen=True)
class AllocationCandidate:
    passport_id: str
    expected_return: float
    expected_loss: float
    probability: float
    drawdown: float
    time_to_thesis_days: float
    liquidity_score: float
    correlation_penalty: float
    evidence_quality: float
    capital_complexity: float
    cash_opportunity_cost: float


def allocation_score(candidate: AllocationCandidate) -> dict[str, Any]:
    if not 0 <= candidate.probability <= 1:
        raise ValueError("probability must be between zero and one")
    weighted = candidate.probability * candidate.expected_return - (1 - candidate.probability) * candidate.expected_loss
    utility = (weighted * candidate.evidence_quality * candidate.liquidity_score
               - candidate.drawdown - candidate.correlation_penalty - candidate.capital_complexity
               - candidate.cash_opportunity_cost - min(candidate.time_to_thesis_days / 3650, 0.25))
    return {"passport_id": candidate.passport_id, "probability_weighted_outcome": round(weighted, 6),
            "allocation_utility": round(utility, 6), "projected_return_only_ranking": False,
            "paper_only": True, "automatic_allocation": False}
