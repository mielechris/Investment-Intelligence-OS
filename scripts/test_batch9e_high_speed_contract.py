#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"

core = (BACKEND / "high_speed_market_radar.py").read_text(encoding="utf-8")
pipeline = (BACKEND / "high_speed_market_pipeline.py").read_text(encoding="utf-8")
case_floor = (BACKEND / "high_speed_case_queue.py").read_text(encoding="utf-8")
swarm = (BACKEND / "high_speed_kimi_swarm_worker.py").read_text(encoding="utf-8")
runner = (ROOT / "scripts" / "iios_high_speed_factory_runner.py").read_text(encoding="utf-8")
acceptance = (ROOT / "scripts" / "run_batch9e_high_speed_acceptance.py").read_text(encoding="utf-8")

# Parse every file without importing the production dependency graph.
for text in (core, pipeline, case_floor, swarm, runner, acceptance):
    ast.parse(text)

assert '"day_gainers"' in core
assert '"day_losers"' in core
assert '"most_actives"' in core
assert "STRICT_GOVERNED_UNIVERSE_UNAVAILABLE" in core
assert "current_strict_governed_universe" in core
assert 'replace(".", "-")' in core

# Throughput is deliberately bounded.
assert re.search(r'IIOS_9E_MAX_PROMOTIONS", "5"', core)
assert "MAX_CONCURRENT_CASES = 2" in case_floor
assert re.search(r'IIOS_9E_GROK_MAX_BATCHES", "2"', core)
assert re.search(r'IIOS_9E_KIMI_WORKERS", "4"', core)
assert re.search(r'IIOS_9E_DEEP_REFRESH_MINUTES", "15"', core)
assert "RECENT_GOVERNED_CASE_EXISTS" in core

# Best-capability model routing is explicit but remains context-only.
assert "ThreadPoolExecutor(max_workers=2)" in pipeline
assert "GROK_AND_KIMI_PARALLEL" in pipeline
assert "use_x_search=True" in core
assert "use_web_search=True" in core
assert "research_json_with_web_search" in core
assert "max_tool_rounds=6" in core
assert "run_native_swarm" in swarm
assert "repo_write_access_granted" in swarm

# Independent lanes keep scanning, agent-floor work and swarm work decoupled.
assert "iios-9e-radar" in runner
assert "iios-9e-case-floor" in runner
assert "iios-9e-kimi-swarm" in runner
assert "Radar cadence" in runner
assert "Case-floor cadence" in runner
assert "Kimi Swarm queue cadence" in runner

# First acceptance cannot touch the live ledger and cannot call models/promote.
assert "sqlite_backup" in acceptance
assert '"--dry-run"' in acceptance
assert '"--no-models"' in acceptance
assert "Live ledger mutation: FORBIDDEN" in acceptance

# 9E never creates execution authority.
for text in (core, pipeline, case_floor, swarm, runner):
    assert '"live_execution": True' not in text
    assert '"trade_execution_permission": True' not in text
    assert '"auto_trade_authority": True' not in text
    assert '"paper_order_permission": True' not in text

assert '"qualification_evidence": False' in core
assert '"repo_write_access_granted": False' in swarm
assert '"committee_override": False' in pipeline
assert '"risk_override": False' in pipeline
assert '"capital_authority": False' in pipeline

print("PASS: Batch 9E High-Speed Market Radar contract")
