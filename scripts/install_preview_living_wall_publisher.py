#!/usr/bin/env python3
"""Install and manage only the Preview Living Wall publisher LaunchAgent."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
from typing import Any


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "run_preview_living_wall_publisher.py"
LABEL = "com.iios.living-wall-preview-publisher"


def _runner_module() -> Any:
    spec = importlib.util.spec_from_file_location("preview_living_wall_publisher", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("runner unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def launch_agent_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def launch_domain() -> str:
    return f"gui/{os.getuid()}"


def launch_service() -> str:
    return f"{launch_domain()}/{LABEL}"


def build_plist(policy: dict[str, Any], *, python: str = sys.executable) -> dict[str, Any]:
    if policy.get("label") != LABEL or policy.get("interval_seconds") != 30:
        raise RuntimeError("publisher policy boundary mismatch")
    return {
        "Label": LABEL,
        "ProgramArguments": [python, str(RUNNER)],
        "WorkingDirectory": str(REPO),
        "RunAtLoad": True,
        "StartInterval": 30,
        "KeepAlive": False,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin", "PYTHONUNBUFFERED": "1"},
    }


def _launchctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/launchctl", *arguments], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=15, check=False,
        env={"PATH": "/usr/bin:/bin"},
    )


def _write_plist(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            plistlib.dump(payload, handle, sort_keys=True)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def install() -> int:
    if sys.platform != "darwin":
        print(json.dumps({"status": "FAILED_CLOSED", "failure_code": "MACOS_REQUIRED"}))
        return 1
    module = _runner_module()
    try:
        policy = module.load_policy()
        # Presence checks only. Values remain inside this process and are never printed.
        module.keychain_secret(policy["ingest_keychain"])
        module.keychain_secret(policy["bypass_keychain"])
    except Exception:
        print(json.dumps({"status": "FAILED_CLOSED", "failure_code": "INSTALL_PREFLIGHT_FAILED"}))
        return 1
    path = launch_agent_path()
    payload = build_plist(policy)
    if path.exists():
        _launchctl("bootout", launch_service())
    _write_plist(path, payload)
    result = _launchctl("bootstrap", launch_domain(), str(path))
    if result.returncode != 0:
        print(json.dumps({"status": "FAILED_CLOSED", "failure_code": "LAUNCHCTL_BOOTSTRAP_FAILED"}))
        return 1
    result = _launchctl("kickstart", "-k", launch_service())
    if result.returncode != 0:
        print(json.dumps({"status": "FAILED_CLOSED", "failure_code": "LAUNCHCTL_KICKSTART_FAILED"}))
        return 1
    print(json.dumps({"status": "INSTALLED", "label": LABEL, "interval_seconds": 30}))
    return 0


def stop() -> int:
    result = _launchctl("bootout", launch_service())
    state = "STOPPED" if result.returncode == 0 else "ALREADY_STOPPED"
    print(json.dumps({"status": state, "label": LABEL}))
    return 0


def uninstall() -> int:
    _launchctl("bootout", launch_service())
    path = launch_agent_path()
    if path.exists():
        path.unlink()
    print(json.dumps({"status": "UNINSTALLED", "label": LABEL, "logs_preserved": True}))
    return 0


def status() -> int:
    module = _runner_module()
    try:
        policy = module.load_policy()
    except Exception:
        print(json.dumps({"status": "FAILED_CLOSED", "failure_code": "POLICY_INVALID"}))
        return 1
    loaded = _launchctl("print", launch_service()).returncode == 0
    state = module.read_state(policy)
    safe_state = {
        key: state.get(key)
        for key in (
            "event", "failure_code", "last_attempt_at", "last_success_at",
            "next_attempt_at", "consecutive_failures", "http_status", "availability",
            "freshness", "age_seconds", "live_execution", "telemetry_read_only",
        )
        if key in state
    }
    try:
        remote = module.health_check(policy)
        remote_status = {"status": "CURRENT", **remote}
    except Exception:
        remote_status = {"status": "FAILED_CLOSED"}
    print(json.dumps({"label": LABEL, "loaded": loaded, "state": safe_state, "remote": remote_status}, sort_keys=True))
    return 0 if loaded and remote_status["status"] == "CURRENT" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the IIOS Preview Living Wall publisher")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--install", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--stop", action="store_true")
    actions.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if args.install:
        return install()
    if args.status:
        return status()
    if args.stop:
        return stop()
    return uninstall()


if __name__ == "__main__":
    raise SystemExit(main())
