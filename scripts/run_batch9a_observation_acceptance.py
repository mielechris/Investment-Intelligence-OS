#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
PREVIEW = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9a-observation")
BRANCH = "feature/batch9a-observation-paper-operations"
LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
DOTENV = LIVE / "BACK END" / "backend" / ".env"
VENV_PYTHON = LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python"


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
        check=check,
    )


def capture(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(list(args), cwd=str(cwd) if cwd else None, text=True).strip()


def load_dotenv(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value, posix=True)
            env[key] = parsed[0] if len(parsed) == 1 else value.strip('"\'')
        except ValueError:
            env[key] = value.strip('"\'')


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live Batch8 checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live IIOS ledger not found: {LEDGER}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9A — ISOLATED OBSERVATION ACCEPTANCE")
    print(f"Live checkout: {LIVE}")
    print(f"Live branch: {branch_before}")
    print(f"Live ledger: {LEDGER}")
    print("Live checkout mutation: FORBIDDEN")
    print("Live execution authority: FALSE")

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)

    if PREVIEW.exists():
        if not (PREVIEW / ".git").exists():
            raise SystemExit(f"Preview path exists but is not a git worktree: {PREVIEW}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=PREVIEW)
        run("git", "clean", "-fd", cwd=PREVIEW)
    else:
        run("git", "worktree", "add", "--detach", str(PREVIEW), f"origin/{BRANCH}", cwd=LIVE)

    python = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["IIOS_DB_PATH"] = str(LEDGER)
    env["PYTHONUNBUFFERED"] = "1"

    print(f"Acceptance checkout: {PREVIEW}")
    print(f"Python: {python}")
    print("Running one forced observation cycle against the live governed ledger...")

    result = subprocess.run(
        [str(python), "scripts/iios_observation_runner.py", "--once", "--force-scan"],
        cwd=str(PREVIEW),
        env=env,
        text=True,
    )

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)

    print("\n=== BATCH 9A ACCEPTANCE ISOLATION ===")
    print(f"Live branch unchanged: {branch_after == branch_before} ({branch_after})")
    print(f"Live tracked status unchanged: {status_after == status_before}")
    print(f"Runner exit code: {result.returncode}")

    if branch_after != branch_before:
        print("RESULT: FAIL — live Batch8 branch changed")
        return 2
    if status_after != status_before:
        print("RESULT: FAIL — live Batch8 tracked status changed")
        return 3
    if result.returncode != 0:
        print("RESULT: FAIL — observation cycle failed")
        return result.returncode or 4

    print("RESULT: PASS — observation cycle completed against live ledger without checkout mutation")
    print("Next: inspect 5175/5189 browser for new scan/case/snapshot state before enabling continuous mode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
