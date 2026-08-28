#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION="batch10d-capital-preservation-stress-lab-v1"
SCENARIOS=(
    ("BROAD_MARKET_DOWN_5",-5.0),("BROAD_MARKET_DOWN_10",-10.0),("BROAD_MARKET_DOWN_20",-20.0),("BROAD_MARKET_UP_10",10.0),
)


def _float(value:Any)->float|None:
    try:return float(value)
    except(TypeError,ValueError):return None


def build_stress(*,portfolio:dict[str,Any],regime:dict[str,Any]|None=None,generated_at:datetime|None=None)->dict[str,Any]:
    nav=_float(portfolio.get("nav")) or 0.0
    positions=[row for row in portfolio.get("positions") or [] if isinstance(row,dict)]
    scenarios=[]
    for name,shock in SCENARIOS:
        pnl=0.0
        for row in positions:
            mv=abs(_float(row.get("market_value")) or 0.0);direction=str(row.get("direction") or "LONG").upper()
            pnl += mv*(shock/100.0)*(-1.0 if direction=="SHORT" else 1.0)
        post_nav=nav+pnl
        scenarios.append({"scenario":name,"shock_pct":shock,"estimated_pnl":round(pnl,2),"estimated_post_stress_nav":round(post_nav,2),"estimated_nav_change_pct":round((pnl/nav)*100.0,2) if nav>0 else None,"forecast":False,"deterministic_hypothetical":True})
    largest=max((abs(_float(row.get("market_value")) or 0.0) for row in positions),default=0.0)
    single_loss=-largest*0.25
    scenarios.append({"scenario":"LARGEST_POSITION_ADVERSE_25","shock_pct":-25.0,"estimated_pnl":round(single_loss,2),"estimated_post_stress_nav":round(nav+single_loss,2),"estimated_nav_change_pct":round((single_loss/nav)*100.0,2) if nav>0 else None,"forecast":False,"deterministic_hypothetical":True})
    worst=min(scenarios,key=lambda row:float(row.get("estimated_pnl") or 0.0)) if scenarios else {}
    status="CASH_ONLY_NO_MARKET_STRESS_EXPOSURE" if not positions else "PAPER_STRESS_LAB_ACTIVE"
    return {
        "schema_version":SCHEMA_VERSION,"generated_at":(generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),"status":status,
        "paper_nav":nav,"position_count":len(positions),"current_regime_label":(regime or {}).get("regime_label"),"scenarios":scenarios,
        "worst_scenario":worst,
        "measurement_gaps":["correlation breakdown and contagion require governed historical covariance data","liquidity slippage and market impact are not modeled","options/nonlinear payoff stress is unavailable without instrument Greeks","overnight gap and halt risk require additional persisted event/liquidity data"],
        "stress_contract":"Deterministic hypothetical shocks only; these are not forecasts, VaR estimates, trade signals or execution instructions.",
        "safety":{"stress_only":True,"paper_only":True,"forecast_authority":False,"auto_reduce_exposure":False,"position_change_authority":False,"risk_rule_change_authority":False,"capital_authority":False,"trade_execution_permission":False,"live_execution":False}
    }
