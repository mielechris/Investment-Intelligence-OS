from __future__ import annotations

from typing import Any

from fastapi import APIRouter

import agent_calibration_weighting
import cross_case_memory
import evidence_depth_engine
import portfolio_intelligence


router = APIRouter()
MANIFEST_VERSION = "intelligence-learning-pre-freeze-v1"
AUTONOMOUS_BATCHES_COMPLETE = [1, 2, 3, 5, 6, 7]
USER_GATED_BATCH = 4
FINAL_FREEZE_BATCH = 8


def intelligence_safety_manifest() -> dict[str, Any]:
    calibration = agent_calibration_weighting.build_calibration_policy()
    memory_plan = cross_case_memory.cross_case_memory_plan()
    portfolio_plan = portfolio_intelligence.portfolio_rank_plan()

    invariant_checks = {
        "cross_case_memory_not_qualification_evidence": memory_plan["qualification_evidence"] is False,
        "cross_case_memory_not_gap_resolution_evidence": memory_plan["gap_resolution_eligible"] is False,
        "cross_case_memory_no_judgment_cache": memory_plan["judgment_output_cache"] is False,
        "calibration_requires_meaningful_sample": agent_calibration_weighting.MIN_DECISIVE_OBSERVATIONS >= 20,
        "calibration_cannot_override_committee": calibration["committee_override"] is False,
        "portfolio_rank_cannot_allocate_capital": portfolio_plan["capital_allocation_allowed"] is False,
        "portfolio_rank_cannot_size_positions": portfolio_plan["position_sizing_allowed"] is False,
        "evidence_depth_has_bounded_fact_count": evidence_depth_engine.MAX_FACTS_PER_REQUIREMENT <= 6,
    }

    return {
        "manifest_version": MANIFEST_VERSION,
        "autonomous_batches_complete": list(AUTONOMOUS_BATCHES_COMPLETE),
        "user_gated_batch": USER_GATED_BATCH,
        "final_freeze_batch": FINAL_FREEZE_BATCH,
        "invariant_checks": invariant_checks,
        "all_current_invariants_pass": all(invariant_checks.values()),
        "final_intelligence_freeze_ready": False,
        "freeze_blockers": [
            "Batch 4 Judgment Bank integration policy requires user approval",
            "Final Batch 8 freeze must be rerun after Batch 4 integration is tested",
        ],
        "automatic_configuration_change": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/intelligence/safety-manifest")
def intelligence_manifest():
    return intelligence_safety_manifest()
