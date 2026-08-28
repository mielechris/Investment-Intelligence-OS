from __future__ import annotations

from typing import Any
from uuid import uuid4

from ledger import get_object, record_event, record_object, utc_now
from primary_evidence_contracts import contract_for_requirement


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _lane(requirement: str) -> str | None:
    lane, _ = contract_for_requirement(requirement)
    if lane:
        return lane
    value = _norm(requirement)
    heuristics = [
        ("policy", ("tariff", "export control", "semiconductor incentive", "permitting", "policy", "section 232")),
        ("memory_pricing", ("hbm price", "dram price", "nand price", "memory pricing", "spot price", "contract price")),
        ("supply_inventory", ("inventory days", "wafer starts", "bit shipments", "utilization", "packaging capacity", "yields")),
        ("hyperscaler_demand", ("hyperscaler", "ai-capex", "ai capex", "server shipments", "backlog", "cancellations", "strategic-agreement")),
        ("micron_financials", ("micron", "revenue mix", "hbm volumes", "free cash flow", "debt", "capex", "asp sensitivity")),
        ("valuation_market", ("current mu price", "diluted shares", "consensus revenue", "eps", "valuation", "short interest", "options positioning")),
    ]
    for key, terms in heuristics:
        if any(term in value for term in terms):
            return key
    return None


def build_requirement_lineage(prior_matrix: list[dict[str, Any]], current_requirements: list[str]) -> dict[str, Any]:
    current_rows = [str(item).strip() for item in current_requirements if str(item).strip()]
    current_by_lane: dict[str, list[str]] = {}
    for requirement in current_rows:
        lane = _lane(requirement)
        if lane:
            current_by_lane.setdefault(lane, []).append(requirement)

    rows: list[dict[str, Any]] = []
    prior_resolved = 0
    accepted_resolved = 0
    reopened = 0
    for row in prior_matrix or []:
        requirement = str(row.get("requirement") or "").strip()
        resolved = bool(row.get("resolved"))
        if resolved:
            prior_resolved += 1
        lane = _lane(requirement)
        replacements = current_by_lane.get(lane or "", []) if lane else []
        changed_replacement = next((item for item in replacements if _norm(item) != _norm(requirement)), None)

        if resolved and changed_replacement:
            status = "SUPERSEDED_REOPENED"
            effective_resolved = False
            reopened += 1
        elif resolved:
            status = "PRIOR_RESOLVED_ACCEPTED"
            effective_resolved = True
            accepted_resolved += 1
        else:
            status = "PRIOR_OPEN"
            effective_resolved = False

        rows.append({
            "prior_requirement": requirement,
            "lane": lane,
            "prior_resolved": resolved,
            "effective_resolved": effective_resolved,
            "status": status,
            "replacement_requirement": changed_replacement,
        })

    return {
        "prior_requirement_count": len(prior_matrix or []),
        "prior_resolved_count": prior_resolved,
        "accepted_resolved_count": accepted_resolved,
        "reopened_count": reopened,
        "current_open_count": len(current_rows),
        "current_requirements": current_rows,
        "rows": rows,
    }


def _provider_fail_closed_result(agent_key: str, topic: str, exc: Exception) -> dict[str, Any]:
    return {
        "agent_key": agent_key,
        "agent": agent_key,
        "room": "Gap Hunter",
        "status": "error",
        "topic": topic,
        "headline": f"{agent_key} unavailable during evidence-gap hunt",
        "view": "Provider failure prevented a fresh desk opinion. The gap remains open and cannot qualify capital.",
        "confidence": 0.0,
        "disposition": "NO_TRADE",
        "missing_evidence": ["successful fresh specialist analysis"],
        "falsifier": "No governed specialist output was produced.",
        "floor_comment": "Desk failed closed; no authority gained.",
        "error": f"{type(exc).__name__}: {exc}",
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def install_requirement_lineage_guard(module: Any) -> None:
    prior_run = module.run_gap_hunt

    def guarded_run(case_id: str):
        # Gap Hunter historically called main.run_specialist/build_committee directly.
        # During evidence acquisition we make that legacy stage provider-failure tolerant,
        # then supersede its authority with the canonical nine-desk orchestration below.
        import main
        from eight_agent_orchestrator import run_eight_agent_orchestration

        original_specialist = main.run_specialist
        original_committee = main.build_committee

        def safe_specialist(agent_key: str, topic: str, evidence=None):
            try:
                return original_specialist(agent_key, topic, evidence)
            except Exception as exc:
                return _provider_fail_closed_result(agent_key, topic, exc)

        def placeholder_committee(review_case: dict[str, Any]):
            prior = module._latest_decision(case_id)
            return {
                **prior,
                "decision_id": f"decision_gap_placeholder_{uuid4().hex}",
                "case_id": case_id,
                "evidence_packet_id": review_case.get("evidence_packet_id"),
                "evidence_summary": review_case.get("evidence_summary") or {},
                "status": "complete",
                "paper_mode": True,
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
                "created_at": utc_now(),
            }

        main.run_specialist = safe_specialist
        main.build_committee = placeholder_committee
        try:
            hunt = prior_run(case_id)
        finally:
            main.run_specialist = original_specialist
            main.build_committee = original_committee

        qualification = hunt.get("qualification") or {}
        packet_id = str(qualification.get("evidence_packet_id") or "")
        packet = get_object(packet_id) if packet_id else None
        case = get_object(case_id) or {}

        if not packet:
            raise RuntimeError("Gap Hunter refreshed evidence packet unavailable for nine-desk reunderwrite")

        refreshed_case = {
            **case,
            "evidence_packet_id": packet_id,
            "evidence": packet.get("items") or [],
            "evidence_summary": packet.get("summary") or {},
            "updated_at": utc_now(),
            "paper_mode": True,
        }
        record_object(case_id, "case", case_id, refreshed_case, topic=refreshed_case.get("topic"))

        nine = run_eight_agent_orchestration(case_id)
        committee = nine.get("committee") or {}
        risk = main.evaluate_decision(committee)
        execution = main.submit_paper_order({"risk_authorization_id": risk["risk_authorization_id"]})
        assessment = module._qualification_assessment(
            committee,
            risk,
            hunt.get("resolution_matrix") or [],
        )

        assessment_id = f"qualification_{uuid4().hex}"
        assessment_payload = {
            **assessment,
            "qualification_assessment_id": assessment_id,
            "case_id": case_id,
            "decision_id": committee.get("decision_id"),
            "evidence_packet_id": packet_id,
            "nine_desk_reunderwrite": True,
        }
        record_object(
            assessment_id,
            "qualification_assessment",
            case_id,
            assessment_payload,
            parent_id=committee.get("decision_id"),
            topic=hunt.get("topic"),
        )

        current_requirements = [
            str(item).strip()
            for item in committee.get("required_evidence") or []
            if str(item).strip()
        ]
        lineage = build_requirement_lineage(hunt.get("resolution_matrix") or [], current_requirements)
        updated = {
            **hunt,
            "committee": committee,
            "risk": risk,
            "execution": execution,
            "qualification": assessment_payload,
            "nine_desk_orchestration": nine.get("orchestration") or {},
            "historical_pattern": nine.get("historical_pattern") or {},
            "requirement_lineage": lineage,
            "legacy_committee_authoritative": False,
            "nine_desk_committee_authoritative": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

        hunt_id = str(updated.get("gap_hunt_id") or "")
        if hunt_id:
            record_object(
                hunt_id,
                "gap_hunt",
                case_id,
                updated,
                parent_id=assessment_id,
                topic=updated.get("topic"),
            )
            record_event(
                case_id,
                "REQUIREMENT_LINEAGE_RECONCILED",
                entity_id=hunt_id,
                payload={
                    "prior_resolved_count": lineage["prior_resolved_count"],
                    "accepted_resolved_count": lineage["accepted_resolved_count"],
                    "reopened_count": lineage["reopened_count"],
                    "current_open_count": lineage["current_open_count"],
                    "nine_desk_committee_authoritative": True,
                    "trade_execution_permission": False,
                },
            )
            record_event(
                case_id,
                "GAP_HUNTER_NINE_DESK_REUNDERWRITE_COMPLETE",
                entity_id=hunt_id,
                payload={
                    "historical_pattern_signal": (nine.get("historical_pattern") or {}).get("historical_signal"),
                    "committee_disposition": committee.get("disposition"),
                    "qualification_stage": assessment_payload.get("stage"),
                    "qualified_buy_candidate": assessment_payload.get("qualified_buy_candidate"),
                    "trade_execution_permission": False,
                    "live_execution": False,
                },
            )
        return updated

    module.run_gap_hunt = guarded_run