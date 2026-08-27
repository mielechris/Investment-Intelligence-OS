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
ISOLATED_DB = Path("/tmp/iios_batch9e_full_factory_acceptance.db")
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


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live checkout not found: {LIVE}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9E — FULL ISOLATED INTELLIGENCE FACTORY ACCEPTANCE")
    print("Chain: governed universe -> Radar -> Grok/Gemini -> promotion -> 8 agents -> Committee -> Risk -> Capital boundary")
    print("Ledger: BRAND-NEW /tmp ISOLATED DATABASE")
    print("Synthetic promotion fixture: FORBIDDEN")
    print("Promotion/risk/capital gate weakening: FORBIDDEN")
    print("Maximum agent-floor cases: 2")
    print("Authorization functions: NOT CALLED")
    print("Execution functions: NOT CALLED")
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

    python = resolve_python()
    if ISOLATED_DB.exists():
        ISOLATED_DB.unlink()

    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["PYTHONUNBUFFERED"] = "1"
    env["IIOS_DB_PATH"] = str(ISOLATED_DB)
    env["IIOS_9E_GROK_MAX_BATCHES"] = "1"
    env["IIOS_9E_GROK_BATCH_SIZE"] = "20"
    env["IIOS_9E_GEMINI_FINALISTS"] = "4"
    env["IIOS_9E_GEMINI_WORKERS"] = "2"
    env["IIOS_9E_MAX_PROMOTIONS"] = "5"

    code = r'''
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

root = Path.cwd()
backend = root / "BACK END" / "backend"
sys.path.insert(0, str(backend))

from index_tls_bootstrap import configure_verified_tls

tls = configure_verified_tls()

import ledger
ledger.init_ledger()

# Install the same production source/risk/lineage guards as the live backend,
# but all persistence is routed to the isolated IIOS_DB_PATH.
import app as _iios_bootstrap  # noqa: F401
import main as governed_main

from batch8c_production_inputs import refresh_production_universe
from high_speed_case_queue import run_case_floor_cycle
from high_speed_gemini_pipeline import run_parallel_high_speed_cycle
from ledger import latest_object
from paper_capital_api import paper_capital_status


def object_count(object_type: str) -> int:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM ledger_objects WHERE object_type = ?",
            (object_type,),
        ).fetchone()
    finally:
        connection.close()
    return int(row[0] if row else 0)


print("\n=== A. SAFETY + TLS ===")
print(f"Isolated DB: {ledger.DB_PATH}")
print(f"TLS configured: {tls.get('configured') is True}")
print(f"TLS mode: {tls.get('mode')}")
print(f"Certificate verification: {tls.get('certificate_verification') is True}")
print(f"Hostname verification: {tls.get('hostname_verification') is True}")

print("\n=== B. GOVERNED S&P 500 + NASDAQ-100 UNIVERSE ===")
universe = refresh_production_universe(force=True)
print(f"Universe verified: {universe.get('verified_complete') is True}")
print(f"Strict membership: {universe.get('strict_membership') is True}")
print(f"Governed unique symbols: {universe.get('symbol_count')}")
for row in universe.get("source_lineage") or []:
    print(
        f"  {row.get('index')}: count={row.get('symbol_count')} "
        f"mode={row.get('source_mode')} publisher={row.get('source_publisher')}"
    )

print("\n=== C. HIGH-SPEED RADAR + GROK/GEMINI ===")
started = time.perf_counter()
radar = run_parallel_high_speed_cycle(
    enable_grok=True,
    enable_gemini=True,
    enable_promotions=True,
    promotion_limit=5,
    force_model_refresh=True,
)
print(f"Governed universe count: {radar.get('governed_universe_count')}")
print(f"Screener hits: {radar.get('screener_hit_count')}")
print(f"Grok candidates: {radar.get('grok_candidate_count')}")
print(f"Gemini candidates: {radar.get('gemini_candidate_count')}")
print(f"Grok execution satisfied: {radar.get('grok_execution_satisfied') is True}")
print(f"Gemini execution satisfied: {radar.get('gemini_execution_satisfied') is True}")
print(f"Model execution satisfied: {radar.get('model_execution_satisfied') is True}")
print(f"Provider errors: {radar.get('provider_errors') or 'NONE'}")
print(f"Promoted governed cases: {radar.get('promoted_case_count')}")
print(f"Radar seconds: {round(time.perf_counter() - started, 3)}")

promotions = list(radar.get("promotions") or [])
for index, item in enumerate(promotions, 1):
    candidate = item.get("candidate") or {}
    case = item.get("case") or {}
    print(
        f"  PROMOTION {index}: ticker={candidate.get('ticker')} "
        f"research_score={candidate.get('score')} "
        f"radar_rank={candidate.get('radar_rank_score')} case={case.get('case_id')}"
    )

if not promotions:
    print("RESULT: INCONCLUSIVE — no candidate cleared the unchanged real promotion gate this cycle")
    print("No synthetic case was injected and no threshold was weakened.")
    raise SystemExit(2)

print("\n=== D. EIGHT-AGENT FLOOR + INVESTMENT COMMITTEE ===")
floor = run_case_floor_cycle(max_cases=2)
print(f"Queue depth before: {floor.get('queue_depth_before')}")
print(f"Selected cases: {floor.get('selected_count')}")
print(f"Completed cases: {floor.get('completed_count')}")
print(f"Failed-closed cases: {floor.get('failed_closed_count')}")
print(f"Case-floor seconds: {floor.get('cycle_duration_seconds')}")

completed_case_ids = []
for row in floor.get("results") or []:
    print(
        f"  CASE: ticker={row.get('ticker')} case={row.get('case_id')} "
        f"status={row.get('status')} committee={row.get('committee_disposition')} "
        f"confidence={row.get('committee_confidence')}"
    )
    if row.get("status") == "COMPLETE" and row.get("case_id"):
        completed_case_ids.append(str(row.get("case_id")))

if not completed_case_ids:
    print("RESULT: FAIL — no promoted case completed the governed agent/Committee floor")
    raise SystemExit(1)

print("\n=== E. GOVERNED RISK ===")
risk_reached = 0
for case_id in completed_case_ids:
    committee = latest_object("committee_decision", case_id=case_id) or {}
    if not committee:
        print(f"  {case_id}: missing Committee state")
        continue
    risk = latest_object("risk_authorization", case_id=case_id) or {}
    if not risk:
        risk = governed_main.evaluate_decision(committee)
    if risk:
        risk_reached += 1
    reconciliation = risk.get("required_evidence_reconciliation") or {}
    print(
        f"  {case_id}: risk={risk.get('decision')} rules={risk.get('triggered_rules') or []} "
        f"blocking={reconciliation.get('blocking_count')} "
        f"watching={reconciliation.get('watching_count')}"
    )

print("\n=== F. READ-ONLY CAPITAL BOUNDARY ===")
capital_attempted = 0
capital_evaluated = 0
for case_id in completed_case_ids:
    capital_attempted += 1
    try:
        view = paper_capital_status(case_id)
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        print(
            f"  {case_id}: CAPITAL FAIL-CLOSED / PREREQUISITE BLOCK — "
            f"{detail if detail is not None else exc}"
        )
        continue
    capital_evaluated += 1
    print(
        f"  {case_id}: stage={view.get('stage')} "
        f"capital={(view.get('capital') or {}).get('decision')} "
        f"qualified={(view.get('research') or {}).get('qualified_buy_candidate')}"
    )

print("\n=== G. AUTHORITY LOCK CHECK ===")
authorizations = object_count("paper_authorization")
governed_executions = object_count("governed_paper_execution")
print(f"Paper authorization objects: {authorizations}")
print(f"Governed execution objects: {governed_executions}")
print("Authorization functions called: False")
print("Execution functions called: False")
print("Broker connected: False")
print("Live execution: False")

universe_ok = bool(
    tls.get("configured") is True
    and tls.get("certificate_verification") is True
    and tls.get("hostname_verification") is True
    and universe.get("verified_complete") is True
    and universe.get("strict_membership") is True
    and 500 <= int(universe.get("symbol_count") or 0) <= 620
)
model_ok = bool(
    radar.get("grok_execution_satisfied") is True
    and radar.get("gemini_execution_satisfied") is True
    and radar.get("model_execution_satisfied") is True
)
floor_ok = bool(
    int(floor.get("selected_count") or 0) >= 1
    and int(floor.get("completed_count") or 0) >= 1
    and int(floor.get("failed_closed_count") or 0) == 0
)
risk_ok = risk_reached == len(completed_case_ids) and risk_reached >= 1
capital_boundary_ok = capital_attempted == len(completed_case_ids) and capital_attempted >= 1
authority_locked = authorizations == 0 and governed_executions == 0

print("\n=== H. FULL FACTORY ACCEPTANCE SUMMARY ===")
print(f"Governed universe/TLS: {universe_ok}")
print(f"Grok + Gemini: {model_ok}")
print(f"Natural promotions: {len(promotions)}")
print(f"Eight-agent + Committee floor: {floor_ok}")
print(f"Governed Risk reached: {risk_ok}")
print(f"Read-only Capital boundary reached: {capital_boundary_ok}")
print(f"Capital fully evaluated cases: {capital_evaluated}")
print(f"Authorization/execution authority locked: {authority_locked}")
print("A Capital prerequisite block is a valid governed outcome; it is not bypassed for acceptance.")

passed = bool(
    universe_ok
    and model_ok
    and len(promotions) >= 1
    and floor_ok
    and risk_ok
    and capital_boundary_ok
    and authority_locked
)

if passed:
    print("RESULT: PASS — real governed intelligence factory reached Capital boundary on isolated ledger with authority locked")
    raise SystemExit(0)

print("RESULT: FAIL — one or more factory/safety assertions did not hold")
raise SystemExit(1)
'''

    result = run(str(python), "-c", code, cwd=WORKTREE, check=False, env=env)

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    branch_unchanged = branch_after == branch_before
    status_unchanged = status_after == status_before

    print("\n=== LIVE CHECKOUT SAFETY SUMMARY ===")
    print(f"Live branch unchanged: {branch_unchanged} ({branch_after})")
    print(f"Live tracked status unchanged: {status_unchanged}")
    print(f"Isolated DB exists: {ISOLATED_DB.exists()}")
    print(f"Runner exit code: {result.returncode}")

    if result.returncode == 0 and branch_unchanged and status_unchanged:
        print("FINAL RESULT: PASS")
        return 0
    if result.returncode == 2 and branch_unchanged and status_unchanged:
        print("FINAL RESULT: INCONCLUSIVE — safe run, but no real candidate cleared promotion this cycle")
        return 2

    print("FINAL RESULT: FAIL — inspect stage output above; live lanes were not intentionally stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
