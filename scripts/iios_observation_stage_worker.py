#!/usr/bin/env python3
"""Isolated worker for bounded Batch 9A external discovery stages.

The parent observation loop launches this script in a separate OS process and
applies a hard subprocess timeout. If an external provider call wedges, the child
process can be terminated without wedging the parent 9A scheduler.

This worker has no broker, capital, authorization, or live-execution authority.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import json
import sys
from typing import Any

import iios_observation_runner as runner


def _read_payload() -> tuple[list[Any], dict[str, Any]]:
    raw = sys.stdin.read()
    payload = json.loads(raw or "{}")
    if not isinstance(payload, dict):
        raise ValueError("worker payload must be an object")
    args = payload.get("args") or []
    kwargs = payload.get("kwargs") or {}
    if not isinstance(args, list):
        raise ValueError("worker args must be a list")
    if not isinstance(kwargs, dict):
        raise ValueError("worker kwargs must be an object")
    return args, kwargs


def run_stage(stage: str, args: list[Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    if stage == "market_event_radar":
        result = runner.run_market_event_radar(*args, **kwargs)
    elif stage == "opportunity_scan":
        result = runner.scan_universe(*args, **kwargs)
    else:
        raise ValueError(f"unknown stage: {stage}")

    if not isinstance(result, dict):
        raise TypeError(f"{stage} returned non-object result")
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: iios_observation_stage_worker.py <stage>", file=sys.stderr)
        return 2

    stage = str(sys.argv[1]).strip()
    try:
        args, kwargs = _read_payload()
        # External stage code may print diagnostics. Keep stdout machine-readable
        # for the parent process and route any stage prints to stderr instead.
        with redirect_stdout(sys.stderr):
            result = run_stage(stage, args, kwargs)
        sys.stdout.write(json.dumps(result, default=str))
        sys.stdout.flush()
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
