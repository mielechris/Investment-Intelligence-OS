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
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = REPO / "config" / "iios_batch10m3_overnight_readiness.json"
SOURCE_WORKER = REPO / "scripts" / "iios_9e_terminal_bridge_worker.py"
SOURCE_SUPERVISOR = REPO / "scripts" / "iios_9e_terminal_bridge_supervisor.py"
SOURCE_PREOPEN = REPO / "scripts" / "iios_preopen_readiness.py"
SOURCE_BRAIN = REPO / "scripts" / "iios_brain_capability_scorecard.py"
RUNTIME_ROOT = Path.home() / ".iios" / "radar-bridge"
RUNTIME_BIN = RUNTIME_ROOT / "bin"
RUNTIME_CONFIG = RUNTIME_ROOT / "config.json"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / ".iios" / "logs"
NY = ZoneInfo("America/New_York")


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_config() -> dict[str, Any]:
    value = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("Batch 10M.3 config must be a JSON object")
    return value


def run(args: list[str], *, check: bool = False, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(args, 124, exc.stdout or "", exc.stderr or "timeout")
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed rc={result.returncode}: {' '.join(args[:8])}\n{detail[:2500]}")
    return result


def domain() -> str:
    return f"gui/{os.getuid()}"


def launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return run(["launchctl", *args], timeout=20)


def launchd_loaded(label: str) -> bool:
    return launchctl("print", f"{domain()}/{label}").returncode == 0


def bootout(label: str, plist: Path | None = None) -> None:
    if plist is not None and plist.exists():
        launchctl("bootout", domain(), str(plist))
    else:
        launchctl("bootout", f"{domain()}/{label}")


def regular_session_guard_active() -> bool:
    current = datetime.now(NY)
    if current.weekday() >= 5:
        return False
    minute = current.hour * 60 + current.minute
    return 570 <= minute < 970


def validate(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for source in (SOURCE_CONFIG, SOURCE_WORKER, SOURCE_SUPERVISOR, SOURCE_PREOPEN, SOURCE_BRAIN):
        if not source.exists():
            errors.append(f"Missing source: {source}")
    launcher = REPO / "scripts" / "launch_batch9e_live_paper_factory.py"
    if not launcher.exists():
        errors.append(f"Missing 9E launcher: {launcher}")
    safety = config.get("safety") or {}
    for key in ("9A_touched", "9B_touched", "9H_touched", "9I_touched", "backend_8002_changed", "model_routing_auto_change", "threshold_auto_change", "committee_change_authority", "risk_change_authority", "capital_authority", "broker_connected", "trade_execution_permission", "live_execution"):
        if safety.get(key) is not False:
            errors.append(f"Safety contract requires {key}=false")
    return errors


def pgrep(fragment: str) -> list[int]:
    result = run(["pgrep", "-f", fragment], timeout=10)
    if result.returncode not in (0, 1):
        return []
    output: list[int] = []
    for raw in (result.stdout or "").splitlines():
        try:
            pid = int(raw.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            output.append(pid)
    return sorted(set(output))


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def stop_pids(pids: list[int], timeout_seconds: int = 12) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.time() + timeout_seconds
    remaining = list(pids)
    while remaining and time.time() < deadline:
        time.sleep(0.25)
        remaining = [pid for pid in remaining if alive(pid)]
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def plist_path(label: str) -> Path:
    return LAUNCH_AGENTS / f"{label}.plist"


def write_plist(label: str, payload: dict[str, Any]) -> Path:
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    path = plist_path(label)
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    return path


def bootstrap(label: str, path: Path) -> tuple[bool, str]:
    bootout(label, path)
    result = launchctl("bootstrap", domain(), str(path))
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or f"rc={result.returncode}").strip()
    launchctl("enable", f"{domain()}/{label}")
    return True, "LOADED"


def build_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    runtime = json.loads(json.dumps(config))
    runtime["runtime_root"] = str(RUNTIME_ROOT)
    runtime["heartbeat_directory"] = str(Path.home() / ".iios" / "radar-heartbeats")
    runtime["log_directory"] = str(LOG_DIR)
    runtime["launcher_path"] = str(REPO / "scripts" / "launch_batch9e_live_paper_factory.py")
    return runtime


def install_runtime_files(runtime: dict[str, Any]) -> dict[str, Path]:
    RUNTIME_BIN.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (Path.home() / ".iios" / "radar-heartbeats").mkdir(parents=True, exist_ok=True)
    copies = {
        "worker": (SOURCE_WORKER, RUNTIME_BIN / SOURCE_WORKER.name),
        "supervisor": (SOURCE_SUPERVISOR, RUNTIME_BIN / SOURCE_SUPERVISOR.name),
        "preopen": (SOURCE_PREOPEN, RUNTIME_BIN / SOURCE_PREOPEN.name),
        "brain": (SOURCE_BRAIN, RUNTIME_BIN / SOURCE_BRAIN.name),
    }
    output: dict[str, Path] = {}
    for key, (source, destination) in copies.items():
        shutil.copy2(source, destination)
        destination.chmod(0o755)
        output[key] = destination
    RUNTIME_CONFIG.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_terminal_command(worker: Path) -> Path:
    command = RUNTIME_ROOT / "start_9e.command"
    command.write_text(
        "#!/bin/zsh\n"
        "printf '\\033]0;IIOS 9E RADAR SUPERVISED\\007'\n"
        f"exec /usr/bin/python3 '{worker}' --config '{RUNTIME_CONFIG}'\n",
        encoding="utf-8",
    )
    command.chmod(0o755)
    return command


def supervisor_plist(config: dict[str, Any], supervisor: Path) -> dict[str, Any]:
    label = str(config["radar_supervisor_label"])
    return {
        "Label": label,
        "ProgramArguments": ["/usr/bin/python3", str(supervisor), "--config", str(RUNTIME_CONFIG)],
        "WorkingDirectory": str(RUNTIME_ROOT),
        "RunAtLoad": True,
        "StartInterval": max(300, int(config.get("radar_supervisor_interval_seconds") or 300)),
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(LOG_DIR / "9e-supervisor.launchd.out.log"),
        "StandardErrorPath": str(LOG_DIR / "9e-supervisor.launchd.err.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }


def periodic_plist(label: str, script: Path, interval_seconds: int, log_name: str) -> dict[str, Any]:
    return {
        "Label": label,
        "ProgramArguments": ["/usr/bin/python3", str(script), "--config", str(RUNTIME_CONFIG)],
        "WorkingDirectory": str(RUNTIME_ROOT),
        "RunAtLoad": True,
        "StartInterval": max(300, int(interval_seconds)),
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(LOG_DIR / f"{log_name}.out.log"),
        "StandardErrorPath": str(LOG_DIR / f"{log_name}.err.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }


def awake_plist(label: str) -> dict[str, Any]:
    return {
        "Label": label,
        "ProgramArguments": ["/usr/bin/caffeinate", "-imsu"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(LOG_DIR / "market-awake.out.log"),
        "StandardErrorPath": str(LOG_DIR / "market-awake.err.log"),
    }


def run_once(script: Path) -> tuple[int, str]:
    result = run(["/usr/bin/python3", str(script), "--config", str(RUNTIME_CONFIG)], timeout=30)
    return result.returncode, (result.stdout or result.stderr or "").strip()[:4000]


def print_plan(config: dict[str, Any]) -> int:
    errors = validate(config)
    print("=" * 82)
    print("IIOS BATCH 10M.3 — OVERNIGHT READINESS + BRAIN LEAGUE PLAN")
    print("=" * 82)
    print("Runtime mutation: NONE")
    print("9E supervision: isolated Terminal-Bridge under ~/.iios/radar-bridge")
    print("Pre-open readiness: every 5 minutes")
    print("Brain capability league: every 5 minutes; read-only measurement only")
    print("Awake guard: caffeinate -imsu; keep Mac plugged in, logged in, lid open")
    print("9A / 9B: UNTOUCHED")
    print("9H / 9I: UNTOUCHED")
    print("Backend 8002: UNCHANGED")
    print("Model routing auto-change: FALSE")
    print("Live execution: FALSE")
    print("Trade execution permission: FALSE")
    print("SESSION GUARD:", "ACTIVE" if regular_session_guard_active() else "CLEAR")
    if errors:
        print("Validation: FAIL")
        for error in errors:
            print(" -", error)
        return 2
    print("Validation: PASS")
    print("Activate with: --activate")
    return 0


def activate(config: dict[str, Any]) -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 10M.3 activation is macOS-only")
    errors = validate(config)
    if errors:
        for error in errors:
            print(error)
        return 2
    if regular_session_guard_active():
        print("SESSION GUARD ACTIVE: refusing to migrate 9E during the regular market session. Run after 16:10 ET.")
        return 3

    runtime = build_runtime_config(config)
    files = install_runtime_files(runtime)
    command = write_terminal_command(files["worker"])

    fragment = str(runtime.get("runner_process_fragment") or "scripts/iios_high_speed_factory_runner.py")
    prior_9e = pgrep(fragment)
    stop_pids(prior_9e)

    labels = {
        "radar": str(runtime["radar_supervisor_label"]),
        "preopen": str(runtime["preopen_label"]),
        "brain": str(runtime["brain_league_label"]),
        "awake": str(runtime["awake_label"]),
    }
    plists = {
        "radar": write_plist(labels["radar"], supervisor_plist(runtime, files["supervisor"])),
        "preopen": write_plist(labels["preopen"], periodic_plist(labels["preopen"], files["preopen"], int(runtime.get("preopen_interval_seconds") or 300), "preopen-readiness")),
        "brain": write_plist(labels["brain"], periodic_plist(labels["brain"], files["brain"], int(runtime.get("brain_league_interval_seconds") or 300), "brain-league")),
        "awake": write_plist(labels["awake"], awake_plist(labels["awake"])),
    }

    failures: list[str] = []
    for key in ("radar", "preopen", "brain", "awake"):
        ok, detail = bootstrap(labels[key], plists[key])
        if not ok:
            failures.append(f"{key} launchd load failed: {detail}")

    open_result = run(["/usr/bin/open", "-g", "-a", "Terminal", str(command)], timeout=20)
    if open_result.returncode != 0:
        failures.append(f"9E Terminal bridge open failed rc={open_result.returncode}: {(open_result.stderr or open_result.stdout).strip()}")

    time.sleep(8)
    preopen_rc, preopen_output = run_once(files["preopen"])
    brain_rc, brain_output = run_once(files["brain"])

    print("=" * 82)
    print("IIOS BATCH 10M.3 — ACTIVATION RESULT")
    print("=" * 82)
    print("Prior 9E runner PIDs migrated:", prior_9e)
    print("9E Terminal-Bridge open rc:", open_result.returncode)
    print("9E radar supervisor loaded:", launchd_loaded(labels["radar"]))
    print("Pre-open readiness worker loaded:", launchd_loaded(labels["preopen"]))
    print("Brain capability league loaded:", launchd_loaded(labels["brain"]))
    print("Awake guard loaded:", launchd_loaded(labels["awake"]))
    print("Pre-open one-shot rc:", preopen_rc)
    print(preopen_output[-2500:])
    print("Brain league one-shot rc:", brain_rc)
    print(brain_output[-2500:])
    print("9A / 9B: UNTOUCHED")
    print("9H / 9I: UNTOUCHED")
    print("Backend 8002: UNCHANGED")
    print("Live execution: FALSE / UNCHANGED")
    print("Trade execution permission: FALSE / UNCHANGED")

    if failures:
        print("Activation: ATTENTION")
        for failure in failures:
            print(" -", failure)
        return 2
    print("Activation: PASS")
    print("Mac requirement overnight: plugged in, logged in, lid open. Screen may turn off; system idle sleep is inhibited.")
    return 0


def status(config: dict[str, Any]) -> int:
    labels = {
        "radar": str(config["radar_supervisor_label"]),
        "preopen": str(config["preopen_label"]),
        "brain": str(config["brain_league_label"]),
        "awake": str(config["awake_label"]),
    }
    print("IIOS BATCH 10M.3 STATUS")
    for key, label in labels.items():
        print(f"{key}: {label}: {'LOADED' if launchd_loaded(label) else 'NOT_LOADED'}")

    artifacts = {
        "radar": RUNTIME_ROOT / "latest_status.json",
        "preopen": expand(str(config.get("preopen_output_path") or "~/Library/Application Support/IIOS/overnight-readiness/latest_preopen_readiness.json")),
        "brain": expand(str(config.get("brain_league_output_path") or "~/Library/Application Support/IIOS/brain-league/latest_brain_capability_league.json")),
    }
    for key, path in artifacts.items():
        print(f"\n----- {key.upper()} -----")
        if path.exists():
            print(path.read_text(encoding="utf-8")[:12000])
        else:
            print(f"No artifact yet: {path}")
    return 0 if all(launchd_loaded(label) for label in labels.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate Batch 10M.3 overnight readiness and brain league")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--activate", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()
    config = read_config()
    if args.activate:
        return activate(config)
    if args.status:
        return status(config)
    return print_plan(config)


if __name__ == "__main__":
    raise SystemExit(main())
