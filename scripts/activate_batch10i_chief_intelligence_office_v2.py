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

BRANCH = "feature/batch10i-chief-intelligence-office-v2"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_10I_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10i-chief-intelligence-office-v2")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
FINAL_LABEL = "com.iios.institutional-browser-artifacts"
FINAL_INTERVAL_SECONDS = 300
FINAL_PLIST = LAUNCH_DIR / f"{FINAL_LABEL}.plist"
PRESERVED_PLISTS = {
    "9O": LAUNCH_DIR / "com.iios.daily-factory-episode.plist",
    "9P": LAUNCH_DIR / "com.iios.chief-intelligence-office.plist",
    "9Q": LAUNCH_DIR / "com.iios.experiment-ab-laboratory.plist",
    "9R": LAUNCH_DIR / "com.iios.data-expansion-factory.plist",
    "9S": LAUNCH_DIR / "com.iios.agent-performance-league.plist",
    "10H": LAUNCH_DIR / "com.iios.historical-market-intelligence.plist",
}


def _run(args: list[str], *, cwd: Path | None = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=capture, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args[:8])}\n{detail[:3000]}")
    return result


def _capture(args: list[str], *, cwd: Path | None = None) -> str:
    return _run(args, cwd=cwd, capture=True).stdout.strip()


def _configure_base() -> None:
    base.BRANCH = BRANCH
    base.LIVE = LIVE
    base.WORKTREE = WORKTREE
    base.FRONTEND = FRONTEND
    base.DIST = DIST
    base.PREVIEW_HOST = PREVIEW_HOST
    base.PREVIEW_PORT = PREVIEW_PORT


def _clean_generated(git: str) -> None:
    if not WORKTREE.exists():
        return
    status = _capture([git, "status", "--porcelain"], cwd=WORKTREE)
    if not status:
        return
    allowed = ("FRONT END/dist/", "scripts/__pycache__/")
    unexpected: list[str] = []
    for line in status.splitlines():
        path = line[3:].strip().strip('"') if len(line) >= 4 else ""
        if not any(path.startswith(prefix) for prefix in allowed):
            unexpected.append(line)
    if unexpected:
        raise SystemExit("10I worktree has non-generated local changes; refusing activation:\n" + "\n".join(unexpected[:20]))
    _run([git, "restore", "--worktree", "--staged", "--", "FRONT END/dist"], cwd=WORKTREE, check=False)
    _run([git, "clean", "-fd", "--", "FRONT END/dist", "scripts/__pycache__"], cwd=WORKTREE, check=False)


def _prepare_worktree(git: str) -> tuple[str, str]:
    if not LIVE.exists():
        raise SystemExit(f"Live IIOS checkout not found: {LIVE}")
    branch_before = _capture([git, "branch", "--show-current"], cwd=LIVE)
    status_before = _capture([git, "status", "--porcelain"], cwd=LIVE)
    _run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    remote = f"origin/{BRANCH}"
    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"10I path exists but is not a git worktree: {WORKTREE}")
        _clean_generated(git)
        _run([git, "fetch", "origin", BRANCH], cwd=WORKTREE)
        _run([git, "reset", "--hard", remote], cwd=WORKTREE)
    else:
        _run([git, "worktree", "add", "--detach", str(WORKTREE), remote], cwd=LIVE)
    if _capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before or _capture([git, "status", "--porcelain"], cwd=LIVE) != status_before:
        raise SystemExit("Live IIOS checkout changed while preparing 10I")
    return branch_before, status_before


def _build(npm: str) -> None:
    _run([npm, "ci"], cwd=FRONTEND)
    _run([npm, "exec", "eslint", "--", "src/LiveFactoryBrowser.tsx", "src/ChiefIntelligenceOfficeV2.tsx", "src/HistoricalMarketIntelligence.tsx", "src/QualificationWatch.tsx"], cwd=FRONTEND)
    _run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists():
        raise SystemExit("10I frontend build did not produce dist/index.html")


def _publish(python: Path) -> dict:
    _run([
        str(python), str(WORKTREE / "scripts" / "iios_final_institutional_publisher.py"),
        "--state-dir", str(STATE_DIR),
        "--telemetry-dir", str(TELEMETRY_DIR),
        "--historical-dir", str(HISTORICAL_DIR),
        "--browser-dir", str(DIST),
    ], cwd=WORKTREE)
    return json.loads((DIST / "chief_intelligence_office_v2.json").read_text(encoding="utf-8"))


def _install_final_publisher(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True); LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": FINAL_LABEL,
        "ProgramArguments": [
            str(python), str(WORKTREE / "scripts" / "iios_final_institutional_publisher.py"),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--historical-dir", str(HISTORICAL_DIR),
            "--browser-dir", str(DIST),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": FINAL_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "institutional-browser-artifacts.out.log"),
        "StandardErrorPath": str(LOG_DIR / "institutional-browser-artifacts.err.log"),
    }
    tmp = FINAL_PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle: plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(FINAL_PLIST)
    domain = f"gui/{os.getuid()}"
    _run(["launchctl", "bootout", domain, str(FINAL_PLIST)], check=False, capture=True)
    _run(["launchctl", "bootstrap", domain, str(FINAL_PLIST)])
    _run(["launchctl", "kickstart", "-k", f"{domain}/{FINAL_LABEL}"])


def _port_open() -> bool:
    try:
        with socket.create_connection((PREVIEW_HOST, PREVIEW_PORT), timeout=0.25):
            return True
    except OSError:
        return False


def _restart_preview(python: Path) -> dict:
    domain = f"gui/{os.getuid()}"
    _run(["launchctl", "bootout", domain, str(base.PLIST)], check=False, capture=True)
    for _ in range(20):
        if not _port_open(): break
        time.sleep(0.25)
    base._install_preview_agent(python)
    try:
        return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health", attempts=60)
    except RuntimeError:
        time.sleep(1.5)
        base._install_preview_agent(python)
        return base._json_url(f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/health", attempts=80)


def main() -> int:
    if sys.platform != "darwin": raise SystemExit("10I activation is macOS-only for this IIOS runtime")
    _configure_base()
    git = base._require_command("git"); npm = base._require_command("npm"); base._require_command("launchctl")
    print("IIOS BATCH 10I — CHIEF INTELLIGENCE OFFICE V2 ACTIVATION")
    print("10H 24/7 historical research: PRESERVED")
    print("10G qualification campaign: PRESERVED")
    print("Existing Backend 8002: UNCHANGED")
    print("10I authority: WHOLE-STACK ADVISORY ONLY")
    print("Live execution: FALSE")
    protected = base._protected_hashes()
    preserved = {key: base._hash(path) for key, path in PRESERVED_PLISTS.items()}
    branch_before, status_before = _prepare_worktree(git)
    python = base._resolve_python()
    _build(npm)
    backend = base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend.get("read_only_aggregation") is not True: raise SystemExit("Backend 8002 is not read-only")
    office = _publish(python)
    safety = office.get("safety") if isinstance(office.get("safety"), dict) else {}
    for key in ("auto_apply_recommendations", "auto_change_thresholds", "auto_change_agent_weights", "auto_change_model_routing", "provider_change_authority", "broker_connection_authority", "capital_authority", "trade_execution_permission", "live_execution"):
        if safety.get(key) is not False: raise SystemExit(f"10I safety contract violated: {key}")
    if safety.get("advisory_only") is not True or safety.get("human_approval_required") is not True: raise SystemExit("10I advisory/human gate missing")
    _install_final_publisher(python)
    health = _restart_preview(python)
    if health.get("backend_access") != "READ_ONLY_GET_ONLY" or health.get("live_execution") is not False: raise SystemExit("10I preview safety boundary failed")
    if base._protected_hashes() != protected: raise SystemExit("Protected 9G–9J worker changed")
    if {key: base._hash(path) for key, path in PRESERVED_PLISTS.items()} != preserved: raise SystemExit("A preserved 9O–9S or 10H worker changed")
    if _capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before or _capture([git, "status", "--porcelain"], cwd=LIVE) != status_before: raise SystemExit("Live checkout changed during 10I activation")
    opener = shutil.which("open")
    if opener: _run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)
    top = office.get("top_recommendation") if isinstance(office.get("top_recommendation"), dict) else {}
    print(json.dumps({
        "status": "BATCH10I_CHIEF_INTELLIGENCE_OFFICE_V2_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "office_status": office.get("status"),
        "whole_stack_inputs_observed": office.get("whole_stack_inputs_observed"),
        "whole_stack_input_count": office.get("whole_stack_input_count"),
        "top_recommendation": top.get("upgrade_id"),
        "top_action_class": top.get("action_class"),
        "10h_worker_preserved": True,
        "10g_qualification_preserved": True,
        "backend_8002_unchanged": True,
        "protected_9g_9j_workers_unchanged": True,
        "capital_authority": False,
        "trade_execution_permission": False,
        "broker_connected": False,
        "live_execution": False,
        "worktree": str(WORKTREE),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
