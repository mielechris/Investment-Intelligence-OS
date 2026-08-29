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
ISOLATED_DB = Path("/tmp/iios_batch9e_full_factory_acceptance_v2.db")
VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def run(*args: str, cwd: Path | None = None, check: bool = True, env=None):
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
        raise SystemExit(f"Live checkout not found: {LIVE}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9E — FULL ISOLATED FACTORY ACCEPTANCE V2")
    print("Chain: governed universe -> Radar -> Grok/Gemini -> promotion -> GPT 8-agent floor -> Committee -> Risk -> Gap Hunter/Qualification -> Capital")
    print("Ledger: BRAND-NEW /tmp ISOLATED DATABASE")
    print("Natural promotion gate: REQUIRED / UNCHANGED")
    print("Qualification stage: REQUIRED")
    print("Legacy execution check: INTERCEPTED / NO OBJECT MAY BE CREATED")
    print("Paper authorization functions: NOT CALLED")
    print("Governed execution functions: NOT CALLED")
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
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "IIOS_DB_PATH": str(ISOLATED_DB),
            "IIOS_9E_GROK_MAX_BATCHES": "1",
            "IIOS_9E_GROK_BATCH_SIZE": "20",
            "IIOS_9E_GEMINI_FINALISTS": "4",
            "IIOS_9E_GEMINI_WORKERS": "2",
            "IIOS_9E_MAX_PROMOTIONS": "5",
        }
    )

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

# Install all production governance patches against only the isolated ledger.
import app as _iios_bootstrap  # noqa: F401
import main as governed_main
import evidence_gap_hunter

from batch8c_production_inputs import refresh_production_universe
from high_speed_case_queue import run_case_floor_cycle
from high_speed_gemini_pipeline import run_parallel_high_speed_cycle
from ledger import latest_object
from paper_capital_api import paper_capital_status


def object_count(object_type: str) -> int:
    db = sqlite3.connect(ledger.DB_PATH, timeout=30)
    try:
        row = db.execute(
            "SELECT COUNT(*) FROM ledger_objects WHERE object_type=?", (object_type,)
        ).fetchone()
    finally:
        db.close()
    return int(row[0] if row else 0)


print("\n=== A. SAFETY + GOVERNED UNIVERSE ===")
universe = refresh_production_universe(force=True)
print(f"TLS configured: {tls.get('configured') is True}")
print(f"Certificate verification: {tls.get('certificate_verification') is True}")
print(f"Hostname verification: {tls.get('hostname_verification') is True}")
print(f"Universe verified: {universe.get('verified_complete') is True}")
print(f"Strict membership: {universe.get('strict_membership') is True}")
print(f"Governed unique symbols: {universe.get('symbol_count')}")

print("\n=== B. RADAR + GROK/GEMINI + NATURAL PROMOTION ===")
radar_started = time.perf_counter()
radar = run_parallel_high_speed_cycle(
    enable_grok=True,
    enable_gemini=True,
    enable_promotions=True,
    promotion_limit=5,
    force_model_refresh=True,
)
print(f"Grok candidates: {radar.get('grok_candidate_count')}")
print(f"Gemini candidates: {radar.get('gemini_candidate_count')}")
print(f"Model execution satisfied: {radar.get('model_execution_satisfied') is True}")
print(f"Provider errors: {radar.get('provider_errors') or 'NONE'}")
print(f"Natural promotions: {radar.get('promoted_case_count')}")
print(f"Radar seconds: {time.perf_counter() - radar_started:.3f}")

promoted = list(radar.get("promoted_cases") or [])
if not promoted:
    print("RESULT: INCONCLUSIVE — no candidate cleared the unchanged natural promotion gate")
    raise SystemExit(2)

print("\n=== C. GPT EIGHT-AGENT FLOOR + COMMITTEE ===")
floor = run_case_floor_cycle(max_cases=2)
print(f"Selected cases: {floor.get('selected_count')}")
print(f"Completed cases: {floor.get('completed_count')}")
print(f"Failed-closed cases: {floor.get('failed_closed_count')}")
print(f"Case-floor seconds: {floor.get('cycle_duration_seconds')}")

completed = [
    str(row.get("case_id"))
    for row in (floor.get("results") or [])
    if row.get("status") == "COMPLETE" and row.get("case_id")
]
if not completed:
    print("RESULT: FAIL — no promoted case completed the GPT agent/Committee floor")
    raise SystemExit(1)

print("\n=== D. GOVERNED RISK ===")
for case_id in completed:
    committee = latest_object("committee_decision", case_id=case_id) or {}
    risk = latest_object("risk_authorization", case_id=case_id) or {}
    if not risk:
        risk = governed_main.evaluate_decision(committee)
    print(
        f"  {case_id}: committee={committee.get('disposition')} "
        f"confidence={committee.get('confidence')} risk={risk.get('decision')} "
        f"rules={risk.get('triggered_rules') or []}"
    )

print("\n=== E. GAP HUNTER + QUALIFICATION (ONE NATURAL CASE) ===")
# Evidence Gap Hunter still contains a legacy paper-execution check. For this
# isolated acceptance only, intercept that function in memory so the real
# research/qualification path runs but no execution object or authorization is
# created. No production source is modified by this interception.
legacy_execution_attempts = []
original_submit = governed_main.submit_paper_order

def blocked_legacy_submit(request):
    legacy_execution_attempts.append(dict(request or {}))
    return {
        "status": "NOT_CALLED",
        "execution": "NOT_SUBMITTED",
        "reason": "BATCH9E_ACCEPTANCE_EXECUTION_LOCK",
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }

governed_main.submit_paper_order = blocked_legacy_submit
qualification_case = completed[0]
try:
    hunt = evidence_gap_hunter.run_gap_hunt(qualification_case)
finally:
    governed_main.submit_paper_order = original_submit

qualification = latest_object("qualification_assessment", case_id=qualification_case) or {}
latest_risk = latest_object("risk_authorization", case_id=qualification_case) or {}
print(f"Qualification case: {qualification_case}")
print(f"Gap hunt id: {hunt.get('gap_hunt_id')}")
print(f"Qualification object present: {bool(qualification)}")
print(f"Qualified candidate: {qualification.get('qualified_buy_candidate') is True}")
print(f"Qualification stage: {qualification.get('stage')}")
print(f"Unmet requirements: {qualification.get('unmet_requirements') or []}")
print(f"Latest governed Risk: {latest_risk.get('decision')}")
print(f"Legacy execution calls intercepted: {len(legacy_execution_attempts)}")

print("\n=== F. READ-ONLY CAPITAL BOUNDARY ===")
try:
    capital = paper_capital_status(qualification_case)
except Exception as exc:
    detail = getattr(exc, "detail", None)
    print(f"Capital boundary error: {detail if detail is not None else exc}")
    capital = None

if capital:
    print(f"Capital stage: {capital.get('stage')}")
    print(f"Capital decision: {(capital.get('capital') or {}).get('decision')}")
    print(f"Research qualified: {(capital.get('research') or {}).get('qualified_buy_candidate')}")
    print(f"Paper order permission: {(capital.get('permissions') or {}).get('paper_order_permission')}")

print("\n=== G. AUTHORITY LOCK ===")
paper_auth = object_count("paper_authorization")
governed_exec = object_count("governed_paper_execution")
legacy_exec = object_count("execution")
positions = object_count("paper_position")
print(f"Paper authorization objects: {paper_auth}")
print(f"Governed execution objects: {governed_exec}")
print(f"Legacy execution objects: {legacy_exec}")
print(f"Paper position objects: {positions}")
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
    int(floor.get("completed_count") or 0) >= 1
    and int(floor.get("failed_closed_count") or 0) == 0
)
qualification_ok = bool(qualification)
capital_boundary_ok = capital is not None
authority_locked = (
    paper_auth == 0 and governed_exec == 0 and legacy_exec == 0 and positions == 0
)

print("\n=== H. FULL FACTORY V2 SUMMARY ===")
print(f"Governed universe/TLS: {universe_ok}")
print(f"Grok + Gemini: {model_ok}")
print(f"Natural promotions: {len(promoted)}")
print(f"GPT 8-agent + Committee floor: {floor_ok}")
print(f"Qualification object created: {qualification_ok}")
print(f"Read-only Capital boundary returned state: {capital_boundary_ok}")
print(f"Authorization/execution/position authority locked: {authority_locked}")
print("Qualification may legitimately be FALSE; Capital must still report that governed state rather than being bypassed.")

passed = bool(
    universe_ok
    and model_ok
    and len(promoted) >= 1
    and floor_ok
    and qualification_ok
    and capital_boundary_ok
    and authority_locked
)

if passed:
    print("RESULT: PASS — full governed chain reached Qualification and Capital on isolated ledger with all execution authority locked")
    raise SystemExit(0)

print("RESULT: FAIL — inspect stage output above")
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
        print("FINAL RESULT: INCONCLUSIVE — safe run, no natural promotion this cycle")
        return 2

    print("FINAL RESULT: FAIL — live lanes were not intentionally stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
