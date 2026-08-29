#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

BRANCH = "feature/batch10j-historical-event-reconstruction"
LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10j-historical-event-reconstruction")
HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
EVENT_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-event-reconstruction"
RUNTIME_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "runtime"
RUNTIME_FILE = RUNTIME_DIR / "iios_historical_event_reconstruction_runtime.py"
DIST = WORKTREE / "FRONT END" / "dist"
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LABEL = "com.iios.historical-event-reconstruction"
PLIST = LAUNCH_DIR / f"{LABEL}.plist"
INTERVAL_SECONDS = 1800


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False, env=env)
    if check and result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed")[:4000])
    return result


def resolve_python() -> Path:
    preferred = LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python"
    if preferred.exists() and os.access(preferred, os.X_OK):
        return preferred
    return Path(sys.executable)


def install_runtime_file(git: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    content = run([git, "show", f"origin/{BRANCH}:scripts/iios_historical_event_reconstruction_runtime.py"], cwd=LIVE).stdout
    if "DOC_SEARCH_START = date(2017, 1, 1)" not in content:
        raise SystemExit("Fetched 10J runtime does not contain the corrected DOC coverage contract")
    RUNTIME_FILE.write_text(content, encoding="utf-8")


def runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(WORKTREE / "scripts")
    return env


def run_bootstrap(python: Path) -> dict:
    run([
        str(python), str(RUNTIME_FILE),
        "--historical-dir", str(HISTORICAL_DIR),
        "--event-dir", str(EVENT_DIR),
        "--symbols-per-cycle", "4",
    ], cwd=WORKTREE, env=runtime_env())
    artifact = EVENT_DIR / "latest_historical_event_reconstruction.json"
    return json.loads(artifact.read_text(encoding="utf-8"))


def install_worker(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            str(python), str(RUNTIME_FILE),
            "--historical-dir", str(HISTORICAL_DIR),
            "--event-dir", str(EVENT_DIR),
            "--symbols-per-cycle", "1",
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(WORKTREE / "scripts"),
        },
        "StandardOutPath": str(LOG_DIR / "historical-event-reconstruction.out.log"),
        "StandardErrorPath": str(LOG_DIR / "historical-event-reconstruction.err.log"),
    }
    temp = PLIST.with_suffix(".tmp.plist")
    with temp.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temp.replace(PLIST)
    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", domain, str(PLIST)], check=False)
    run(["launchctl", "bootstrap", domain, str(PLIST)])
    run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"])


def republish(python: Path) -> tuple[dict, dict]:
    publisher = WORKTREE / "scripts" / "iios_final_institutional_publisher.py"
    run([
        str(python), str(publisher),
        "--state-dir", str(STATE_DIR),
        "--telemetry-dir", str(TELEMETRY_DIR),
        "--historical-dir", str(HISTORICAL_DIR),
        "--event-dir", str(EVENT_DIR),
        "--browser-dir", str(DIST),
    ], cwd=WORKTREE)
    event = json.loads((DIST / "historical_event_reconstruction.json").read_text(encoding="utf-8"))
    office = json.loads((DIST / "chief_intelligence_office_v2.json").read_text(encoding="utf-8"))
    return event, office


def health() -> dict:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            with urlopen(Request("http://127.0.0.1:5176/health", headers={"Accept": "application/json"}), timeout=2) as response:
                value = json.loads(response.read().decode("utf-8"))
            if isinstance(value, dict):
                return value
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"preview health unavailable after 10J runtime repair: {last_error}")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("10J runtime repair is macOS-only")
    git = shutil.which("git")
    if not git:
        raise SystemExit("git not found")
    if not LIVE.exists() or not WORKTREE.exists():
        raise SystemExit("Expected IIOS live checkout and 10J worktree are required")
    run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    install_runtime_file(git)
    python = resolve_python()
    payload = run_bootstrap(python)
    install_worker(python)
    browser_event, office = republish(python)
    browser_health = health()
    summary = browser_event.get("research_summary") if isinstance(browser_event.get("research_summary"), dict) else {}
    top = office.get("top_recommendation") if isinstance(office.get("top_recommendation"), dict) else {}
    print(json.dumps({
        "status": "BATCH10J_EVENT_RUNTIME_REPAIRED",
        "event_status": browser_event.get("status"),
        "symbols_ready": summary.get("symbols_ready"),
        "current_contexts_ready": summary.get("current_contexts_ready"),
        "analog_contexts_ready": summary.get("analog_contexts_ready"),
        "10i_top_recommendation_after_repair": top.get("upgrade_id"),
        "10i_top_action_after_repair": top.get("action_class"),
        "worker": LABEL,
        "interval_seconds": INTERVAL_SECONDS,
        "doc_search_start": "2017-01-01",
        "current_windows_capped_at_now": True,
        "event_analog_selection": "PREFER_POST_2017_FROM_FULL_10H_ANALOG_SET",
        "preview_health": browser_health.get("status"),
        "causal_claim_authority": False,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
