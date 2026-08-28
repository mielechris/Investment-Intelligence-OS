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

BRANCH = "feature/batch9t-market-regime-intelligence"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_9T_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9t-market-regime")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
REGIME_LABEL = "com.iios.market-regime-intelligence"
REGIME_INTERVAL_SECONDS = 1800
REGIME_PLIST = LAUNCH_DIR / f"{REGIME_LABEL}.plist"
BROWSER_OUTPUT = DIST / "market_regime_intelligence.json"
PARENT_PLISTS = {
    "9O": LAUNCH_DIR / "com.iios.daily-factory-episode.plist",
    "9P": LAUNCH_DIR / "com.iios.chief-intelligence-office.plist",
    "9Q": LAUNCH_DIR / "com.iios.experiment-ab-laboratory.plist",
    "9R": LAUNCH_DIR / "com.iios.data-expansion-factory.plist",
    "9S": LAUNCH_DIR / "com.iios.agent-performance-league.plist",
}


def _configure_base() -> None:
    base.BRANCH = BRANCH
    base.LIVE = LIVE
    base.WORKTREE = WORKTREE
    base.FRONTEND = FRONTEND
    base.DIST = DIST
    base.PREVIEW_HOST = PREVIEW_HOST
    base.PREVIEW_PORT = PREVIEW_PORT


def _cleanup_generated_cache() -> None:
    cache = WORKTREE / "scripts" / "__pycache__"
    if cache.exists() and cache.is_dir():
        shutil.rmtree(cache)


def _hash(path: Path) -> str | None:
    return base._hash(path)


def _build_frontend(npm: str) -> None:
    base._run([npm, "ci"], cwd=FRONTEND)
    base._run([npm, "exec", "eslint", "--",
        "src/LiveFactoryBrowser.tsx", "src/LivingFactoryExperience.tsx", "src/CharacterStoryEngine.tsx",
        "src/InteractiveCaseTheater.tsx", "src/DailyFactoryEpisode.tsx", "src/ChiefIntelligenceOffice.tsx",
        "src/ExperimentABLaboratory.tsx", "src/DataExpansionFactory.tsx", "src/AgentPerformanceLeague.tsx",
        "src/MarketRegimeIntelligence.tsx", "src/MarketValidationStackPanel.tsx"], cwd=FRONTEND)
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9T frontend build did not produce dist/index.html")


def _publish_parent_artifacts(python: Path) -> None:
    commands = [
        ("iios_chief_intelligence_office.py", "chief_intelligence_office.json"),
        ("iios_experiment_ab_laboratory.py", "experiment_ab_laboratory.json"),
        ("iios_data_expansion_factory.py", "data_expansion_factory.json"),
        ("iios_agent_performance_league.py", "agent_performance_league.json"),
    ]
    for script, output in commands:
        base._run([str(python), str(WORKTREE / "scripts" / script), "--state-dir", str(STATE_DIR), "--telemetry-dir", str(TELEMETRY_DIR), "--output", str(DIST / output)], cwd=WORKTREE)
    episode = STATE_DIR / "browser" / "daily_factory_episode.json"
    if episode.exists() and episode.is_file():
        shutil.copy2(episode, DIST / "daily_factory_episode.json")


def _publish_once(python: Path) -> dict:
    base._run([str(python), str(WORKTREE / "scripts" / "iios_market_regime_intelligence_publisher.py"), "--state-dir", str(STATE_DIR), "--telemetry-dir", str(TELEMETRY_DIR), "--browser-output", str(BROWSER_OUTPUT)], cwd=WORKTREE)
    return json.loads(BROWSER_OUTPUT.read_text(encoding="utf-8"))


def _install_regime_agent(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": REGIME_LABEL,
        "ProgramArguments": [str(python), str(WORKTREE / "scripts" / "iios_market_regime_intelligence_publisher.py"), "--state-dir", str(STATE_DIR), "--telemetry-dir", str(TELEMETRY_DIR), "--browser-output", str(BROWSER_OUTPUT)],
        "WorkingDirectory": str(WORKTREE), "RunAtLoad": True, "StartInterval": REGIME_INTERVAL_SECONDS,
        "ProcessType": "Background", "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "market-regime-intelligence.out.log"),
        "StandardErrorPath": str(LOG_DIR / "market-regime-intelligence.err.log"),
    }
    tmp = REGIME_PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle: plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(REGIME_PLIST)
    domain = f"gui/{os.getuid()}"
    base._run(["launchctl", "bootout", domain, str(REGIME_PLIST)], check=False, capture=True)
    base._run(["launchctl", "bootstrap", domain, str(REGIME_PLIST)])
    base._run(["launchctl", "kickstart", "-k", f"{domain}/{REGIME_LABEL}"])


def _preview_health() -> dict:
    url = f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health"
    time.sleep(2)
    try:
        return base._json_url(url, attempts=80)
    except RuntimeError:
        domain = f"gui/{os.getuid()}"
        base._run(["launchctl", "kickstart", "-k", f"{domain}/{base.LABEL}"], check=False, capture=True)
        time.sleep(2)
        return base._json_url(url, attempts=80)


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9T activation is intentionally macOS-only for this IIOS runtime")
    _configure_base(); _cleanup_generated_cache()
    git = base._require_command("git"); npm = base._require_command("npm"); base._require_command("launchctl")
    print("IIOS BATCH 9T — MARKET REGIME INTELLIGENCE ACTIVATION")
    print("Parent Batch 9S: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print("Regime mode: CLASSIFICATION ONLY · ADVISORY METADATA")
    print("Threshold / agent / portfolio / capital authority: NONE")
    print("Trade execution permission: FALSE")
    print("Live execution: FALSE")
    protected_before = base._protected_hashes()
    parent_before = {key: _hash(path) for key, path in PARENT_PLISTS.items()}
    branch_before, status_before = base._prepare_worktree(git)
    python = base._resolve_python(); _build_frontend(npm)
    backend = base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend.get("read_only_aggregation") is not True: raise SystemExit("Backend 8002 Factory Intelligence contract is not read-only")
    _publish_parent_artifacts(python); payload = _publish_once(python)
    safety = payload.get("safety") or {}
    for key in ("auto_change_thresholds", "auto_change_agent_weights", "auto_change_model_routing", "auto_change_portfolio_exposure", "committee_change_authority", "risk_rule_change_authority", "capital_authority", "trade_execution_permission", "live_execution"):
        if safety.get(key) is not False: raise SystemExit(f"Batch 9T safety contract violated: {key}")
    _install_regime_agent(python); base._install_preview_agent(python)
    health = _preview_health()
    if health.get("backend_access") != "READ_ONLY_GET_ONLY" or health.get("live_execution") is not False: raise SystemExit("Batch 9T preview safety boundary failed")
    if base._protected_hashes() != protected_before: raise SystemExit("Refusing Batch 9T activation: protected 9G/9H/9I/9J LaunchAgent changed")
    if {key: _hash(path) for key, path in PARENT_PLISTS.items()} != parent_before: raise SystemExit("Refusing Batch 9T activation: one or more 9O/9P/9Q/9R/9S LaunchAgents changed")
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before or base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before: raise SystemExit("Live IIOS checkout changed during Batch 9T activation")
    opener = shutil.which("open")
    if opener: base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)
    current = payload.get("current_regime") or {}
    print(json.dumps({"status":"BATCH9T_MARKET_REGIME_INTELLIGENCE_PREVIEW","preview_url":f"http://{PREVIEW_HOST}:{PREVIEW_PORT}","parent_9s_preserved":True,"backend_8002_unchanged":True,"protected_launch_agents_unchanged":True,"parent_launch_agents_unchanged":True,"regime_launch_agent":REGIME_LABEL,"regime_label":current.get("regime_label"),"evidence_level":current.get("evidence_level"),"classification_only":True,"capital_authority":False,"trade_execution_permission":False,"broker_connected":False,"live_execution":False,"worktree":str(WORKTREE)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
