#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shlex
import subprocess
from pathlib import Path
from typing import Any

LABEL = "com.iios.nightly-reconstruction"
CADENCE_SECONDS = 15 * 60
RUNTIME_ROOT = Path.home() / ".iios" / "nightly-reconstruction"
COMMAND_PATH = RUNTIME_ROOT / "run-nightly-reconstruction.command"
STDOUT_PATH = RUNTIME_ROOT / "launchd.stdout.log"
STDERR_PATH = RUNTIME_ROOT / "launchd.stderr.log"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DEFAULT_BASE_DIR = Path.home() / "Library" / "Application Support" / "IIOS"

SAFETY = {
    "advisory_only": True,
    "paper_mode_only": True,
    "live_execution": False,
    "live_capital_locked": True,
    "trade_execution_permission": False,
    "no_broker_authority": True,
    "no_committee_or_risk_authority": True,
    "no_automatic_parameter_changes": True,
    "no_case_promotion_authority": True,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_command(*, repo_root: Path, base_dir: Path) -> str:
    repo = shlex.quote(str(repo_root))
    base = shlex.quote(str(base_dir))
    return f"""#!/bin/zsh
set -euo pipefail
cd {repo}
exec /usr/bin/python3 scripts/iios_nightly_post_close_reconstruction.py --run-once --base-dir {base}
"""


def build_plist(*, command_path: Path = COMMAND_PATH) -> dict[str, Any]:
    return {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/open", "-g", "-a", "Terminal", str(command_path)],
        "StartInterval": CADENCE_SECONDS,
        "RunAtLoad": False,
        "StandardOutPath": str(STDOUT_PATH),
        "StandardErrorPath": str(STDERR_PATH),
        "ProcessType": "Background",
    }


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/launchctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _loaded() -> bool:
    result = _launchctl("print", f"{_domain()}/{LABEL}")
    return result.returncode == 0


def activate(*, repo_root: Path | None = None, base_dir: Path = DEFAULT_BASE_DIR) -> dict[str, Any]:
    repo_root = Path(repo_root or _repo_root()).resolve()
    base_dir = Path(base_dir).expanduser()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    COMMAND_PATH.write_text(build_command(repo_root=repo_root, base_dir=base_dir), encoding="utf-8")
    COMMAND_PATH.chmod(0o755)
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(build_plist(command_path=COMMAND_PATH), handle, sort_keys=True)

    _launchctl("bootout", _domain(), str(PLIST_PATH))
    result = _launchctl("bootstrap", _domain(), str(PLIST_PATH))
    if result.returncode != 0:
        return {
            "batch": "10M.7",
            "status": "ACTIVATION_ERROR",
            "error": (result.stderr or result.stdout or "launchctl bootstrap failed").strip(),
            "transport": "TERMINAL_BRIDGE",
            "safety": dict(SAFETY),
        }
    return status(base_dir=base_dir)


def deactivate() -> dict[str, Any]:
    result = _launchctl("bootout", _domain(), str(PLIST_PATH))
    return {
        "batch": "10M.7",
        "status": "DEACTIVATED" if result.returncode in {0, 3} else "DEACTIVATION_WARNING",
        "loaded": _loaded(),
        "transport": "TERMINAL_BRIDGE",
        "runtime_root": str(RUNTIME_ROOT),
        "safety": dict(SAFETY),
    }


def status(*, base_dir: Path = DEFAULT_BASE_DIR) -> dict[str, Any]:
    base_dir = Path(base_dir).expanduser()
    latest = base_dir / "nightly-reconstruction" / "latest_nightly_reconstruction.json"
    latest_payload: dict[str, Any] = {}
    try:
        value = json.loads(latest.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            latest_payload = value
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    loaded = _loaded()
    return {
        "batch": "10M.7",
        "surface": "Nightly_Post_Close_Reconstruction",
        "status": "LOADED" if loaded else "NOT_LOADED",
        "loaded": loaded,
        "label": LABEL,
        "cadence_seconds": CADENCE_SECONDS,
        "transport": "TERMINAL_BRIDGE",
        "runtime_root": str(RUNTIME_ROOT),
        "command_path": str(COMMAND_PATH),
        "plist_path": str(PLIST_PATH),
        "artifact_base_dir": str(base_dir),
        "latest_worker_status": latest_payload.get("status") or "NOT_YET_RUN",
        "latest_worker_completed_at": latest_payload.get("completed_at"),
        "post_close_guard": "WORKER_ENFORCES_16:20_ET_WEEKDAY_GUARD",
        "preserved_stack": {
            "9A_observation": "UNCHANGED",
            "9B_paper_trading": "UNCHANGED",
            "9E_radar": "UNCHANGED",
            "backend_8002": "UNCHANGED",
            "10J_event_reconstruction": "REUSED",
            "10K_macro_regime": "REUSED",
        },
        "safety": dict(SAFETY),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate or inspect the Batch 10M.7 Terminal-Bridge nightly reconstruction worker.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--activate", action="store_true")
    action.add_argument("--status", action="store_true")
    action.add_argument("--deactivate", action="store_true")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR))
    args = parser.parse_args()

    base_dir = Path(args.base_dir).expanduser()
    if args.activate:
        payload = activate(base_dir=base_dir)
    elif args.deactivate:
        payload = deactivate()
    else:
        payload = status(base_dir=base_dir)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 1 if payload.get("status") == "ACTIVATION_ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
