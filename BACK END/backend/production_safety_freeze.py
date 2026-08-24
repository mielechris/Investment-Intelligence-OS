from __future__ import annotations

from typing import Any

from fastapi import APIRouter


router = APIRouter()
FREEZE_VERSION = "speed-safety-v1"


def production_freeze_manifest() -> dict[str, Any]:
    import adaptive_research_queue as research_queue
    import opportunity_scheduler
    import orchestration_resilience
    import orchestration_runtime
    import orchestration_speed
    import orchestration_worker_pool
    import research_source_cache

    scheduler = opportunity_scheduler.current_config()
    runtime = orchestration_runtime.runtime_policy()
    queue_plan = research_queue.research_queue_plan()
    source_cache = research_source_cache.research_source_cache_plan()
    resilience = orchestration_resilience.resilience_plan()

    invariant_checks = {
        "baseline_profile_is_default": orchestration_runtime.BASELINE_PROFILE == "baseline",
        "default_case_workers_is_two": orchestration_worker_pool.DEFAULT_CASE_WORKERS == 2,
        "case_worker_ceiling_at_most_four": orchestration_worker_pool.MAX_CASE_WORKERS <= 4,
        "default_specialist_parallelism_is_six": orchestration_speed.DEFAULT_PARALLEL_SPECIALISTS == 6,
        "specialist_parallelism_ceiling_is_six": orchestration_speed.MAX_PARALLEL_SPECIALISTS == 6,
        "judgment_output_cache_disabled": runtime["judgment_output_cache"] is False,
        "research_queue_automatic_drain_disabled": queue_plan["automatic_drain"] is False,
        "research_queue_has_backpressure": queue_plan["high_watermark"] < queue_plan["max_queue_depth"],
        "source_cache_success_only": source_cache["cache_successes_only"] is True,
        "source_cache_exact_match_only": source_cache["exact_request_match_required"] is True,
        "source_cache_never_caches_judgments": source_cache["judgment_output_cache"] is False,
        "transient_attempts_bounded": resilience["max_transient_attempts"] <= 2,
        "resilience_fail_closed": resilience["fail_closed"] is True,
        "scanner_disabled": scheduler.get("enabled") is False,
        "auto_dispatch_disabled": scheduler.get("auto_dispatch_enabled") is False,
    }

    safety_flags = {
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    current_runtime = {
        "profile": runtime["profile"],
        "first_wave_reasoning_effort": runtime["first_wave_reasoning_effort"],
        "critical_reasoning_effort": runtime["critical_reasoning_effort"],
        "committee_reasoning_effort": runtime["committee_reasoning_effort"],
        "configured_case_workers": orchestration_worker_pool.configured_case_workers(),
        "scanner_enabled": bool(scheduler.get("enabled")),
        "auto_dispatch_enabled": bool(scheduler.get("auto_dispatch_enabled")),
    }
    current_matches_proven_envelope = all(
        (
            current_runtime["profile"] == "baseline",
            current_runtime["first_wave_reasoning_effort"] == "medium",
            current_runtime["critical_reasoning_effort"] == "medium",
            current_runtime["committee_reasoning_effort"] == "medium",
            current_runtime["configured_case_workers"] == 2,
            current_runtime["scanner_enabled"] is False,
            current_runtime["auto_dispatch_enabled"] is False,
        )
    )

    return {
        "freeze_version": FREEZE_VERSION,
        "invariant_checks": invariant_checks,
        "all_invariants_pass": all(invariant_checks.values()),
        "proven_production_envelope": {
            "orchestration_profile": "baseline",
            "first_wave_reasoning_effort": "medium",
            "critical_reasoning_effort": "medium",
            "committee_reasoning_effort": "medium",
            "specialist_parallelism": 6,
            "default_case_workers": 2,
            "case_worker_hard_ceiling": 4,
            "scanner_default": "OFF",
            "auto_dispatch_default": "OFF",
            "prompt_cache": "ON",
            "research_source_cache": "ON",
            "judgment_output_cache": "OFF",
            "automatic_queue_drain": "OFF",
        },
        "current_runtime": current_runtime,
        "current_matches_proven_envelope": current_matches_proven_envelope,
        "automatic_configuration_change": False,
        "paper_mode": True,
        **safety_flags,
    }


@router.get("/production-safety/freeze")
def production_safety_freeze():
    return production_freeze_manifest()
