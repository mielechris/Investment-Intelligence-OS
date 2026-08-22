import json
import math
from typing import Literal

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from factory.store import agents
from factory.system_agents import (
    IPO_AGENT_ID,
    MARKET_HISTORY_AGENT_ID,
    FUNDAMENTALS_AGENT_ID,
    MACRO_AGENT_ID,
    MARKET_STRUCTURE_AGENT_ID,
    SENTIMENT_AGENT_ID,
    CATALYST_AGENT_ID,
    RED_TEAM_AGENT_ID,
)


router = APIRouter(prefix="/intelligence/council", tags=["eight-agent-council"])

COUNCIL_AGENT_IDS = [
    IPO_AGENT_ID,
    MARKET_HISTORY_AGENT_ID,
    FUNDAMENTALS_AGENT_ID,
    MACRO_AGENT_ID,
    MARKET_STRUCTURE_AGENT_ID,
    SENTIMENT_AGENT_ID,
    CATALYST_AGENT_ID,
    RED_TEAM_AGENT_ID,
]


class CouncilSimulationRequest(BaseModel):
    topic: str
    asset: str
    direction: Literal["LONG", "SHORT", "WATCH"] = "WATCH"
    horizon: str = "1-3 months"
    thesis: str
    catalysts: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    simulated_notional: float = Field(default=10000.0, ge=0.0, le=1_000_000.0)


def _parse_object(text: str) -> dict:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Model output was not a JSON object")
    return parsed


def _run_specialist(client: OpenAI, agent, request: CouncilSimulationRequest) -> dict:
    prompt = f"""
You are {agent.name}, one of eight independent specialist agents inside Investment Intelligence OS.

ROLE: {agent.role}
MISSION: {agent.mission}
INSTRUCTIONS: {agent.instructions}
EVIDENCE REQUIREMENTS: {json.dumps(agent.evidence_requirements)}
RISK BOUNDARIES: {json.dumps(agent.risk_boundaries)}

PROPOSED PAPER THESIS:
Topic: {request.topic}
Asset: {request.asset}
Direction: {request.direction}
Horizon: {request.horizon}
Thesis: {request.thesis}
Catalysts: {json.dumps(request.catalysts)}
Invalidation: {json.dumps(request.invalidation)}

EVIDENCE PROVIDED:
{json.dumps(request.evidence, indent=2)}

Rules:
- This is a SIMULATION-ONLY council test. PAPER MODE ONLY. No live execution or real capital.
- Review independently. Do not assume the thesis is good because it was submitted for testing.
- Use only supplied evidence for factual claims. Explicitly identify missing evidence.
- First classify whether your specialist mandate genuinely applies to this asset/thesis.
- Use NOT_APPLICABLE only for a true mandate mismatch (for example an IPO-only specialist reviewing a mature listed company).
- Missing or weak evidence is NOT a reason to mark NOT_APPLICABLE; remain APPLICABLE and use NEUTRAL or OPPOSE as warranted.
- SUPPORT means the supplied evidence supports advancing the thesis to council/risk review, not that a real-money trade should be placed.
- OPPOSE means the evidence or thesis has a material flaw.
- Confidence must be 0.0 to 1.0.

Return ONLY valid JSON:
{{
  "applicability": "APPLICABLE|NOT_APPLICABLE",
  "applicability_reason": "string",
  "headline": "string",
  "stance": "SUPPORT|NEUTRAL|OPPOSE",
  "confidence": 0.0,
  "view": "string",
  "supporting_points": ["string"],
  "risks": ["string"],
  "missing_evidence": ["string"],
  "invalidation_checks": ["string"],
  "disposition": "WATCH|NO_TRADE"
}}
"""
    response = client.responses.create(model=agent.model, input=prompt)
    output = _parse_object(response.output_text)

    applicability = str(output.get("applicability", "APPLICABLE")).upper()
    if applicability not in {"APPLICABLE", "NOT_APPLICABLE"}:
        applicability = "APPLICABLE"
    if agent.id == RED_TEAM_AGENT_ID:
        applicability = "APPLICABLE"
    output["applicability"] = applicability
    output.setdefault("applicability_reason", "Specialist mandate applies to this thesis.")

    stance = str(output.get("stance", "NEUTRAL")).upper()
    if stance not in {"SUPPORT", "NEUTRAL", "OPPOSE"}:
        stance = "NEUTRAL"
    if applicability == "NOT_APPLICABLE":
        stance = "NEUTRAL"
    output["stance"] = stance

    try:
        confidence = float(output.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    output["confidence"] = max(0.0, min(confidence, 1.0))
    output["agent_id"] = agent.id
    output["agent_name"] = agent.name
    return output


def _build_vote_summary(reviews: list[dict]) -> dict:
    applicable = [item for item in reviews if item.get("applicability") != "NOT_APPLICABLE"]
    abstentions = [item for item in reviews if item.get("applicability") == "NOT_APPLICABLE"]

    support = sum(1 for item in applicable if item.get("stance") == "SUPPORT")
    neutral = sum(1 for item in applicable if item.get("stance") == "NEUTRAL")
    oppose = sum(1 for item in applicable if item.get("stance") == "OPPOSE")
    confidences = [float(item.get("confidence", 0.0)) for item in applicable]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    applicable_count = len(applicable)
    required_support = max(3, math.ceil(applicable_count * 0.60)) if applicable_count else 0
    support_ratio = support / applicable_count if applicable_count else 0.0

    red_team = next((item for item in reviews if item.get("agent_id") == RED_TEAM_AGENT_ID), None)
    red_team_block = bool(
        red_team
        and red_team.get("stance") == "OPPOSE"
        and float(red_team.get("confidence", 0.0)) >= 0.75
    )

    return {
        "support": support,
        "neutral": neutral,
        "oppose": oppose,
        "abstain": len(abstentions),
        "average_confidence": round(avg_confidence, 4),
        "agent_count": len(reviews),
        "applicable_count": applicable_count,
        "support_ratio": round(support_ratio, 4),
        "required_support": required_support,
        "red_team_block": red_team_block,
        "abstaining_agents": [item.get("agent_name") for item in abstentions],
    }


def _deterministic_council_gate(vote_summary: dict, chair: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    applicable_count = int(vote_summary.get("applicable_count", 0))
    support = int(vote_summary.get("support", 0))
    required_support = int(vote_summary.get("required_support", 0))
    oppose = int(vote_summary.get("oppose", 0))
    avg_confidence = float(vote_summary.get("average_confidence", 0.0))

    if applicable_count < 5:
        reasons.append("Fewer than five specialist mandates were applicable.")
    if support < required_support:
        reasons.append(f"Applicable support {support} did not meet required support {required_support}.")
    if oppose > 1:
        reasons.append("More than one applicable specialist opposed the thesis.")
    if avg_confidence < 0.60:
        reasons.append("Applicable-specialist average confidence was below 60%.")
    if bool(vote_summary.get("red_team_block", False)):
        reasons.append("High-confidence Red Team opposition triggered a council block.")
    if chair.get("decision") != "PASS_TO_RISK":
        reasons.append("Council Chair did not approve passage to Risk.")

    return not reasons, reasons


def _run_chair(client: OpenAI, request: CouncilSimulationRequest, reviews: list[dict], vote_summary: dict) -> dict:
    prompt = f"""
You are the Eight-Agent Council Chair inside Investment Intelligence OS.

This is a simulation-only paper test. Synthesize the eight independent reviews without erasing dissent.
Do not reward consensus for its own sake and do not turn missing evidence into assumptions.
Specialists marked NOT_APPLICABLE are abstentions because their mandate genuinely does not apply; do not count them as support or opposition.
An APPLICABLE specialist who is NEUTRAL because evidence is missing still represents unresolved evidence risk.

THESIS:
{json.dumps(request.model_dump(), indent=2)}

VOTE SUMMARY:
{json.dumps(vote_summary, indent=2)}

SPECIALIST REVIEWS:
{json.dumps(reviews, indent=2)}

Rules:
- PAPER MODE ONLY. No live execution or real capital.
- PASS_TO_RISK is allowed only if the evidence is coherent enough for a bounded paper simulation.
- Preserve the strongest supporting case and the strongest objection.
- A specialist vote is advisory; explain disagreements rather than averaging them away.
- Do not penalize a thesis merely because a genuinely non-applicable specialist abstained.
- If important pricing, liquidity, solvency, catalyst, cash-flow, valuation, or invalidation evidence is missing, prefer REJECT.

Return ONLY valid JSON:
{{
  "decision": "PASS_TO_RISK|REJECT",
  "confidence": 0.0,
  "headline": "string",
  "summary": "string",
  "strongest_support": "string",
  "strongest_objection": "string",
  "unresolved_disagreements": ["string"],
  "missing_evidence": ["string"],
  "disposition": "WATCH|NO_TRADE"
}}
"""
    response = client.responses.create(model="gpt-5.6-luna", input=prompt)
    output = _parse_object(response.output_text)
    decision = str(output.get("decision", "REJECT")).upper()
    if decision not in {"PASS_TO_RISK", "REJECT"}:
        decision = "REJECT"
    output["decision"] = decision
    return output


def _run_risk_gate(client: OpenAI, request: CouncilSimulationRequest, reviews: list[dict], chair: dict) -> dict:
    prompt = f"""
You are the isolated simulation Risk Desk inside Investment Intelligence OS.

Review this eight-agent council result. This test must NOT write to production Risk, Committee,
Portfolio, or Institutional Memory stores.

THESIS:
{json.dumps(request.model_dump(), indent=2)}

COUNCIL CHAIR:
{json.dumps(chair, indent=2)}

SPECIALIST REVIEWS:
{json.dumps(reviews, indent=2)}

Rules:
- PAPER MODE ONLY. Real allowed_notional is always 0.
- VETO if evidence is insufficient to bound downside, liquidity, sizing, or invalidation.
- WATCH_ONLY is allowed only with no hard vetoes and enough evidence for a hypothetical paper simulation.
- paper_execution_eligible may be true only with WATCH_ONLY and no hard vetoes.

Return ONLY valid JSON:
{{
  "decision": "VETOED|WATCH_ONLY",
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "headline": "string",
  "primary_risks": ["string"],
  "downside_scenarios": ["string"],
  "liquidity_assessment": "string",
  "sizing_constraints": ["string"],
  "hard_vetoes": ["string"],
  "missing_evidence": ["string"],
  "allowed_notional": 0,
  "confidence": 0.0,
  "paper_execution_eligible": false
}}
"""
    response = client.responses.create(model="gpt-5.6-luna", input=prompt)
    output = _parse_object(response.output_text)
    decision = str(output.get("decision", "VETOED")).upper()
    if decision not in {"VETOED", "WATCH_ONLY"}:
        decision = "VETOED"
    output["decision"] = decision
    output["allowed_notional"] = 0
    hard_vetoes = output.get("hard_vetoes") or []
    eligible = bool(output.get("paper_execution_eligible", False))
    if decision != "WATCH_ONLY" or hard_vetoes:
        eligible = False
    output["paper_execution_eligible"] = eligible
    return output


@router.post("/simulate")
def simulate_full_council(request: CouncilSimulationRequest):
    selected = []
    for agent_id in COUNCIL_AGENT_IDS:
        agent = agents.get(agent_id)
        if agent is None or agent.status != "approved":
            raise HTTPException(status_code=409, detail=f"Council agent unavailable or not approved: {agent_id}")
        selected.append(agent)

    client = OpenAI()
    reviews = []
    for agent in selected:
        try:
            reviews.append(_run_specialist(client, agent, request))
        except Exception as exc:
            reviews.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "applicability": "APPLICABLE",
                "applicability_reason": "Agent execution failed; conservatively retained in quorum.",
                "headline": "Agent review failed",
                "stance": "NEUTRAL",
                "confidence": 0.0,
                "view": str(exc),
                "supporting_points": [],
                "risks": ["Agent execution error"],
                "missing_evidence": agent.evidence_requirements,
                "invalidation_checks": [],
                "disposition": "NO_TRADE",
                "error": True,
            })

    vote_summary = _build_vote_summary(reviews)
    chair = _run_chair(client, request, reviews, vote_summary)
    gate_passed, gate_reasons = _deterministic_council_gate(vote_summary, chair)
    if not gate_passed:
        chair["decision"] = "REJECT"

    if chair["decision"] == "PASS_TO_RISK":
        risk = _run_risk_gate(client, request, reviews, chair)
    else:
        risk = {
            "decision": "VETOED",
            "risk_level": "HIGH",
            "headline": "Council did not clear the thesis for risk review",
            "primary_risks": ["Relevance-aware council gate was not satisfied.", *gate_reasons],
            "downside_scenarios": [],
            "liquidity_assessment": "Not evaluated because the council gate failed.",
            "sizing_constraints": ["No paper order may be simulated."],
            "hard_vetoes": ["COUNCIL_GATE_FAILED"],
            "missing_evidence": chair.get("missing_evidence", []),
            "allowed_notional": 0,
            "confidence": 1.0,
            "paper_execution_eligible": False,
        }

    paper_eligible = (
        risk.get("decision") == "WATCH_ONLY"
        and bool(risk.get("paper_execution_eligible"))
        and not (risk.get("hard_vetoes") or [])
    )
    simulated_order = None
    if paper_eligible:
        simulated_order = {
            "execution": "HYPOTHETICAL_PAPER_ORDER",
            "asset": request.asset,
            "side": request.direction,
            "simulated_notional": request.simulated_notional,
            "real_notional": 0,
            "broker_order_sent": False,
            "live_execution": False,
            "paper_mode": True,
        }

    return {
        "mode": "EIGHT_AGENT_COUNCIL_SIMULATION",
        "simulation_only": True,
        "paper_mode": True,
        "live_execution": False,
        "real_capital": 0,
        "production_committee_write": False,
        "production_risk_write": False,
        "production_portfolio_write": False,
        "institutional_memory_write": False,
        "thesis": request.model_dump(),
        "vote_summary": vote_summary,
        "council_gate": {
            "passed": gate_passed,
            "reasons": gate_reasons,
            "minimum_applicable_specialists": 5,
            "support_requirement": vote_summary.get("required_support"),
            "red_team_high_confidence_opposition_blocks": True,
        },
        "agent_reviews": reviews,
        "council_chair": chair,
        "risk_gate": risk,
        "paper_execution_eligible": paper_eligible,
        "simulated_order": simulated_order,
    }
