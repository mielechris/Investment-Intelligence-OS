#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BRANCH = "feature/iios-experience-x0-x1"
EXPERIENCE_IMPORT = 'import ExperienceCommandCenter from "./ExperienceCommandCenter";\n'
FLOOR_IMPORT = 'import LivingFactoryFloor from "./LivingFactoryFloor";\n'
EVENT_RAIL_IMPORT = 'import FactoryEventRail from "./FactoryEventRail";\n'
DESK_FLOOR_IMPORT = 'import SpecialistDeskFloor from "./SpecialistDeskFloor";\n'
ANCHOR_IMPORT = 'import FactoryRoom from "./FactoryRoom";\n'
EXPERIENCE_RENDER = '      <ExperienceCommandCenter />\n\n'
FLOOR_RENDER = '      <LivingFactoryFloor />\n\n'
EVENT_RAIL_RENDER = '      <FactoryEventRail />\n\n'
DESK_FLOOR_RENDER = '      <SpecialistDeskFloor />\n\n'
RENDER_ANCHOR = '      <section style={{ ...panel, marginBottom: "22px", borderColor: "#365575" }}>\n'


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    frontend = repo / "FRONT END"
    app_path = frontend / "src" / "App.tsx"

    required = [
        app_path,
        frontend / "src" / "ExperienceCommandCenter.tsx",
        frontend / "src" / "experienceBlueprint.ts",
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
    print("IIOS EXPERIENCE X0-X3 - SAFE PREVIEW / BUILD GATE")
    print("=" * 72)

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

    run(["git", "diff", "--check"], repo)

    app = app_path.read_text(encoding="utf-8")

    if EXPERIENCE_IMPORT not in app:
        if ANCHOR_IMPORT not in app:
            print("STOP: App import anchor not found")
            return 2
        app = app.replace(ANCHOR_IMPORT, ANCHOR_IMPORT + EXPERIENCE_IMPORT, 1)

    if FLOOR_IMPORT not in app:
        app = app.replace(EXPERIENCE_IMPORT, EXPERIENCE_IMPORT + FLOOR_IMPORT, 1)

    if EVENT_RAIL_IMPORT not in app:
        app = app.replace(FLOOR_IMPORT, FLOOR_IMPORT + EVENT_RAIL_IMPORT, 1)

    if DESK_FLOOR_IMPORT not in app:
        app = app.replace(EVENT_RAIL_IMPORT, EVENT_RAIL_IMPORT + DESK_FLOOR_IMPORT, 1)

    ordered_renders = [EXPERIENCE_RENDER, FLOOR_RENDER, DESK_FLOOR_RENDER, EVENT_RAIL_RENDER]
    if not any(render in app for render in ordered_renders):
        if RENDER_ANCHOR not in app:
            print("STOP: App render anchor not found")
            return 2
        app = app.replace(RENDER_ANCHOR, "".join(ordered_renders) + RENDER_ANCHOR, 1)
    else:
        for render in ordered_renders:
            if render not in app:
                existing_anchor = next((candidate for candidate in reversed(ordered_renders) if candidate in app), None)
                if existing_anchor:
                    app = app.replace(existing_anchor, existing_anchor + render, 1)
                elif RENDER_ANCHOR in app:
                    app = app.replace(RENDER_ANCHOR, render + RENDER_ANCHOR, 1)

    app_path.write_text(app, encoding="utf-8")

    run(["git", "diff", "--check"], repo)

    print("\n=== FRONTEND BUILD ===")
    run(["npm", "run", "build"], frontend)

    print("\n=== EXPERIENCE DIFF ===")
    run(["git", "diff", "--stat"], repo)
    run(["git", "status", "-sb"], repo)

    print("\nX0-X3 preview gate is build-clean.")
    print("Living Factory Floor reads /factory-room/status active_room derived from audit events.")
    print("Factory Event Rail exposes strict raw-ledger -> canonical-X2 translation.")
    print("Eight Specialist Desks read only /agents plus recent audit activity.")
    print("MAX reacts only to real desk telemetry; no synthetic activity is generated.")
    print("Unknown active_room values remain UNPLACED; unknown event types remain IGNORED.")
    print("No backend, Batch 8D, paper-chain, or live-execution permissions were changed.")
    print("Review the UI locally before committing App.tsx.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
