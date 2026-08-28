from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from closed_loop_case_lineage import build_closed_loop_overview
from factory_genericization import resolve_case_profile
from ledger import latest_object
from options_shadow_observation import build_options_shadow_status
from paper_portfolio_core import build_portfolio_state


router = APIRouter()
POLICY_VERSION = "batch10d-operations-visibility-v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _capital_reason(case_id: str, lineage: dict[str, Any]) -> dict[str, Any]:
    qualification = latest_object("qualification_assessment", case_id=case_id) or {}
    committee = latest_object("committee_decision", case_id=case_id) or {}
    risk = latest_object("risk_authorization", case_id=case_id) or {}
    gap_hunt = latest_object("gap_hunt", case_id=case_id) or {}

    risk_decision = risk.get("decision") or (gap_hunt.get("risk") or {}).get("decision")
    committee_disposition = lineage.get("committee_disposition") or committee.get("disposition")

    unmet = [
        str(item).strip()
        for item in qualification.get("unmet_requirements") or []
        if str(item).strip()
    ]
    required = [
        str(item).strip()
        for item in committee.get("required_evidence") or []
        if str(item).strip()
    ]
    triggered = [
        str(item).strip()
        for item in (
            risk.get("triggered_rules")
            or (gap_hunt.get("risk") or {}).get("triggered_rules")
            or []
        )
        if str(item).strip()
    ]

    if lineage.get("paper_execution_complete") is True:
        state = "CAPITAL_DEPLOYED"
        reason = "Governed paper execution completed."
    elif qualification.get("qualified_buy_candidate") is True:
        state = "QUALIFIED_AWAITING_CAPITAL_PATH"
        reason = "Research qualification passed; downstream capital gates remain authoritative."
    elif unmet:
        state = "RESEARCH_NOT_QUALIFIED"
        reason = f"{len(unmet)} qualification requirements remain unmet."
    elif str(risk_decision or "").upper() in {"VETOED", "WATCH_ONLY"}:
        state = "RISK_BLOCKED"
        reason = f"Risk decision is {risk_decision}."
    elif str(committee_disposition or "").upper() in {"NO_TRADE", "WATCH"}:
        state = "COMMITTEE_NOT_CAPITAL_READY"
        reason = f"Committee disposition is {committee_disposition}."
    else:
        state = "NO_CAPITAL_DECISION_YET"
        reason = "No governed capital-ready decision is present."

    return {
        "state": state,
        "reason": reason,
        "committee_disposition": committee_disposition,
        "risk_decision": risk_decision,
        "unmet_requirements": unmet,
        "required_evidence": required,
        "risk_triggered_rules": triggered,
    }


def _case_row(source: dict[str, Any]) -> dict[str, Any]:
    case_id = str(source.get("case_id") or "")
    identity: dict[str, Any] = {}
    try:
        identity = resolve_case_profile(case_id)
    except Exception:
        identity = {}

    deep_watch = latest_object("deep_watch_obligation_set", case_id=case_id) or {}
    deep_reunderwrite = latest_object("deep_watch_reunderwrite", case_id=case_id) or {}

    options: dict[str, Any]
    try:
        options = build_options_shadow_status(case_id)
    except Exception as exc:
        options = {
            "mode": "UNKNOWN_FAIL_CLOSED",
            "observation_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "option_order_permission": False,
            "live_execution": False,
        }

    reason = _capital_reason(case_id, source)
    material_changes = int(deep_watch.get("material_change_count") or 0)
    obligation_count = int(deep_watch.get("obligation_count") or 0)

    if source.get("dead_end") is True:
        attention = "DEAD_END"
    elif material_changes > 0:
        attention = "MATERIAL_CHANGE"
    elif obligation_count > 0:
        attention = "WATCHING"
    else:
        attention = "NORMAL"

    reunderwrite_committee = deep_reunderwrite.get("committee") or {}

    return {
        "case_id": case_id,
        "ticker": identity.get("ticker"),
        "company": identity.get("company"),
        "topic": source.get("topic"),
        "current_stage": source.get("current_stage"),
        "continuity_state": source.get("continuity_state"),
        "valid_no_capital_outcome": bool(source.get("valid_no_capital_outcome")),
        "dead_end": bool(source.get("dead_end")),
        "missing_continuation": source.get("missing_continuation") or [],
        "committee_disposition": reason.get("committee_disposition"),
        "risk_decision": reason.get("risk_decision"),
        "qualified_buy_candidate": bool(source.get("qualified_buy_candidate")),
        "capital_stage": source.get("capital_stage") or reason.get("state"),
        "paper_execution_complete": bool(source.get("paper_execution_complete")),
        "monitoring_active": bool(source.get("monitoring_active")),
        "deep_watch": {
            "active": bool(deep_watch),
            "obligation_count": obligation_count,
            "material_change_count": material_changes,
            "policy_version": deep_watch.get("policy_version"),
            "latest_reunderwrite_disposition": reunderwrite_committee.get("disposition"),
            "latest_reunderwrite_confidence": reunderwrite_committee.get("confidence"),
        },
        "options_shadow": {
            "mode": options.get("mode"),
            "observation_count": int(options.get("observation_count") or 0),
            "option_order_permission": False,
            "live_execution": False,
        },
        "capital_reason": reason,
        "attention": attention,
        "paper_mode": True,
        "read_only_surface": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "option_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def build_operations_visibility(limit: int = 25) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    portfolio = build_portfolio_state()
    lineage = build_closed_loop_overview(limit)
    cases = [_case_row(row) for row in lineage.get("cases") or []]

    nav = _safe_float(portfolio.get("nav"))
    cash = _safe_float(portfolio.get("cash"))
    deployed = max(0.0, nav - cash)

    summary = {
        "case_count": len(cases),
        "deep_watch_cases": sum(1 for row in cases if (row.get("deep_watch") or {}).get("active")),
        "open_obligations": sum(int((row.get("deep_watch") or {}).get("obligation_count") or 0) for row in cases),
        "material_change_cases": sum(1 for row in cases if int((row.get("deep_watch") or {}).get("material_change_count") or 0) > 0),
        "options_shadow_cases": sum(1 for row in cases if (row.get("options_shadow") or {}).get("mode") == "SHADOW_OBSERVATION_ONLY"),
        "options_observations": sum(int((row.get("options_shadow") or {}).get("observation_count") or 0) for row in cases),
        "dead_end_count": sum(1 for row in cases if row.get("dead_end") is True),
        "valid_no_capital_paths": sum(1 for row in cases if row.get("valid_no_capital_outcome") is True),
        "paper_positions_opened": sum(1 for row in cases if row.get("paper_execution_complete") is True),
    }

    return {
        "policy_version": POLICY_VERSION,
        "portfolio": {
            "nav": portfolio.get("nav"),
            "cash": portfolio.get("cash"),
            "position_count": portfolio.get("position_count"),
            "transaction_count": portfolio.get("transaction_count"),
            "capital_deployed": round(deployed, 2),
            "cash_weight_pct": round((cash / nav) * 100.0, 4) if nav > 0 else None,
            "accounting_scope": portfolio.get("accounting_scope"),
        },
        "summary": summary,
        "cases": cases,
        "paper_mode": True,
        "read_only_surface": True,
        "equity_paper_expression_authoritative": True,
        "options_shadow_only": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "option_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/operations-visibility/overview")
def operations_visibility_overview(limit: int = 25):
    return build_operations_visibility(limit)
