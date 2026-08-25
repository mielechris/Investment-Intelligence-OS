from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from ledger import (
    latest_object,
    record_event,
    record_object,
    utc_now,
)

from paper_portfolio_core import (
    ACCOUNT_ID,
    PORTFOLIO_CASE_ID,
    build_portfolio_scoreboard,
    record_live_portfolio_snapshot,
    refresh_benchmarks,
)


router = APIRouter()

POLICY_VERSION = "paper-portfolio-auto-monitor-v1"

STATE_ID = "paper_portfolio_auto_monitor"
STATE_TYPE = "paper_portfolio_auto_monitor_state"

DEFAULT_INTERVAL_MINUTES = 15
MIN_INTERVAL_MINUTES = 15
POLL_SECONDS = 30

_stop = threading.Event()
_thread: threading.Thread | None = None
_cycle_lock = threading.Lock()


def _bool_env(
    name: str,
    default: bool = False,
) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _enabled() -> bool:
    return _bool_env(
        "IIOS_PAPER_PORTFOLIO_AUTO",
        False,
    )


def _interval_minutes() -> int:
    raw = os.getenv(
        "IIOS_PAPER_PORTFOLIO_INTERVAL_MINUTES",
        str(DEFAULT_INTERVAL_MINUTES),
    )

    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_INTERVAL_MINUTES

    return max(
        MIN_INTERVAL_MINUTES,
        value,
    )


def _parse_time(
    value: Any,
) -> datetime | None:
    text = str(value or "").strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _state() -> dict[str, Any]:
    return (
        latest_object(
            STATE_TYPE,
            case_id=PORTFOLIO_CASE_ID,
        )
        or {}
    )


def _save_state(
    **updates: Any,
) -> dict[str, Any]:
    previous = _state()

    state = {
        "paper_portfolio_auto_monitor_id":
            STATE_ID,
        "policy_version":
            POLICY_VERSION,
        "paper_portfolio_account_id":
            ACCOUNT_ID,
        "enabled":
            _enabled(),
        "interval_minutes":
            _interval_minutes(),
        "last_run_at":
            previous.get("last_run_at"),
        "last_status":
            previous.get("last_status"),
        "last_snapshot_id":
            previous.get("last_snapshot_id"),
        "last_nav":
            previous.get("last_nav"),
        "last_error":
            previous.get("last_error"),
        **updates,
        "measurement_only":
            True,
        "capital_allocation_allowed":
            False,
        "position_sizing_allowed":
            False,
        "paper_mode":
            True,
        "auto_trade_authority":
            False,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
        "updated_at":
            utc_now(),
    }

    record_object(
        STATE_ID,
        STATE_TYPE,
        PORTFOLIO_CASE_ID,
        state,
        parent_id=ACCOUNT_ID,
        topic="PAPER_PORTFOLIO",
    )

    return state


def automation_status() -> dict[str, Any]:
    state = _state()

    return {
        "policy_version":
            POLICY_VERSION,
        "enabled":
            _enabled(),
        "scheduler_running":
            bool(
                _thread
                and _thread.is_alive()
            ),
        "cycle_running":
            _cycle_lock.locked(),
        "interval_minutes":
            _interval_minutes(),
        "minimum_interval_minutes":
            MIN_INTERVAL_MINUTES,
        "last_run_at":
            state.get("last_run_at"),
        "last_status":
            state.get("last_status"),
        "last_snapshot_id":
            state.get("last_snapshot_id"),
        "last_nav":
            state.get("last_nav"),
        "last_error":
            state.get("last_error"),
        "measurement_only":
            True,
        "capital_allocation_allowed":
            False,
        "position_sizing_allowed":
            False,
        "paper_mode":
            True,
        "auto_trade_authority":
            False,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
    }


def _due() -> bool:
    if not _enabled():
        return False

    state = _state()

    last_run = _parse_time(
        state.get("last_run_at")
    )

    if last_run is None:
        return True

    age_seconds = (
        datetime.now(timezone.utc)
        - last_run
    ).total_seconds()

    return (
        age_seconds
        >= _interval_minutes() * 60
    )


def run_monitor_cycle(
    *,
    force: bool = False,
) -> dict[str, Any]:
    if not _enabled() and not force:
        return {
            **automation_status(),
            "status":
                "AUTOMATION_DISABLED",
        }

    if not force and not _due():
        return {
            **automation_status(),
            "status":
                "NOT_DUE",
        }

    if not _cycle_lock.acquire(
        blocking=False
    ):
        return {
            **automation_status(),
            "status":
                "ALREADY_RUNNING",
        }

    try:
        snapshot = (
            record_live_portfolio_snapshot()
        )

        benchmarks = (
            refresh_benchmarks()
        )

        scoreboard = (
            build_portfolio_scoreboard()
        )

        state = _save_state(
            last_run_at=utc_now(),
            last_status="COMPLETE",
            last_snapshot_id=
                snapshot.get(
                    "paper_portfolio_snapshot_id"
                ),
            last_nav=
                snapshot.get("nav"),
            last_error=None,
        )

        record_event(
            PORTFOLIO_CASE_ID,
            "PAPER_PORTFOLIO_AUTO_MONITOR_COMPLETE",
            entity_id=
                snapshot.get(
                    "paper_portfolio_snapshot_id"
                ),
            payload={
                "nav":
                    snapshot.get("nav"),
                "cash":
                    snapshot.get("cash"),
                "position_count":
                    snapshot.get(
                        "position_count"
                    ),
                "risk_status":
                    (
                        scoreboard.get(
                            "risk"
                        )
                        or {}
                    ).get(
                        "risk_status"
                    ),
                "benchmark_refresh_status":
                    benchmarks.get("status"),
                "trade_execution_permission":
                    False,
                "live_execution":
                    False,
            },
        )

        return {
            "status":
                "COMPLETE",
            "snapshot":
                snapshot,
            "benchmarks":
                benchmarks,
            "scoreboard":
                scoreboard,
            "automation":
                state,
            "measurement_only":
                True,
            "capital_allocation_allowed":
                False,
            "position_sizing_allowed":
                False,
            "paper_mode":
                True,
            "auto_trade_authority":
                False,
            "paper_order_permission":
                False,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        }

    except Exception as exc:
        error = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )[:1000]

        _save_state(
            last_run_at=utc_now(),
            last_status="ERROR",
            last_error=error,
        )

        record_event(
            PORTFOLIO_CASE_ID,
            "PAPER_PORTFOLIO_AUTO_MONITOR_FAILED",
            entity_id=STATE_ID,
            payload={
                "error":
                    error,
                "trade_execution_permission":
                    False,
                "live_execution":
                    False,
            },
        )

        return {
            "status":
                "ERROR",
            "error":
                error,
            "measurement_only":
                True,
            "paper_mode":
                True,
            "trade_execution_permission":
                False,
            "live_execution":
                False,
        }

    finally:
        _cycle_lock.release()


def _loop() -> None:
    while not _stop.wait(
        POLL_SECONDS
    ):
        run_monitor_cycle()


def start_portfolio_scheduler() -> None:
    global _thread

    if (
        _thread
        and _thread.is_alive()
    ):
        return

    _stop.clear()

    _thread = threading.Thread(
        target=_loop,
        name="iios-paper-portfolio-monitor",
        daemon=True,
    )

    _thread.start()


def stop_portfolio_scheduler() -> None:
    _stop.set()


@router.on_event("startup")
def start_router_scheduler() -> None:
    start_portfolio_scheduler()


@router.on_event("shutdown")
def stop_router_scheduler() -> None:
    stop_portfolio_scheduler()


@router.get(
    "/paper-portfolio/automation/status"
)
def paper_portfolio_automation_status():
    return automation_status()


@router.post(
    "/paper-portfolio/automation/run-now"
)
def paper_portfolio_automation_run_now():
    return run_monitor_cycle(
        force=True
    )
