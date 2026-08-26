#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "iios_observation_runner.py"
text = RUNNER.read_text(encoding="utf-8")

required = [
    'DEFAULT_CYCLE_MINUTES = 15',
    'DEFAULT_MARKET_SCAN_MINUTES = 30',
    'DEFAULT_OFF_HOURS_SCAN_MINUTES = 120',
    'MAX_PROMOTIONS_PER_SCAN = 1',
    'scan_universe',
    'promote_candidate',
    'run_eight_agent_orchestration',
    'refresh_due_profiles',
    'record_live_portfolio_snapshot',
    'OBSERVATION_CYCLE_COMPLETE',
    '"auto_trade_authority": False',
    '"trade_execution_permission": False',
    '"live_execution": False',
    '"broker_connected": False',
]

for token in required:
    assert token in text, f"Missing Batch 9A contract token: {token}"

for forbidden in [
    '"live_execution": True',
    '"trade_execution_permission": True',
    '"auto_trade_authority": True',
    'alpaca',
    'interactive_brokers',
    'ib_insync',
    'submit_order(',
]:
    assert forbidden.lower() not in text.lower(), f"Forbidden authority/broker token: {forbidden}"

print("BATCH 9A OBSERVATION CONTRACT: PASS")
print("- 15-minute bounded observation cycle")
print("- at most one candidate promoted per scan")
print("- eight-desk + Committee research allowed")
print("- paper portfolio marked/snapshotted")
print("- no broker/live execution authority")
