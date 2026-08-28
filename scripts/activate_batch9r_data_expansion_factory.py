#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import sys
import time
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH = "feature/batch9r-data-expansion-factory"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_9R_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9r-data-expansion")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
DATA_LABEL = "com.iios.data-expansion-factory"
DATA_INTERVAL_SECONDS = 1800
DATA_PLIST = LAUNCH_DIR / f"{DATA_LABEL}.plist"
BROWSER_OUTPUT = DIST / "data_expansion_factory.json"
EPISODE_PLIST = LAUNCH_DIR / "com.iios.daily-factory-episode.plist"
OFFICE_PLIST = LAUNCH_DIR / "com.iios.chief-intelligence-office.plist"
LAB_PLIST = LAUNCH_DIR / "com.iios.experiment-ab-laboratory.plist"


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
            "src/ChiefIntelligenceOffice.tsx",
            "src/ExperimentABLaboratory.tsx",
            "src/DataExpansionFactory.tsx",
            "src/MarketValidationStackPanel.tsx",
        ],
        cwd=FRONTEND,
    )
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9R frontend build did not produce dist/index.html")


def _publish_parent_artifacts(python: Path) -> None:
    base._run(
        [
            str(python),
            str(WORKTREE / "scripts" / "iios_chief_intelligence_office.py"),
            "--state-dir",
            str(STATE_DIR),
            "--telemetry-dir",
            str(TELEMETRY_DIR),
            "--output",
            str(DIST / "chief_intelligence_office.json"),
        ],
        cwd=WORKTREE,
    )
    base._run(
        [
            str(python),
            str(WORKTREE / "scripts" / "iios_experiment_ab_laboratory.py"),
            "--state-dir",
            str(STATE_DIR),
            "--telemetry-dir",
            str(TELEMETRY_DIR),
            "--output",
            str(DIST / "experiment_ab_laboratory.json"),
        ],
        cwd=WORKTREE,
    )
    episode = STATE_DIR / "browser" / "daily_factory_episode.json"
    if episode.exists() and episode.is_file():
        shutil.copy2(episode, DIST / "daily_factory_episode.json")


def _publish_once(python: Path) -> dict:
    base._run(
        [
            str(python),
            str(WORKTREE / "scripts" / "iios_data_expansion_factory_publisher.py"),
            "--state-dir",
            str(STATE_DIR),
            "--telemetry-dir",
            str(TELEMETRY_DIR),
            "--browser-output",
            str(BROWSER_OUTPUT),
        ],
        cwd=WORKTREE,
    )
    return json.loads(BROWSER_OUTPUT.read_text(encoding="utf-8"))


def _install_data_agent(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": DATA_LABEL,
        "ProgramArguments": [
            str(python),
            str(WORKTREE / "scripts" / "iios_data_expansion_factory_publisher.py"),
            "--state-dir",
            str(STATE_DIR),
            "--telemetry-dir",
            str(TELEMETRY_DIR),
            "--browser-output",
            str(BROWSER_OUTPUT),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": DATA_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "data-expansion-factory.out.log"),
        "StandardErrorPath": str(LOG_DIR / "data-expansion-factory.err.log"),
    }
    temporary = DATA_PLIST.with_suffix(".tmp.plist")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temporary.replace(DATA_PLIST)
    domain = f"gui/{os.getuid()}"
    base._run(["launchctl", "bootout", domain, str(DATA_PLIST)], check=False, capture=True)
    base._run(["launchctl", "bootstrap", domain, str(DATA_PLIST)])
    base._run(["launchctl", "kickstart", "-k", f"{domain}/{DATA_LABEL}"])


def _preview_health() -> dict:
    url = f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health"
    time.sleep(2.0)
    try:
        return base._json_url(url, attempts=80)
    except RuntimeError:
        domain = f"gui/{os.getuid()}"
        label = f"{domain}/{base.LABEL}"
        base._run(["launchctl", "kickstart", "-k", label], check=False, capture=True)
        time.sleep(2.0)
        return base._json_url(url, attempts=80)


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9R activation is intentionally macOS-only for this IIOS runtime")
    _configure_base()
    _cleanup_generated_cache()
    git = base._require_command("git")
    npm = base._require_command("npm")
    base._require_command("launchctl")

    print("IIOS BATCH 9R — DATA EXPANSION FACTORY ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Parent Batch 9Q: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("Expansion source: PERSISTED 9P / 9Q / 9H / 9G READ-ONLY STATE")
    print(f"Expansion refresh interval: {DATA_INTERVAL_SECONDS} seconds")
    print("Provider connection / credentials / purchase / licensing authority: NONE")
    print("Production feed change authority: FALSE")
    print("Trade execution permission: FALSE")
    print("Live execution: FALSE")

    protected_before = base._protected_hashes()
    parent_hashes_before = {
        "9O": _hash(EPISODE_PLIST),
        "9P": _hash(OFFICE_PLIST),
        "9Q": _hash(LAB_PLIST),
    }
    branch_before, status_before = base._prepare_worktree(git)
    python = base._resolve_python()
    _build_frontend(npm)

    backend_status = base._json_url(
        "http://127.0.0.1:8002/experience/factory-intelligence/status",
        attempts=4,
    )
    if backend_status.get("read_only_aggregation") is not True:
        raise SystemExit("Backend 8002 Factory Intelligence contract is not read-only")

    _publish_parent_artifacts(python)
    factory = _publish_once(python)
    safety = factory.get("safety") or {}
    for key in (
        "auto_connect_provider",
        "auto_request_credentials",
        "credential_use_authority",
        "purchase_authority",
        "license_acceptance_authority",
        "production_feed_change_authority",
        "auto_apply_thresholds",
        "agent_weight_change_authority",
        "committee_change_authority",
        "risk_rule_change_authority",
        "capital_authority",
        "trade_execution_permission",
        "live_execution",
    ):
        if safety.get(key) is not False:
            raise SystemExit(f"Batch 9R safety contract violated: {key}")
    if safety.get("advisory_only") is not True or safety.get("human_approval_required") is not True:
        raise SystemExit("Batch 9R advisory/human-approval contract missing")

    _install_data_agent(python)
    base._install_preview_agent(python)
    health = _preview_health()
    if health.get("backend_access") != "READ_ONLY_GET_ONLY" or health.get("live_execution") is not False:
        raise SystemExit("Batch 9R preview did not preserve read-only/no-execution boundary")

    if base._protected_hashes() != protected_before:
        raise SystemExit("Refusing Batch 9R activation: a protected 9G/9H/9I/9J LaunchAgent changed")
    parent_hashes_after = {
        "9O": _hash(EPISODE_PLIST),
        "9P": _hash(OFFICE_PLIST),
        "9Q": _hash(LAB_PLIST),
    }
    if parent_hashes_after != parent_hashes_before:
        raise SystemExit("Refusing Batch 9R activation: one or more 9O/9P/9Q LaunchAgents changed")
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9R activation")
    if base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9R activation")

    opener = shutil.which("open")
    if opener:
        base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    summary = factory.get("summary") or {}
    print(
        json.dumps(
            {
                "status": "BATCH9R_DATA_EXPANSION_FACTORY_PREVIEW",
                "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
                "parent_9q_preserved": True,
                "backend_8002_unchanged": True,
                "protected_launch_agents_unchanged": True,
                "episode_office_lab_launch_agents_unchanged": True,
                "data_expansion_launch_agent": DATA_LABEL,
                "data_refresh_interval_seconds": DATA_INTERVAL_SECONDS,
                "identified_gap_count": summary.get("identified_gap_count"),
                "candidate_source_count": summary.get("candidate_source_count"),
                "shadow_connected_count": summary.get("shadow_connected_count"),
                "production_sources_added": summary.get("production_sources_added"),
                "advisory_only": True,
                "human_approval_required": True,
                "purchase_authority": False,
                "production_feed_change_authority": False,
                "trade_execution_permission": False,
                "broker_connected": False,
                "live_execution": False,
                "worktree": str(WORKTREE),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
