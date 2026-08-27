#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import high_speed_market_radar as radar  # noqa: E402


assert radar.MAX_PROMOTIONS_PER_CYCLE <= 5
assert radar.MAX_AGENT_CASES_PER_CYCLE <= 2
assert radar.GROK_MAX_BATCHES <= 4
assert radar.KIMI_WORKERS <= 8
assert radar.RECENT_CASE_COOLDOWN_HOURS >= 1
assert radar.DEEP_REFRESH_MINUTES >= 5
assert set(radar.SCREENER_IDS) == {"day_gainers", "day_losers", "most_actives"}
assert radar._canonical_symbol("BRK.B") == "BRK-B"
assert radar._canonical_symbol("brk-b") == "BRK-B"

score, reasons = radar._radar_score(
    {
        "regularMarketChangePercent": 6.0,
        "regularMarketVolume": 3_000_000,
        "averageDailyVolume3Month": 1_000_000,
        "marketCap": 50_000_000_000,
    },
    {"day_gainers", "most_actives"},
)
assert score >= 70.0
assert "LARGE_PRICE_MOVE" in reasons
assert "UNUSUAL_VOLUME" in reasons
assert "MULTI_SCREENER_CONSENSUS" in reasons

pipeline = (BACKEND / "high_speed_market_pipeline.py").read_text(encoding="utf-8")
case_floor = (BACKEND / "high_speed_case_queue.py").read_text(encoding="utf-8")
swarm = (BACKEND / "high_speed_kimi_swarm_worker.py").read_text(encoding="utf-8")
runner = (ROOT / "scripts" / "iios_high_speed_factory_runner.py").read_text(encoding="utf-8")
core = (BACKEND / "high_speed_market_radar.py").read_text(encoding="utf-8")

assert "ThreadPoolExecutor(max_workers=2)" in pipeline
assert "GROK_AND_KIMI_PARALLEL" in pipeline
assert "use_x_search=True" in core
assert "use_web_search=True" in core
assert "research_json_with_web_search" in core
assert "max_tool_rounds=6" in core
assert "run_native_swarm" in swarm
assert "MAX_CONCURRENT_CASES = 2" in case_floor
assert "Radar cadence" in runner
assert "Case-floor cadence" in runner
assert "Kimi Swarm queue cadence" in runner

for text in (core, pipeline, case_floor, swarm, runner):
    assert '"live_execution": True' not in text
    assert '"trade_execution_permission": True' not in text
    assert '"auto_trade_authority": True' not in text
    assert '"paper_order_permission": True' not in text

assert "qualification_evidence\": False" in core
assert "repo_write_access_granted\": False" in swarm
assert "committee_override\": False" in pipeline
assert "risk_override\": False" in pipeline
assert "capital_authority\": False" in pipeline

print("PASS: Batch 9E High-Speed Market Radar contract")
