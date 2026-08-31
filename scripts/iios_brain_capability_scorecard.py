#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP = Path.home() / "Library" / "Application Support" / "IIOS"


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _task_rows(scientific: dict[str, Any]) -> list[dict[str, Any]]:
    league = scientific.get("model_task_league") if isinstance(scientific.get("model_task_league"), dict) else {}
    return [row for row in league.get("task_rows") or [] if isinstance(row, dict)]


def _health_components(model_health: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = [row for row in model_health.get("components") or [] if isinstance(row, dict)]
    return {str(row.get("component") or ""): row for row in rows}


def _provider_rows(rows: list[dict[str, Any]], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        haystack = " ".join(str(row.get(key) or "") for key in ("provider", "model", "task_type")).lower()
        if any(word in haystack for word in keywords):
            output.append(row)
    return output


def _sum_requests(rows: list[dict[str, Any]]) -> int:
    return sum(int(row.get("requests") or 0) for row in rows)


def _weighted_latency(rows: list[dict[str, Any]]) -> float | None:
    numerator = 0.0
    denominator = 0
    for row in rows:
        latency = row.get("average_latency_ms")
        requests = int(row.get("requests") or 0)
        if latency is None or not requests:
            continue
        try:
            numerator += float(latency) * requests
        except (TypeError, ValueError):
            continue
        denominator += requests
    return round(numerator / denominator, 1) if denominator else None


def _sum_cost(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get("exact_cost_usd") or 0.0)
        except (TypeError, ValueError):
            pass
    return round(total, 6)


def build_brain_league(scientific: dict[str, Any], model_health: dict[str, Any]) -> dict[str, Any]:
    rows = _task_rows(scientific)
    components = _health_components(model_health)
    model_context = components.get("GROK_GEMINI_MODEL_CONTEXT", {})
    gpt_floor = components.get("GPT_EIGHT_AGENT_CASE_FLOOR", {})
    gpt_desks = components.get("EIGHT_GPT_DESKS", {})
    committee = components.get("INVESTMENT_COMMITTEE", {})
    gemini_pro = components.get("GEMINI_PRO_DEEP_WORKER", {})

    grok_rows = _provider_rows(rows, ("grok", "xai"))
    gemini_rows = _provider_rows(rows, ("gemini", "google"))
    openai_rows = _provider_rows(rows, ("openai", "gpt"))

    grok_runtime = bool((model_context.get("detail") or {}).get("grok_satisfied") is True)
    gemini_runtime = bool((model_context.get("detail") or {}).get("gemini_satisfied") is True)
    openai_runtime = str(gpt_floor.get("state") or "") in {"HEALTHY", "IDLE_HEALTHY"} and str(gpt_desks.get("state") or "") in {"HEALTHY", "IDLE_HEALTHY"}
    committee_runtime = str(committee.get("state") or "") in {"HEALTHY", "IDLE_HEALTHY"}

    brains = [
        {
            "brain": "GROK",
            "current_role": "REAL_TIME_WIRE_ROOM",
            "configured_capabilities": ["X_SEARCH", "WEB_SEARCH", "breaking narrative detection", "crowding/contradiction context"],
            "runtime_observed": grok_runtime,
            "health_state": model_context.get("state"),
            "measured_requests": _sum_requests(grok_rows),
            "measured_average_latency_ms": _weighted_latency(grok_rows),
            "measured_exact_cost_usd": _sum_cost(grok_rows),
            "task_accuracy_score": None,
            "accuracy_state": "WAITING_FOR_EXACT_OUTCOME_LINKAGE",
        },
        {
            "brain": "GEMINI",
            "current_role": "GROUNDED_RESEARCH_AND_DEEP_EVIDENCE",
            "configured_capabilities": ["GOOGLE_SEARCH_GROUNDING", "URL_CONTEXT", "structured rapid research", "selective Pro deep research"],
            "runtime_observed": gemini_runtime,
            "health_state": model_context.get("state"),
            "deep_worker_state": gemini_pro.get("state"),
            "measured_requests": _sum_requests(gemini_rows),
            "measured_average_latency_ms": _weighted_latency(gemini_rows),
            "measured_exact_cost_usd": _sum_cost(gemini_rows),
            "task_accuracy_score": None,
            "accuracy_state": "WAITING_FOR_EXACT_OUTCOME_LINKAGE",
        },
        {
            "brain": "OPENAI",
            "current_role": "EIGHT_SPECIALIST_DESKS_PLUS_COMMITTEE_SYNTHESIS",
            "configured_capabilities": ["domain-specialist reasoning", "peer-aware red team", "portfolio context", "Committee synthesis"],
            "runtime_observed": bool(openai_runtime and committee_runtime),
            "health_state": gpt_desks.get("state"),
            "committee_state": committee.get("state"),
            "measured_requests": _sum_requests(openai_rows),
            "measured_average_latency_ms": _weighted_latency(openai_rows),
            "measured_exact_cost_usd": _sum_cost(openai_rows),
            "task_accuracy_score": None,
            "accuracy_state": "WAITING_FOR_EXACT_OUTCOME_LINKAGE",
        },
    ]

    any_accuracy = any(
        row.get("accuracy_score") is not None
        for row in rows
    )
    routing_state = "OUTCOME_EVIDENCE_AVAILABLE_FOR_SHADOW_ROUTING" if any_accuracy else "HOLD_CURRENT_ROUTING_COLLECT_EVIDENCE"

    combinations = [
        {
            "experiment": "WIRE_BOOKS_COMMITTEE",
            "sequence": ["GROK discovery", "GEMINI evidence verification", "OPENAI eight desks + Committee"],
            "purpose": "Measure whether specialized handoffs outperform a single-model path on detection quality, evidence quality, latency, and cost.",
            "status": "SHADOW_DESIGN_READY_NOT_AUTO_APPLIED",
        },
        {
            "experiment": "PARALLEL_GROK_GEMINI_OPENAI_ARBITRATION",
            "sequence": ["GROK and GEMINI in parallel", "OPENAI resolves contradictions and synthesizes"],
            "purpose": "Test whether parallel independent research improves recall and contradiction detection enough to justify cost.",
            "status": "SHADOW_DESIGN_READY_NOT_AUTO_APPLIED",
        },
        {
            "experiment": "OPENAI_CONTROL",
            "sequence": ["OPENAI-only governed research control"],
            "purpose": "Provide a lower-complexity control so multi-model gains are measured rather than assumed.",
            "status": "SHADOW_DESIGN_READY_NOT_AUTO_APPLIED",
        },
    ]

    return {
        "schema_version": "batch10m3-brain-capability-league-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BRAIN_CAPABILITY_LEAGUE_MEASURING",
        "routing_state": routing_state,
        "brains": brains,
        "combination_experiments": combinations,
        "current_truth": {
            "capability_configuration_can_be_verified_now": True,
            "runtime_health_can_be_verified_now": True,
            "latency_cost_usage_can_be_measured_now": True,
            "task_accuracy_is_not_yet_proven": not any_accuracy,
            "best_model_by_task_is_not_yet_proven": not any_accuracy,
        },
        "decision_rule": "Do not auto-route or downgrade a model from cost, latency, or anecdotal wins alone. Require exact task-to-outcome linkage, shadow comparison, and human approval before production routing changes.",
        "safety": {
            "provider_requests_made_by_scorecard": False,
            "model_routing_auto_change": False,
            "threshold_auto_change": False,
            "committee_change_authority": False,
            "risk_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Grok/OpenAI/Gemini capability scorecard")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = read_json(expand(args.config))
    scientific = read_json(expand(str(config.get("scientific_measurement_path") or APP / "scientific-measurement" / "latest_scientific_measurement.json")))
    model_health = read_json(expand(str(config.get("model_agent_health_path") or APP / "model-agent-health" / "latest_model_agent_health.json")))
    snapshot = build_brain_league(scientific, model_health)
    output = expand(str(config.get("brain_league_output_path") or APP / "brain-league" / "latest_brain_capability_league.json"))
    atomic_write(output, snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
