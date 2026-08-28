#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH = "feature/batch9l-living-factory-provenance"
LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9L_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9l-living-factory",
    )
).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
LIVING_SCHEMA_VERSION = "batch9l-living-factory-provenance-v1"


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
        raise SystemExit(f"9L frontend not found: {FRONTEND}")
    base._run([npm, "ci"], cwd=FRONTEND)
    base._run(
        [
            npm,
            "exec",
            "eslint",
            "--",
            "src/LiveFactoryBrowser.tsx",
            "src/LivingFactoryExperience.tsx",
            "src/MarketValidationStackPanel.tsx",
        ],
        cwd=FRONTEND,
    )
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9L frontend build did not produce dist/index.html")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9L activation is intentionally macOS-only for this IIOS runtime")
    _configure_base()
    git = base._require_command("git")
    npm = base._require_command("npm")
    base._require_command("launchctl")

    print("IIOS BATCH 9L — LIVING FACTORY + SIGNAL PROVENANCE ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("Direct ledger access: NONE")
    print("Backend access: READ-ONLY GET ONLY")
    print("Backend write permission: FALSE")
    print("Preview bind: LOCALHOST ONLY")
    print("Broker connected: FALSE")
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
    stack = base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/validation/stack")
    living = base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/living/overview")

    if health.get("ledger_access") != "NONE" or health.get("live_execution") is not False:
        raise SystemExit("Batch 9L preview health did not preserve no-ledger/no-execution boundary")
    if health.get("backend_access") != "READ_ONLY_GET_ONLY":
        raise SystemExit("Batch 9L preview health did not preserve read-only backend access")
    if health.get("backend_write_permission") is not False:
        raise SystemExit("Batch 9L preview unexpectedly reports backend write permission")
    if stack.get("schema_version") != "batch9k-live-factory-browser-v1":
        raise SystemExit("Batch 9L did not preserve the inherited 9K validation-stack contract")
    if living.get("schema_version") != LIVING_SCHEMA_VERSION:
        raise SystemExit("Batch 9L living factory schema mismatch")
    safety = living.get("safety") or {}
    if safety.get("direct_ledger_access") is not False:
        raise SystemExit("Batch 9L living sidecar unexpectedly reports direct ledger access")
    if safety.get("backend_write_permission") is not False:
        raise SystemExit("Batch 9L living sidecar unexpectedly reports backend write permission")
    if safety.get("trade_execution_permission") is not False or safety.get("live_execution") is not False:
        raise SystemExit("Batch 9L living sidecar violated paper/live execution boundary")

    protected_after = base._protected_hashes()
    if protected_after != protected_before:
        raise SystemExit(
            "Refusing Batch 9L activation: one or more 9G/9H/9I/9J LaunchAgents changed"
        )
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9L activation")
    if base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9L activation")

    opener = shutil.which("open")
    if opener:
        base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    layers = stack.get("layers") or {}
    summary = {
        "status": "BATCH9L_LIVING_FACTORY_PROVENANCE_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "backend_8002_unchanged": True,
        "live_checkout_unchanged": True,
        "protected_launch_agents_unchanged": True,
        "direct_ledger_access": "NONE",
        "backend_access": "READ_ONLY_GET_ONLY",
        "backend_write_permission": False,
        "preview_localhost_only": True,
        "factory_telemetry_state": (layers.get("factory_telemetry") or {}).get("availability"),
        "market_validation_state": (layers.get("market_validation") or {}).get("availability"),
        "shadow_strategy_state": (layers.get("shadow_strategy") or {}).get("availability"),
        "outcome_learning_state": (layers.get("outcome_learning") or {}).get("availability"),
        "factory_overview_state": (living.get("factory") or {}).get("availability"),
        "jesse_dislocation_state": (living.get("jesse_dislocation") or {}).get("availability"),
        "broker_connected": False,
        "live_execution": False,
        "worktree": str(WORKTREE),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "\nBatch 9L preview is live. Only the browser preview LaunchAgent was replaced; Backend 8002 and market workers remain untouched."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
