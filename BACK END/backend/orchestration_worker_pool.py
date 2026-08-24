from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from eight_agent_orchestrator import run_eight_agent_orchestration


router = APIRouter()

DEFAULT_CASE_WORKERS = 2
MAX_CASE_WORKERS = 2
MAX_BATCH_CASES = 6


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000.0, 2)


def normalize_case_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        case_id = str(value or "").strip()
        if not case_id.startswith("case_") or case_id in seen:
            continue
        seen.add(case_id)
        output.append(case_id)
        if len(output) >= MAX_BATCH_CASES:
            break
    return output


def _run_case(case_id: str) -> dict[str, Any]:
    started = perf_counter()
    try:
        result = run_eight_agent_orchestration(case_id)
        committee = result.get("committee") or {}
        performance = result.get("performance") or {}
        return {
            "case_id": case_id,
            "status": "complete",
            "committee_disposition": committee.get("disposition"),
            "committee_confidence": committee.get("confidence"),
            "orchestration_id": (result.get("orchestration") or {}).get("orchestration_id"),
            "total_latency_ms": performance.get("total_latency_ms") or _elapsed_ms(started),
            "result": result,
            "paper_mode": True,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
    except Exception as exc:
        return {
            "case_id": case_id,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "total_latency_ms": _elapsed_ms(started),
            "result": None,
            "paper_mode": True,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }


def run_case_batch(case_ids: Any) -> dict[str, Any]:
    normalized = normalize_case_ids(case_ids)
    if not normalized:
        raise ValueError("Provide at least one valid case_id")

    started = perf_counter()
    completed: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=MAX_CASE_WORKERS) as pool:
        future_map = {pool.submit(_run_case, case_id): case_id for case_id in normalized}
        for future in as_completed(future_map):
            case_id = future_map[future]
            completed[case_id] = future.result()

    ordered = [completed[case_id] for case_id in normalized if case_id in completed]
    success_count = sum(1 for row in ordered if row.get("status") == "complete")
    error_count = len(ordered) - success_count

    return {
        "status": "complete" if error_count == 0 else "partial",
        "requested_case_count": len(normalized),
        "completed_case_count": success_count,
        "error_case_count": error_count,
        "case_workers": MAX_CASE_WORKERS,
        "max_batch_cases": MAX_BATCH_CASES,
        "total_batch_latency_ms": _elapsed_ms(started),
        "results": ordered,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/orchestration-batch/plan")
def batch_plan():
    return {
        "case_workers": MAX_CASE_WORKERS,
        "max_batch_cases": MAX_BATCH_CASES,
        "manual_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/orchestration-batch/run")
def run_batch(request: dict[str, Any] = Body(...)):
    try:
        return run_case_batch(request.get("case_ids"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
