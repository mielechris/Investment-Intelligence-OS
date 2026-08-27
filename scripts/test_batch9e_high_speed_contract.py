#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"

core_path = BACKEND / "high_speed_market_radar.py"
pipeline_path = BACKEND / "high_speed_market_pipeline.py"
case_floor_path = BACKEND / "high_speed_case_queue.py"
swarm_path = BACKEND / "high_speed_kimi_swarm_worker.py"
runner_path = ROOT / "scripts" / "iios_high_speed_factory_runner.py"
model_acceptance_path = ROOT / "scripts" / "run_batch9e_model_acceptance.py"

for path in (
    core_path,
    pipeline_path,
    case_floor_path,
    swarm_path,
    runner_path,
    model_acceptance_path,
):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

core = core_path.read_text(encoding="utf-8")
pipeline = pipeline_path.read_text(encoding="utf-8")
case_floor = case_floor_path.read_text(encoding="utf-8")
swarm = swarm_path.read_text(encoding="utf-8")
runner = runner_path.read_text(encoding="utf-8")
model_acceptance = model_acceptance_path.read_text(encoding="utf-8")

assert 'MAX_PROMOTIONS_PER_CYCLE = max(1, min(int(os.getenv("IIOS_9E_MAX_PROMOTIONS", "5")), 5))' in core
assert 'MAX_AGENT_CASES_PER_CYCLE = max(1, min(int(os.getenv("IIOS_9E_MAX_AGENT_CASES", "2")), 2))' in core
assert 'GROK_MAX_BATCHES = max(1, min(int(os.getenv("IIOS_9E_GROK_MAX_BATCHES", "2")), 4))' in core
assert 'KIMI_WORKERS = max(1, min(int(os.getenv("IIOS_9E_KIMI_WORKERS", "4")), 8))' in core
assert 'RECENT_CASE_COOLDOWN_HOURS = max(1' in core
assert 'DEEP_REFRESH_MINUTES = max(5' in core
assert '"day_gainers"' in core
assert '"day_losers"' in core
assert '"most_actives"' in core
assert 'return str(value or "").strip().upper().replace(".", "-")' in core

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

# Model-enabled acceptance must remain a dry-run on an isolated copied ledger.
assert 'MODEL_LEDGER = Path("/tmp/iios_batch9e_model_acceptance.db")' in model_acceptance
assert '"--dry-run"' in model_acceptance
assert 'Case promotions: DISABLED' in model_acceptance
assert 'Paper order authority: FALSE' in model_acceptance
assert 'Broker connected: FALSE' in model_acceptance
assert 'Live execution: FALSE' in model_acceptance
assert 'IIOS_9E_GROK_MAX_BATCHES' in model_acceptance
assert 'IIOS_9E_KIMI_FINALISTS' in model_acceptance

for text in (core, pipeline, case_floor, swarm, runner, model_acceptance):
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
