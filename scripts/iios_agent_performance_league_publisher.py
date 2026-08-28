#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import iios_agent_performance_league as league


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the Batch 9S Agent Performance League browser artifact.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--browser-output", required=True)
    args = parser.parse_args()
    payload = league.build_from_state(Path(args.state_dir).expanduser(), Path(args.telemetry_dir).expanduser())
    output = Path(args.browser_output).expanduser()
    league._atomic_write(output, payload)
    summary = payload.get("summary") or {}
    print(json.dumps({
        "status": "BATCH9S_AGENT_PERFORMANCE_LEAGUE_PUBLISHED",
        "browser_output": str(output),
        "officially_ranked_count": summary.get("officially_ranked_count"),
        "provisional_count": summary.get("provisional_count"),
        "ranked_model_count": summary.get("ranked_model_count"),
        "automatic_weight_changes": 0,
        "automatic_model_routing_changes": 0,
        "advisory_only": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
