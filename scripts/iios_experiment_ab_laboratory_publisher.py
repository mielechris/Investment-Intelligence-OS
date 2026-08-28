#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import iios_experiment_ab_laboratory as lab


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the Batch 9Q Experiment & A/B Laboratory browser artifact.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--browser-output", required=True)
    args = parser.parse_args()

    payload = lab.build_from_state(
        Path(args.state_dir).expanduser(),
        Path(args.telemetry_dir).expanduser(),
    )
    output = Path(args.browser_output).expanduser()
    lab._atomic_write(output, payload)
    print(json.dumps({
        "status": "BATCH9Q_EXPERIMENT_AB_LAB_PUBLISHED",
        "browser_output": str(output),
        "experiment_count": len(payload.get("experiments") or []),
        "shadow_only": True,
        "advisory_only": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
