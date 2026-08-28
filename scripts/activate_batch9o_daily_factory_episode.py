#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import sys
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH = "feature/batch9o-daily-factory-episode"
LIVE = Path(
    os.getenv(
        "IIOS_LIVE_CHECKOUT",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8",
    )
).expanduser()
WORKTREE = Path(
    os.getenv(
        "IIOS_9O_WORKTREE",
        "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9o-daily-episode",
    )
).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
EPISODE_LABEL = "com.iios.daily-factory-episode"
EPISODE_INTERVAL_SECONDS = 1800
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
EPISODE_PLIST = LAUNCH_DIR / f"{EPISODE_LABEL}.plist"
BROWSER_EPISODE = DIST / "daily_factory_episode.json"


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
        raise SystemExit(f"9O frontend not found: {FRONTEND}")
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
            "src/DailyFactoryEpisode.tsx",
            "src/MarketValidationStackPanel.tsx",
        ],
        cwd=FRONTEND,
    )
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9O frontend build did not produce dist/index.html")


def _install_episode_agent(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": EPISODE_LABEL,
        "ProgramArguments": [
            str(python),
            str(WORKTREE / "scripts" / "iios_daily_factory_episode_publisher.py"),
            "--state-dir",
            str(STATE_DIR),
            "--telemetry-dir",
            str(TELEMETRY_DIR),
            "--browser-output",
            str(BROWSER_EPISODE),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": EPISODE_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "daily-factory-episode.out.log"),
        "StandardErrorPath": str(LOG_DIR / "daily-factory-episode.err.log"),
    }
    temporary = EPISODE_PLIST.with_suffix(".tmp.plist")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temporary.replace(EPISODE_PLIST)
    domain = f"gui/{os.getuid()}"
    base._run(["launchctl", "bootout", domain, str(EPISODE_PLIST)], check=False, capture=True)
    base._run(["launchctl", "bootstrap", domain, str(EPISODE_PLIST)])
    base._run(["launchctl", "kickstart", "-k", f"{domain}/{EPISODE_LABEL}"])
    base._run(["launchctl", "print", f"{domain}/{EPISODE_LABEL}"], capture=True)


def _episode_preview(python: Path) -> dict:
    result = base._run(
        [
            str(python),
            str(WORKTREE / "scripts" / "iios_daily_factory_episode.py"),
            "--state-dir",
            str(STATE_DIR),
            "--telemetry-dir",
            str(TELEMETRY_DIR),
            "--preview",
            "--stdout",
        ],
        cwd=WORKTREE,
        capture=True,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Batch 9O preview builder did not return JSON: {result.stdout[:1000]}") from exc
    if not isinstance(value, dict):
        raise SystemExit("Batch 9O preview builder returned a non-object payload")
    return value


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9O activation is intentionally macOS-only for this IIOS runtime")
    _configure_base()
    git = base._require_command("git")
    npm = base._require_command("npm")
    base._require_command("launchctl")

    print("IIOS BATCH 9O — DAILY FACTORY EPISODE ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Parent Batch 9N: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("Episode source: PERSISTED 9G/9H/9I/9J READ-ONLY STATE")
    print("Episode final window: 16:45 America/New_York")
    print(f"Episode check interval: {EPISODE_INTERVAL_SECONDS} seconds")
    print("Episode write scope: local browser/report artifacts only")
    print("Direct ledger access: NONE")
    print("Backend write permission: FALSE")
    print("Trade execution permission: FALSE")
    print("Live execution: FALSE")

    protected_before = base._protected_hashes()
    branch_before, status_before = base._prepare_worktree(git)
    python = base._resolve_python()
    _build_frontend(npm)

    episode_preview = _episode_preview(python)
    episode_safety = episode_preview.get("safety") or {}
    if episode_safety.get("direct_ledger_access") is not False:
        raise SystemExit("Batch 9O episode preview unexpectedly reports direct ledger access")
    if episode_safety.get("trade_execution_permission") is not False:
        raise SystemExit("Batch 9O episode preview unexpectedly reports trade execution permission")
    if episode_safety.get("live_execution") is not False:
        raise SystemExit("Batch 9O episode preview violated the live-execution lock")

    backend_status = base._json_url(
        "http://127.0.0.1:8002/experience/factory-intelligence/status",
        attempts=4,
    )
    if backend_status.get("read_only_aggregation") is not True:
        raise SystemExit(
            "Backend 8002 Factory Intelligence contract is not reporting read-only aggregation"
        )

    _install_episode_agent(python)
    base._install_preview_agent(python)
    health = base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health")
    living = base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/living/overview")

    if health.get("ledger_access") != "NONE":
        raise SystemExit("Batch 9O preview unexpectedly reports ledger access")
    if health.get("backend_access") != "READ_ONLY_GET_ONLY":
        raise SystemExit("Batch 9O preview did not preserve read-only backend access")
    if health.get("backend_write_permission") is not False:
        raise SystemExit("Batch 9O preview unexpectedly reports backend write permission")
    if health.get("live_execution") is not False:
        raise SystemExit("Batch 9O preview violated live-execution lock")

    safety = living.get("safety") or {}
    if safety.get("direct_ledger_access") is not False:
        raise SystemExit("Batch 9O living source unexpectedly reports direct ledger access")
    if safety.get("backend_write_permission") is not False:
        raise SystemExit("Batch 9O living source unexpectedly reports backend write permission")
    if safety.get("trade_execution_permission") is not False:
        raise SystemExit("Batch 9O living source unexpectedly reports execution permission")
    if safety.get("live_execution") is not False:
        raise SystemExit("Batch 9O living source violated live-execution lock")

    protected_after = base._protected_hashes()
    if protected_after != protected_before:
        raise SystemExit(
            "Refusing Batch 9O activation: one or more 9G/9H/9I/9J LaunchAgents changed"
        )
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9O activation")
    if base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9O activation")

    opener = shutil.which("open")
    if opener:
        base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    summary = {
        "status": "BATCH9O_DAILY_FACTORY_EPISODE_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "parent_9n_preserved": True,
        "backend_8002_unchanged": True,
        "live_checkout_unchanged": True,
        "protected_launch_agents_unchanged": True,
        "episode_launch_agent": EPISODE_LABEL,
        "episode_check_interval_seconds": EPISODE_INTERVAL_SECONDS,
        "episode_final_window_ny": "16:45",
        "episode_preview_status": episode_preview.get("status"),
        "episode_session_id": episode_preview.get("episode_session_id"),
        "direct_ledger_access": "NONE",
        "backend_access": "READ_ONLY_GET_ONLY",
        "backend_write_permission": False,
        "trade_execution_permission": False,
        "broker_connected": False,
        "live_execution": False,
        "worktree": str(WORKTREE),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "\nBatch 9O daily episode is installed in the isolated preview. It writes only local report/browser artifacts and cannot alter factory decisions, capital authority or execution."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
