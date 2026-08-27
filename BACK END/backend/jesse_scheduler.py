from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body

from dislocation_intelligence import run_dislocation_scan
from jesse_outcome_attribution import (
    refresh_all_jesse_outcome_attributions,
    router as jesse_outcome_router,
)
from jesse_paper_fund_bridge import dispatch_jesse_top_three
from jesse_source_acquisition import (
    current_governed_universe,
    discover_public_institutional_research,
    ingest_authorized_research_inbox,
    read_fed_probability_source,
)
from ledger import DB_PATH, latest_object, record_event, record_object, utc_now
from macro_policy_intelligence import run_tariff_transmission_scan
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE
from provider_hardening import fetch_market_quote

router = APIRouter()
router.include_router(jesse_outcome_router)
SCHEDULER_CASE = "jesse_intelligence_scheduler"
STATE_ID = "jesse_scheduler_state"
STATE_TYPE = "jesse_scheduler_state"
POLL_SECONDS = 60
PT = ZoneInfo("America/Los_Angeles")

_stop = threading.Event()
_thread: threading.Thread | None = None

DEFAULTS = {
    "enabled": True,
    "public_research_hour_pt": 6,
    "dislocation_hour_pt": 11,
    "dislocation_minute_pt": 0,
    "tariff_refresh_minutes": 60,
    "fed_refresh_minutes": 60,
    "inbox_refresh_minutes": 15,
    "followup_hour_pt": 13,
    "followup_minute_pt": 15,
}


def _rows(object_type: str, limit: int = 1000) -> list[dict[str, Any]]:
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT ?",
            (object_type, limit),
        ).fetchall()
    finally:
        db.close()
    return [json.loads(r["payload_json"]) for r in rows]


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def default_state() -> dict[str, Any]:
    return {
        "jesse_scheduler_state_id": STATE_ID,
        **DEFAULTS,
        "last_public_research_date": None,
        "last_dislocation_date": None,
        "last_tariff_at": None,
        "last_fed_at": None,
        "last_inbox_at": None,
        "last_followup_date": None,
        "last_error": None,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def state() -> dict[str, Any]:
    return latest_object(STATE_TYPE, case_id=SCHEDULER_CASE) or default_state()


def save_state(value: dict[str, Any]) -> dict[str, Any]:
    payload = {
        **default_state(),
        **value,
        "jesse_scheduler_state_id": STATE_ID,
        "updated_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(STATE_ID, STATE_TYPE, SCHEDULER_CASE, payload)
    return payload


def _elapsed_minutes(stamp: Any, now: datetime) -> float | None:
    prior = _parse(stamp)
    if prior is None:
        return None
    return max(0.0, (now.astimezone(timezone.utc) - prior).total_seconds() / 60.0)


def should_run_daily(last_date: Any, *, hour: int, minute: int, now_pt: datetime) -> bool:
    if now_pt.weekday() >= 5:
        return False
    if str(last_date or "") == now_pt.date().isoformat():
        return False
    return (now_pt.hour, now_pt.minute) >= (int(hour), int(minute))


def _existing_outcome(scan_id: str, ticker: str) -> bool:
    return any(
        row.get("dislocation_scan_id") == scan_id and row.get("ticker") == ticker
        for row in _rows("dislocation_outcome", 5000)
    )


def settle_dislocation_outcomes(now_pt: datetime | None = None) -> dict[str, Any]:
    now_pt = now_pt or datetime.now(timezone.utc).astimezone(PT)
    settled = []
    skipped = 0
    for scan in _rows("dislocation_scan", 250):
        created = _parse(scan.get("created_at"))
        if created is None or created.astimezone(PT).date() >= now_pt.date():
            continue
        scan_id = str(scan.get("dislocation_scan_id") or "")
        for candidate in scan.get("top_three") or []:
            ticker = str(candidate.get("ticker") or "").upper()
            baseline = candidate.get("current_price")
            if not ticker or baseline in (None, 0) or _existing_outcome(scan_id, ticker):
                skipped += 1
                continue
            quote = fetch_market_quote(ticker)
            price = quote.get("current_price")
            if price is None:
                skipped += 1
                continue
            return_pct = (float(price) / float(baseline) - 1.0) * 100.0
            outcome_id = f"dislocation_outcome_{uuid4().hex}"
            outcome = {
                "dislocation_outcome_id": outcome_id,
                "dislocation_scan_id": scan_id,
                "ticker": ticker,
                "baseline_price": baseline,
                "followup_price": price,
                "return_pct": round(return_pct, 4),
                "target_upside_pct": 5.0,
                "target_hit": return_pct >= 5.0,
                "original_recommendation": candidate.get("recommendation"),
                "financial_strength_score": candidate.get("financial_strength_score"),
                "followup_quote_provider": quote.get("provider"),
                "scan_created_at": scan.get("created_at"),
                "measured_at": utc_now(),
                "paper_mode": True,
                "trade_execution_permission": False,
                "live_execution": False,
            }
            record_object(outcome_id, "dislocation_outcome", OPPORTUNITY_LEDGER_CASE, outcome)
            settled.append(outcome)
    return {
        "settled_count": len(settled),
        "skipped_count": skipped,
        "outcomes": settled,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def dislocation_calibration() -> dict[str, Any]:
    rows = [r for r in _rows("dislocation_outcome", 5000) if r.get("target_hit") is not None]
    hits = sum(1 for r in rows if r.get("target_hit") is True)
    avg = sum(float(r.get("return_pct") or 0.0) for r in rows) / len(rows) if rows else None
    return {
        "observation_count": len(rows),
        "target_hit_count": hits,
        "target_hit_rate": round(hits / len(rows), 4) if rows else None,
        "average_next_day_return_pct": round(avg, 4) if avg is not None else None,
        "target_upside_pct": 5.0,
        "calibrated": len(rows) >= 30,
        "minimum_calibration_observations": 30,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def run_cycle(force_jobs: list[str] | None = None) -> dict[str, Any]:
    s = state()
    if not s.get("enabled"):
        return {"status": "disabled", "state": s, "live_execution": False}

    now = datetime.now(timezone.utc)
    now_pt = now.astimezone(PT)
    force = {str(x).lower() for x in (force_jobs or [])}
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    jobs: list[tuple[str, Any]] = []

    if "public_research" in force or should_run_daily(
        s.get("last_public_research_date"),
        hour=int(s.get("public_research_hour_pt") or 6),
        minute=0,
        now_pt=now_pt,
    ):
        def public_research():
            result = discover_public_institutional_research(3)
            s["last_public_research_date"] = now_pt.date().isoformat()
            return result
        jobs.append(("public_research", public_research))

    inbox_elapsed = _elapsed_minutes(s.get("last_inbox_at"), now)
    if "authorized_inbox" in force or inbox_elapsed is None or inbox_elapsed >= int(s.get("inbox_refresh_minutes") or 15):
        def inbox():
            result = ingest_authorized_research_inbox()
            s["last_inbox_at"] = now.isoformat()
            return result
        jobs.append(("authorized_inbox", inbox))

    fed_elapsed = _elapsed_minutes(s.get("last_fed_at"), now)
    if "fed_probability" in force or fed_elapsed is None or fed_elapsed >= int(s.get("fed_refresh_minutes") or 60):
        def fed():
            result = read_fed_probability_source()
            s["last_fed_at"] = now.isoformat()
            return result
        jobs.append(("fed_probability", fed))

    tariff_elapsed = _elapsed_minutes(s.get("last_tariff_at"), now)
    if "tariff" in force or tariff_elapsed is None or tariff_elapsed >= int(s.get("tariff_refresh_minutes") or 60):
        def tariff():
            result = run_tariff_transmission_scan({})
            s["last_tariff_at"] = now.isoformat()
            return result
        jobs.append(("tariff", tariff))

    if "dislocation" in force or should_run_daily(
        s.get("last_dislocation_date"),
        hour=int(s.get("dislocation_hour_pt") or 11),
        minute=int(s.get("dislocation_minute_pt") or 0),
        now_pt=now_pt,
    ):
        def dislocation():
            universe = current_governed_universe() or {}
            request: dict[str, Any] = {"count": 60, "promote_top_three": False}
            if universe.get("symbols"):
                request["universe_symbols"] = universe["symbols"]
            result = run_dislocation_scan(request)
            bridge = dispatch_jesse_top_three(result)
            s["last_dislocation_date"] = now_pt.date().isoformat()
            return {**result, "bridge": bridge}
        jobs.append(("dislocation", dislocation))

    if "followup" in force or should_run_daily(
        s.get("last_followup_date"),
        hour=int(s.get("followup_hour_pt") or 13),
        minute=int(s.get("followup_minute_pt") or 15),
        now_pt=now_pt,
    ):
        def followup():
            result = settle_dislocation_outcomes(now_pt)
            attribution = refresh_all_jesse_outcome_attributions()
            s["last_followup_date"] = now_pt.date().isoformat()
            return {**result, "attribution": attribution}
        jobs.append(("followup", followup))

    for name, func in jobs:
        try:
            results[name] = func()
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"

    s["last_error"] = errors or None
    s = save_state(s)
    cycle_id = f"jesse_scheduler_cycle_{uuid4().hex}"
    cycle = {
        "jesse_scheduler_cycle_id": cycle_id,
        "jobs_attempted": [name for name, _ in jobs],
        "results": results,
        "errors": errors,
        "state": s,
        "calibration": dislocation_calibration(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(cycle_id, "jesse_scheduler_cycle", SCHEDULER_CASE, cycle)
    record_event(
        SCHEDULER_CASE,
        "JESSE_SCHEDULER_CYCLE_COMPLETE",
        entity_id=cycle_id,
        payload={
            "jobs_attempted": cycle["jobs_attempted"],
            "error_count": len(errors),
            "trade_execution_permission": False,
        },
    )
    return cycle


def _loop() -> None:
    while not _stop.wait(POLL_SECONDS):
        try:
            run_cycle()
        except Exception:
            pass


def start_jesse_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="iios-jesse-intelligence-scheduler", daemon=True)
    _thread.start()


def stop_jesse_scheduler() -> None:
    _stop.set()


@router.get("/intelligence/jesse-scheduler/status")
def scheduler_status():
    return {
        "state": state(),
        "scheduler_running": bool(_thread and _thread.is_alive()),
        "calibration": dislocation_calibration(),
        "latest_cycle": latest_object("jesse_scheduler_cycle", case_id=SCHEDULER_CASE),
        "timezone": "America/Los_Angeles",
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/intelligence/jesse-scheduler/run-now")
def scheduler_run_now(request: dict[str, Any] = Body(default={})):
    jobs = request.get("jobs")
    return run_cycle([str(x) for x in jobs] if isinstance(jobs, list) else [])


@router.post("/intelligence/jesse-scheduler/config")
def scheduler_config(request: dict[str, Any] = Body(default={})):
    current = state()
    allowed = {
        "enabled",
        "public_research_hour_pt",
        "dislocation_hour_pt",
        "dislocation_minute_pt",
        "tariff_refresh_minutes",
        "fed_refresh_minutes",
        "inbox_refresh_minutes",
        "followup_hour_pt",
        "followup_minute_pt",
    }
    for key in allowed:
        if key in request:
            current[key] = request[key]
    return save_state(current)
