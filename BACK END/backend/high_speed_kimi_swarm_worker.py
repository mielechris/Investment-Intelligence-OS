from __future__ import annotations

import json
import sqlite3
import time
from typing import Any
from uuid import uuid4

import kimi_swarm_bridge
from ledger import DB_PATH, latest_object, record_event, record_object, utc_now
from high_speed_market_radar import SWARM_REQUEST_TYPE


POLICY_VERSION = "batch9e-kimi-swarm-worker-v1"
WORKER_CASE_ID = "high_speed_kimi_swarm_worker"
STATE_ID = "high_speed_kimi_swarm_worker_state_v1"
STATE_TYPE = "high_speed_kimi_swarm_worker_state"
RESULT_TYPE = "kimi_swarm_research_result"


def _queued_requests(limit: int = 20) -> list[dict[str, Any]]:
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            """
            SELECT payload_json
            FROM ledger_objects
            WHERE object_type=?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (SWARM_REQUEST_TYPE, max(1, min(int(limit), 100))),
        ).fetchall()
    finally:
        db.close()

    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            value = json.loads(row["payload_json"])
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(value, dict) or value.get("status") != "QUEUED":
            continue
        request_id = str(value.get("kimi_swarm_research_request_id") or "")
        case_id = str(value.get("case_id") or "")
        if not request_id or not case_id:
            continue
        existing = latest_object(RESULT_TYPE, case_id=case_id)
        if existing and existing.get("source_request_id") == request_id:
            continue
        output.append(value)
    return output


def _swarm_prompt(request: dict[str, Any]) -> str:
    return json.dumps(
        {
            "role": "IIOS selective deep-research swarm",
            "objective": request.get("objective"),
            "ticker": request.get("ticker"),
            "source_context": request.get("source_context"),
            "instructions": [
                "Use multiple subagents where useful.",
                "Seek primary and credible sources before relying on secondary narrative.",
                "Test the strongest bull and bear explanations.",
                "Identify what changed versus what was already known.",
                "Explicitly list contradictions and unresolved evidence gaps.",
                "Do not recommend or execute a trade.",
                "Do not write to the IIOS repository.",
                "Return a concise research memorandum with source locators where available.",
            ],
        },
        ensure_ascii=False,
        default=str,
    )


def run_swarm_once() -> dict[str, Any]:
    started = time.perf_counter()
    provider = kimi_swarm_bridge.configuration_status()
    queued = _queued_requests(limit=20)

    if not provider.get("configured"):
        state = {
            "high_speed_kimi_swarm_worker_state_id": STATE_ID,
            "policy_version": POLICY_VERSION,
            "status": "PROVIDER_NOT_CONFIGURED",
            "queue_depth": len(queued),
            "processed": False,
            "paper_mode": True,
            "repo_write_access_granted": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(STATE_ID, STATE_TYPE, WORKER_CASE_ID, state)
        return state

    if not queued:
        state = {
            "high_speed_kimi_swarm_worker_state_id": STATE_ID,
            "policy_version": POLICY_VERSION,
            "status": "IDLE",
            "queue_depth": 0,
            "processed": False,
            "paper_mode": True,
            "repo_write_access_granted": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(STATE_ID, STATE_TYPE, WORKER_CASE_ID, state)
        return state

    request = queued[0]
    case_id = str(request.get("case_id") or "")
    request_id = str(request.get("kimi_swarm_research_request_id") or "")
    ticker = str(request.get("ticker") or "").upper()

    record_event(
        case_id,
        "KIMI_SWARM_RESEARCH_STARTED",
        entity_id=request_id,
        payload={
            "ticker": ticker,
            "repo_write_access_granted": False,
            "trade_execution_permission": False,
        },
    )

    try:
        result = kimi_swarm_bridge.run_native_swarm(
            prompt=_swarm_prompt(request),
            timeout_seconds=1800,
        )
        status = "COMPLETE" if result.get("status") == "CAPTURED" else "FAILED_CLOSED"
        error = None
    except Exception as exc:  # noqa: BLE001
        result = {}
        status = "FAILED_CLOSED"
        error = f"{type(exc).__name__}: {exc}"[:2000]

    result_id = f"kimi_swarm_result_{uuid4().hex}"
    payload = {
        "kimi_swarm_research_result_id": result_id,
        "source_request_id": request_id,
        "case_id": case_id,
        "ticker": ticker,
        "status": status,
        "output_text": str(result.get("output_text") or "")[:30000],
        "subagent_count": int(result.get("subagent_count") or 0),
        "usage": result.get("usage") or {},
        "session_id": result.get("session_id"),
        "error": error,
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "repo_write_access_granted": False,
        "capital_authority": False,
        "trade_signal": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(result_id, RESULT_TYPE, case_id, payload, parent_id=request_id, topic=ticker)
    record_event(
        case_id,
        "KIMI_SWARM_RESEARCH_COMPLETE" if status == "COMPLETE" else "KIMI_SWARM_RESEARCH_FAILED_CLOSED",
        entity_id=result_id,
        payload={
            "ticker": ticker,
            "subagent_count": payload["subagent_count"],
            "trade_execution_permission": False,
        },
    )

    state = {
        "high_speed_kimi_swarm_worker_state_id": STATE_ID,
        "policy_version": POLICY_VERSION,
        "status": status,
        "queue_depth_before": len(queued),
        "processed": True,
        "request_id": request_id,
        "result_id": result_id,
        "ticker": ticker,
        "subagent_count": payload["subagent_count"],
        "duration_seconds": round(time.perf_counter() - started, 3),
        "paper_mode": True,
        "repo_write_access_granted": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(STATE_ID, STATE_TYPE, WORKER_CASE_ID, state)
    return state


def latest_status() -> dict[str, Any]:
    return {
        "state": latest_object(STATE_TYPE, case_id=WORKER_CASE_ID),
        "queue_depth": len(_queued_requests(limit=50)),
        "provider": kimi_swarm_bridge.configuration_status(),
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
