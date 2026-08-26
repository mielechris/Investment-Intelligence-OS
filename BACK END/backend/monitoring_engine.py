from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from openai import OpenAI

from evidence_engine import build_packet
from capital_entry_watch import refresh_capital_entry_watch
from learning_loop import record_position_monitor, record_thesis_monitor
from ledger import DB_PATH, get_object, latest_object, list_objects, record_event, record_object
from source_ingestion import ingest_sources
from provider_hardening import fetch_market_quote


router = APIRouter()
PAPER_MODE = True
DEFAULT_INTERVAL_MINUTES = 240
MIN_INTERVAL_MINUTES = 60
SCHEDULER_POLL_SECONDS = 60
_scheduler_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rows_by_type(object_type: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? ORDER BY created_at DESC",
            (object_type,),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _default_sources(topic: str) -> list[dict[str, Any]]:
    query = topic[:180].strip()
    return [
        {"source": "gdelt_news", "params": {"query": query, "limit": 12, "timespan": "24h"}},
        {"source": "fred_series", "params": {"series_id": "DGS10", "limit": 4}},
    ]


def _fetch_stooq_quote(
    symbol: str,
) -> dict[str, Any]:
    """
    Backward-compatible market quote wrapper.

    Legacy callers retain the old function name, but
    governed monitoring now uses the hardened market
    provider rather than relying on Stooq directly.
    """
    return fetch_market_quote(symbol)


def configure_profile(request: dict[str, Any]) -> dict[str, Any]:
    case_id = str(request.get("case_id", "")).strip()
    case = _require_case(case_id)
    interval = int(request.get("interval_minutes") or DEFAULT_INTERVAL_MINUTES)
    interval = max(MIN_INTERVAL_MINUTES, interval)
    source_requests = request.get("source_requests") if isinstance(request.get("source_requests"), list) else _default_sources(case.get("topic", ""))
    existing = latest_object("monitor_profile", case_id=case_id)
    profile_id = (existing or {}).get("monitor_profile_id") or f"monitor_profile_{uuid4().hex}"
    profile = {
        "monitor_profile_id": profile_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "enabled": bool(request.get("enabled", True)),
        "interval_minutes": interval,
        "source_requests": source_requests,
        "ticker": str(request.get("ticker", (existing or {}).get("ticker", ""))).strip(),
        "direction": str(request.get("direction", (existing or {}).get("direction", "UNSPECIFIED"))).upper(),
        "reference_price": _safe_float(request.get("reference_price", (existing or {}).get("reference_price"))),
        "analysis_mode": str(request.get("analysis_mode", (existing or {}).get("analysis_mode", "llm"))).lower(),
        "last_refresh_at": (existing or {}).get("last_refresh_at"),
        "last_refresh_status": (existing or {}).get("last_refresh_status"),
        "created_at": (existing or {}).get("created_at") or utc_now(),
        "updated_at": utc_now(),
        "paper_mode": PAPER_MODE,
    }
    if profile["direction"] not in {"LONG", "SHORT", "UNSPECIFIED"}:
        raise HTTPException(status_code=422, detail="direction must be LONG, SHORT, or UNSPECIFIED")
    if profile["analysis_mode"] not in {"llm", "deterministic"}:
        raise HTTPException(status_code=422, detail="analysis_mode must be llm or deterministic")
    record_object(profile_id, "monitor_profile", case_id, profile, parent_id=case_id, topic=case.get("topic"))
    record_event(case_id, "MONITOR_PROFILE_UPDATED", entity_id=profile_id, payload={"enabled": profile["enabled"], "interval_minutes": interval, "ticker": profile["ticker"]})
    return profile


def _falsifier_review(case_id: str, evidence_items: list[dict[str, Any]], analysis_mode: str) -> dict[str, Any]:
    agents = list_objects(case_id, "agent_result")
    falsifiers = [
        {"agent_key": item.get("agent_key"), "falsifier": item.get("falsifier")}
        for item in agents
        if item.get("falsifier")
    ]
    if analysis_mode == "deterministic" or not evidence_items:
        return {"falsifiers_triggered": [], "catalyst_status": "UNKNOWN", "summary": "No semantic LLM surveillance review performed."}

    prompt = f"""
You are the Thesis Surveillance Analyst inside a PAPER-ONLY Investment Intelligence OS.
Compare fresh evidence with the stored falsifiers from the original specialist analysis.
Do not infer that a falsifier triggered unless the new evidence materially supports it.

STORED FALSIFIERS:
{json.dumps(falsifiers, indent=2, default=str)}

FRESH EVIDENCE:
{json.dumps(evidence_items, indent=2, default=str)}

Return ONLY JSON:
{{"falsifiers_triggered":["agent_key: concise reason"],"catalyst_status":"ON_TRACK|MISSED|UNKNOWN|ACHIEVED","summary":"brief surveillance assessment"}}
"""
    response = OpenAI().responses.create(model="gpt-5.6-luna", input=prompt)
    try:
        output = json.loads(response.output_text)
        if not isinstance(output, dict):
            raise ValueError
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"falsifiers_triggered": [], "catalyst_status": "UNKNOWN", "summary": "Surveillance output could not be structured."}
    triggered = output.get("falsifiers_triggered") if isinstance(output.get("falsifiers_triggered"), list) else []
    catalyst = str(output.get("catalyst_status", "UNKNOWN")).upper()
    if catalyst not in {"ON_TRACK", "MISSED", "UNKNOWN", "ACHIEVED"}:
        catalyst = "UNKNOWN"
    return {"falsifiers_triggered": [str(item) for item in triggered], "catalyst_status": catalyst, "summary": str(output.get("summary", ""))}


def refresh_profile(profile: dict[str, Any]) -> dict[str, Any]:
    case_id = str(profile.get("case_id", ""))
    case = _require_case(case_id)
    ingestion = ingest_sources(profile.get("source_requests") or [])
    quote = _fetch_stooq_quote(str(profile.get("ticker", "")))
    raw_evidence = list(ingestion.get("evidence_items") or []) + list(quote.get("items") or [])
    packet = build_packet(raw_evidence)

    snapshot_id = f"snapshot_{uuid4().hex}"
    snapshot = {
        "monitor_snapshot_id": snapshot_id,
        "monitor_profile_id": profile.get("monitor_profile_id"),
        "case_id": case_id,
        "topic": case.get("topic"),
        "ingestion": ingestion,
        "quote": quote,
        "evidence_packet": packet,
        "created_at": utc_now(),
        "paper_mode": PAPER_MODE,
    }
    record_object(snapshot_id, "monitor_snapshot", case_id, snapshot, parent_id=profile.get("monitor_profile_id"), topic=case.get("topic"))
    record_event(case_id, "AUTOMATIC_EVIDENCE_REFRESH", entity_id=snapshot_id, payload={"evidence_count": packet["summary"]["evidence_count"], "successful_sources": ingestion.get("successful_sources"), "quote_status": quote.get("status")})

    position = record_position_monitor({
        "case_id": case_id,
        "direction": profile.get("direction", "UNSPECIFIED"),
        "reference_price": profile.get("reference_price"),
        "current_price": quote.get("current_price"),
        "evidence": raw_evidence,
        "observations": ["Automatic monitoring refresh"],
    })
    surveillance = _falsifier_review(case_id, packet["items"], str(profile.get("analysis_mode", "llm")))
    thesis = record_thesis_monitor({
        "case_id": case_id,
        "falsifiers_triggered": surveillance["falsifiers_triggered"],
        "catalyst_status": surveillance["catalyst_status"],
        "evidence": raw_evidence,
        "notes": surveillance["summary"],
    })

    # Reuse the exact quote already fetched by the
    # monitor. No second market-data request is needed.
    capital_entry_watch = (
        refresh_capital_entry_watch(
            case_id,
            quote=quote,
        )
    )

    updated = {**profile, "last_refresh_at": utc_now(), "last_refresh_status": "complete", "updated_at": utc_now()}
    record_object(updated["monitor_profile_id"], "monitor_profile", case_id, updated, parent_id=case_id, topic=case.get("topic"))
    record_event(case_id, "AUTO_MONITOR_COMPLETE", entity_id=snapshot_id, payload={"thesis_status": thesis.get("thesis_status"), "return_pct": position.get("return_pct")})
    return {
        "profile": updated,
        "snapshot": snapshot,
        "position": position,
        "thesis": thesis,
        "surveillance": surveillance,
        "capital_entry_watch": capital_entry_watch,
    }


def _is_due(profile: dict[str, Any], now: datetime | None = None) -> bool:
    if not profile.get("enabled"):
        return False
    now = now or datetime.now(timezone.utc)
    last = _parse_time(profile.get("last_refresh_at"))
    if last is None:
        return True
    interval = max(MIN_INTERVAL_MINUTES, int(profile.get("interval_minutes") or DEFAULT_INTERVAL_MINUTES))
    return (now - last).total_seconds() >= interval * 60


def refresh_due_profiles() -> dict[str, Any]:
    profiles = _rows_by_type("monitor_profile")
    # record_object replaces profiles by ID, but guard against legacy duplicates defensively
    latest_by_case: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        latest_by_case.setdefault(str(profile.get("case_id")), profile)
    due = [profile for profile in latest_by_case.values() if _is_due(profile)]
    results = []
    for profile in due:
        try:
            results.append({"case_id": profile.get("case_id"), "status": "complete", "result": refresh_profile(profile)})
        except Exception as exc:
            case_id = str(profile.get("case_id", ""))
            record_event(case_id, "AUTO_MONITOR_FAILED", entity_id=profile.get("monitor_profile_id"), payload={"error": f"{type(exc).__name__}: {exc}"})
            results.append({"case_id": case_id, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return {"checked_profiles": len(latest_by_case), "due_profiles": len(due), "results": results, "checked_at": utc_now()}


def _scheduler_loop() -> None:
    while not _scheduler_stop.wait(SCHEDULER_POLL_SECONDS):
        refresh_due_profiles()


def start_scheduler() -> None:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, name="iios-auto-monitor", daemon=True)
    _scheduler_thread.start()


def stop_scheduler() -> None:
    _scheduler_stop.set()


def build_dashboard(limit: int = 25) -> dict[str, Any]:
    cases = _rows_by_type("case")[: max(1, min(limit, 100))]
    rows = []
    for case in cases:
        case_id = case.get("case_id")
        profile = latest_object("monitor_profile", case_id=case_id)
        position = latest_object("position_monitor", case_id=case_id)
        thesis = latest_object("thesis_monitor", case_id=case_id)
        reunderwrite = latest_object("reunderwrite", case_id=case_id)
        postmortem = latest_object("postmortem", case_id=case_id)
        decision = latest_object("committee_decision", case_id=case_id)
        snapshot = latest_object("monitor_snapshot", case_id=case_id)
        if postmortem:
            health = "CLOSED"
        elif thesis:
            health = thesis.get("thesis_status", "UNKNOWN")
        elif profile and profile.get("enabled"):
            health = "AUTO_WATCH"
        else:
            health = "UNMONITORED"
        rows.append({
            "case_id": case_id,
            "topic": case.get("topic"),
            "created_at": case.get("created_at"),
            "health": health,
            "committee_disposition": (decision or {}).get("disposition"),
            "committee_confidence": (decision or {}).get("confidence"),
            "evidence_quality": (case.get("evidence_summary") or {}).get("average_quality_score"),
            "monitoring_enabled": bool((profile or {}).get("enabled")),
            "interval_minutes": (profile or {}).get("interval_minutes"),
            "ticker": (profile or {}).get("ticker"),
            "last_refresh_at": (profile or {}).get("last_refresh_at"),
            "latest_return_pct": (position or {}).get("return_pct"),
            "thesis_flags": (thesis or {}).get("flags", []),
            "latest_action": (reunderwrite or {}).get("action"),
            "outcome": (postmortem or {}).get("outcome"),
            "last_snapshot_id": (snapshot or {}).get("monitor_snapshot_id"),
            "paper_mode": True,
        })
    return {"cases": rows, "count": len(rows), "scheduler_running": bool(_scheduler_thread and _scheduler_thread.is_alive()), "generated_at": utc_now()}


@router.get("/monitoring/status")
def monitoring_status():
    profiles = _rows_by_type("monitor_profile")
    return {"scheduler_running": bool(_scheduler_thread and _scheduler_thread.is_alive()), "profiles": len(profiles), "poll_seconds": SCHEDULER_POLL_SECONDS, "minimum_interval_minutes": MIN_INTERVAL_MINUTES, "paper_mode": True}


@router.post("/monitoring/configure")
def monitoring_configure(request: dict = Body(...)):
    return configure_profile(request)


@router.post("/monitoring/refresh/{case_id}")
def monitoring_refresh(case_id: str):
    profile = latest_object("monitor_profile", case_id=case_id)
    if not profile:
        raise HTTPException(status_code=409, detail="Monitoring profile required")
    return refresh_profile(profile)


@router.post("/monitoring/refresh-due")
def monitoring_refresh_due():
    return refresh_due_profiles()


@router.get("/monitoring/dashboard")
def monitoring_dashboard(limit: int = 25):
    return build_dashboard(limit)
