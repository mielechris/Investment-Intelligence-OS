#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
PREVIEW = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9a-observation")
BRANCH = "feature/batch9a-observation-paper-operations"
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
    raise SystemExit(
        "No IIOS backend virtualenv Python found. Refusing to fall back to system Python because provider dependencies must match the live backend."
    )


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live Batch8 checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live IIOS ledger not found: {LEDGER}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9A — ISOLATED FAST ACCEPTANCE", flush=True)
    print(f"Live checkout: {LIVE}", flush=True)
    print(f"Live branch: {branch_before}", flush=True)
    print(f"Live ledger: {LEDGER}", flush=True)
    print("Live checkout mutation: FORBIDDEN", flush=True)
    print("Live execution authority: FALSE", flush=True)

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)

    if PREVIEW.exists():
        if not (PREVIEW / ".git").exists():
            raise SystemExit(f"Preview path exists but is not a git worktree: {PREVIEW}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=PREVIEW)
        run("git", "clean", "-fd", cwd=PREVIEW)
    else:
        run("git", "worktree", "add", "--detach", str(PREVIEW), f"origin/{BRANCH}", cwd=LIVE)

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["IIOS_DB_PATH"] = str(LEDGER)
    env["PYTHONUNBUFFERED"] = "1"

    print(f"Acceptance checkout: {PREVIEW}", flush=True)
    print(f"Python: {python}", flush=True)
    print("Running fast three-symbol live-data acceptance against the governed ledger...", flush=True)

    result = subprocess.run(
        [str(python), "scripts/iios_observation_acceptance_cycle.py"],
        cwd=str(PREVIEW),
        env=env,
        text=True,
    )

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)

    print("\n=== BATCH 9A ACCEPTANCE ISOLATION ===", flush=True)
    print(f"Live branch unchanged: {branch_after == branch_before} ({branch_after})", flush=True)
    print(f"Live tracked status unchanged: {status_after == status_before}", flush=True)
    print(f"Runner exit code: {result.returncode}", flush=True)

    if branch_after != branch_before:
        print("RESULT: FAIL — live Batch8 branch changed", flush=True)
        return 2
    if status_after != status_before:
        print("RESULT: FAIL — live Batch8 tracked status changed", flush=True)
        return 3
    if result.returncode != 0:
        print("RESULT: FAIL — fast observation acceptance failed", flush=True)
        return result.returncode or 4

    print("RESULT: PASS — fast live-data acceptance completed against the live ledger without checkout mutation", flush=True)
    print("Next: inspect the browser, then enable the full progress-visible continuous runner.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
