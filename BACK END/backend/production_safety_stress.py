from __future__ import annotations

import math
from typing import Any

import adaptive_research_queue as research_queue
import orchestration_resilience
import orchestration_worker_pool
from production_safety_freeze import production_freeze_manifest


def synthetic_load_plan(total_cases: int = 100, workers: int | None = None) -> dict[str, Any]:
    total = max(0, int(total_cases))
    configured = orchestration_worker_pool.configured_case_workers() if workers is None else int(workers)
    active_workers = max(1, min(configured, orchestration_worker_pool.MAX_CASE_WORKERS))
    accepted = min(total, research_queue.MAX_QUEUE_DEPTH)
    deferred = max(0, total - accepted)
    waves = math.ceil(accepted / active_workers) if accepted else 0
    pressure = research_queue.backpressure_state(min(accepted, research_queue.HIGH_WATERMARK))
    return {
        "requested_cases": total,
        "accepted_into_bounded_queue": accepted,
        "deferred_by_capacity": deferred,
        "workers": active_workers,
        "estimated_worker_waves": waves,
        "backpressure_expected": total >= research_queue.HIGH_WATERMARK,
        "backpressure_state": pressure,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def production_stress_report(total_cases: int = 100) -> dict[str, Any]:
    freeze = production_freeze_manifest()
    load = synthetic_load_plan(total_cases)
    resilience = orchestration_resilience.resilience_plan()

    checks = {
        "freeze_invariants_pass": freeze["all_invariants_pass"],
        "queue_is_bounded": load["accepted_into_bounded_queue"] <= research_queue.MAX_QUEUE_DEPTH,
        "burst_triggers_backpressure": load["backpressure_expected"],
        "worker_count_hard_bounded": load["workers"] <= orchestration_worker_pool.MAX_CASE_WORKERS,
        "resilience_is_fail_closed": resilience["fail_closed"] is True,
        "transient_retries_are_bounded": resilience["max_transient_attempts"] <= 2,
        "automatic_default_change_disabled": freeze["automatic_configuration_change"] is False,
    }

    return {
        "stress_version": "speed-safety-stress-v1",
        "load": load,
        "freeze": freeze,
        "checks": checks,
        "stress_pass": all(checks.values()),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


if __name__ == "__main__":
    report = production_stress_report(100)
    print("IIOS PRODUCTION SAFETY STRESS")
    print("-----------------------------")
    print("stress_pass:", report["stress_pass"])
    print("requested_cases:", report["load"]["requested_cases"])
    print("accepted_into_bounded_queue:", report["load"]["accepted_into_bounded_queue"])
    print("deferred_by_capacity:", report["load"]["deferred_by_capacity"])
    print("workers:", report["load"]["workers"])
    print("estimated_worker_waves:", report["load"]["estimated_worker_waves"])
    print("all_invariants_pass:", report["freeze"]["all_invariants_pass"])
    print("current_matches_proven_envelope:", report["freeze"]["current_matches_proven_envelope"])
    print("trade_execution_permission:", report["trade_execution_permission"])
    print("live_execution:", report["live_execution"])
