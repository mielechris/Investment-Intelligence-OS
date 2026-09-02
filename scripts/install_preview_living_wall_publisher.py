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
import time
from typing import Any


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "run_preview_living_wall_publisher.py"
LABEL = "com.iios.living-wall-preview-publisher"
LAUNCHCTL_TIMEOUT_SECONDS = 15
INSTALL_ACCEPTANCE_TIMEOUT_SECONDS = 90
RUN_AT_LOAD_GRACE_SECONDS = 45
INSTALL_POLL_INTERVAL_SECONDS = 1

INSTALL_FAILURE_CODES = {
    "LAUNCHCTL_BOOTSTRAP_FAILED",
    "LAUNCHCTL_BOOTSTRAP_TIMEOUT",
    "LAUNCHCTL_JOB_NOT_LOADED",
    "PUBLISHER_CYCLE_FAILED",
    "INSTALL_ACCEPTANCE_TIMEOUT",
}


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


def _launchctl(
    *arguments: str,
    timeout_seconds: float = LAUNCHCTL_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/launchctl", *arguments], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=timeout_seconds, check=False,
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


def _rollback_install(path: Path) -> None:
    try:
        _launchctl("bootout", launch_service())
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _fail_install(path: Path, failure_code: str) -> int:
    if failure_code not in INSTALL_FAILURE_CODES:
        failure_code = "INSTALL_ACCEPTANCE_TIMEOUT"
    _rollback_install(path)
    print(json.dumps({"status": "FAILED_CLOSED", "failure_code": failure_code}))
    return 1


def _new_cycle(state: dict[str, Any], baseline: dict[str, Any]) -> bool:
    attempt = state.get("last_attempt_at")
    return isinstance(attempt, str) and bool(attempt) and attempt != baseline.get("last_attempt_at")


def _successful_cycle(state: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return (
        _new_cycle(state, baseline)
        and state.get("event") == "CYCLE_OK"
        and isinstance(state.get("last_success_at"), str)
        and bool(state["last_success_at"])
        and state["last_success_at"] != baseline.get("last_success_at")
        and state.get("last_attempt_at") == state.get("last_success_at")
        and state.get("consecutive_failures") == 0
        and state.get("next_attempt_at") is None
        and state.get("http_status") == 200
        and state.get("availability") == "AVAILABLE"
        and state.get("freshness") == "CURRENT"
        and isinstance(state.get("age_seconds"), int)
        and 0 <= state["age_seconds"] <= 60
        and state.get("live_execution") is False
        and state.get("telemetry_read_only") is True
    )


def _await_installation(
    module: Any,
    policy: dict[str, Any],
    baseline: dict[str, Any],
) -> str | None:
    started = time.monotonic()
    deadline = started + INSTALL_ACCEPTANCE_TIMEOUT_SECONDS
    ever_loaded = False
    kickstart_attempted = False

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            result = _launchctl(
                "print", launch_service(),
                timeout_seconds=min(LAUNCHCTL_TIMEOUT_SECONDS, remaining),
            )
            loaded = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            loaded = False
        ever_loaded = ever_loaded or loaded

        try:
            state = module.read_state(policy)
        except Exception:
            state = {}
        if not isinstance(state, dict):
            state = {}
        if loaded and _successful_cycle(state, baseline):
            return None
        if _new_cycle(state, baseline) and state.get("event") == "CYCLE_FAILED":
            return "PUBLISHER_CYCLE_FAILED"

        now = time.monotonic()
        if not kickstart_attempted and now - started >= RUN_AT_LOAD_GRACE_SECONDS:
            kickstart_attempted = True
            remaining = deadline - now
            if remaining > 0:
                try:
                    _launchctl(
                        "kickstart", "-k", launch_service(),
                        timeout_seconds=min(LAUNCHCTL_TIMEOUT_SECONDS, remaining),
                    )
                except (OSError, subprocess.TimeoutExpired):
                    # A kickstart timeout is not authoritative. The launchd
                    # registration and sanitized cycle status remain the gates.
                    pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(INSTALL_POLL_INTERVAL_SECONDS, remaining))

    if not ever_loaded:
        return "LAUNCHCTL_JOB_NOT_LOADED"
    return "INSTALL_ACCEPTANCE_TIMEOUT"


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
    try:
        baseline = module.read_state(policy)
    except Exception:
        baseline = {}
    if not isinstance(baseline, dict):
        baseline = {}
    if path.exists():
        try:
            _launchctl("bootout", launch_service())
        except (OSError, subprocess.TimeoutExpired):
            pass
    _write_plist(path, payload)
    try:
        result = _launchctl("bootstrap", launch_domain(), str(path))
    except subprocess.TimeoutExpired:
        return _fail_install(path, "LAUNCHCTL_BOOTSTRAP_TIMEOUT")
    except OSError:
        return _fail_install(path, "LAUNCHCTL_BOOTSTRAP_FAILED")
    if result.returncode != 0:
        return _fail_install(path, "LAUNCHCTL_BOOTSTRAP_FAILED")
    failure_code = _await_installation(module, policy, baseline)
    if failure_code is not None:
        return _fail_install(path, failure_code)
    print(json.dumps({
        "status": "INSTALLED", "label": LABEL, "interval_seconds": 30,
        "acceptance": "CYCLE_OK",
    }))
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
