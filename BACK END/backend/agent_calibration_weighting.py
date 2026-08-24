from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from learning_loop import build_agent_scorecards


router = APIRouter()
AGENT_KEYS = (
    "policy",
    "macro",
    "fundamentals",
    "market_structure",
    "commodities",
    "geo_weather",
    "skeptic",
    "portfolio",
)
MIN_DECISIVE_OBSERVATIONS = 20
MIN_CALIBRATION_SCORE = 0.45
MIN_WEIGHT = 0.75
MAX_WEIGHT = 1.25


def _weight(calibration: float) -> float:
    value = MIN_WEIGHT + (MAX_WEIGHT - MIN_WEIGHT) * max(0.0, min(1.0, calibration))
    return round(max(MIN_WEIGHT, min(MAX_WEIGHT, value)), 4)


def build_calibration_policy() -> dict[str, Any]:
    scorecards = {str(row.get("agent_key")): row for row in build_agent_scorecards()}
    agents: dict[str, dict[str, Any]] = {}
    all_mature = True
    for key in AGENT_KEYS:
        row = scorecards.get(key) or {}
        decisive = int(row.get("decisive_observations") or 0)
        calibration = float(row.get("average_calibration_score") or 0.0)
        mature = decisive >= MIN_DECISIVE_OBSERVATIONS and calibration >= MIN_CALIBRATION_SCORE
        all_mature = all_mature and mature
        agents[key] = {
            "agent_key": key,
            "decisive_observations": decisive,
            "average_calibration_score": round(calibration, 4),
            "sample_mature": mature,
            "proposed_weight": _weight(calibration) if mature else 1.0,
        }

    # Dynamic influence is deliberately all-or-nothing at v1. This prevents a few
    # early lucky outcomes from making one desk dominate an immature committee.
    weighting_active = all_mature
    if not weighting_active:
        for row in agents.values():
            row["effective_weight"] = 1.0
    else:
        for row in agents.values():
            row["effective_weight"] = row["proposed_weight"]

    return {
        "weighting_active": weighting_active,
        "activation_rule": f"all 8 desks need >= {MIN_DECISIVE_OBSERVATIONS} decisive observations and calibration >= {MIN_CALIBRATION_SCORE}",
        "agents": agents,
        "weight_floor": MIN_WEIGHT,
        "weight_ceiling": MAX_WEIGHT,
        "committee_override": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def install_calibration_context(module) -> None:
    """Expose mature calibration to committee synthesis without bypassing guards."""
    if getattr(module, "_calibration_context_installed", False):
        return
    module._calibration_context_installed = True
    original = module._synthesize_committee

    def calibrated_synthesize(*args, **kwargs):
        policy = build_calibration_policy()
        specialists = kwargs.get("specialists")
        if policy["weighting_active"] and isinstance(specialists, dict):
            enriched = {}
            for key, row in specialists.items():
                weight = (policy["agents"].get(key) or {}).get("effective_weight", 1.0)
                enriched[key] = {**row, "historical_calibration_weight": weight}
            kwargs = {**kwargs, "specialists": enriched}
        result = original(*args, **kwargs)
        return {
            **result,
            "calibration_weighting_active": policy["weighting_active"],
            "calibration_weights": {
                key: row["effective_weight"] for key, row in policy["agents"].items()
            },
        }

    module._synthesize_committee = calibrated_synthesize


@router.get("/intelligence/agent-calibration")
def agent_calibration():
    return build_calibration_policy()
