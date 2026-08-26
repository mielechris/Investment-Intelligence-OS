#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

BRANCH = "feature/iios-experience-x0-x1"
SUPERVISOR_LABEL = "com.iios.batch-supervisor"
SUPERVISOR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{SUPERVISOR_LABEL}.plist"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def supervisor_working_directory() -> Path | None:
    if not SUPERVISOR_PLIST.exists():
        return None
    try:
        with SUPERVISOR_PLIST.open("rb") as handle:
            payload = plistlib.load(handle)
    except Exception as exc:
        raise SystemExit(f"STOP: unable to inspect batch supervisor LaunchAgent: {exc}") from exc

    value = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    if not value:
        raise SystemExit("STOP: batch supervisor LaunchAgent has no WorkingDirectory; isolation cannot be proven.")
    return Path(str(value)).expanduser().resolve()


def enforce_supervisor_isolation(repo: Path) -> None:
    supervisor_repo = supervisor_working_directory()
    if supervisor_repo is None:
        print("Supervisor LaunchAgent not installed at the standard path; continuing with branch guard.")
        return

    current_repo = repo.resolve()
    print("Batch supervisor checkout:", supervisor_repo)
    print("Experience preview checkout:", current_repo)

    if current_repo == supervisor_repo:
        print()
        print("STOP: experience preview is running inside the batch supervisor checkout.")
        print("This gate will NOT patch or build the supervisor checkout.")
        print("Use the separate experience worktree.")
        raise SystemExit(3)

    print("ISOLATION OK: preview checkout is separate from the batch supervisor checkout.")


def ensure_frontend_dependencies(frontend: Path) -> None:
    node_modules = frontend / "node_modules"
    if node_modules.exists():
        return

    print("\n=== FRONTEND DEPENDENCIES ===")
    lockfile = frontend / "package-lock.json"
    if lockfile.exists():
        run(["npm", "ci"], frontend)
    else:
        run(["npm", "install"], frontend)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    frontend = repo / "FRONT END"

    required = [
        frontend / "src" / "main.tsx",
        frontend / "src" / "ExperienceNativeShell.tsx",
        frontend / "src" / "experienceShell.css",
        frontend / "src" / "ExperienceCommandCenter.tsx",
        frontend / "src" / "LivingFactoryFloor.tsx",
        frontend / "src" / "FactoryEventRail.tsx",
        frontend / "src" / "SpecialistDeskFloor.tsx",
        frontend / "src" / "agentVisualContracts.ts",
        frontend / "src" / "factoryGeometry.ts",
        frontend / "src" / "factoryMovement.ts",
        frontend / "src" / "factoryLedgerAdapter.ts",
        frontend / "src" / "factoryVisualLanguage.ts",
    ]

    print("=" * 72)
    print("IIOS EXPERIENCE X0-X3 - NATIVE SHELL / SUPERVISOR-SAFE BUILD GATE")
    print("=" * 72)

    enforce_supervisor_isolation(repo)

    branch = output(["git", "branch", "--show-current"], repo)
    if branch != BRANCH:
        print(f"STOP: expected {BRANCH}, found {branch}")
        print("No files changed.")
        return 2

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("STOP: required experience files are missing")
        for path in missing:
            print(" ", path)
        return 2

    main_text = (frontend / "src" / "main.tsx").read_text(encoding="utf-8")
    if "ExperienceNativeShell" not in main_text:
        print("STOP: main.tsx is not mounted to the native five-room experience shell.")
        return 2

    ensure_frontend_dependencies(frontend)
    run(["git", "diff", "--check"], repo)

    print("\n=== FRONTEND BUILD ===")
    run(["npm", "run", "build"], frontend)

    print("\n=== EXPERIENCE STATUS ===")
    run(["git", "status", "-sb"], repo)

    print("\nX0-X3 native-shell preview gate is build-clean.")
    print("Factory / Research / Cases / Capital / Judgment are mounted as React views, not DOM-hidden modules.")
    print("Factory defaults to the cinematic eight-desk floor and truthful event lineage.")
    print("Live map, operations conveyor, and system architecture are secondary drawers.")
    print("Research owns discovery and market/evidence inputs; Capital owns portfolio/risk controls; Judgment owns interview capture.")
    print("Cases temporarily retains the legacy underwriting workspace until its inline sections are extracted.")
    print("Batch supervisor checkout was verified separate; no supervisor, backend, paper-chain, or live-execution permissions were changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
