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

BRANCH = "feature/batch10k-historical-macro-regime-library"
LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10k-historical-macro-regime-library")
HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
EVENT_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-event-reconstruction"
MACRO_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-macro-regime"
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
RUNTIME_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "runtime"
RUNTIME_FILE = RUNTIME_DIR / "iios_historical_macro_regime_runtime.py"
DIST = WORKTREE / "FRONT END" / "dist"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LABEL = "com.iios.historical-macro-regime-library"
PLIST = LAUNCH_DIR / f"{LABEL}.plist"
INTERVAL_SECONDS = 3600


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


def runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(WORKTREE / "scripts")
    return env


def install_runtime_file(git: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    content = run([git, "show", f"origin/{BRANCH}:scripts/iios_historical_macro_regime_runtime.py"], cwd=LIVE).stdout
    required = (
        "US_TREASURY_XML",
        "CBOE_VIX_HISTORY",
        "DIRECT_US_TREASURY_XML_PLUS_CBOE_VIX_VERIFIED_TLS",
        "--http1.1",
    )
    if not all(token in content for token in required):
        raise SystemExit("Fetched 10K runtime is missing the direct-source provider mesh contract")
    if "--insecure" in content:
        raise SystemExit("10K direct-source runtime may not disable TLS verification")
    RUNTIME_FILE.write_text(content, encoding="utf-8")


def run_bootstrap(python: Path) -> dict:
    run([
        str(python), str(RUNTIME_FILE),
        "--historical-dir", str(HISTORICAL_DIR),
        "--macro-dir", str(MACRO_DIR),
    ], cwd=WORKTREE, env=runtime_env())
    artifact = MACRO_DIR / "latest_historical_macro_regime_library.json"
    if not artifact.exists():
        raise SystemExit("10K direct-source repair did not produce the macro artifact")
    return json.loads(artifact.read_text(encoding="utf-8"))


def install_worker(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            str(python), str(RUNTIME_FILE),
            "--historical-dir", str(HISTORICAL_DIR),
            "--macro-dir", str(MACRO_DIR),
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(WORKTREE / "scripts"),
        },
        "StandardOutPath": str(LOG_DIR / "historical-macro-regime-library.out.log"),
        "StandardErrorPath": str(LOG_DIR / "historical-macro-regime-library.err.log"),
    }
    tmp = PLIST.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(PLIST)
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
        "--macro-dir", str(MACRO_DIR),
        "--browser-dir", str(DIST),
    ], cwd=WORKTREE)
    macro = json.loads((DIST / "historical_macro_regime_library.json").read_text(encoding="utf-8"))
    office = json.loads((DIST / "chief_intelligence_office_v2.json").read_text(encoding="utf-8"))
    return macro, office


def health() -> dict:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            with urlopen(Request("http://127.0.0.1:5176/health", headers={"Accept": "application/json"}), timeout=2) as response:
                value = json.loads(response.read().decode("utf-8"))
            if isinstance(value, dict):
                return value
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"10K preview health unavailable after direct-source repair: {last_error}")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("10K runtime repair is macOS-only")
    git = shutil.which("git")
    if not git:
        raise SystemExit("git not found")
    if not LIVE.exists() or not WORKTREE.exists():
        raise SystemExit("Expected IIOS live checkout and 10K worktree are required")
    run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    install_runtime_file(git)
    python = resolve_python()
    payload = run_bootstrap(python)
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("auto_generate_trades", "auto_change_thresholds", "auto_change_agent_weights", "auto_change_model_routing", "auto_change_portfolio_exposure", "provider_change_authority", "broker_connection_authority", "capital_authority", "trade_execution_permission", "live_execution"):
        if safety.get(key) is not False:
            raise SystemExit(f"10K safety contract violated after direct-source repair: {key}")
    install_worker(python)
    browser_macro, office = republish(python)
    browser_health = health()
    coverage = browser_macro.get("coverage") if isinstance(browser_macro.get("coverage"), dict) else {}
    summary = browser_macro.get("research_summary") if isinstance(browser_macro.get("research_summary"), dict) else {}
    diagnostics = browser_macro.get("provider_diagnostics") if isinstance(browser_macro.get("provider_diagnostics"), dict) else {}
    top = office.get("top_recommendation") if isinstance(office.get("top_recommendation"), dict) else {}
    print(json.dumps({
        "status": "BATCH10K_DIRECT_PROVIDER_RUNTIME_REPAIRED",
        "macro_status": browser_macro.get("status"),
        "tier_a_series_ready": coverage.get("tier_a_series_ready"),
        "tier_a_series_required_for_active": coverage.get("tier_a_series_required_for_active"),
        "tier_b_context_series_ready": coverage.get("tier_b_context_series_ready"),
        "normalized_symbols_ready": coverage.get("normalized_symbols_ready"),
        "provider_errors": summary.get("errors"),
        "provider_diagnostics": diagnostics,
        "10i_top_recommendation_after_repair": top.get("upgrade_id"),
        "10i_top_action_after_repair": top.get("action_class"),
        "transport": browser_macro.get("runtime_transport"),
        "worker": LABEL,
        "interval_seconds": INTERVAL_SECONDS,
        "preview_health": browser_health.get("status"),
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
