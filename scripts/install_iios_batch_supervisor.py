#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "iios_batch_pipeline.json"
SUPERVISOR = REPO / "scripts" / "iios_batch_supervisor.py"
LABEL = "com.iios.batch-supervisor"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def config_value() -> dict:
    if not CONFIG.exists():
        raise SystemExit(f"Missing config: {CONFIG}")
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("Supervisor config must be a JSON object")
    return value


def state_directory(config: dict) -> Path:
    path = Path(
        os.path.expanduser(
            str(config.get("state_directory") or "~/.iios/batch-supervisor")
        )
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def launchctl(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args],
        text=True,
        capture_output=True,
        check=check,
    )


def domain() -> str:
    return f"gui/{os.getuid()}"


def bootout_if_loaded() -> None:
    if PLIST.exists():
        launchctl("bootout", domain(), str(PLIST), check=False)


def install() -> int:
    config = config_value()
    if not SUPERVISOR.exists():
        raise SystemExit(f"Missing supervisor: {SUPERVISOR}")

    poll_seconds = max(60, int(config.get("poll_seconds") or 900))
    state_dir = state_directory(config)
    PLIST.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            str(SUPERVISOR),
            "--once",
        ],
        "WorkingDirectory": str(REPO),
        "RunAtLoad": True,
        "StartInterval": poll_seconds,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(state_dir / "launchd.out.log"),
        "StandardErrorPath": str(state_dir / "launchd.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
        },
    }

    bootout_if_loaded()
    with PLIST.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)

    result = launchctl("bootstrap", domain(), str(PLIST), check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        print("LaunchAgent file was written, but launchctl bootstrap failed.")
        return result.returncode

    launchctl("kickstart", "-k", f"{domain()}/{LABEL}", check=False)

    print("=" * 72)
    print("IIOS BATCH SUPERVISOR INSTALLED")
    print("=" * 72)
    print("LaunchAgent:", PLIST)
    print("Repo:", REPO)
    print("Python:", sys.executable)
    print("Check interval:", poll_seconds, "seconds")
    print("State/log directory:", state_dir)
    print("Live trading authority: NOT CHANGED / FALSE")
    print()
    print("Status:")
    print(f"  {sys.executable} {SUPERVISOR} --status")
    print()
    print("Uninstall:")
    print(f"  {sys.executable} {Path(__file__).resolve()} --uninstall")
    print("=" * 72)
    return 0


def uninstall() -> int:
    bootout_if_loaded()
    if PLIST.exists():
        PLIST.unlink()
    print("IIOS batch supervisor LaunchAgent removed.")
    print("Supervisor state/log files were preserved for auditability.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or remove the IIOS batch supervisor LaunchAgent")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())
