#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "iios_worker_supervision.json"
WATCHDOG = REPO / "scripts" / "iios_worker_watchdog.py"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Missing worker supervision config: {CONFIG_PATH}")
    value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("Worker supervision config must be a JSON object")
    workers = value.get("workers")
    if not isinstance(workers, dict) or set(workers) != {"9A", "9B"}:
        raise SystemExit("Worker supervision config must define exactly 9A and 9B")
    return value


def expand_path(value: Any) -> Path:
    return Path(os.path.expanduser(str(value or ""))).resolve()


def state_directory(config: dict[str, Any]) -> Path:
    path = expand_path(config.get("state_directory") or "~/.iios/worker-supervision")
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_directory(config: dict[str, Any]) -> Path:
    path = expand_path(config.get("log_directory") or "~/.iios/logs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def domain() -> str:
    return f"gui/{os.getuid()}"


def launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def plist_path(label: str) -> Path:
    return LAUNCH_AGENTS / f"{label}.plist"


def bootout_label(label: str) -> None:
    path = plist_path(label)
    if path.exists():
        launchctl("bootout", domain(), str(path))
    else:
        launchctl("bootout", f"{domain()}/{label}")


def pgrep(fragment: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", fragment],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return []
    output: list[int] = []
    for line in (result.stdout or "").splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            output.append(pid)
    return sorted(set(output))


def stop_matching_processes(fragment: str, timeout_seconds: int = 12) -> list[int]:
    pids = pgrep(fragment)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if not pids:
        return []

    deadline = time.time() + timeout_seconds
    remaining = list(pids)
    while time.time() < deadline and remaining:
        next_remaining: list[int] = []
        for pid in remaining:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            except PermissionError:
                next_remaining.append(pid)
            else:
                next_remaining.append(pid)
        remaining = next_remaining
        if remaining:
            time.sleep(0.25)

    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return pids


def validate(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    ledger = expand_path(config.get("ledger_path"))
    if not ledger.exists():
        errors.append(f"Governed ledger not found: {ledger}")
    if not WATCHDOG.exists():
        errors.append(f"Watchdog not found: {WATCHDOG}")
    for key, worker in config["workers"].items():
        launcher = expand_path(worker.get("launcher_path"))
        working = expand_path(worker.get("working_directory"))
        if not launcher.exists():
            errors.append(f"{key} launcher not found: {launcher}")
        if not working.exists():
            errors.append(f"{key} working directory not found: {working}")
    return errors


def worker_plist(config: dict[str, Any], worker_key: str) -> dict[str, Any]:
    worker = config["workers"][worker_key]
    label = str(worker["label"])
    logs = log_directory(config)
    return {
        "Label": label,
        "ProgramArguments": [
            "/usr/bin/python3",
            str(expand_path(worker["launcher_path"])),
        ],
        "WorkingDirectory": str(expand_path(worker["working_directory"])),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "AbandonProcessGroup": False,
        "StandardOutPath": str(logs / f"{worker_key.lower()}.launchd.out.log"),
        "StandardErrorPath": str(logs / f"{worker_key.lower()}.launchd.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1"
        },
    }


def watchdog_plist(config: dict[str, Any]) -> dict[str, Any]:
    logs = log_directory(config)
    label = str(config.get("watchdog_label") or "com.iios.worker-watchdog")
    interval = max(300, int(config.get("watchdog_interval_seconds") or 300))
    return {
        "Label": label,
        "ProgramArguments": [
            "/usr/bin/python3",
            str(WATCHDOG),
        ],
        "WorkingDirectory": str(REPO),
        "RunAtLoad": True,
        "StartInterval": interval,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(logs / "worker-watchdog.launchd.out.log"),
        "StandardErrorPath": str(logs / "worker-watchdog.launchd.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1"
        },
    }


def write_plist(label: str, payload: dict[str, Any]) -> Path:
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    path = plist_path(label)
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    return path


def initialize_runtime_state(config: dict[str, Any]) -> Path:
    now = iso_now()
    payload = {
        "activated_at": now,
        "last_watchdog_run_at": None,
        "workers": {
            key: {
                "activated_at": now,
                "last_action_at": None,
                "last_action_reason": "INSTALL_ACTIVATION_GRACE",
            }
            for key in config["workers"]
        },
    }
    path = state_directory(config) / "state.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def print_plan(config: dict[str, Any]) -> int:
    errors = validate(config)
    print("=" * 76)
    print("IIOS WORKER SUPERVISION — INSTALL PLAN")
    print("=" * 76)
    print("Runtime mutation: NONE (plan only)")
    print("Managed workers: 9A Observation, 9B Paper Trading")
    print("9E High-Speed Radar: EXCLUDED / UNCHANGED")
    print("Watchdog interval:", max(300, int(config.get("watchdog_interval_seconds") or 300)), "seconds")
    print("Stale threshold:", max(45, int(config.get("stale_after_minutes") or 45)), "minutes")
    print("Startup grace:", max(45, int(config.get("startup_grace_minutes") or 60)), "minutes")
    print("Recovery cooldown:", max(45, int(config.get("recovery_cooldown_minutes") or 60)), "minutes")
    print("Live execution authority: FALSE / UNCHANGED")
    print("Broker authority: FALSE / UNCHANGED")
    for key, worker in config["workers"].items():
        print(f"{key}: {worker['label']}")
        print(f"    launcher={expand_path(worker['launcher_path'])}")
        print(f"    heartbeat={worker['object_type']}.{worker['completed_at_field']}")
    if errors:
        print("\nVALIDATION ERRORS:")
        for error in errors:
            print("  -", error)
        return 2
    print("\nValidation: PASS")
    print("Activate with: --activate")
    print("=" * 76)
    return 0


def activate(config: dict[str, Any]) -> int:
    if sys.platform != "darwin":
        raise SystemExit("IIOS worker supervision activation is macOS-only")
    errors = validate(config)
    if errors:
        for error in errors:
            print(error)
        return 2

    watchdog_label = str(config.get("watchdog_label") or "com.iios.worker-watchdog")

    # Stop any prior supervised jobs first. This ensures activation is idempotent.
    bootout_label(watchdog_label)
    for worker in config["workers"].values():
        bootout_label(str(worker["label"]))

    # Transition existing terminal-owned workers into launchd ownership. Only the
    # two explicit 9A/9B runner fragments in config are eligible for termination.
    stopped: dict[str, list[int]] = {}
    for key, worker in config["workers"].items():
        stopped[key] = stop_matching_processes(str(worker["runner_process_fragment"]))

    state_file = initialize_runtime_state(config)

    worker_paths: dict[str, Path] = {}
    for key in ("9A", "9B"):
        worker = config["workers"][key]
        label = str(worker["label"])
        path = write_plist(label, worker_plist(config, key))
        worker_paths[key] = path

    watchdog_path = write_plist(watchdog_label, watchdog_plist(config))

    failures: list[str] = []
    for key in ("9A", "9B"):
        label = str(config["workers"][key]["label"])
        result = launchctl("bootstrap", domain(), str(worker_paths[key]))
        if result.returncode != 0:
            failures.append(f"{key} bootstrap failed: {(result.stderr or result.stdout).strip()}")
            continue
        launchctl("enable", f"{domain()}/{label}")
        kick = launchctl("kickstart", "-k", f"{domain()}/{label}")
        if kick.returncode != 0:
            failures.append(f"{key} kickstart failed: {(kick.stderr or kick.stdout).strip()}")

    watchdog_boot = launchctl("bootstrap", domain(), str(watchdog_path))
    if watchdog_boot.returncode != 0:
        failures.append(
            f"watchdog bootstrap failed: {(watchdog_boot.stderr or watchdog_boot.stdout).strip()}"
        )
    else:
        launchctl("enable", f"{domain()}/{watchdog_label}")

    print("=" * 76)
    print("IIOS WORKER SUPERVISION ACTIVATED")
    print("=" * 76)
    print("Terminal-owned workers stopped:", stopped)
    print("9A service:", config["workers"]["9A"]["label"])
    print("9B service:", config["workers"]["9B"]["label"])
    print("Watchdog service:", watchdog_label)
    print("Watchdog state:", state_file)
    print("Logs:", log_directory(config))
    print("9E High-Speed Radar: UNCHANGED")
    print("Live execution: FALSE / UNCHANGED")
    print("Broker connected: FALSE / UNCHANGED")
    if failures:
        print("\nACTIVATION ERRORS:")
        for failure in failures:
            print("  -", failure)
        print("=" * 76)
        return 2
    print("Activation: PASS")
    print("Workers now survive VS Code terminal closure and are restarted by launchd.")
    print("Hung workers are eligible for watchdog kickstart only after the configured grace/cooldown.")
    print("=" * 76)
    return 0


def status(config: dict[str, Any]) -> int:
    labels = [str(config["workers"][key]["label"]) for key in ("9A", "9B")]
    labels.append(str(config.get("watchdog_label") or "com.iios.worker-watchdog"))
    print("IIOS WORKER SUPERVISION STATUS")
    rc = 0
    for label in labels:
        result = launchctl("print", f"{domain()}/{label}")
        loaded = result.returncode == 0
        rc = rc or (0 if loaded else 1)
        print(f"{label}: {'LOADED' if loaded else 'NOT_LOADED'}")
    latest = state_directory(config) / "latest_status.json"
    if latest.exists():
        print("\nLatest watchdog status:")
        print(latest.read_text(encoding="utf-8"))
    return rc


def uninstall(config: dict[str, Any]) -> int:
    watchdog_label = str(config.get("watchdog_label") or "com.iios.worker-watchdog")
    labels = [watchdog_label] + [str(config["workers"][key]["label"]) for key in ("9A", "9B")]
    for label in labels:
        bootout_label(label)
        path = plist_path(label)
        if path.exists():
            path.unlink()
    print("IIOS worker supervision LaunchAgents removed.")
    print("Audit state and logs were preserved.")
    print("9A/9B are NOT automatically returned to terminal ownership.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install launchd supervision for IIOS 9A/9B workers"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--activate", action="store_true", help="Install and activate services")
    mode.add_argument("--status", action="store_true", help="Show launchd/watchdog status")
    mode.add_argument("--uninstall", action="store_true", help="Remove LaunchAgents")
    args = parser.parse_args()

    config = load_config()
    if args.activate:
        return activate(config)
    if args.status:
        return status(config)
    if args.uninstall:
        return uninstall(config)
    return print_plan(config)


if __name__ == "__main__":
    raise SystemExit(main())
