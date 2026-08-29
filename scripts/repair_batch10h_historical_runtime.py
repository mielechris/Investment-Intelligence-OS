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

BRANCH = "feature/batch10h-historical-market-intelligence"
LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10h-historical-market-intelligence")
STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
HISTORICAL_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"
DIST = WORKTREE / "FRONT END" / "dist"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"
LABEL = "com.iios.historical-market-intelligence"
PLIST = LAUNCH_DIR / f"{LABEL}.plist"
INTERVAL_SECONDS = 900
GENERATED_PREFIXES = ("FRONT END/dist/", "scripts/__pycache__/")


def run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed")[:3000])
    return result


def _dirty_paths(status_text: str) -> list[str]:
    paths: list[str] = []
    for raw in status_text.splitlines():
        if len(raw) < 4:
            continue
        path = raw[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def _is_generated(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized == "FRONT END/dist" or normalized == "scripts/__pycache__" or any(normalized.startswith(prefix) for prefix in GENERATED_PREFIXES)


def ensure_worktree() -> None:
    git = shutil.which("git")
    if not git:
        raise SystemExit("git not found")
    run([git, "fetch", "origin", BRANCH], cwd=LIVE)
    remote = f"origin/{BRANCH}"
    if WORKTREE.exists():
        status = run([git, "status", "--porcelain"], cwd=WORKTREE).stdout.strip()
        dirty = _dirty_paths(status)
        unsafe = [path for path in dirty if not _is_generated(path)]
        if unsafe:
            raise SystemExit(
                "10H worktree has non-generated local changes; refusing runtime repair: "
                + ", ".join(unsafe[:12])
            )
        if dirty:
            # 10H deliberately republishes browser artifacts into dist. Those files are
            # runtime products, not source edits. Clean only those known generated paths.
            run([git, "restore", "--staged", "--worktree", "--", "FRONT END/dist", "scripts/__pycache__"], cwd=WORKTREE, check=False)
            run([git, "clean", "-fd", "--", "FRONT END/dist", "scripts/__pycache__"], cwd=WORKTREE, check=False)
        run([git, "reset", "--hard", remote], cwd=WORKTREE)
    else:
        run([git, "worktree", "add", "--detach", str(WORKTREE), remote], cwd=LIVE)


def resolve_python() -> Path:
    preferred = LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python"
    if preferred.exists() and os.access(preferred, os.X_OK):
        return preferred
    return Path(sys.executable)


def install_worker(python: Path) -> None:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(WORKTREE / "scripts" / "iios_historical_market_intelligence_runtime.py"),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--research-dir", str(HISTORICAL_DIR),
            "--targets-per-cycle", "3",
        ],
        "WorkingDirectory": str(WORKTREE),
        "RunAtLoad": True,
        "StartInterval": INTERVAL_SECONDS,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "historical-market-intelligence.out.log"),
        "StandardErrorPath": str(LOG_DIR / "historical-market-intelligence.err.log"),
    }
    temp = PLIST.with_suffix(".tmp.plist")
    with temp.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    temp.replace(PLIST)
    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", domain, str(PLIST)], check=False)
    run(["launchctl", "bootstrap", domain, str(PLIST)])
    run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"])


def run_bootstrap(python: Path) -> dict:
    run(
        [
            str(python),
            str(WORKTREE / "scripts" / "iios_historical_market_intelligence_runtime.py"),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--research-dir", str(HISTORICAL_DIR),
            "--targets-per-cycle", "9",
        ],
        cwd=WORKTREE,
    )
    path = HISTORICAL_DIR / "latest_historical_market_intelligence.json"
    return json.loads(path.read_text(encoding="utf-8"))


def republish(python: Path) -> None:
    publisher = WORKTREE / "scripts" / "iios_final_institutional_publisher.py"
    run(
        [
            str(python), str(publisher),
            "--state-dir", str(STATE_DIR),
            "--telemetry-dir", str(TELEMETRY_DIR),
            "--historical-dir", str(HISTORICAL_DIR),
            "--browser-dir", str(DIST),
        ],
        cwd=WORKTREE,
    )


def health() -> dict:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            with urlopen(Request("http://127.0.0.1:5176/health", headers={"Accept":"application/json"}), timeout=2) as response:
                value = json.loads(response.read().decode("utf-8"))
            if isinstance(value, dict):
                return value
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"preview health unavailable after repair: {last_error}")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("10H runtime repair is macOS-only")
    ensure_worktree()
    python = resolve_python()
    payload = run_bootstrap(python)
    install_worker(python)
    republish(python)
    browser_health = health()
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), list) else []
    studies = payload.get("studies") if isinstance(payload.get("studies"), list) else []
    summary = payload.get("research_summary") if isinstance(payload.get("research_summary"), dict) else {}
    compact = []
    by_symbol = {str(row.get("symbol")): row for row in studies if isinstance(row, dict)}
    for row in coverage:
        if not isinstance(row, dict):
            continue
        study = by_symbol.get(str(row.get("symbol")), {})
        compact.append({
            "symbol": row.get("symbol"),
            "provider": row.get("provider"),
            "rows": row.get("row_count"),
            "start": row.get("start_date"),
            "end": row.get("end_date"),
            "coverage": row.get("coverage_quality"),
            "study": study.get("status"),
            "analogs": study.get("analog_count"),
            "error": row.get("error"),
        })
    print(json.dumps({
        "status": "BATCH10H_HISTORICAL_RUNTIME_REPAIRED",
        "historical_status": payload.get("status"),
        "studies_ready": summary.get("studies_ready"),
        "coverage_records": summary.get("coverage_records"),
        "worker": LABEL,
        "interval_seconds": INTERVAL_SECONDS,
        "tls_policy": "MACOS_SYSTEM_TRUST_VERIFIED_NO_INSECURE_FLAG",
        "preview_health": browser_health.get("status"),
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "coverage": compact,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
