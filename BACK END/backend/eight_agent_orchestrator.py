from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from openai import OpenAI

from evidence_engine import build_packet
from ledger import get_object, latest_object, record_event, record_object, utc_now
from main import AGENT_CONFIGS, clamp_confidence, normalize_disposition, run_specialist


router = APIRouter()

PAPER_MODE = True
FIRST_WAVE = (
    "policy",
    "macro",
    "fundamentals",
    "market_structure",
    "commodities",
    "geo_weather",
)
SECOND_WAVE = ("skeptic", "portfolio")
MAX_PARALLEL_SPECIALISTS = 3


def agent_wave_plan() -> dict[str, Any]:
    return {
        "first_wave": list(FIRST_WAVE),
        "second_wave": list(SECOND_WAVE),
        "all_agents": list(FIRST_WAVE + SECOND_WAVE),
        "max_parallel_specialists": MAX_PARALLEL_SPECIALISTS,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _error_result(agent_key: str, topic: str, exc: Exception) -> dict[str, Any]:
    config = AGENT_CONFIGS[agent_key]
    return {
        "agent_key": agent_key,
        "agent": config["name"],
        "room": config["room"],
        "status": "error",
        "topic": topic,
        "headline": f"{config['name']} unavailable",
        "view": "The desk failed to return a governed analysis and cannot be counted as complete.",
        "confidence": 0.0,
        "disposition": "NO_TRADE",
        "missing_evidence": ["successful specialist analysis"],
        "falsifier": "No governed specialist output was produced.",
        "floor_comment": "Desk offline; committee must fail closed.",
        "error": f"{type(exc).__name__}: {exc}",
    }


def _run_one(agent_key: str, topic: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        return run_specialist(agent_key, topic, evidence)
    except Exception as exc:
        return _error_result(agent_key, topic, exc)


def _peer_context_items(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, result in results.items():
        items.append(
            {
                "source": "IIOS Agent Floor",
                "source_type": "governed_analysis",
                "evidence_type": "agent_context",
                "url": f"iios://agent-floor/{key}",
                "title": f"Peer desk context: {result.get('agent') or key}",
                "claim": (
                    f"Disposition={result.get('disposition')}; confidence={result.get('confidence')}; "
                    f"headline={result.get('headline')}; view={result.get('view')}; "
                    f"falsifier={result.get('falsifier')}"
                ),
                "timestamp": utc_now(),
                "reliability_score": 0.65,
                "gap_resolution_eligible": False,
                "governed_analysis": True,
                "trade_signal": False,
                "trade_execution_permission": False,
            }
        )
    return items


def _persist_agent_result(
    *,
    case_id: str,
    topic: str,
    evidence_packet_id: str | None,
    result: dict[str, Any],
    wave: int,
) -> dict[str, Any]:
    result_id = f"agent_{uuid4().hex}"
    persistent = {
        **result,
        "agent_result_id": result_id,
        "case_id": case_id,
        "evidence_packet_id": evidence_packet_id,
        "orchestration_wave": wave,
        "created_at": utc_now(),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(
        result_id,
        "agent_result",
        case_id,
        persistent,
        parent_id=evidence_packet_id,
        topic=topic,
    )
    record_event(
        case_id,
        "AGENT_COMPLETE" if persistent.get("status") == "complete" else "AGENT_FAILED_CLOSED",
        entity_id=result_id,
        payload={
            "agent_key": persistent.get("agent_key"),
            "confidence": persistent.get("confidence"),
            "disposition": persistent.get("disposition"),
            "orchestration_wave": wave,
            "trade_execution_permission": False,
        },
    )
    return persistent


def committee_guard(
    *,
    specialists: dict[str, dict[str, Any]],
    evidence_summary: dict[str, Any],
    requested_disposition: str,
) -> dict[str, Any]:
    required = set(FIRST_WAVE + SECOND_WAVE)
    complete = {
        key
        for key, value in specialists.items()
        if value.get("status") == "complete"
    }
    flags = set(evidence_summary.get("critical_flags") or [])
    checks = {
        "all_eight_agents_complete": required.issubset(complete),
        "skeptic_complete": "skeptic" in complete,
        "portfolio_complete": "portfolio" in complete,
        "evidence_supplied": "NO_EVIDENCE_SUPPLIED" not in flags,
        "evidence_not_all_stale": "ALL_EVIDENCE_STALE" not in flags,
    }
    failed = [key for key, passed in checks.items() if not passed]
    disposition = normalize_disposition(requested_disposition)
    if failed:
        disposition = "NO_TRADE"
    return {
        "checks": checks,
        "failed_checks": failed,
        "final_disposition": disposition,
        "committee_can_watch": not failed,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _committee_metrics(specialists: dict[str, dict[str, Any]]) -> dict[str, Any]:
    confidences = [
        clamp_confidence(row.get("confidence"), 0.0)
        for row in specialists.values()
    ]
    watch_agents = [key for key, row in specialists.items() if row.get("disposition") == "WATCH"]
    no_trade_agents = [key for key, row in specialists.items() if row.get("disposition") == "NO_TRADE"]
    return {
        "agent_count": len(specialists),
        "watch_count": len(watch_agents),
        "no_trade_count": len(no_trade_agents),
        "watch_agents": watch_agents,
        "no_trade_agents": no_trade_agents,
        "mean_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "min_confidence": round(min(confidences), 4) if confidences else 0.0,
        "max_confidence": round(max(confidences), 4) if confidences else 0.0,
        "confidence_dispersion": round(max(confidences) - min(confidences), 4) if confidences else 0.0,
    }


def _synthesize_committee(
    *,
    case_id: str,
    topic: str,
    evidence_summary: dict[str, Any],
    specialists: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metrics = _committee_metrics(specialists)
    packet = {
        "case_id": case_id,
        "topic": topic,
        "evidence_summary": evidence_summary,
        "agent_metrics": metrics,
        "specialists": specialists,
    }
    prompt = f"""
You are the Investment Committee Chair inside a PAPER-ONLY Investment Intelligence OS.
Eight specialist desks have completed a peer-aware two-wave review.

CASE PACKET:
{json.dumps(packet, indent=2, default=str)}

Rules:
- Synthesize; do not simply average.
- Preserve dissent and name the strongest disagreement.
- Separate evidence from inference and unknowns.
- Penalize stale, conflicting, missing, or low-quality evidence.
- The Skeptic and Portfolio desks reviewed peer context and deserve explicit treatment.
- Never recommend or execute a real-money trade.
- Final disposition must be WATCH or NO_TRADE only.
- Confidence must be 0.0 to 1.0.
Return ONLY JSON with exactly these fields:
{{"headline":"short headline","summary":"3 to 5 sentence conclusion","agreement":"shared view","dissent":"strongest disagreement","bull_case":"strongest supported bull case","bear_case":"strongest supported bear case","key_disagreements":["specific disagreement"],"required_evidence":["specific next evidence"],"confidence":0.0,"disposition":"WATCH","floor_comment":"short dry one-liner"}}
"""
    try:
        response = OpenAI().responses.create(model="gpt-5.6-luna", input=prompt)
        analysis = json.loads(response.output_text)
        if not isinstance(analysis, dict):
            raise ValueError("Committee output was not an object")
    except Exception as exc:
        analysis = {
            "headline": "Committee synthesis unavailable",
            "summary": "The committee model failed to return a governed structured synthesis.",
            "agreement": "Specialist records remain available for review.",
            "dissent": "Committee synthesis unavailable.",
            "bull_case": "Not established.",
            "bear_case": "Committee failure itself requires a fail-closed result.",
            "key_disagreements": [],
            "required_evidence": ["successful committee synthesis"],
            "confidence": 0.0,
            "disposition": "NO_TRADE",
            "floor_comment": "The committee room lost power; the gate stayed shut.",
            "error": f"{type(exc).__name__}: {exc}",
        }

    guard = committee_guard(
        specialists=specialists,
        evidence_summary=evidence_summary,
        requested_disposition=str(analysis.get("disposition") or "NO_TRADE"),
    )
    decision_id = f"decision_{uuid4().hex}"
    decision = {
        "decision_id": decision_id,
        "case_id": case_id,
        "topic": topic,
        "status": "complete",
        "headline": str(analysis.get("headline") or "Committee review completed"),
        "summary": str(analysis.get("summary") or "Committee review completed."),
        "agreement": str(analysis.get("agreement") or "No clear agreement recorded."),
        "dissent": str(analysis.get("dissent") or "No dissent recorded."),
        "bull_case": str(analysis.get("bull_case") or "No bull case recorded."),
        "bear_case": str(analysis.get("bear_case") or "No bear case recorded."),
        "key_disagreements": analysis.get("key_disagreements") if isinstance(analysis.get("key_disagreements"), list) else [],
        "required_evidence": analysis.get("required_evidence") if isinstance(analysis.get("required_evidence"), list) else [],
        "confidence": clamp_confidence(analysis.get("confidence"), 0.0),
        "disposition": guard["final_disposition"],
        "floor_comment": str(analysis.get("floor_comment") or "Committee review complete."),
        "agents": specialists,
        "agent_metrics": metrics,
        "orchestration_guard": guard,
        "created_at": utc_now(),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    return decision


def run_eight_agent_orchestration(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise ValueError("Unknown case_id")

    topic = str(case.get("topic") or "").strip()
    evidence = case.get("evidence") if isinstance(case.get("evidence"), list) else []
    packet = build_packet(evidence)
    evidence_items = packet["items"]
    evidence_summary = packet["summary"]
    evidence_packet_id = case.get("evidence_packet_id")

    orchestration_id = f"orchestration_{uuid4().hex}"
    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SPECIALISTS) as pool:
        future_map = {
            pool.submit(_run_one, agent_key, topic, evidence_items): agent_key
            for agent_key in FIRST_WAVE
        }
        for future in as_completed(future_map):
            key = future_map[future]
            result = future.result()
            results[key] = _persist_agent_result(
                case_id=case_id,
                topic=topic,
                evidence_packet_id=evidence_packet_id,
                result=result,
                wave=1,
            )

    peer_context = _peer_context_items(results)
    second_wave_evidence = list(evidence_items) + peer_context
    for key in SECOND_WAVE:
        result = _run_one(key, topic, second_wave_evidence)
        results[key] = _persist_agent_result(
            case_id=case_id,
            topic=topic,
            evidence_packet_id=evidence_packet_id,
            result=result,
            wave=2,
        )

    # Present specialists in the canonical eight-desk order regardless of parallel completion order.
    ordered = {key: results[key] for key in FIRST_WAVE + SECOND_WAVE if key in results}
    decision = _synthesize_committee(
        case_id=case_id,
        topic=topic,
        evidence_summary=evidence_summary,
        specialists=ordered,
    )
    decision["evidence_packet_id"] = evidence_packet_id
    decision["orchestration_id"] = orchestration_id
    record_object(
        decision["decision_id"],
        "committee_decision",
        case_id,
        decision,
        parent_id=evidence_packet_id,
        topic=topic,
    )

    orchestration = {
        "orchestration_id": orchestration_id,
        "case_id": case_id,
        "topic": topic,
        "wave_plan": agent_wave_plan(),
        "agent_metrics": decision["agent_metrics"],
        "committee_decision_id": decision["decision_id"],
        "committee_disposition": decision["disposition"],
        "committee_confidence": decision["confidence"],
        "agents": ordered,
        "created_at": utc_now(),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(orchestration_id, "agent_orchestration", case_id, orchestration, parent_id=evidence_packet_id, topic=topic)
    record_event(
        case_id,
        "EIGHT_AGENT_ORCHESTRATION_COMPLETE",
        entity_id=orchestration_id,
        payload={
            "agent_count": len(ordered),
            "committee_disposition": decision["disposition"],
            "committee_confidence": decision["confidence"],
            "failed_guard_checks": decision["orchestration_guard"]["failed_checks"],
            "trade_execution_permission": False,
        },
    )
    return {"orchestration": orchestration, "committee": decision}


@router.get("/orchestration/plan")
def get_orchestration_plan():
    return agent_wave_plan()


@router.post("/orchestration/{case_id}/run")
def run_orchestration(case_id: str):
    try:
        return run_eight_agent_orchestration(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/orchestration/{case_id}/status")
def orchestration_status(case_id: str):
    case = get_object(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")
    orchestration = latest_object("agent_orchestration", case_id=case_id)
    committee = latest_object("committee_decision", case_id=case_id)
    return {
        "case_id": case_id,
        "latest_orchestration": orchestration,
        "latest_committee": committee,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
