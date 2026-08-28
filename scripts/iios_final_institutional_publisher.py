#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import iios_agent_performance_league as league
import iios_chief_intelligence_office as chief
import iios_data_expansion_factory as data_factory
import iios_experiment_ab_laboratory as lab
import iios_market_regime_intelligence as regime
import iios_paper_performance_qualification as qualification
import iios_portfolio_intelligence as portfolio
import iios_capital_preservation_stress_lab as stress
import iios_governed_capital_readiness as readiness
import iios_institutional_investment_firm_os as firm
import iios_unified_production_browser as unified


def publish_all(state:Path,telemetry_dir:Path,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    score=unified._read_json(state/"latest_market_validation.json");learning=unified._read_json(state/"latest_outcome_learning.json");telemetry=unified._read_json(telemetry_dir/"latest.json")
    office=chief.build_from_state(state,telemetry_dir);experiments=lab.build_from_state(state,telemetry_dir);expansion=data_factory.build_from_state(state,telemetry_dir);league_payload=league.build_from_state(state,telemetry_dir);regime_payload=regime.build_regime(scorecard=score,learning=learning,league=league_payload,telemetry=telemetry)
    q=qualification.build_qualification(telemetry=telemetry,learning=learning,scorecard=score);p=portfolio.build_portfolio(telemetry=telemetry);u=unified.build_unified(state_dir=state,telemetry_dir=telemetry_dir);s=stress.build_stress(portfolio=p,regime=regime_payload.get("current_regime") or {});r=readiness.build_readiness(qualification=q,stress=s);f=firm.build_firm_os(readiness=r,qualification=q,portfolio=p,regime=regime_payload.get("current_regime") or {})
    artifacts={"chief_intelligence_office.json":office,"experiment_ab_laboratory.json":experiments,"data_expansion_factory.json":expansion,"agent_performance_league.json":league_payload,"market_regime_intelligence.json":regime_payload,"paper_performance_qualification.json":q,"portfolio_intelligence.json":p,"unified_production_browser.json":u,"capital_preservation_stress_lab.json":s,"governed_capital_readiness.json":r,"institutional_investment_firm_os.json":f}
    for name,payload in artifacts.items(): unified._atomic_write(out/name,payload)
    episode=state/"browser"/"daily_factory_episode.json"
    if episode.exists() and episode.is_file(): shutil.copy2(episode,out/"daily_factory_episode.json")
    return {"artifact_count":len(artifacts),"paper_qualification":q.get("status"),"capital_readiness":r.get("status"),"firm_os":f.get("status"),"live_execution":False}


def main()->int:
    parser=argparse.ArgumentParser(description="Refresh final IIOS institutional browser artifacts")
    parser.add_argument("--state-dir",required=True);parser.add_argument("--telemetry-dir",required=True);parser.add_argument("--browser-dir",required=True);args=parser.parse_args()
    result=publish_all(Path(args.state_dir).expanduser(),Path(args.telemetry_dir).expanduser(),Path(args.browser_dir).expanduser())
    import json;print(json.dumps({"status":"FINAL_INSTITUTIONAL_BROWSER_ARTIFACTS_PUBLISHED",**result},sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
