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

BRANCH = "feature/batch10l-10m-measurement-health-superbatch"
LIVE = Path(os.getenv("IIOS_LIVE_CHECKOUT", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")).expanduser()
WORKTREE = Path(os.getenv("IIOS_10LM_WORKTREE", "/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10l-10m-measurement-health-superbatch")).expanduser()
FRONTEND = WORKTREE / "FRONT END"
DIST = FRONTEND / "dist"
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
EVENT_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-event-reconstruction"
MACRO_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-macro-regime"
BENCHMARK_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "benchmark-alpha"
HEALTH_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "browser-health"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 5176
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
BENCHMARK_LABEL = "com.iios.benchmark-alpha-attribution"
HEALTH_LABEL = "com.iios.data-health-watchdog"
FINAL_LABEL = "com.iios.institutional-browser-artifacts"
BENCHMARK_INTERVAL = 3600
HEALTH_INTERVAL = 300
FINAL_INTERVAL = 300
PRESERVED = {
    "9O": LAUNCH_DIR / "com.iios.daily-factory-episode.plist",
    "9P": LAUNCH_DIR / "com.iios.chief-intelligence-office.plist",
    "9Q": LAUNCH_DIR / "com.iios.experiment-ab-laboratory.plist",
    "9R": LAUNCH_DIR / "com.iios.data-expansion-factory.plist",
    "9S": LAUNCH_DIR / "com.iios.agent-performance-league.plist",
    "10H": LAUNCH_DIR / "com.iios.historical-market-intelligence.plist",
    "10J": LAUNCH_DIR / "com.iios.historical-event-reconstruction.plist",
    "10K": LAUNCH_DIR / "com.iios.historical-macro-regime-library.plist",
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
        raise SystemExit("10L-10M worktree has non-generated local changes; refusing activation:\n" + "\n".join(unexpected[:20]))
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
        raise SystemExit("Live IIOS checkout changed while preparing 10L-10M")
    return branch_before, status_before


def build_frontend(npm: str) -> None:
    run([npm, "ci"], cwd=FRONTEND)
    run([npm, "exec", "eslint", "--", "src/LiveFactoryBrowser.tsx", "src/MeasurementHealthSuperbatch.tsx"], cwd=FRONTEND)
    run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST / "index.html").exists(): raise SystemExit("10L-10M frontend build missing dist/index.html")


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
    if sys.platform != "darwin": raise SystemExit("10L-10M activation is macOS-only")
    configure_base()
    git = base._require_command("git"); npm = base._require_command("npm"); base._require_command("launchctl")
    print("IIOS BATCH 10L–10M — MEASUREMENT + DATA HEALTH SUPERBATCH")
    print("10L benchmark attribution: MEASUREMENT ONLY")
    print("10M data health watchdog: OBSERVABILITY ONLY")
    print("10K/10J/10H/10G: PRESERVED")
    print("Backend 8002: UNCHANGED")
    print("Live execution: FALSE")

    protected = base._protected_hashes()
    preserved = {key: base._hash(path) for key, path in PRESERVED.items()}
    branch_before, status_before = prepare_worktree(git)
    python = base._resolve_python()
    build_frontend(npm)
    backend = base._json_url("http://127.0.0.1:8002/experience/factory-intelligence/status", attempts=4)
    if backend.get("read_only_aggregation") is not True: raise SystemExit("Backend 8002 is not read-only")

    benchmark_program = [str(python), str(WORKTREE / "scripts" / "iios_benchmark_alpha_attribution.py"), "--telemetry-dir", str(TELEMETRY_DIR), "--research-dir", str(HISTORICAL_DIR), "--benchmark-dir", str(BENCHMARK_DIR)]
    health_program = [str(python), str(WORKTREE / "scripts" / "iios_data_health_watchdog.py"), "--state-dir", str(STATE_DIR), "--telemetry-dir", str(TELEMETRY_DIR), "--historical-dir", str(HISTORICAL_DIR), "--event-dir", str(EVENT_DIR), "--macro-dir", str(MACRO_DIR), "--benchmark-dir", str(BENCHMARK_DIR), "--browser-dir", str(DIST)]
    final_program = [str(python), str(WORKTREE / "scripts" / "iios_measurement_health_publisher.py"), "--state-dir", str(STATE_DIR), "--telemetry-dir", str(TELEMETRY_DIR), "--historical-dir", str(HISTORICAL_DIR), "--event-dir", str(EVENT_DIR), "--macro-dir", str(MACRO_DIR), "--benchmark-dir", str(BENCHMARK_DIR), "--health-dir", str(HEALTH_DIR), "--browser-dir", str(DIST)]

    run(benchmark_program, cwd=WORKTREE)
    install_plist(BENCHMARK_LABEL, benchmark_program, BENCHMARK_INTERVAL, "benchmark-alpha-attribution")
    install_plist(HEALTH_LABEL, health_program, HEALTH_INTERVAL, "data-health-watchdog")
    install_plist(FINAL_LABEL, final_program, FINAL_INTERVAL, "institutional-browser-artifacts")
    run(final_program, cwd=WORKTREE)

    benchmark = json.loads((DIST / "benchmark_alpha_attribution.json").read_text(encoding="utf-8"))
    health = json.loads((DIST / "data_health_watchdog.json").read_text(encoding="utf-8"))
    office = json.loads((DIST / "chief_intelligence_office_v2.json").read_text(encoding="utf-8"))
    health_check = restart_preview(python)
    if health_check.get("backend_access") != "READ_ONLY_GET_ONLY" or health_check.get("live_execution") is not False: raise SystemExit("10L-10M preview safety boundary failed")
    if base._protected_hashes() != protected: raise SystemExit("Protected 9G–9J worker changed")
    if {key: base._hash(path) for key, path in PRESERVED.items()} != preserved: raise SystemExit("Preserved 9O–10K worker changed")
    if capture([git, "branch", "--show-current"], cwd=LIVE) != branch_before or capture([git, "status", "--porcelain"], cwd=LIVE) != status_before: raise SystemExit("Live checkout changed during 10L-10M")

    top = office.get("top_recommendation") if isinstance(office.get("top_recommendation"), dict) else {}
    b_safety = benchmark.get("safety") if isinstance(benchmark.get("safety"), dict) else {}
    h_safety = health.get("safety") if isinstance(health.get("safety"), dict) else {}
    for payload, keys in ((b_safety, ("capital_authority", "broker_connection_authority", "trade_execution_permission", "live_execution")), (h_safety, ("capital_authority", "trade_execution_permission", "live_execution"))):
        for key in keys:
            if payload.get(key) is not False: raise SystemExit(f"10L-10M safety violation: {key}")

    opener = shutil.which("open")
    if opener: run([opener, f"http://{PREVIEW_HOST}:{PREVIEW_PORT}"], check=False)
    print(json.dumps({
        "status": "BATCH10L_10M_MEASUREMENT_HEALTH_PREVIEW",
        "preview_url": f"http://{PREVIEW_HOST}:{PREVIEW_PORT}",
        "benchmark_status": benchmark.get("status"),
        "benchmark_contract_ready": benchmark.get("measurement_contract_ready"),
        "data_health_status": health.get("status"),
        "data_health_chain": health.get("health_chain"),
        "data_health_issues": len(health.get("issues") or []),
        "10i_top_recommendation_after_10lm": top.get("upgrade_id"),
        "10i_top_action_after_10lm": top.get("action_class"),
        "benchmark_worker": BENCHMARK_LABEL,
        "health_worker": HEALTH_LABEL,
        "10k_worker_preserved": True,
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


if __name__ == "__main__":
    raise SystemExit(main())
