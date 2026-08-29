from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from main import AGENT_CONFIGS, clamp_confidence, normalize_disposition


CONTRACT_VERSION = "batch10m1-agent-contract-v2"
MODEL = "gpt-5.6-luna"
MAX_KEY_CLAIMS = 6
MAX_GAPS = 6
MAX_QUESTIONS = 5


def _list(value: Any, *, limit: int = 10, chars: int = 800) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text[:chars])
        if len(out) >= limit:
            break
    return out


def _evidence_ids(evidence: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("evidence_id") or "").strip()
        for item in evidence
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }


def _claim_rows(value: Any, allowed_ids: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    invalid_refs: list[str] = []
    if not isinstance(value, list):
        return rows, invalid_refs
    for item in value[:MAX_KEY_CLAIMS]:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()[:1200]
        if not claim:
            continue
        refs = []
        for raw in item.get("evidence_ids") or []:
            ref = str(raw or "").strip()
            if ref in allowed_ids:
                refs.append(ref)
            elif ref:
                invalid_refs.append(ref)
        rows.append(
            {
                "claim": claim,
                "evidence_ids": list(dict.fromkeys(refs))[:8],
                "confidence": clamp_confidence(item.get("confidence"), 0.35),
                "direction": str(item.get("direction") or "neutral").lower()[:32],
                "inference": bool(item.get("inference", False)),
            }
        )
    return rows, list(dict.fromkeys(invalid_refs))[:20]


def _confidence_components(value: Any) -> dict[str, float]:
    src = value if isinstance(value, dict) else {}
    return {
        "evidence_quality": clamp_confidence(src.get("evidence_quality"), 0.35),
        "causal_strength": clamp_confidence(src.get("causal_strength"), 0.35),
        "timing_clarity": clamp_confidence(src.get("timing_clarity"), 0.35),
        "contradiction_resilience": clamp_confidence(src.get("contradiction_resilience"), 0.35),
    }


def _scenario(value: Any, name: str) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    return {
        "name": name,
        "case": str(row.get("case") or "Not established.")[:1800],
        "probability": clamp_confidence(row.get("probability"), 0.0),
        "drivers": _list(row.get("drivers"), limit=5),
        "invalidators": _list(row.get("invalidators"), limit=5),
    }


def _scenarios(value: Any) -> dict[str, dict[str, Any]]:
    src = value if isinstance(value, dict) else {}
    return {
        "bull": _scenario(src.get("bull"), "bull"),
        "base": _scenario(src.get("base"), "base"),
        "bear": _scenario(src.get("bear"), "bear"),
    }


def _empty_result(agent_key: str, topic: str) -> dict[str, Any]:
    config = AGENT_CONFIGS[agent_key]
    return {
        "agent_key": agent_key,
        "agent": config["name"],
        "room": config["room"],
        "status": "complete",
        "topic": topic,
        "headline": "No thesis supplied",
        "view": "A usable investment thesis or market question is required.",
        "confidence": 0.0,
        "disposition": "NO_TRADE",
        "missing_evidence": ["investment topic"],
        "falsifier": "No thesis exists to falsify.",
        "floor_comment": "The desk received an empty folder.",
        "contract_version": CONTRACT_VERSION,
        "key_claims": [],
        "catalyst_timeline": [],
        "scenarios": _scenarios({}),
        "confidence_components": _confidence_components({}),
        "contradictions": [],
        "missing_evidence_ranked": ["investment topic"],
        "falsifiers": ["No thesis exists to falsify."],
        "questions_for_other_desks": [],
        "risk_flags": ["NO_TOPIC"],
        "evidence_ids_used": [],
        "invalid_evidence_references": [],
        "evidence_linkage_ratio": 0.0,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def run_specialist_v2(
    agent_key: str,
    topic: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One-call specialist contract with richer evidence linkage.

    This intentionally replaces no call with multiple calls. It returns all legacy
    specialist fields plus v2 structured reasoning fields so existing consumers
    remain compatible.
    """
    config = AGENT_CONFIGS.get(agent_key)
    if not config:
        raise KeyError(f"Unknown agent: {agent_key}")
    topic = str(topic or "").strip()
    if not topic:
        return _empty_result(agent_key, topic)

    items = [row for row in (evidence or []) if isinstance(row, dict)]
    allowed_ids = _evidence_ids(items)
    evidence_text = json.dumps(items, indent=2, ensure_ascii=False, default=str)
    prompt = f"""
You are the {config['name']} inside the governed PAPER-ONLY Investment Intelligence OS.

TOPIC: {topic}
YOUR DOMAIN: {config['focus']}
YOUR OPERATING STANCE: {config['stance']}

NORMALIZED EVIDENCE PACKET:
{evidence_text if items else 'No structured evidence packet was supplied.'}

AGENT CONTRACT V2 RULES:
- Perform exactly one desk review; do not ask another model or tool to research for you.
- Use only evidence supplied in this packet. Never invent an evidence_id.
- Every material factual key_claim should cite one or more evidence_ids when evidence supports it.
- If a claim is inference rather than directly supported fact, mark inference=true.
- Explicitly separate evidence, inference, contradictions, and unknowns.
- Use quality_score, freshness_score, reliability_score, stale, conflict_group, and missing_fields.
- Build bull/base/bear scenarios as analytical possibilities, not trading instructions.
- Probabilities are scenario weights, not expected returns, and must remain 0.0 to 1.0.
- Rank missing evidence by what could most change your conclusion.
- Ask other desks only questions that could materially change the case.
- State concrete falsifiers and catalyst timing when supported.
- PAPER MODE only. Never recommend or execute a real-money trade.
- Disposition must be WATCH or NO_TRADE only.
- Overall confidence must be 0.0 to 1.0 and reflect evidence quality and contradictions.

Return ONLY valid JSON with these fields:
{{
  "headline":"short headline",
  "view":"2 to 4 sentence domain conclusion",
  "confidence":0.0,
  "disposition":"WATCH",
  "missing_evidence":["legacy compatibility gap"],
  "falsifier":"legacy compatibility falsifier",
  "floor_comment":"short dry one-liner",
  "key_claims":[{{"claim":"material claim","evidence_ids":["evidence_id_from_packet"],"confidence":0.0,"direction":"bullish|bearish|neutral","inference":false}}],
  "catalyst_timeline":["dated or sequenced catalyst only when supported"],
  "scenarios":{{
    "bull":{{"case":"scenario","probability":0.0,"drivers":["driver"],"invalidators":["invalidator"]}},
    "base":{{"case":"scenario","probability":0.0,"drivers":["driver"],"invalidators":["invalidator"]}},
    "bear":{{"case":"scenario","probability":0.0,"drivers":["driver"],"invalidators":["invalidator"]}}
  }},
  "confidence_components":{{"evidence_quality":0.0,"causal_strength":0.0,"timing_clarity":0.0,"contradiction_resilience":0.0}},
  "contradictions":["specific conflict or alternative explanation"],
  "missing_evidence_ranked":["highest-value missing evidence first"],
  "falsifiers":["specific observable falsifier"],
  "questions_for_other_desks":["material cross-desk question"],
  "risk_flags":["concise risk flag"]
}}
"""

    response = OpenAI().responses.create(model=MODEL, input=prompt)
    try:
        analysis = json.loads(response.output_text)
        if not isinstance(analysis, dict):
            raise ValueError("specialist output was not an object")
    except Exception:
        analysis = {
            "headline": f"{config['name']} review completed",
            "view": str(response.output_text or "")[:5000],
            "confidence": 0.25,
            "disposition": "NO_TRADE",
            "missing_evidence": ["structured model output"],
            "falsifier": "Unable to structure a falsifier from model output.",
            "floor_comment": "The analysis arrived. The paperwork did not.",
            "key_claims": [],
            "missing_evidence_ranked": ["structured model output"],
            "falsifiers": ["Unable to structure a falsifier from model output."],
            "risk_flags": ["STRUCTURED_OUTPUT_FALLBACK"],
        }

    claims, invalid_refs = _claim_rows(analysis.get("key_claims"), allowed_ids)
    linked_claims = sum(1 for row in claims if row.get("evidence_ids"))
    linkage_ratio = round(linked_claims / len(claims), 4) if claims else 0.0
    used = []
    for row in claims:
        used.extend(row.get("evidence_ids") or [])

    missing_ranked = _list(
        analysis.get("missing_evidence_ranked"), limit=MAX_GAPS
    ) or _list(analysis.get("missing_evidence"), limit=MAX_GAPS)
    falsifiers = _list(analysis.get("falsifiers"), limit=5)
    legacy_falsifier = str(analysis.get("falsifier") or "No falsifier recorded.")[:1200]
    if not falsifiers and legacy_falsifier:
        falsifiers = [legacy_falsifier]

    return {
        "agent_key": agent_key,
        "agent": config["name"],
        "room": config["room"],
        "status": "complete",
        "topic": topic,
        # Legacy contract retained.
        "headline": str(analysis.get("headline") or f"{config['name']} review completed")[:1000],
        "view": str(analysis.get("view") or "Review completed.")[:5000],
        "confidence": clamp_confidence(analysis.get("confidence"), 0.35),
        "disposition": normalize_disposition(analysis.get("disposition")),
        "missing_evidence": _list(analysis.get("missing_evidence"), limit=MAX_GAPS) or missing_ranked,
        "falsifier": legacy_falsifier,
        "floor_comment": str(analysis.get("floor_comment") or "Desk review complete.")[:1000],
        # V2 intelligence contract.
        "contract_version": CONTRACT_VERSION,
        "key_claims": claims,
        "catalyst_timeline": _list(analysis.get("catalyst_timeline"), limit=8),
        "scenarios": _scenarios(analysis.get("scenarios")),
        "confidence_components": _confidence_components(analysis.get("confidence_components")),
        "contradictions": _list(analysis.get("contradictions"), limit=8),
        "missing_evidence_ranked": missing_ranked,
        "falsifiers": falsifiers,
        "questions_for_other_desks": _list(analysis.get("questions_for_other_desks"), limit=MAX_QUESTIONS),
        "risk_flags": _list(analysis.get("risk_flags"), limit=8, chars=300),
        "evidence_ids_used": list(dict.fromkeys(used))[:30],
        "invalid_evidence_references": invalid_refs,
        "evidence_linkage_ratio": linkage_ratio,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
