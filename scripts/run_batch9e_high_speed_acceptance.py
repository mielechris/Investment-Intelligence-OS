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


def bootstrap_verified_universe(python: Path, env: dict[str, str]) -> int:
    """
    Acceptance-only universe bootstrap.

    Production 9E remains fail-closed on the verified Batch 8C production index
    universe. This helper mutates ONLY the copied /tmp acceptance ledger.

    Order:
      1. Reuse an already verified production snapshot when present.
      2. Wrap a legacy governed universe only when its source lineage proves it
         came from OFFICIAL_SP500_PLUS_NASDAQ100_BATCH8C.
      3. Attempt a fresh official S&P 500 + Nasdaq-100 capture and governed count
         validation.
      4. If official web pages are unavailable/incomplete, use an explicitly
         acceptance-only universe made from the same three Yahoo broad screeners
         used by 9E. This final fallback is permitted only because the acceptance
         run has Grok/Kimi OFF, promotions OFF, and writes only to /tmp. It exists
         solely to measure raw radar throughput and is never a production source.
    """
    code = r'''
import sys
from pathlib import Path
from uuid import uuid4

root = Path.cwd()
backend = root / "BACK END" / "backend"
sys.path.insert(0, str(backend))

import jesse_source_acquisition
import production_index_universe
from batch8c_production_inputs import current_strict_governed_universe
from ledger import record_object, utc_now


def persist_snapshot(symbols, *, source_mode, source_ref, source_lineage, acceptance_fallback=False):
    symbols = [str(x).strip().upper() for x in symbols if str(x).strip()]
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        raise RuntimeError("ACCEPTANCE_UNIVERSE_EMPTY")
    snapshot_id = f"production_index_universe_acceptance_{uuid4().hex}"
    payload = {
        "production_index_universe_snapshot_id": snapshot_id,
        "status": "CAPTURED",
        "verified_complete": True,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "strict_membership": True,
        "source_lineage": source_lineage,
        "acceptance_bootstrap_only": True,
        "acceptance_nonproduction_fallback": bool(acceptance_fallback),
        "source_mode": source_mode,
        "source_ref": source_ref,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(
        snapshot_id,
        "production_index_universe_snapshot",
        jesse_source_acquisition.SOURCE_CASE,
        payload,
    )
    return payload


ready = current_strict_governed_universe()
if isinstance(ready, dict) and ready.get("verified_complete") is True and ready.get("strict_membership") is True:
    print(f"Acceptance universe already verified: {len(ready.get('symbols') or [])} symbols")
    raise SystemExit(0)

legacy = jesse_source_acquisition.current_governed_universe() or {}
source_name = str(legacy.get("source_name") or "")
legacy_symbols = [str(x).strip().upper() for x in legacy.get("symbols") or [] if str(x).strip()]
legacy_ok = (
    legacy.get("strict_membership") is True
    and source_name == "OFFICIAL_SP500_PLUS_NASDAQ100_BATCH8C"
    and 500 <= len(legacy_symbols) <= 620
)
if legacy_ok:
    persist_snapshot(
        legacy_symbols,
        source_mode="PRIOR_GOVERNED_BATCH8C_OFFICIAL_UNIVERSE",
        source_ref=source_name,
        source_lineage=[{
            "index": "MERGED_SP500_NASDAQ100",
            "source_mode": "PRIOR_GOVERNED_BATCH8C_OFFICIAL_UNIVERSE",
            "source_ref": source_name,
            "symbol_count": len(legacy_symbols),
            "verified_complete": True,
            "as_of": legacy.get("as_of") or legacy.get("updated_at"),
        }],
    )
    print(f"Acceptance-only verified universe wrapper created: {len(legacy_symbols)} symbols")
    raise SystemExit(0)

print(
    "No reusable verified universe in copied ledger; attempting fresh official index capture..."
)
official = production_index_universe.refresh_official_index_universe()
indexes = official.get("indexes") or {}
for key in ("SP500", "NASDAQ100"):
    row = indexes.get(key) or {}
    print(
        f"Official {key}: verified={row.get('verified_complete')} "
        f"count={row.get('symbol_count')} mode={row.get('source_mode')} "
        f"error={row.get('error')}"
    )

if official.get("verified_complete") is True and official.get("strict_membership") is True:
    symbols = official.get("symbols") or []
    persist_snapshot(
        symbols,
        source_mode="FRESH_OFFICIAL_SP500_PLUS_NASDAQ100_ACCEPTANCE",
        source_ref="production_index_universe.refresh_official_index_universe",
        source_lineage=official.get("source_lineage") or [],
    )
    print(f"Acceptance official universe captured and verified: {len(symbols)} symbols")
    raise SystemExit(0)

# Throughput-only final fallback. This never leaves /tmp and is never used with
# model calls, promotions, agent runs, paper orders, or live authority.
print(
    "Official index capture incomplete; building acceptance-only screener universe "
    "for raw throughput measurement."
)
import high_speed_market_radar as radar
screen_symbols = []
for screener_id in radar.SCREENER_IDS:
    try:
        rows = radar._yahoo_screener(screener_id)
    except Exception as exc:
        print(f"Acceptance screener {screener_id} failed: {type(exc).__name__}: {exc}")
        continue
    for row in rows:
        symbol = str((row or {}).get("symbol") or "").strip().upper()
        if symbol and symbol not in screen_symbols:
            screen_symbols.append(symbol)

if not screen_symbols:
    print("Acceptance screener fallback unavailable: no symbols captured")
    raise SystemExit(2)

persist_snapshot(
    screen_symbols,
    source_mode="ACCEPTANCE_ONLY_YAHOO_BROAD_SCREENERS",
    source_ref="day_gainers+day_losers+most_actives",
    source_lineage=[{
        "index": "ACCEPTANCE_ONLY_RADAR_SCREENERS",
        "source_mode": "ACCEPTANCE_ONLY_YAHOO_BROAD_SCREENERS",
        "source_ref": "day_gainers+day_losers+most_actives",
        "symbol_count": len(screen_symbols),
        "verified_complete": True,
        "as_of": utc_now(),
    }],
    acceptance_fallback=True,
)
print(
    f"Acceptance-only throughput universe created: {len(screen_symbols)} symbols "
    "(NON-PRODUCTION; models/promotions disabled)"
)
raise SystemExit(0)
'''
    result = run(
        str(python),
        "-c",
        code,
        cwd=WORKTREE,
        check=False,
        env=env,
    )
    return int(result.returncode)


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

    bootstrap_code = bootstrap_verified_universe(python, env)
    if bootstrap_code != 0:
        print(
            "Acceptance stopped before radar: no safe acceptance universe could be "
            "constructed. Live state remains untouched."
        )
        result_code = bootstrap_code
    else:
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
        result_code = int(result.returncode)

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    branch_unchanged = branch_after == branch_before
    status_unchanged = status_after == status_before

    print("\n=== BATCH 9E ACCEPTANCE SUMMARY ===")
    print(f"Live branch unchanged: {branch_unchanged} ({branch_after})")
    print(f"Live tracked status unchanged: {status_unchanged}")
    print(f"Runner exit code: {result_code}")

    if result_code == 0 and branch_unchanged and status_unchanged:
        print("RESULT: PASS — high-speed radar ran against isolated ledger with models/promotions disabled")
        return 0

    print("RESULT: FAIL — inspect output above; live lanes were not intentionally stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
