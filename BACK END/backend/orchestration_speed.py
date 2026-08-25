from __future__ import annotations

import os
from time import perf_counter
from typing import Any
from uuid import uuid4


DEFAULT_PARALLEL_SPECIALISTS = 6
MAX_PARALLEL_SPECIALISTS = 6


def configured_parallelism() -> int:
    raw = os.getenv("IIOS_AGENT_PARALLELISM", str(DEFAULT_PARALLEL_SPECIALISTS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_PARALLEL_SPECIALISTS
    return max(1, min(value, MAX_PARALLEL_SPECIALISTS))


def _latency_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000.0, 2)


def _agent_latency_map(agents: dict[str, dict[str, Any]]) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, row in agents.items():
        try:
            output[key] = round(float(row.get("latency_ms") or 0.0), 2)
        except (TypeError, ValueError):
            output[key] = 0.0
    return output


def install_orchestration_speed(module) -> None:
    """Add bounded parallelism and timing telemetry to the 8-agent orchestrator.

    This layer changes orchestration throughput only. It does not change agent
    disposition rules, committee guards, paper authorization, paper execution,
    or live-execution permissions.
    """
    if getattr(module, "_speed_layer_installed", False):
        return

    module._speed_layer_installed = True
    module.MAX_PARALLEL_SPECIALISTS = configured_parallelism()

    original_run_one = module._run_one
    original_synthesize = module._synthesize_committee
    original_orchestration = module.run_eight_agent_orchestration

    def timed_run_one(agent_key: str, topic: str, evidence: list[dict[str, Any]]):
        started = perf_counter()
        result = original_run_one(agent_key, topic, evidence)
        return {
            **result,
            "latency_ms": _latency_ms(started),
            "timing_measured": True,
        }

    def timed_synthesize_committee(*args, **kwargs):
        started = perf_counter()
        result = original_synthesize(*args, **kwargs)
        return {
            **result,
            "committee_latency_ms": _latency_ms(started),
            "timing_measured": True,
        }

    def timed_orchestration(case_id: str):
        started = perf_counter()
        result = original_orchestration(case_id)
        total_ms = _latency_ms(started)

        orchestration = result.get("orchestration") or {}
        committee = result.get("committee") or {}
        agents = orchestration.get("agents") or {}
        latencies = _agent_latency_map(agents)
        first_wave = [latencies.get(key, 0.0) for key in module.FIRST_WAVE]
        second_wave = [latencies.get(key, 0.0) for key in module.SECOND_WAVE]
        serial_agent_ms = round(sum(latencies.values()), 2)
        first_wave_parallel_floor_ms = round(max(first_wave) if first_wave else 0.0, 2)
        committee_ms = round(float(committee.get("committee_latency_ms") or 0.0), 2)

        performance_id = f"orchestration_perf_{uuid4().hex}"
        performance = {
            "orchestration_performance_id": performance_id,
            "orchestration_id": orchestration.get("orchestration_id"),
            "case_id": case_id,
            "total_latency_ms": total_ms,
            "agent_latency_ms": latencies,
            "first_wave_parallelism": module.MAX_PARALLEL_SPECIALISTS,
            "first_wave_parallel_floor_ms": first_wave_parallel_floor_ms,
            "second_wave_serial_ms": round(sum(second_wave), 2),
            "committee_latency_ms": committee_ms,
            "serial_agent_latency_ms": serial_agent_ms,
            "estimated_agent_parallel_speedup": (
                round(serial_agent_ms / max(first_wave_parallel_floor_ms + sum(second_wave), 1.0), 2)
                if serial_agent_ms > 0
                else 0.0
            ),
            "paper_mode": True,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": module.utc_now(),
        }
        module.record_object(
            performance_id,
            "orchestration_performance",
            case_id,
            performance,
            parent_id=orchestration.get("orchestration_id"),
            topic=orchestration.get("topic"),
        )
        module.record_event(
            case_id,
            "ORCHESTRATION_PERFORMANCE_RECORDED",
            entity_id=performance_id,
            payload={
                "total_latency_ms": total_ms,
                "first_wave_parallelism": module.MAX_PARALLEL_SPECIALISTS,
                "committee_latency_ms": committee_ms,
                "trade_execution_permission": False,
            },
        )
        result["performance"] = performance
        return result

    module._run_one = timed_run_one
    module._synthesize_committee = timed_synthesize_committee
    module.run_eight_agent_orchestration = timed_orchestration
