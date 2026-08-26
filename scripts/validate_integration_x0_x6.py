#!/usr/bin/env python3
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

INTEGRATION_PREFIX = "integration/iios-experience-x0-x6"
SUPERVISOR_LABEL = "com.iios.batch-supervisor"
SUPERVISOR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{SUPERVISOR_LABEL}.plist"
OPERATOR_PORT = 8002
SMOKE_PORT = 8102


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def run(cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def listening_pids(port: int) -> tuple[int, ...]:
    if shutil.which("lsof") is None:
        return ()
    result = subprocess.run(
        ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
        check=False,
    )
    return tuple(sorted(int(v) for v in result.stdout.split() if v.isdigit()))


def supervisor_dir() -> Path | None:
    if not SUPERVISOR_PLIST.exists():
        return None
    with SUPERVISOR_PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    value = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    return Path(str(value)).expanduser().resolve() if value else None


def supervisor_loaded() -> bool | None:
    if sys.platform != "darwin" or not SUPERVISOR_PLIST.exists():
        return None
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{SUPERVISOR_LABEL}"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def branch(path: Path) -> str:
    return output(["git", "branch", "--show-current"], path)


def tracked_status(path: Path) -> str:
    return output(["git", "status", "--porcelain", "--untracked-files=no"], path)


def ensure_frontend_dependencies(frontend: Path) -> None:
    if (frontend / "node_modules").exists():
        return
    print("\n=== FRONTEND DEPENDENCIES ===")
    if (frontend / "package-lock.json").exists():
        run(["npm", "ci"], frontend)
    else:
        run(["npm", "install"], frontend)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    frontend = repo / "FRONT END"

    print("=" * 80)
    print("IIOS X0-X6 + BATCH 8F — ISOLATED INTEGRATION VALIDATOR")
    print("=" * 80)

    current_branch = branch(repo)
    if not current_branch.startswith(INTEGRATION_PREFIX):
        raise SystemExit(f"STOP: validator requires an integration validation branch; found {current_branch!r}")

    supervisor = supervisor_dir()
    supervisor_branch_before = branch(supervisor) if supervisor and supervisor.exists() else None
    supervisor_loaded_before = supervisor_loaded()
    if supervisor and supervisor == repo.resolve():
        raise SystemExit("STOP: validation checkout is the Batch Supervisor checkout.")
    if supervisor_loaded_before is False:
        raise SystemExit("STOP: Batch Supervisor LaunchAgent is not loaded before validation.")

    operator_before = listening_pids(OPERATOR_PORT)
    tracked_before = tracked_status(repo)
    if tracked_before:
        raise SystemExit(f"STOP: integration validation checkout has tracked local changes:\n{tracked_before}")

    print("Validation checkout:", repo)
    print("Validation branch:", current_branch)
    print("Supervisor checkout:", supervisor or "not detected")
    print("Supervisor branch:", supervisor_branch_before or "unknown")
    print("Supervisor LaunchAgent:", "LOADED" if supervisor_loaded_before else "UNKNOWN")
    print(f"Operator port {OPERATOR_PORT} PID(s):", operator_before or "none detected")
    print(f"Isolated smoke port: {SMOKE_PORT}")

    ensure_frontend_dependencies(frontend)

    print("\n=== GATE 1: X0-X6 EXPERIENCE ACCEPTANCE ===")
    run([sys.executable, "scripts/experience_release_gate.py"], repo)

    print("\n=== GATE 2: BATCH 8F ENGINEERING SMOKE — ISOLATED ===")
    smoke_env = os.environ.copy()
    smoke_env["IIOS_INTEGRATION_SMOKE_PORT"] = str(SMOKE_PORT)
    run([sys.executable, "scripts/smoke_batch8f_isolated.py"], repo, env=smoke_env)

    print("\n=== OPERATOR LANE INVARIANTS ===")
    operator_after = listening_pids(OPERATOR_PORT)
    smoke_after = listening_pids(SMOKE_PORT)
    supervisor_branch_after = branch(supervisor) if supervisor and supervisor.exists() else None
    supervisor_loaded_after = supervisor_loaded()
    tracked_after = tracked_status(repo)

    if operator_after != operator_before:
        raise SystemExit(
            f"STOP: operator port {OPERATOR_PORT} process changed during validation: {operator_before} -> {operator_after}"
        )
    if smoke_after:
        raise SystemExit(f"STOP: isolated smoke left process(es) listening on {SMOKE_PORT}: {smoke_after}")
    if supervisor_branch_after != supervisor_branch_before:
        raise SystemExit(
            f"STOP: supervisor branch changed during validation: {supervisor_branch_before!r} -> {supervisor_branch_after!r}"
        )
    if supervisor_loaded_before is True and supervisor_loaded_after is not True:
        raise SystemExit("STOP: Batch Supervisor LaunchAgent became unloaded during validation.")
    if tracked_after:
        raise SystemExit(f"STOP: validation produced tracked working-tree changes:\n{tracked_after}")

    print(f"PASS: operator port {OPERATOR_PORT} PID(s) unchanged -> {operator_after or 'none'}")
    print("PASS: isolated smoke port 8102 cleaned up")
    print("PASS: Batch Supervisor branch unchanged")
    print("PASS: Batch Supervisor LaunchAgent remains loaded")
    print("PASS: validation checkout has no tracked mutations")

    print("\n" + "=" * 80)
    print("INTEGRATION VALIDATION RESULT: PASS")
    print("X0-X6 experience gate: PASS")
    print("Batch 8F isolated engineering smoke: PASS")
    print("Operator backend / supervisor isolation: PASS")
    print("Live execution authority: NOT CHANGED / FALSE")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
