from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from eight_agent_orchestrator_v2 import run_eight_agent_orchestration
from ledger import DB_PATH, get_object, latest_object, record_event, record_object, utc_now


POLICY_VERSION = "batch10m1-case-floor-agent-contract-v2"
QUEUE_CASE_ID = "high_speed_case_floor"
STATE_ID = "high_speed_case_floor_state_v1"
STATE_TYPE = "high_speed_case_floor_state"
CYCLE_TYPE = "high_speed_case_floor_cycle"
MAX_CONCURRENT_CASES = 2
CASE_MAX_AGE_HOURS = 24
ALLOWED_PROMOTION_CREATORS = {
    "BATCH_9E_GROK_GEMINI_HIGH_SPEED_RADAR",
    "BATCH_9E_HIGH_SPEED_MARKET_RADAR",
}


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


def _nine_e_promoted_cases(limit: int = 50) -> list[dict[str, Any]]:
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            """
            SELECT payload_json, created_at
            FROM ledger_objects
            WHERE object_type='opportunity_candidate'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    finally:
        db.close()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=CASE_MAX_AGE_HOURS)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        try:
            candidate = json.loads(row["payload_json"])
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(candidate, dict):
            continue
        created_by = str(candidate.get("created_by") or "").strip()
        if created_by not in ALLOWED_PROMOTION_CREATORS:
            continue
        case_id = str(candidate.get("promoted_case_id") or "").strip()
        if not case_id or case_id in seen:
            continue
        created = _parse_time(candidate.get("promoted_at") or candidate.get("created_at") or row["created_at"])
        if created is not None and created < cutoff:
            continue
        seen.add(case_id)
        output.append(
            {
                "case_id": case_id,
                "ticker": str(candidate.get("ticker") or "").upper(),
                "rank_score": candidate.get("radar_rank_score"),
                "candidate_id": candidate.get("opportunity_candidate_id"),
                "created_by": created_by,
                "created_at": candidate.get("promoted_at") or candidate.get("created_at"),
            }
        )
    output.sort(
        key=lambda item: (
            float(item.get("rank_score") or 0.0),
            str(item.get("created_at") or ""),
        ),
        reverse=True,
    )
    return output


def pending_cases(limit: int = 20) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for item in _nine_e_promoted_cases(limit=100):
        case_id = str(item.get("case_id") or "")
        if not case_id or not get_object(case_id):
            continue
        committee = latest_object("committee_decision", case_id=case_id)
        if committee:
            continue
        pending.append(item)
        if len(pending) >= max(1, min(int(limit), 50)):
            break
    return pending


def _run_case(item: dict[str, Any]) -> dict[str, Any]:
    case_id = str(item.get("case_id") or "")
    started = time.perf_counter()
    record_event(
        case_id,
        "HIGH_SPEED_CASE_FLOOR_STARTED",
        entity_id=case_id,
        payload={
            "ticker": item.get("ticker"),
            "created_by": item.get("created_by"),
            "agent_contract_version": "batch10m1-agent-contract-v2",
            "trade_execution_permission": False,
        },
    )
    try:
        result = run_eight_agent_orchestration(case_id)
        committee = result.get("committee") or {}
        return {
            **item,
            "status": "COMPLETE",
            "committee_disposition": committee.get("disposition"),
            "committee_confidence": committee.get("confidence"),
            "agent_contract_version": "batch10m1-agent-contract-v2",
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001
        record_event(
            case_id,
            "HIGH_SPEED_CASE_FLOOR_FAILED_CLOSED",
            entity_id=case_id,
            payload={
                "error": f"{type(exc).__name__}: {exc}"[:1000],
                "agent_contract_version": "batch10m1-agent-contract-v2",
                "trade_execution_permission": False,
            },
        )
        return {
            **item,
            "status": "FAILED_CLOSED",
            "error": f"{type(exc).__name__}: {exc}"[:1500],
            "duration_seconds": round(time.perf_counter() - started, 3),
        }


def run_case_floor_cycle(max_cases: int = MAX_CONCURRENT_CASES) -> dict[str, Any]:
    started = time.perf_counter()
    cycle_id = f"high_speed_case_floor_{uuid4().hex}"
    queue = pending_cases(limit=20)
    selected = queue[: max(0, min(int(max_cases), MAX_CONCURRENT_CASES))]
    results: list[dict[str, Any]] = []

    if selected:
        with ThreadPoolExecutor(max_workers=len(selected)) as pool:
            future_map = {pool.submit(_run_case, item): item for item in selected}
            for future in as_completed(future_map):
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    item = future_map[future]
                    results.append(
                        {
                            **item,
                            "status": "FAILED_CLOSED",
                            "error": f"{type(exc).__name__}: {exc}"[:1500],
                        }
                    )

    results.sort(key=lambda row: str(row.get("ticker") or ""))
    completed = sum(1 for row in results if row.get("status") == "COMPLETE")
    failed = sum(1 for row in results if row.get("status") != "COMPLETE")
    completed_at = utc_now()
    duration = round(time.perf_counter() - started, 3)

    state = {
        "high_speed_case_floor_state_id": STATE_ID,
        "policy_version": POLICY_VERSION,
        "last_cycle_id": cycle_id,
        "last_cycle_completed_at": completed_at,
        "queue_depth_before": len(queue),
        "selected_count": len(selected),
        "completed_count": completed,
        "failed_closed_count": failed,
        "remaining_queue_depth": max(0, len(queue) - len(selected)),
        "results": results,
        "cycle_duration_seconds": duration,
        "max_concurrent_cases": MAX_CONCURRENT_CASES,
        "agent_contract_version": "batch10m1-agent-contract-v2",
        "specialist_call_count_per_case": 8,
        "committee_call_count_per_case": 1,
        "extra_model_calls_added": 0,
        "allowed_promotion_creators": sorted(ALLOWED_PROMOTION_CREATORS),
        "paper_mode": True,
        "committee_override": False,
        "risk_override": False,
        "capital_override": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": completed_at,
    }
    record_object(STATE_ID, STATE_TYPE, QUEUE_CASE_ID, state, topic="HIGH_SPEED_CASE_FLOOR")
    cycle = {
        "high_speed_case_floor_cycle_id": cycle_id,
        **state,
    }
    record_object(cycle_id, CYCLE_TYPE, QUEUE_CASE_ID, cycle, topic="HIGH_SPEED_CASE_FLOOR")
    record_event(
        QUEUE_CASE_ID,
        "HIGH_SPEED_CASE_FLOOR_COMPLETE",
        entity_id=cycle_id,
        payload={
            "queue_depth_before": len(queue),
            "selected_count": len(selected),
            "completed_count": completed,
            "failed_closed_count": failed,
            "agent_contract_version": "batch10m1-agent-contract-v2",
            "trade_execution_permission": False,
        },
    )
    return cycle


def latest_status() -> dict[str, Any]:
    return {
        "state": latest_object(STATE_TYPE, case_id=QUEUE_CASE_ID),
        "pending_cases": pending_cases(limit=20),
        "policy_version": POLICY_VERSION,
        "agent_contract_version": "batch10m1-agent-contract-v2",
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
