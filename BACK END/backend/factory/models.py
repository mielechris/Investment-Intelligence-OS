from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


InterviewStatus = Literal["draft", "ready", "extracted", "archived"]
AgentStatus = Literal["proposed", "approved", "disabled"]
AgentPermission = Literal[
    "read_evidence",
    "read_market_data",
    "read_macro_data",
    "read_policy_data",
    "submit_committee_view",
]


class InterviewSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    subject_name: str
    subject_context: str | None = None
    objective: str
    transcript: str = ""
    status: InterviewStatus = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InterviewInsight(BaseModel):
    claim: str
    category: Literal[
        "expertise",
        "signal",
        "decision_rule",
        "assumption",
        "risk",
        "data_source",
        "workflow",
        "other",
    ] = "other"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_excerpt: str | None = None


class InterviewInsightPacket(BaseModel):
    interview_id: str
    subject_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str
    expertise_areas: list[str] = Field(default_factory=list)
    insights: list[InterviewInsight] = Field(default_factory=list)
    candidate_agent_roles: list[str] = Field(default_factory=list)
    provenance_note: str


class AgentDefinition(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    role: str
    mission: str
    instructions: str
    model: str = "gpt-5.6-luna"
    data_feeds: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    permissions: list[AgentPermission] = Field(default_factory=lambda: ["read_evidence"])
    output_schema: dict = Field(default_factory=dict)
    risk_boundaries: list[str] = Field(default_factory=lambda: [
        "PAPER_MODE_ONLY",
        "NO_LIVE_EXECUTION",
        "NO_REAL_MONEY_TRADE_RECOMMENDATION",
    ])
    status: AgentStatus = "proposed"
    source_interview_id: str | None = None
    source_subject_name: str | None = None
    provenance: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None


class AgentRunRequest(BaseModel):
    topic: str
    evidence: list[dict] = Field(default_factory=list)


class AgentRunResult(BaseModel):
    agent_id: str
    agent_name: str
    topic: str
    status: Literal["complete"] = "complete"
    output: dict
    paper_mode: bool = True
