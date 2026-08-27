import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

from evidence_engine import build_packet
from ledger import (
    consume_authorization,
    get_audit,
    get_object,
    latest_object,
    list_objects,
    record_event,
    record_object,
)
from paper_fund_operations_api import build_paper_fund_operations

load_dotenv()

app = FastAPI(title="Investment Intelligence OS", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PAPER_MODE = True
MIN_COMMITTEE_CONFIDENCE = 0.65
MIN_EVIDENCE_QUALITY = 0.55

AGENT_CONFIGS = {
    "policy": {"name":"Policy Analyst","room":"Policy Floor","focus":"government policy, executive actions, legislation, regulation, tariffs, industrial policy, fiscal transmission, and policy-sensitive sectors","stance":"Analyze policy transmission without assuming causality that is not evidenced."},
    "macro": {"name":"Macro & Rates Analyst","room":"Macro Desk","focus":"rates, inflation, growth, labor, liquidity, Federal Reserve policy, the dollar, credit conditions, and broad market transmission","stance":"Separate cyclical, liquidity, and policy effects and identify regime uncertainty."},
    "fundamentals": {"name":"Fundamentals Analyst","room":"Fundamentals Lab","focus":"revenue, earnings, margins, balance sheet quality, valuation, capital intensity, competitive position, and business-model durability","stance":"Distinguish business quality from security price and valuation attractiveness."},
    "market_structure": {"name":"Market Structure Analyst","room":"Tape & Positioning","focus":"price action, positioning, liquidity, volatility, crowding, flows, catalysts, technical structure, and what may already be priced in","stance":"Treat narrative and price behavior as separate evidence streams."},
    "commodities": {"name":"Commodities & Supply Chain Analyst","room":"Physical Markets","focus":"energy, agriculture, metals, freight, inventories, production, supply disruptions, seasonality, input costs, and supply-chain transmission","stance":"Focus on physical constraints, timing, seasonality, and second-order effects."},
    "geo_weather": {"name":"Geopolitics & Weather Analyst","room":"Global Events Room","focus":"war, sanctions, elections, geopolitical chokepoints, extreme weather, drought, hurricanes, crop conditions, and event-driven supply or demand shocks","stance":"Separate confirmed events from scenario risk and avoid sensational weighting."},
    "skeptic": {"name":"Skeptic / Red Team","room":"Red Team","focus":"false causality, confirmation bias, hidden assumptions, missing evidence, crowding, priced-in expectations, base-rate neglect, and alternative explanations","stance":"Attack the strongest version of the thesis and identify what would falsify it."},
    "portfolio": {"name":"Portfolio Context Analyst","room":"Portfolio Control","focus":"portfolio concentration, correlation, factor exposure, scenario overlap, opportunity cost, drawdown sensitivity, and whether a good idea is a good portfolio addition","stance":"Judge the idea in portfolio context rather than as an isolated prediction."},
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
    packet_id = f"packet_{uuid4().hex}"
    packet = {**build_packet(evidence), "evidence_packet_id": packet_id, "case_id": case_id}
    case = {
        "case_id": case_id,
        "topic": topic.strip(),
        "evidence_packet_id": packet_id,
        "evidence": packet["items"],
        "evidence_summary": packet["summary"],
        "created_at": utc_now(),
        "paper_mode": PAPER_MODE,
    }
    record_object(case_id, "case", case_id, case, topic=case["topic"])
    record_object(packet_id, "evidence_packet", case_id, packet, parent_id=case_id, topic=case["topic"])
    record_event(case_id, "CASE_CREATED", entity_id=case_id, payload={"topic": case["topic"], "evidence_count": packet["summary"]["evidence_count"]})
    record_event(case_id, "EVIDENCE_NORMALIZED", entity_id=packet_id, payload=packet["summary"])
    return case


def evidence_prompt(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "No structured evidence packet was supplied. Treat all claims requiring current data as unverified and explicitly state what fresh evidence is needed."
    return json.dumps(evidence, indent=2, default=str)


def run_specialist(agent_key: str, topic: str, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    config = AGENT_CONFIGS.get(agent_key)
    if not config:
        raise HTTPException(status_code=404, detail="Unknown agent")
    topic = topic.strip()
    if not topic:
        return {"agent_key":agent_key,"agent":config["name"],"room":config["room"],"status":"complete","topic":"","headline":"No thesis supplied","view":"A usable investment thesis or market question is required.","confidence":0.0,"disposition":"NO_TRADE","missing_evidence":["investment topic"],"falsifier":"No thesis exists to falsify.","floor_comment":"The desk received an empty folder."}

    client = OpenAI()
    prompt = f"""
You are the {config['name']} inside the Investment Intelligence OS.
TOPIC: {topic}
YOUR DOMAIN: {config['focus']}
YOUR OPERATING STANCE: {config['stance']}
NORMALIZED EVIDENCE PACKET:
{evidence_prompt(evidence or [])}
Rules:
- PAPER MODE only. Never recommend or execute a real-money trade.
- Use evidence quality, freshness_score, reliability_score, stale flags, conflict groups, and missing_fields explicitly.
- Do not pretend information is current when fresh data is required.
- Separate evidence, inference, and unknowns.
- Identify missing evidence that materially affects the conclusion.
- State at least one falsifier.
- Disposition must be WATCH or NO_TRADE.
- Confidence must be 0.0 to 1.0 and reflect evidence quality.
Return ONLY valid JSON with exactly these fields:
{{"headline":"short headline","view":"2 to 4 sentence domain analysis","confidence":0.0,"disposition":"WATCH","missing_evidence":["specific missing item"],"falsifier":"what would weaken or overturn this view","floor_comment":"short dry one-liner"}}
"""
    response = client.responses.create(model="gpt-5.6-luna", input=prompt)
    try:
        analysis = json.loads(response.output_text)
        if not isinstance(analysis, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError, TypeError):
        analysis = {"headline":f"{config['name']} review completed","view":response.output_text,"confidence":0.35,"disposition":"NO_TRADE","missing_evidence":["structured model output"],"falsifier":"Unable to structure falsifier from model output.","floor_comment":"The analysis arrived. The paperwork did not."}
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
    return {"message":"IIOS backend online","version":"0.4.0","paper_mode":PAPER_MODE,"governed_chain":True,"persistent_ledger":True,"evidence_engine":True}


@app.get("/agents")
def get_agents():
    return {"agents":[{"key":key,"name":config["name"],"room":config["room"],"status":"idle"} for key, config in AGENT_CONFIGS.items()]}


@app.get("/paper-fund/operations")
def paper_fund_operations():
    return build_paper_fund_operations()


@app.post("/evidence/normalize")
def normalize_evidence(request: dict = Body(...)):
    evidence = request.get("evidence") if isinstance(request.get("evidence"), list) else []
    return build_packet(evidence)


@app.post("/agents/{agent_key}/run")
def run_agent(agent_key: str, request: TopicRequest):
    packet = build_packet(request.evidence)
    return run_specialist(agent_key, request.topic, packet["items"])


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
    specialist_results = {key: run_specialist(key, case["topic"], case["evidence"]) for key in AGENT_CONFIGS}
    for key, result in specialist_results.items():
        result_id = f"agent_{uuid4().hex}"
        persistent = {**result,"agent_result_id":result_id,"case_id":case["case_id"],"evidence_packet_id":case["evidence_packet_id"],"created_at":utc_now()}
        specialist_results[key] = persistent
        record_object(result_id, "agent_result", case["case_id"], persistent, parent_id=case["evidence_packet_id"], topic=case["topic"])
        record_event(case["case_id"], "AGENT_COMPLETE", entity_id=result_id, payload={"agent_key":key,"confidence":persistent["confidence"],"disposition":persistent["disposition"]})

    client = OpenAI()
    committee_packet = {"case_id":case["case_id"],"topic":case["topic"],"evidence_summary":case["evidence_summary"],"specialists":specialist_results}
    prompt = f"""
You are the Investment Committee Chair inside the Investment Intelligence OS.
Eight specialist agents reviewed one case.
CASE PACKET:
{json.dumps(committee_packet, indent=2, default=str)}
Synthesize rather than average. Preserve dissent. Distinguish evidence from inference. Penalize stale, absent, contradictory, incomplete, or low-quality evidence using the evidence summary. Identify strongest bull and bear cases and required evidence. PAPER MODE only. Final disposition WATCH or NO_TRADE. Confidence 0.0 to 1.0.
Return ONLY valid JSON with exactly these fields:
{{"headline":"short committee headline","summary":"3 to 5 sentence committee conclusion","agreement":"what specialists agree on","dissent":"strongest objection","bull_case":"strongest supported bullish case","bear_case":"strongest supported bearish case","required_evidence":["next evidence item"],"confidence":0.0,"disposition":"WATCH","floor_comment":"short dry committee one-liner"}}
"""
    response = client.responses.create(model="gpt-5.6-luna", input=prompt)
    try:
        analysis = json.loads(response.output_text)
        if not isinstance(analysis, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError, TypeError):
        analysis = {"headline":"Committee review completed","summary":response.output_text,"agreement":"Specialist reviews completed.","dissent":"Dissent could not be structured.","bull_case":"Not structured.","bear_case":"Not structured.","required_evidence":["structured committee output"],"confidence":0.25,"disposition":"NO_TRADE","floor_comment":"Eight opinions entered. Governance kept the door locked."}

    decision_id = f"decision_{uuid4().hex}"
    decision = {
        "decision_id": decision_id,
        "case_id": case["case_id"],
        "evidence_packet_id": case["evidence_packet_id"],
        "evidence_summary": case["evidence_summary"],
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
    record_object(decision_id, "committee_decision", case["case_id"], decision, parent_id=case["evidence_packet_id"], topic=case["topic"])
    record_event(case["case_id"], "COMMITTEE_COMPLETE", entity_id=decision_id, payload={"confidence":decision["confidence"],"disposition":decision["disposition"]})
    return decision


@app.post("/committee/run")
def run_committee(request: dict = Body(...)):
    topic = str(request.get("topic", "")).strip()
    evidence = request.get("evidence") if isinstance(request.get("evidence"), list) else []
    return build_committee(new_case(topic, evidence))


def evaluate_decision(decision: dict[str, Any]) -> dict[str, Any]:
    triggered_rules: list[str] = []
    summary = decision.get("evidence_summary") or {}
    flags = set(summary.get("critical_flags") or [])
    if decision["disposition"] == "NO_TRADE":
        triggered_rules.append("COMMITTEE_NO_TRADE")
    if decision["confidence"] < MIN_COMMITTEE_CONFIDENCE:
        triggered_rules.append("CONFIDENCE_BELOW_THRESHOLD")
    if not decision["topic"]:
        triggered_rules.append("MISSING_INVESTMENT_TOPIC")
    if decision.get("required_evidence"):
        triggered_rules.append("OPEN_EVIDENCE_REQUIREMENTS")
    if summary.get("average_quality_score", 0.0) < MIN_EVIDENCE_QUALITY:
        triggered_rules.append("EVIDENCE_QUALITY_BELOW_THRESHOLD")
    if "NO_EVIDENCE_SUPPLIED" in flags:
        triggered_rules.append("NO_EVIDENCE_SUPPLIED")
    if "ALL_EVIDENCE_STALE" in flags:
        triggered_rules.append("ALL_EVIDENCE_STALE")
    if "CONFLICTING_EVIDENCE_PRESENT" in flags:
        triggered_rules.append("CONFLICTING_EVIDENCE_PRESENT")

    decision_value = "VETOED" if triggered_rules else "WATCH_ONLY"
    authorization_id = f"risk_{uuid4().hex}"
    authorization = {
        "risk_authorization_id": authorization_id,
        "decision_id": decision["decision_id"],
        "case_id": decision["case_id"],
        "evidence_packet_id": decision.get("evidence_packet_id"),
        "room": "Risk Inspection",
        "status": "complete",
        "topic": decision["topic"],
        "decision": decision_value,
        "allowed_notional": 0.0,
        "triggered_rules": triggered_rules,
        "confidence_received": decision["confidence"],
        "committee_disposition": decision["disposition"],
        "evidence_quality_received": summary.get("average_quality_score", 0.0),
        "floor_comment": "Risk saw the proposal and quietly moved the keys." if decision_value == "VETOED" else "Interesting. Still not getting a company credit card.",
        "paper_mode": PAPER_MODE,
        "created_at": utc_now(),
    }
    record_object(authorization_id, "risk_authorization", decision["case_id"], authorization, parent_id=decision["decision_id"], topic=decision["topic"])
    record_event(decision["case_id"], "RISK_COMPLETE", entity_id=authorization_id, payload={"decision":decision_value,"triggered_rules":triggered_rules})
    return authorization


@app.post("/risk/evaluate")
def evaluate_risk(request: dict = Body(...)):
    decision_id = str(request.get("decision_id", "")).strip()
    if decision_id:
        decision = get_object(decision_id)
        if not decision or not str(decision_id).startswith("decision_"):
            raise HTTPException(status_code=404, detail="Unknown committee decision_id")
        return evaluate_decision(decision)
    topic = str(request.get("topic", "")).strip()
    decision = latest_object("committee_decision", topic=topic)
    if not decision:
        raise HTTPException(status_code=409, detail="No server-created committee decision exists for this topic")
    if normalize_disposition(request.get("disposition")) != decision["disposition"] or abs(clamp_confidence(request.get("confidence"), 0.0) - decision["confidence"]) > 1e-9:
        raise HTTPException(status_code=409, detail="Committee handoff mismatch")
    return evaluate_decision(decision)


@app.post("/paper-execution/submit")
def submit_paper_order(request: dict = Body(...)):
    authorization_id = str(request.get("risk_authorization_id", "")).strip()
    authorization = get_object(authorization_id) if authorization_id else latest_object("risk_authorization", topic=str(request.get("topic", "")).strip())
    if not authorization:
        raise HTTPException(status_code=409, detail="Valid risk authorization required")
    authorization_id = authorization["risk_authorization_id"]
    if not consume_authorization(authorization_id):
        raise HTTPException(status_code=409, detail="Risk authorization already consumed or invalid")
    base = {"execution_id":f"paper_{uuid4().hex}","room":"Paper Execution","case_id":authorization["case_id"],"decision_id":authorization["decision_id"],"risk_authorization_id":authorization_id,"topic":authorization["topic"],"risk_decision":authorization["decision"],"paper_mode":PAPER_MODE,"live_execution":False,"created_at":utc_now()}
    if authorization["decision"] != "APPROVED":
        execution = {**base,"status":"blocked","execution":"NOT_SUBMITTED","reason":"RISK_NOT_APPROVED","allowed_notional":0,"floor_comment":"Execution checked the authorization. Risk did not approve capital."}
    elif authorization["allowed_notional"] <= 0:
        execution = {**base,"status":"blocked","execution":"NOT_SUBMITTED","reason":"NO_NOTIONAL_AUTHORIZED","allowed_notional":0,"floor_comment":"Approval without capital is mostly decorative."}
    else:
        execution = {**base,"status":"complete","execution":"PAPER_ORDER_CREATED","allowed_notional":authorization["allowed_notional"],"floor_comment":"Paper order accepted. No actual money was harmed in the making of this trade."}
    record_object(execution["execution_id"], "execution", authorization["case_id"], execution, parent_id=authorization_id, topic=authorization["topic"])
    record_event(authorization["case_id"], "PAPER_EXECUTION_CHECKED", entity_id=execution["execution_id"], payload={"status":execution["status"],"execution":execution["execution"],"reason":execution.get("reason")})
    return execution


@app.post("/factory/run")
def run_factory(request: TopicRequest):
    case = new_case(request.topic, request.evidence)
    committee = build_committee(case)
    risk = evaluate_decision(committee)
    execution = submit_paper_order({"risk_authorization_id":risk["risk_authorization_id"]})
    return {"case":case,"committee":committee,"risk":risk,"execution":execution,"chain":["CASE_CREATED","EVIDENCE_NORMALIZED","EIGHT_SPECIALISTS_COMPLETE","COMMITTEE_COMPLETE","RISK_COMPLETE","PAPER_EXECUTION_CHECKED"]}


@app.get("/audit/{case_id}")
def get_case_audit(case_id: str):
    case = get_object(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")
    audit = get_audit(case_id)
    return {
        "case": case,
        "evidence_packets": list_objects(case_id, "evidence_packet"),
        "agent_results": list_objects(case_id, "agent_result"),
        "committee_decisions": list_objects(case_id, "committee_decision"),
        "risk_authorizations": list_objects(case_id, "risk_authorization"),
        "executions": list_objects(case_id, "execution"),
        "events": audit["events"],
    }
