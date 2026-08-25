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
from grok_social_intelligence import (
    install_grok_prompt_context,
    router as grok_social_router,
)
from agent_calibration_weighting import (
    install_calibration_context,
    router as agent_calibration_router,
)
from dynamic_agent_factory import router as dynamic_agent_factory_router
from grok_ab_benchmark import router as grok_ab_router
from grok_ab_reuse import router as grok_ab_reuse_router
from grok_batch7_checkpoint import router as grok_batch7_checkpoint_router
from grok_discovery_lead_time import router as grok_lead_time_router
from grok_experiment_manifest import router as grok_experiment_manifest_router
from grok_experiment_scorecard import router as grok_scorecard_router
from grok_false_positive_tracker import router as grok_false_positive_router
import grok_opportunity_discovery
from grok_opportunity_discovery import router as grok_opportunity_router
from grok_paper_value import router as grok_paper_value_router
from grok_shadow_paper import router as grok_shadow_paper_router
from grok_value_cycle import router as grok_value_cycle_router
from grok_value_cycle_async import router as grok_value_cycle_async_router
from grok_value_scheduler import router as grok_value_scheduler_router
from grok_value_instrumentation import install_grok_value_instrumentation
from grok_value_probe import router as grok_value_probe_router
from grok_value_scorecard import router as grok_value_scorecard_router
from ipo_monitoring import router as ipo_monitoring_router
from market_event_radar import router as market_event_radar_router
from monitoring_engine import _default_sources, _fetch_stooq_quote, configure_profile
import opportunity_acquisition
from opportunity_evidence_hardening import install_opportunity_evidence_hardening
import source_ingestion
from research_source_cache import (
    install_research_source_cache,
    router as research_source_cache_router,
)

install_orchestration_runtime(eight_agent_orchestrator)
install_orchestration_resilience(eight_agent_orchestrator)
install_orchestration_speed(eight_agent_orchestrator)
install_cross_case_memory(eight_agent_orchestrator)
install_judgment_bank_context(eight_agent_orchestrator)
install_grok_prompt_context(eight_agent_orchestrator)
install_calibration_context(eight_agent_orchestrator)
install_opportunity_evidence_hardening(opportunity_acquisition)
install_research_source_cache(source_ingestion)
install_grok_value_instrumentation(opportunity_acquisition, grok_opportunity_discovery)

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
from v1_consolidation_manifest import router as v1_consolidation_router


router = APIRouter()
router.include_router(opportunity_router)
router.include_router(opportunity_dispatch_router)
router.include_router(opportunity_scheduler_router)
router.include_router(adaptive_research_queue_router)
router.include_router(ipo_monitoring_router)
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
router.include_router(dynamic_agent_factory_router)
router.include_router(grok_social_router)
router.include_router(grok_ab_router)
router.include_router(grok_ab_reuse_router)
router.include_router(grok_opportunity_router)
router.include_router(grok_experiment_manifest_router)
router.include_router(grok_scorecard_router)
router.include_router(grok_lead_time_router)
router.include_router(grok_false_positive_router)
router.include_router(grok_paper_value_router)
router.include_router(grok_shadow_paper_router)
router.include_router(grok_value_probe_router)
router.include_router(grok_value_cycle_router)
router.include_router(grok_value_cycle_async_router)
router.include_router(grok_value_scheduler_router)
router.include_router(grok_value_scorecard_router)
router.include_router(grok_batch7_checkpoint_router)
router.include_router(agent_calibration_router)
router.include_router(thesis_lifecycle_router)
router.include_router(portfolio_intelligence_router)
router.include_router(intelligence_safety_manifest_router)
router.include_router(v1_consolidation_router)
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
