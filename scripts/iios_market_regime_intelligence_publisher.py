#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import iios_market_regime_intelligence as regime


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Batch 9T Market Regime Intelligence browser artifact.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--browser-output", required=True)
    args = parser.parse_args()
    payload = regime.build_from_state(Path(args.state_dir).expanduser(), Path(args.telemetry_dir).expanduser())
    output = Path(args.browser_output).expanduser()
    regime._atomic_write(output, payload)
    current = payload.get("current_regime") or {}
    print(json.dumps({
        "status": "BATCH9T_MARKET_REGIME_INTELLIGENCE_PUBLISHED",
        "browser_output": str(output),
        "regime_label": current.get("regime_label"),
        "evidence_level": current.get("evidence_level"),
        "classification_only": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
