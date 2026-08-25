from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

import grok_opportunity_discovery
from grok_discovery_lead_time import build_discovery_lead_time_report
from grok_false_positive_tracker import build_false_positive_report


router = APIRouter()
POLICY_VERSION = "grok-value-probe-v1"
MAX_PROBE_CANDIDATES = 5


def run_value_probe(query: str, *, days: int = 2, max_candidates: int = 5) -> dict[str, Any]:
    max_candidates = max(1, min(int(max_candidates), MAX_PROBE_CANDIDATES))
    discovery = grok_opportunity_discovery.discover_grok_opportunities(
        query,
        days=days,
        max_candidates=max_candidates,
        persist=True,
    )
    resolved: list[dict[str, Any]] = []
    for nomination in discovery.get("nominations") or []:
        candidate_id = str(nomination.get("grok_opportunity_candidate_id") or "")
        if not candidate_id:
            continue
        try:
            result = grok_opportunity_discovery.revalidate_grok_candidate(candidate_id)
            standard = result.get("standard_candidate") or {}
            resolved.append({
                "grok_opportunity_candidate_id": candidate_id,
                "ticker": nomination.get("ticker"),
                "status": "REVALIDATED",
                "standard_candidate_id": standard.get("opportunity_candidate_id"),
                "standard_score": standard.get("score"),
                "standard_promotion_available": result.get("standard_promotion_available") is True,
            })
        except Exception as exc:
            resolved.append({
                "grok_opportunity_candidate_id": candidate_id,
                "ticker": nomination.get("ticker"),
                "status": "REVALIDATION_ERROR",
                "error": f"{type(exc).__name__}: {exc}"[:1000],
                "standard_promotion_available": False,
            })

    false_positive = build_false_positive_report()
    lead_time = build_discovery_lead_time_report()
    return {
        "policy_version": POLICY_VERSION,
        "query": query,
        "discovery": {
            "nominated_count": discovery.get("nominated_count"),
            "quarantined_count": discovery.get("quarantined_count"),
            "grok_usage": discovery.get("grok_usage") or {},
        },
        "revalidation_results": resolved,
        "resolved_this_probe": sum(1 for row in resolved if row.get("status") == "REVALIDATED"),
        "false_positive_sample": {
            "nomination_count": false_positive.get("nomination_count"),
            "resolved_count": false_positive.get("resolved_count"),
            "validated_count": false_positive.get("validated_count"),
            "rejected_count": false_positive.get("rejected_count"),
            "false_positive_rate": false_positive.get("false_positive_rate"),
        },
        "lead_time_sample": {
            "measurable_pair_count": lead_time.get("measurable_pair_count"),
            "prospective_pair_count": lead_time.get("prospective_pair_count"),
            "median_grok_lead_minutes": lead_time.get("median_grok_lead_minutes"),
            "prospective_median_grok_lead_minutes": lead_time.get("prospective_median_grok_lead_minutes"),
        },
        "xai_discovery_batches": 1,
        "automatic_standard_revalidation": True,
        "automatic_case_promotion": False,
        "automatic_agent_run": False,
        "qualification_evidence": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/grok/value/probe/plan")
def value_probe_plan():
    return {
        "policy_version": POLICY_VERSION,
        "purpose": "one Grok discovery batch followed by automatic independent standard-IIOS research revalidation",
        "max_candidates": MAX_PROBE_CANDIDATES,
        "automatic_standard_revalidation": True,
        "automatic_case_promotion": False,
        "automatic_agent_run": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/grok/value/probe")
def value_probe(request: dict[str, Any] = Body(...)):
    try:
        return run_value_probe(
            str(request.get("query") or ""),
            days=int(request.get("days") or 2),
            max_candidates=int(request.get("max_candidates") or 5),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000])
