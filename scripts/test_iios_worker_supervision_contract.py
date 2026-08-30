#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import iios_worker_watchdog as watchdog  # noqa: E402


def main() -> int:
    config_path = ROOT / "config" / "iios_worker_supervision.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["schema_version"] == "iios-worker-supervision-v1"
    assert set(config["workers"]) == {"9A", "9B"}
    assert "9E" not in config["workers"]
    assert int(config["watchdog_interval_seconds"]) >= 300
    assert int(config["stale_after_minutes"]) >= 45
    assert int(config["startup_grace_minutes"]) >= 45
    assert int(config["recovery_cooldown_minutes"]) >= 45

    labels = [config["workers"][key]["label"] for key in ("9A", "9B")]
    assert len(labels) == len(set(labels)) == 2
    assert config["workers"]["9A"]["object_type"] == "observation_operations_state"
    assert config["workers"]["9A"]["completed_at_field"] == "last_cycle_completed_at"
    assert config["workers"]["9B"]["object_type"] == "governed_paper_trading_state"
    assert config["workers"]["9B"]["completed_at_field"] == "cycle_completed_at"

    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    fresh = now - timedelta(minutes=10)
    stale = now - timedelta(minutes=50)
    recent_activation = now - timedelta(minutes=5)
    old_activation = now - timedelta(hours=2)
    recent_action = now - timedelta(minutes=5)

    due, reason = watchdog.recovery_due(
        last_completed=stale,
        now=now,
        stale_after_seconds=45 * 60,
        grace_anchor=recent_activation,
        grace_seconds=60 * 60,
        last_action=None,
        cooldown_seconds=60 * 60,
    )
    assert due is False and reason == "STARTUP_GRACE"

    due, reason = watchdog.recovery_due(
        last_completed=stale,
        now=now,
        stale_after_seconds=45 * 60,
        grace_anchor=old_activation,
        grace_seconds=60 * 60,
        last_action=recent_action,
        cooldown_seconds=60 * 60,
    )
    assert due is False and reason == "RECOVERY_COOLDOWN"

    due, reason = watchdog.recovery_due(
        last_completed=stale,
        now=now,
        stale_after_seconds=45 * 60,
        grace_anchor=old_activation,
        grace_seconds=60 * 60,
        last_action=None,
        cooldown_seconds=60 * 60,
    )
    assert due is True and reason == "STALE_COMPLETION_CHECKPOINT"

    due, reason = watchdog.recovery_due(
        last_completed=fresh,
        now=now,
        stale_after_seconds=45 * 60,
        grace_anchor=old_activation,
        grace_seconds=60 * 60,
        last_action=None,
        cooldown_seconds=60 * 60,
    )
    assert due is False and reason == "ON_CADENCE"

    due, reason = watchdog.recovery_due(
        last_completed=None,
        now=now,
        stale_after_seconds=45 * 60,
        grace_anchor=old_activation,
        grace_seconds=60 * 60,
        last_action=None,
        cooldown_seconds=60 * 60,
    )
    assert due is True and reason == "NO_COMPLETION_CHECKPOINT"

    watchdog_source = (ROOT / "scripts" / "iios_worker_watchdog.py").read_text(encoding="utf-8")
    installer_source = (ROOT / "scripts" / "install_iios_worker_supervision.py").read_text(encoding="utf-8")

    for event_name in (
        "WORKER_AUTO_RECOVERY_REQUESTED",
        "WORKER_AUTO_RECOVERY_KICKSTARTED",
        "WORKER_AUTO_RECOVERY_FAILED",
    ):
        assert event_name in watchdog_source

    assert '"kickstart", "-k"' in watchdog_source
    assert '"KeepAlive": True' in installer_source
    assert '"AbandonProcessGroup": False' in installer_source
    assert '"trade_execution_permission": False' in watchdog_source
    assert '"live_execution": False' in watchdog_source
    assert '"broker_connected": False' in watchdog_source

    forbidden = [
        '"trade_execution_permission": True',
        '"live_execution": True',
        '"broker_connected": True',
        "alpaca",
        "interactive_brokers",
        "ib_insync",
    ]
    combined = (watchdog_source + "\n" + installer_source).lower()
    for fragment in forbidden:
        assert fragment.lower() not in combined, fragment

    print("IIOS worker supervision contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
