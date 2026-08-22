from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from monitoring_engine import _default_sources, _fetch_stooq_quote, configure_profile
from source_ingestion import ingest_sources


router = APIRouter()


@router.post("/factory/run-public")
def run_public_case(request: dict[str, Any] = Body(...)):
    topic = str(request.get("topic", "")).strip()
    if not topic:
        raise HTTPException(status_code=422, detail="topic is required")

    ticker = str(request.get("ticker", "")).strip()
    source_requests = request.get("source_requests") if isinstance(request.get("source_requests"), list) else _default_sources(topic)
    ingestion = ingest_sources(source_requests)
    quote = _fetch_stooq_quote(ticker)
    evidence = list(ingestion.get("evidence_items") or []) + list(quote.get("items") or [])

    # Imported lazily so app -> router imports do not create a startup cycle.
    from main import TopicRequest, run_factory

    factory = run_factory(TopicRequest(topic=topic, evidence=evidence))
    case_id = factory["case"]["case_id"]

    profile = None
    if bool(request.get("auto_watch", True)):
        reference_price = request.get("reference_price")
        if reference_price in (None, ""):
            reference_price = quote.get("current_price")
        profile = configure_profile({
            "case_id": case_id,
            "enabled": True,
            "interval_minutes": request.get("interval_minutes", 240),
            "source_requests": source_requests,
            "ticker": ticker,
            "direction": request.get("direction", "UNSPECIFIED"),
            "reference_price": reference_price,
            "analysis_mode": request.get("analysis_mode", "llm"),
        })

    return {
        "topic": topic,
        "ingestion": ingestion,
        "quote": quote,
        "factory": factory,
        "monitor_profile": profile,
        "paper_mode": True,
    }
