#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import activate_batch9k_live_factory_browser as base

BRANCH = "feature/batch10k-historical-macro-regime-library"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_10K_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10k-historical-macro-regime-library")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
EVENT_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-event-reconstruction"
MACRO_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-macro-regime"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
MACRO_LABEL = "com.iios.historical-macro-regime-library"
MACRO_INTERVAL_SECONDS = 3600
FINAL_LABEL = "com.iios.institutional-browser-artifacts"
FINAL_INTERVAL_SECONDS = 300
PRESERVED_PLISTS = {
    "9O": LAUNCH_DIR / "com.iios.daily-factory-episode.plist",
    "9P": LAUNCH_DIR / "com.iios.chief-intelligence-office.plist",
    "9Q": LAUNCH_DIR / "com.iios.experiment-ab-laboratory.plist",
    "9R": LAUNCH_DIR / "com.iios.data-expansion-factory.plist",
    "9S": LAUNCH_DIR / "com.iios.agent-performance-league.plist",
    "10H": LAUNCH_DIR / "com.iios.historical-market-intelligence.plist",
    "10J": LAUNCH_DIR / "com.iios.historical-event-reconstruction.plist",
}


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=capture, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args[:8])}\n{detail[:3000]}")
    return result


def capture(args: list[str], *, cwd: Path | None = None) -> str:
    return run(args, cwd=cwd, capture=True).stdout.strip()


def configure_base() -> None:
    base.BRANCH = BRANCH
    base.LIVE = LIVE
    base.WORKTREE = WORKTREE
    base.FRONTEND = FRONTEND
    base.DIST = DIST
    base.PREVIEW_HOST = PREVIEW_HOST
    base.PREVIEW_PORT = PREVIEW_PORT


def clean_generated(git: str) -> None:
    if not WORKTREE.exists(): return
    status = capture([git, "status", "--porcelain"], cwd=WORKTREE)
    if not status: return
    allowed = ("FRONT END/dist/", "scripts/__pycache__/")
    unexpected = []
    for line in status.splitlines():
        path = line[3:].strip().strip('"') if len(line) >= 4 else ""
        if not any(path.startswith(prefix) for prefix in allowed): unexpected.append(line)
    if unexpected:
        raise SystemExit("10K worktree has non-generated local changes; refusing activation:\n" + "\n".join(unexpected[:20]))
    run([git, "restore", "--worktree", "--staged", "--", "FRONT END/dist"], cwd=WORKTREE, check=False)
    run([git, "clean", "-fd", "--", "FRONT END/dist", "scripts/__pycache__"], cwd=WORKTREE, check=False)


def prepare_worktree(git: str) -> tuple[str, str]:
    branch_before = capture([git, "branch", "--show-current"], cwd=LIVE)
    status_before = capture([git, "status", "--porcelain"], cwd=LIVE)
    run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    remote = f"origin/{BRANCH}"
    if WORKTREE.exists():
        clean_generated(git)
        run([git, "fetch", "origin", BRANCH], cwd=WORKTREE)
        run([git, "reset", "--hard", remote], cwd=WORKTREE)
    else:
        run([git, "worktree", "add", "--detach", str(WORKTREE), remote], cwd=LIVE)
    if capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before or capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS checkout changed while preparing 10K")
    return branch_before, status_before


def build_frontend(npm: str) -> None:
    run([npm, "ci"], cwd=FRONTEND)
    run([npm, "exec", "eslint", "--", "src/LiveFactoryBrowser.tsx", "src/HistoricalMacroRegimeLibrary.tsx", "src/HistoricalEventReconstruction.tsx", "src/ChiefIntelligenceOfficeV2.tsx"], cwd=FRONTEND)
    run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists(): raise SystemExit("10K frontend build missing dist/index.html")


def install_plist(label: str, program: list[str], interval: int, log_name: str) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True); LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LAUNCH_DIR / f"{label}.plist"
    payload = {"Label": label, "ProgramArguments": program, "WorkingDirectory": str(WORKTREE), "RunAtLoad": True, "StartInterval": interval, "ProcessType": "Background", "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"}, "StandardOutPath": str(LOG_DIR / f"{log_name}.out.log"), "StandardErrorPath": str(LOG_DIR / f"{log_name}.err.log")}
    tmp = path.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle: plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(path)
    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", domain, str(path)], check=False, capture=True)
    run(["launchctl", "bootstrap", domain, str(path)])
    run(["launchctl", "kickstart", "-k", f"{domain}/{label}"])


def run_macro(python: Path) -> dict:
    run([str(python), str(WORKTREE / "scripts" / "iios_historical_macro_regime_library.py"), "--historical-dir", str(HISTORICAL_DIR), "--macro-dir", str(MACRO_DIR)], cwd=WORKTREE)
    artifact = MACRO_DIR / "latest_historical_macro_regime_library.json"
    if not artifact.exists(): raise SystemExit("10K macro artifact not produced")
    return json.loads(artifact.read_text(encoding="utf-8"))


def publish(python: Path) -> tuple[dict, dict]:
    run([str(python), str(WORKTREE / "scripts" / "iios_final_institutional_publisher.py"), "--state-dir", str(STATE_DIR), "--telemetry-dir", str(TELEMETRY_DIR), "--historical-dir", str(HISTORICAL_DIR), "--event-dir", str(EVENT_DIR), "--macro-dir", str(MACRO_DIR), "--browser-dir", str(DIST)], cwd=WORKTREE)
    macro = json.loads((DIST / "historical_macro_regime_library.json").read_text(encoding="utf-8"))
    office = json.loads((DIST / "chief_intelligence_office_v2.json").read_text(encoding="utf-8"))
    return macro, office


def port_open() -> bool:
    try:
        with socket.create_connection((PREVIEW_HOST, PREVIEW_PORT), timeout=0.25): return True
    except OSError: return False


def restart_preview(python: Path) -> dict:
    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", domain, str(base.PLIST)], check=False, capture=True)
    for _ in range(20):
        if not port_open(): break
        time.sleep(0.25)
    base._install_preview_agent(python)
    try:
        return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health", attempts=60)
    except RuntimeError:
        time.sleep(1.5); base._install_preview_agent(python)
        return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health", attempts=80)


def main() -> int:
    if sys.platform != "darwin": raise SystemExit("10K activation is macOS-only")
    configure_base()
    git = base._require_command("git"); npm = base._require_command("npm"); base._require_command("launchctl")
    print("IIOS BATCH 10K — HISTORICAL MACRO + REGIME NORMALIZATION")
    print("10J event reconstruction: PRESERVED")
    print("10H historical research: PRESERVED")
    print("10G qualification: PRESERVED")
    print("Backend 8002: UNCHANGED")
    print("Tier B revised macro history: CONTEXT ONLY")
    print("Live execution: FALSE")
    protected = base._protected_hashes()
    preserved = {key: base._hash(path) for key, path in PRESERVED_PLISTS.items()}
    branch_before, status_before = prepare_worktree(git)
    python = base._resolve_python()
    build_frontend(npm)
    backend = base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend.get("read_only_aggregation") is not True: raise SystemExit("Backend 8002 is not read-only")
    macro = run_macro(python)
    safety = macro.get("safety") if isinstance(macro.get("safety"), dict) else {}
    for key in ("auto_generate_trades", "auto_change_thresholds", "auto_change_agent_weights", "auto_change_model_routing", "auto_change_portfolio_exposure", "provider_change_authority", "broker_connection_authority", "capital_authority", "trade_execution_permission", "live_execution"):
        if safety.get(key) is not False: raise SystemExit(f"10K safety violation: {key}")
    if safety.get("read_only_research") is not True or safety.get("advisory_only") is not True: raise SystemExit("10K read-only advisory contract missing")
    install_plist(MACRO_LABEL, [str(python), str(WORKTREE / "scripts" / "iios_historical_macro_regime_library.py"), "--historical-dir", str(HISTORICAL_DIR), "--macro-dir", str(MACRO_DIR)], MACRO_INTERVAL_SECONDS, "historical-macro-regime-library")
    install_plist(FINAL_LABEL, [str(python), str(WORKTREE / "scripts" / "iios_final_institutional_publisher.py"), "--state-dir", str(STATE_DIR), "--telemetry-dir", str(TELEMETRY_DIR), "--historical-dir", str(HISTORICAL_DIR), "--event-dir", str(EVENT_DIR), "--macro-dir", str(MACRO_DIR), "--browser-dir", str(DIST)], FINAL_INTERVAL_SECONDS, "institutional-browser-artifacts")
    browser_macro, office = publish(python)
    health = restart_preview(python)
    if health.get("backend_access") != "READ_ONLY_GET_ONLY" or health.get("live_execution") is not False: raise SystemExit("10K preview safety boundary failed")
    if base._protected_hashes() != protected: raise SystemExit("Protected 9G–9J worker changed")
    if {key: base._hash(path) for key, path in PRESERVED_PLISTS.items()} != preserved: raise SystemExit("Preserved historical/self-improvement worker changed")
    if capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before or capture([git, "status", "--porcelain"], cwd=LIVE) != status_before: raise SystemExit("Live checkout changed during 10K")
    opener = shutil.which("open")
    if opener: run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)
    cov = browser_macro.get("coverage") if isinstance(browser_macro.get("coverage"), dict) else {}
    top = office.get("top_recommendation") if isinstance(office.get("top_recommendation"), dict) else {}
    print(json.dumps({
        "status": "BATCH10K_HISTORICAL_MACRO_REGIME_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "macro_status": browser_macro.get("status"),
        "tier_a_series_ready": cov.get("tier_a_series_ready"),
        "tier_b_context_series_ready": cov.get("tier_b_context_series_ready"),
        "normalized_symbols_ready": cov.get("normalized_symbols_ready"),
        "10i_top_recommendation_after_10k": top.get("upgrade_id"),
        "10i_top_action_after_10k": top.get("action_class"),
        "macro_worker": MACRO_LABEL,
        "macro_interval_seconds": MACRO_INTERVAL_SECONDS,
        "10j_worker_preserved": True,
        "10h_worker_preserved": True,
        "10g_qualification_preserved": True,
        "backend_8002_unchanged": True,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "worktree": str(WORKTREE),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
