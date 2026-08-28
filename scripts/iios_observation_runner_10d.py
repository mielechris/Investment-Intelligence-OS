#!/usr/bin/env python3
"""Batch 10D wrapper for the existing 9A observation runner.

Discovery/orchestration remain in the isolated 9A worktree. Monitoring refreshes
are delegated to Backend 8002 so the authoritative installed chain runs:
base monitoring -> paper-fund portfolio context -> evidence watch -> Deep Watch.

Slow external discovery stages are executed in child processes with hard wall-
clock deadlines. If a provider call wedges, only that child process is terminated;
the parent 9A loop records the stage as an error through the existing `_safe_call`
and continues fail-closed.

After a local 9A cycle completes, its already-governed observation checkpoint is
mirrored to Backend 8002 for command-layer heartbeat visibility. Heartbeat sync is
telemetry only: it cannot create research cases, authorize capital, submit orders,
or enable live execution.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.request import Request, urlopen

import iios_observation_runner as runner

BACKEND_BASE_URL = "http://127.0.0.1:8002"
MONITORING_PATH = "/monitoring/refresh-due"
HEARTBEAT_PATH = "/observation-heartbeat/checkpoint"
MONITORING_TIMEOUT_SECONDS = 900
HEARTBEAT_TIMEOUT_SECONDS = 10
RADAR_TIMEOUT_SECONDS = 120
OPPORTUNITY_SCAN_TIMEOUT_SECONDS = 180
STAGE_WORKER = Path(__file__).with_name("iios_observation_stage_worker.py")

_ORIGINAL_RUN_CYCLE = runner.run_cycle


class ObservationStageTimeout(TimeoutError):
    """Raised when an isolated 9A stage exceeds its hard wall-clock ceiling."""


def refresh_due_profiles_via_backend() -> dict:
    req = Request(
        f"{BACKEND_BASE_URL}{MONITORING_PATH}",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=MONITORING_TIMEOUT_SECONDS) as response:
        payload = json.load(response)
        status = int(getattr(response, "status", 200) or 200)

    if status != 200:
        raise RuntimeError(f"BACKEND_MONITORING_HTTP_{status}")
    if not isinstance(payload, dict):
        raise RuntimeError("BACKEND_MONITORING_INVALID_RESPONSE")

    return {
        **payload,
        "monitoring_authority": "BACKEND_8002",
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def sync_observation_checkpoint_via_backend(state: dict[str, Any]) -> dict[str, Any]:
    payload = {
        **state,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    req = Request(
        f"{BACKEND_BASE_URL}{HEARTBEAT_PATH}",
        data=json.dumps(payload, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=HEARTBEAT_TIMEOUT_SECONDS) as response:
        result = json.load(response)
        status = int(getattr(response, "status", 200) or 200)

    if status != 200:
        raise RuntimeError(f"BACKEND_HEARTBEAT_HTTP_{status}")
    if not isinstance(result, dict):
        raise RuntimeError("BACKEND_HEARTBEAT_INVALID_RESPONSE")
    return result


def run_cycle_with_backend_heartbeat(*args: Any, **kwargs: Any) -> dict[str, Any]:
    state = _ORIGINAL_RUN_CYCLE(*args, **kwargs)
    try:
        heartbeat = sync_observation_checkpoint_via_backend(state)
        runner._log(
            "[HEARTBEAT] Backend 8002 observation checkpoint "
            f"status={heartbeat.get('status', 'UNKNOWN')}"
        )
    except Exception as exc:
        # The local observation cycle is already complete and persisted. Telemetry
        # sync failure must not create authority or terminate the governed 9A loop.
        runner._log(
            "[HEARTBEAT] Backend 8002 sync failed closed: "
            f"{type(exc).__name__}: {exc}"
        )
    return state


def _run_stage_in_subprocess(
    stage: str,
    timeout_seconds: int,
    label: str,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    payload = json.dumps({"args": list(args), "kwargs": kwargs}, default=str)
    command = [sys.executable, str(STAGE_WORKER), stage]

    try:
        completed = subprocess.run(
            command,
            input=payload,
            text=True,
            capture_output=True,
            timeout=max(1, int(timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ObservationStageTimeout(
            f"{label}_TIMEOUT_{timeout_seconds}s"
        ) from exc

    if completed.returncode != 0:
        detail = str(completed.stderr or "").strip()[-1200:]
        raise RuntimeError(
            f"{label}_WORKER_FAILED_{completed.returncode}: {detail or 'no stderr'}"
        )

    try:
        result = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label}_WORKER_INVALID_JSON") from exc

    if not isinstance(result, dict):
        raise RuntimeError(f"{label}_WORKER_INVALID_RESPONSE")
    return result


def run_market_event_radar_bounded(*args: Any, **kwargs: Any) -> dict:
    return _run_stage_in_subprocess(
        "market_event_radar",
        RADAR_TIMEOUT_SECONDS,
        "MARKET_EVENT_RADAR",
        *args,
        **kwargs,
    )


def scan_universe_bounded(*args: Any, **kwargs: Any) -> dict:
    return _run_stage_in_subprocess(
        "opportunity_scan",
        OPPORTUNITY_SCAN_TIMEOUT_SECONDS,
        "OPPORTUNITY_SCAN",
        *args,
        **kwargs,
    )


def install_backend_monitoring_bridge():
    runner.refresh_due_profiles = refresh_due_profiles_via_backend
    runner.run_market_event_radar = run_market_event_radar_bounded
    runner.scan_universe = scan_universe_bounded
    runner.run_cycle = run_cycle_with_backend_heartbeat
    return runner


def main() -> int:
    install_backend_monitoring_bridge()
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
