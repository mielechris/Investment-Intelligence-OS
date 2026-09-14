from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter

from grok_discovery_lead_time import build_discovery_lead_time_report
from grok_value_cycle_async import start_cycle_job
from grok_value_instrumentation import MEASUREMENT_CASE_ID
from ledger import latest_object, record_event, record_object, utc_now


router = APIRouter()

POLICY_VERSION = "grok-value-auto-scheduler-v1"
STATE_ID = "grok_value_auto_scheduler"
STATE_TYPE = "grok_value_auto_scheduler_state"

TARGET_PROSPECTIVE_PAIRS = 5
MIN_INTERVAL_MINUTES = 11
DEFAULT_INTERVAL_MINUTES = 15
POLL_SECONDS = 30

_stop = threading.Event()
_thread: threading.Thread | None = None


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _interval_minutes() -> int:
    raw = os.getenv(
        "IIOS_GROK_7C_INTERVAL_MINUTES",
        str(DEFAULT_INTERVAL_MINUTES),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_INTERVAL_MINUTES
    return max(MIN_INTERVAL_MINUTES, value)


def _enabled() -> bool:
    return _bool_env("IIOS_GROK_7C_AUTO", False)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _state() -> dict[str, Any]:
    return (
        latest_object(
            STATE_TYPE,
            case_id=MEASUREMENT_CASE_ID,
        )
        or {}
    )


def _save_state(**updates: Any) -> dict[str, Any]:
    prior = _state()

    body = {
        "grok_value_auto_scheduler_id": STATE_ID,
        "policy_version": POLICY_VERSION,
        "enabled": _enabled(),
        "target_prospective_pairs": TARGET_PROSPECTIVE_PAIRS,
        "interval_minutes": _interval_minutes(),
        "last_attempt_at": prior.get("last_attempt_at"),
        "last_start_status": prior.get("last_start_status"),
        "last_job_id": prior.get("last_job_id"),
        "last_error": prior.get("last_error"),
        **updates,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "updated_at": utc_now(),
    }

    record_object(
        STATE_ID,
        STATE_TYPE,
        MEASUREMENT_CASE_ID,
        body,
        topic="BATCH_7C_AUTOMATION",
    )
    return body


def automation_status() -> dict[str, Any]:
    lead = build_discovery_lead_time_report()
    pairs = int(lead.get("prospective_pair_count") or 0)
    state = _state()

    last_attempt = _parse_time(state.get("last_attempt_at"))
    interval = _interval_minutes()

    next_due_at = None
    if last_attempt:
        next_due_at = (
            last_attempt + timedelta(minutes=interval)
        ).isoformat()

    return {
        "policy_version": POLICY_VERSION,
        "enabled": _enabled(),
        "scheduler_running": bool(_thread and _thread.is_alive()),
        "prospective_pair_count": pairs,
        "target_prospective_pairs": TARGET_PROSPECTIVE_PAIRS,
        "remaining_pairs": max(
            0,
            TARGET_PROSPECTIVE_PAIRS - pairs,
        ),
        "goal_reached": pairs >= TARGET_PROSPECTIVE_PAIRS,
        "interval_minutes": interval,
        "minimum_interval_minutes": MIN_INTERVAL_MINUTES,
        "last_attempt_at": state.get("last_attempt_at"),
        "last_start_status": state.get("last_start_status"),
        "last_job_id": state.get("last_job_id"),
        "last_error": state.get("last_error"),
        "next_due_at": next_due_at,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _due() -> bool:
    status = automation_status()

    if not status["enabled"]:
        return False

    if status["goal_reached"]:
        return False

    last_attempt = _parse_time(status.get("last_attempt_at"))
    if last_attempt is None:
        return True

    return (
        datetime.now(timezone.utc) - last_attempt
    ).total_seconds() >= _interval_minutes() * 60


def run_if_due(force: bool = False) -> dict[str, Any]:
    status = automation_status()

    if status["goal_reached"]:
        return {
            **status,
            "status": "GOAL_REACHED",
        }

    if not force and not _due():
        return {
            **status,
            "status": "NOT_DUE",
        }

    attempt_at = utc_now()

    try:
        started = start_cycle_job(
            {
                "days": 2,
                "max_candidates": 5,
                "native_symbol_limit": 20,
                "native_news_limit": 12,
                "native_timespan": "24h",
            }
        )

        job = started.get("job") or {}
        job_id = job.get("grok_value_cycle_job_id")

        _save_state(
            last_attempt_at=attempt_at,
            last_start_status=started.get("status"),
            last_job_id=job_id,
            last_error=None,
        )

        record_event(
            MEASUREMENT_CASE_ID,
            "BATCH_7C_AUTO_CYCLE_ATTEMPTED",
            entity_id=job_id,
            payload={
                "start_status": started.get("status"),
                "prospective_pair_count_before": status[
                    "prospective_pair_count"
                ],
                "target_prospective_pairs": TARGET_PROSPECTIVE_PAIRS,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        )

        return {
            "status": started.get("status"),
            "job": job,
            "automation": automation_status(),
            "research_only": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:1000]

        _save_state(
            last_attempt_at=attempt_at,
            last_start_status="ERROR",
            last_error=error,
        )

        return {
            "status": "ERROR",
            "error": error,
            "automation": automation_status(),
            "research_only": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }


def _loop() -> None:
    while not _stop.wait(POLL_SECONDS):
        run_if_due()


def start_grok_value_scheduler() -> None:
    global _thread

    if _thread and _thread.is_alive():
        return

    _stop.clear()
    _thread = threading.Thread(
        target=_loop,
        name="iios-grok-value-scheduler",
        daemon=True,
    )
    _thread.start()


def stop_grok_value_scheduler() -> None:
    _stop.set()


@router.on_event("startup")
def start_router_scheduler() -> None:
    start_grok_value_scheduler()


@router.on_event("shutdown")
def stop_router_scheduler() -> None:
    stop_grok_value_scheduler()


@router.get("/grok/value/auto/status")
def get_auto_status():
    return automation_status()


@router.post("/grok/value/auto/run-now")
def run_auto_now():
    return run_if_due(force=True)
