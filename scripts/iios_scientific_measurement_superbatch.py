#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch10m2-scientific-measurement-superbatch-v1"
APP = Path.home() / "Library" / "Application Support" / "IIOS"
DEFAULT_STATE_DIR = APP / "market-validation"
DEFAULT_TELEMETRY_DIR = APP / "telemetry"
DEFAULT_COST_DIR = APP / "model-cost"
DEFAULT_MODEL_HEALTH_DIR = APP / "model-agent-health"
DEFAULT_BENCHMARK_DIR = APP / "benchmark-alpha"
DEFAULT_DATA_HEALTH_DIR = APP / "browser-health"
DEFAULT_EVENT_DIR = APP / "historical-event-reconstruction"
DEFAULT_MACRO_DIR = APP / "historical-macro-regime"
DEFAULT_OUTPUT_DIR = APP / "scientific-measurement"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "NO_DATA")


def build_case_flow(telemetry: dict[str, Any]) -> dict[str, Any]:
    promotions = [row for row in telemetry.get("recent_promotions") or [] if isinstance(row, dict)]
    dispositions: dict[str, int] = defaultdict(int)
    eight_complete = 0
    committee_complete = 0
    risk_complete = 0
    paper_executions = 0
    broken: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    for row in promotions:
        case_id = str(row.get("case_id") or "")
        ticker = str(row.get("ticker") or "UNKNOWN")
        agents = row.get("agents") if isinstance(row.get("agents"), dict) else {}
        committee = row.get("committee") if isinstance(row.get("committee"), dict) else {}
        risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
        execution = row.get("paper_execution") if isinstance(row.get("paper_execution"), dict) else {}
        complete8 = agents.get("eight_agent_complete") is True and _int(agents.get("completed_count")) >= 8
        if complete8:
            eight_complete += 1
        disposition = str(committee.get("disposition") or "")
        if disposition:
            committee_complete += 1
            dispositions[disposition] += 1
        risk_decision = str(risk.get("decision") or "")
        if risk_decision:
            risk_complete += 1
        execution_status = str(execution.get("status") or execution.get("execution") or "")
        if execution_status:
            paper_executions += 1

        stage = "PROMOTED"
        if complete8:
            stage = "EIGHT_AGENTS_COMPLETE"
        if disposition:
            stage = f"COMMITTEE_{disposition}"
        if risk_decision:
            stage = f"RISK_{risk_decision}"
        if execution_status:
            stage = f"PAPER_{execution_status}"

        defects: list[str] = []
        if not complete8:
            defects.append("EIGHT_AGENT_COMPLETION_MISSING")
        if not disposition:
            defects.append("COMMITTEE_DECISION_MISSING")
        if execution_status and risk_decision not in {"APPROVED", "AUTHORIZED"}:
            defects.append("PAPER_EXECUTION_WITHOUT_APPROVED_RISK")
        if defects:
            broken.append({"case_id": case_id, "ticker": ticker, "defects": defects})

        cases.append({
            "case_id": case_id,
            "ticker": ticker,
            "opportunity_score": row.get("opportunity_score"),
            "eight_agent_complete": complete8,
            "committee_disposition": disposition or None,
            "committee_confidence": committee.get("confidence"),
            "risk_decision": risk_decision or None,
            "paper_execution_status": execution_status or None,
            "stage": stage,
        })

    if not promotions:
        state = "NO_RECENT_PROMOTIONS"
    elif broken:
        state = "PIPELINE_DEFECT_DETECTED"
    else:
        state = "WORKING_AS_DESIGNED"

    return {
        "state": state,
        "recent_promoted_case_count": len(promotions),
        "eight_agent_complete_count": eight_complete,
        "committee_complete_count": committee_complete,
        "risk_complete_count": risk_complete,
        "paper_execution_count": paper_executions,
        "committee_dispositions": dict(sorted(dispositions.items())),
        "pipeline_defects": broken,
        "cases": cases[:20],
        "interpretation": (
            "NO_TRADE or WATCH is not a broken case. A governed case is doing its job when it reaches all eight desks and Committee, then stops because Committee/Risk does not authorize paper execution."
        ),
    }


def build_validation_misses(validation: dict[str, Any]) -> dict[str, Any]:
    metrics = validation.get("metrics") if isinstance(validation.get("metrics"), dict) else {}
    missed = [row for row in validation.get("missed_opportunities") or [] if isinstance(row, dict)]
    benchmark_complete = validation.get("benchmark_complete") is True
    benchmark_count = _int(metrics.get("opportunity_count", metrics.get("benchmark_opportunity_count")))
    detected_count = _int(metrics.get("detected_count", metrics.get("eventual_detected_count")))
    reported_missed = _int(metrics.get("missed_count")) or len(missed)
    miss_rate = _float(metrics.get("opportunity_miss_rate_pct", metrics.get("eventual_opportunity_miss_rate_pct")))
    evidence_state = "VALID_FOR_TUNING" if benchmark_complete else "INCOMPLETE_BENCHMARK_DO_NOT_TUNE"
    return {
        "benchmark_complete": benchmark_complete,
        "evidence_state": evidence_state,
        "benchmark_opportunity_count": benchmark_count,
        "factory_detected_count": detected_count,
        "validation_miss_count": reported_missed,
        "validation_miss_rate_pct": miss_rate,
        "examples": missed[:12],
        "plain_english_definition": (
            "A validation miss means the independent 9H benchmark saw a material market mover that met the benchmark rules, but IIOS did not detect that same opportunity in the governed factory window. It does NOT automatically mean IIOS lost money, should have traded it, or made a bad Committee decision. It is a recall/coverage measurement."
        ),
        "tuning_rule": (
            "Do not change radar thresholds from miss statistics unless the 9H benchmark session is complete. Incomplete benchmark coverage can make miss rates misleading."
        ),
    }


def build_model_task_league(cost_events: list[dict[str, Any]], model_health: dict[str, Any], learning: dict[str, Any]) -> dict[str, Any]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {
        "requests": 0,
        "priced_requests": 0,
        "exact_cost_usd": 0.0,
        "latency_total_ms": 0.0,
        "latency_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    })
    for row in cost_events:
        provider = str(row.get("provider") or "UNKNOWN")
        model = str(row.get("model") or "UNKNOWN")
        task = str(row.get("task_type") or "UNKNOWN")
        bucket = buckets[(provider, model, task)]
        bucket["requests"] += 1
        cost = _float(row.get("cost_usd"))
        if cost is not None:
            bucket["priced_requests"] += 1
            bucket["exact_cost_usd"] += cost
        latency = _float(row.get("latency_ms"))
        if latency is not None:
            bucket["latency_total_ms"] += latency
            bucket["latency_count"] += 1
        bucket["input_tokens"] += _int(row.get("input_tokens"))
        bucket["output_tokens"] += _int(row.get("output_tokens"))

    rows: list[dict[str, Any]] = []
    for (provider, model, task), bucket in buckets.items():
        requests = int(bucket["requests"])
        priced = int(bucket["priced_requests"])
        latency_count = int(bucket["latency_count"])
        rows.append({
            "provider": provider,
            "model": model,
            "task_type": task,
            "requests": requests,
            "exact_cost_coverage_pct": round(priced / requests * 100.0, 1) if requests else 0.0,
            "exact_cost_usd": round(float(bucket["exact_cost_usd"]), 6),
            "average_latency_ms": round(float(bucket["latency_total_ms"]) / latency_count, 1) if latency_count else None,
            "input_tokens": int(bucket["input_tokens"]),
            "output_tokens": int(bucket["output_tokens"]),
            "accuracy_score": None,
            "accuracy_state": "MEASUREMENT_GAP_OUTCOME_LINK_NOT_PERSISTED",
        })
    rows.sort(key=lambda row: (row["requests"], row["exact_cost_usd"]), reverse=True)

    health_status = str(model_health.get("status") or "NO_DATA")
    outcome_count = _int(learning.get("outcome_count"))
    return {
        "status": "MODEL_TASK_LEAGUE_MEASURING" if rows else "MODEL_TASK_LEAGUE_INSTRUMENTATION_GAP",
        "model_agent_health_status": health_status,
        "outcome_count_available": outcome_count,
        "task_rows": rows[:30],
        "what_is_measured_now": ["request count", "provider/model/task identity", "tokens", "latency when recorded", "exact provider cost when recorded"],
        "what_is_not_yet_proven": [
            "task-level correctness/accuracy by model",
            "model contribution to later investment outcome",
            "cost per useful/correct result",
            "regime-specific model superiority",
        ],
        "rule": "Do not auto-route models from cost or latency alone. Accuracy/outcome linkage must exist first and any routing change remains shadow-tested and human-approved.",
    }


def build_superbatch(*, state_dir: Path, telemetry_dir: Path, cost_dir: Path, model_health_dir: Path, benchmark_dir: Path, data_health_dir: Path, event_dir: Path, macro_dir: Path) -> dict[str, Any]:
    telemetry = _read_json(telemetry_dir / "latest.json")
    validation = _read_json(state_dir / "latest_market_validation.json")
    shadow = _read_json(state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json")
    learning = _read_json(state_dir / "latest_outcome_learning.json")
    benchmark = _read_json(benchmark_dir / "latest_benchmark_alpha_attribution.json")
    data_health = _read_json(data_health_dir / "latest_data_health_watchdog.json")
    model_health = _read_json(model_health_dir / "latest_model_agent_health.json")
    event_reconstruction = _read_json(event_dir / "latest_historical_event_reconstruction.json")
    macro_regime = _read_json(macro_dir / "latest_historical_macro_regime_library.json")
    cost_events = _read_jsonl(cost_dir / "model_usage.jsonl")

    case_flow = build_case_flow(telemetry)
    misses = build_validation_misses(validation)
    model_league = build_model_task_league(cost_events, model_health, learning)

    layers = [
        {"layer": "9G", "name": "Factory telemetry", "status": telemetry.get("health", {}).get("state") if isinstance(telemetry.get("health"), dict) else "NO_DATA"},
        {"layer": "9H", "name": "Independent validation", "status": _status(validation)},
        {"layer": "9I", "name": "Shadow strategy", "status": _status(shadow)},
        {"layer": "9J", "name": "Outcome learning", "status": _status(learning)},
        {"layer": "10J", "name": "Historical event reconstruction", "status": _status(event_reconstruction)},
        {"layer": "10K", "name": "Historical macro/regime", "status": _status(macro_regime)},
        {"layer": "10L", "name": "Benchmark attribution", "status": _status(benchmark)},
        {"layer": "10M", "name": "End-to-end data health", "status": _status(data_health)},
        {"layer": "10M.1", "name": "Model/agent health", "status": _status(model_health)},
        {"layer": "10M.2", "name": "Model task league", "status": model_league["status"]},
    ]

    shadow_sessions = _int(shadow.get("complete_session_count"))
    mature_5d = _int(learning.get("mature_5d_count"))
    next_actions: list[dict[str, Any]] = []
    if not misses["benchmark_complete"]:
        next_actions.append({"priority": 1, "action": "RESTORE_COMPLETE_9H_SESSIONS", "why": "Independent grading is not trustworthy for tuning until full-session benchmark coverage is complete."})
    if shadow_sessions < 5:
        next_actions.append({"priority": 2, "action": "ACCUMULATE_5_COMPLETE_9H_SESSIONS_FOR_9I", "why": f"9I currently has {shadow_sessions} complete sessions; it requires 5 before threshold advice."})
    if not model_league["task_rows"] or all(row.get("accuracy_score") is None for row in model_league["task_rows"]):
        next_actions.append({"priority": 3, "action": "PERSIST_MODEL_TASK_OUTCOME_LINKAGE", "why": "Cost and latency can be measured, but model accuracy by task is not yet proven."})
    if mature_5d < 30:
        next_actions.append({"priority": 4, "action": "WAIT_FOR_MATURE_CASE_OUTCOMES_BEFORE_REWEIGHTING", "why": f"Only {mature_5d} mature 5-day outcomes are available; deeper decision attribution should mature before weight/routing changes."})
    if case_flow["state"] == "PIPELINE_DEFECT_DETECTED":
        next_actions.insert(0, {"priority": 0, "action": "REPAIR_CASE_PIPELINE", "why": "One or more promoted cases did not follow the governed eight-agent → Committee → Risk/paper sequence."})

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "SCIENTIFIC_MEASUREMENT_SUPERBATCH_ACTIVE",
        "question": "Can IIOS prove that its factory is working, improving, and adding investment value?",
        "case_flow": case_flow,
        "validation_misses": misses,
        "model_task_league": model_league,
        "measurement_layers": layers,
        "benchmark_attribution": {
            "status": _status(benchmark),
            "measurement_contract_ready": benchmark.get("measurement_contract_ready"),
            "paper": benchmark.get("paper"),
            "controls": benchmark.get("controls"),
            "edge_claim_allowed": False,
        },
        "data_health": {
            "status": _status(data_health),
            "health_chain": data_health.get("health_chain"),
            "critical_issues": data_health.get("critical_issues") or [],
        },
        "next_actions": sorted(next_actions, key=lambda row: int(row.get("priority", 999))),
        "proof_policy": {
            "working_process_is_not_equal_to_fresh_data": True,
            "promotion_is_not_equal_to_buy": True,
            "validation_miss_is_not_equal_to_lost_trade": True,
            "paper_profit_is_not_equal_to_alpha": True,
            "low_model_cost_is_not_equal_to_high_model_quality": True,
            "wait_for_evidence_when_sample_is_immature": True,
        },
        "safety": {
            "measurement_observability_only": True,
            "auto_change_thresholds": False,
            "auto_change_agent_weights": False,
            "auto_change_model_routing": False,
            "provider_change_authority": False,
            "committee_change_authority": False,
            "risk_rule_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build IIOS Batch 10M.2 scientific measurement superbatch artifact")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--cost-dir", default=str(DEFAULT_COST_DIR))
    parser.add_argument("--model-health-dir", default=str(DEFAULT_MODEL_HEALTH_DIR))
    parser.add_argument("--benchmark-dir", default=str(DEFAULT_BENCHMARK_DIR))
    parser.add_argument("--data-health-dir", default=str(DEFAULT_DATA_HEALTH_DIR))
    parser.add_argument("--event-dir", default=str(DEFAULT_EVENT_DIR))
    parser.add_argument("--macro-dir", default=str(DEFAULT_MACRO_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = build_superbatch(
        state_dir=Path(args.state_dir).expanduser(),
        telemetry_dir=Path(args.telemetry_dir).expanduser(),
        cost_dir=Path(args.cost_dir).expanduser(),
        model_health_dir=Path(args.model_health_dir).expanduser(),
        benchmark_dir=Path(args.benchmark_dir).expanduser(),
        data_health_dir=Path(args.data_health_dir).expanduser(),
        event_dir=Path(args.event_dir).expanduser(),
        macro_dir=Path(args.macro_dir).expanduser(),
    )
    output = Path(args.output_dir).expanduser() / "latest_scientific_measurement.json"
    _atomic_write(output, payload)
    summary = {
        "status": payload["status"],
        "case_flow": payload["case_flow"]["state"],
        "validation_evidence": payload["validation_misses"]["evidence_state"],
        "model_task_league": payload["model_task_league"]["status"],
        "output": str(output),
        "live_execution": False,
    }
    print(json.dumps(payload if args.stdout else summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
