#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "iios_validation_bridge_supervision.json"
INSTALLER_PATH = ROOT / "scripts" / "install_iios_validation_bridge_supervision.py"
WORKER_PATH = ROOT / "scripts" / "iios_validation_bridge_worker.py"
SUPERVISOR_PATH = ROOT / "scripts" / "iios_validation_bridge_supervisor.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("validation_bridge_installer", INSTALLER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["schema_version"] == "iios-validation-bridge-v1"
    assert set(config["services"]) == {"9H_COLLECTOR", "9H_VALIDATOR", "9I_SHADOW"}
    assert int(config["services"]["9H_COLLECTOR"]["interval_seconds"]) == 300
    assert int(config["services"]["9H_VALIDATOR"]["interval_seconds"]) == 900
    assert int(config["services"]["9I_SHADOW"]["interval_seconds"]) == 1800

    safety = config["safety"]
    for key in ("9A_touched", "9B_touched", "9E_touched", "9G_touched", "9J_touched"):
        assert safety[key] is False
    assert safety["benchmark_collector_ledger_access"] == "NONE"
    assert safety["auto_apply_threshold_changes"] is False
    assert safety["committee_gate_change_authority"] is False
    assert safety["risk_gate_change_authority"] is False
    assert safety["capital_authority"] is False
    assert safety["broker_connected"] is False
    assert safety["trade_execution_permission"] is False
    assert safety["live_execution"] is False

    installer = load_installer()
    paths = installer.runtime_paths(config)
    plist = installer.supervisor_plist(config, paths)
    serialized_plist = json.dumps(plist)
    assert "/Documents/" not in serialized_plist
    assert str(paths["root"]) in serialized_plist
    assert str(paths["supervisor"]) in plist["ProgramArguments"]
    assert plist["WorkingDirectory"] == str(paths["root"])

    runtime = installer.build_runtime_config(
        config,
        gh="/opt/homebrew/bin/gh",
        python=Path("/tmp/iios-python"),
        issue_9h=2,
        issue_9i=3,
    )
    collector_command = runtime["services"]["9H_COLLECTOR"]["command"]
    validator_command = runtime["services"]["9H_VALIDATOR"]["command"]
    shadow_command = runtime["services"]["9I_SHADOW"]["command"]
    assert "--db" not in collector_command
    assert str(config["ledger_path"]) not in collector_command
    assert "--db" in validator_command
    assert "--db" in shadow_command
    assert "--auto" in validator_command
    assert "--auto" in shadow_command
    assert "--min-complete-sessions" not in shadow_command  # preserve Batch 9I default = 5

    worker_source = WORKER_PATH.read_text(encoding="utf-8").lower()
    supervisor_source = SUPERVISOR_PATH.read_text(encoding="utf-8").lower()
    installer_source = INSTALLER_PATH.read_text(encoding="utf-8").lower()
    assert "fcntl.flock" in worker_source
    assert "duplicate_bridge_refused" in worker_source
    assert '"ledger_mode": (\n            "none"\n            if service_key == "9h_collector"' in worker_source
    assert '"9a_touched": false' in supervisor_source
    assert '"9b_touched": false' in supervisor_source
    assert '"9e_touched": false' in supervisor_source
    assert '"9g_touched": false' in supervisor_source
    assert '"9j_touched": false' in supervisor_source
    assert "refusing to migrate 9h during the regular session" in installer_source
    assert "force-session-migration" in installer_source

    combined = "\n".join((worker_source, supervisor_source, installer_source))
    forbidden = (
        '"live_execution": true',
        '"trade_execution_permission": true',
        '"broker_connected": true',
        "submit_governed_paper_order",
        "prepare_paper_authorization",
        "consume_paper_authorization",
    )
    for fragment in forbidden:
        assert fragment not in combined, fragment

    print("IIOS 9H/9I validation Terminal-Bridge contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
