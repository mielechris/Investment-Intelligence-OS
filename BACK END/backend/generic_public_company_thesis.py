from __future__ import annotations

from typing import Any
from uuid import uuid4

from ledger import latest_object, record_event, record_object, utc_now

EPS_REVISION_BREAK_PCT = -10.0


def build_generic_thesis_status(case_id: str) -> dict[str, Any]:
    qualification = latest_object(
        "qualification_assessment",
        case_id=case_id,
    ) or {}

    risk = latest_object(
        "risk_authorization",
        case_id=case_id,
    ) or {}

    revision = latest_object(
        "consensus_revision_history",
        case_id=case_id,
    ) or {}

    reconciliation = (
        risk.get("required_evidence_reconciliation")
        or {}
    )

    breached: list[str] = []
    watching: list[str] = []

    if qualification.get("qualified_buy_candidate") is not True:
        breached.append("RESEARCH_QUALIFICATION_LOST")

    if (
        risk.get("decision") != "WATCH_ONLY"
        or bool(risk.get("triggered_rules"))
    ):
        breached.append("RISK_CLEARANCE_LOST")

    if int(reconciliation.get("blocking_count") or 0) > 0:
        breached.append("GOVERNED_BLOCKER_REOPENED")

    if int(
        reconciliation.get("ungoverned_new_scope_count") or 0
    ) > 0:
        breached.append("UNGOVERNED_SCOPE_REOPENED")

    if revision.get("verified_revision_history") is True:
        eps_change = revision.get("eps_change_pct")

        if (
            eps_change is not None
            and float(eps_change) <= EPS_REVISION_BREAK_PCT
        ):
            breached.append("EPS_REVISION_BREAK")
    else:
        watching.append("CONSENSUS_REVISION_HISTORY")

    for row in risk.get("watch_obligations") or []:
        key = (
            str(row.get("lane") or ""),
            str(row.get("fact_key") or ""),
        )

        if key == (
            "generic_operating_context",
            "operating_kpis",
        ):
            watching.append("OPERATING_KPI_CONFIRMATION")

    watching = sorted(set(watching))
    breached = sorted(set(breached))

    if breached:
        status = "INVALIDATED"
    elif watching:
        status = "ACTIVE_WITH_WATCHES"
    else:
        status = "ACTIVE_CLEAR"

    status_id = f"generic_thesis_status_{uuid4().hex}"

    result = {
        "generic_thesis_status_id": status_id,
        "case_id": case_id,
        "status": status,
        "thesis_invalidated": bool(breached),
        "breached_rules": breached,
        "watching_rules": watching,
        "governance": {
            "deterministic_mapper": True,
            "llm_can_trigger_rule": False,
            "automatic_sell_order": False,
            "capital_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
        "created_at": utc_now(),
        "paper_mode": True,
        "live_execution": False,
    }

    record_object(
        status_id,
        "generic_thesis_status",
        case_id,
        result,
    )

    record_event(
        case_id,
        "GENERIC_PUBLIC_COMPANY_THESIS_STATUS_RECORDED",
        entity_id=status_id,
        payload={
            "status": status,
            "breached_rules": breached,
            "watching_rules": watching,
            "trade_execution_permission": False,
        },
    )

    return result
