from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from eight_agent_orchestrator import run_eight_agent_orchestration
from ledger import get_object, latest_object, record_event
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE, opportunity_queue, promote_candidate


router = APIRouter()
MAX_BATCH_DISPATCH = 3


def dispatch_candidate(candidate_id: str, *, force_research_rerun: bool = False) -> dict[str, Any]:
    candidate = get_object(candidate_id)
    if not candidate or not str(candidate_id).startswith("opportunity_"):
        raise ValueError("Unknown opportunity candidate")
    if candidate.get("eligible_for_promotion") is not True:
        raise ValueError("Candidate has not met the research-promotion gate")

    promoted = promote_candidate(candidate_id)
    case = promoted["case"]
    case_id = str(case["case_id"])
    existing = latest_object("agent_orchestration", case_id=case_id)
    if existing and not force_research_rerun:
        return {
            "candidate_id": candidate_id,
            "case": case,
            "orchestration": existing,
            "already_dispatched": True,
            "paper_mode": True,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    result = run_eight_agent_orchestration(case_id)
    record_event(
        case_id,
        "OPPORTUNITY_DISPATCHED_TO_EIGHT_AGENT_FLOOR",
        entity_id=result["orchestration"]["orchestration_id"],
        payload={
            "source_candidate_id": candidate_id,
            "committee_disposition": result["committee"]["disposition"],
            "committee_confidence": result["committee"]["confidence"],
            "trade_execution_permission": False,
        },
    )
    return {
        "candidate_id": candidate_id,
        "case": case,
        **result,
        "already_dispatched": False,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def dispatch_ranked_queue(*, limit: int = 1) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_BATCH_DISPATCH))
    candidates = [row for row in opportunity_queue(20) if row.get("eligible_for_promotion")]
    selected = candidates[:limit]
    results: list[dict[str, Any]] = []
    for candidate in selected:
        candidate_id = str(candidate.get("opportunity_candidate_id") or "")
        try:
            result = dispatch_candidate(candidate_id)
            results.append({
                "candidate_id": candidate_id,
                "ticker": candidate.get("ticker"),
                "score": candidate.get("score"),
                "status": "complete",
                "result": result,
            })
        except Exception as exc:
            results.append({
                "candidate_id": candidate_id,
                "ticker": candidate.get("ticker"),
                "score": candidate.get("score"),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    record_event(
        OPPORTUNITY_LEDGER_CASE,
        "OPPORTUNITY_QUEUE_DISPATCH_COMPLETE",
        payload={
            "requested": limit,
            "selected": len(selected),
            "completed": sum(1 for row in results if row["status"] == "complete"),
            "failed": sum(1 for row in results if row["status"] != "complete"),
            "trade_execution_permission": False,
        },
    )
    return {
        "requested": limit,
        "selected": len(selected),
        "results": results,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/opportunities/{candidate_id}/dispatch")
def dispatch_opportunity(candidate_id: str, request: dict[str, Any] = Body(default={})):
    try:
        return dispatch_candidate(
            candidate_id,
            force_research_rerun=bool(request.get("force_research_rerun", False)),
        )
    except ValueError as exc:
        status = 404 if "Unknown" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))


@router.post("/opportunities/dispatch-queue")
def dispatch_opportunity_queue(request: dict[str, Any] = Body(default={})):
    return dispatch_ranked_queue(limit=int(request.get("limit") or 1))
