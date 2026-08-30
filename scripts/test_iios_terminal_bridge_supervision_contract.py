#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "iios_terminal_bridge_supervision.json"
INSTALLER = ROOT / "scripts" / "install_iios_terminal_bridge_supervision.py"
BRIDGE = ROOT / "scripts" / "iios_terminal_bridge_worker.py"
SUPERVISOR = ROOT / "scripts" / "iios_terminal_bridge_supervisor.py"


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["schema_version"] == "iios-terminal-bridge-supervision-v2"
    assert set(config["workers"]) == {"9A", "9B"}
    assert config["safety"]["managed_workers"] == ["9A", "9B"]
    assert config["safety"]["9E_touched"] is False
    assert config["safety"]["paper_mode"] is True
    assert config["safety"]["broker_connected"] is False
    assert config["safety"]["live_execution"] is False
    assert config["safety"]["trade_execution_permission"] is False
    assert int(config["supervisor_interval_seconds"]) >= 300
    assert int(config["stale_after_minutes"]) >= 45

    installer = INSTALLER.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    supervisor = SUPERVISOR.read_text(encoding="utf-8")

    # launchd must execute only the copied supervisor/config under ~/.iios.
    assert '"ProgramArguments": [' in installer
    assert 'str(paths["supervisor"])' in installer
    assert 'str(paths["config"])' in installer
    assert '"WorkingDirectory": str(paths["root"])' in installer
    assert "launcher_path" not in installer.split("def supervisor_plist", 1)[1].split("def print_plan", 1)[0]

    # Worker access to ~/Documents happens only after Terminal opens the .command bridge.
    assert '["/usr/bin/open", "-g", "-a", "Terminal"' in installer
    assert '["/usr/bin/open", "-g", "-a", "Terminal"' in supervisor
    assert "iios_terminal_bridge_worker.py" in installer

    # Duplicate worker protection is mandatory.
    assert "fcntl.flock" in bridge
    assert "LOCK_EX | fcntl.LOCK_NB" in bridge
    assert "refusing duplicate start" in bridge

    # Stale worker recovery must remain scoped to the two configured workers.
    assert 'for worker_key in ("9A", "9B")' in supervisor
    assert "STALE_COMPLETION_HEARTBEAT" in supervisor
    assert "PROCESS_MISSING" in supervisor
    assert "SIGTERM" in supervisor
    assert '"9E_touched": False' in supervisor

    combined = (installer + "\n" + bridge + "\n" + supervisor).lower()
    forbidden = [
        '"live_execution": true',
        '"broker_connected": true',
        '"trade_execution_permission": true',
        "alpaca",
        "interactive_brokers",
        "ib_insync",
    ]
    for fragment in forbidden:
        assert fragment not in combined, fragment

    print("IIOS Terminal-Bridge supervision v2 contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
