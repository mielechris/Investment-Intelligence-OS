#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from iios_brain_capability_scorecard import build_brain_league  # noqa: E402
from iios_preopen_readiness import market_phase  # noqa: E402

NY = ZoneInfo("America/New_York")


def test_market_phase_contract() -> None:
    assert market_phase(datetime(2026, 9, 1, 9, 20, tzinfo=NY)) == "PREOPEN_WINDOW"
    assert market_phase(datetime(2026, 9, 1, 9, 30, tzinfo=NY)) == "REGULAR_SESSION"
    assert market_phase(datetime(2026, 9, 1, 16, 30, tzinfo=NY)) == "AFTER_HOURS"


def test_brain_league_does_not_invent_accuracy() -> None:
    scientific = {
        "model_task_league": {
            "task_rows": [
                {"provider": "XAI", "model": "grok", "task_type": "RADAR", "requests": 2, "average_latency_ms": 900, "exact_cost_usd": 0.2, "accuracy_score": None},
                {"provider": "GOOGLE", "model": "gemini-3.7-flash", "task_type": "RESEARCH", "requests": 2, "average_latency_ms": 1100, "exact_cost_usd": 0.1, "accuracy_score": None},
                {"provider": "OPENAI", "model": "gpt-5.6-luna", "task_type": "AGENT", "requests": 9, "average_latency_ms": 700, "exact_cost_usd": 0.3, "accuracy_score": None},
            ]
        }
    }
    model_health = {
        "components": [
            {"component": "GROK_GEMINI_MODEL_CONTEXT", "state": "HEALTHY", "detail": {"grok_satisfied": True, "gemini_satisfied": True}},
            {"component": "GEMINI_PRO_DEEP_WORKER", "state": "IDLE_HEALTHY", "detail": {}},
            {"component": "GPT_EIGHT_AGENT_CASE_FLOOR", "state": "HEALTHY", "detail": {}},
            {"component": "EIGHT_GPT_DESKS", "state": "HEALTHY", "detail": {}},
            {"component": "INVESTMENT_COMMITTEE", "state": "HEALTHY", "detail": {}},
        ]
    }
    result = build_brain_league(scientific, model_health)
    assert result["routing_state"] == "HOLD_CURRENT_ROUTING_COLLECT_EVIDENCE"
    assert {row["brain"] for row in result["brains"]} == {"GROK", "GEMINI", "OPENAI"}
    assert all(row["task_accuracy_score"] is None for row in result["brains"])
    assert result["safety"]["model_routing_auto_change"] is False
    assert result["safety"]["trade_execution_permission"] is False
    assert result["safety"]["live_execution"] is False


def test_static_isolation_contract() -> None:
    config = json.loads((ROOT / "config" / "iios_batch10m3_overnight_readiness.json").read_text(encoding="utf-8"))
    safety = config["safety"]
    for key in (
        "9A_touched",
        "9B_touched",
        "9H_touched",
        "9I_touched",
        "backend_8002_changed",
        "model_routing_auto_change",
        "threshold_auto_change",
        "committee_change_authority",
        "risk_change_authority",
        "capital_authority",
        "broker_connected",
        "trade_execution_permission",
        "live_execution",
    ):
        assert safety[key] is False

    activator = (ROOT / "scripts" / "activate_batch10m3_overnight_readiness.py").read_text(encoding="utf-8")
    assert '"/usr/bin/caffeinate", "-imsu"' in activator
    assert "9A / 9B: UNTOUCHED" in activator
    assert "9H / 9I: UNTOUCHED" in activator
    assert "Backend 8002: UNCHANGED" in activator
    assert "SESSION GUARD ACTIVE" in activator


def test_supervisor_is_9e_only() -> None:
    supervisor = (ROOT / "scripts" / "iios_9e_terminal_bridge_supervisor.py").read_text(encoding="utf-8")
    worker = (ROOT / "scripts" / "iios_9e_terminal_bridge_worker.py").read_text(encoding="utf-8")
    assert "scripts/iios_high_speed_factory_runner.py" in supervisor
    assert '"worker": "9E"' in supervisor
    assert '"worker": "9E"' in worker
    assert "iios_observation_runner.py" not in supervisor
    assert "iios_paper_trading_runner.py" not in supervisor


def main() -> int:
    test_market_phase_contract()
    test_brain_league_does_not_invent_accuracy()
    test_static_isolation_contract()
    test_supervisor_is_9e_only()
    print("Batch 10M.3 overnight readiness + brain league: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
