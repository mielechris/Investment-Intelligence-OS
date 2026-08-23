from __future__ import annotations

from typing import Any

from ledger import record_event, record_object
from primary_evidence_contracts import contract_for_requirement


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _lane(requirement: str) -> str | None:
    """Map requirement lineage broadly without weakening evidence qualification.

    The strict contract matcher intentionally needs multiple exact concepts before it
    activates a fact contract. Lineage has a different job: recognize that a rewritten
    Committee sentence belongs to the same research lane even when wording changes.
    """
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


def install_requirement_lineage_guard(module: Any) -> None:
    prior_run = module.run_gap_hunt

    def guarded_run(case_id: str):
        hunt = prior_run(case_id)
        current_requirements = [
            str(item).strip()
            for item in (hunt.get("committee") or {}).get("required_evidence") or []
            if str(item).strip()
        ]
        lineage = build_requirement_lineage(hunt.get("resolution_matrix") or [], current_requirements)
        updated = {**hunt, "requirement_lineage": lineage}
        hunt_id = str(updated.get("gap_hunt_id") or "")
        if hunt_id:
            qualification = updated.get("qualification") or {}
            record_object(
                hunt_id,
                "gap_hunt",
                case_id,
                updated,
                parent_id=qualification.get("qualification_assessment_id"),
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
                },
            )
        return updated

    module.run_gap_hunt = guarded_run
