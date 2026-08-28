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

BRANCH = "feature/batch9q-experiment-ab-laboratory"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_9Q_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9q-experiment-lab")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LAB_LABEL = "com.iios.experiment-ab-laboratory"
LAB_INTERVAL_SECONDS = 1800
LAB_PLIST = LAUNCH_DIR / f"{LAB_LABEL}.plist"
BROWSER_OUTPUT = DIST / "experiment_ab_laboratory.json"
OFFICE_PLIST = LAUNCH_DIR / "com.iios.chief-intelligence-office.plist"
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
        "src/ExperimentABLaboratory.tsx",
        "src/MarketValidationStackPanel.tsx",
    ], cwd=FRONTEND)
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9Q frontend build did not produce dist/index.html")


def _install_lab_agent(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LAB_LABEL,
        "ProgramArguments": [
            str(python),
            str(WORKTREE / "scripts" / "iios_experiment_ab_laboratory_publisher.py"),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--browser-output", str(BROWSER_OUTPUT),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": LAB_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "experiment-ab-laboratory.out.log"),
        "StandardErrorPath": str(LOG_DIR / "experiment-ab-laboratory.err.log"),
    }
    tmp = LAB_PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(LAB_PLIST)
    domain = f"gui/{os.getuid()}"
    base._run(["launchctl", "bootout", domain, str(LAB_PLIST)], check=False, capture=True)
    base._run(["launchctl", "bootstrap", domain, str(LAB_PLIST)])
    base._run(["launchctl", "kickstart", "-k", f"{domain}/{LAB_LABEL}"])


def _publish_once(python: Path) -> dict:
    base._run([
        str(python),
        str(WORKTREE / "scripts" / "iios_experiment_ab_laboratory_publisher.py"),
        "--state-dir", str(STATE_DIR),
        "--telemetry-dir", str(TELEMETRY_DIR),
        "--browser-output", str(BROWSER_OUTPUT),
    ], cwd=WORKTREE)
    return json.loads(BROWSER_OUTPUT.read_text(encoding="utf-8"))


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
        raise SystemExit("Batch 9Q activation is intentionally macOS-only for this IIOS runtime")
    _configure_base()
    _cleanup_generated_cache()
    git = base._require_command("git")
    npm = base._require_command("npm")
    base._require_command("launchctl")

    print("IIOS BATCH 9Q — EXPERIMENT & A/B LABORATORY ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Parent Batch 9P: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("Lab source: PERSISTED 9P / 9I / 9J / 9G READ-ONLY STATE")
    print(f"Lab refresh interval: {LAB_INTERVAL_SECONDS} seconds")
    print("Experiment mode: SHADOW ONLY · ADVISORY ONLY")
    print("Variant / threshold / agent / Committee / Risk / capital authority: NONE")
    print("Trade execution permission: FALSE")
    print("Live execution: FALSE")

    protected_before = base._protected_hashes()
    office_hash_before = _hash(OFFICE_PLIST)
    episode_hash_before = _hash(EPISODE_PLIST)
    branch_before, status_before = base._prepare_worktree(git)
    python = base._resolve_python()
    _build_frontend(npm)

    backend_status = base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend_status.get("read_only_aggregation") is not True:
        raise SystemExit("Backend 8002 Factory Intelligence contract is not read-only")

    lab = _publish_once(python)
    safety = lab.get("safety") or {}
    for key in (
        "browser_controls_execute_factory",
        "auto_apply_variants",
        "auto_apply_thresholds",
        "agent_weight_change_authority",
        "committee_change_authority",
        "risk_rule_change_authority",
        "capital_authority",
        "trade_execution_permission",
        "live_execution",
    ):
        if safety.get(key) is not False:
            raise SystemExit(f"Batch 9Q safety contract violated: {key}")
    if safety.get("shadow_only") is not True or safety.get("advisory_only") is not True:
        raise SystemExit("Batch 9Q shadow/advisory contract missing")
    if safety.get("human_approval_required") is not True:
        raise SystemExit("Batch 9Q human approval contract missing")

    _install_lab_agent(python)
    base._install_preview_agent(python)
    health = _preview_health()
    if health.get("backend_access") != "READ_ONLY_GET_ONLY" or health.get("live_execution") is not False:
        raise SystemExit("Batch 9Q preview did not preserve read-only/no-execution boundary")

    if base._protected_hashes() != protected_before:
        raise SystemExit("Refusing Batch 9Q activation: a protected 9G/9H/9I/9J LaunchAgent changed")
    if _hash(OFFICE_PLIST) != office_hash_before:
        raise SystemExit("Refusing Batch 9Q activation: the 9P Chief Intelligence Office LaunchAgent changed")
    if _hash(EPISODE_PLIST) != episode_hash_before:
        raise SystemExit("Refusing Batch 9Q activation: the 9O Daily Factory Episode LaunchAgent changed")
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9Q activation")
    if base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9Q activation")

    opener = shutil.which("open")
    if opener:
        base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    summary = lab.get("summary") or {}
    print(json.dumps({
        "status": "BATCH9Q_EXPERIMENT_AB_LAB_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "parent_9p_preserved": True,
        "backend_8002_unchanged": True,
        "protected_launch_agents_unchanged": True,
        "chief_office_launch_agent_unchanged": True,
        "episode_launch_agent_unchanged": True,
        "lab_launch_agent": LAB_LABEL,
        "lab_refresh_interval_seconds": LAB_INTERVAL_SECONDS,
        "experiment_count": summary.get("experiment_count"),
        "keep_count": summary.get("keep_count"),
        "reject_count": summary.get("reject_count"),
        "need_more_data_count": summary.get("need_more_data_count"),
        "production_changes_applied": 0,
        "shadow_only": True,
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
