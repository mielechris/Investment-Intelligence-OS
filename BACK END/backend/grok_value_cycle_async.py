from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from grok_value_cycle import run_forward_value_cycle
from ledger import get_object, record_object, utc_now


router = APIRouter()
POLICY_VERSION = "grok-forward-value-cycle-async-v1"
JOB_CASE_ID = "grok_value_cycle_jobs"
_JOB_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="iios-value-cycle-job")
_JOB_LOCK = threading.Lock()
_ACTIVE_JOB_ID: str | None = None


def _job_object_id(job_id: str) -> str:
    return f"grok_value_cycle_job_{job_id}"


def _safe_job(job_id: str) -> dict[str, Any] | None:
    return get_object(_job_object_id(job_id))


def _record_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    object_id = _job_object_id(job_id)
    body = {
        "grok_value_cycle_job_id": job_id,
        "policy_version": POLICY_VERSION,
        **payload,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "updated_at": utc_now(),
    }
    record_object(object_id, "grok_value_cycle_job", JOB_CASE_ID, body, topic="BATCH_7C_FORWARD_VALUE_JOB")
    return body


def _run_job(job_id: str, request: dict[str, Any]) -> None:
    global _ACTIVE_JOB_ID
    _record_job(job_id, {
        "status": "RUNNING",
        "started_at": utc_now(),
        "request": request,
        "result_cycle_id": None,
        "error": None,
    })
    try:
        result = run_forward_value_cycle(request)
        _record_job(job_id, {
            "status": "COMPLETE",
            "started_at": (_safe_job(job_id) or {}).get("started_at"),
            "completed_at": utc_now(),
            "request": request,
            "result_cycle_id": result.get("grok_value_cycle_id"),
            "result": result,
            "error": None,
        })
    except Exception as exc:
        _record_job(job_id, {
            "status": "ERROR",
            "started_at": (_safe_job(job_id) or {}).get("started_at"),
            "completed_at": utc_now(),
            "request": request,
            "result_cycle_id": None,
            "result": None,
            "error": f"{type(exc).__name__}: {exc}"[:2000],
        })
    finally:
        with _JOB_LOCK:
            if _ACTIVE_JOB_ID == job_id:
                _ACTIVE_JOB_ID = None


def start_cycle_job(request: dict[str, Any] | None = None) -> dict[str, Any]:
    global _ACTIVE_JOB_ID
    request = request or {}
    with _JOB_LOCK:
        if _ACTIVE_JOB_ID:
            active = _safe_job(_ACTIVE_JOB_ID)
            if active and active.get("status") in {"QUEUED", "RUNNING"}:
                return {
                    "status": "ALREADY_RUNNING",
                    "job": active,
                    "research_only": True,
                    "paper_mode": True,
                    "trade_execution_permission": False,
                    "live_execution": False,
                }
            _ACTIVE_JOB_ID = None

        job_id = uuid4().hex
        _ACTIVE_JOB_ID = job_id
        job = _record_job(job_id, {
            "status": "QUEUED",
            "queued_at": utc_now(),
            "request": request,
            "result_cycle_id": None,
            "result": None,
            "error": None,
        })
        _JOB_POOL.submit(_run_job, job_id, dict(request))

    return {
        "status": "STARTED",
        "job": job,
        "poll_path": f"/grok/value/cycle/jobs/{job_id}",
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/grok/value/cycle/start")
def start_forward_value_cycle(request: dict[str, Any] = Body(default={})):
    try:
        return start_cycle_job(request)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}"[:1000])


@router.get("/grok/value/cycle/jobs/{job_id}")
def get_cycle_job(job_id: str):
    job = _safe_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown Batch 7C cycle job")
    return job


@router.get("/grok/value/cycle/job-active")
def get_active_cycle_job():
    with _JOB_LOCK:
        job_id = _ACTIVE_JOB_ID
    if not job_id:
        return {
            "status": "IDLE",
            "research_only": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }
    job = _safe_job(job_id)
    return job or {
        "status": "UNKNOWN",
        "grok_value_cycle_job_id": job_id,
        "research_only": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
