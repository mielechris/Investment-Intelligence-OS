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

BRANCH = "feature/batch9s-agent-performance-league"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_9S_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9s-agent-league")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LEAGUE_LABEL = "com.iios.agent-performance-league"
LEAGUE_INTERVAL_SECONDS = 1800
LEAGUE_PLIST = LAUNCH_DIR / f"{LEAGUE_LABEL}.plist"
BROWSER_OUTPUT = DIST / "agent_performance_league.json"
PARENT_PLISTS = {
    "9O": LAUNCH_DIR / "com.iios.daily-factory-episode.plist",
    "9P": LAUNCH_DIR / "com.iios.chief-intelligence-office.plist",
    "9Q": LAUNCH_DIR / "com.iios.experiment-ab-laboratory.plist",
    "9R": LAUNCH_DIR / "com.iios.data-expansion-factory.plist",
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
        "src/DataExpansionFactory.tsx",
        "src/AgentPerformanceLeague.tsx",
        "src/MarketValidationStackPanel.tsx",
    ], cwd=FRONTEND)
    base._run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("Batch 9S frontend build did not produce dist/index.html")


def _publish_parent_artifacts(python: Path) -> None:
    builders = (
        ("iios_chief_intelligence_office.py", "chief_intelligence_office.json"),
        ("iios_experiment_ab_laboratory.py", "experiment_ab_laboratory.json"),
        ("iios_data_expansion_factory.py", "data_expansion_factory.json"),
    )
    for script, output in builders:
        base._run([
            str(python), str(WORKTREE / "scripts" / script),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--output", str(DIST / output),
        ], cwd=WORKTREE)
    episode = STATE_DIR / "browser" / "daily_factory_episode.json"
    if episode.exists() and episode.is_file():
        shutil.copy2(episode, DIST / "daily_factory_episode.json")


def _publish_once(python: Path) -> dict:
    base._run([
        str(python),
        str(WORKTREE / "scripts" / "iios_agent_performance_league_publisher.py"),
        "--state-dir", str(STATE_DIR),
        "--telemetry-dir", str(TELEMETRY_DIR),
        "--browser-output", str(BROWSER_OUTPUT),
    ], cwd=WORKTREE)
    return json.loads(BROWSER_OUTPUT.read_text(encoding="utf-8"))


def _install_league_agent(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LEAGUE_LABEL,
        "ProgramArguments": [
            str(python),
            str(WORKTREE / "scripts" / "iios_agent_performance_league_publisher.py"),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--browser-output", str(BROWSER_OUTPUT),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": LEAGUE_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "agent-performance-league.out.log"),
        "StandardErrorPath": str(LOG_DIR / "agent-performance-league.err.log"),
    }
    tmp = LEAGUE_PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(LEAGUE_PLIST)
    domain = f"gui/{os.getuid()}"
    base._run(["launchctl", "bootout", domain, str(LEAGUE_PLIST)], check=False, capture=True)
    base._run(["launchctl", "bootstrap", domain, str(LEAGUE_PLIST)])
    base._run(["launchctl", "kickstart", "-k", f"{domain}/{LEAGUE_LABEL}"])


def _preview_health() -> dict:
    url = f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health"
    time.sleep(2.0)
    try:
        return base._json_url(url, attempts=80)
    except RuntimeError:
        domain = f"gui/{os.getuid()}"
        base._run(["launchctl", "kickstart", "-k", f"{domain}/{base.LABEL}"], check=False, capture=True)
        time.sleep(2.0)
        return base._json_url(url, attempts=80)


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("Batch 9S activation is intentionally macOS-only for this IIOS runtime")
    _configure_base()
    _cleanup_generated_cache()
    git = base._require_command("git")
    npm = base._require_command("npm")
    base._require_command("launchctl")

    print("IIOS BATCH 9S — AGENT PERFORMANCE LEAGUE ACTIVATION")
    print(f"Live IIOS checkout: {LIVE}")
    print("Parent Batch 9R: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print(f"Preview URL: http://{PREVIEW_HOST}:{PREVIEW_PORT}")
    print("League source: PERSISTED 9J OUTCOME MEMORY + 9G TELEMETRY")
    print(f"League refresh interval: {LEAGUE_INTERVAL_SECONDS} seconds")
    print("Automatic agent reweighting / model routing authority: NONE")
    print("Committee / Risk / capital authority: NONE")
    print("Trade execution permission: FALSE")
    print("Live execution: FALSE")

    protected_before = base._protected_hashes()
    parent_hashes_before = {key: _hash(path) for key, path in PARENT_PLISTS.items()}
    branch_before, status_before = base._prepare_worktree(git)
    python = base._resolve_python()
    _build_frontend(npm)

    backend_status = base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend_status.get("read_only_aggregation") is not True:
        raise SystemExit("Backend 8002 Factory Intelligence contract is not read-only")

    _publish_parent_artifacts(python)
    league = _publish_once(python)
    safety = league.get("safety") or {}
    for key in (
        "automatic_agent_weight_changes",
        "agent_weight_change_authority",
        "automatic_model_routing_changes",
        "model_routing_change_authority",
        "committee_change_authority",
        "risk_rule_change_authority",
        "capital_authority",
        "trade_execution_permission",
        "live_execution",
    ):
        if safety.get(key) is not False:
            raise SystemExit(f"Batch 9S safety contract violated: {key}")
    if safety.get("advisory_only") is not True or safety.get("human_approval_required") is not True:
        raise SystemExit("Batch 9S advisory/human approval contract missing")

    _install_league_agent(python)
    base._install_preview_agent(python)
    health = _preview_health()
    if health.get("backend_access") != "READ_ONLY_GET_ONLY" or health.get("live_execution") is not False:
        raise SystemExit("Batch 9S preview did not preserve read-only/no-execution boundary")

    if base._protected_hashes() != protected_before:
        raise SystemExit("Refusing Batch 9S activation: a protected 9G/9H/9I/9J LaunchAgent changed")
    if {key: _hash(path) for key, path in PARENT_PLISTS.items()} != parent_hashes_before:
        raise SystemExit("Refusing Batch 9S activation: one or more 9O/9P/9Q/9R LaunchAgents changed")
    if base._capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before:
        raise SystemExit("Live IIOS branch changed during Batch 9S activation")
    if base._capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS worktree changed during Batch 9S activation")

    opener = shutil.which("open")
    if opener:
        base._run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)

    summary = league.get("summary") or {}
    print(json.dumps({
        "status": "BATCH9S_AGENT_PERFORMANCE_LEAGUE_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "parent_9r_preserved": True,
        "backend_8002_unchanged": True,
        "protected_launch_agents_unchanged": True,
        "parent_9o_9p_9q_9r_launch_agents_unchanged": True,
        "league_launch_agent": LEAGUE_LABEL,
        "league_refresh_interval_seconds": LEAGUE_INTERVAL_SECONDS,
        "officially_ranked_count": summary.get("officially_ranked_count"),
        "provisional_count": summary.get("provisional_count"),
        "warm_up_count": summary.get("warm_up_count"),
        "ranked_model_count": summary.get("ranked_model_count"),
        "automatic_weight_changes": 0,
        "automatic_model_routing_changes": 0,
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
