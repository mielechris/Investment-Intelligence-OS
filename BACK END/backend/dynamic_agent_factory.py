from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from openai import OpenAI

from ledger import DB_PATH, get_object, list_objects, record_event, record_object, utc_now


router = APIRouter()
POLICY_VERSION = "dynamic-agent-factory-v1"
MAX_PROPOSALS_PER_INTERVIEW = 3
ALLOWED_PERMISSIONS = {"read_evidence", "submit_committee_view"}
FIXED_RISK_BOUNDARIES = [
    "PAPER_MODE_ONLY",
    "NO_LIVE_EXECUTION",
    "NO_CAPITAL_AUTHORITY",
    "NO_POSITION_SIZING_AUTHORITY",
    "NO_COMMITTEE_QUORUM_MEMBERSHIP",
    "NO_AUTOMATIC_COMMITTEE_INJECTION",
    "CURRENT_CLAIMS_REQUIRE_PROVIDED_EVIDENCE",
]


def _parse_json_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def _require_interview(interview_id: str) -> dict[str, Any]:
    interview = get_object(interview_id)
    if not interview or not str(interview_id).startswith("interview_"):
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _judgments_for_interview(interview_id: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? AND case_id = ? ORDER BY created_at ASC",
            ("professional_judgment", interview_id),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def eligible_source_judgments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row.get("human_approved") is True
        and row.get("research_only") is True
        and str(row.get("restriction_risk") or "").upper() == "LOW"
        and str(row.get("professional_judgment_id") or "").startswith("professional_judgment_")
    ]


def _clean_permissions(values: Any) -> list[str]:
    raw = values if isinstance(values, list) else []
    cleaned = [str(value) for value in raw if str(value) in ALLOWED_PERMISSIONS]
    return cleaned or ["read_evidence"]


def normalize_agent_proposal(raw: dict[str, Any], *, interview_id: str, source_judgments: list[dict[str, Any]]) -> dict[str, Any]:
    source_ids = [str(row.get("professional_judgment_id")) for row in source_judgments]
    name = str(raw.get("name") or "Interview-Derived Research Specialist").strip()[:120]
    role = str(raw.get("role") or "Specialist Research Analyst").strip()[:180]
    mission = str(raw.get("mission") or "Apply approved professional judgment as advisory research context.").strip()[:1200]
    instructions = str(raw.get("instructions") or "Use only provided evidence for current factual claims and state uncertainty.").strip()[:4000]
    evidence_requirements = [str(item).strip()[:500] for item in raw.get("evidence_requirements") or [] if str(item).strip()][:12]

    agent_id = f"dynamic_agent_{uuid4().hex}"
    return {
        "dynamic_agent_id": agent_id,
        "policy_version": POLICY_VERSION,
        "source_interview_id": interview_id,
        "source_professional_judgment_ids": source_ids,
        "name": name,
        "role": role,
        "mission": mission,
        "instructions": instructions,
        "model": "gpt-5.6-luna",
        "evidence_requirements": evidence_requirements,
        "permissions": _clean_permissions(raw.get("permissions")),
        "risk_boundaries": list(FIXED_RISK_BOUNDARIES),
        "status": "PROPOSED",
        "human_approved": False,
        "committee_quorum_member": False,
        "automatic_committee_injection": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "position_sizing_permission": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }


def propose_agents(interview_id: str, max_agents: int = MAX_PROPOSALS_PER_INTERVIEW) -> dict[str, Any]:
    interview = _require_interview(interview_id)
    judgments = eligible_source_judgments(_judgments_for_interview(interview_id))
    if not judgments:
        raise HTTPException(status_code=409, detail="At least one human-approved LOW-risk Judgment Bank entry is required before agent proposal")

    max_agents = max(1, min(int(max_agents), MAX_PROPOSALS_PER_INTERVIEW))
    prompt = f"""
You are the Agent Architect inside Investment Intelligence OS (IIOS).
Create up to {max_agents} narrow reusable research-agent proposals using ONLY the approved professional judgments below.

INTERVIEW OBJECTIVE: {interview.get('objective')}
APPROVED JUDGMENTS:
{json.dumps(judgments, indent=2, default=str)}

Rules:
- Do not create a personality clone.
- PAPER/RESEARCH MODE ONLY.
- No capital authority, position sizing, order creation, or live execution.
- The agent is not a voting member of the fixed eight-agent committee.
- It may produce an advisory committee view only when manually run.
- Current factual claims require evidence supplied at run time.
- Preserve provenance and uncertainty.

Return ONLY JSON:
{{"agents":[{{"name":"string","role":"string","mission":"string","instructions":"string","evidence_requirements":["string"],"permissions":["read_evidence","submit_committee_view"]}}]}}
"""
    response = OpenAI().responses.create(model="gpt-5.6-luna", input=prompt)
    try:
        parsed = _parse_json_object(response.output_text)
        raw_agents = parsed.get("agents") if isinstance(parsed.get("agents"), list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        raw_agents = []

    proposals: list[dict[str, Any]] = []
    for raw in raw_agents[:max_agents]:
        if not isinstance(raw, dict):
            continue
        proposal = normalize_agent_proposal(raw, interview_id=interview_id, source_judgments=judgments)
        record_object(
            proposal["dynamic_agent_id"],
            "dynamic_agent_definition",
            interview_id,
            proposal,
            parent_id=interview_id,
            topic=str(interview.get("objective") or "Dynamic research agent"),
        )
        proposals.append(proposal)

    record_event(
        interview_id,
        "DYNAMIC_AGENT_PROPOSALS_CREATED",
        entity_id=interview_id,
        payload={"proposal_count": len(proposals), "human_approval_required": True, "trade_execution_permission": False},
    )
    return {
        "interview_id": interview_id,
        "proposals": proposals,
        "proposal_count": len(proposals),
        "human_approval_required": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _require_agent(agent_id: str) -> dict[str, Any]:
    agent = get_object(agent_id)
    if not agent or not str(agent_id).startswith("dynamic_agent_"):
        raise HTTPException(status_code=404, detail="Dynamic agent not found")
    return agent


def approve_agent(agent_id: str, request: dict[str, Any]) -> dict[str, Any]:
    agent = _require_agent(agent_id)
    if request.get("confirm_research_only") is not True:
        raise HTTPException(status_code=422, detail="Explicit research-only confirmation is required")
    approved = {
        **agent,
        "status": "APPROVED",
        "human_approved": True,
        "approved_at": utc_now(),
        "approval_notes": str(request.get("approval_notes") or "").strip()[:1000],
        "auto_trade_authority": False,
        "position_sizing_permission": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(agent_id, "dynamic_agent_definition", str(agent.get("source_interview_id")), approved, parent_id=str(agent.get("source_interview_id")))
    record_event(str(agent.get("source_interview_id")), "DYNAMIC_AGENT_HUMAN_APPROVED", entity_id=agent_id, payload={"trade_execution_permission": False})
    return approved


def disable_agent(agent_id: str) -> dict[str, Any]:
    agent = _require_agent(agent_id)
    disabled = {**agent, "status": "DISABLED", "disabled_at": utc_now(), "trade_execution_permission": False, "live_execution": False}
    record_object(agent_id, "dynamic_agent_definition", str(agent.get("source_interview_id")), disabled, parent_id=str(agent.get("source_interview_id")))
    return disabled


def normalize_agent_output(value: Any) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    disposition = str(row.get("disposition") or "NO_TRADE").upper()
    if disposition not in {"WATCH", "NO_TRADE"}:
        disposition = "NO_TRADE"
    try:
        confidence = max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "headline": str(row.get("headline") or "Dynamic specialist review completed")[:500],
        "view": str(row.get("view") or "")[:6000],
        "confidence": confidence,
        "disposition": disposition,
        "evidence_used": [str(item)[:500] for item in row.get("evidence_used") or []][:20],
        "missing_evidence": [str(item)[:500] for item in row.get("missing_evidence") or []][:20],
    }


def run_agent(agent_id: str, request: dict[str, Any]) -> dict[str, Any]:
    agent = _require_agent(agent_id)
    if agent.get("status") != "APPROVED" or agent.get("human_approved") is not True:
        raise HTTPException(status_code=403, detail="Dynamic agent must be human-approved before it can run")

    case_id = str(request.get("case_id") or "").strip()
    case = _require_case(case_id)
    evidence = request.get("evidence") if isinstance(request.get("evidence"), list) else []
    if not evidence:
        raise HTTPException(status_code=422, detail="Provided evidence is required")

    topic = str(request.get("topic") or case.get("topic") or "").strip()
    prompt = f"""
You are {agent.get('name')}, an optional research specialist inside IIOS.
ROLE: {agent.get('role')}
MISSION: {agent.get('mission')}
INSTRUCTIONS: {agent.get('instructions')}
EVIDENCE REQUIREMENTS: {json.dumps(agent.get('evidence_requirements') or [])}
RISK BOUNDARIES: {json.dumps(FIXED_RISK_BOUNDARIES)}

TOPIC: {topic}
PROVIDED EVIDENCE:
{json.dumps(evidence, indent=2, default=str)}

Rules:
- Use provided evidence for all current factual claims.
- State missing evidence and uncertainty.
- Output is advisory research only and does not alter Committee quorum or governance.
- Disposition must be WATCH or NO_TRADE.
- No trade sizing, order creation, capital authorization, or live execution.

Return ONLY JSON:
{{"headline":"string","view":"string","confidence":0.0,"disposition":"WATCH|NO_TRADE","evidence_used":["string"],"missing_evidence":["string"]}}
"""
    response = OpenAI().responses.create(model=str(agent.get("model") or "gpt-5.6-luna"), input=prompt)
    try:
        output = normalize_agent_output(_parse_json_object(response.output_text))
    except (json.JSONDecodeError, TypeError, ValueError):
        output = normalize_agent_output({"view": response.output_text, "disposition": "NO_TRADE", "confidence": 0.0, "missing_evidence": agent.get("evidence_requirements") or []})

    run_id = f"dynamic_agent_run_{uuid4().hex}"
    result = {
        "dynamic_agent_run_id": run_id,
        "dynamic_agent_id": agent_id,
        "case_id": case_id,
        "topic": topic,
        "output": output,
        "advisory_committee_view": True,
        "committee_quorum_member": False,
        "automatic_committee_injection": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "position_sizing_permission": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(run_id, "dynamic_agent_run", case_id, result, parent_id=agent_id, topic=topic)
    record_event(case_id, "DYNAMIC_AGENT_RESEARCH_RUN_COMPLETE", entity_id=run_id, payload={"agent_id": agent_id, "disposition": output["disposition"], "trade_execution_permission": False})
    return result


def dynamic_agent_plan() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "source": "GOVERNED_INTERVIEW_JUDGMENT_BANK",
        "human_approval_required_for_source_judgment": True,
        "low_restriction_risk_source_only": True,
        "human_approval_required_for_agent": True,
        "max_proposals_per_interview": MAX_PROPOSALS_PER_INTERVIEW,
        "allowed_permissions": sorted(ALLOWED_PERMISSIONS),
        "committee_quorum_member": False,
        "automatic_committee_injection": False,
        "capital_authority": False,
        "position_sizing_permission": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "paper_mode": True,
    }


@router.get("/dynamic-agent-factory/plan")
def dynamic_agent_factory_plan():
    return dynamic_agent_plan()


@router.get("/dynamic-agent-factory/interviews/{interview_id}/agents")
def dynamic_agents_for_interview(interview_id: str):
    _require_interview(interview_id)
    agents = list_objects(interview_id, "dynamic_agent_definition")
    return {"interview_id": interview_id, "agents": agents, "count": len(agents), "paper_mode": True, "trade_execution_permission": False}


@router.post("/dynamic-agent-factory/interviews/{interview_id}/propose")
def dynamic_agent_propose(interview_id: str, request: dict[str, Any] = Body(default={})):
    return propose_agents(interview_id, int(request.get("max_agents") or MAX_PROPOSALS_PER_INTERVIEW))


@router.post("/dynamic-agent-factory/agents/{agent_id}/approve")
def dynamic_agent_approve(agent_id: str, request: dict[str, Any] = Body(...)):
    return approve_agent(agent_id, request)


@router.post("/dynamic-agent-factory/agents/{agent_id}/disable")
def dynamic_agent_disable(agent_id: str):
    return disable_agent(agent_id)


@router.post("/dynamic-agent-factory/agents/{agent_id}/run")
def dynamic_agent_run(agent_id: str, request: dict[str, Any] = Body(...)):
    return run_agent(agent_id, request)
