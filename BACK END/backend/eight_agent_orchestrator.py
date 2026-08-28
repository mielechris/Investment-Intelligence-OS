from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from openai import OpenAI

from evidence_engine import build_packet
from historical_pattern_analyst import AGENT_KEY as HISTORICAL_AGENT_KEY
from historical_pattern_analyst import AGENT_NAME as HISTORICAL_AGENT_NAME
from historical_pattern_analyst import ROOM as HISTORICAL_ROOM
from historical_pattern_analyst import run_historical_pattern_review
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
THIRD_WAVE = (HISTORICAL_AGENT_KEY,)
CORE_EIGHT = FIRST_WAVE + SECOND_WAVE
ALL_REVIEW_DESKS = CORE_EIGHT + THIRD_WAVE
MAX_PARALLEL_SPECIALISTS = 3


def agent_wave_plan() -> dict[str, Any]:
    return {
        "first_wave": list(FIRST_WAVE),
        "second_wave": list(SECOND_WAVE),
        "third_wave": list(THIRD_WAVE),
        "core_eight_agents": list(CORE_EIGHT),
        "all_agents": list(ALL_REVIEW_DESKS),
        "historical_review_required": True,
        "historical_review_position": "AFTER_SKEPTIC_AND_PORTFOLIO_BEFORE_COMMITTEE",
        "max_parallel_specialists": MAX_PARALLEL_SPECIALISTS,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _error_result(agent_key: str, topic: str, exc: Exception) -> dict[str, Any]:
    if agent_key == HISTORICAL_AGENT_KEY:
        name = HISTORICAL_AGENT_NAME
        room = HISTORICAL_ROOM
    else:
        config = AGENT_CONFIGS[agent_key]
        name = config["name"]
        room = config["room"]
    return {
        "agent_key": agent_key,
        "agent": name,
        "room": room,
        "status": "error",
        "topic": topic,
        "headline": f"{name} unavailable",
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


def _run_historical(case_id: str, topic: str) -> dict[str, Any]:
    try:
        return run_historical_pattern_review(case_id)
    except Exception as exc:
        return _error_result(HISTORICAL_AGENT_KEY, topic, exc)


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


def second_wave_evidence(
    base_evidence: list[dict[str, Any]],
    completed_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Second-wave desks see the raw governed evidence plus every desk that has
    completed before them. This means Skeptic sees all six first-wave desks,
    and Portfolio sees those six plus Skeptic's challenge.
    """
    return list(base_evidence) + _peer_context_items(completed_results)


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
    required_core = set(CORE_EIGHT)
    complete = {
        key
        for key, value in specialists.items()
        if value.get("status") == "complete"
    }
    flags = set(evidence_summary.get("critical_flags") or [])
    checks = {
        "all_eight_agents_complete": required_core.issubset(complete),
        "skeptic_complete": "skeptic" in complete,
        "portfolio_complete": "portfolio" in complete,
        "historical_pattern_complete": HISTORICAL_AGENT_KEY in complete,
        "all_nine_review_desks_complete": set(ALL_REVIEW_DESKS).issubset(complete),
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
Nine governed review desks have completed review: the core eight specialist desks plus
a Historical Pattern & Precedent Analyst. The historical desk runs after Skeptic and
Portfolio and before this Committee.

CASE PACKET:
{json.dumps(packet, indent=2, default=str)}

Rules:
- Synthesize; do not simply average.
- Preserve dissent and name the strongest disagreement.
- Separate evidence from inference and unknowns.
- Penalize stale, conflicting, missing, or low-quality evidence.
- The Skeptic reviewed all six first-wave desks; Portfolio reviewed those desks plus the Skeptic challenge.
- Historical precedent is context, not proof. Do not treat analogy as causation or as an external backtest unless the record explicitly says so.
- A lack of historical precedent is an unknown, not evidence that the thesis is false.
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
        "evidence_summary": evidence_summary,
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
    """
    Backward-compatible entry point for the opportunity research floor.

    The core eight specialists still run in their original two waves. A ninth,
    required Historical Pattern & Precedent review now runs after Skeptic and
    Portfolio and before Committee. No desk has execution authority.
    """
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

    # Second wave is intentionally sequential: Skeptic challenges the six first-wave
    # desks, then Portfolio sees the same evidence plus the Skeptic's challenge.
    for key in SECOND_WAVE:
        result = _run_one(
            key,
            topic,
            second_wave_evidence(evidence_items, results),
        )
        results[key] = _persist_agent_result(
            case_id=case_id,
            topic=topic,
            evidence_packet_id=evidence_packet_id,
            result=result,
            wave=2,
        )

    # Third wave: historical precedent is reviewed only after the core eight have
    # completed, and always before Committee. It consumes governed IIOS memory and
    # paper-trade outcomes when available; it cannot create or authorize an order.
    historical = _run_historical(case_id, topic)
    results[HISTORICAL_AGENT_KEY] = _persist_agent_result(
        case_id=case_id,
        topic=topic,
        evidence_packet_id=evidence_packet_id,
        result=historical,
        wave=3,
    )

    # Present specialists in canonical order regardless of parallel completion order.
    ordered = {key: results[key] for key in ALL_REVIEW_DESKS if key in results}
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
        "historical_pattern_review_id": historical.get("historical_pattern_review_id"),
        "historical_pattern_signal": historical.get("historical_signal"),
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
            "legacy_event_name": True,
            "core_agent_count": len([key for key in ordered if key in CORE_EIGHT]),
            "review_desk_count": len(ordered),
            "historical_pattern_complete": historical.get("status") == "complete",
            "committee_disposition": decision["disposition"],
            "committee_confidence": decision["confidence"],
            "failed_guard_checks": decision["orchestration_guard"]["failed_checks"],
            "trade_execution_permission": False,
        },
    )
    record_event(
        case_id,
        "NINE_DESK_GOVERNED_REVIEW_COMPLETE",
        entity_id=orchestration_id,
        payload={
            "review_desk_count": len(ordered),
            "historical_pattern_signal": historical.get("historical_signal"),
            "committee_disposition": decision["disposition"],
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )
    return {
        "orchestration": orchestration,
        "historical_pattern": historical,
        "committee": decision,
    }


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
    historical = latest_object("historical_pattern_review", case_id=case_id)
    return {
        "case_id": case_id,
        "latest_orchestration": orchestration,
        "latest_historical_pattern": historical,
        "latest_committee": committee,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }