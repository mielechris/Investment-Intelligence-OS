#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import iios_capital_preservation_stress_lab as stress
import iios_governed_capital_readiness as readiness
import iios_institutional_investment_firm_os as firm
import iios_market_regime_intelligence as regime
import iios_paper_performance_qualification as qualification
import iios_portfolio_intelligence as portfolio
import iios_unified_production_browser as unified


def main()->int:
    parser=argparse.ArgumentParser(description="Publish 10D-10F readiness artifacts")
    parser.add_argument("--state-dir",required=True);parser.add_argument("--telemetry-dir",required=True);parser.add_argument("--browser-dir",required=True);args=parser.parse_args()
    state=Path(args.state_dir).expanduser();telemetry_dir=Path(args.telemetry_dir).expanduser();out=Path(args.browser_dir).expanduser()
    score=unified._read_json(state/"latest_market_validation.json");learning=unified._read_json(state/"latest_outcome_learning.json");telemetry=unified._read_json(telemetry_dir/"latest.json")
    league_payload=unified.league.build_from_state(state,telemetry_dir)
    regime_payload=regime.build_regime(scorecard=score,learning=learning,league=league_payload,telemetry=telemetry)
    q=qualification.build_qualification(telemetry=telemetry,learning=learning,scorecard=score);p=portfolio.build_portfolio(telemetry=telemetry);s=stress.build_stress(portfolio=p,regime=regime_payload.get("current_regime") or {});r=readiness.build_readiness(qualification=q,stress=s);f=firm.build_firm_os(readiness=r,qualification=q,portfolio=p,regime=regime_payload.get("current_regime") or {})
    for name,payload in [("capital_preservation_stress_lab.json",s),("governed_capital_readiness.json",r),("institutional_investment_firm_os.json",f)]: unified._atomic_write(out/name,payload)
    print(json.dumps({"status":"BATCH10D_10F_READINESS_ARTIFACTS_PUBLISHED","stress_status":s.get("status"),"capital_readiness":r.get("status"),"firm_os_status":f.get("status"),"live_capital_authorized":False,"trade_execution_permission":False,"live_execution":False},sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
