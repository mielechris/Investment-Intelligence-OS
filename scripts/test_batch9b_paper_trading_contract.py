#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import governed_paper_trading_controller as controller  # noqa: E402


def main() -> int:
    assert controller.MAX_GAP_HUNTS_PER_CYCLE == 1
    assert controller.MAX_PAPER_EXECUTIONS_PER_CYCLE == 1
    assert controller.GAP_RETRY_MINUTES >= 240

    passed = controller.cash_guard(
        available_cash=10_000,
        authorized_max_notional=500,
    )
    assert passed["passed"] is True
    assert passed["remaining_cash_floor"] == 9500.0

    blocked = controller.cash_guard(
        available_cash=400,
        authorized_max_notional=500,
    )
    assert blocked["passed"] is False

    eastern = ZoneInfo("America/New_York")
    regular = datetime(2026, 8, 26, 10, 0, tzinfo=eastern)
    after_hours = datetime(2026, 8, 26, 18, 0, tzinfo=eastern)
    weekend = datetime(2026, 8, 29, 10, 0, tzinfo=eastern)

    assert controller.paper_execution_window_open(regular) is True
    assert controller.paper_execution_window_open(after_hours) is False
    assert controller.paper_execution_window_open(weekend) is False

    source = (BACKEND / "governed_paper_trading_controller.py").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "iios_paper_trading_runner.py").read_text(encoding="utf-8")

    required_fragments = [
        "prepare_paper_authorization",
        "submit_governed_paper_order",
        "BLOCKED_DUPLICATE_TICKER_POSITION",
        "BLOCKED_INSUFFICIENT_PAPER_CASH",
        "WAITING_FOR_REGULAR_SESSION",
        "MAX_PAPER_EXECUTIONS_PER_CYCLE = 1",
        '"broker_connected": False',
        '"live_execution": False',
    ]
    for fragment in required_fragments:
        assert fragment in source, fragment

    assert "import app as _iios_bootstrap" in runner
    assert "--dry-run" in runner
    assert "--no-deepen" in runner

    forbidden = [
        '"live_execution": True',
        '"trade_execution_permission": True',
        '"broker_connected": True',
        "alpaca",
        "interactive_brokers",
        "ib_insync",
    ]
    combined = source.lower()
    for fragment in forbidden:
        assert fragment.lower() not in combined, fragment

    print("Batch 9B governed paper-trading contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
