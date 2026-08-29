#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import iios_benchmark_alpha_attribution as benchmark
import iios_data_health_watchdog as health
import iios_final_institutional_publisher as base
import iios_model_cost_governor as cost_governor
import iios_unified_production_browser as unified

DEFAULT_BENCHMARK_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "benchmark-alpha"
DEFAULT_HEALTH_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "browser-health"
DEFAULT_COST_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "model-cost"


def _patch_office(office: dict[str, Any], benchmark_payload: dict[str, Any], health_payload: dict[str, Any], cost_payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(office)
    layers = [dict(row) for row in result.get("whole_stack_inputs", []) if isinstance(row, dict)]
    layers = [row for row in layers if row.get("layer") not in {"10L", "10M"}]
    layers.extend([
        {"layer": "10L", "name": "Benchmark / Alpha Attribution", "status": benchmark_payload.get("status")},
        {"layer": "10M", "name": "Data Health + Model Cost Control", "status": health_payload.get("status"), "cost_status": cost_payload.get("status")},
    ])
    result["whole_stack_inputs"] = layers
    result["whole_stack_input_count"] = len(layers)
    result["whole_stack_inputs_observed"] = sum(1 for row in layers if row.get("status"))

    benchmark_ready = bool(benchmark_payload.get("measurement_contract_ready"))
    health_built = health_payload.get("central_data_health") is True
    remove = set()
    if benchmark_ready:
        remove.add("BENCHMARK_ALPHA_ATTRIBUTION")
    if health_built:
        remove.add("DATA_HEALTH_WATCHDOG")
    ranked = [dict(row) for row in result.get("ranked_upgrades", []) if isinstance(row, dict) and row.get("upgrade_id") not in remove]
    result["ranked_upgrades"] = ranked
    result["top_recommendation"] = ranked[0] if ranked else None

    diagnostics = dict(result.get("historical_diagnostics") or {})
    rolling = cost_payload.get("rolling_7d") if isinstance(cost_payload.get("rolling_7d"), dict) else {}
    diagnostics.update({
        "benchmark_measurement_contract_ready": benchmark_ready,
        "data_health_status": health_payload.get("status"),
        "data_health_chain": health_payload.get("health_chain"),
        "model_cost_governor_status": cost_payload.get("status"),
        "model_cost_budget_state": cost_payload.get("budget_state"),
        "model_cost_exact_coverage_pct": rolling.get("exact_cost_coverage_pct"),
        "model_cost_enforcement_hooks_connected": cost_payload.get("enforcement_hooks_connected"),
        "model_cost_binding_xai_grok_hook": cost_payload.get("binding_xai_grok_hook"),
    })
    result["historical_diagnostics"] = diagnostics
    return result


def publish_all(*, state_dir: Path, telemetry_dir: Path, historical_dir: Path, event_dir: Path, macro_dir: Path, benchmark_dir: Path, health_dir: Path, cost_dir: Path, browser_dir: Path) -> dict[str, Any]:
    base_result = base.publish_all(state_dir, telemetry_dir, browser_dir, historical_dir, event_dir, macro_dir)
    telemetry = unified._read_json(telemetry_dir / "latest.json")
    benchmark_payload = benchmark.build_attribution(telemetry=telemetry, research_dir=historical_dir, benchmark_dir=benchmark_dir)
    unified._atomic_write(benchmark_dir / "latest_benchmark_alpha_attribution.json", benchmark_payload)
    unified._atomic_write(browser_dir / "benchmark_alpha_attribution.json", benchmark_payload)

    # iios_model_cost_governor.build_governor is binding-aware. When the
    # xAI/Grok enforcement hook registry is connected, it reconstructs and
    # preserves MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE instead of downgrading
    # the shared artifact to the legacy advisory/instrumentation state.
    cost_payload = cost_governor.build_governor(cost_dir)
    unified._atomic_write(cost_dir / "latest_model_cost_governor.json", cost_payload)
    unified._atomic_write(browser_dir / "model_cost_governor.json", cost_payload)

    health_payload = health.build_watchdog(
        state_dir=state_dir,
        telemetry_dir=telemetry_dir,
        historical_dir=historical_dir,
        event_dir=event_dir,
        macro_dir=macro_dir,
        benchmark_dir=benchmark_dir,
        cost_dir=cost_dir,
        browser_dir=browser_dir,
    )
    unified._atomic_write(health_dir / "latest_data_health_watchdog.json", health_payload)
    unified._atomic_write(browser_dir / "data_health_watchdog.json", health_payload)

    qualification_path = browser_dir / "paper_performance_qualification.json"
    portfolio_path = browser_dir / "portfolio_intelligence.json"
    watch_path = browser_dir / "qualification_watch.json"
    office_path = browser_dir / "chief_intelligence_office_v2.json"

    q = unified._read_json(qualification_path)
    p = unified._read_json(portfolio_path)
    w = unified._read_json(watch_path)
    office = unified._read_json(office_path)
    benchmark_summary = {
        "status": benchmark_payload.get("status"),
        "measurement_contract_ready": benchmark_payload.get("measurement_contract_ready"),
        "paper_return_pct": (benchmark_payload.get("paper") or {}).get("return_pct") if isinstance(benchmark_payload.get("paper"), dict) else None,
        "excess_return_pct": benchmark_payload.get("excess_return_pct"),
    }
    cost_rolling = cost_payload.get("rolling_7d") if isinstance(cost_payload.get("rolling_7d"), dict) else {}
    cost_summary = {
        "status": cost_payload.get("status"),
        "budget_state": cost_payload.get("budget_state"),
        "exact_cost_coverage_pct": cost_rolling.get("exact_cost_coverage_pct"),
        "exact_spend_usd": cost_rolling.get("exact_spend_usd"),
        "enforcement_hooks_connected": cost_payload.get("enforcement_hooks_connected"),
        "binding_xai_grok_hook": cost_payload.get("binding_xai_grok_hook"),
        "no_spend_estimate_invented": True,
    }
    q["benchmark_alpha_attribution"] = benchmark_summary
    p["benchmark_alpha_attribution"] = benchmark_summary
    w["benchmark_alpha_attribution"] = benchmark_summary
    w["data_health"] = {"status": health_payload.get("status"), "central_data_health": True, "health_chain": health_payload.get("health_chain")}
    w["model_cost_control"] = cost_summary
    office = _patch_office(office, benchmark_payload, health_payload, cost_payload)

    unified._atomic_write(qualification_path, q)
    unified._atomic_write(portfolio_path, p)
    unified._atomic_write(watch_path, w)
    unified._atomic_write(office_path, office)

    top = office.get("top_recommendation") if isinstance(office.get("top_recommendation"), dict) else {}
    return {
        **base_result,
        "artifact_count": int(base_result.get("artifact_count") or 0) + 3,
        "benchmark_alpha_attribution": benchmark_payload.get("status"),
        "benchmark_measurement_contract_ready": benchmark_payload.get("measurement_contract_ready"),
        "data_health_watchdog": health_payload.get("status"),
        "data_health_issues": len(health_payload.get("issues") or []),
        "model_cost_governor": cost_payload.get("status"),
        "model_cost_budget_state": cost_payload.get("budget_state"),
        "model_cost_exact_coverage_pct": cost_rolling.get("exact_cost_coverage_pct"),
        "model_cost_rolling_7d_exact_spend_usd": cost_rolling.get("exact_spend_usd"),
        "model_cost_enforcement_hooks_connected": cost_payload.get("enforcement_hooks_connected"),
        "model_cost_binding_xai_grok_hook": cost_payload.get("binding_xai_grok_hook"),
        "top_recommendation": top.get("upgrade_id"),
        "top_action": top.get("action_class"),
        "live_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh IIOS browser artifacts through Batch 10L/10M with binding-aware cost control.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--historical-dir", required=True)
    parser.add_argument("--event-dir", required=True)
    parser.add_argument("--macro-dir", required=True)
    parser.add_argument("--benchmark-dir", default=str(DEFAULT_BENCHMARK_DIR))
    parser.add_argument("--health-dir", default=str(DEFAULT_HEALTH_DIR))
    parser.add_argument("--cost-dir", default=str(DEFAULT_COST_DIR))
    parser.add_argument("--browser-dir", required=True)
    args = parser.parse_args()
    result = publish_all(
        state_dir=Path(args.state_dir).expanduser(),
        telemetry_dir=Path(args.telemetry_dir).expanduser(),
        historical_dir=Path(args.historical_dir).expanduser(),
        event_dir=Path(args.event_dir).expanduser(),
        macro_dir=Path(args.macro_dir).expanduser(),
        benchmark_dir=Path(args.benchmark_dir).expanduser(),
        health_dir=Path(args.health_dir).expanduser(),
        cost_dir=Path(args.cost_dir).expanduser(),
        browser_dir=Path(args.browser_dir).expanduser(),
    )
    print(json.dumps({"status": "BATCH10L_10M_BROWSER_ARTIFACTS_PUBLISHED", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
