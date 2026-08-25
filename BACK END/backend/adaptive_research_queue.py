from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ledger import get_object, list_objects, record_event, record_object, utc_now
from opportunity_acquisition import opportunity_queue, promote_candidate
from orchestration_worker_pool import configured_case_workers, run_case_batch


router = APIRouter()

RESEARCH_QUEUE_LEDGER_CASE = "adaptive_research_queue"
QUEUE_ITEM_TYPE = "adaptive_research_queue_item"
MAX_QUEUE_DEPTH = 50
HIGH_WATERMARK = 20
DEFAULT_INTAKE_LIMIT = 10
MAX_INTAKE_PER_CYCLE = 20
STALE_RUNNING_MINUTES = 20

PENDING = "PENDING"
RUNNING = "RUNNING"
COMPLETE = "COMPLETE"
ERROR = "ERROR"


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


def _queue_item_id(case_id: str) -> str:
    return f"research_queue_{case_id}"


def _queue_rows() -> list[dict[str, Any]]:
    return list_objects(RESEARCH_QUEUE_LEDGER_CASE, QUEUE_ITEM_TYPE)


def _priority_key(row: dict[str, Any]) -> tuple[float, str]:
    return (-float(row.get("priority_score") or 0.0), str(row.get("enqueued_at") or ""))


def backpressure_state(pending_count: int, running_count: int = 0) -> dict[str, Any]:
    pending = max(0, int(pending_count))
    running = max(0, int(running_count))
    active_depth = pending + running
    return {
        "pending_count": pending,
        "running_count": running,
        "active_depth": active_depth,
        "high_watermark": HIGH_WATERMARK,
        "max_queue_depth": MAX_QUEUE_DEPTH,
        "backpressure_active": pending >= HIGH_WATERMARK,
        "intake_open": active_depth < MAX_QUEUE_DEPTH,
        "capacity_remaining": max(0, MAX_QUEUE_DEPTH - active_depth),
    }


def queue_status() -> dict[str, Any]:
    rows = _queue_rows()
    counts = {PENDING: 0, RUNNING: 0, COMPLETE: 0, ERROR: 0}
    for row in rows:
        state = str(row.get("state") or PENDING).upper()
        counts[state] = counts.get(state, 0) + 1

    pressure = backpressure_state(counts.get(PENDING, 0), counts.get(RUNNING, 0))
    pending = sorted(
        [row for row in rows if str(row.get("state") or "").upper() == PENDING],
        key=_priority_key,
    )
    return {
        **pressure,
        "counts": counts,
        "configured_case_workers": configured_case_workers(),
        "next_cases": [
            {
                "case_id": row.get("case_id"),
                "ticker": row.get("ticker"),
                "priority_score": row.get("priority_score"),
                "source_candidate_id": row.get("source_candidate_id"),
            }
            for row in pending[:10]
        ],
        "automatic_drain": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def enqueue_case(
    case_id: str,
    *,
    source_candidate_id: str | None = None,
    ticker: str | None = None,
    priority_score: float = 0.0,
) -> dict[str, Any]:
    case_id = str(case_id or "").strip()
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise ValueError("Unknown case_id")

    item_id = _queue_item_id(case_id)
    existing = get_object(item_id)
    if existing:
        return {"item": existing, "already_queued": True}

    status = queue_status()
    if not status["intake_open"]:
        raise ValueError("Research queue capacity reached; intake is fail-closed")

    item = {
        "research_queue_item_id": item_id,
        "case_id": case_id,
        "source_candidate_id": source_candidate_id,
        "ticker": str(ticker or "").upper() or None,
        "priority_score": round(float(priority_score or 0.0), 4),
        "state": PENDING,
        "attempt_count": 0,
        "enqueued_at": utc_now(),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(item_id, QUEUE_ITEM_TYPE, RESEARCH_QUEUE_LEDGER_CASE, item, topic=case.get("topic"))
    record_event(
        RESEARCH_QUEUE_LEDGER_CASE,
        "RESEARCH_CASE_ENQUEUED",
        entity_id=item_id,
        payload={
            "case_id": case_id,
            "source_candidate_id": source_candidate_id,
            "priority_score": item["priority_score"],
            "trade_execution_permission": False,
        },
    )
    return {"item": item, "already_queued": False}


def enqueue_ranked_opportunities(limit: int = DEFAULT_INTAKE_LIMIT) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_INTAKE_PER_CYCLE))
    before = queue_status()
    if before["backpressure_active"]:
        return {
            "status": "backpressure",
            "reason": "HIGH_WATERMARK_REACHED",
            "selected": 0,
            "results": [],
            "queue": before,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    candidates = [row for row in opportunity_queue(20) if row.get("eligible_for_promotion") is True]
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(results) >= limit:
            break
        if not queue_status()["intake_open"]:
            break
        candidate_id = str(candidate.get("opportunity_candidate_id") or "")
        try:
            promoted = promote_candidate(candidate_id)
            case = promoted["case"]
            queued = enqueue_case(
                str(case["case_id"]),
                source_candidate_id=candidate_id,
                ticker=str(candidate.get("ticker") or ""),
                priority_score=float(candidate.get("score") or 0.0),
            )
            results.append({
                "candidate_id": candidate_id,
                "case_id": case.get("case_id"),
                "ticker": candidate.get("ticker"),
                "score": candidate.get("score"),
                "status": "queued",
                "already_queued": queued["already_queued"],
            })
        except Exception as exc:
            results.append({
                "candidate_id": candidate_id,
                "ticker": candidate.get("ticker"),
                "score": candidate.get("score"),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    after = queue_status()
    return {
        "status": "complete",
        "requested": limit,
        "selected": len(results),
        "results": results,
        "queue": after,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def recover_stale_running(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    recovered = 0
    for row in _queue_rows():
        if str(row.get("state") or "").upper() != RUNNING:
            continue
        started = _parse_time(row.get("started_at"))
        if started and now - started < timedelta(minutes=STALE_RUNNING_MINUTES):
            continue
        updated = {
            **row,
            "state": PENDING,
            "started_at": None,
            "updated_at": utc_now(),
            "last_error": "STALE_RUNNING_RECOVERED",
        }
        record_object(
            str(row["research_queue_item_id"]),
            QUEUE_ITEM_TYPE,
            RESEARCH_QUEUE_LEDGER_CASE,
            updated,
        )
        recovered += 1
    return recovered


def drain_queue(limit: int | None = None) -> dict[str, Any]:
    recovered = recover_stale_running()
    pending = sorted(
        [row for row in _queue_rows() if str(row.get("state") or "").upper() == PENDING],
        key=_priority_key,
    )
    workers = configured_case_workers()
    requested = workers if limit is None else max(1, min(int(limit), workers))
    selected = pending[:requested]

    if not selected:
        return {
            "status": "empty",
            "selected": 0,
            "recovered_stale_items": recovered,
            "results": [],
            "queue": queue_status(),
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    by_case: dict[str, dict[str, Any]] = {}
    for row in selected:
        updated = {
            **row,
            "state": RUNNING,
            "started_at": utc_now(),
            "attempt_count": int(row.get("attempt_count") or 0) + 1,
            "updated_at": utc_now(),
        }
        record_object(
            str(row["research_queue_item_id"]),
            QUEUE_ITEM_TYPE,
            RESEARCH_QUEUE_LEDGER_CASE,
            updated,
        )
        by_case[str(row["case_id"])] = updated

    batch = run_case_batch(list(by_case))
    batch_results = {str(row.get("case_id")): row for row in batch.get("results") or []}
    outputs: list[dict[str, Any]] = []
    for case_id, item in by_case.items():
        result = batch_results.get(case_id) or {
            "case_id": case_id,
            "status": "error",
            "error": "Worker pool returned no result for case",
        }
        succeeded = result.get("status") == "complete"
        final = {
            **item,
            "state": COMPLETE if succeeded else ERROR,
            "completed_at": utc_now(),
            "updated_at": utc_now(),
            "last_error": None if succeeded else result.get("error"),
            "orchestration_id": result.get("orchestration_id"),
            "committee_disposition": result.get("committee_disposition"),
            "committee_confidence": result.get("committee_confidence"),
        }
        record_object(
            str(item["research_queue_item_id"]),
            QUEUE_ITEM_TYPE,
            RESEARCH_QUEUE_LEDGER_CASE,
            final,
        )
        outputs.append({"queue_item": final, "worker_result": result})

    record_event(
        RESEARCH_QUEUE_LEDGER_CASE,
        "RESEARCH_QUEUE_DRAIN_COMPLETE",
        payload={
            "selected": len(selected),
            "completed": sum(1 for row in outputs if row["queue_item"]["state"] == COMPLETE),
            "failed": sum(1 for row in outputs if row["queue_item"]["state"] == ERROR),
            "configured_case_workers": workers,
            "trade_execution_permission": False,
        },
    )
    return {
        "status": "complete",
        "selected": len(selected),
        "recovered_stale_items": recovered,
        "worker_batch": batch,
        "results": outputs,
        "queue": queue_status(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def run_queue_cycle(intake_limit: int = DEFAULT_INTAKE_LIMIT) -> dict[str, Any]:
    before = queue_status()
    intake = (
        {
            "status": "backpressure",
            "reason": "HIGH_WATERMARK_REACHED",
            "selected": 0,
        }
        if before["backpressure_active"]
        else enqueue_ranked_opportunities(intake_limit)
    )
    drain = drain_queue()
    return {
        "status": "complete",
        "intake": intake,
        "drain": drain,
        "queue": queue_status(),
        "automatic_drain": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/research-queue/plan")
def research_queue_plan():
    return {
        "max_queue_depth": MAX_QUEUE_DEPTH,
        "high_watermark": HIGH_WATERMARK,
        "default_intake_limit": DEFAULT_INTAKE_LIMIT,
        "max_intake_per_cycle": MAX_INTAKE_PER_CYCLE,
        "stale_running_minutes": STALE_RUNNING_MINUTES,
        "configured_case_workers": configured_case_workers(),
        "automatic_drain": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/research-queue/status")
def research_queue_status():
    return queue_status()


@router.post("/research-queue/enqueue-ranked")
def research_queue_enqueue_ranked(request: dict[str, Any] = Body(default={})):
    return enqueue_ranked_opportunities(int(request.get("limit") or DEFAULT_INTAKE_LIMIT))


@router.post("/research-queue/drain")
def research_queue_drain(request: dict[str, Any] = Body(default={})):
    limit = request.get("limit")
    return drain_queue(None if limit in (None, "") else int(limit))


@router.post("/research-queue/cycle")
def research_queue_cycle(request: dict[str, Any] = Body(default={})):
    return run_queue_cycle(int(request.get("intake_limit") or DEFAULT_INTAKE_LIMIT))
