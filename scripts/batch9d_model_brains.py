from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ledger import DB_PATH, utc_now


WORKING_WINDOW_SECONDS = 300
RECENT_WINDOW_SECONDS = 90


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


def _age_seconds(value: Any) -> float:
    parsed = _parse_time(value)
    if parsed is None:
        return float("inf")
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _latest_events(limit: int = 200) -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT event_type, case_id, entity_id, payload_json, created_at
            FROM audit_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(20, min(int(limit), 1000)),),
        ).fetchall()
    finally:
        connection.close()

    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            payload = {}
        output.append(
            {
                "event_type": row["event_type"],
                "case_id": row["case_id"],
                "entity_id": row["entity_id"],
                "payload": payload if isinstance(payload, dict) else {},
                "created_at": row["created_at"],
            }
        )
    return output


def _latest_model_context() -> dict[str, Any]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT payload_json, created_at
            FROM ledger_objects
            WHERE object_type='high_speed_market_model_context'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    if not row:
        return {}
    try:
        payload = json.loads(row["payload_json"])
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {**payload, "_ledger_created_at": row["created_at"]}


def _latest_of(events: list[dict[str, Any]], types: set[str]) -> dict[str, Any] | None:
    for event in events:
        if str(event.get("event_type") or "") in types:
            return event
    return None


def _state_from_events(
    *,
    events: list[dict[str, Any]],
    started: set[str],
    completed: set[str],
    failed: set[str],
    configured: bool,
) -> tuple[str, dict[str, Any] | None]:
    latest = _latest_of(events, started | completed | failed)
    if latest is None:
        return ("ARMED" if configured else "OFFLINE"), None

    event_type = str(latest.get("event_type") or "")
    age = _age_seconds(latest.get("created_at"))
    if event_type in failed and age <= WORKING_WINDOW_SECONDS:
        return "BLOCKED", latest
    if event_type in started and age <= WORKING_WINDOW_SECONDS:
        return "WORKING", latest
    if event_type in completed and age <= RECENT_WINDOW_SECONDS:
        return "RECENT", latest
    return ("ARMED" if configured else "OFFLINE"), latest


def _key_present(*names: str) -> bool:
    return any(bool(str(os.getenv(name) or "").strip()) for name in names)


def build_model_brains() -> dict[str, Any]:
    events = _latest_events()
    context = _latest_model_context()

    gpt_configured = _key_present("OPENAI_API_KEY", "OPENAI_ADMIN_KEY")
    grok_configured = bool(
        context.get("grok_configured") is True
        or _key_present("IIOS_GROK_API_KEY", "XAI_API_KEY")
    )
    gemini_configured = bool(
        context.get("gemini_configured") is True
        or _key_present("IIOS_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    )

    gpt_state, gpt_event = _state_from_events(
        events=events,
        started={"HIGH_SPEED_CASE_FLOOR_STARTED"},
        completed={"EIGHT_AGENT_ORCHESTRATION_COMPLETE", "HIGH_SPEED_CASE_FLOOR_COMPLETE"},
        failed={"HIGH_SPEED_CASE_FLOOR_FAILED_CLOSED", "AGENT_FAILED_CLOSED"},
        configured=gpt_configured,
    )

    shared_state, shared_event = _state_from_events(
        events=events,
        started={"HIGH_SPEED_MODEL_RESEARCH_STARTED"},
        completed={"HIGH_SPEED_MODEL_RESEARCH_COMPLETE"},
        failed={"HIGH_SPEED_MODEL_RESEARCH_FAILED_CLOSED"},
        configured=(grok_configured or gemini_configured),
    )

    completion_payload = (shared_event or {}).get("payload") or {}

    def provider_state(provider: str, configured: bool) -> str:
        if not configured:
            return "OFFLINE"
        if shared_state == "WORKING":
            return "WORKING"
        if shared_state == "BLOCKED":
            return "BLOCKED"
        if shared_state == "RECENT":
            satisfied = completion_payload.get(f"{provider}_execution_satisfied")
            return "RECENT" if satisfied is True else "BLOCKED"
        return "ARMED"

    grok_state = provider_state("grok", grok_configured)
    gemini_state = provider_state("gemini", gemini_configured)

    providers = [
        {
            "key": "gpt",
            "alias": "The House Brain",
            "provider": "OpenAI GPT",
            "role": "8 specialist desks + Investment Committee",
            "state": gpt_state,
            "configured": gpt_configured,
            "last_event": (gpt_event or {}).get("event_type"),
            "last_event_at": (gpt_event or {}).get("created_at"),
            "last_case_id": (gpt_event or {}).get("case_id"),
            "trade_execution_permission": False,
            "live_execution": False,
        },
        {
            "key": "grok",
            "alias": "The Wire",
            "provider": "xAI Grok",
            "role": "X Search + Web Search catalyst intelligence",
            "state": grok_state,
            "configured": grok_configured,
            "last_event": (shared_event or {}).get("event_type"),
            "last_event_at": (shared_event or {}).get("created_at") or context.get("created_at"),
            "candidate_count": context.get("grok_candidate_count"),
            "execution_satisfied": context.get("grok_execution_satisfied"),
            "trade_execution_permission": False,
            "live_execution": False,
        },
        {
            "key": "gemini",
            "alias": "The Books",
            "provider": "Google Gemini",
            "role": "Google-grounded source research + deep synthesis",
            "state": gemini_state,
            "configured": gemini_configured,
            "last_event": (shared_event or {}).get("event_type"),
            "last_event_at": (shared_event or {}).get("created_at") or context.get("created_at"),
            "candidate_count": context.get("gemini_candidate_count"),
            "execution_satisfied": context.get("gemini_execution_satisfied"),
            "trade_execution_permission": False,
            "live_execution": False,
        },
    ]

    return {
        "generated_at": utc_now(),
        "providers": providers,
        "model_context_present": bool(context),
        "model_execution_mode": context.get("model_execution_mode"),
        "provider_errors": context.get("provider_errors") or {},
        "read_only": True,
        "paper_mode": True,
        "broker_connected": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
