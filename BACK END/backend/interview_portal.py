from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from openai import OpenAI

from ledger import get_object, list_objects, record_event, record_object


router = APIRouter()
PAPER_MODE = True
ALLOWED_CATEGORIES = {
    "expertise",
    "signal",
    "decision_rule",
    "assumption",
    "risk",
    "data_source",
    "workflow",
    "other",
}


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _parse_json_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def _require_interview(interview_id: str) -> dict[str, Any]:
    interview = get_object(interview_id)
    if not interview or not interview_id.startswith("interview_"):
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


def _latest_packet(interview_id: str) -> dict[str, Any] | None:
    packets = [
        item
        for item in list_objects(interview_id, "interview_insight_packet")
        if item.get("interview_id") == interview_id
    ]
    return sorted(packets, key=lambda item: str(item.get("created_at") or ""))[-1] if packets else None


def create_interview(request: dict[str, Any]) -> dict[str, Any]:
    subject_name = str(request.get("subject_name") or "").strip()
    objective = str(request.get("objective") or "").strip()
    if not subject_name or not objective:
        raise HTTPException(status_code=422, detail="subject_name and objective are required")

    interview_id = f"interview_{uuid4().hex}"
    interview = {
        "interview_id": interview_id,
        "subject_name": subject_name,
        "professional_role": str(request.get("professional_role") or "").strip(),
        "organization_context": str(request.get("organization_context") or "").strip(),
        "expertise_context": str(request.get("expertise_context") or "").strip(),
        "objective": objective,
        "confidentiality_scope": str(request.get("confidentiality_scope") or "Public/non-confidential professional judgment only").strip(),
        "transcript": "",
        "status": "DRAFT",
        "compliance_status": "PENDING_REVIEW",
        "paper_mode": True,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    record_object(interview_id, "professional_interview", interview_id, interview, topic=objective)
    record_event(interview_id, "PROFESSIONAL_INTERVIEW_CREATED", entity_id=interview_id, payload={"subject_name": subject_name, "objective": objective})
    return interview


def update_transcript(interview_id: str, request: dict[str, Any]) -> dict[str, Any]:
    interview = _require_interview(interview_id)
    incoming = str(request.get("transcript") or "").strip()
    append = bool(request.get("append", False))
    transcript = f"{interview.get('transcript', '')}\n{incoming}".strip() if append and interview.get("transcript") else incoming
    updated = {
        **interview,
        "transcript": transcript,
        "status": "READY_FOR_EXTRACTION" if transcript else "DRAFT",
        "updated_at": _utc_now(),
    }
    record_object(interview_id, "professional_interview", interview_id, updated, topic=interview.get("objective"))
    record_event(interview_id, "INTERVIEW_TRANSCRIPT_UPDATED", entity_id=interview_id, payload={"characters": len(transcript)})
    return updated


def extract_insights(interview_id: str) -> dict[str, Any]:
    interview = _require_interview(interview_id)
    transcript = str(interview.get("transcript") or "").strip()
    if not transcript:
        raise HTTPException(status_code=409, detail="Transcript required before extraction")

    prompt = f"""
You are the Professional Judgment Extractor inside Investment Intelligence OS (IIOS).

SUBJECT: {interview.get('subject_name')}
ROLE: {interview.get('professional_role') or 'Not provided'}
ORGANIZATION CONTEXT: {interview.get('organization_context') or 'Not provided'}
EXPERTISE CONTEXT: {interview.get('expertise_context') or 'Not provided'}
OBJECTIVE: {interview.get('objective')}
CONFIDENTIALITY SCOPE: {interview.get('confidentiality_scope')}

TRANSCRIPT:
{transcript}

Extract only judgment supported by the transcript. Never invent credentials, facts, views, or certainty.
Preserve provenance with a short source excerpt. Distinguish a reusable decision method from a one-off opinion.
This system may ultimately support investment research, so explicitly flag anything that could plausibly be
material non-public information, employer/client confidential information, unreleased results, private customer
demand, planned transactions, undisclosed contracts, non-public forecasts, or other restricted information.
Do NOT decide legal compliance. Your flags are screening signals only; human approval is mandatory.

Return ONLY JSON:
{{
  "summary": "concise summary",
  "expertise_areas": ["area"],
  "compliance_flags": ["screening concern, if any"],
  "candidate_agent_roles": ["reusable analytical role"],
  "insights": [
    {{
      "claim": "transcript-supported insight",
      "category": "expertise|signal|decision_rule|assumption|risk|data_source|workflow|other",
      "confidence": 0.0,
      "source_excerpt": "short excerpt",
      "applicability": "where this judgment is useful",
      "restriction_risk": "LOW|MEDIUM|HIGH",
      "restriction_reason": "why it may be restricted, or empty"
    }}
  ]
}}
"""
    response = OpenAI().responses.create(model="gpt-5.6-luna", input=prompt)
    try:
        extracted = _parse_json_object(response.output_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        extracted = {
            "summary": response.output_text,
            "expertise_areas": [],
            "compliance_flags": ["Extraction could not be structured; manual review required"],
            "candidate_agent_roles": [],
            "insights": [],
        }

    normalized_insights: list[dict[str, Any]] = []
    for index, item in enumerate(extracted.get("insights") or []):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "other").lower()
        if category not in ALLOWED_CATEGORIES:
            category = "other"
        risk = str(item.get("restriction_risk") or "MEDIUM").upper()
        if risk not in {"LOW", "MEDIUM", "HIGH"}:
            risk = "MEDIUM"
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        normalized_insights.append(
            {
                "insight_index": index,
                "claim": str(item.get("claim") or "").strip(),
                "category": category,
                "confidence": confidence,
                "source_excerpt": str(item.get("source_excerpt") or "").strip(),
                "applicability": str(item.get("applicability") or "").strip(),
                "restriction_risk": risk,
                "restriction_reason": str(item.get("restriction_reason") or "").strip(),
            }
        )

    packet_id = f"interview_packet_{uuid4().hex}"
    packet = {
        "interview_insight_packet_id": packet_id,
        "interview_id": interview_id,
        "subject_name": interview.get("subject_name"),
        "summary": str(extracted.get("summary") or "Interview extraction completed."),
        "expertise_areas": [str(item) for item in extracted.get("expertise_areas") or []],
        "compliance_flags": [str(item) for item in extracted.get("compliance_flags") or []],
        "candidate_agent_roles": [str(item) for item in extracted.get("candidate_agent_roles") or []],
        "insights": normalized_insights,
        "human_approval_required": True,
        "provenance_note": f"Derived from professional interview {interview_id}; no insight is published without human approval.",
        "created_at": _utc_now(),
        "paper_mode": True,
    }
    record_object(packet_id, "interview_insight_packet", interview_id, packet, parent_id=interview_id, topic=interview.get("objective"))
    updated = {**interview, "status": "EXTRACTED", "updated_at": _utc_now()}
    record_object(interview_id, "professional_interview", interview_id, updated, topic=interview.get("objective"))
    record_event(interview_id, "INTERVIEW_JUDGMENT_EXTRACTED", entity_id=packet_id, payload={"insight_count": len(normalized_insights), "compliance_flags": packet["compliance_flags"]})
    return packet


def approve_judgment(interview_id: str, request: dict[str, Any]) -> dict[str, Any]:
    interview = _require_interview(interview_id)
    packet = _latest_packet(interview_id)
    if not packet:
        raise HTTPException(status_code=409, detail="Extract interview insights before approval")
    if request.get("attest_no_mnpi") is not True:
        raise HTTPException(status_code=422, detail="Explicit no-MNPI attestation is required")
    if request.get("attest_right_to_use") is not True:
        raise HTTPException(status_code=422, detail="Explicit right-to-use attestation is required")

    raw_indexes = request.get("approved_insight_indexes")
    if not isinstance(raw_indexes, list) or not raw_indexes:
        raise HTTPException(status_code=422, detail="Select at least one insight to approve")
    indexes: set[int] = set()
    for item in raw_indexes:
        try:
            indexes.add(int(item))
        except (TypeError, ValueError):
            continue

    approved: list[dict[str, Any]] = []
    restricted: list[dict[str, Any]] = []
    for insight in packet.get("insights") or []:
        if int(insight.get("insight_index", -1)) not in indexes:
            continue
        if insight.get("restriction_risk") != "LOW":
            restricted.append(insight)
            continue
        judgment_id = f"professional_judgment_{uuid4().hex}"
        judgment = {
            "professional_judgment_id": judgment_id,
            "interview_id": interview_id,
            "interview_insight_packet_id": packet.get("interview_insight_packet_id"),
            "subject_name": interview.get("subject_name"),
            "professional_role": interview.get("professional_role"),
            "claim": insight.get("claim"),
            "category": insight.get("category"),
            "confidence": insight.get("confidence"),
            "source_excerpt": insight.get("source_excerpt"),
            "applicability": insight.get("applicability"),
            "restriction_risk": insight.get("restriction_risk"),
            "human_approved": True,
            "approval_notes": str(request.get("approval_notes") or "").strip(),
            "research_only": True,
            "trade_execution_permission": False,
            "created_at": _utc_now(),
            "paper_mode": True,
        }
        record_object(judgment_id, "professional_judgment", interview_id, judgment, parent_id=packet.get("interview_insight_packet_id"), topic=interview.get("objective"))
        approved.append(judgment)

    compliance_status = "APPROVED_FOR_JUDGMENT_BANK" if approved else "RESTRICTED_OR_NOT_APPROVED"
    updated = {
        **interview,
        "status": "REVIEWED",
        "compliance_status": compliance_status,
        "updated_at": _utc_now(),
    }
    record_object(interview_id, "professional_interview", interview_id, updated, topic=interview.get("objective"))
    record_event(interview_id, "INTERVIEW_HUMAN_REVIEW_COMPLETE", entity_id=interview_id, payload={"approved_count": len(approved), "restricted_count": len(restricted), "compliance_status": compliance_status})
    return {
        "interview": updated,
        "approved_judgments": approved,
        "restricted_insights": restricted,
        "judgment_bank_entries_added": len(approved),
        "paper_mode": True,
    }


@router.get("/interview-portal/status")
def interview_portal_status():
    interviews = list_objects(None, "professional_interview") if False else []
    return {
        "name": "Professional Interview Portal",
        "version": "0.9.0",
        "human_approval_required": True,
        "mnpi_screening": True,
        "auto_publish_to_trade_evidence": False,
        "paper_mode": True,
    }


@router.post("/interview-portal/interviews")
def interview_create(request: dict = Body(...)):
    return create_interview(request)


@router.get("/interview-portal/interviews/{interview_id}")
def interview_get(interview_id: str):
    return _require_interview(interview_id)


@router.put("/interview-portal/interviews/{interview_id}/transcript")
def interview_transcript(interview_id: str, request: dict = Body(...)):
    return update_transcript(interview_id, request)


@router.post("/interview-portal/interviews/{interview_id}/extract")
def interview_extract(interview_id: str):
    return extract_insights(interview_id)


@router.get("/interview-portal/interviews/{interview_id}/insights")
def interview_insights(interview_id: str):
    packet = _latest_packet(interview_id)
    if not packet:
        raise HTTPException(status_code=404, detail="Insight packet not found")
    return packet


@router.post("/interview-portal/interviews/{interview_id}/approve")
def interview_approve(interview_id: str, request: dict = Body(...)):
    return approve_judgment(interview_id, request)


@router.get("/interview-portal/interviews/{interview_id}/judgment-bank")
def interview_judgment_bank(interview_id: str):
    _require_interview(interview_id)
    entries = list_objects(interview_id, "professional_judgment")
    return {"interview_id": interview_id, "entries": entries, "count": len(entries), "paper_mode": True}
