from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from grok_discovery_lead_time import build_discovery_lead_time_report
from grok_experiment_scorecard import build_grok_scorecard
from grok_false_positive_tracker import build_false_positive_report
from grok_paper_value import build_paper_value_report
from ledger import utc_now


router = APIRouter()
SCORECARD_VERSION = "grok-value-proof-v2"


def build_grok_value_scorecard() -> dict[str, Any]:
    repeatability = build_grok_scorecard()
    lead_time = build_discovery_lead_time_report()
    false_positive = build_false_positive_report()
    paper = build_paper_value_report()

    milestones = {
        "four_case_repeatability_sample": int(repeatability.get("valid_repeatability_cases") or 0) >= 4,
        "prospective_lead_time_pairs_measured": int(lead_time.get("prospective_pair_count") or 0) > 0,
        "false_positive_sample_resolved": int(false_positive.get("resolved_count") or 0) > 0,
        "shadow_measurement_ledger_ready": paper.get("shadow_measurement_ledger_ready") is True,
        "paper_outcomes_observed": int(paper.get("cases_with_realized_return") or 0) > 0,
        "dual_arm_pnl_ready": paper.get("return_comparison_ready") is True,
    }

    blockers: list[str] = []
    if not milestones["prospective_lead_time_pairs_measured"]:
        blockers.append("prospective discovery lead-time sample required")
    if not milestones["false_positive_sample_resolved"]:
        blockers.append("resolved Grok nomination false-positive sample required")
    if not milestones["shadow_measurement_ledger_ready"]:
        blockers.append("decision-shadow ledger enrollment required")
    if not milestones["paper_outcomes_observed"]:
        blockers.append("realized paper outcomes required")
    if not milestones["dual_arm_pnl_ready"]:
        blockers.append("governed dual-arm paper P&L comparison required")

    return {
        "scorecard_version": SCORECARD_VERSION,
        "status": "VALUE_PROOF_IN_PROGRESS" if milestones["four_case_repeatability_sample"] else "REPEATABILITY_SAMPLE_INCOMPLETE",
        "milestones": milestones,
        "repeatability": {
            "valid_cases": repeatability.get("valid_repeatability_cases"),
            "mean_confidence_delta": (repeatability.get("aggregate") or {}).get("mean_confidence_delta"),
            "median_confidence_delta": (repeatability.get("aggregate") or {}).get("median_confidence_delta"),
            "disposition_change_cases": (repeatability.get("aggregate") or {}).get("disposition_change_cases"),
            "all_guards_clean": (repeatability.get("aggregate") or {}).get("all_guards_clean"),
        },
        "lead_time": {
            "measurable_pair_count": lead_time.get("measurable_pair_count"),
            "prospective_pair_count": lead_time.get("prospective_pair_count"),
            "grok_earlier_count": lead_time.get("grok_earlier_count"),
            "iios_earlier_count": lead_time.get("iios_earlier_count"),
            "prospective_grok_earlier_count": lead_time.get("prospective_grok_earlier_count"),
            "prospective_iios_earlier_count": lead_time.get("prospective_iios_earlier_count"),
            "median_grok_lead_minutes": lead_time.get("median_grok_lead_minutes"),
            "prospective_median_grok_lead_minutes": lead_time.get("prospective_median_grok_lead_minutes"),
        },
        "false_positive": {
            "nomination_count": false_positive.get("nomination_count"),
            "resolved_count": false_positive.get("resolved_count"),
            "validated_count": false_positive.get("validated_count"),
            "rejected_count": false_positive.get("rejected_count"),
            "false_positive_rate": false_positive.get("false_positive_rate"),
        },
        "paper_value": {
            "valid_ab_case_count": paper.get("valid_ab_case_count"),
            "cases_with_position_monitor": paper.get("cases_with_position_monitor"),
            "cases_with_realized_return": paper.get("cases_with_realized_return"),
            "shadow_pair_count": paper.get("shadow_pair_count"),
            "shadow_snapshot_count": paper.get("shadow_snapshot_count"),
            "differentiated_action_pair_count": paper.get("differentiated_action_pair_count"),
            "shadow_measurement_ledger_ready": paper.get("shadow_measurement_ledger_ready"),
            "return_comparison_ready": paper.get("return_comparison_ready"),
        },
        "recommendation": "CONTINUE_VALUE_PROOF",
        "permanent_factory_promotion_ready": False,
        "promotion_blockers": blockers,
        "automatic_configuration_change": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.get("/grok/value/scorecard")
def get_grok_value_scorecard():
    return build_grok_value_scorecard()
