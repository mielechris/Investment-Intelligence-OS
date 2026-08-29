from __future__ import annotations

import json
import sqlite3
import time
from typing import Any
from uuid import uuid4

import gemini_provider
from high_speed_gemini_pipeline import GEMINI_DEEP_REQUEST_TYPE
from ledger import DB_PATH, latest_object, record_event, record_object, utc_now


POLICY_VERSION = "batch10m1-gemini-pro-evidence-gap-v2"
WORKER_CASE_ID = "high_speed_gemini_deep_worker"
STATE_ID = "high_speed_gemini_deep_worker_state_v1"
STATE_TYPE = "high_speed_gemini_deep_worker_state"
RESULT_TYPE = "gemini_deep_research_result"
MAX_PRIORITY_QUESTIONS = 6

DEEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "executive_summary": {"type": "string"},
        "what_changed": {"type": "array", "items": {"type": "string"}},
        "primary_source_findings": {"type": "array", "items": {"type": "string"}},
        "confirming_evidence": {"type": "array", "items": {"type": "string"}},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "open_evidence_gaps": {"type": "array", "items": {"type": "string"}},
        "question_resolutions": {"type": "array", "items": {"type": "string"}},
        "decision_changing_unknowns": {"type": "array", "items": {"type": "string"}},
        "structural_vs_temporary": {"type": "string"},
        "research_confidence": {"type": "number"},
        "complexity_score": {"type": "number"},
    },
    "required": [
        "ticker",
        "executive_summary",
        "what_changed",
        "primary_source_findings",
        "confirming_evidence",
        "contradictions",
        "open_evidence_gaps",
        "question_resolutions",
        "decision_changing_unknowns",
        "structural_vs_temporary",
        "research_confidence",
        "complexity_score",
    ],
}


def _queued_requests(limit: int = 20) -> list[dict[str, Any]]:
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at ASC LIMIT ?",
            (GEMINI_DEEP_REQUEST_TYPE, max(1, min(int(limit), 100))),
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
        request_id = str(value.get("gemini_deep_research_request_id") or "")
        case_id = str(value.get("case_id") or "")
        if not request_id or not case_id:
            continue
        existing = latest_object(RESULT_TYPE, case_id=case_id)
        if existing and existing.get("source_request_id") == request_id:
            continue
        output.append(value)
    return output


def _string_list(value: Any, limit: int = MAX_PRIORITY_QUESTIONS) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text[:1200])
        if len(out) >= limit:
            break
    return out


def priority_research_questions(request: dict[str, Any]) -> list[str]:
    """Extract the highest-value unresolved questions without another model call."""
    explicit = _string_list(request.get("research_questions"))
    if explicit:
        return explicit
    source = request.get("source_context") if isinstance(request.get("source_context"), dict) else {}
    gemini = source.get("gemini") if isinstance(source.get("gemini"), dict) else {}
    questions = _string_list(gemini.get("open_questions"))
    if questions:
        return questions
    # If Flash did not return questions, contradictions are the next best deep-research targets.
    return [f"Resolve or bound this counterevidence: {text}" for text in _string_list(gemini.get("counterevidence"))]


def _prompt(request: dict[str, Any]) -> tuple[str, str]:
    questions = priority_research_questions(request)
    system = (
        "You are Gemini Pro serving as IIOS's selective deep Research Office. Use Google Search grounding and URL Context "
        "to independently investigate the case. Seek primary sources wherever possible. PRIORITIZE the supplied unresolved "
        "research questions before broadening the investigation. For each question, state what the evidence resolves, what remains "
        "unknown, and whether the uncertainty could materially change the thesis. Test the strongest confirming and opposing "
        "explanations, identify what changed, and distinguish structural changes from temporary narrative. This is context only. "
        "Do not recommend or execute a trade and do not override IIOS Committee, Risk, or Capital."
    )
    user = json.dumps(
        {
            "objective": request.get("objective"),
            "ticker": request.get("ticker"),
            "priority_research_questions": questions,
            "source_context": request.get("source_context"),
        },
        ensure_ascii=False,
        default=str,
    )
    return system, user


def run_deep_once() -> dict[str, Any]:
    started = time.perf_counter()
    provider = gemini_provider.configuration_status()
    queued = _queued_requests(limit=20)

    if not provider.get("configured"):
        state = {
            "high_speed_gemini_deep_worker_state_id": STATE_ID,
            "policy_version": POLICY_VERSION,
            "status": "PROVIDER_NOT_CONFIGURED",
            "queue_depth": len(queued),
            "processed": False,
            "evidence_gap_driven": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(STATE_ID, STATE_TYPE, WORKER_CASE_ID, state)
        return state

    if not queued:
        state = {
            "high_speed_gemini_deep_worker_state_id": STATE_ID,
            "policy_version": POLICY_VERSION,
            "status": "IDLE",
            "queue_depth": 0,
            "processed": False,
            "evidence_gap_driven": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(STATE_ID, STATE_TYPE, WORKER_CASE_ID, state)
        return state

    request = queued[0]
    request_id = str(request.get("gemini_deep_research_request_id") or "")
    case_id = str(request.get("case_id") or "")
    ticker = str(request.get("ticker") or "").upper()
    questions = priority_research_questions(request)

    record_event(
        case_id,
        "GEMINI_DEEP_RESEARCH_STARTED",
        entity_id=request_id,
        payload={
            "ticker": ticker,
            "priority_question_count": len(questions),
            "evidence_gap_driven": True,
            "trade_execution_permission": False,
        },
    )

    try:
        system, user = _prompt(request)
        result = gemini_provider.research_json(
            system=system,
            user=user,
            schema=DEEP_SCHEMA,
            model=gemini_provider.pro_model(),
            thinking_level="high",
            use_google_search=True,
            use_url_context=True,
            max_output_tokens=14000,
        )
        output = result.get("output") or {}
        if not isinstance(output, dict):
            raise ValueError("Gemini deep output missing structured packet")
        status = "COMPLETE"
        error = None
    except Exception as exc:  # noqa: BLE001
        result = {}
        output = {}
        status = "FAILED_CLOSED"
        error = f"{type(exc).__name__}: {exc}"[:3000]

    result_id = f"gemini_deep_result_{uuid4().hex}"
    payload = {
        "gemini_deep_research_result_id": result_id,
        "source_request_id": request_id,
        "case_id": case_id,
        "ticker": ticker,
        "status": status,
        "research": output,
        "priority_research_questions": questions,
        "evidence_gap_driven": True,
        "provider_model": result.get("model"),
        "latency_ms": result.get("latency_ms"),
        "usage": result.get("usage") or {},
        "web_search_queries": result.get("web_search_queries") or [],
        "grounding_sources": result.get("grounding_sources") or [],
        "url_context_metadata": result.get("url_context_metadata") or {},
        "error": error,
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "committee_override": False,
        "risk_override": False,
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
        "GEMINI_DEEP_RESEARCH_COMPLETE" if status == "COMPLETE" else "GEMINI_DEEP_RESEARCH_FAILED_CLOSED",
        entity_id=result_id,
        payload={
            "ticker": ticker,
            "status": status,
            "priority_question_count": len(questions),
            "evidence_gap_driven": True,
            "trade_execution_permission": False,
        },
    )

    state = {
        "high_speed_gemini_deep_worker_state_id": STATE_ID,
        "policy_version": POLICY_VERSION,
        "status": status,
        "queue_depth_before": len(queued),
        "processed": True,
        "request_id": request_id,
        "result_id": result_id,
        "ticker": ticker,
        "priority_question_count": len(questions),
        "evidence_gap_driven": True,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "paper_mode": True,
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
        "provider": gemini_provider.configuration_status(),
        "evidence_gap_driven": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
