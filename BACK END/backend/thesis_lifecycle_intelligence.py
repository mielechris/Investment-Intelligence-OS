from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ledger import get_object, latest_object, record_event, record_object, utc_now


router = APIRouter()
REUNDERWRITE_ACTIONS = {"REUNDERWRITE_REQUIRED", "THESIS_BROKEN"}


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def assess_thesis_lifecycle(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    decision = latest_object("committee_decision", case_id=case_id)
    if not decision:
        raise HTTPException(status_code=409, detail="Committee decision required before thesis lifecycle assessment")

    thesis = latest_object("thesis_monitor", case_id=case_id) or {}
    position = latest_object("position_monitor", case_id=case_id) or {}
    profile = latest_object("monitor_profile", case_id=case_id) or {}

    thesis_status = str(thesis.get("thesis_status") or "NOT_MONITORED")
    flags = [str(item) for item in thesis.get("flags") or []]
    catalyst_status = str(thesis.get("catalyst_status") or "UNKNOWN")

    if thesis_status == "THESIS_BROKEN":
        lifecycle_state = "THESIS_BROKEN"
        action = "REUNDERWRITE_REQUIRED"
        urgency = "CRITICAL"
    elif thesis_status == "REUNDERWRITE_REQUIRED" or flags:
        lifecycle_state = "MATERIAL_CHANGE"
        action = "REUNDERWRITE_REQUIRED"
        urgency = "HIGH"
    elif thesis_status == "INTACT":
        lifecycle_state = "MONITORING"
        action = "CONTINUE_MONITORING"
        urgency = "NORMAL"
    else:
        lifecycle_state = "MONITOR_SETUP_REQUIRED"
        action = "CREATE_THESIS_MONITOR"
        urgency = "NORMAL"

    targeted_desks: list[str] = []
    if action == "REUNDERWRITE_REQUIRED":
        targeted_desks.extend(["skeptic", "portfolio"])
        if any(flag in flags for flag in ("CATALYST_MISSED", "FALSIFIER_TRIGGERED")):
            targeted_desks.append("fundamentals")
        if "DRAWDOWN_TRIGGERED" in flags:
            targeted_desks.append("market_structure")
        if "UPDATE_EVIDENCE_CONFLICT" in flags:
            targeted_desks.append("fundamentals")
    targeted_desks = list(dict.fromkeys(targeted_desks))

    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "decision_id": decision.get("decision_id"),
        "lifecycle_state": lifecycle_state,
        "action": action,
        "urgency": urgency,
        "thesis_status": thesis_status,
        "thesis_flags": flags,
        "catalyst_status": catalyst_status,
        "observed_return_pct": position.get("return_pct"),
        "monitor_profile_enabled": bool(profile.get("enabled")),
        "targeted_desks": targeted_desks,
        "automatic_agent_rerun": False,
        "automatic_order_action": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def record_reunderwrite_request(case_id: str) -> dict[str, Any]:
    assessment = assess_thesis_lifecycle(case_id)
    if assessment["action"] != "REUNDERWRITE_REQUIRED":
        return {
            "status": "not_required",
            "assessment": assessment,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    request_id = f"lifecycle_reunderwrite_{uuid4().hex}"
    request = {
        "lifecycle_reunderwrite_request_id": request_id,
        "case_id": case_id,
        "decision_id": assessment.get("decision_id"),
        "reason_state": assessment.get("lifecycle_state"),
        "thesis_status": assessment.get("thesis_status"),
        "flags": assessment.get("thesis_flags"),
        "targeted_desks": assessment.get("targeted_desks"),
        "status": "REQUESTED",
        "agents_started": 0,
        "human_or_scheduler_drain_required": True,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(request_id, "lifecycle_reunderwrite_request", case_id, request, parent_id=assessment.get("decision_id"), topic=assessment.get("topic"))
    record_event(case_id, "THESIS_LIFECYCLE_REUNDERWRITE_REQUESTED", entity_id=request_id, payload={
        "targeted_desks": request["targeted_desks"],
        "agents_started": 0,
        "trade_execution_permission": False,
    })
    return {"status": "requested", "request": request, "assessment": assessment}


@router.get("/intelligence/thesis-lifecycle/{case_id}")
def thesis_lifecycle(case_id: str):
    return assess_thesis_lifecycle(case_id)


@router.post("/intelligence/thesis-lifecycle/{case_id}/request-reunderwrite")
def thesis_lifecycle_reunderwrite(case_id: str):
    return record_reunderwrite_request(case_id)
