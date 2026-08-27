#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import sqlite3
import subprocess
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
BRANCH = "feature/batch9e-high-speed-market-radar"
LIVE_LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
TEST_LEDGER = Path("/tmp/iios_batch9e_acceptance.db")
DOTENV = LIVE / "BACK END" / "backend" / ".env"

VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def run(*args: str, cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None):
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
        check=check,
        env=env,
    )


def capture(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(list(args), cwd=str(cwd) if cwd else None, text=True).strip()


def resolve_python() -> Path:
    for candidate in VENV_CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend virtualenv Python found; refusing system Python fallback")


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
            env[key] = parsed[0] if len(parsed) == 1 else value.strip("\"'")
        except ValueError:
            env[key] = value.strip("\"'")


def sqlite_backup(source: Path, destination: Path) -> None:
    if destination.exists():
        destination.unlink()
    source_db = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    destination_db = sqlite3.connect(destination, timeout=30)
    try:
        source_db.backup(destination_db)
    finally:
        destination_db.close()
        source_db.close()


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live checkout not found: {LIVE}")
    if not LIVE_LEDGER.exists():
        raise SystemExit(f"Live governed ledger not found: {LIVE_LEDGER}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9E — ISOLATED HIGH-SPEED RADAR ACCEPTANCE")
    print(f"Live branch: {branch_before}")
    print("Live Batch8 working tree: MUST REMAIN UNCHANGED")
    print("Live ledger mutation: FORBIDDEN — acceptance uses SQLite backup")
    print("Grok/Kimi provider calls: DISABLED for first acceptance")
    print("Case promotions: DISABLED")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)
    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"9E path exists but is not a git worktree: {WORKTREE}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=WORKTREE)
        run("git", "clean", "-fd", cwd=WORKTREE)
    else:
        run("git", "worktree", "add", "--detach", str(WORKTREE), f"origin/{BRANCH}", cwd=LIVE)

    sqlite_backup(LIVE_LEDGER, TEST_LEDGER)
    print(f"Acceptance ledger backup: {TEST_LEDGER}")

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["IIOS_DB_PATH"] = str(TEST_LEDGER)
    env["PYTHONUNBUFFERED"] = "1"
    env["IIOS_9E_KIMI_FINALISTS"] = "8"
    env["IIOS_9E_KIMI_WORKERS"] = "4"

    runner = WORKTREE / "scripts" / "iios_high_speed_factory_runner.py"
    result = run(
        str(python),
        str(runner),
        "--once",
        "--dry-run",
        "--no-models",
        cwd=WORKTREE,
        check=False,
        env=env,
    )

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    branch_unchanged = branch_after == branch_before
    status_unchanged = status_after == status_before

    print("\n=== BATCH 9E ACCEPTANCE SUMMARY ===")
    print(f"Live branch unchanged: {branch_unchanged} ({branch_after})")
    print(f"Live tracked status unchanged: {status_unchanged}")
    print(f"Runner exit code: {result.returncode}")

    if result.returncode == 0 and branch_unchanged and status_unchanged:
        print("RESULT: PASS — high-speed governed-universe radar ran against isolated ledger with models/promotions disabled")
        return 0

    print("RESULT: FAIL — inspect output above; live lanes were not intentionally stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
