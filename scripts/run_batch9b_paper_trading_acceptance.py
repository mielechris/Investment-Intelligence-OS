#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9b-paper-trading")
BRANCH = "feature/batch9b-governed-paper-trading"
LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
DOTENV = LIVE / "BACK END" / "backend" / ".env"
VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


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


def resolve_python() -> Path:
    for candidate in VENV_CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend virtualenv Python found; refusing system Python fallback")


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live Batch8 checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live IIOS ledger not found: {LEDGER}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9B — ISOLATED PAPER-TRADING ACCEPTANCE")
    print(f"Live checkout: {LIVE}")
    print(f"Live branch: {branch_before}")
    print(f"Live ledger: {LEDGER}")
    print("Acceptance mode: DRY RUN + NO DEEPENING")
    print("Paper execution: DISABLED")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")
    print("Live checkout mutation: FORBIDDEN")

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)

    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"9B path exists but is not a git worktree: {WORKTREE}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=WORKTREE)
        run("git", "clean", "-fd", cwd=WORKTREE)
    else:
        run("git", "worktree", "add", "--detach", str(WORKTREE), f"origin/{BRANCH}", cwd=LIVE)

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["IIOS_DB_PATH"] = str(LEDGER)
    env["PYTHONUNBUFFERED"] = "1"

    print(f"Acceptance worktree: {WORKTREE}")
    print(f"Python: {python}")
    print("Running one read/decision-path acceptance cycle...")

    result = subprocess.run(
        [
            str(python),
            "scripts/iios_paper_trading_runner.py",
            "--once",
            "--dry-run",
            "--no-deepen",
        ],
        cwd=str(WORKTREE),
        env=env,
        text=True,
    )

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)

    print("\n=== BATCH 9B ACCEPTANCE ISOLATION ===")
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
        print("RESULT: FAIL — 9B dry-run acceptance failed")
        return result.returncode or 4

    print("RESULT: PASS — 9B decision path inspected live ledger with paper execution disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
