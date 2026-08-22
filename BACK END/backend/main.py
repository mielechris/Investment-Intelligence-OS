import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Investment Intelligence OS", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PAPER_MODE = True
MIN_COMMITTEE_CONFIDENCE = 0.65

# Prototype persistence. Move these stores to a database before production/live capital.
CASES: dict[str, dict[str, Any]] = {}
COMMITTEE_DECISIONS: dict[str, dict[str, Any]] = {}
RISK_AUTHORIZATIONS: dict[str, dict[str, Any]] = {}
EXECUTIONS: dict[str, dict[str, Any]] = {}


AGENT_CONFIGS = {
    "policy": {
        "name": "Policy Analyst",
        "room": "Policy Floor",
        "focus": (
            "government policy, executive actions, legislation, regulation, tariffs, "
            "industrial policy, fiscal transmission, and policy-sensitive sectors"
        ),
        "stance": "Analyze policy transmission without assuming causality that is not evidenced.",
    },
    "macro": {
        "name": "Macro & Rates Analyst",
        "room": "Macro Desk",
        "focus": (
            "rates, inflation, growth, labor, liquidity, Federal Reserve policy, the dollar, "
            "credit conditions, and broad market transmission"
        ),
        "stance": "Separate cyclical, liquidity, and policy effects and identify regime uncertainty.",
    },
    "fundamentals": {
        "name": "Fundamentals Analyst",
        "room": "Fundamentals Lab",
        "focus": (
            "revenue, earnings, margins, balance sheet quality, valuation, capital intensity, "
            "competitive position, and business-model durability"
        ),
        "stance": "Distinguish business quality from security price and valuation attractiveness.",
    },
    "market_structure": {
        "name": "Market Structure Analyst",
        "room": "Tape & Positioning",
        "focus": (
            "price action, positioning, liquidity, volatility, crowding, flows, catalysts, "
            "technical structure, and what may already be priced in"
        ),
        "stance": "Treat narrative and price behavior as separate evidence streams.",
    },
    "commodities": {
        "name": "Commodities & Supply Chain Analyst",
        "room": "Physical Markets",
        "focus": (
            "energy, agriculture, metals, freight, inventories, production, supply disruptions, "
            "seasonality, input costs, and supply-chain transmission"
        ),
        "stance": "Focus on physical constraints, timing, seasonality, and second-order effects.",
    },
    "geo_weather": {
        "name": "Geopolitics & Weather Analyst",
        "room": "Global Events Room",
        "focus": (
            "war, sanctions, elections, geopolitical chokepoints, extreme weather, drought, "
            "hurricanes, crop conditions, and event-driven supply or demand shocks"
        ),
        "stance": "Separate confirmed events from scenario risk and avoid sensational weighting.",
    },
    "skeptic": {
        "name": "Skeptic / Red Team",
        "room": "Red Team",
        "focus": (
            "false causality, confirmation bias, hidden assumptions, missing evidence, crowding, "
            "priced-in expectations, base-rate neglect, and alternative explanations"
        ),
        "stance": "Attack the strongest version of the thesis and identify what would falsify it.",
    },
    "portfolio": {
        "name": "Portfolio Context Analyst",
        "room": "Portfolio Control",
        "focus": (
            "portfolio concentration, correlation, factor exposure, scenario overlap, opportunity cost, "
            "drawdown sensitivity, and whether a good idea is a good portfolio addition"
        ),
        "stance": "Judge the idea in portfolio context rather than as an isolated prediction.",
    },
}


class TopicRequest(BaseModel):
    topic: str
    evidence: list[dict[str, Any]] | None = None


class PolicyRequest(BaseModel):
    topic: str


class MacroRequest(BaseModel):
    topic: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp_confidence(value: Any, default: float = 0.5) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))


def normalize_disposition(value: Any) -> str:
    disposition = str(value or "NO_TRADE").upper()
    return disposition if disposition in {"WATCH", "NO_TRADE"} else "NO_TRADE"


def new_case(topic: str, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    case_id = f"case_{uuid4().hex}"
    case = {
        "case_id": case_id,
        "topic": topic.strip(),
        "evidence": evidence or [],
        "created_at": utc_now(),
        "paper_mode": PAPER_MODE,
    }
    CASES[case_id] = case
    return case


def evidence_prompt(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return (
            "No structured evidence packet was supplied. Treat all claims requiring current data as "
            "unverified and explicitly state what fresh evidence is needed."
        )
    return json.dumps(evidence, indent=2, default=str)


def run_specialist(agent_key: str, topic: str, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    config = AGENT_CONFIGS.get(agent_key)
    if not config:
        raise HTTPException(status_code=404, detail="Unknown agent")

    topic = topic.strip()
    if not topic:
        return {
            "agent_key": agent_key,
            "agent": config["name"],
            "room": config["room"],
            "status": "complete",
            "topic": "",
            "headline": "No thesis supplied",
            "view": "A usable investment thesis or market question is required.",
            "confidence": 0.0,
            "disposition": "NO_TRADE",
            "missing_evidence": ["investment topic"],
            "falsifier": "No thesis exists to falsify.",
            "floor_comment": "The desk received an empty folder.",
        }

    client = OpenAI()
    prompt = f"""
You are the {config['name']} inside the Investment Intelligence OS.

TOPIC:
{topic}

YOUR DOMAIN:
{config['focus']}

YOUR OPERATING STANCE:
{config['stance']}

EVIDENCE PACKET:
{evidence_prompt(evidence or [])}

Rules:
- PAPER MODE only. Never recommend or execute a real-money trade.
- Do not pretend information is current when fresh data is required.
- Separate evidence, inference, and unknowns.
- Identify missing evidence that materially affects the conclusion.
- State at least one falsifier: what observation would weaken or overturn your view.
- Disposition must be WATCH or NO_TRADE.
- Confidence must be 0.0 to 1.0 and should reflect evidence quality, not writing confidence.
- Be concise and analytical.
- Use dry professional floor humor in floor_comment.

Return ONLY valid JSON with exactly these fields:
{{
  "headline": "short headline",
  "view": "2 to 4 sentence domain analysis",
  "confidence": 0.0,
  "disposition": "WATCH",
  "missing_evidence": ["specific missing item"],
  "falsifier": "what would weaken or overturn this view",
  "floor_comment": "short dry one-liner"
}}
"""

    response = client.responses.create(model="gpt-5.6-luna", input=prompt)

    try:
        analysis = json.loads(response.output_text)
        if not isinstance(analysis, dict):
            raise ValueError("Agent output was not a JSON object")
    except (json.JSONDecodeError, ValueError, TypeError):
        analysis = {
            "headline": f"{config['name']} review completed",
            "view": response.output_text,
            "confidence": 0.35,
            "disposition": "NO_TRADE",
            "missing_evidence": ["structured model output"],
            "falsifier": "Unable to structure falsifier from model output.",
            "floor_comment": "The analysis arrived. The paperwork did not.",
        }

    return {
        "agent_key": agent_key,
        "agent": config["name"],
        "room": config["room"],
        "status": "complete",
        "topic": topic,
        "headline": str(analysis.get("headline", f"{config['name']} review completed")),
        "view": str(analysis.get("view", "Review completed.")),
        "confidence": clamp_confidence(analysis.get("confidence"), 0.35),
        "disposition": normalize_disposition(analysis.get("disposition")),
        "missing_evidence": analysis.get("missing_evidence", []),
        "falsifier": str(analysis.get("falsifier", "No falsifier recorded.")),
        "floor_comment": str(analysis.get("floor_comment", "Desk review complete.")),
    }


@app.get("/")
def root():
    return {
        "message": "IIOS backend online",
        "version": "0.2.0",
        "paper_mode": PAPER_MODE,
        "governed_chain": True,
    }


@app.get("/agents")
def get_agents():
    return {
        "agents": [
            {
                "key": key,
                "name": config["name"],
                "room": config["room"],
                "status": "idle",
            }
            for key, config in AGENT_CONFIGS.items()
        ]
    }


@app.post("/agents/{agent_key}/run")
def run_agent(agent_key: str, request: TopicRequest):
    return run_specialist(agent_key, request.topic, request.evidence)


# Backward-compatible specialist endpoints used by the current frontend.
@app.post("/agents/policy/run")
def run_policy_agent(request: PolicyRequest):
    return run_specialist("policy", request.topic)


@app.post("/agents/macro/run")
def run_macro_agent(request: MacroRequest):
    return run_specialist("macro", request.topic)


@app.post("/agents/skeptic/run")
def run_skeptic_agent(request: dict = Body(...)):
    return run_specialist("skeptic", str(request.get("topic", "")))


def build_committee(case: dict[str, Any]) -> dict[str, Any]:
    specialist_results = {
        key: run_specialist(key, case["topic"], case["evidence"])
        for key in AGENT_CONFIGS
    }

    client = OpenAI()
    committee_packet = {
        "case_id": case["case_id"],
        "topic": case["topic"],
        "evidence_count": len(case["evidence"]),
        "specialists": specialist_results,
    }

    prompt = f"""
You are the Investment Committee Chair inside the Investment Intelligence OS.

Eight specialist agents reviewed one case.

CASE PACKET:
{json.dumps(committee_packet, indent=2, default=str)}

Your job:
- Synthesize; do not merely average.
- Preserve meaningful disagreement and identify the strongest dissent.
- Distinguish evidence from inference.
- Penalize confidence when evidence is stale, absent, contradictory, or unverified.
- Identify the strongest bullish case and strongest bearish case even if the final disposition is NO_TRADE.
- Identify the key evidence required before the case could advance.
- PAPER MODE only; never recommend a real-money trade.
- Final disposition must be WATCH or NO_TRADE.
- Confidence must be 0.0 to 1.0.

Return ONLY valid JSON with exactly these fields:
{{
  "headline": "short committee headline",
  "summary": "3 to 5 sentence committee conclusion",
  "agreement": "what the specialists broadly agree on",
  "dissent": "strongest disagreement or objection",
  "bull_case": "strongest supported bullish case",
  "bear_case": "strongest supported bearish case",
  "required_evidence": ["next evidence item"],
  "confidence": 0.0,
  "disposition": "WATCH",
  "floor_comment": "short dry committee one-liner"
}}
"""

    response = client.responses.create(model="gpt-5.6-luna", input=prompt)

    try:
        analysis = json.loads(response.output_text)
        if not isinstance(analysis, dict):
            raise ValueError("Committee output was not a JSON object")
    except (json.JSONDecodeError, ValueError, TypeError):
        analysis = {
            "headline": "Committee review completed",
            "summary": response.output_text,
            "agreement": "Specialist reviews completed.",
            "dissent": "Dissent could not be structured.",
            "bull_case": "Not structured.",
            "bear_case": "Not structured.",
            "required_evidence": ["structured committee output"],
            "confidence": 0.25,
            "disposition": "NO_TRADE",
            "floor_comment": "Eight opinions entered. Governance kept the door locked.",
        }

    decision_id = f"decision_{uuid4().hex}"
    decision = {
        "decision_id": decision_id,
        "case_id": case["case_id"],
        "topic": case["topic"],
        "status": "complete",
        "headline": str(analysis.get("headline", "Committee review completed")),
        "summary": str(analysis.get("summary", "Committee review completed.")),
        "agreement": str(analysis.get("agreement", "No clear agreement recorded.")),
        "dissent": str(analysis.get("dissent", "No dissent recorded.")),
        "bull_case": str(analysis.get("bull_case", "No bull case recorded.")),
        "bear_case": str(analysis.get("bear_case", "No bear case recorded.")),
        "required_evidence": analysis.get("required_evidence", []),
        "confidence": clamp_confidence(analysis.get("confidence"), 0.25),
        "disposition": normalize_disposition(analysis.get("disposition")),
        "floor_comment": str(analysis.get("floor_comment", "Committee review complete.")),
        "agents": specialist_results,
        "created_at": utc_now(),
        "paper_mode": PAPER_MODE,
    }
    COMMITTEE_DECISIONS[decision_id] = decision
    return decision


@app.post("/committee/run")
def run_committee(request: dict = Body(...)):
    topic = str(request.get("topic", "")).strip()
    evidence = request.get("evidence") if isinstance(request.get("evidence"), list) else []
    case = new_case(topic, evidence)
    return build_committee(case)


def evaluate_decision(decision: dict[str, Any]) -> dict[str, Any]:
    triggered_rules: list[str] = []

    if decision["disposition"] == "NO_TRADE":
        triggered_rules.append("COMMITTEE_NO_TRADE")
    if decision["confidence"] < MIN_COMMITTEE_CONFIDENCE:
        triggered_rules.append("CONFIDENCE_BELOW_THRESHOLD")
    if not decision["topic"]:
        triggered_rules.append("MISSING_INVESTMENT_TOPIC")
    if decision.get("required_evidence"):
        triggered_rules.append("OPEN_EVIDENCE_REQUIREMENTS")

    # Current v0.2 policy intentionally cannot authorize capital.
    # Later paper-trading phases can introduce deterministic sizing rules here.
    decision_value = "VETOED" if triggered_rules else "WATCH_ONLY"
    allowed_notional = 0.0

    authorization_id = f"risk_{uuid4().hex}"
    authorization = {
        "risk_authorization_id": authorization_id,
        "decision_id": decision["decision_id"],
        "case_id": decision["case_id"],
        "room": "Risk Inspection",
        "status": "complete",
        "topic": decision["topic"],
        "decision": decision_value,
        "allowed_notional": allowed_notional,
        "triggered_rules": triggered_rules,
        "confidence_received": decision["confidence"],
        "committee_disposition": decision["disposition"],
        "floor_comment": (
            "Risk saw the proposal and quietly moved the keys."
            if decision_value == "VETOED"
            else "Interesting. Still not getting a company credit card."
        ),
        "paper_mode": PAPER_MODE,
        "created_at": utc_now(),
        "consumed": False,
    }
    RISK_AUTHORIZATIONS[authorization_id] = authorization
    return authorization


@app.post("/risk/evaluate")
def evaluate_risk(request: dict = Body(...)):
    decision_id = str(request.get("decision_id", "")).strip()

    if decision_id:
        decision = COMMITTEE_DECISIONS.get(decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Unknown committee decision_id")
        return evaluate_decision(decision)

    # Legacy compatibility for the existing UI: only accept fields that exactly match
    # the latest server-created committee decision for this topic.
    topic = str(request.get("topic", "")).strip()
    candidates = [d for d in COMMITTEE_DECISIONS.values() if d["topic"] == topic]
    if not candidates:
        raise HTTPException(
            status_code=409,
            detail="No server-created committee decision exists for this topic",
        )
    decision = candidates[-1]

    supplied_disposition = normalize_disposition(request.get("disposition"))
    supplied_confidence = clamp_confidence(request.get("confidence"), 0.0)
    if (
        supplied_disposition != decision["disposition"]
        or abs(supplied_confidence - decision["confidence"]) > 1e-9
    ):
        raise HTTPException(status_code=409, detail="Committee handoff mismatch")

    return evaluate_decision(decision)


@app.post("/paper-execution/submit")
def submit_paper_order(request: dict = Body(...)):
    authorization_id = str(request.get("risk_authorization_id", "")).strip()

    if authorization_id:
        authorization = RISK_AUTHORIZATIONS.get(authorization_id)
    else:
        # Legacy compatibility for the current UI. We never trust caller-supplied approval;
        # we resolve the latest server-issued authorization for the topic instead.
        topic = str(request.get("topic", "")).strip()
        matches = [a for a in RISK_AUTHORIZATIONS.values() if a["topic"] == topic]
        authorization = matches[-1] if matches else None

    if not authorization:
        raise HTTPException(status_code=409, detail="Valid risk authorization required")

    if authorization["consumed"]:
        raise HTTPException(status_code=409, detail="Risk authorization already consumed")

    authorization["consumed"] = True

    if authorization["decision"] != "APPROVED":
        return {
            "room": "Paper Execution",
            "status": "blocked",
            "case_id": authorization["case_id"],
            "decision_id": authorization["decision_id"],
            "risk_authorization_id": authorization["risk_authorization_id"],
            "topic": authorization["topic"],
            "execution": "NOT_SUBMITTED",
            "reason": "RISK_NOT_APPROVED",
            "risk_decision": authorization["decision"],
            "allowed_notional": 0,
            "paper_mode": PAPER_MODE,
            "floor_comment": "Execution checked the authorization. Risk did not approve capital.",
        }

    if authorization["allowed_notional"] <= 0:
        return {
            "room": "Paper Execution",
            "status": "blocked",
            "case_id": authorization["case_id"],
            "decision_id": authorization["decision_id"],
            "risk_authorization_id": authorization["risk_authorization_id"],
            "topic": authorization["topic"],
            "execution": "NOT_SUBMITTED",
            "reason": "NO_NOTIONAL_AUTHORIZED",
            "risk_decision": authorization["decision"],
            "allowed_notional": 0,
            "paper_mode": PAPER_MODE,
            "floor_comment": "Approval without capital is mostly decorative.",
        }

    execution_id = f"paper_{uuid4().hex}"
    execution = {
        "execution_id": execution_id,
        "room": "Paper Execution",
        "status": "complete",
        "case_id": authorization["case_id"],
        "decision_id": authorization["decision_id"],
        "risk_authorization_id": authorization["risk_authorization_id"],
        "topic": authorization["topic"],
        "execution": "PAPER_ORDER_CREATED",
        "risk_decision": authorization["decision"],
        "allowed_notional": authorization["allowed_notional"],
        "paper_mode": PAPER_MODE,
        "live_execution": False,
        "created_at": utc_now(),
        "floor_comment": "Paper order accepted. No actual money was harmed in the making of this trade.",
    }
    EXECUTIONS[execution_id] = execution
    return execution


@app.post("/factory/run")
def run_factory(request: TopicRequest):
    """Run one governed case end-to-end through committee, risk, and paper execution."""
    case = new_case(request.topic, request.evidence)
    committee = build_committee(case)
    risk = evaluate_decision(committee)
    execution = submit_paper_order({"risk_authorization_id": risk["risk_authorization_id"]})

    return {
        "case": case,
        "committee": committee,
        "risk": risk,
        "execution": execution,
        "chain": [
            "CASE_CREATED",
            "EIGHT_SPECIALISTS_COMPLETE",
            "COMMITTEE_COMPLETE",
            "RISK_COMPLETE",
            "PAPER_EXECUTION_CHECKED",
        ],
    }


@app.get("/audit/{case_id}")
def get_case_audit(case_id: str):
    case = CASES.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")

    decisions = [d for d in COMMITTEE_DECISIONS.values() if d["case_id"] == case_id]
    decision_ids = {d["decision_id"] for d in decisions}
    authorizations = [
        a for a in RISK_AUTHORIZATIONS.values() if a["decision_id"] in decision_ids
    ]
    auth_ids = {a["risk_authorization_id"] for a in authorizations}
    executions = [
        e for e in EXECUTIONS.values() if e["risk_authorization_id"] in auth_ids
    ]

    return {
        "case": case,
        "committee_decisions": decisions,
        "risk_authorizations": authorizations,
        "executions": executions,
    }
