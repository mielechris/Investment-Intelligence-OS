#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import sys
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH = "feature/batch9p-chief-intelligence-office"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_9P_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9p-chief-office")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
OFFICE_LABEL = "com.iios.chief-intelligence-office"
OFFICE_INTERVAL_SECONDS = 1800
OFFICE_PLIST = LAUNCH_DIR / f"{OFFICE_LABEL}.plist"
BROWSER_OUTPUT = DIST / "chief_intelligence_office.json"
EPISODE_PLIST = LAUNCH_DIR / "com.iios.daily-factory-episode.plist"


def _configure_base() -> None:
    base.BRANCH = BRANCH
    base.LIVE = LIVE
    base.WORKTREE = WORKTREE
    base.FRONTEND = FRONTEND
    base.DIST = DIST
    base.PREVIEW_HOST = PREVIEW_HOST
    base.PREVIEW_PORT = PREVIEW_PORT


def _cleanup_generated_cache() -> None:
    scripts_cache = WORKTREE / "scripts" / "__pycache__"
    if scripts_cache.exists() and scripts_cache.is_dir():
        shutil.rmtree(scripts_cache)


def _hash(path: Path) -> str | None:
    return base._hash(path)


def _build_frontend(npm: str) -> None:
    base._run([npm, "ci"], cwd=FRONTEND)
    base._run([
        npm, "exec", "eslint", "--",
        "src/LiveFactoryBrowser.tsx",
        "src/LivingFactoryExperience.tsx",
        "src/CharacterStoryEngine.tsx",
        "src/InteractiveCaseTheater.tsx",
        "src/DailyFactoryEpisode.tsx",
        "src/ChiefIntelligenceOffice.tsx",
        "src/MarketValidationStackPanel.tsx",
    ], cwd=FRONTEND)
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9P frontend build did not produce dist/index.html")


def _install_office_agent(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": OFFICE_LABEL,
        "ProgramArguments": [
            str(python),
            str(WORKTREE / "scripts" / "iios_chief_intelligence_office_publisher.py"),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--browser-output", str(BROWSER_OUTPUT),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": OFFICE_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "chief-intelligence-office.out.log"),
        "StandardErrorPath": str(LOG_DIR / "chief-intelligence-office.err.log"),
    }
    tmp = OFFICE_PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(OFFICE_PLIST)
    domain = f"gui/{os.getuid()}"
    base._run(["launchctl", "bootout", domain, str(OFFICE_PLIST)], check=False, capture=True)
    base._run(["launchctl", "bootstrap", domain, str(OFFICE_PLIST)])
    base._run(["launchctl", "kickstart", "-k", f"{domain}/{OFFICE_LABEL}"])


def _publish_once(python: Path) -> None:
    base._run([
        str(python),
        str(WORKTREE / "scripts" / "iios_chief_intelligence_office_publisher.py"),
        "--state-dir", str(STATE_DIR),
        "--telemetry-dir", str(TELEMETRY_DIR),
        "--browser-output", str(BROWSER_OUTPUT),
    ], cwd=WORKTREE)


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9P activation is intentionally macOS-only for this IIOS runtime")
    _configure_base()
    _cleanup_generated_cache()
    git = base._require_command("git")
    npm = base._require_command("npm")
    base._require_command("launchctl")

    print("IIOS BATCH 9P — CHIEF INTELLIGENCE OFFICE ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Parent Batch 9O: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("Office source: PERSISTED 9G/9H/9I/9J + 9O READ-ONLY STATE")
    print(f"Office refresh interval: {OFFICE_INTERVAL_SECONDS} seconds")
    print("Threshold / agent / Committee / Risk / capital authority: NONE")
    print("Trade execution permission: FALSE")
    print("Live execution: FALSE")

    protected_before = base._protected_hashes()
    episode_hash_before = _hash(EPISODE_PLIST)
    branch_before, status_before = base._prepare_worktree(git)
    python = base._resolve_python()
    _build_frontend(npm)

    backend_status = base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend_status.get("read_only_aggregation") is not True:
        raise SystemExit("Backend 8002 Factory Intelligence contract is not read-only")

    _publish_once(python)
    office = json.loads(BROWSER_OUTPUT.read_text(encoding="utf-8"))
    safety = office.get("safety") or {}
    for key in (
        "auto_apply_thresholds",
        "agent_weight_change_authority",
        "committee_change_authority",
        "risk_rule_change_authority",
        "capital_authority",
        "trade_execution_permission",
        "live_execution",
    ):
        if safety.get(key) is not False:
            raise SystemExit(f"Batch 9P safety contract violated: {key}")
    if safety.get("advisory_only") is not True or safety.get("human_approval_required") is not True:
        raise SystemExit("Batch 9P advisory/human approval contract missing")

    _install_office_agent(python)
    base._install_preview_agent(python)
    health = base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health", attempts=60)
    if health.get("backend_access") != "READ_ONLY_GET_ONLY" or health.get("live_execution") is not False:
        raise SystemExit("Batch 9P preview did not preserve read-only/no-execution boundary")

    if base._protected_hashes() != protected_before:
        raise SystemExit("Refusing Batch 9P activation: a protected 9G/9H/9I/9J LaunchAgent changed")
    if _hash(EPISODE_PLIST) != episode_hash_before:
        raise SystemExit("Refusing Batch 9P activation: the 9O Daily Factory Episode LaunchAgent changed")
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9P activation")
    if base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9P activation")

    opener = shutil.which("open")
    if opener:
        base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    print(json.dumps({
        "status": "BATCH9P_CHIEF_INTELLIGENCE_OFFICE_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "parent_9o_preserved": True,
        "backend_8002_unchanged": True,
        "protected_launch_agents_unchanged": True,
        "episode_launch_agent_unchanged": True,
        "office_launch_agent": OFFICE_LABEL,
        "office_refresh_interval_seconds": OFFICE_INTERVAL_SECONDS,
        "office_status": office.get("status"),
        "top_upgrade_count": len((office.get("improvement_memo") or {}).get("top_five_upgrades") or []),
        "advisory_only": True,
        "human_approval_required": True,
        "trade_execution_permission": False,
        "broker_connected": False,
        "live_execution": False,
        "worktree": str(WORKTREE),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
