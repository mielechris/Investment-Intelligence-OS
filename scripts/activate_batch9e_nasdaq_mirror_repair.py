#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
BRANCH = "feature/batch9e-high-speed-market-radar"
LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
PYTHON_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python3",
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python3"),
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, capture: bool = False):
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{detail[:3000]}")
    return result


def output(args: list[str], *, cwd: Path | None = None) -> str:
    return run(args, cwd=cwd, capture=True).stdout.strip()


def resolve_python() -> Path:
    for candidate in PYTHON_CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend virtualenv Python found")


def nine_e_pids() -> list[str]:
    result = run(["pgrep", "-af", "iios_high_speed_factory_runner.py"], check=False, capture=True)
    return [row for row in result.stdout.splitlines() if row.strip()]


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("This activation is macOS-only")
    if not LIVE.exists():
        raise SystemExit(f"Live checkout missing: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Governed live ledger missing: {LEDGER}")

    git = shutil.which("git")
    if not git:
        raise SystemExit("git not found")

    live_branch_before = output([git, "branch", "--show-current"], cwd=LIVE)
    live_status_before = output([git, "status", "--porcelain"], cwd=LIVE)

    run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    remote = f"origin/{BRANCH}"

    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"9E path exists but is not a git worktree: {WORKTREE}")
        status = output([git, "status", "--porcelain"], cwd=WORKTREE)
        if status:
            raise SystemExit(
                "9E worktree has local changes; refusing repair so nothing is overwritten:\n"
                + status[:3000]
            )
        run([git, "reset", "--hard", remote], cwd=WORKTREE)
    else:
        run([git, "worktree", "add", "--detach", str(WORKTREE), remote], cwd=LIVE)

    source = WORKTREE / "BACK END" / "backend" / "production_index_universe_resilient.py"
    text = source.read_text(encoding="utf-8")
    required = (
        "NASDAQ100_IQQ_MIRROR_URL",
        "ishares-nasdaq-100-etf/latest-holdings.csv",
        "GOVERNED_INDEX_TRACKER_MIRROR",
        "Nasdaq 100 Index",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit(f"Repaired 9E source missing markers: {missing}")

    python = resolve_python()
    backend = WORKTREE / "BACK END" / "backend"
    canary = r'''
import json
from index_tls_bootstrap import configure_verified_tls
status = configure_verified_tls()
import production_index_universe
payload = production_index_universe.refresh_official_index_universe()
print(json.dumps({
    "tls": status,
    "status": payload.get("status"),
    "verified_complete": payload.get("verified_complete"),
    "symbol_count": payload.get("symbol_count"),
    "sp500": (payload.get("indexes") or {}).get("SP500"),
    "nasdaq100": (payload.get("indexes") or {}).get("NASDAQ100"),
    "live_execution": payload.get("live_execution"),
}, default=str))
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(backend)
    result = subprocess.run(
        [str(python), "-c", canary],
        cwd=str(backend),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("REAL_SOURCE_CANARY_FAILED:\n" + (result.stderr or result.stdout)[-4000:])

    try:
        canary_payload = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise SystemExit(f"Could not decode canary result: {exc}\n{result.stdout[-3000:]}") from exc

    n = canary_payload.get("nasdaq100") or {}
    s = canary_payload.get("sp500") or {}
    universe_ok = (
        canary_payload.get("verified_complete") is True
        and 490 <= int(s.get("symbol_count") or 0) <= 520
        and 95 <= int(n.get("symbol_count") or 0) <= 110
    )
    if not universe_ok:
        raise SystemExit("REAL_SOURCE_CANARY_NOT_VERIFIED:\n" + json.dumps(canary_payload, indent=2, default=str))

    if output([git, "branch", "--show-current"], cwd=LIVE) != live_branch_before:
        raise SystemExit("Live checkout branch changed during repair")
    if output([git, "status", "--porcelain"], cwd=LIVE) != live_status_before:
        raise SystemExit("Live checkout tracked status changed during repair")

    running = nine_e_pids()
    print(json.dumps({
        "status": "BATCH9E_NASDAQ100_MIRROR_REPAIR_INSTALLED",
        "live_branch_preserved": live_branch_before,
        "live_ledger_preserved": str(LEDGER),
        "tls_mode": (canary_payload.get("tls") or {}).get("mode"),
        "certificate_verification": (canary_payload.get("tls") or {}).get("certificate_verification"),
        "universe_status": canary_payload.get("status"),
        "strict_universe_verified": canary_payload.get("verified_complete"),
        "combined_symbol_count": canary_payload.get("symbol_count"),
        "sp500_symbol_count": s.get("symbol_count"),
        "sp500_source_mode": s.get("source_mode"),
        "nasdaq100_symbol_count": n.get("symbol_count"),
        "nasdaq100_source_mode": n.get("source_mode"),
        "nasdaq100_source_publisher": n.get("source_publisher"),
        "nasdaq100_benchmark": n.get("benchmark"),
        "nine_e_process_running": bool(running),
        "nine_e_processes": running[:3],
        "restart_performed": False,
        "broker_connected": False,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "next_action": "CONTROLLED_9E_RESTART_REQUIRED" if running else "START_9E_WITH_REPAIRED_SOURCE",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
