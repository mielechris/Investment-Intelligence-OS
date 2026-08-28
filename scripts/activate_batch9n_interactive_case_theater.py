#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH = "feature/batch9n-interactive-case-theater"
LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9N_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9n-case-theater",
    )
).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176


def _configure_base() -> None:
    base.BRANCH = BRANCH
    base.LIVE = LIVE
    base.WORKTREE = WORKTREE
    base.FRONTEND = FRONTEND
    base.DIST = DIST
    base.PREVIEW_HOST = PREVIEW_HOST
    base.PREVIEW_PORT = PREVIEW_PORT


def _build_frontend(npm: str) -> None:
    if not FRONTEND.exists():
        raise SystemExit(f"9N frontend not found: {FRONTEND}")
    base._run([npm, "ci"], cwd=FRONTEND)
    base._run(
        [
            npm,
            "exec",
            "eslint",
            "--",
            "src/LiveFactoryBrowser.tsx",
            "src/LivingFactoryExperience.tsx",
            "src/CharacterStoryEngine.tsx",
            "src/InteractiveCaseTheater.tsx",
            "src/MarketValidationStackPanel.tsx",
        ],
        cwd=FRONTEND,
    )
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9N frontend build did not produce dist/index.html")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9N activation is intentionally macOS-only for this IIOS runtime")
    _configure_base()
    git = base._require_command("git")
    npm = base._require_command("npm")
    base._require_command("launchctl")

    print("IIOS BATCH 9N — INTERACTIVE CASE THEATER ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Parent Batch 9M: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("Replay authority: BROWSER CURSOR ONLY")
    print("Direct ledger access: NONE")
    print("Backend access: READ-ONLY GET ONLY")
    print("Backend write permission: FALSE")
    print("Broker connected: FALSE")
    print("Trade execution permission: FALSE")
    print("Live execution: FALSE")

    protected_before = base._protected_hashes()
    branch_before, status_before = base._prepare_worktree(git)
    python = base._resolve_python()
    _build_frontend(npm)

    backend_status = base._json_url(
        "http://127.0.0.1:8002/experience/factory-intelligence/status",
        attempts=4,
    )
    if backend_status.get("read_only_aggregation") is not True:
        raise SystemExit(
            "Backend 8002 Factory Intelligence contract is not reporting read-only aggregation"
        )

    base._install_preview_agent(python)
    health = base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health")
    living = base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/living/overview")

    if health.get("ledger_access") != "NONE":
        raise SystemExit("Batch 9N preview unexpectedly reports ledger access")
    if health.get("backend_access") != "READ_ONLY_GET_ONLY":
        raise SystemExit("Batch 9N preview did not preserve read-only backend access")
    if health.get("backend_write_permission") is not False:
        raise SystemExit("Batch 9N preview unexpectedly reports backend write permission")
    if health.get("live_execution") is not False:
        raise SystemExit("Batch 9N preview violated live-execution lock")

    safety = living.get("safety") or {}
    if safety.get("direct_ledger_access") is not False:
        raise SystemExit("Batch 9N living source unexpectedly reports direct ledger access")
    if safety.get("backend_write_permission") is not False:
        raise SystemExit("Batch 9N living source unexpectedly reports backend write permission")
    if safety.get("trade_execution_permission") is not False:
        raise SystemExit("Batch 9N living source unexpectedly reports execution permission")
    if safety.get("live_execution") is not False:
        raise SystemExit("Batch 9N living source violated live-execution lock")

    protected_after = base._protected_hashes()
    if protected_after != protected_before:
        raise SystemExit(
            "Refusing Batch 9N activation: one or more 9G/9H/9I/9J LaunchAgents changed"
        )
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9N activation")
    if base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9N activation")

    opener = shutil.which("open")
    if opener:
        base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    telemetry = ((living.get("validation") or {}).get("layers") or {}).get("factory_telemetry") or {}
    payload = telemetry.get("payload") or {}
    overview = (living.get("factory") or {}).get("payload") or {}
    summary = {
        "status": "BATCH9N_INTERACTIVE_CASE_THEATER_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "parent_9m_preserved": True,
        "backend_8002_unchanged": True,
        "live_checkout_unchanged": True,
        "protected_launch_agents_unchanged": True,
        "replay_authority": "BROWSER_CURSOR_ONLY",
        "governed_case_count": len(overview.get("cases") or []),
        "persisted_story_event_count": len(payload.get("recent_meaningful_events") or []),
        "direct_ledger_access": "NONE",
        "backend_access": "READ_ONLY_GET_ONLY",
        "backend_write_permission": False,
        "broker_connected": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "worktree": str(WORKTREE),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "\nBatch 9N case theater is live in the isolated preview. Replay controls change only browser state; Backend 8002, market workers, 9G–9J and capital controls were not modified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
