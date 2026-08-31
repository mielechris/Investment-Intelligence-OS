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
LIVE_LEDGER = LIVE_ROOT / "BACK END" / "backend" / "iios_ledger.db"
RADAR_ROOT = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
RADAR_BACKEND = RADAR_ROOT / "BACK END" / "backend"
BACKEND_PYTHON_CANDIDATES = (
    LIVE_ROOT / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)
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


def resolve_backend_python() -> Path:
    for candidate in BACKEND_PYTHON_CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    searched = ", ".join(str(path) for path in BACKEND_PYTHON_CANDIDATES)
    raise SystemExit(f"No executable IIOS backend Python found. Checked: {searched}")


def refresh_governed_universe_seed(backend_python: Path) -> tuple[bool, str]:
    """Persist a fresh verified production universe for Batch 9H to seed from.

    This uses the same governed S&P 500 + Nasdaq-100 production input adapter that
    Batch 9E uses. It writes only a production-universe snapshot to the live IIOS
    ledger. It does not create cases, orders, positions, threshold changes, or any
    trading authority. Verification remains fail-closed.
    """
    if not RADAR_BACKEND.exists():
        return False, f"Batch 9E backend not found: {RADAR_BACKEND}"
    if not LIVE_LEDGER.exists():
        return False, f"Live IIOS ledger not found: {LIVE_LEDGER}"

    code = r'''
import json
from index_tls_bootstrap import configure_verified_tls

tls = configure_verified_tls()
from batch8c_production_inputs import refresh_production_universe

result = refresh_production_universe(force=True)
summary = {
    "status": result.get("status"),
    "verified_complete": result.get("verified_complete") is True,
    "strict_membership": result.get("strict_membership") is True,
    "symbol_count": int(result.get("symbol_count") or 0),
    "tls_verified": bool(
        tls.get("configured") is True
        and tls.get("certificate_verification") is True
        and tls.get("hostname_verification") is True
    ),
    "paper_mode": result.get("paper_mode") is True,
    "trade_execution_permission": bool(result.get("trade_execution_permission")),
    "live_execution": bool(result.get("live_execution")),
}
print(json.dumps(summary, sort_keys=True))
ok = bool(
    summary["verified_complete"]
    and summary["strict_membership"]
    and summary["tls_verified"]
    and 500 <= summary["symbol_count"] <= 620
    and summary["trade_execution_permission"] is False
    and summary["live_execution"] is False
)
raise SystemExit(0 if ok else 4)
'''

    env = dict(os.environ)
    env["IIOS_DB_PATH"] = str(LIVE_LEDGER)
    env["PYTHONUNBUFFERED"] = "1"
    try:
        result = subprocess.run(
            [str(backend_python), "-c", code],
            cwd=str(RADAR_BACKEND),
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "Governed universe refresh timed out after 120 seconds"

    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    detail = output or error or f"exit={result.returncode}"
    return result.returncode == 0, detail[:3000]


def validate() -> list[str]:
    errors: list[str] = []
    if not SOURCE_BUILDER.exists():
        errors.append(f"Missing builder: {SOURCE_BUILDER}")
    if not VALIDATION_BRIDGE_INSTALLER.exists():
        errors.append(f"Missing 9H/9I validation bridge installer: {VALIDATION_BRIDGE_INSTALLER}")
    if not any(path.exists() and os.access(path, os.X_OK) for path in BACKEND_PYTHON_CANDIDATES):
        errors.append("No executable IIOS backend Python found in known live/main checkout locations")
    if not RADAR_BACKEND.exists():
        errors.append(f"Batch 9E backend not found: {RADAR_BACKEND}")
    if not LIVE_LEDGER.exists():
        errors.append(f"Live IIOS ledger not found: {LIVE_LEDGER}")
    return errors


def print_plan() -> int:
    errors = validate()
    print("=" * 78)
    print("IIOS BATCH 10M.2 — SCIENTIFIC MEASUREMENT SUPERBATCH PLAN")
    print("=" * 78)
    print("Runtime mutation: NONE")
    print("Purpose: prove case-flow integrity, validation recall, model task measurement, benchmark attribution, and data health")
    print("9H/9I hardening: INCLUDED through existing validation Terminal-Bridge installer")
    print("Governed universe seed: AUTO-REFRESHED from the same verified production input layer used by 9E")
    print("10J/10K/10L/10M/10M.1 artifacts: CONSUMED WHEN PRESENT; NOT DUPLICATED")
    print("Scientific measurement cadence: 5 minutes")
    print("Runtime root:", RUNTIME_ROOT)
    try:
        print("Validation bridge Python:", resolve_backend_python())
    except SystemExit:
        print("Validation bridge Python: UNRESOLVED")
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

    backend_python = resolve_backend_python()
    print("Validation bridge Python:", backend_python)

    universe_ok, universe_detail = refresh_governed_universe_seed(backend_python)
    print("Governed universe seed refresh:", "PASS" if universe_ok else "FAIL")
    print("Governed universe seed detail:", universe_detail)
    if not universe_ok:
        print("Activation: ATTENTION")
        print(" - Refusing 9H/9I activation because a fresh verified governed universe could not be persisted")
        return 2

    validation = subprocess.run([str(backend_python), str(VALIDATION_BRIDGE_INSTALLER), "--activate"], text=True, check=False)
    failures: list[str] = []
    if validation.returncode != 0:
        failures.append(f"9H/9I validation bridge activation returned {validation.returncode}")

    failures.extend(install_measurement_worker())
    subprocess.run(["/usr/bin/python3", str(RUNTIME_BUILDER)], text=True, check=False)

    print("=" * 78)
    print("IIOS BATCH 10M.2 — SCIENTIFIC MEASUREMENT SUPERBATCH ACTIVATION")
    print("=" * 78)
    print("9H/9I validation bridge: requested")
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
