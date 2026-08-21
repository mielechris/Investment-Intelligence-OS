import json
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException
from openai import OpenAI
from pydantic import BaseModel

from factory.models import (
    AgentDefinition,
    AgentRunRequest,
    AgentRunResult,
    InterviewInsight,
    InterviewInsightPacket,
    InterviewSession,
)
from factory.store import agents, insight_packets, interviews, save_agent, save_insight_packet, save_interview


router = APIRouter(prefix="/factory", tags=["factory"])


class InterviewCreateRequest(BaseModel):
    subject_name: str
    subject_context: str | None = None
    objective: str


class TranscriptUpdateRequest(BaseModel):
    transcript: str
    append: bool = True


def _parse_json_object(text: str) -> dict:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Model output must be a JSON object")
    return parsed


@router.get("/status")
def factory_status():
    return {
        "version": "1.2",
        "name": "Interview-to-Agent Factory",
        "paper_mode": True,
        "human_approval_required": True,
        "interview_count": len(interviews),
        "agent_count": len(agents),
        "approved_agent_count": sum(1 for agent in agents.values() if agent.status == "approved"),
    }


@router.post("/interviews", response_model=InterviewSession)
def create_interview(request: InterviewCreateRequest):
    interview = InterviewSession(
        subject_name=request.subject_name.strip(),
        subject_context=request.subject_context,
        objective=request.objective.strip(),
    )
    if not interview.subject_name or not interview.objective:
        raise HTTPException(status_code=400, detail="subject_name and objective are required")
    return save_interview(interview)


@router.get("/interviews", response_model=list[InterviewSession])
def list_interviews():
    return list(interviews.values())


@router.get("/interviews/{interview_id}", response_model=InterviewSession)
def get_interview(interview_id: str):
    interview = interviews.get(interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.put("/interviews/{interview_id}/transcript", response_model=InterviewSession)
def update_transcript(interview_id: str, request: TranscriptUpdateRequest):
    interview = interviews.get(interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    incoming = request.transcript.strip()
    if request.append and interview.transcript:
        interview.transcript = f"{interview.transcript}\n{incoming}".strip()
    else:
        interview.transcript = incoming

    interview.status = "ready" if interview.transcript else "draft"
    return save_interview(interview)


@router.post("/interviews/{interview_id}/extract", response_model=InterviewInsightPacket)
def extract_interview_insights(interview_id: str):
    interview = interviews.get(interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if not interview.transcript.strip():
        raise HTTPException(status_code=400, detail="Interview transcript is empty")

    client = OpenAI()
    prompt = f"""
You are the Interview Intelligence Extractor inside Investment Intelligence OS (IIOS).

SUBJECT: {interview.subject_name}
CONTEXT: {interview.subject_context or "Not provided"}
OBJECTIVE: {interview.objective}

TRANSCRIPT:
{interview.transcript}

Extract only insights supported by the transcript. Do not invent expertise, facts, credentials,
or opinions that are not present. Preserve uncertainty. Candidate agents should represent reusable
analytical roles, not clones of the person. This is PAPER MODE only.

Return ONLY valid JSON:
{{
  "summary": "concise interview summary",
  "expertise_areas": ["area"],
  "insights": [
    {{
      "claim": "supported insight",
      "category": "expertise|signal|decision_rule|assumption|risk|data_source|workflow|other",
      "confidence": 0.0,
      "source_excerpt": "short supporting excerpt from transcript"
    }}
  ],
  "candidate_agent_roles": ["reusable role name"]
}}
"""

    response = client.responses.create(model="gpt-5.6-luna", input=prompt)
    try:
        extracted = _parse_json_object(response.output_text)
        insights = [InterviewInsight(**item) for item in extracted.get("insights", [])]
    except (json.JSONDecodeError, ValueError, TypeError):
        extracted = {
            "summary": response.output_text,
            "expertise_areas": [],
            "candidate_agent_roles": [],
        }
        insights = []

    packet = InterviewInsightPacket(
        interview_id=interview.id,
        subject_name=interview.subject_name,
        summary=str(extracted.get("summary", "Interview extraction completed.")),
        expertise_areas=[str(item) for item in extracted.get("expertise_areas", [])],
        insights=insights,
        candidate_agent_roles=[str(item) for item in extracted.get("candidate_agent_roles", [])],
        provenance_note=(
            f"Derived from interview with {interview.subject_name} on "
            f"{interview.created_at.date().isoformat()}. Human approval is required before deployment."
        ),
    )
    interview.status = "extracted"
    save_interview(interview)
    return save_insight_packet(packet)


@router.get("/interviews/{interview_id}/insights", response_model=InterviewInsightPacket)
def get_interview_insights(interview_id: str):
    packet = insight_packets.get(interview_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Insight packet not found")
    return packet


@router.post("/interviews/{interview_id}/agents/propose", response_model=list[AgentDefinition])
def propose_agents(interview_id: str, request: dict = Body(default={})): 
    interview = interviews.get(interview_id)
    packet = insight_packets.get(interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if packet is None:
        raise HTTPException(status_code=400, detail="Extract interview insights first")

    max_agents = max(1, min(3, int(request.get("max_agents", 3))))
    client = OpenAI()
    prompt = f"""
You are the Agent Architect inside Investment Intelligence OS (IIOS).

Create up to {max_agents} reusable investment-intelligence agent proposals from this interview
insight packet. Do not create a personality clone of the interview subject. Build professional roles
that encode useful analytical methods while retaining provenance and uncertainty.

INTERVIEW ID: {interview.id}
SUBJECT: {interview.subject_name}
OBJECTIVE: {interview.objective}
INSIGHT PACKET:
{packet.model_dump_json(indent=2)}

Rules:
- PAPER MODE ONLY.
- No agent may execute trades or authorize capital.
- Every proposal requires human approval before it can run.
- Prefer narrow, testable missions over vague generalists.
- Evidence requirements should name what the agent needs to verify its claims.
- Allowed permissions: read_evidence, read_market_data, read_macro_data, read_policy_data,
  submit_committee_view.

Return ONLY valid JSON:
{{
  "agents": [
    {{
      "name": "agent display name",
      "role": "short role",
      "mission": "specific mission",
      "instructions": "operating instructions",
      "data_feeds": ["feed identifiers"],
      "evidence_requirements": ["required evidence"],
      "permissions": ["read_evidence"],
      "output_schema": {{
        "headline": "string",
        "view": "string",
        "confidence": "0.0-1.0",
        "disposition": "WATCH|NO_TRADE",
        "evidence_used": "array",
        "floor_comment": "string"
      }}
    }}
  ]
}}
"""

    response = client.responses.create(model="gpt-5.6-luna", input=prompt)
    try:
        generated = _parse_json_object(response.output_text)
        raw_agents = generated.get("agents", [])[:max_agents]
    except (json.JSONDecodeError, ValueError, TypeError):
        raw_agents = []

    proposals: list[AgentDefinition] = []
    for raw in raw_agents:
        if not isinstance(raw, dict):
            continue
        proposal = AgentDefinition(
            name=str(raw.get("name", "Interview Analyst")),
            role=str(raw.get("role", "Specialist Analyst")),
            mission=str(raw.get("mission", packet.summary)),
            instructions=str(raw.get("instructions", "Analyze only supported evidence and state uncertainty.")),
            data_feeds=[str(item) for item in raw.get("data_feeds", [])],
            evidence_requirements=[str(item) for item in raw.get("evidence_requirements", [])],
            permissions=[str(item) for item in raw.get("permissions", ["read_evidence"])],
            output_schema=raw.get("output_schema", {}),
            source_interview_id=interview.id,
            source_subject_name=interview.subject_name,
            provenance=[
                packet.provenance_note,
                *[insight.claim for insight in packet.insights[:8]],
            ],
        )
        proposals.append(save_agent(proposal))

    return proposals


@router.get("/agents", response_model=list[AgentDefinition])
def list_factory_agents(status: str | None = None):
    values = list(agents.values())
    if status:
        values = [agent for agent in values if agent.status == status]
    return values


@router.get("/agents/{agent_id}", response_model=AgentDefinition)
def get_factory_agent(agent_id: str):
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/agents/{agent_id}/approve", response_model=AgentDefinition)
def approve_agent(agent_id: str):
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "approved"
    agent.approved_at = datetime.now(timezone.utc)
    return save_agent(agent)


@router.post("/agents/{agent_id}/disable", response_model=AgentDefinition)
def disable_agent(agent_id: str):
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "disabled"
    return save_agent(agent)


@router.post("/agents/{agent_id}/run", response_model=AgentRunResult)
def run_factory_agent(agent_id: str, request: AgentRunRequest):
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status != "approved":
        raise HTTPException(status_code=403, detail="Agent must be human-approved before it can run")

    client = OpenAI()
    prompt = f"""
You are {agent.name}, a dynamically configured specialist agent inside Investment Intelligence OS.

ROLE: {agent.role}
MISSION: {agent.mission}
INSTRUCTIONS: {agent.instructions}
EVIDENCE REQUIREMENTS: {json.dumps(agent.evidence_requirements)}
RISK BOUNDARIES: {json.dumps(agent.risk_boundaries)}

TOPIC:
{request.topic}

EVIDENCE PROVIDED:
{json.dumps(request.evidence, indent=2)}

Rules:
- PAPER MODE ONLY.
- Use only the provided evidence for claims that require current information.
- Explicitly identify missing evidence.
- Do not recommend a real-money trade.
- Disposition must be WATCH or NO_TRADE.
- Confidence must be between 0.0 and 1.0.
- Preserve disagreement and uncertainty.

Return ONLY valid JSON with these fields:
{{
  "headline": "short headline",
  "view": "2 to 5 sentence analysis",
  "confidence": 0.0,
  "disposition": "WATCH",
  "evidence_used": ["source names or evidence identifiers actually used"],
  "missing_evidence": ["important missing evidence"],
  "floor_comment": "short dry professional one-liner"
}}
"""

    response = client.responses.create(model=agent.model, input=prompt)
    try:
        output = _parse_json_object(response.output_text)
    except (json.JSONDecodeError, ValueError, TypeError):
        output = {
            "headline": f"{agent.name} completed review",
            "view": response.output_text,
            "confidence": 0.5,
            "disposition": "NO_TRADE",
            "evidence_used": [],
            "missing_evidence": agent.evidence_requirements,
            "floor_comment": "The specialist spoke. Structure filed a complaint.",
        }

    return AgentRunResult(
        agent_id=agent.id,
        agent_name=agent.name,
        topic=request.topic,
        output=output,
    )
