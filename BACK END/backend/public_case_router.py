from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

import eight_agent_orchestrator
from eight_agent_orchestrator import router as orchestration_router
from orchestration_runtime import (
    install_orchestration_runtime,
    router as orchestration_runtime_router,
)
from orchestration_resilience import (
    install_orchestration_resilience,
    router as orchestration_resilience_router,
)
from orchestration_speed import install_orchestration_speed
from cross_case_memory import (
    install_cross_case_memory,
    router as cross_case_memory_router,
)
from judgment_bank_integration import (
    install_judgment_bank_context,
    router as judgment_bank_router,
)
from agent_calibration_weighting import (
    install_calibration_context,
    router as agent_calibration_router,
)
from market_event_radar import router as market_event_radar_router
from monitoring_engine import _default_sources, _fetch_stooq_quote, configure_profile
import opportunity_acquisition
from opportunity_evidence_hardening import install_opportunity_evidence_hardening
import source_ingestion
from research_source_cache import (
    install_research_source_cache,
    router as research_source_cache_router,
)

# Install model/effort routing and request deadlines first.
install_orchestration_runtime(eight_agent_orchestrator)

# Add bounded retries/circuit breaking before timing so telemetry measures the
# resilient path. Persistent failures still fall into the existing fail-closed
# agent/committee guards.
install_orchestration_resilience(eight_agent_orchestrator)

# Install bounded orchestration throughput/timing before dispatch, queue, or
# worker-pool modules import the run function.
install_orchestration_speed(eight_agent_orchestrator)

# Cross-case memory is specialist context only. It never enters qualification
# evidence counts, fact resolution, sizing, authorization, or execution gates.
install_cross_case_memory(eight_agent_orchestrator)

# Human Judgment Bank context is injected only after explicit human approval,
# LOW restriction-risk screening, and case relevance. It is advisory/untrusted
# context only and cannot become qualifying evidence or capital authority.
install_judgment_bank_context(eight_agent_orchestrator)

# Calibration remains neutral until every desk reaches the governed sample-size
# threshold. Even when mature, it cannot bypass committee guards.
install_calibration_context(eight_agent_orchestrator)

# Install research-only evidence hardening before dispatch/scheduler modules import
# the opportunity scan function. This changes only scanner evidence acquisition;
# it does not touch sizing, authorization, paper execution, or live execution.
install_opportunity_evidence_hardening(opportunity_acquisition)

# Reuse successful exact-match public source responses within bounded TTLs. This
# never caches model judgments or market-quote decisions.
install_research_source_cache(source_ingestion)

# Import modules that capture the installed orchestrator only after runtime,
# resilience, timing, memory, Judgment Bank, and calibration layers are in place.
from adaptive_research_queue import router as adaptive_research_queue_router
from evidence_depth_engine import router as evidence_depth_router
from historical_regime_memory import router as historical_regime_memory_router
from intelligence_safety_manifest import router as intelligence_safety_manifest_router
from opportunity_acquisition import router as opportunity_router
from opportunity_dispatch import router as opportunity_dispatch_router
from opportunity_scheduler import router as opportunity_scheduler_router
from orchestration_worker_pool import router as orchestration_worker_pool_router
from portfolio_intelligence import router as portfolio_intelligence_router
from production_safety_freeze import router as production_safety_freeze_router
from source_ingestion import ingest_sources
from thesis_lifecycle_intelligence import router as thesis_lifecycle_router


router = APIRouter()
router.include_router(opportunity_router)
router.include_router(opportunity_dispatch_router)
router.include_router(opportunity_scheduler_router)
router.include_router(adaptive_research_queue_router)
router.include_router(market_event_radar_router)
router.include_router(orchestration_runtime_router)
router.include_router(orchestration_resilience_router)
router.include_router(research_source_cache_router)
router.include_router(orchestration_worker_pool_router)
router.include_router(production_safety_freeze_router)
router.include_router(evidence_depth_router)
router.include_router(historical_regime_memory_router)
router.include_router(cross_case_memory_router)
router.include_router(judgment_bank_router)
router.include_router(agent_calibration_router)
router.include_router(thesis_lifecycle_router)
router.include_router(portfolio_intelligence_router)
router.include_router(intelligence_safety_manifest_router)
router.include_router(orchestration_router)


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
