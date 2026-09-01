#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "iios_batch10m7_nightly_market_reconstruction.json"
LABEL = "com.iios.nightly-market-reconstruction"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "IIOS"


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "command failed")[:4000])
    return result


def resolve_python(config: dict[str, Any]) -> Path:
    for candidate in config.get("backend_python_candidates") or []:
        path = expand(str(candidate))
        if path.exists() and os.access(path, os.X_OK):
            return path
    raise SystemExit("No executable IIOS backend Python found")


def ensure_worktree(live: Path, path: Path, branch: str, required_file: str) -> dict[str, Any]:
    git = shutil.which("git")
    if not git:
        raise SystemExit("git not found")
    run([git, "fetch", "origin", branch], cwd=live)
    remote = f"origin/{branch}"
    if not path.exists():
        run([git, "worktree", "add", "--detach", str(path), remote], cwd=live)
    required = path / required_file
    if not required.exists():
        raise SystemExit(f"Historical dependency missing required file: {required}")
    status = run([git, "status", "--porcelain"], cwd=path, check=False).stdout.strip()
    # Historical worktrees are dependencies. Never reset or overwrite local edits.
    return {"path": str(path), "branch_source": branch, "required_file": str(required), "worktree_dirty": bool(status)}


def install_command(config: dict[str, Any], python: Path) -> Path:
    runtime_root = expand(str(config.get("runtime_root") or "~/.iios/nightly-reconstruction"))
    runtime_root.mkdir(parents=True, exist_ok=True)
    command = runtime_root / "run-nightly-reconstruction.command"
    lock = runtime_root / "worker.lock"
    log = runtime_root / "nightly-reconstruction.log"
    body = f'''#!/bin/zsh
set -u
LOCK={json.dumps(str(lock))}
LOG={json.dumps(str(log))}
if ! mkdir "$LOCK" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT INT TERM
cd {json.dumps(str(ROOT))} || exit 2
{json.dumps(str(python))} {json.dumps(str(ROOT / "scripts" / "iios_nightly_market_reconstruction.py"))} >> "$LOG" 2>&1
RC=$?
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] rc=$RC" >> "$LOG"
exit $RC
'''
    command.write_text(body, encoding="utf-8")
    command.chmod(0o755)
    return command


def install_launch_agent(config: dict[str, Any], command: Path) -> Path:
    LAUNCH_DIR.mkdir(parents=True, exist_ok=True); LOG_DIR.mkdir(parents=True, exist_ok=True)
    plist = LAUNCH_DIR / f"{LABEL}.plist"
    interval = max(900, int(config.get("supervisor_interval_seconds") or 1800))
    payload = {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/open", "-gj", "-a", "Terminal", str(command)],
        "RunAtLoad": True,
        "StartInterval": interval,
        "ProcessType": "Background",
        "StandardOutPath": str(LOG_DIR / "nightly-market-reconstruction-supervisor.out.log"),
        "StandardErrorPath": str(LOG_DIR / "nightly-market-reconstruction-supervisor.err.log"),
    }
    tmp = plist.with_suffix(".tmp.plist")
    with tmp.open("wb") as handle: plistlib.dump(payload, handle, sort_keys=True)
    tmp.replace(plist)
    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", domain, str(plist)], check=False)
    run(["launchctl", "bootstrap", domain, str(plist)])
    run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], check=False)
    return plist


def launch_state() -> str:
    result = run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], check=False)
    return "LOADED" if result.returncode == 0 else "NOT_LOADED"


def latest_status(config: dict[str, Any]) -> dict[str, Any]:
    latest = expand(str(config.get("output_root") or "~/Library/Application Support/IIOS/nightly-reconstruction")) / "latest_nightly_reconstruction.json"
    payload = read_json(latest)
    return {
        "artifact_exists": latest.exists(),
        "artifact": str(latest),
        "status": payload.get("status"),
        "session_date": payload.get("session_date"),
        "official_9h_score_impact": ((payload.get("learning_contract") or {}).get("official_9h_score_impact") or (payload.get("truth") or {}).get("official_9h_score_impact")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate IIOS Batch 10M.7 Nightly Market Reconstruction")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin" and args.activate:
        raise SystemExit("10M.7 activation is macOS-only")
    config = read_json(expand(args.config))
    if not config:
        raise SystemExit("10M.7 config missing or invalid")
    safety = config.get("safety") or {}; truth = config.get("truth_contract") or {}
    if safety.get("ledger_mode") != "READ_ONLY" or safety.get("ledger_write") is not False:
        raise SystemExit("10M.7 ledger safety contract invalid")
    if truth.get("counts_as_live_detection") is not False or truth.get("eligible_for_9h_live_score") is not False or truth.get("official_9h_score_impact") != "NONE":
        raise SystemExit("10M.7 backfill/live-detection truth contract invalid")
    if args.status:
        print(json.dumps({"label": LABEL, "launch_agent": launch_state(), "latest": latest_status(config), "live_execution": False, "trade_execution_permission": False}, indent=2, sort_keys=True))
        return 0
    python = resolve_python(config)
    result: dict[str, Any] = {
        "status": "PLAN_ONLY",
        "label": LABEL,
        "python": str(python),
        "runtime_root": str(expand(str(config.get("runtime_root")))),
        "post_close_not_before_et": config.get("post_close_not_before_et"),
        "supervisor_interval_seconds": config.get("supervisor_interval_seconds"),
        "detection_mode": truth.get("detection_mode"),
        "counts_as_live_detection": False,
        "eligible_for_9h_live_score": False,
        "official_9h_score_impact": "NONE",
        "live_execution": False,
        "trade_execution_permission": False,
    }
    if args.activate:
        live = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
        if not live.exists(): raise SystemExit(f"Live checkout missing: {live}")
        worktrees = config.get("historical_worktrees") or {}; branches = config.get("historical_branches") or {}
        dependencies = {
            "10h": ensure_worktree(live, expand(str(worktrees["10h"])), str(branches["10h"]), "scripts/iios_historical_market_intelligence_runtime.py"),
            "10j": ensure_worktree(live, expand(str(worktrees["10j"])), str(branches["10j"]), "scripts/iios_historical_event_reconstruction_runtime.py"),
            "10k": ensure_worktree(live, expand(str(worktrees["10k"])), str(branches["10k"]), "scripts/iios_historical_macro_regime_library.py"),
        }
        command = install_command(config, python)
        plist = install_launch_agent(config, command)
        result.update({"status": "BATCH10M7_NIGHTLY_RECONSTRUCTION_ACTIVE", "command": str(command), "plist": str(plist), "launch_agent": launch_state(), "dependencies": dependencies, "9a_9b_9e_9h_9i_touched": False, "backend_8002_changed": False})
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
