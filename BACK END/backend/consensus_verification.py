from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ledger import get_object, latest_object, record_event, record_object
import primary_evidence


router = APIRouter()
PAPER_MODE = True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _ticker(case_id: str) -> str:
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


def _valid_public_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@router.get("/consensus-verification/{case_id}")
def consensus_verification_status(case_id: str):
    _require_case(case_id)
    ticker = _ticker(case_id)
    latest = latest_object("user_verified_consensus_snapshot", case_id=case_id)
    return {
        "case_id": case_id,
        "ticker": ticker,
        "suggested_source_url": f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/" if ticker else None,
        "latest_snapshot": latest,
        "paper_mode": True,
        "live_execution": False,
    }


@router.post("/consensus-verification/{case_id}")
def record_verified_consensus(case_id: str, payload: dict[str, Any]):
    case = _require_case(case_id)
    ticker = _ticker(case_id)
    if payload.get("verified_against_source") is not True:
        raise HTTPException(status_code=422, detail="Verify the values against the cited public source before saving")

    source_url = str(payload.get("source_url") or "").strip()
    if not _valid_public_url(source_url):
        raise HTTPException(status_code=422, detail="Provide a valid http/https public source URL")

    try:
        fiscal_year = int(payload.get("fiscal_year"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Fiscal year must be numeric")
    if fiscal_year < 2000 or fiscal_year > 2100:
        raise HTTPException(status_code=422, detail="Fiscal year is outside the supported range")

    try:
        revenue_billion = float(payload.get("revenue_consensus_billion"))
        eps = float(payload.get("eps_consensus"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Revenue consensus and EPS consensus must be numeric")
    if revenue_billion <= 0:
        raise HTTPException(status_code=422, detail="Revenue consensus must be greater than zero")

    observed_at = str(payload.get("observed_at") or utc_now()).strip()
    revenue = round(revenue_billion * 1_000_000_000.0, 2)
    source_name = str(payload.get("source_name") or "User-verified public consensus source").strip()
    snapshot_id = f"user_verified_consensus_{uuid4().hex}"
    snapshot = {
        "user_verified_consensus_snapshot_id": snapshot_id,
        "case_id": case_id,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "revenue_consensus": revenue,
        "eps_consensus": eps,
        "source_name": source_name,
        "source_url": source_url,
        "observed_at": observed_at,
        "verified_against_source": True,
        "source_class": "USER_VERIFIED_GOVERNED_CONSENSUS",
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }
    record_object(snapshot_id, "user_verified_consensus_snapshot", case_id, snapshot, topic=case.get("topic"))

    item = {
        "source": source_name,
        "source_type": "consensus_data",
        "evidence_type": "analyst_consensus",
        "url": source_url,
        "title": f"{ticker} user-verified revenue / EPS consensus",
        "claim": f"{ticker} analyst consensus for {fiscal_year}: revenue={revenue}; EPS={eps}; user verified values against cited public source.",
        "timestamp": observed_at,
        "reliability_score": 0.86,
    }
    record = primary_evidence._persist_record(case_id, case, "valuation_market", "consensus", item)
    if not record:
        raise HTTPException(status_code=500, detail="Consensus evidence could not be persisted")

    record_event(
        case_id,
        "USER_VERIFIED_CONSENSUS_RECORDED",
        entity_id=snapshot_id,
        payload={
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "primary_evidence_id": record.get("primary_evidence_id"),
            "source_url": source_url,
        },
    )
    return {
        "case_id": case_id,
        "snapshot": snapshot,
        "primary_evidence_id": record.get("primary_evidence_id"),
        "source_grade": record.get("source_grade"),
        "gap_resolution_eligible": record.get("gap_resolution_eligible"),
        "paper_mode": True,
        "live_execution": False,
    }
