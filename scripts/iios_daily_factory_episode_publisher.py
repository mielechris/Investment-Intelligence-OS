#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
HERE = Path(__file__).resolve().parent
BUILDER = HERE / "iios_daily_factory_episode_exact.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Batch 9O exact-linked daily episode builder and publish the persisted final JSON into the localhost browser dist."
    )
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--browser-output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser()
    telemetry_dir = Path(args.telemetry_dir).expanduser()
    browser_output = Path(args.browser_output).expanduser()
    command = [
        sys.executable,
        str(BUILDER),
        "--state-dir",
        str(state_dir),
        "--telemetry-dir",
        str(telemetry_dir),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode

    source = state_dir / "browser" / "daily_factory_episode.json"
    published = False
    episode_session_id = None
    episode_status = None
    learning_lineage_mode = None
    if source.exists():
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and payload.get("status") in {
            "FINAL",
            "FINAL_WITH_LEARNING_WARMUP",
        }:
            browser_output.parent.mkdir(parents=True, exist_ok=True)
            temporary = browser_output.with_suffix(browser_output.suffix + ".tmp")
            shutil.copy2(source, temporary)
            temporary.replace(browser_output)
            published = True
            episode_session_id = payload.get("episode_session_id")
            episode_status = payload.get("status")
            learning_lineage_mode = (payload.get("source_freshness") or {}).get(
                "learning_lineage_mode"
            )

    summary = {
        "status": "BATCH9O_EPISODE_PUBLISHER_COMPLETE",
        "builder_output": result.stdout.strip()[:1200],
        "published": published,
        "episode_session_id": episode_session_id,
        "episode_status": episode_status,
        "learning_lineage_mode": learning_lineage_mode,
        "browser_output": str(browser_output),
        "source_mode": "PERSISTED_9G_9H_9I_9J_EXACT_LINKED_READ_ONLY",
        "direct_ledger_access": False,
        "backend_write_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
