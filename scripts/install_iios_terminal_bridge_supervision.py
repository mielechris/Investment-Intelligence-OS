#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = REPO / "config" / "iios_terminal_bridge_supervision.json"
SOURCE_BRIDGE = REPO / "scripts" / "iios_terminal_bridge_worker.py"
SOURCE_SUPERVISOR = REPO / "scripts" / "iios_terminal_bridge_supervisor.py"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def load_source_config() -> dict[str, Any]:
    value = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set((value.get("workers") or {}).keys()) != {"9A", "9B"}:
        raise SystemExit("Terminal-Bridge source config must define exactly 9A and 9B")
    return value


def launchctl(*args: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["launchctl", *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(["launchctl", *args], 124, exc.stdout or "", exc.stderr or "timeout")


def domain() -> str:
    return f"gui/{os.getuid()}"


def bootout_label(label: str) -> None:
    plist = LAUNCH_AGENTS / f"{label}.plist"
    if plist.exists():
        launchctl("bootout", domain(), str(plist))
    else:
        launchctl("bootout", f"{domain()}/{label}")


def pgrep(fragment: str) -> list[int]:
    result = subprocess.run(["pgrep", "-f", fragment], text=True, capture_output=True, check=False)
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for raw in (result.stdout or "").splitlines():
        try:
            pid = int(raw.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            pids.append(pid)
    return sorted(set(pids))


def stop_pids(pids: list[int], timeout_seconds: int = 10) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.time() + timeout_seconds
    remaining = list(pids)
    while remaining and time.time() < deadline:
        time.sleep(0.25)
        remaining = [pid for pid in remaining if _alive(pid)]
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def validate(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for source in (SOURCE_BRIDGE, SOURCE_SUPERVISOR):
        if not source.exists():
            errors.append(f"Missing supervision source: {source}")
    for key, worker in config["workers"].items():
        launcher = expand(str(worker.get("launcher_path") or ""))
        if not launcher.exists():
            errors.append(f"{key} launcher not found: {launcher}")
    if config.get("safety", {}).get("9E_touched") is not False:
        errors.append("9E must remain explicitly untouched")
    return errors


def runtime_paths(config: dict[str, Any]) -> dict[str, Path]:
    root = expand(str(config.get("runtime_root") or "~/.iios/terminal-bridge"))
    return {
        "root": root,
        "bin": root / "bin",
        "config": root / "config.json",
        "bridge": root / "bin" / "iios_terminal_bridge_worker.py",
        "supervisor": root / "bin" / "iios_terminal_bridge_supervisor.py",
        "plist": LAUNCH_AGENTS / f"{config['supervisor_label']}.plist",
    }


def write_worker_command(config: dict[str, Any], paths: dict[str, Path], key: str) -> Path:
    worker = config["workers"][key]
    command_path = paths["root"] / f"start_{key.lower()}.command"
    title = str(worker.get("terminal_title") or f"IIOS {key} SUPERVISED").replace('"', "")
    text = (
        "#!/bin/zsh\n"
        f"printf '\\033]0;{title}\\007'\n"
        f"exec /usr/bin/python3 '{paths['bridge']}' --config '{paths['config']}' --worker {key}\n"
    )
    command_path.write_text(text, encoding="utf-8")
    command_path.chmod(0o755)
    return command_path


def supervisor_plist(config: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    log_dir = expand(str(config.get("log_directory") or "~/.iios/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    interval = max(300, int(config.get("supervisor_interval_seconds") or 300))
    return {
        "Label": str(config["supervisor_label"]),
        "ProgramArguments": [
            "/usr/bin/python3",
            str(paths["supervisor"]),
            "--config",
            str(paths["config"]),
        ],
        "WorkingDirectory": str(paths["root"]),
        "RunAtLoad": True,
        "StartInterval": interval,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(log_dir / "terminal-bridge-supervisor.launchd.out.log"),
        "StandardErrorPath": str(log_dir / "terminal-bridge-supervisor.launchd.err.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }


def print_plan(config: dict[str, Any]) -> int:
    errors = validate(config)
    paths = runtime_paths(config)
    print("=" * 78)
    print("IIOS TERMINAL-BRIDGE SUPERVISION V2 — PLAN")
    print("=" * 78)
    print("Purpose: avoid direct launchd access to ~/Documents/GitHub")
    print("launchd runtime root:", paths["root"])
    print("Managed workers: 9A, 9B")
    print("9E: UNTOUCHED")
    print("Stale threshold:", config["stale_after_minutes"], "minutes")
    print("Supervisor cadence:", config["supervisor_interval_seconds"], "seconds")
    print("Live execution: FALSE / UNCHANGED")
    print("Broker connected: FALSE / UNCHANGED")
    if errors:
        print("VALIDATION ERRORS:")
        for error in errors:
            print(" -", error)
        return 2
    print("Validation: PASS")
    print("Activate with: --activate")
    return 0


def activate(config: dict[str, Any]) -> int:
    if sys.platform != "darwin":
        raise SystemExit("Terminal-Bridge activation is macOS-only")
    errors = validate(config)
    if errors:
        for error in errors:
            print(error)
        return 2

    paths = runtime_paths(config)
    paths["bin"].mkdir(parents=True, exist_ok=True)
    expand(str(config.get("log_directory") or "~/.iios/logs")).mkdir(parents=True, exist_ok=True)
    expand(str(config.get("heartbeat_directory") or "~/.iios/heartbeats")).mkdir(parents=True, exist_ok=True)

    # Remove the failed direct-launchd design first. These labels are intentionally
    # scoped to 9A/9B/watchdog; 9E is not represented here and cannot be touched.
    for label in config.get("legacy_labels") or []:
        bootout_label(str(label))
    bootout_label(str(config["supervisor_label"]))

    # Stop only the currently running 9A/9B runner fragments to prevent duplicate
    # ownership during the migration.
    stopped: dict[str, list[int]] = {}
    for key, worker in config["workers"].items():
        pids = pgrep(str(worker["runner_process_fragment"]))
        stopped[key] = pids
        stop_pids(pids)

    shutil.copy2(SOURCE_BRIDGE, paths["bridge"])
    shutil.copy2(SOURCE_SUPERVISOR, paths["supervisor"])
    paths["bridge"].chmod(0o755)
    paths["supervisor"].chmod(0o755)

    # Runtime config lives outside Documents so launchd never needs protected-file access.
    runtime_config = json.loads(json.dumps(config))
    runtime_config["runtime_root"] = str(paths["root"])
    runtime_config["log_directory"] = str(expand(str(config.get("log_directory") or "~/.iios/logs")))
    runtime_config["heartbeat_directory"] = str(expand(str(config.get("heartbeat_directory") or "~/.iios/heartbeats")))
    paths["config"].write_text(json.dumps(runtime_config, indent=2, sort_keys=True), encoding="utf-8")

    commands = {key: write_worker_command(runtime_config, paths, key) for key in ("9A", "9B")}

    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    with paths["plist"].open("wb") as handle:
        plistlib.dump(supervisor_plist(runtime_config, paths), handle, sort_keys=True)

    boot = launchctl("bootstrap", domain(), str(paths["plist"]))
    failures: list[str] = []
    if boot.returncode != 0:
        failures.append(f"supervisor bootstrap failed rc={boot.returncode}: {(boot.stderr or boot.stdout).strip()}")
    else:
        launchctl("enable", f"{domain()}/{runtime_config['supervisor_label']}")

    # Initial worker start goes through Terminal. The worker wrappers acquire
    # per-worker locks, so a simultaneous supervisor tick cannot create duplicates.
    opens: dict[str, int] = {}
    for key in ("9A", "9B"):
        result = subprocess.run(
            ["/usr/bin/open", "-g", "-a", "Terminal", str(commands[key])],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        opens[key] = result.returncode
        if result.returncode != 0:
            failures.append(f"{key} Terminal bridge open failed rc={result.returncode}: {(result.stderr or result.stdout).strip()}")

    print("=" * 78)
    print("IIOS TERMINAL-BRIDGE SUPERVISION V2 ACTIVATED")
    print("=" * 78)
    print("Legacy direct LaunchAgents removed:", list(config.get("legacy_labels") or []))
    print("Prior 9A/9B runner PIDs stopped:", stopped)
    print("Runtime root:", paths["root"])
    print("Supervisor:", runtime_config["supervisor_label"])
    print("Initial Terminal bridge opens:", opens)
    print("9E: UNTOUCHED")
    print("Live execution: FALSE / UNCHANGED")
    print("Broker connected: FALSE / UNCHANGED")
    if failures:
        print("ACTIVATION ERRORS:")
        for failure in failures:
            print(" -", failure)
        return 2
    print("Activation: PASS")
    print("9A/9B now run under Terminal security context; launchd supervises only ~/.iios state.")
    return 0


def status(config: dict[str, Any]) -> int:
    paths = runtime_paths(config)
    label = str(config["supervisor_label"])
    result = launchctl("print", f"{domain()}/{label}")
    print("IIOS TERMINAL-BRIDGE SUPERVISION V2 STATUS")
    print(label + ":", "LOADED" if result.returncode == 0 else "NOT_LOADED")
    latest = paths["root"] / "latest_status.json"
    if latest.exists():
        print(latest.read_text(encoding="utf-8"))
    else:
        print("No supervisor status file yet.")
    return 0 if result.returncode == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Install IIOS Terminal-Bridge supervision v2")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--activate", action="store_true")
    mode.add_argument("--status", action="store_true")
    args = parser.parse_args()
    config = load_source_config()
    if args.activate:
        return activate(config)
    if args.status:
        return status(config)
    return print_plan(config)


if __name__ == "__main__":
    raise SystemExit(main())
