#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
RUNNER_WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9a-observation")
BRANCH = "feature/batch9a-observation-paper-operations"
LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
DOTENV = LIVE / "BACK END" / "backend" / ".env"
VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
        check=True,
    )


def capture(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
    ).strip()


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
    raise SystemExit(
        "No IIOS backend virtualenv Python found. Refusing to use system Python."
    )


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live Batch8 checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live IIOS ledger not found: {LEDGER}")

    live_branch = capture("git", "branch", "--show-current", cwd=LIVE)
    live_status = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9A — CONTINUOUS OBSERVATION MODE", flush=True)
    print(f"Live checkout: {LIVE}", flush=True)
    print(f"Live branch: {live_branch}", flush=True)
    print(f"Live tracked status: {'clean' if not live_status else 'unchanged / not touched'}", flush=True)
    print(f"Governed ledger: {LEDGER}", flush=True)
    print("Cycle cadence: 15 minutes", flush=True)
    print("Discovery cadence: 30 min regular session / 120 min off-hours", flush=True)
    print("Authority: PAPER/SHADOW ONLY", flush=True)
    print("Broker connected: FALSE", flush=True)
    print("Live execution: FALSE", flush=True)
    print("Live Batch8 working tree mutation: FORBIDDEN", flush=True)

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)

    if RUNNER_WORKTREE.exists():
        if not (RUNNER_WORKTREE / ".git").exists():
            raise SystemExit(
                f"Observation path exists but is not a git worktree: {RUNNER_WORKTREE}"
            )
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=RUNNER_WORKTREE)
        run("git", "clean", "-fd", cwd=RUNNER_WORKTREE)
    else:
        run(
            "git",
            "worktree",
            "add",
            "--detach",
            str(RUNNER_WORKTREE),
            f"origin/{BRANCH}",
            cwd=LIVE,
        )

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["IIOS_DB_PATH"] = str(LEDGER)
    env["PYTHONUNBUFFERED"] = "1"

    print(f"Runner checkout: {RUNNER_WORKTREE}", flush=True)
    print(f"Python: {python}", flush=True)
    print("Starting Observation Mode now. Use Ctrl+C in THIS terminal only to stop it.", flush=True)

    completed = subprocess.run(
        [
            str(python),
            "scripts/iios_observation_runner.py",
            "--force-scan",
            "--interval-minutes",
            "15",
        ],
        cwd=str(RUNNER_WORKTREE),
        env=env,
        text=True,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
