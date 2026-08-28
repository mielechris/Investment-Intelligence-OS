#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import iios_paper_performance_qualification as qualification
import iios_portfolio_intelligence as portfolio
import iios_unified_production_browser as unified


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish 10A-10C operating browser artifacts.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--browser-dir", required=True)
    args = parser.parse_args()
    state = Path(args.state_dir).expanduser(); telemetry_dir = Path(args.telemetry_dir).expanduser(); out = Path(args.browser_dir).expanduser()
    scorecard = unified._read_json(state / "latest_market_validation.json")
    learning = unified._read_json(state / "latest_outcome_learning.json")
    telemetry = unified._read_json(telemetry_dir / "latest.json")
    q = qualification.build_qualification(telemetry=telemetry, learning=learning, scorecard=scorecard)
    p = portfolio.build_portfolio(telemetry=telemetry)
    u = unified.build_unified(state_dir=state, telemetry_dir=telemetry_dir)
    unified._atomic_write(out / "paper_performance_qualification.json", q)
    unified._atomic_write(out / "portfolio_intelligence.json", p)
    unified._atomic_write(out / "unified_production_browser.json", u)
    print(json.dumps({
        "status":"BATCH10A_10C_OPERATING_ARTIFACTS_PUBLISHED",
        "paper_qualification":q.get("status"),
        "portfolio_status":p.get("status"),
        "unified_status":u.get("status"),
        "production_changes_applied":0,
        "capital_authority":False,
        "trade_execution_permission":False,
        "live_execution":False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
