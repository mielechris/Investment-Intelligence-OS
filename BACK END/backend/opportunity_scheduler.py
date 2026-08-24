from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ledger import latest_object, record_event, record_object, utc_now
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE, scan_universe
from opportunity_dispatch import dispatch_ranked_queue


router = APIRouter()

CONFIG_ID = "opportunity_automation_default"
CONFIG_TYPE = "opportunity_automation_config"
DEFAULT_INTERVAL_MINUTES = 240
MIN_INTERVAL_MINUTES = 240
MAX_INTERVAL_MINUTES = 24 * 60
DEFAULT_NEWS_LIMIT = 8
MAX_NEWS_LIMIT = 12
DEFAULT_MAX_CANDIDATES = 10
MAX_AUTO_DISPATCH = 1
SCHEDULER_POLL_SECONDS = 60

_scheduler_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None


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


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def default_config() -> dict[str, Any]:
    return {
        "opportunity_automation_config_id": CONFIG_ID,
        # User asked for unattended hunting. Scanning is public-data-only and bounded.
        "enabled": _bool_env("IIOS_OPPORTUNITY_AUTO_SCAN", True),
        # LLM dispatch stays opt-in. Scanning may rank candidates but does not run agents automatically.
        "auto_dispatch_enabled": _bool_env("IIOS_OPPORTUNITY_AUTO_DISPATCH", False),
        "interval_minutes": DEFAULT_INTERVAL_MINUTES,
        "news_limit": DEFAULT_NEWS_LIMIT,
        "max_candidates": DEFAULT_MAX_CANDIDATES,
        "dispatch_limit": 1,
        "last_scan_at": None,
        "last_scan_status": None,
        "last_error": None,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def normalize_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    existing = latest_object(CONFIG_TYPE, case_id=OPPORTUNITY_LEDGER_CASE) or default_config()

    try:
        interval = int(payload.get("interval_minutes", existing.get("interval_minutes", DEFAULT_INTERVAL_MINUTES)))
        news_limit = int(payload.get("news_limit", existing.get("news_limit", DEFAULT_NEWS_LIMIT)))
        max_candidates = int(payload.get("max_candidates", existing.get("max_candidates", DEFAULT_MAX_CANDIDATES)))
        dispatch_limit = int(payload.get("dispatch_limit", existing.get("dispatch_limit", 1)))
    except (TypeError, ValueError):
        raise ValueError("Automation numeric settings must be integers")

    interval = max(MIN_INTERVAL_MINUTES, min(interval, MAX_INTERVAL_MINUTES))
    news_limit = max(2, min(news_limit, MAX_NEWS_LIMIT))
    max_candidates = max(1, min(max_candidates, DEFAULT_MAX_CANDIDATES))
    dispatch_limit = max(1, min(dispatch_limit, MAX_AUTO_DISPATCH))

    config = {
        **existing,
        "opportunity_automation_config_id": CONFIG_ID,
        "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
        "auto_dispatch_enabled": bool(
            payload.get("auto_dispatch_enabled", existing.get("auto_dispatch_enabled", False))
        ),
        "interval_minutes": interval,
        "news_limit": news_limit,
        "max_candidates": max_candidates,
        "dispatch_limit": dispatch_limit,
        "updated_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    return config


def save_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    config = normalize_config(payload)
    record_object(CONFIG_ID, CONFIG_TYPE, OPPORTUNITY_LEDGER_CASE, config)
    record_event(
        OPPORTUNITY_LEDGER_CASE,
        "OPPORTUNITY_AUTOMATION_CONFIG_UPDATED",
        entity_id=CONFIG_ID,
        payload={
            "enabled": config["enabled"],
            "auto_dispatch_enabled": config["auto_dispatch_enabled"],
            "interval_minutes": config["interval_minutes"],
            "dispatch_limit": config["dispatch_limit"],
            "auto_trade_authority": False,
        },
    )
    return config


def current_config() -> dict[str, Any]:
    return latest_object(CONFIG_TYPE, case_id=OPPORTUNITY_LEDGER_CASE) or default_config()


def _is_due(config: dict[str, Any], now: datetime | None = None) -> bool:
    if not config.get("enabled"):
        return False
    now = now or datetime.now(timezone.utc)
    last = _parse_time(config.get("last_scan_at"))
    if last is None:
        return True
    interval = max(MIN_INTERVAL_MINUTES, int(config.get("interval_minutes") or DEFAULT_INTERVAL_MINUTES))
    return (now - last).total_seconds() >= interval * 60


def run_automation_cycle(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = normalize_config(config or current_config())
    if not config.get("enabled"):
        return {
            "status": "skipped",
            "reason": "AUTOMATION_DISABLED",
            "paper_mode": True,
            "auto_trade_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    try:
        scan = scan_universe(
            news_limit=config["news_limit"],
            max_candidates=config["max_candidates"],
        )
        if config.get("auto_dispatch_enabled"):
            dispatch = dispatch_ranked_queue(limit=config["dispatch_limit"])
        else:
            dispatch = {
                "status": "NOT_RUN",
                "reason": "AUTO_DISPATCH_DISABLED",
                "requested": 0,
                "selected": 0,
                "results": [],
                "paper_mode": True,
                "trade_execution_permission": False,
                "live_execution": False,
            }
        updated = {
            **config,
            "last_scan_at": utc_now(),
            "last_scan_status": "complete",
            "last_error": None,
            "updated_at": utc_now(),
        }
        record_object(CONFIG_ID, CONFIG_TYPE, OPPORTUNITY_LEDGER_CASE, updated)
        record_event(
            OPPORTUNITY_LEDGER_CASE,
            "OPPORTUNITY_AUTOMATION_CYCLE_COMPLETE",
            entity_id=scan.get("opportunity_scan_id"),
            payload={
                "scanned_count": scan.get("scanned_count"),
                "queued_count": scan.get("queued_count"),
                "auto_dispatch_enabled": updated["auto_dispatch_enabled"],
                "dispatch_selected": dispatch.get("selected", 0),
                "auto_trade_authority": False,
                "trade_execution_permission": False,
            },
        )
        return {
            "status": "complete",
            "scan": scan,
            "dispatch": dispatch,
            "config": updated,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
    except Exception as exc:
        updated = {
            **config,
            "last_scan_at": utc_now(),
            "last_scan_status": "error",
            "last_error": f"{type(exc).__name__}: {exc}",
            "updated_at": utc_now(),
        }
        record_object(CONFIG_ID, CONFIG_TYPE, OPPORTUNITY_LEDGER_CASE, updated)
        record_event(
            OPPORTUNITY_LEDGER_CASE,
            "OPPORTUNITY_AUTOMATION_CYCLE_FAILED",
            entity_id=CONFIG_ID,
            payload={
                "error": updated["last_error"],
                "auto_trade_authority": False,
                "trade_execution_permission": False,
            },
        )
        return {
            "status": "error",
            "error": updated["last_error"],
            "config": updated,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }


def refresh_if_due() -> dict[str, Any]:
    config = current_config()
    if not _is_due(config):
        return {
            "status": "not_due",
            "config": config,
            "paper_mode": True,
            "auto_trade_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
    return run_automation_cycle(config)


def _scheduler_loop() -> None:
    while not _scheduler_stop.wait(SCHEDULER_POLL_SECONDS):
        refresh_if_due()


def start_opportunity_scheduler() -> None:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        name="iios-opportunity-scanner",
        daemon=True,
    )
    _scheduler_thread.start()


def stop_opportunity_scheduler() -> None:
    _scheduler_stop.set()


@router.on_event("startup")
def start_router_opportunity_scheduler() -> None:
    start_opportunity_scheduler()


@router.on_event("shutdown")
def stop_router_opportunity_scheduler() -> None:
    stop_opportunity_scheduler()


@router.get("/opportunities/automation")
def opportunity_automation_status():
    return {
        "config": current_config(),
        "scheduler_running": bool(_scheduler_thread and _scheduler_thread.is_alive()),
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/opportunities/automation")
def update_opportunity_automation(request: dict[str, Any] = Body(default={})):
    try:
        return save_config(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/opportunities/automation/run-now")
def run_opportunity_automation_now():
    return run_automation_cycle(current_config())
