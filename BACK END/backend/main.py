import json

from dotenv import load_dotenv
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:5173"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


class PolicyRequest(BaseModel):
	topic: str


@app.get("/")
def root():
	return {"message": "Hello from IIOS backend"}


@app.get("/agents")
def get_agents():
	return {
		"agents": [
			{
				"name": "Policy Analyst",
				"room": "Policy Floor",
				"status": "idle",
			},
			{
				"name": "Macro Analyst",
				"room": "Macro Desk",
				"status": "idle",
			},
			{
				"name": "Skeptic",
				"room": "Red Team",
				"status": "idle",
			},
		]
	}


@app.post("/agents/policy/run")
def run_policy_agent(request: PolicyRequest):
	client = OpenAI()

	prompt = f"""
You are the Policy Analyst inside the Investment Intelligence OS.

Analyze this topic:

{request.topic}

Important rules:
- This is PAPER MODE only.
- You do not have live market data or live web access yet.
- Do not pretend information is current if that requires live data.
- Separate what is known from what would require fresh evidence.
- Do not recommend a real-money trade.
- Disposition must be WATCH or NO_TRADE.
- Be concise and analytical.
- Include uncertainty.
- Use dry, professional floor humor in the floor_comment.

Return ONLY valid JSON with exactly these fields:

{{
  "headline": "short headline",
  "view": "2 to 4 sentence analysis",
  "confidence": 0.0,
  "disposition": "WATCH",
  "floor_comment": "short dry one-liner"
}}
"""

	response = client.responses.create(
		model="gpt-5.6-luna",
		input=prompt,
	)

	try:
		analysis = json.loads(response.output_text)
	except json.JSONDecodeError:
		analysis = {
			"headline": "Policy analysis completed",
			"view": response.output_text,
			"confidence": 0.5,
			"disposition": "WATCH",
			"floor_comment": "The machine had thoughts. Formatting had other plans.",
		}

	return {
		"agent": "Policy Analyst",
		"status": "complete",
		"topic": request.topic,
		"headline": analysis["headline"],
		"view": analysis["view"],
		"confidence": analysis["confidence"],
		"disposition": analysis["disposition"],
		"floor_comment": analysis["floor_comment"],
	}
class MacroRequest(BaseModel):
    topic: str


@app.post("/agents/macro/run")
def run_macro_agent(request: MacroRequest):
    client = OpenAI()

    prompt = f"""
You are the Macro and Rates Analyst inside the Investment Intelligence OS.

Analyze this topic:

{request.topic}

Important rules:
- This is PAPER MODE only.
- You do not have live market data or live web access yet.
- Do not pretend information is current if fresh data would be required.
- Focus on rates, inflation, growth, labor, liquidity, the Federal Reserve,
  the dollar, and broad market transmission where relevant.
- Clearly identify what fresh evidence would be needed.
- Do not recommend a real-money trade.
- Disposition must be WATCH or NO_TRADE.
- Be concise and analytical.
- Include uncertainty.
- Use dry professional market-floor humor in the floor_comment.

Return ONLY valid JSON with exactly these fields:

{{
  "headline": "short headline",
  "view": "2 to 4 sentence macro analysis",
  "confidence": 0.0,
  "disposition": "WATCH",
  "floor_comment": "short dry one-liner"
}}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt,
    )

    try:
        analysis = json.loads(response.output_text)
    except json.JSONDecodeError:
        analysis = {
            "headline": "Macro analysis completed",
            "view": response.output_text,
            "confidence": 0.5,
            "disposition": "WATCH",
            "floor_comment": "Rates moved. Economists formed a committee.",
        }

    return {
        "agent": "Macro Analyst",
        "status": "complete",
        "topic": request.topic,
        "headline": analysis["headline"],
        "view": analysis["view"],
        "confidence": analysis["confidence"],
        "disposition": analysis["disposition"],
        "floor_comment": analysis["floor_comment"],

 }
@app.post("/agents/skeptic/run")
def run_skeptic_agent(request: dict = Body(...)):
    topic = str(request.get("topic", "")).strip()

    if not topic:
        return {
            "agent": "Skeptic",
            "status": "complete",
            "topic": "",
            "headline": "No thesis supplied",
            "view": "The Red Team needs an actual thesis or market claim to challenge.",
            "confidence": 0.0,
            "disposition": "NO_TRADE",
            "floor_comment": "Even the skeptic needs something to complain about.",
        }

    client = OpenAI()

    prompt = f"""
You are the Skeptic / Red Team inside the Investment Intelligence OS.

Analyze this topic:

{topic}

Your job is to challenge the leading narrative.

Important rules:
- This is PAPER MODE only.
- You do not have live market data or live web access yet.
- Do not pretend information is current if fresh evidence would be required.
- Look for false causality, confirmation bias, priced-in expectations,
  crowding, hidden assumptions, missing evidence, and alternative explanations.
- Do not recommend a real-money trade.
- Disposition must be WATCH or NO_TRADE.
- Be concise and analytical.
- Include uncertainty.
- Use dry professional market-floor humor in the floor_comment.

Return ONLY valid JSON with exactly these fields:

{{
  "headline": "short skeptical headline",
  "view": "2 to 4 sentence red-team analysis",
  "confidence": 0.0,
  "disposition": "NO_TRADE",
  "floor_comment": "short dry one-liner"
}}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt,
    )

    try:
        analysis = json.loads(response.output_text)

        if not isinstance(analysis, dict):
            raise ValueError("Model output was not a JSON object")

    except (json.JSONDecodeError, ValueError, TypeError):
        analysis = {
            "headline": "Red Team review completed",
            "view": response.output_text,
            "confidence": 0.5,
            "disposition": "NO_TRADE",
            "floor_comment": "Someone had to ask the uncomfortable question.",
        }

    try:
        confidence = float(analysis.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    confidence = max(0.0, min(1.0, confidence))

    return {
        "agent": "Skeptic",
        "status": "complete",
        "topic": topic,
        "headline": analysis.get(
            "headline",
            "Red Team review completed"
        ),
        "view": analysis.get(
            "view",
            "The Red Team completed its review."
        ),
        "confidence": confidence,
        "disposition": analysis.get(
            "disposition",
            "NO_TRADE"
        ),
        "floor_comment": analysis.get(
            "floor_comment",
            "Someone had to ask the uncomfortable question."
        ),
    }
    class CommitteeRequest(BaseModel):
        topic: str


@app.post("/committee/run")
def run_committee(request: dict = Body(...)):
    topic = str(request.get("topic", "")).strip()

    policy_result = run_policy_agent(
        PolicyRequest(topic=topic)
    )

    macro_result = run_macro_agent(
        MacroRequest(topic=topic)
    )

    skeptic_result = run_skeptic_agent(
        {"topic": topic}
    )

    client = OpenAI()

    committee_packet = {
        "topic": topic,
        "policy": policy_result,
        "macro": macro_result,
        "skeptic": skeptic_result,
    }

    prompt = f"""
You are the Investment Committee Chair inside the
Investment Intelligence OS.

Three specialist agents reviewed the same topic.

TOPIC:
{topic}

SPECIALIST OUTPUTS:
{json.dumps(committee_packet, indent=2)}

Your job:
- Compare the Policy Analyst, Macro Analyst, and Skeptic.
- Preserve meaningful disagreement.
- Do not average away dissent.
- Identify what they agree on.
- Identify what remains uncertain.
- This is PAPER MODE only.
- There is no live market or web data yet.
- Do not pretend the information is current.
- Do not recommend a real-money trade.
- Final disposition must be WATCH or NO_TRADE.
- Confidence must be between 0.0 and 1.0.
- Be concise.
- Keep the floor_comment dry and professional.

Return ONLY valid JSON with exactly these fields:

{{
  "headline": "short committee headline",
  "summary": "3 to 5 sentence committee conclusion",
  "agreement": "what the agents broadly agree on",
  "dissent": "the strongest disagreement or objection",
  "confidence": 0.0,
  "disposition": "WATCH",
  "floor_comment": "short dry committee one-liner"
}}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt,
    )

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
            "confidence": 0.5,
            "disposition": "NO_TRADE",
            "floor_comment": "The committee met. Minutes were taken. Nobody panicked.",
        }

    try:
        confidence = float(analysis.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    confidence = max(0.0, min(1.0, confidence))

    return {
        "topic": topic,
        "status": "complete",
        "headline": analysis.get(
            "headline",
            "Committee review completed"
        ),
        "summary": analysis.get(
            "summary",
            "Committee review completed."
        ),
        "agreement": analysis.get(
            "agreement",
            "No clear agreement recorded."
        ),
        "dissent": analysis.get(
            "dissent",
            "No dissent recorded."
        ),
        "confidence": confidence,
        "disposition": analysis.get(
            "disposition",
            "NO_TRADE"
        ),
        "floor_comment": analysis.get(
            "floor_comment",
            "Three analysts entered. A decision eventually left."
        ),
        "agents": {
            "policy": policy_result,
            "macro": macro_result,
            "skeptic": skeptic_result,
        },
    }
@app.post("/risk/evaluate")
def evaluate_risk(request: dict = Body(...)):
    topic = str(request.get("topic", "")).strip()
    disposition = str(
        request.get("disposition", "NO_TRADE")
    ).upper()

    try:
        confidence = float(
            request.get("confidence", 0.0)
        )
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))

    triggered_rules = []

    if disposition == "NO_TRADE":
        triggered_rules.append("COMMITTEE_NO_TRADE")

    if confidence < 0.65:
        triggered_rules.append("CONFIDENCE_BELOW_THRESHOLD")

    if not topic:
        triggered_rules.append("MISSING_INVESTMENT_TOPIC")

    if triggered_rules:
        decision = "VETOED"
        allowed_notional = 0
        floor_comment = "Risk saw the proposal and quietly moved the keys."
    else:
        decision = "WATCH_ONLY"
        allowed_notional = 0
        floor_comment = "Interesting. Still not getting a company credit card."

    return {
        "room": "Risk Inspection",
        "status": "complete",
        "topic": topic,
        "decision": decision,
        "allowed_notional": allowed_notional,
        "triggered_rules": triggered_rules,
        "confidence_received": confidence,
        "committee_disposition": disposition,
        "floor_comment": floor_comment,
        "paper_mode": True,
    }