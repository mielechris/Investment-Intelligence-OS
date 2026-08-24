from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ledger import get_object, latest_object, list_objects, record_event, record_object, utc_now
from primary_evidence_contracts import contract_for_requirement


router = APIRouter()
MAX_REQUIREMENTS = 12
MAX_FACTS_PER_REQUIREMENT = 6

_SOURCE_BY_LANE = {
    "memory_pricing": ["licensed pricing data", "supplier/industry primary source"],
    "supply_inventory": ["company filing", "supplier primary source", "industry primary source"],
    "hyperscaler_demand": ["customer investor relations", "company filing", "official company source"],
    "micron_filing": ["SEC EDGAR", "company investor relations"],
    "valuation_market": ["cross-checked market data", "company filing", "governed portfolio snapshot"],
    "policy_regulation": ["Federal Register", "BIS/NIST/agency primary source"],
    "general": ["official/primary source", "independent corroborating source"],
}


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text[:72] or "fact"


def atomic_facts(requirement: str) -> list[str]:
    text = " ".join(str(requirement or "").split())
    if not text:
        return []
    parts = [
        item.strip(" .:-")
        for item in re.split(r"\s*;\s*|\s*,\s*|\s+and\s+|\s+plus\s+", text, flags=re.I)
        if item.strip(" .:-")
    ]
    useful = [item for item in parts if len(item) >= 8]
    if len(useful) <= 1:
        useful = [text]
    return useful[:MAX_FACTS_PER_REQUIREMENT]


def _lane(requirement: str) -> str:
    try:
        lane, _ = contract_for_requirement(requirement)
    except Exception:
        lane = None
    return str(lane or "general")


def _existing_lane_records(case_id: str, lane: str) -> list[dict[str, Any]]:
    return [
        row
        for row in list_objects(case_id, "primary_evidence_record")
        if str(row.get("lane") or "") == lane
        and row.get("gap_resolution_eligible") is True
    ]


def build_evidence_depth_plan(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    decision = latest_object("committee_decision", case_id=case_id)
    if not decision:
        raise HTTPException(status_code=409, detail="Committee decision required before evidence-depth planning")

    requirements = [
        str(item).strip()
        for item in decision.get("required_evidence") or []
        if str(item).strip()
    ][:MAX_REQUIREMENTS]
    if not requirements:
        requirements = [f"Revalidate the strongest supporting and contradicting evidence for {case.get('topic') or case_id}"]

    rows: list[dict[str, Any]] = []
    total_facts = 0
    evidence_present = 0
    for requirement_index, requirement in enumerate(requirements):
        lane = _lane(requirement)
        existing = _existing_lane_records(case_id, lane)
        facts: list[dict[str, Any]] = []
        for fact_index, fact in enumerate(atomic_facts(requirement)):
            total_facts += 1
            present = bool(existing)
            if present:
                evidence_present += 1
            facts.append({
                "fact_key": f"r{requirement_index + 1}_{fact_index + 1}_{_slug(fact)}",
                "fact": fact,
                "state": "EVIDENCE_PRESENT" if present else "OPEN",
                "lane": lane,
                "preferred_sources": list(_SOURCE_BY_LANE.get(lane, _SOURCE_BY_LANE["general"])),
                "existing_primary_record_count": len(existing),
                "resolution_authority": "governed_fact_contract",
            })
        rows.append({
            "requirement_index": requirement_index,
            "requirement": requirement,
            "lane": lane,
            "facts": facts,
            "fact_count": len(facts),
        })

    plan_id = f"evidence_depth_{uuid4().hex}"
    plan = {
        "evidence_depth_plan_id": plan_id,
        "case_id": case_id,
        "decision_id": decision.get("decision_id"),
        "topic": case.get("topic"),
        "requirements": rows,
        "requirement_count": len(rows),
        "atomic_fact_count": total_facts,
        "facts_with_some_lane_evidence": evidence_present,
        "facts_open": max(0, total_facts - evidence_present),
        "note": "EVIDENCE_PRESENT means relevant governed lane evidence exists; it does not by itself resolve the fact contract.",
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(plan_id, "evidence_depth_plan", case_id, plan, parent_id=decision.get("decision_id"), topic=case.get("topic"))
    record_event(case_id, "EVIDENCE_DEPTH_PLAN_RECORDED", entity_id=plan_id, payload={
        "requirement_count": len(rows),
        "atomic_fact_count": total_facts,
        "trade_execution_permission": False,
    })
    return plan


@router.get("/intelligence/evidence-depth/{case_id}")
def evidence_depth(case_id: str):
    return build_evidence_depth_plan(case_id)
