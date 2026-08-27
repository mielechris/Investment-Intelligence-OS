#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import sqlite3
import subprocess
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
BRANCH = "feature/batch9e-high-speed-market-radar"
SOURCE_LEDGER = Path("/tmp/iios_batch9e_acceptance.db")
MODEL_LEDGER = Path("/tmp/iios_batch9e_model_acceptance.db")
DOTENV = LIVE / "BACK END" / "backend" / ".env"

VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def run(*args: str, cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None):
    return subprocess.run(list(args), cwd=str(cwd) if cwd else None, text=True, check=check, env=env)


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


def latest_object(db_path: Path, object_type: str) -> dict:
    db = sqlite3.connect(db_path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT 1",
            (object_type,),
        ).fetchone()
    finally:
        db.close()
    return json.loads(row["payload_json"]) if row else {}


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live checkout not found: {LIVE}")
    if not SOURCE_LEDGER.exists():
        raise SystemExit(
            "First 9E raw-radar acceptance ledger is missing. Run run_batch9e_high_speed_acceptance.py first."
        )

    universe = latest_object(SOURCE_LEDGER, "production_index_universe_snapshot")
    if not (
        universe.get("verified_complete") is True
        and universe.get("strict_membership") is True
        and int(universe.get("symbol_count") or 0) > 0
    ):
        raise SystemExit("Acceptance source ledger does not contain a usable isolated universe")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9E — ISOLATED GROK + KIMI MODEL ACCEPTANCE")
    print(f"Source acceptance universe: {universe.get('symbol_count')} symbols")
    print(f"Universe source mode: {universe.get('source_mode') or 'PERSISTED_ACCEPTANCE_SNAPSHOT'}")
    print("Live ledger mutation: FORBIDDEN")
    print("Case promotions: DISABLED")
    print("8-agent case floor: DISABLED")
    print("Paper order authority: FALSE")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")
    print("Grok: X SEARCH + WEB SEARCH ENABLED when configured")
    print("Kimi: K3/available model + Formula Web Search + HIGH reasoning when configured")

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)
    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"9E path exists but is not a git worktree: {WORKTREE}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=WORKTREE)
        run("git", "clean", "-fd", cwd=WORKTREE)
    else:
        run("git", "worktree", "add", "--detach", str(WORKTREE), f"origin/{BRANCH}", cwd=LIVE)

    sqlite_backup(SOURCE_LEDGER, MODEL_LEDGER)
    print(f"Model acceptance ledger: {MODEL_LEDGER}")

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["IIOS_DB_PATH"] = str(MODEL_LEDGER)
    env["PYTHONUNBUFFERED"] = "1"

    # Full provider capabilities, deliberately bounded breadth for acceptance latency/cost.
    env["IIOS_9E_GROK_MAX_BATCHES"] = "1"
    env["IIOS_9E_GROK_BATCH_SIZE"] = "20"
    env["IIOS_9E_KIMI_FINALISTS"] = "4"
    env["IIOS_9E_KIMI_WORKERS"] = "2"

    # Make direct official/provider HTTPS calls use the same CA bundle as the production app.
    cert = capture(str(python), "-c", "import certifi; print(certifi.where())")
    if cert:
        env["SSL_CERT_FILE"] = cert

    runner = WORKTREE / "scripts" / "iios_high_speed_factory_runner.py"
    result = run(
        str(python),
        str(runner),
        "--once",
        "--dry-run",
        cwd=WORKTREE,
        check=False,
        env=env,
    )

    cycle = latest_object(MODEL_LEDGER, "high_speed_market_radar_cycle")
    provider_errors = cycle.get("provider_errors") or {}

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    branch_unchanged = branch_after == branch_before
    status_unchanged = status_after == status_before

    print("\n=== BATCH 9E MODEL ACCEPTANCE SUMMARY ===")
    print(f"Grok candidates: {cycle.get('grok_candidate_count')}")
    print(f"Kimi candidates: {cycle.get('kimi_candidate_count')}")
    print(f"Deep research seconds: {cycle.get('deep_research_duration_seconds')}")
    print(f"Total cycle seconds: {cycle.get('cycle_duration_seconds')}")
    print(f"Provider errors: {provider_errors or 'NONE'}")
    print(f"Promoted cases: {cycle.get('promoted_case_count')}")
    print(f"Live branch unchanged: {branch_unchanged} ({branch_after})")
    print(f"Live tracked status unchanged: {status_unchanged}")
    print(f"Runner exit code: {result.returncode}")

    if result.returncode == 0 and branch_unchanged and status_unchanged:
        print("RESULT: PASS — Grok/Kimi model-enabled 9E cycle completed on isolated ledger; promotions remained disabled")
        return 0

    print("RESULT: FAIL — inspect model/provider output above; live lanes were not intentionally stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
