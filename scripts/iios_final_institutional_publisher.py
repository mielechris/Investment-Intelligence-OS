#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import iios_agent_performance_league as league
import iios_chief_intelligence_office as chief
import iios_chief_intelligence_office_v2 as chief_v2
import iios_data_expansion_factory as data_factory
import iios_experiment_ab_laboratory as lab
import iios_market_regime_intelligence as regime
import iios_paper_performance_qualification as qualification
import iios_portfolio_intelligence as portfolio
import iios_capital_preservation_stress_lab as stress
import iios_governed_capital_readiness as readiness
import iios_institutional_investment_firm_os as firm
import iios_qualification_watch as qualification_watch
import iios_unified_production_browser as unified

DEFAULT_HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
DEFAULT_EVENT_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-event-reconstruction"
DEFAULT_MACRO_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-macro-regime"


def _payload(path: Path, fallback: dict) -> dict:
    if path.exists() and path.is_file():
        value = unified._read_json(path)
        if value:
            return value
    return fallback


def _historical_payload(directory: Path) -> dict:
    return _payload(directory / "latest_historical_market_intelligence.json", {
        "schema_version": "batch10h-historical-market-intelligence-v1", "status": "HISTORICAL_RESEARCH_WARM_UP", "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_RESEARCH", "cycle": {"cycle_count": 0, "processed_symbols": [], "error_count": 0}, "pipeline": [], "coverage": [], "studies": [], "research_summary": {"targets_known": 0, "studies_ready": 0, "errors": []}, "safety": {"read_only_research": True, "capital_authority": False, "trade_execution_permission": False, "live_execution": False}
    })


def _event_payload(directory: Path) -> dict:
    return _payload(directory / "latest_historical_event_reconstruction.json", {
        "schema_version": "batch10j-historical-event-reconstruction-v1", "status": "HISTORICAL_EVENT_RECONSTRUCTION_WARM_UP", "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_EVENT_RESEARCH", "cycle": {"cycle_count": 0, "processed_symbols": [], "error_count": 0}, "coverage": {"symbols_reconstructed": 0, "symbols_ready": 0}, "reconstructions": [], "research_summary": {"symbols_known": 0, "symbols_reconstructed": 0, "symbols_ready": 0, "current_contexts_ready": 0, "analog_contexts_ready": 0, "errors": []}, "safety": {"read_only_research": True, "advisory_only": True, "causal_claim_authority": False, "capital_authority": False, "trade_execution_permission": False, "live_execution": False}
    })


def _macro_payload(directory: Path) -> dict:
    return _payload(directory / "latest_historical_macro_regime_library.json", {
        "schema_version": "batch10k-historical-macro-regime-library-v1", "status": "HISTORICAL_MACRO_REGIME_LIBRARY_WARM_UP", "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_MACRO_RESEARCH", "series_registry": [], "coverage": {"tier_a_series_ready": 0, "tier_b_context_series_ready": 0, "normalized_symbols_ready": 0, "price_analog_studies_seen": 0}, "normalized_studies": [], "pipeline": [], "research_summary": {"normalized_symbols_ready": 0, "tier_a_series_ready": 0, "tier_b_series_ready": 0, "errors": []}, "safety": {"read_only_research": True, "advisory_only": True, "capital_authority": False, "trade_execution_permission": False, "live_execution": False}
    })


def _apply_macro_feedback(office: dict, macro: dict) -> dict:
    result = dict(office)
    coverage = macro.get("coverage") if isinstance(macro.get("coverage"), dict) else {}
    normalized_ready = int(coverage.get("normalized_symbols_ready") or 0)
    macro_active = macro.get("status") == "HISTORICAL_MACRO_REGIME_LIBRARY_ACTIVE" and normalized_ready > 0
    layers = [dict(row) for row in result.get("whole_stack_inputs", []) if isinstance(row, dict)]
    layers.append({"layer": "10K", "name": "Historical Macro + Regime", "status": macro.get("status")})
    result["whole_stack_inputs"] = layers
    result["whole_stack_input_count"] = len(layers)
    result["whole_stack_inputs_observed"] = sum(1 for row in layers if row.get("status"))
    diagnostics = dict(result.get("historical_diagnostics") or {})
    diagnostics.update({
        "macro_regime_status": macro.get("status"),
        "macro_normalized_symbols_ready": normalized_ready,
        "tier_a_macro_series_ready": coverage.get("tier_a_series_ready"),
        "tier_b_context_series_ready": coverage.get("tier_b_context_series_ready"),
        "regime_normalization_state": "ACTIVE" if macro_active else diagnostics.get("regime_normalization_state"),
    })
    result["historical_diagnostics"] = diagnostics
    if macro_active:
        ranked = [dict(row) for row in result.get("ranked_upgrades", []) if isinstance(row, dict) and row.get("upgrade_id") != "HISTORICAL_REGIME_LIBRARY"]
        result["ranked_upgrades"] = ranked
        result["top_recommendation"] = ranked[0] if ranked else None
    return result


def publish_all(state: Path, telemetry_dir: Path, out: Path, historical_dir: Path | None = None, event_dir: Path | None = None, macro_dir: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    score = unified._read_json(state / "latest_market_validation.json")
    learning = unified._read_json(state / "latest_outcome_learning.json")
    telemetry = unified._read_json(telemetry_dir / "latest.json")
    office = chief.build_from_state(state, telemetry_dir)
    experiments = lab.build_from_state(state, telemetry_dir)
    expansion = data_factory.build_from_state(state, telemetry_dir)
    league_payload = league.build_from_state(state, telemetry_dir)
    regime_payload = regime.build_regime(scorecard=score, learning=learning, league=league_payload, telemetry=telemetry)
    q = qualification.build_qualification(telemetry=telemetry, learning=learning, scorecard=score)
    p = portfolio.build_portfolio(telemetry=telemetry)
    u = unified.build_unified(state_dir=state, telemetry_dir=telemetry_dir)
    s = stress.build_stress(portfolio=p, regime=regime_payload.get("current_regime") or {})
    r = readiness.build_readiness(qualification=q, stress=s)
    f = firm.build_firm_os(readiness=r, qualification=q, portfolio=p, regime=regime_payload.get("current_regime") or {})
    w = qualification_watch.build_watch(qualification=q, readiness=r)
    historical = _historical_payload(historical_dir or DEFAULT_HISTORICAL_DIR)
    events = _event_payload(event_dir or DEFAULT_EVENT_DIR)
    macro = _macro_payload(macro_dir or DEFAULT_MACRO_DIR)
    office_v2 = chief_v2.build_office_v2(legacy_office=office, experiment_lab=experiments, data_expansion=expansion, agent_league=league_payload, regime=regime_payload, qualification=q, portfolio=p, readiness=r, qualification_watch=w, historical=historical, event_reconstruction=events)
    office_v2 = _apply_macro_feedback(office_v2, macro)
    artifacts = {
        "chief_intelligence_office.json": office,
        "chief_intelligence_office_v2.json": office_v2,
        "experiment_ab_laboratory.json": experiments,
        "data_expansion_factory.json": expansion,
        "agent_performance_league.json": league_payload,
        "market_regime_intelligence.json": regime_payload,
        "paper_performance_qualification.json": q,
        "portfolio_intelligence.json": p,
        "unified_production_browser.json": u,
        "capital_preservation_stress_lab.json": s,
        "governed_capital_readiness.json": r,
        "institutional_investment_firm_os.json": f,
        "qualification_watch.json": w,
        "historical_market_intelligence.json": historical,
        "historical_event_reconstruction.json": events,
        "historical_macro_regime_library.json": macro,
    }
    for name, payload in artifacts.items(): unified._atomic_write(out / name, payload)
    episode = state / "browser" / "daily_factory_episode.json"
    if episode.exists() and episode.is_file(): shutil.copy2(episode, out / "daily_factory_episode.json")
    top = office_v2.get("top_recommendation") if isinstance(office_v2.get("top_recommendation"), dict) else {}
    return {
        "artifact_count": len(artifacts),
        "paper_qualification": q.get("status"),
        "qualification_phase": w.get("phase"),
        "qualification_progress_pct": w.get("qualification_progress_pct"),
        "historical_research": historical.get("status"),
        "historical_event_reconstruction": events.get("status"),
        "historical_macro_regime": macro.get("status"),
        "chief_intelligence_office_v2": office_v2.get("status"),
        "top_recommendation": top.get("upgrade_id"),
        "capital_readiness": r.get("status"),
        "firm_os": f.get("status"),
        "live_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh final IIOS browser artifacts through Batch 10K")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--browser-dir", required=True)
    parser.add_argument("--historical-dir", default=str(DEFAULT_HISTORICAL_DIR))
    parser.add_argument("--event-dir", default=str(DEFAULT_EVENT_DIR))
    parser.add_argument("--macro-dir", default=str(DEFAULT_MACRO_DIR))
    args = parser.parse_args()
    result = publish_all(Path(args.state_dir).expanduser(), Path(args.telemetry_dir).expanduser(), Path(args.browser_dir).expanduser(), Path(args.historical_dir).expanduser(), Path(args.event_dir).expanduser(), Path(args.macro_dir).expanduser())
    import json
    print(json.dumps({"status": "FINAL_INSTITUTIONAL_BROWSER_ARTIFACTS_PUBLISHED", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
