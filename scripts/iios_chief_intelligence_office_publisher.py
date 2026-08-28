#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "iios_chief_intelligence_office.py"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the Batch 9P advisory office memo into the localhost browser dist.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--browser-output", required=True)
    args = parser.parse_args()

    state_dir = Path(args.state_dir).expanduser()
    telemetry_dir = Path(args.telemetry_dir).expanduser()
    persistent_output = state_dir / "browser" / "chief_intelligence_office.json"
    command = [
        sys.executable,
        str(ENGINE),
        "--state-dir",
        str(state_dir),
        "--telemetry-dir",
        str(telemetry_dir),
        "--output",
        str(persistent_output),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode

    browser_output = Path(args.browser_output).expanduser()
    browser_output.parent.mkdir(parents=True, exist_ok=True)
    if persistent_output.exists():
        tmp = browser_output.with_suffix(browser_output.suffix + ".tmp")
        shutil.copy2(persistent_output, tmp)
        tmp.replace(browser_output)

    summary = {
        "status": "BATCH9P_CHIEF_INTELLIGENCE_OFFICE_PUBLISHED",
        "persistent_output": str(persistent_output),
        "browser_output": str(browser_output),
        "advisory_only": True,
        "backend_write_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
