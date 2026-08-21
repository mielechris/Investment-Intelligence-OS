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