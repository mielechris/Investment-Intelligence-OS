#!/usr/bin/env python3
"""Batch 10D wrapper for the existing 9A observation runner.

Discovery/orchestration remain in the isolated 9A worktree. Monitoring refreshes
are delegated to Backend 8002 so the authoritative installed chain runs:
base monitoring -> paper-fund portfolio context -> evidence watch -> Deep Watch.

Slow external discovery stages are bounded on the main runner thread. A radar or
opportunity-scan timeout is raised back into the existing runner's `_safe_call`,
which records the stage as an error and continues fail-closed.

After a local 9A cycle completes, its already-governed observation checkpoint is
mirrored to Backend 8002 for command-layer heartbeat visibility. Heartbeat sync is
telemetry only: it cannot create research cases, authorize capital, submit orders,
or enable live execution.
"""
from __future__ import annotations

import json
import signal
from typing import Any, Callable
from urllib.request import Request, urlopen

import iios_observation_runner as runner

BACKEND_BASE_URL = "http://127.0.0.1:8002"
MONITORING_PATH = "/monitoring/refresh-due"
HEARTBEAT_PATH = "/observation-heartbeat/checkpoint"
MONITORING_TIMEOUT_SECONDS = 900
HEARTBEAT_TIMEOUT_SECONDS = 10
RADAR_TIMEOUT_SECONDS = 120
OPPORTUNITY_SCAN_TIMEOUT_SECONDS = 180

_ORIGINAL_RADAR = runner.run_market_event_radar
_ORIGINAL_SCAN = runner.scan_universe
_ORIGINAL_RUN_CYCLE = runner.run_cycle


class ObservationStageTimeout(TimeoutError):
    """Raised when a bounded external 9A stage exceeds its wall-clock ceiling."""


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


def _run_with_timeout(
    function: Callable[..., Any],
    timeout_seconds: int,
    label: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Bound one synchronous external stage on macOS/POSIX main-thread execution."""

    if timeout_seconds <= 0:
        return function(*args, **kwargs)

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)

    def _timeout_handler(_signum: int, _frame: Any) -> None:
        raise ObservationStageTimeout(f"{label}_TIMEOUT_{timeout_seconds}s")

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, float(timeout_seconds))

    try:
        return function(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        delay, interval = previous_timer
        if delay > 0 or interval > 0:
            signal.setitimer(signal.ITIMER_REAL, delay, interval)


def run_market_event_radar_bounded(*args: Any, **kwargs: Any) -> dict:
    return _run_with_timeout(
        _ORIGINAL_RADAR,
        RADAR_TIMEOUT_SECONDS,
        "MARKET_EVENT_RADAR",
        *args,
        **kwargs,
    )


def scan_universe_bounded(*args: Any, **kwargs: Any) -> dict:
    return _run_with_timeout(
        _ORIGINAL_SCAN,
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
