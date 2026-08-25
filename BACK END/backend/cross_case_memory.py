from __future__ import annotations

import os
import threading
from typing import Any

from fastapi import APIRouter, HTTPException

from historical_regime_memory import find_historical_analogs
from ledger import get_object


router = APIRouter()
MAX_MEMORY_ANALOGS = 3
MIN_MEMORY_SIMILARITY = 0.25
_context = threading.local()


def _enabled() -> bool:
    return str(os.getenv("IIOS_CROSS_CASE_MEMORY", "1")).strip().lower() in {"1", "true", "yes", "on"}


def build_memory_context(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")

    analogs = find_historical_analogs(case_id, MAX_MEMORY_ANALOGS).get("analogs") or []
    selected = [
        row for row in analogs
        if float(row.get("similarity") or 0.0) >= MIN_MEMORY_SIMILARITY
    ][:MAX_MEMORY_ANALOGS]

    items: list[dict[str, Any]] = []
    for row in selected:
        outcome_known = row.get("historical_outcome_known") is True
        claim = (
            f"Prior IIOS case {row.get('case_id')} similarity={row.get('similarity')}; "
            f"prior committee disposition={row.get('committee_disposition')}; "
            f"prior confidence={row.get('committee_confidence')}; "
            f"shared regime tags={', '.join(row.get('shared_regime_tags') or []) or 'none'}; "
            f"outcome={row.get('outcome') if outcome_known else 'UNKNOWN'}"
        )
        items.append({
            "source": "IIOS Cross-Case Memory",
            "source_type": "governed_internal_memory",
            "evidence_type": "cross_case_memory",
            "url": f"iios://case/{row.get('case_id')}",
            "title": f"Internal analog: {row.get('topic')}",
            "claim": claim,
            "reliability_score": 0.60 if outcome_known else 0.35,
            "similarity": row.get("similarity"),
            "historical_outcome_known": outcome_known,
            "memory_inference_only": True,
            "gap_resolution_eligible": False,
            "trade_signal": False,
            "trade_execution_permission": False,
        })

    return {
        "case_id": case_id,
        "enabled": _enabled(),
        "memory_items": items if _enabled() else [],
        "memory_item_count": len(items) if _enabled() else 0,
        "min_similarity": MIN_MEMORY_SIMILARITY,
        "max_analogs": MAX_MEMORY_ANALOGS,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def install_cross_case_memory(module) -> None:
    """Feed internal memory to specialist prompts without altering evidence gates.

    Memory is appended only to the evidence argument seen by specialist desks. It is
    never added to the case evidence packet/evidence summary, so it cannot inflate
    evidence counts, quality scores, fact resolution, sizing, or execution gates.
    """
    if getattr(module, "_cross_case_memory_installed", False):
        return
    module._cross_case_memory_installed = True

    original_run_one = module._run_one
    original_orchestration = module.run_eight_agent_orchestration

    def memory_run_one(agent_key: str, topic: str, evidence: list[dict[str, Any]]):
        memory_items = getattr(_context, "memory_items", []) or []
        return original_run_one(agent_key, topic, list(evidence) + list(memory_items))

    def memory_orchestration(case_id: str):
        previous = getattr(_context, "memory_items", None)
        context = build_memory_context(case_id)
        _context.memory_items = list(context.get("memory_items") or [])
        try:
            result = original_orchestration(case_id)
        finally:
            _context.memory_items = previous
        result["memory_context"] = {
            "memory_item_count": context.get("memory_item_count"),
            "qualification_evidence": False,
            "gap_resolution_eligible": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        return result

    module._run_one = memory_run_one
    module.run_eight_agent_orchestration = memory_orchestration


@router.get("/intelligence/cross-case-memory/{case_id}")
def cross_case_memory(case_id: str):
    return build_memory_context(case_id)


@router.get("/intelligence/cross-case-memory-plan")
def cross_case_memory_plan():
    return {
        "enabled": _enabled(),
        "max_analogs": MAX_MEMORY_ANALOGS,
        "min_similarity": MIN_MEMORY_SIMILARITY,
        "injected_into_specialist_prompts": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "judgment_output_cache": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
