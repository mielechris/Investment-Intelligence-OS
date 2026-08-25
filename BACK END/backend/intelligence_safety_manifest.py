from __future__ import annotations

from typing import Any

from fastapi import APIRouter

import agent_calibration_weighting
import cross_case_memory
import evidence_depth_engine
import historical_regime_memory
import judgment_bank_integration
import portfolio_intelligence


router = APIRouter()
MANIFEST_VERSION = "intelligence-learning-v1"
BATCHES_COMPLETE = [1, 2, 3, 4, 5, 6, 7, 8]
USER_APPROVED_BATCH = 4
FINAL_FREEZE_BATCH = 8


def intelligence_safety_manifest() -> dict[str, Any]:
    calibration = agent_calibration_weighting.build_calibration_policy()
    memory_plan = cross_case_memory.cross_case_memory_plan()
    judgment_plan = judgment_bank_integration.judgment_bank_plan()
    portfolio_plan = portfolio_intelligence.portfolio_rank_plan()

    invariant_checks = {
        "evidence_depth_has_bounded_fact_count": evidence_depth_engine.MAX_FACTS_PER_REQUIREMENT <= 6,
        "historical_analogs_are_bounded": historical_regime_memory.MAX_ANALOGS <= 8,
        "cross_case_memory_not_qualification_evidence": memory_plan["qualification_evidence"] is False,
        "cross_case_memory_not_gap_resolution_evidence": memory_plan["gap_resolution_eligible"] is False,
        "cross_case_memory_no_judgment_cache": memory_plan["judgment_output_cache"] is False,
        "judgment_bank_requires_human_approval": judgment_plan["human_approval_required"] is True,
        "judgment_bank_low_risk_only": judgment_plan["low_restriction_risk_only"] is True,
        "judgment_bank_untrusted_advisory_framing": judgment_plan["untrusted_advisory_text"] is True,
        "judgment_bank_not_qualification_evidence": judgment_plan["qualification_evidence"] is False,
        "judgment_bank_not_gap_resolution_evidence": judgment_plan["gap_resolution_eligible"] is False,
        "judgment_bank_no_fact_resolution_authority": judgment_plan["fact_resolution_authority"] is False,
        "judgment_bank_no_committee_override": judgment_plan["committee_override"] is False,
        "judgment_bank_no_capital_authority": judgment_plan["capital_authority"] is False,
        "judgment_bank_no_output_cache": judgment_plan["judgment_output_cache"] is False,
        "calibration_requires_meaningful_sample": agent_calibration_weighting.MIN_DECISIVE_OBSERVATIONS >= 20,
        "calibration_cannot_override_committee": calibration["committee_override"] is False,
        "portfolio_rank_cannot_allocate_capital": portfolio_plan["capital_allocation_allowed"] is False,
        "portfolio_rank_cannot_size_positions": portfolio_plan["position_sizing_allowed"] is False,
    }

    all_pass = all(invariant_checks.values())
    blockers = [key for key, passed in invariant_checks.items() if not passed]

    return {
        "manifest_version": MANIFEST_VERSION,
        "batches_complete": list(BATCHES_COMPLETE),
        "user_approved_batch": USER_APPROVED_BATCH,
        "final_freeze_batch": FINAL_FREEZE_BATCH,
        "invariant_checks": invariant_checks,
        "all_current_invariants_pass": all_pass,
        "final_intelligence_freeze_ready": all_pass,
        "intelligence_v1_frozen": all_pass,
        "freeze_blockers": blockers,
        "approved_judgment_policy": {
            "policy_version": judgment_plan["policy_version"],
            "human_approved_low_risk_only": True,
            "advisory_context_only": True,
            "relevant_desks_only": True,
            "qualification_evidence": False,
            "gap_resolution_eligible": False,
            "fact_resolution_authority": False,
            "committee_override": False,
            "capital_authority": False,
        },
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
