from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

import evidence_engine
from ledger import get_object, latest_object, list_objects, record_event, record_object
from primary_evidence_contracts import contract_for_requirement


router = APIRouter()
PAPER_MODE = True

# A portfolio snapshot is first-party governed state. It should be refreshed frequently,
# but it should not decay like a one-hour quote while the user is reviewing a case.
evidence_engine.FRESHNESS_WINDOWS_HOURS["portfolio_snapshot"] = 24 * 7
evidence_engine.PERIODIC_EVIDENCE_TYPES.add("portfolio_snapshot")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _candidate_ticker(case_id: str) -> str:
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


def _valuation_requirement(case_id: str) -> str | None:
    decision = latest_object("committee_decision", case_id=case_id) or {}
    for requirement in decision.get("required_evidence") or []:
        text = str(requirement or "").strip()
        lane, _ = contract_for_requirement(text)
        if lane == "valuation_market":
            return text
    return None


def _factor_set(value: Any) -> set[str]:
    if isinstance(value, list):
        values = value
    else:
        values = str(value or "").replace("|", ",").split(",")
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _clean_position(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        return None
    try:
        weight = float(row.get("weight_pct"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"Position {ticker} needs a numeric weight_pct")
    if weight < 0 or weight > 100:
        raise HTTPException(status_code=422, detail=f"Position {ticker} weight_pct must be between 0 and 100")
    sector = str(row.get("sector") or "").strip()
    factors = sorted(_factor_set(row.get("factors")))
    return {
        "ticker": ticker,
        "weight_pct": round(weight, 4),
        "sector": sector,
        "factors": factors,
    }


def _compute_overlap(
    candidate_ticker: str,
    candidate_sector: str,
    candidate_factors: set[str],
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_sector_norm = candidate_sector.strip().lower()
    exact_weight = 0.0
    sector_weight = 0.0
    factor_weight = 0.0
    combined_weight = 0.0
    overlapping_positions: list[dict[str, Any]] = []

    for row in positions:
        weight = float(row.get("weight_pct") or 0)
        same_ticker = bool(candidate_ticker and str(row.get("ticker") or "").upper() == candidate_ticker)
        same_sector = bool(candidate_sector_norm and str(row.get("sector") or "").strip().lower() == candidate_sector_norm)
        row_factors = _factor_set(row.get("factors"))
        shared_factors = sorted(candidate_factors & row_factors)
        factor_overlap = bool(shared_factors)

        if same_ticker:
            exact_weight += weight
        if same_sector:
            sector_weight += weight
        if factor_overlap:
            factor_weight += weight
        if same_ticker or same_sector or factor_overlap:
            combined_weight += weight
            overlapping_positions.append(
                {
                    "ticker": row.get("ticker"),
                    "weight_pct": round(weight, 4),
                    "same_ticker": same_ticker,
                    "same_sector": same_sector,
                    "shared_factors": shared_factors,
                }
            )

    combined_weight = min(100.0, combined_weight)
    level = "HIGH" if combined_weight >= 50 else "MODERATE" if combined_weight >= 25 else "LOW"
    return {
        "exact_ticker_weight_pct": round(exact_weight, 4),
        "same_sector_weight_pct": round(sector_weight, 4),
        "factor_overlap_weight_pct": round(factor_weight, 4),
        "combined_overlap_weight_pct": round(combined_weight, 4),
        "concentration_level": level,
        "overlapping_positions": overlapping_positions,
    }


def _supersede_prior_overlap(case_id: str, case: dict[str, Any], new_snapshot_id: str) -> None:
    for row in list_objects(case_id, "primary_evidence_record"):
        if row.get("lane") != "valuation_market" or row.get("fact_key") != "portfolio_overlap":
            continue
        if row.get("first_party_governed_source") is not True or row.get("gap_resolution_eligible") is not True:
            continue
        record_id = str(row.get("primary_evidence_id") or "")
        if not record_id:
            continue
        superseded = {
            **row,
            "gap_resolution_eligible": False,
            "superseded_by_portfolio_snapshot_id": new_snapshot_id,
            "superseded_at": utc_now(),
        }
        record_object(record_id, "primary_evidence_record", case_id, superseded, topic=case.get("topic"))
        record_event(
            case_id,
            "PORTFOLIO_OVERLAP_EVIDENCE_SUPERSEDED",
            entity_id=record_id,
            payload={"superseded_by_portfolio_snapshot_id": new_snapshot_id},
        )


def _record_primary_overlap(case_id: str, case: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    overlap = snapshot["overlap"]
    requirement = _valuation_requirement(case_id)
    claim = (
        f"Governed portfolio snapshot for candidate {snapshot['candidate_ticker']}: "
        f"exact-ticker exposure={overlap['exact_ticker_weight_pct']}%; "
        f"same-sector exposure={overlap['same_sector_weight_pct']}%; "
        f"factor-overlap exposure={overlap['factor_overlap_weight_pct']}%; "
        f"combined overlap={overlap['combined_overlap_weight_pct']}%; "
        f"concentration={overlap['concentration_level']}."
    )

    # Historical snapshots remain auditable, but only the newest snapshot can count as
    # current portfolio-overlap evidence.
    _supersede_prior_overlap(case_id, case, snapshot["portfolio_snapshot_id"])

    record_id = f"primary_evidence_{uuid4().hex}"
    record = {
        "primary_evidence_id": record_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "lane": "valuation_market",
        "lane_label": "MU Valuation / Market",
        "fact_key": "portfolio_overlap",
        "claim": claim,
        "source_name": "User-governed portfolio snapshot",
        "source_url": f"iios://portfolio/{snapshot['portfolio_snapshot_id']}",
        "source_type": "portfolio_data",
        "source_grade": "FIRST_PARTY_GOVERNED",
        "evidence_type": "portfolio_snapshot",
        "observed_at": snapshot["as_of"],
        "reliability_score": 1.0,
        "gap_requirement": requirement,
        "gap_resolution_eligible": True,
        "verified_public_source": False,
        "first_party_governed_source": True,
        "portfolio_snapshot_id": snapshot["portfolio_snapshot_id"],
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }
    record_object(record_id, "primary_evidence_record", case_id, record, topic=case.get("topic"))
    record_event(
        case_id,
        "PORTFOLIO_OVERLAP_PRIMARY_EVIDENCE_RECORDED",
        entity_id=record_id,
        payload={
            "portfolio_snapshot_id": snapshot["portfolio_snapshot_id"],
            "combined_overlap_weight_pct": overlap["combined_overlap_weight_pct"],
            "concentration_level": overlap["concentration_level"],
        },
    )
    return record


def portfolio_status(case_id: str) -> dict[str, Any]:
    _require_case(case_id)
    snapshot = latest_object("portfolio_snapshot", case_id=case_id)
    return {
        "case_id": case_id,
        "candidate_ticker": _candidate_ticker(case_id),
        "snapshot": snapshot,
        "snapshot_required": snapshot is None,
        "paper_mode": True,
        "live_execution": False,
    }


@router.get("/portfolio-context/{case_id}")
def get_portfolio_context(case_id: str):
    return portfolio_status(case_id)


@router.post("/portfolio-context/{case_id}")
def create_portfolio_snapshot(case_id: str, payload: dict[str, Any]):
    case = _require_case(case_id)
    candidate_ticker = _candidate_ticker(case_id)
    candidate_sector = str(payload.get("candidate_sector") or "").strip()
    candidate_factors = _factor_set(payload.get("candidate_factors"))
    if not candidate_sector and not candidate_factors:
        raise HTTPException(status_code=422, detail="Provide candidate_sector or at least one candidate factor")

    positions = [row for item in (payload.get("positions") or []) if (row := _clean_position(item))]
    if not positions:
        raise HTTPException(status_code=422, detail="Add at least one portfolio position")

    weight_sum = round(sum(float(row["weight_pct"]) for row in positions), 4)
    if weight_sum < 99 or weight_sum > 101:
        raise HTTPException(status_code=422, detail=f"Portfolio weights must total about 100%; current total is {weight_sum}%")

    as_of = str(payload.get("as_of") or utc_now()).strip()
    overlap = _compute_overlap(candidate_ticker, candidate_sector, candidate_factors, positions)
    snapshot_id = f"portfolio_snapshot_{uuid4().hex}"
    snapshot = {
        "portfolio_snapshot_id": snapshot_id,
        "case_id": case_id,
        "candidate_ticker": candidate_ticker,
        "candidate_sector": candidate_sector,
        "candidate_factors": sorted(candidate_factors),
        "positions": positions,
        "position_count": len(positions),
        "weight_sum_pct": weight_sum,
        "overlap": overlap,
        "as_of": as_of,
        "source": "USER_GOVERNED_PORTFOLIO_INPUT",
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }
    record_object(snapshot_id, "portfolio_snapshot", case_id, snapshot, topic=case.get("topic"))
    record_event(
        case_id,
        "PORTFOLIO_SNAPSHOT_RECORDED",
        entity_id=snapshot_id,
        payload={
            "position_count": len(positions),
            "weight_sum_pct": weight_sum,
            "candidate_ticker": candidate_ticker,
            "concentration_level": overlap["concentration_level"],
        },
    )
    primary_record = _record_primary_overlap(case_id, case, snapshot)
    return {
        "case_id": case_id,
        "snapshot": snapshot,
        "primary_evidence_id": primary_record["primary_evidence_id"],
        "paper_mode": True,
        "live_execution": False,
    }
