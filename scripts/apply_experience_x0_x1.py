#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BRANCH = "feature/iios-experience-x0-x1"
IMPORT_LINE = 'import ExperienceCommandCenter from "./ExperienceCommandCenter";\n'
ANCHOR_IMPORT = 'import FactoryRoom from "./FactoryRoom";\n'
RENDER_LINE = '      <ExperienceCommandCenter />\n\n'
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
    component_path = frontend / "src" / "ExperienceCommandCenter.tsx"
    blueprint_path = frontend / "src" / "experienceBlueprint.ts"

    print("=" * 72)
    print("IIOS EXPERIENCE X0/X1 - FACTORY BLUEPRINT + COMMAND CENTER")
    print("=" * 72)

    branch = output(["git", "branch", "--show-current"], repo)
    if branch != BRANCH:
        print(f"STOP: expected {BRANCH}, found {branch}")
        return 2

    required = [app_path, component_path, blueprint_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("STOP: required experience files are missing")
        for path in missing:
            print(" ", path)
        return 2

    run(["git", "diff", "--check"], repo)

    app = app_path.read_text(encoding="utf-8")

    if IMPORT_LINE not in app:
        if ANCHOR_IMPORT not in app:
            print("STOP: App import anchor not found")
            return 2
        app = app.replace(ANCHOR_IMPORT, ANCHOR_IMPORT + IMPORT_LINE, 1)

    if RENDER_LINE not in app:
        if RENDER_ANCHOR not in app:
            print("STOP: App render anchor not found")
            return 2
        app = app.replace(RENDER_ANCHOR, RENDER_LINE + RENDER_ANCHOR, 1)

    app_path.write_text(app, encoding="utf-8")

    run(["git", "diff", "--check"], repo)

    print("\n=== FRONTEND BUILD ===")
    run(["npm", "run", "build"], frontend)

    print("\n=== EXPERIENCE DIFF ===")
    run(["git", "diff", "--stat"], repo)
    run(["git", "status", "-sb"], repo)

    print("\nX0/X1 integration is build-clean.")
    print("No backend, paper-chain, or live-execution permissions were changed.")
    print("Review the UI locally before committing App.tsx.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
