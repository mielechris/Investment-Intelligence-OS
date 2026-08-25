from __future__ import annotations

from typing import Any

from fastapi import APIRouter

import grok_social_intelligence as grok_social
from grok_citation_compat import COMPAT_VERSION, install_grok_citation_compat

# xAI Responses API exposes the complete source list on response.citations. Install
# the compatibility shim before any live experiment call so real X citations are
# considered by the existing firewall without trusting URLs from model prose.
install_grok_citation_compat(grok_social)

from grok_ab_benchmark import grok_ab_plan
from grok_opportunity_discovery import grok_opportunity_plan
from v1_consolidation_manifest import v1_consolidation_manifest


grok_plan = grok_social.grok_plan
router = APIRouter()
BATCH_NAME = "Batch 7 — Grok Experimental Intelligence Integration"
BASELINE_TAG = "IIOS-V1.0"
EXPERIMENT_BRANCH = "experiment/grok-intelligence-v1"


def grok_experiment_manifest() -> dict[str, Any]:
    baseline = v1_consolidation_manifest()
    context = grok_plan()
    ab = grok_ab_plan()
    opportunities = grok_opportunity_plan()

    invariants = {
        "v1_baseline_excludes_grok": baseline.get("grok_included") is False,
        "grok_automatic_injection_disabled": context.get("automatic_injection") is False,
        "grok_not_qualification_evidence": context.get("qualification_evidence") is False,
        "grok_not_gap_resolution_evidence": context.get("gap_resolution_eligible") is False,
        "grok_no_fact_resolution_authority": context.get("fact_resolution_authority") is False,
        "grok_no_committee_override": context.get("committee_override") is False,
        "grok_no_capital_authority": context.get("capital_authority") is False,
        "grok_not_trade_signal": context.get("trade_signal") is False,
        "ab_uses_same_case": ab.get("same_case") is True,
        "ab_uses_ledger_snapshots": ab.get("same_ledger_snapshot") is True,
        "ab_does_not_pollute_live_history": ab.get("live_decision_history_pollution") is False,
        "ab_cannot_auto_promote_architecture": ab.get("architecture_promotion_automatic") is False,
        "grok_nomination_cannot_create_case_directly": opportunities.get("grok_can_create_governed_case_directly") is False,
        "grok_nominations_require_standard_iios_revalidation": opportunities.get("standard_opportunity_score_required") is True,
        "grok_nominations_do_not_auto_promote": opportunities.get("automatic_promotion") is False,
        "grok_nominations_do_not_auto_run_agents": opportunities.get("automatic_agent_run") is False,
        "xai_top_level_citation_compat_installed": getattr(grok_social, "_xai_citation_compat_installed", False) is True,
    }
    all_pass = all(invariants.values())
    return {
        "batch": BATCH_NAME,
        "baseline_tag": BASELINE_TAG,
        "experiment_branch": EXPERIMENT_BRANCH,
        "experiment_status": "READY_FOR_LIVE_XAI_SMOKE_TEST" if all_pass else "SAFETY_BLOCKED",
        "xai_api_configured": context.get("api_key_configured"),
        "grok_runtime_enabled": context.get("enabled"),
        "model": context.get("model"),
        "x_search_tool": True,
        "citation_compat_version": COMPAT_VERSION,
        "invariant_checks": invariants,
        "all_invariants_pass": all_pass,
        "permanent_factory_promotion_ready": False,
        "promotion_requirements": [
            "multi-case IIOS vs IIOS+Grok A/B sample",
            "discovery lead-time measurement",
            "false-positive rate measurement",
            "decision-quality comparison",
            "realized paper-return comparison",
        ],
        "main_baseline_should_remain_unchanged": True,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/grok/experiment/manifest")
def get_grok_experiment_manifest():
    return grok_experiment_manifest()
