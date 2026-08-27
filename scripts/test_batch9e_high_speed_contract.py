#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"

core_path = BACKEND / "high_speed_market_radar.py"
gemini_provider_path = BACKEND / "gemini_provider.py"
gemini_rapid_path = BACKEND / "gemini_rapid_research.py"
pipeline_path = BACKEND / "high_speed_gemini_pipeline.py"
case_floor_path = BACKEND / "high_speed_case_queue.py"
deep_worker_path = BACKEND / "high_speed_gemini_deep_worker.py"
runner_path = ROOT / "scripts" / "iios_high_speed_factory_runner.py"
model_acceptance_path = ROOT / "scripts" / "run_batch9e_model_acceptance.py"

paths = (
    core_path,
    gemini_provider_path,
    gemini_rapid_path,
    pipeline_path,
    case_floor_path,
    deep_worker_path,
    runner_path,
    model_acceptance_path,
)
for path in paths:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

core = core_path.read_text(encoding="utf-8")
gemini_provider = gemini_provider_path.read_text(encoding="utf-8")
gemini_rapid = gemini_rapid_path.read_text(encoding="utf-8")
pipeline = pipeline_path.read_text(encoding="utf-8")
case_floor = case_floor_path.read_text(encoding="utf-8")
deep_worker = deep_worker_path.read_text(encoding="utf-8")
runner = runner_path.read_text(encoding="utf-8")
model_acceptance = model_acceptance_path.read_text(encoding="utf-8")

assert 'MAX_PROMOTIONS_PER_CYCLE = max(1, min(int(os.getenv("IIOS_9E_MAX_PROMOTIONS", "5")), 5))' in core
assert 'MAX_AGENT_CASES_PER_CYCLE = max(1, min(int(os.getenv("IIOS_9E_MAX_AGENT_CASES", "2")), 2))' in core
assert 'GROK_MAX_BATCHES = max(1, min(int(os.getenv("IIOS_9E_GROK_MAX_BATCHES", "2")), 4))' in core
assert 'RECENT_CASE_COOLDOWN_HOURS = max(1' in core
assert 'DEEP_REFRESH_MINUTES = max(5' in core
assert '"day_gainers"' in core and '"day_losers"' in core and '"most_actives"' in core
assert 'return str(value or "").strip().upper().replace(".", "-")' in core

# Current Gemini production model choices and provider capabilities.
assert 'DEFAULT_FLASH_MODEL = "gemini-3.7-flash"' in gemini_provider
assert 'DEFAULT_PRO_MODEL = "gemini-3.1-pro-preview"' in gemini_provider
assert '"google_search": {}' in gemini_provider
assert '"url_context": {}' in gemini_provider
assert '"responseFormat"' in gemini_provider
assert '"thinkingConfig"' in gemini_provider
assert '"qualification_evidence": False' in gemini_provider

# Parallel Grok + Gemini rapid research and selective Gemini Pro lane.
assert "ThreadPoolExecutor(max_workers=2)" in pipeline
assert 'MODEL_EXECUTION_MODE = "GROK_AND_GEMINI_PARALLEL"' in pipeline
assert "run_gemini_rapid_research" in pipeline
assert "GEMINI_DEEP_COMPLEXITY_GATE" in pipeline
assert "gemini_deep_research_request" in pipeline
assert "research_json" in deep_worker
assert "pro_model()" in deep_worker
assert 'thinking_level="high"' in deep_worker
assert "MAX_CONCURRENT_CASES = 2" in case_floor
assert "Radar cadence" in runner
assert "Case-floor cadence" in runner
assert "Gemini Pro deep-research queue cadence" in runner
assert "Grok Wire Room" in runner
assert "Gemini Flash" in runner

# Grok keeps its X + web search role.
assert "use_x_search=True" in core
assert "use_web_search=True" in core

# Model-enabled acceptance must remain a dry-run on an isolated copied ledger.
assert 'MODEL_LEDGER = Path("/tmp/iios_batch9e_model_acceptance.db")' in model_acceptance
assert '"--dry-run"' in model_acceptance
assert 'Case promotions: DISABLED' in model_acceptance
assert 'Paper order authority: FALSE' in model_acceptance
assert 'Broker connected: FALSE' in model_acceptance
assert 'Live execution: FALSE' in model_acceptance
assert 'IIOS_9E_GROK_MAX_BATCHES' in model_acceptance
assert 'IIOS_9E_GEMINI_FINALISTS' in model_acceptance
assert 'Gemini execution satisfied' in model_acceptance

for text in (gemini_provider, gemini_rapid, pipeline, case_floor, deep_worker, runner, model_acceptance):
    assert '"live_execution": True' not in text
    assert '"trade_execution_permission": True' not in text
    assert '"auto_trade_authority": True' not in text
    assert '"paper_order_permission": True' not in text

assert '"committee_override": False' in pipeline
assert '"risk_override": False' in pipeline
assert '"capital_authority": False' in pipeline
assert '"qualification_evidence": False' in deep_worker

print("PASS: Batch 9E High-Speed Grok + Gemini contract")
