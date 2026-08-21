from fastapi import APIRouter
from pydantic import BaseModel

from intelligence.memory_retrieval import retrieve_relevant_patterns
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
