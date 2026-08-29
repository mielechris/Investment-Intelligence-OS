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


def _historical_payload(historical_dir: Path) -> dict:
    source = historical_dir / "latest_historical_market_intelligence.json"
    if source.exists() and source.is_file():
        payload = unified._read_json(source)
        if payload:
            return payload
    return {
        "schema_version": "batch10h-historical-market-intelligence-v1",
        "status": "HISTORICAL_RESEARCH_WARM_UP",
        "mode": "TWENTY_FOUR_SEVEN_READ_ONLY_RESEARCH",
        "cycle": {"cycle_count": 0, "processed_symbols": [], "error_count": 0},
        "pipeline": [],
        "coverage": [],
        "studies": [],
        "research_summary": {"targets_known": 0, "studies_ready": 0, "errors": []},
        "historical_scope": {
            "coverage_policy": "NEVER_INFER_OR_BACKFILL_BEYOND_ACTUAL_PROVIDER_ROWS",
            "note": "Waiting for the first governed 10H historical research cycle.",
        },
        "safety": {
            "read_only_research": True,
            "twenty_four_seven_worker": True,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def publish_all(state:Path,telemetry_dir:Path,out:Path,historical_dir:Path|None=None)->dict:
    out.mkdir(parents=True,exist_ok=True)
    score=unified._read_json(state/"latest_market_validation.json");learning=unified._read_json(state/"latest_outcome_learning.json");telemetry=unified._read_json(telemetry_dir/"latest.json")
    office=chief.build_from_state(state,telemetry_dir);experiments=lab.build_from_state(state,telemetry_dir);expansion=data_factory.build_from_state(state,telemetry_dir);league_payload=league.build_from_state(state,telemetry_dir);regime_payload=regime.build_regime(scorecard=score,learning=learning,league=league_payload,telemetry=telemetry)
    q=qualification.build_qualification(telemetry=telemetry,learning=learning,scorecard=score);p=portfolio.build_portfolio(telemetry=telemetry);u=unified.build_unified(state_dir=state,telemetry_dir=telemetry_dir);s=stress.build_stress(portfolio=p,regime=regime_payload.get("current_regime") or {});r=readiness.build_readiness(qualification=q,stress=s);f=firm.build_firm_os(readiness=r,qualification=q,portfolio=p,regime=regime_payload.get("current_regime") or {});w=qualification_watch.build_watch(qualification=q,readiness=r)
    hdir=historical_dir or DEFAULT_HISTORICAL_DIR;historical=_historical_payload(hdir)
    office_v2=chief_v2.build_office_v2(legacy_office=office,experiment_lab=experiments,data_expansion=expansion,agent_league=league_payload,regime=regime_payload,qualification=q,portfolio=p,readiness=r,qualification_watch=w,historical=historical)
    artifacts={
        "chief_intelligence_office.json":office,
        "chief_intelligence_office_v2.json":office_v2,
        "experiment_ab_laboratory.json":experiments,
        "data_expansion_factory.json":expansion,
        "agent_performance_league.json":league_payload,
        "market_regime_intelligence.json":regime_payload,
        "paper_performance_qualification.json":q,
        "portfolio_intelligence.json":p,
        "unified_production_browser.json":u,
        "capital_preservation_stress_lab.json":s,
        "governed_capital_readiness.json":r,
        "institutional_investment_firm_os.json":f,
        "qualification_watch.json":w,
        "historical_market_intelligence.json":historical,
    }
    for name,payload in artifacts.items(): unified._atomic_write(out/name,payload)
    episode=state/"browser"/"daily_factory_episode.json"
    if episode.exists() and episode.is_file(): shutil.copy2(episode,out/"daily_factory_episode.json")
    return {
        "artifact_count":len(artifacts),
        "paper_qualification":q.get("status"),
        "qualification_phase":w.get("phase"),
        "qualification_progress_pct":w.get("qualification_progress_pct"),
        "historical_research":historical.get("status"),
        "chief_intelligence_office_v2":office_v2.get("status"),
        "top_recommendation":(office_v2.get("top_recommendation") or {}).get("upgrade_id") if isinstance(office_v2.get("top_recommendation"),dict) else None,
        "capital_readiness":r.get("status"),
        "firm_os":f.get("status"),
        "live_execution":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description="Refresh final IIOS institutional browser artifacts plus 10G, 10H and 10I self-improvement intelligence")
    parser.add_argument("--state-dir",required=True);parser.add_argument("--telemetry-dir",required=True);parser.add_argument("--browser-dir",required=True);parser.add_argument("--historical-dir",default=str(DEFAULT_HISTORICAL_DIR));args=parser.parse_args()
    result=publish_all(Path(args.state_dir).expanduser(),Path(args.telemetry_dir).expanduser(),Path(args.browser_dir).expanduser(),Path(args.historical_dir).expanduser())
    import json;print(json.dumps({"status":"FINAL_INSTITUTIONAL_BROWSER_ARTIFACTS_PUBLISHED",**result},sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
