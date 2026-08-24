from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ledger import get_object, latest_object


router = APIRouter()
MAX_CASES = 20


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_case_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        case_id = str(value or "").strip()
        if case_id.startswith("case_") and case_id not in seen:
            output.append(case_id)
            seen.add(case_id)
        if len(output) >= MAX_CASES:
            break
    return output


def score_case_for_portfolio_research(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Unknown case_id: {case_id}")

    committee = latest_object("committee_decision", case_id=case_id) or {}
    qualification = latest_object("qualification_assessment", case_id=case_id) or {}
    snapshot = latest_object("portfolio_snapshot", case_id=case_id) or {}

    disposition = str(committee.get("disposition") or "NO_TRADE")
    confidence = max(0.0, min(1.0, _safe_float(committee.get("confidence"))))
    opportunity_score = max(0.0, min(100.0, _safe_float(case.get("opportunity_score"))))
    qualified = qualification.get("qualified_buy_candidate") is True
    overlap = _safe_float((snapshot.get("overlap") or {}).get("combined_overlap_weight_pct"))

    score = confidence * 35.0
    score += opportunity_score * 0.25
    score += 25.0 if disposition == "WATCH" else 0.0
    score += 15.0 if qualified else 0.0
    score -= min(30.0, overlap * 0.30)
    if not snapshot:
        score -= 5.0
    if disposition == "NO_TRADE":
        score = min(score, 30.0)

    reasons: list[str] = []
    if disposition == "WATCH":
        reasons.append("COMMITTEE_WATCH")
    else:
        reasons.append("COMMITTEE_NO_TRADE")
    if qualified:
        reasons.append("QUALIFIED_RESEARCH_CANDIDATE")
    if overlap >= 50:
        reasons.append("HIGH_PORTFOLIO_OVERLAP")
    elif overlap >= 25:
        reasons.append("MODERATE_PORTFOLIO_OVERLAP")
    elif snapshot:
        reasons.append("LOW_PORTFOLIO_OVERLAP")
    else:
        reasons.append("PORTFOLIO_SNAPSHOT_MISSING")

    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "source_candidate_id": case.get("source_candidate_id"),
        "committee_disposition": disposition,
        "committee_confidence": confidence,
        "opportunity_score": opportunity_score,
        "qualified_buy_candidate": qualified,
        "portfolio_overlap_pct": round(overlap, 4) if snapshot else None,
        "research_rank_score": round(max(0.0, min(100.0, score)), 4),
        "reason_codes": reasons,
        "ranking_scope": "RESEARCH_PRIORITY_ONLY",
        "capital_allocation_allowed": False,
        "position_sizing_allowed": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def rank_portfolio_research(case_ids: Any) -> dict[str, Any]:
    normalized = _normalize_case_ids(case_ids)
    if not normalized:
        raise HTTPException(status_code=422, detail="Provide at least one valid case_id")
    rows = [score_case_for_portfolio_research(case_id) for case_id in normalized]
    rows.sort(key=lambda row: float(row.get("research_rank_score") or 0.0), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["research_rank"] = index
    return {
        "case_count": len(rows),
        "ranking": rows,
        "ranking_scope": "RESEARCH_PRIORITY_ONLY",
        "capital_allocation_allowed": False,
        "position_sizing_allowed": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/intelligence/portfolio-rank/plan")
def portfolio_rank_plan():
    return {
        "max_cases": MAX_CASES,
        "inputs": ["committee disposition/confidence", "opportunity score", "qualification", "governed portfolio overlap"],
        "capital_allocation_allowed": False,
        "position_sizing_allowed": False,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/intelligence/portfolio-rank")
def portfolio_rank(request: dict[str, Any] = Body(...)):
    return rank_portfolio_research(request.get("case_ids"))
