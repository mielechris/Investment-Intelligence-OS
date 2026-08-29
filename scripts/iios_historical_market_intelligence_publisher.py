#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

DEFAULT_RESEARCH_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "historical-research"


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the latest persisted Batch 10H historical research artifact without performing research.")
    parser.add_argument("--research-dir", default=str(DEFAULT_RESEARCH_DIR))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(args.research_dir).expanduser() / "latest_historical_market_intelligence.json"
    destination = Path(args.output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        payload = {"schema_version":"batch10h-historical-market-intelligence-v1","status":"HISTORICAL_RESEARCH_WARM_UP","mode":"TWENTY_FOUR_SEVEN_READ_ONLY_RESEARCH","coverage":[],"studies":[],"cycle":{"cycle_count":0},"safety":{"read_only_research":True,"capital_authority":False,"trade_execution_permission":False,"live_execution":False}}
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": payload["status"], "published": str(destination)}))
        return 0
    shutil.copy2(source, destination)
    payload = json.loads(source.read_text(encoding="utf-8"))
    print(json.dumps({"status": payload.get("status"), "published": str(destination)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
