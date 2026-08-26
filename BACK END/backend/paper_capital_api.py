from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ledger import latest_object
from live_invalidation_mapper import build_live_invalidation_status
from paper_capital_gate import assess_paper_capital
from factory_genericization import resolve_case_profile
from generic_public_company_capital import assess_generic_public_company_capital, build_generic_public_company_stress

router = APIRouter()


def _require_latest(object_type: str, case_id: str) -> dict[str, Any]:
    obj = latest_object(object_type, case_id=case_id)
    if not obj:
        raise HTTPException(status_code=409, detail=f"Required governed object missing: {object_type}")
    return obj


def _pending_status(case_id: str, missing: list[str]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "stage": "RESEARCH_INPUTS_PENDING",
        "research": {"stage": "INPUTS_PENDING", "qualified_buy_candidate": False, "unmet_requirements": [f"MISSING_GOVERNED_OBJECT:{item}" for item in missing]},
        "thesis": {"status": "UNKNOWN", "invalidated": False, "breached_rules": [], "watching_rules": []},
        "capital": {"decision": "NOT_EVALUATED", "failed_hard_checks": [f"MISSING_GOVERNED_OBJECT:{item}" for item in missing]},
        "watch_obligations": [],
        "entry_watch": {"armed": False, "crossed_into_ready": False, "position_sizing_ready": False, "paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False},
        "sizing": {"profile_present": False, "profile_enabled": False, "inputs_complete": False, "portfolio_snapshot_present": False, "automatic": {"paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False}},
        "permissions": {"qualified_research": False, "thesis_valid": False, "capital_approved": False, "position_sizing_ready": False, "paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False},
        "paper_mode": True,
    }


@router.get("/paper-capital/{case_id}/status")
def paper_capital_status(case_id: str) -> dict[str, Any]:
    """Read-only governed capital-control status with zero live-money authority."""
    qualification = latest_object("qualification_assessment", case_id=case_id) or {}
    hunt = latest_object("gap_hunt", case_id=case_id) or {}
    missing = []
    if not qualification:
        missing.append("qualification_assessment")
    if not hunt:
        missing.append("gap_hunt")
    if missing:
        return _pending_status(case_id, missing)

    risk = hunt.get("risk") or {}
    if not risk:
        return _pending_status(case_id, ["gap_hunt.risk"])

    thesis = build_live_invalidation_status(case_id)
    qualification_ok = qualification.get("qualified_buy_candidate") is True
    identity = resolve_case_profile(case_id)
    stress = {}

    if not qualification_ok:
        capital = {"decision": "NOT_EVALUATED", "failed_hard_checks": ["RESEARCH_NOT_QUALIFIED"], "watch_obligations": risk.get("watch_obligations") or [], "paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False}
    elif identity.get("is_micron"):
        stress = latest_object("cycle_valuation_stress", case_id=case_id) or {}
        if not stress:
            return _pending_status(case_id, ["cycle_valuation_stress"])
        capital = assess_paper_capital(qualification=qualification, risk=risk, stress=stress, thesis_status=thesis)
    else:
        stress = latest_object("generic_capital_stress", case_id=case_id) or {}
        if not stress:
            try:
                stress = build_generic_public_company_stress(case_id)
            except Exception as exc:
                capital = {"decision": "INPUTS_PENDING", "failed_hard_checks": [f"GENERIC_CAPITAL_INPUT:{type(exc).__name__}:{exc}"], "watch_obligations": risk.get("watch_obligations") or [], "paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False}
            else:
                capital = assess_generic_public_company_capital(qualification=qualification, risk=risk, stress=stress, thesis_status=thesis)
        else:
            capital = assess_generic_public_company_capital(qualification=qualification, risk=risk, stress=stress, thesis_status=thesis)

    entry_watch = latest_object("capital_entry_watch", case_id=case_id) or {}
    sizing_profile = latest_object("paper_sizing_profile", case_id=case_id) or {}
    portfolio_snapshot = latest_object("portfolio_snapshot", case_id=case_id) or {}
    portfolio_overlap = portfolio_snapshot.get("overlap") or {}
    automatic_sizing = entry_watch.get("automatic_sizing") or {}
    thesis_ok = thesis.get("status") in {"ACTIVE_CLEAR", "ACTIVE_WITH_WATCHES"} and thesis.get("thesis_invalidated") is False
    capital_decision = str(capital.get("decision") or "")
    if not qualification_ok: stage = "RESEARCH_NOT_QUALIFIED"
    elif not thesis_ok: stage = "THESIS_INVALIDATED"
    elif capital_decision == "WAIT_FOR_ENTRY": stage = "WAIT_FOR_ENTRY"
    elif capital_decision == "REJECTED": stage = "CAPITAL_REJECTED"
    elif capital_decision == "APPROVED": stage = "READY_FOR_POSITION_SIZING"
    elif capital_decision == "INPUTS_PENDING": stage = "CAPITAL_INPUTS_PENDING"
    else: stage = "CAPITAL_STATE_UNKNOWN"

    return {
        "case_id": case_id, "stage": stage,
        "research": {"stage": qualification.get("stage"), "qualified_buy_candidate": qualification_ok, "unmet_requirements": qualification.get("unmet_requirements") or []},
        "thesis": {"status": thesis.get("status"), "invalidated": thesis.get("thesis_invalidated"), "breached_rules": thesis.get("breached_rules") or [], "watching_rules": thesis.get("watching_rules") or []},
        "capital": {"decision": capital_decision, "current_price": capital.get("current_price"), "upside_reference": capital.get("upside_reference_value"), "downside_reference": capital.get("downside_reference_value"), "reward_risk": capital.get("reward_risk"), "minimum_reward_risk": capital.get("minimum_reward_risk"), "maximum_qualifying_entry": capital.get("maximum_qualifying_entry"), "failed_hard_checks": capital.get("failed_hard_checks") or []},
        "watch_obligations": capital.get("watch_obligations") or [],
        "entry_watch": {"armed": bool(entry_watch), "stage": entry_watch.get("stage"), "current_price": entry_watch.get("current_price"), "maximum_qualifying_entry": entry_watch.get("maximum_qualifying_entry"), "entry_gap": entry_watch.get("entry_gap"), "entry_gap_pct": entry_watch.get("entry_gap_pct"), "reward_risk": entry_watch.get("reward_risk"), "quote_provider": entry_watch.get("quote_provider"), "quote_timestamp": entry_watch.get("quote_timestamp"), "checked_at": entry_watch.get("created_at"), "crossed_into_ready": bool(entry_watch.get("crossed_into_ready")), "position_sizing_ready": bool(entry_watch.get("position_sizing_ready")), "paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False},
        "sizing": {"profile_present": bool(sizing_profile), "profile_enabled": bool(sizing_profile.get("enabled")), "inputs_complete": bool(sizing_profile.get("inputs_complete")), "portfolio_nav": sizing_profile.get("portfolio_nav"), "invalidation_price": sizing_profile.get("invalidation_price"), "invalidation_basis": sizing_profile.get("invalidation_basis"), "portfolio_snapshot_present": bool(portfolio_snapshot), "portfolio_snapshot_id": portfolio_snapshot.get("portfolio_snapshot_id"), "combined_overlap_weight_pct": portfolio_overlap.get("combined_overlap_weight_pct"), "concentration_level": portfolio_overlap.get("concentration_level"), "automatic": {"decision": automatic_sizing.get("decision"), "reason": automatic_sizing.get("reason"), "proposed_shares": automatic_sizing.get("proposed_shares"), "proposed_notional": automatic_sizing.get("proposed_notional"), "proposed_position_pct": automatic_sizing.get("proposed_position_pct"), "proposed_portfolio_risk_pct": automatic_sizing.get("proposed_portfolio_risk_pct"), "binding_constraint": automatic_sizing.get("binding_constraint"), "paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False}},
        "permissions": {"qualified_research": qualification_ok, "thesis_valid": thesis_ok, "capital_approved": capital_decision == "APPROVED", "position_sizing_ready": capital_decision == "APPROVED", "paper_authorization_ready": False, "paper_order_permission": False, "trade_execution_permission": False, "live_execution": False},
        "paper_mode": True,
    }
