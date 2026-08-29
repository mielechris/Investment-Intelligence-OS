#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
BRANCH = "feature/batch10m1-model-agent-intelligence-health"
LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
MAIN_BACKEND = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend")
COST_HELPER = MAIN_BACKEND / "model_cost_enforcement.py"
VENV = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python3")


def capture(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(list(args), cwd=str(cwd) if cwd else None, text=True).strip()


def run(*args: str, cwd: Path | None = None, check: bool = True, env=None):
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
        check=check,
        env=env,
    )


def nine_e_processes() -> list[str]:
    result = subprocess.run(
        ["pgrep", "-af", "iios_high_speed_factory_runner.py"],
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    report = {
        "status": "BATCH10M1_ACTIVATION_CHECK",
        "target_branch": BRANCH,
        "live_ledger": str(LEDGER),
        "broker_connected": False,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }

    if not LIVE.exists() or not LEDGER.exists():
        report.update(status="REFUSED", reason="LIVE_CHECKOUT_OR_LEDGER_MISSING")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    if not COST_HELPER.exists():
        report.update(status="REFUSED", reason="SHARED_GROK_COST_GOVERNOR_MISSING")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    if not VENV.exists():
        report.update(status="REFUSED", reason="IIOS_VENV_PYTHON3_MISSING")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    running = nine_e_processes()
    if running:
        report.update(
            status="CONTROLLED_9E_STOP_REQUIRED",
            running_9e_processes=running,
            next_action="CTRL_C_FULL_FACTORY_9E_LIVE_THEN_RERUN_THIS_ACTIVATOR",
            files_modified=False,
            ledger_modified=False,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3

    live_branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    live_status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)
    target_sha = capture("git", "rev-parse", f"origin/{BRANCH}", cwd=LIVE)

    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"Refusing non-worktree target: {WORKTREE}")
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

    live_branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    live_status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    if live_branch_after != live_branch_before or live_status_after != live_status_before:
        raise SystemExit("Refusing activation: governed Batch8 branch/status changed")

    compile_paths = [
        WORKTREE / "BACK END" / "backend" / "agent_contract_v2.py",
        WORKTREE / "BACK END" / "backend" / "eight_agent_orchestrator_v2.py",
        WORKTREE / "BACK END" / "backend" / "model_agent_health_watchdog.py",
        WORKTREE / "BACK END" / "backend" / "high_speed_case_queue.py",
        WORKTREE / "BACK END" / "backend" / "high_speed_gemini_deep_worker.py",
        WORKTREE / "scripts" / "iios_high_speed_factory_runner.py",
        WORKTREE / "scripts" / "launch_batch9e_live_paper_factory.py",
    ]
    run(str(VENV), "-m", "py_compile", *(str(path) for path in compile_paths))

    env = dict(os.environ)
    env["IIOS_DB_PATH"] = str(LEDGER)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(WORKTREE / "BACK END" / "backend"), str(MAIN_BACKEND)]
    )
    health_cmd = (
        "from model_agent_health_watchdog import publish_health_artifact; "
        "import json; print(json.dumps(publish_health_artifact(), sort_keys=True))"
    )
    health_result = subprocess.run(
        [str(VENV), "-c", health_cmd],
        cwd=str(WORKTREE),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    try:
        health = json.loads(health_result.stdout.strip().splitlines()[-1])
    except Exception:
        health = {"status": "HEALTH_CANARY_UNPARSEABLE", "raw": health_result.stdout[-1000:]}

    report.update(
        status="BATCH10M1_SUPERBATCH_STAGED",
        target_sha=target_sha,
        worktree_head=capture("git", "rev-parse", "HEAD", cwd=WORKTREE),
        live_branch_preserved=live_branch_after == live_branch_before,
        live_status_preserved=live_status_after == live_status_before,
        compile_pass=True,
        health_canary_status=health.get("status"),
        health_canary_state=health.get("overall_state"),
        health_canary_issues=health.get("issues") or [],
        provider_requests_made=False,
        ledger_modified=False,
        next_action="START_10M1_WITH_GUARDED_LAUNCHER",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
