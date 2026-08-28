#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import iios_data_expansion_factory as factory


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the Batch 9R Data Expansion Factory browser artifact.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--browser-output", required=True)
    args = parser.parse_args()

    payload = factory.build_from_state(
        Path(args.state_dir).expanduser(),
        Path(args.telemetry_dir).expanduser(),
    )
    output = Path(args.browser_output).expanduser()
    factory._atomic_write(output, payload)
    summary = payload.get("summary") or {}
    print(
        json.dumps(
            {
                "status": "BATCH9R_DATA_EXPANSION_FACTORY_PUBLISHED",
                "browser_output": str(output),
                "candidate_source_count": summary.get("candidate_source_count"),
                "shadow_connected_count": summary.get("shadow_connected_count"),
                "production_sources_added": summary.get("production_sources_added"),
                "advisory_only": True,
                "purchase_authority": False,
                "production_feed_change_authority": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
