#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import iios_experiment_ab_laboratory as lab


def _copy_json(source: Path, destination: Path) -> bool:
    if not source.exists() or not source.is_file():
        return False
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(value, dict):
        return False
    lab._atomic_write(destination, value)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the Batch 9Q Experiment & A/B Laboratory browser artifact.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--telemetry-dir", required=True)
    parser.add_argument("--browser-output", required=True)
    parser.add_argument("--office-output")
    parser.add_argument("--episode-output")
    args = parser.parse_args()

    state_dir = Path(args.state_dir).expanduser()
    telemetry_dir = Path(args.telemetry_dir).expanduser()
    office = lab.chief.build_from_state(state_dir, telemetry_dir)
    payload = lab.build_lab(
        office=office,
        shadow=lab._read_json(state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json"),
        learning=lab._read_json(state_dir / "latest_outcome_learning.json"),
        telemetry=lab._read_json(telemetry_dir / "latest.json"),
    )

    output = Path(args.browser_output).expanduser()
    lab._atomic_write(output, payload)
    if args.office_output:
        lab._atomic_write(Path(args.office_output).expanduser(), office)
    episode_copied = False
    if args.episode_output:
        episode_copied = _copy_json(
            state_dir / "browser" / "daily_factory_episode.json",
            Path(args.episode_output).expanduser(),
        )

    print(json.dumps({
        "status": "BATCH9Q_EXPERIMENT_AB_LAB_PUBLISHED",
        "browser_output": str(output),
        "office_output": args.office_output,
        "episode_copied": episode_copied,
        "experiment_count": len(payload.get("experiments") or []),
        "shadow_only": True,
        "advisory_only": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
