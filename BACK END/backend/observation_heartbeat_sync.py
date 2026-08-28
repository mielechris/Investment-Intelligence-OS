from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ledger import record_event, record_object, utc_now


router = APIRouter()
POLICY_VERSION = "batch10d-observation-heartbeat-sync-v1"
OBSERVATION_CASE_ID = "observation_operations"
OBSERVATION_STATE_ID = "observation_operations_state_v1"
OBSERVATION_STATE_TYPE = "observation_operations_state"


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


def persist_observation_checkpoint(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("checkpoint must be an object")

    completed_at = _parse_time(payload.get("last_cycle_completed_at"))
    if completed_at is None:
        raise ValueError("last_cycle_completed_at must be a valid timestamp")

    sanitized = {
        **payload,
        "observation_operations_state_id": OBSERVATION_STATE_ID,
        "observation_heartbeat_source": "BATCH9A_BACKEND_8002_BRIDGE",
        "observation_heartbeat_received_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }

    record_object(
        OBSERVATION_STATE_ID,
        OBSERVATION_STATE_TYPE,
        OBSERVATION_CASE_ID,
        sanitized,
        topic="Batch 9A observation operations",
    )
    record_event(
        OBSERVATION_CASE_ID,
        "OBSERVATION_HEARTBEAT_SYNCED",
        entity_id=OBSERVATION_STATE_ID,
        payload={
            "last_cycle_completed_at": sanitized.get("last_cycle_completed_at"),
            "market_phase": sanitized.get("market_phase"),
            "last_scan_status": sanitized.get("last_scan_status"),
            "last_scan_count": sanitized.get("last_scan_count"),
            "last_queue_count": sanitized.get("last_queue_count"),
            "promoted_case_count": sanitized.get("promoted_case_count"),
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )

    return {
        "status": "accepted",
        "policy_version": POLICY_VERSION,
        "last_cycle_completed_at": sanitized.get("last_cycle_completed_at"),
        "market_phase": sanitized.get("market_phase"),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/observation-heartbeat/checkpoint")
def observation_heartbeat_checkpoint(request: dict[str, Any] = Body(...)):
    try:
        return persist_observation_checkpoint(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
