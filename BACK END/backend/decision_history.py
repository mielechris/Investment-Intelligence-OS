from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ledger import get_object, latest_object, list_objects


router = APIRouter()
AGENT_ORDER = [
    "policy",
    "macro",
    "fundamentals",
    "market_structure",
    "commodities",
    "geo_weather",
    "skeptic",
    "portfolio",
]


def _created(item: dict[str, Any]) -> str:
    return str(item.get("created_at") or "")


def _find_by_decision(items: list[dict[str, Any]], decision_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("decision_id") == decision_id), None)


def _compact_agent(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_key": agent.get("agent_key"),
        "agent": agent.get("agent"),
        "room": agent.get("room"),
        "disposition": agent.get("disposition"),
        "confidence": agent.get("confidence"),
        "headline": agent.get("headline"),
        "falsifier": agent.get("falsifier"),
        "missing_evidence": agent.get("missing_evidence") or [],
    }


def _agent_changes(
    current: dict[str, Any], previous: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if not previous:
        return []
    changes: list[dict[str, Any]] = []
    current_agents = current.get("agents") or {}
    previous_agents = previous.get("agents") or {}
    for key in AGENT_ORDER:
        now = current_agents.get(key) or {}
        before = previous_agents.get(key) or {}
        if not now or not before:
            continue
        now_conf = float(now.get("confidence") or 0.0)
        before_conf = float(before.get("confidence") or 0.0)
        disposition_changed = now.get("disposition") != before.get("disposition")
        confidence_delta = round(now_conf - before_conf, 4)
        if disposition_changed or abs(confidence_delta) >= 0.05:
            changes.append(
                {
                    "agent_key": key,
                    "agent": now.get("agent") or key,
                    "from_disposition": before.get("disposition"),
                    "to_disposition": now.get("disposition"),
                    "from_confidence": before_conf,
                    "to_confidence": now_conf,
                    "confidence_delta": confidence_delta,
                    "headline": now.get("headline"),
                }
            )
    return changes


def _qualification_requirements(assessment: dict[str, Any] | None) -> list[str]:
    if not assessment:
        return []
    mapping = {
        "committee_watch": "Committee must remain WATCH",
        "committee_confidence": "Committee confidence must reach 80%",
        "evidence_quality": "Evidence quality must reach 65%",
        "evidence_count": "At least 12 evidence items are required",
        "no_critical_flags": "Evidence packet must have no critical flags",
        "required_evidence_resolved": "Committee required-evidence list must be resolved",
        "risk_clear_for_watch": "Deterministic Risk must clear all research blockers",
        "watch_desk_quorum": "At least 6 of 8 desks must be WATCH",
        "fundamentals_watch": "Fundamentals desk must be WATCH",
        "skeptic_watch": "Skeptic / Red Team must be WATCH",
    }
    return [mapping.get(key, key.replace("_", " ")) for key in assessment.get("unmet_requirements") or []]


def build_case_history(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")

    decisions = sorted(list_objects(case_id, "committee_decision"), key=_created)
    risks = list_objects(case_id, "risk_authorization")
    executions = list_objects(case_id, "execution")
    reunderwrites = list_objects(case_id, "full_reunderwrite")
    gap_hunts = list_objects(case_id, "gap_hunt")
    reunderwrite_decision_ids = {
        str((item.get("committee") or {}).get("decision_id"))
        for item in reunderwrites
        if (item.get("committee") or {}).get("decision_id")
    }
    gap_hunt_decision_ids = {
        str((item.get("committee") or {}).get("decision_id"))
        for item in gap_hunts
        if (item.get("committee") or {}).get("decision_id")
    }

    rounds: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for index, decision in enumerate(decisions, start=1):
        decision_id = str(decision.get("decision_id") or "")
        risk = _find_by_decision(risks, decision_id) or {}
        execution = _find_by_decision(executions, decision_id) or {}
        summary = decision.get("evidence_summary") or {}
        agents = decision.get("agents") or {}
        if decision_id in gap_hunt_decision_ids:
            round_type = "GAP_HUNT"
        elif decision_id in reunderwrite_decision_ids:
            round_type = "REUNDERWRITE"
        else:
            round_type = "INITIAL" if index == 1 else "REVIEW"
        rounds.append(
            {
                "round_number": index,
                "round_type": round_type,
                "created_at": decision.get("created_at"),
                "decision_id": decision_id,
                "evidence_packet_id": decision.get("evidence_packet_id"),
                "evidence_count": summary.get("evidence_count", 0),
                "evidence_quality": summary.get("average_quality_score", 0.0),
                "critical_flags": summary.get("critical_flags") or [],
                "committee": {
                    "headline": decision.get("headline"),
                    "summary": decision.get("summary"),
                    "disposition": decision.get("disposition"),
                    "confidence": decision.get("confidence"),
                    "agreement": decision.get("agreement"),
                    "dissent": decision.get("dissent"),
                    "bull_case": decision.get("bull_case"),
                    "bear_case": decision.get("bear_case"),
                    "required_evidence": decision.get("required_evidence") or [],
                },
                "risk": {
                    "decision": risk.get("decision"),
                    "triggered_rules": risk.get("triggered_rules") or [],
                    "allowed_notional": risk.get("allowed_notional", 0.0),
                },
                "execution": {
                    "execution": execution.get("execution"),
                    "reason": execution.get("reason"),
                },
                "agents": [_compact_agent(agents[key]) for key in AGENT_ORDER if key in agents],
                "agent_changes": _agent_changes(decision, previous),
            }
        )
        previous = decision

    latest = rounds[-1] if rounds else None
    assessment = latest_object("qualification_assessment", case_id=case_id)
    qualified = bool((assessment or {}).get("qualified_buy_candidate"))
    current_stage = "QUALIFIED_BUY_CANDIDATE" if qualified else (((latest or {}).get("committee") or {}).get("disposition") or "NO_TRADE")
    evidence_quality = float((latest or {}).get("evidence_quality") or 0.0)
    committee_confidence = float((((latest or {}).get("committee") or {}).get("confidence")) or 0.0)
    risk_rules = ((latest or {}).get("risk") or {}).get("triggered_rules") or []
    next_requirements = _qualification_requirements(assessment)
    if not assessment:
        if committee_confidence < 0.65:
            next_requirements.append("Committee confidence must reach at least 65%")
        if evidence_quality < 0.55:
            next_requirements.append("Evidence quality must reach at least 55%")
        if "OPEN_EVIDENCE_REQUIREMENTS" in risk_rules:
            next_requirements.append("Committee required-evidence list must be resolved")
        if not next_requirements and current_stage == "WATCH":
            next_requirements.append("Run Evidence Gap Hunter to evaluate the governed QUALIFIED BUY CANDIDATE gate")
    elif qualified:
        next_requirements = ["Qualified research candidate reached; PAPER BUY remains disabled until a separate paper-risk tier is governed and approved"]

    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "rounds": rounds,
        "round_count": len(rounds),
        "latest_qualification": assessment,
        "signal_ladder": {
            "current_stage": current_stage,
            "stages": ["NO_TRADE", "WATCH", "QUALIFIED_BUY_CANDIDATE", "PAPER_BUY"],
            "qualified_buy_candidate_enabled": qualified,
            "paper_buy_enabled": False,
            "next_requirements": next_requirements,
        },
        "paper_mode": True,
    }


@router.get("/history/{case_id}")
def case_history(case_id: str):
    return build_case_history(case_id)
