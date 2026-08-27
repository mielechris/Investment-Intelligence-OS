#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
BRANCH = "feature/batch9e-high-speed-market-radar"
DOTENV = LIVE / "BACK END" / "backend" / ".env"
LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def run(*args: str, cwd: Path | None = None, check: bool = True, env=None):
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
        check=check,
        env=env,
    )


def capture(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args), cwd=str(cwd) if cwd else None, text=True
    ).strip()


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
        key, value = key.strip(), value.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value, posix=True)
            env[key] = parsed[0] if len(parsed) == 1 else value.strip("\"'")
        except ValueError:
            env[key] = value.strip("\"'")


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live Batch8 checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live governed ledger not found: {LEDGER}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9E — LIVE-LEDGER PAPER INTELLIGENCE FACTORY")
    print(f"Live checkout: {LIVE}")
    print(f"Live branch: {branch_before}")
    print(f"Governed ledger: {LEDGER}")
    print("Ledger mutation: ENABLED for 9E radar/model/case telemetry")
    print("9A / 9B existing processes: UNTOUCHED")
    print("Grok: critical-path real-time context")
    print("Gemini: bounded enrichment; provider degradation cannot freeze case flow")
    print("Gemini preferred: gemini-3.7-flash")
    print("Gemini rapid fallback: gemini-3.6-flash")
    print("Gemini request timeout: 30 seconds; retries: 0")
    print("Radar cadence: 5 minutes")
    print("Case-floor cadence: 30 seconds")
    print("Current case-floor production cap: 2 concurrent governed cases")
    print("Paper portfolio authority: EXISTING 9B GOVERNED CHAIN ONLY")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)

    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"9E path exists but is not a git worktree: {WORKTREE}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=WORKTREE)
        run("git", "clean", "-fd", cwd=WORKTREE)
    else:
        run(
            "git",
            "worktree",
            "add",
            "--detach",
            str(WORKTREE),
            f"origin/{BRANCH}",
            cwd=LIVE,
        )

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit("Refusing 9E launch: live Batch8 branch or tracked working tree changed")

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "IIOS_DB_PATH": str(LEDGER),
            "IIOS_GEMINI_TIMEOUT_SECONDS": "30",
            "IIOS_GEMINI_RETRIES": "0",
            "IIOS_9E_GEMINI_FALLBACK_MODEL": "gemini-3.6-flash",
            "IIOS_9E_GEMINI_FINALISTS": "4",
            "IIOS_9E_GEMINI_WORKERS": "2",
            "IIOS_9E_GROK_MAX_BATCHES": "1",
            "IIOS_9E_GROK_BATCH_SIZE": "20",
            "IIOS_9E_MAX_PROMOTIONS": "5",
        }
    )

    script = WORKTREE / "scripts" / "iios_high_speed_factory_runner.py"
    if not script.exists():
        raise SystemExit(f"9E factory runner missing: {script}")

    print("\nStarting continuous 9E. Use Ctrl+C in THIS terminal only to stop 9E.")
    print("Family Network may remain open on 127.0.0.1:5191.")

    result = run(
        str(python),
        str(script),
        "--radar-minutes",
        "5",
        "--case-floor-seconds",
        "30",
        "--deep-seconds",
        "60",
        cwd=WORKTREE,
        check=False,
        env=env,
    )

    branch_final = capture("git", "branch", "--show-current", cwd=LIVE)
    status_final = capture("git", "status", "--porcelain", cwd=LIVE)
    print("\nBatch 9E process ended.")
    print(f"Live branch unchanged: {branch_final == branch_before} ({branch_final})")
    print(f"Live tracked status unchanged: {status_final == status_before}")
    print(f"Runner exit code: {result.returncode}")
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
