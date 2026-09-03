from __future__ import annotations

from copy import deepcopy
from typing import Any

POLICIES = {
    "CURRENT_GOVERNED": {"research_score": 0.70, "promotion_score": 0.75},
    "BALANCED": {"research_score": 0.60, "promotion_score": 0.65},
    "EXPLORATORY": {"research_score": 0.45, "promotion_score": 0.50},
}
IMMUTABLE_GATES = ("authority", "provenance", "data_integrity", "live_execution")


def observe_counterfactual(opportunity: dict[str, Any], policy_name: str) -> dict[str, Any]:
    if policy_name not in POLICIES:
        raise ValueError("unknown strictness policy")
    row = deepcopy(opportunity)
    gates = row.get("gates") or {}
    failed_immutable = [key for key in IMMUTABLE_GATES if gates.get(key) is not True]
    score = float(row.get("research_score") or 0)
    threshold = POLICIES[policy_name]["promotion_score"]
    would_promote = not failed_immutable and score >= threshold
    return {
        "policy": policy_name, "entered_universe": bool(row.get("entered_universe")),
        "radar_detected": bool(row.get("radar_detected")), "candidate_created": bool(row.get("candidate_created")),
        "evidence_gate": row.get("evidence_gate", "UNKNOWN"), "committee_result": row.get("committee_result", "UNKNOWN"),
        "risk_result": row.get("risk_result", "UNKNOWN"), "paper_eligibility": row.get("paper_eligibility", "UNKNOWN"),
        "detection_latency_seconds": row.get("detection_latency_seconds"),
        "responsible_threshold": "promotion_score", "threshold": threshold,
        "would_promote_for_research": would_promote, "immutable_gate_failures": failed_immutable,
        "hypothetical_return_after_costs": row.get("hypothetical_return_after_costs"),
        "hypothetical_drawdown_after_costs": row.get("hypothetical_drawdown_after_costs"),
        "read_only": True, "automatic_application": False,
    }
