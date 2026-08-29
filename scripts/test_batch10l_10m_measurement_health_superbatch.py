#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import iios_benchmark_alpha_attribution as bench
import iios_data_health_watchdog as health
import iios_measurement_health_publisher as publisher
import iios_model_cost_governor as cost_governor


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_history(path: Path, start: float, end: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"Date,Open,High,Low,Close,Volume\n2026-08-28,{start},{start},{start},{start},100\n2026-08-31,{end},{end},{end},{end},100\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        research = root / "historical"
        telemetry = {"generated_at": "2026-08-29T00:00:00+00:00", "paper_fund": {"nav": 10000.0, "cash": 10000.0, "transaction_count": 0, "max_drawdown_pct": 0.0}}
        write_history(research / "datasets" / "stooq" / "SPY.csv", 100.0, 110.0)
        write_history(research / "datasets" / "stooq" / "QQQ.csv", 200.0, 220.0)
        b = bench.build_attribution(telemetry=telemetry, research_dir=research, benchmark_dir=root / "benchmark")
        assert b["measurement_contract_ready"] is True
        assert b["status"] == "BENCHMARK_ALPHA_ATTRIBUTION_ACTIVE"
        assert b["controls"]["SPY"]["return_pct"] == 10.0
        assert b["controls"]["QQQ"]["return_pct"] == 10.0
        assert b["controls"]["MECHANICAL_50_50_SPY_QQQ"]["return_pct"] == 10.0
        assert b["safety"]["trade_execution_permission"] is False
        assert b["safety"]["capital_authority"] is False

        # 10M cost governor must never invent spend when exact provider cost is absent.
        cost_dir = root / "cost"
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        empty_cost = cost_governor.build_governor(cost_dir, now=now)
        assert empty_cost["status"] == "MODEL_COST_GOVERNOR_INSTRUMENTATION_REQUIRED"
        assert empty_cost["budget_state"] == "INSTRUMENTATION_GAP"
        assert empty_cost["rolling_7d"]["exact_spend_usd"] is None
        assert empty_cost["rolling_7d"]["exact_cost_coverage_pct"] == 0.0
        assert empty_cost["no_spend_estimate_invented"] is True

        cost_governor.record_usage(cost_dir, {
            "timestamp": "2026-08-29T07:00:00+00:00", "provider": "XAI", "model": "grok-test", "task_type": "RESEARCH", "case_id": "CASE-1", "agent": "GROK_RESEARCH", "input_tokens": 12000, "cached_input_tokens": 4000, "output_tokens": 500, "web_search_calls": 2, "cost_usd": 12.0, "cost_source": "PROVIDER_REPORTED", "query": "What changed?",
        })
        cost_governor.record_usage(cost_dir, {
            "timestamp": "2026-08-29T07:10:00+00:00", "provider": "XAI", "model": "grok-test", "task_type": "RESEARCH", "case_id": "CASE-1", "agent": "GROK_RESEARCH", "input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 100, "web_search_calls": 0, "cost_usd": None, "query": "What changed?",
        })
        active_cost = cost_governor.build_governor(cost_dir, now=now)
        assert active_cost["status"] == "MODEL_COST_GOVERNOR_ACTIVE"
        assert active_cost["budget_state"] == "SOFT_LIMIT"
        assert active_cost["rolling_7d"]["requests"] == 2
        assert active_cost["rolling_7d"]["priced_requests"] == 1
        assert active_cost["rolling_7d"]["unpriced_requests"] == 1
        assert active_cost["rolling_7d"]["exact_spend_usd"] == 12.0
        assert active_cost["rolling_7d"]["exact_cost_coverage_pct"] == 50.0
        assert active_cost["rolling_7d"]["web_search_calls"] == 2
        assert active_cost["safety"]["auto_change_model_routing"] is False
        assert active_cost["safety"]["auto_change_provider"] is False
        assert active_cost["safety"]["capital_authority"] is False
        duplicate_decision = cost_governor.admission_decision(
            artifact=active_cost,
            case_id="CASE-1",
            input_tokens=17000,
            web_searches_requested=6,
            query_fingerprint_value=cost_governor.query_fingerprint("What changed?"),
            now=now,
        )
        assert duplicate_decision["binding"] is False
        assert duplicate_decision["decision"] == "DEFER_EXPENSIVE_RESEARCH"

        state = root / "state"; tele = root / "telemetry"; event = root / "event"; macro = root / "macro"; benchmark = root / "benchmark2"; browser = root / "dist"; launch = root / "launch"
        write_json(tele / "latest.json", {"status": "AVAILABLE"})
        write_json(state / "latest_market_validation.json", {"status": "VALIDATION_COMPLETE"})
        write_json(research / "latest_historical_market_intelligence.json", {"status": "HISTORICAL_RESEARCH_ACTIVE"})
        write_json(event / "latest_historical_event_reconstruction.json", {"status": "HISTORICAL_EVENT_RECONSTRUCTION_ACTIVE"})
        write_json(macro / "latest_historical_macro_regime_library.json", {"status": "HISTORICAL_MACRO_REGIME_LIBRARY_ACTIVE"})
        write_json(benchmark / "latest_benchmark_alpha_attribution.json", {"status": "BENCHMARK_ALPHA_ATTRIBUTION_ACTIVE"})
        write_json(cost_dir / "latest_model_cost_governor.json", active_cost)
        for name in ("historical_market_intelligence.json", "historical_event_reconstruction.json", "historical_macro_regime_library.json", "benchmark_alpha_attribution.json", "model_cost_governor.json"):
            write_json(browser / name, {"status": "PUBLISHED"})
        for label in ("com.iios.historical-market-intelligence", "com.iios.historical-event-reconstruction", "com.iios.historical-macro-regime-library", "com.iios.benchmark-alpha-attribution", "com.iios.model-cost-governor"):
            p = launch / f"{label}.plist"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("plist", encoding="utf-8")
        now_epoch = max(p.stat().st_mtime for p in [tele / "latest.json", research / "latest_historical_market_intelligence.json", event / "latest_historical_event_reconstruction.json", macro / "latest_historical_macro_regime_library.json", benchmark / "latest_benchmark_alpha_attribution.json", cost_dir / "latest_model_cost_governor.json"])
        h = health.build_watchdog(state_dir=state, telemetry_dir=tele, historical_dir=research, event_dir=event, macro_dir=macro, benchmark_dir=benchmark, cost_dir=cost_dir, browser_dir=browser, launch_dir=launch, now=now_epoch)
        assert h["central_data_health"] is True
        assert h["status"] == "DATA_HEALTH_WATCHDOG_ACTIVE"
        assert all(h["health_chain"].values())
        assert h["safety"]["auto_restart_workers"] is False
        cost_rows = [row for row in h["modules"] if row["module"] == "10M_MODEL_COST_CONTROL"]
        assert len(cost_rows) == 1 and cost_rows[0]["critical"] is False

        office = {"whole_stack_inputs": [], "ranked_upgrades": [
            {"upgrade_id": "BENCHMARK_ALPHA_ATTRIBUTION", "priority_score": 110, "action_class": "BUILD_MEASUREMENT_LAYER"},
            {"upgrade_id": "DATA_HEALTH_WATCHDOG", "priority_score": 108, "action_class": "BUILD_OPERATING_CONTROL"},
            {"upgrade_id": "DECISION_ATTRIBUTION_DEPTH", "priority_score": 104, "action_class": "WAIT_AND_MEASURE_THEN_BUILD"},
        ], "top_recommendation": {"upgrade_id": "BENCHMARK_ALPHA_ATTRIBUTION"}}
        patched = publisher._patch_office(office, b, h, active_cost)
        assert patched["top_recommendation"]["upgrade_id"] == "DECISION_ATTRIBUTION_DEPTH"
        assert patched["top_recommendation"]["action_class"] == "WAIT_AND_MEASURE_THEN_BUILD"
        ids = [row["upgrade_id"] for row in patched["ranked_upgrades"]]
        assert "BENCHMARK_ALPHA_ATTRIBUTION" not in ids
        assert "DATA_HEALTH_WATCHDOG" not in ids
        assert patched["historical_diagnostics"]["model_cost_budget_state"] == "SOFT_LIMIT"

    print("BATCH10L_10M_MEASUREMENT_HEALTH_COST_GOVERNOR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
