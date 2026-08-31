#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime, time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
SOURCE_BUILDER = REPO / "scripts" / "iios_scientific_measurement_superbatch.py"
VALIDATION_BRIDGE_INSTALLER = REPO / "scripts" / "install_iios_validation_bridge_supervision.py"
LIVE_ROOT = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
BACKEND_PYTHON = LIVE_ROOT / "BACK END" / "backend" / ".venv" / "bin" / "python"
RUNTIME_ROOT = Path.home() / ".iios" / "scientific-measurement"
RUNTIME_BIN = RUNTIME_ROOT / "bin"
RUNTIME_BUILDER = RUNTIME_BIN / "iios_scientific_measurement_superbatch.py"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL = "com.iios.scientific-measurement"
PLIST = LAUNCH_DIR / f"{LABEL}.plist"
NEW_YORK = ZoneInfo("America/New_York")


def domain() -> str:
    return f"gui/{os.getuid()}"


def launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["launchctl", *args], text=True, capture_output=True, check=False, timeout=20)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(["launchctl", *args], 124, exc.stdout or "", exc.stderr or "timeout")


def regular_session_guard_active() -> bool:
    now = datetime.now(NEW_YORK)
    if now.weekday() >= 5:
        return False
    return clock_time(9, 30) <= now.time().replace(tzinfo=None) < clock_time(16, 10)


def validate() -> list[str]:
    errors: list[str] = []
    if not SOURCE_BUILDER.exists():
        errors.append(f"Missing builder: {SOURCE_BUILDER}")
    if not VALIDATION_BRIDGE_INSTALLER.exists():
        errors.append(f"Missing 9H/9I validation bridge installer: {VALIDATION_BRIDGE_INSTALLER}")
    if not BACKEND_PYTHON.exists() or not os.access(BACKEND_PYTHON, os.X_OK):
        errors.append(f"Missing executable IIOS backend Python: {BACKEND_PYTHON}")
    return errors


def print_plan() -> int:
    errors = validate()
    print("=" * 78)
    print("IIOS BATCH 10M.2 — SCIENTIFIC MEASUREMENT SUPERBATCH PLAN")
    print("=" * 78)
    print("Runtime mutation: NONE")
    print("Purpose: prove case-flow integrity, validation recall, model task measurement, benchmark attribution, and data health")
    print("9H/9I hardening: INCLUDED through existing validation Terminal-Bridge installer")
    print("Validation bridge interpreter:", BACKEND_PYTHON)
    print("10J/10K/10L/10M/10M.1 artifacts: CONSUMED WHEN PRESENT; NOT DUPLICATED")
    print("Scientific measurement cadence: 5 minutes")
    print("Runtime root:", RUNTIME_ROOT)
    print("Core 9A/9B/9E workers: UNTOUCHED")
    print("Backend 8002: UNCHANGED")
    print("Live execution: FALSE / UNCHANGED")
    print("Trade execution permission: FALSE / UNCHANGED")
    print("SESSION GUARD:", "ACTIVE" if regular_session_guard_active() else "CLEAR")
    if errors:
        print("Validation: FAIL")
        for error in errors:
            print(" -", error)
        return 2
    print("Validation: PASS")
    print("Activate with: --activate")
    return 0


def install_measurement_worker() -> list[str]:
    failures: list[str] = []
    RUNTIME_BIN.mkdir(parents=True, exist_ok=True)
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_BUILDER, RUNTIME_BUILDER)
    RUNTIME_BUILDER.chmod(0o755)
    payload = {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/python3", str(RUNTIME_BUILDER)],
        "WorkingDirectory": str(RUNTIME_ROOT),
        "RunAtLoad": True,
        "StartInterval": 300,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(RUNTIME_ROOT / "scientific-measurement.out.log"),
        "StandardErrorPath": str(RUNTIME_ROOT / "scientific-measurement.err.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }
    with PLIST.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    launchctl("bootout", domain(), str(PLIST))
    boot = launchctl("bootstrap", domain(), str(PLIST))
    if boot.returncode != 0:
        failures.append(f"bootstrap failed rc={boot.returncode}: {(boot.stderr or boot.stdout).strip()}")
    else:
        launchctl("enable", f"{domain()}/{LABEL}")
        kick = launchctl("kickstart", "-k", f"{domain()}/{LABEL}")
        if kick.returncode not in (0, 124):
            failures.append(f"kickstart failed rc={kick.returncode}: {(kick.stderr or kick.stdout).strip()}")
    return failures


def activate() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 10M.2 activation is macOS-only")
    errors = validate()
    if errors:
        for error in errors:
            print(error)
        return 2
    if regular_session_guard_active():
        print("SESSION GUARD ACTIVE: refusing to migrate 9H/9I during the regular market session. Run again after 16:10 ET.")
        return 3

    validation = subprocess.run([str(BACKEND_PYTHON), str(VALIDATION_BRIDGE_INSTALLER), "--activate"], text=True, check=False)
    failures: list[str] = []
    if validation.returncode != 0:
        failures.append(f"9H/9I validation bridge activation returned {validation.returncode}")

    failures.extend(install_measurement_worker())
    subprocess.run(["/usr/bin/python3", str(RUNTIME_BUILDER)], text=True, check=False)

    print("=" * 78)
    print("IIOS BATCH 10M.2 — SCIENTIFIC MEASUREMENT SUPERBATCH ACTIVATION")
    print("=" * 78)
    print("9H/9I validation bridge: requested via IIOS backend Python")
    print("Scientific measurement worker:", LABEL)
    print("Runtime root:", RUNTIME_ROOT)
    print("9A/9B/9E: UNTOUCHED")
    print("Backend 8002: UNCHANGED")
    print("Live execution: FALSE / UNCHANGED")
    print("Trade execution permission: FALSE / UNCHANGED")
    if failures:
        print("Activation: ATTENTION")
        for failure in failures:
            print(" -", failure)
        return 2
    print("Activation: PASS")
    return 0


def status() -> int:
    result = launchctl("print", f"{domain()}/{LABEL}")
    print("IIOS BATCH 10M.2 STATUS")
    print(LABEL + ":", "LOADED" if result.returncode == 0 else "NOT_LOADED")
    artifact = Path.home() / "Library" / "Application Support" / "IIOS" / "scientific-measurement" / "latest_scientific_measurement.json"
    if artifact.exists():
        print(artifact.read_text(encoding="utf-8"))
    else:
        print("No scientific measurement artifact yet.")
    return 0 if result.returncode == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate IIOS Batch 10M.2 scientific measurement superbatch")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--activate", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.activate:
        return activate()
    if args.status:
        return status()
    return print_plan()


if __name__ == "__main__":
    raise SystemExit(main())
