from fastapi import APIRouter
from pydantic import BaseModel

from factory.system_agents import MARKET_HISTORY_AGENT_ID
from intelligence.dispatcher import dispatcher
from intelligence.memory_retrieval import retrieve_relevant_patterns
from intelligence.models import EvidenceItem
from intelligence.postmortem_intelligence import postmortem_intelligence


router = APIRouter(prefix="/intelligence/memory", tags=["institutional-memory"])


class MemoryPreviewRequest(BaseModel):
    source_name: str = "Memory Preview"
    source_kind: str = "other"
    title: str
    summary: str = ""
    url: str | None = None
    limit: int = 3


@router.get("/search")
def search_memory(q: str = "", limit: int = 25):
    items = postmortem_intelligence.search_patterns(q, limit=max(1, min(limit, 100)))
    return {
        "query": q,
        "count": len(items),
        "items": items,
        "paper_mode": True,
        "memory_is_context_not_authority": True,
    }


@router.post("/preview")
def preview_memory(request: MemoryPreviewRequest):
    event = {
        "source_name": request.source_name,
        "source_kind": request.source_kind,
        "title": request.title,
        "summary": request.summary,
        "url": request.url,
    }
    items = retrieve_relevant_patterns(event, limit=max(1, min(request.limit, 10)))
    return {
        "event": event,
        "retrieved_count": len(items),
        "items": items,
        "guardrails": {
            "memory_is_context_not_authority": True,
            "synthetic_lessons_excluded_from_real_market_context": True,
            "analog_differences_required": True,
        },
        "paper_mode": True,
    }


@router.post("/decision-test")
def run_memory_decision_test(request: MemoryPreviewRequest):
    """Run a submitted event through the real dispatcher + approved History agent."""
    item = EvidenceItem(
        source_name=request.source_name,
        source_kind=request.source_kind,
        title=request.title,
        summary=request.summary,
        url=request.url,
        freshness="fresh",
        confidence=1.0,
    )
    event = item.model_dump(mode="json")
    memory = retrieve_relevant_patterns(event, limit=max(1, min(request.limit, 10)))
    synthetic_fixture = any(
        marker in " ".join(
            [request.source_name, request.title, request.summary, request.url or ""]
        ).lower()
        for marker in ("synthetic", "iios-test", "test fixture")
    )
    row = {
        "dispatch_id": "memory-decision-test",
        "agent_id": MARKET_HISTORY_AGENT_ID,
        "route_reason": "Institutional-memory decision test",
        "evidence_payload": item.model_dump_json(),
    }
    result = dispatcher._run_agent(row)
    if synthetic_fixture:
        result["committee_escalation"] = False
    return {
        "synthetic_fixture": synthetic_fixture,
        "event": event,
        "retrieved_count": len(memory),
        "retrieved_memory": memory,
        "agent_id": MARKET_HISTORY_AGENT_ID,
        "agent_result": result,
        "guardrails": {
            "memory_is_context_not_authority": True,
            "synthetic_lessons_excluded_from_real_market_context": True,
            "no_real_market_inference_from_synthetic_tests": True,
        },
        "paper_mode": True,
        "live_execution": False,
        "real_capital": 0,
    }
