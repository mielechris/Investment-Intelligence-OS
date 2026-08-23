from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ledger import get_object, latest_object, record_event, record_object
from monitoring_engine import configure_profile, refresh_profile


router = APIRouter()
PAPER_MODE = True
PROFILE_VERSION = "0.7.2"

MICRON_CIK = "723125"
HYPERSCALER_CIKS = {
    "Microsoft": "789019",
    "Meta": "1326801",
    "Alphabet": "1652044",
    "Amazon": "1018724",
}

MICRON_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "NetIncomeLoss",
    "InventoryNet",
    "CashAndCashEquivalentsAtCarryingValue",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PropertyPlantAndEquipmentNet",
]


def utc_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def build_memory_source_requests(topic: str = "") -> list[dict[str, Any]]:
    """Balanced public evidence profile for semiconductor-memory cases.

    The profile prefers official Micron investor-relations content, keeps SEC as an
    optional official filing source, uses one current-news query per provider to
    avoid rate-limit concentration, and retains macro/market context.
    """
    topic = topic.strip() or "Micron memory demand"
    news_query = (
        '(Micron OR "Micron Technology" OR HBM OR DRAM OR NAND) '
        '(pricing OR price OR inventory OR capacity OR supply OR demand OR capex OR hyperscaler OR "AI data center")'
    )
    return [
        {
            "source": "official_web",
            "params": {
                "url": "https://investors.micron.com/overview/default.aspx",
                "label": "Micron Investor Relations",
                "keywords": [
                    "record fiscal Q3",
                    "HBM",
                    "Strategic Customer Agreements",
                    "investing at record levels",
                ],
                "limit": 4,
                "evidence_type": "fundamental",
                "reliability_score": 0.93,
            },
        },
        {
            "source": "official_web",
            "params": {
                "url": "https://investors.micron.com/quarterly-results",
                "label": "Micron Quarterly Results",
                "keywords": ["Q3", "Revenue", "Prepared Remarks", "Form 10-Q"],
                "limit": 4,
                "evidence_type": "fundamental",
                "reliability_score": 0.93,
            },
        },
        {
            "source": "sec_companyfacts",
            "params": {
                "cik": MICRON_CIK,
                "tags": MICRON_TAGS,
                "limit": 8,
                "label": "Micron SEC Company Facts",
            },
        },
        {
            "source": "google_news_rss",
            "params": {"query": news_query, "limit": 8},
        },
        {
            "source": "gdelt_news",
            "params": {"query": news_query, "limit": 8, "timespan": "7d"},
        },
        {
            "source": "fred_series",
            "params": {"series_id": "DGS10", "limit": 4},
        },
    ]


def apply_memory_profile(case_id: str) -> dict[str, Any]:
    case = utc_case(case_id)
    existing = latest_object("monitor_profile", case_id=case_id) or {}
    profile = configure_profile(
        {
            "case_id": case_id,
            "enabled": True,
            "interval_minutes": existing.get("interval_minutes", 240),
            "source_requests": build_memory_source_requests(str(case.get("topic", ""))),
            "ticker": existing.get("ticker") or "MU.US",
            "direction": existing.get("direction") or "LONG",
            "reference_price": existing.get("reference_price"),
            "analysis_mode": "llm",
        }
    )
    record_event(
        case_id,
        "SEMICONDUCTOR_MEMORY_PROFILE_APPLIED",
        entity_id=profile.get("monitor_profile_id"),
        payload={
            "profile_version": PROFILE_VERSION,
            "source_count": len(profile.get("source_requests") or []),
            "ticker": profile.get("ticker"),
        },
    )
    return profile


def run_memory_refresh(case_id: str) -> dict[str, Any]:
    profile = apply_memory_profile(case_id)
    refreshed = refresh_profile(profile)
    return {
        "case_id": case_id,
        "profile_version": PROFILE_VERSION,
        "profile": refreshed["profile"],
        "snapshot": refreshed["snapshot"],
        "position": refreshed["position"],
        "thesis": refreshed["thesis"],
        "surveillance": refreshed["surveillance"],
        "paper_mode": PAPER_MODE,
    }


def run_full_memory_reunderwrite(case_id: str) -> dict[str, Any]:
    """Refresh semiconductor evidence and re-run all eight desks on the SAME case."""
    case = utc_case(case_id)
    refreshed = run_memory_refresh(case_id)
    packet = refreshed["snapshot"]["evidence_packet"]

    review_packet_id = f"packet_reunderwrite_{uuid4().hex}"
    review_packet = {
        **packet,
        "evidence_packet_id": review_packet_id,
        "case_id": case_id,
        "purpose": "SEMICONDUCTOR_MEMORY_REUNDERWRITE",
        "profile_version": PROFILE_VERSION,
    }
    record_object(
        review_packet_id,
        "evidence_packet",
        case_id,
        review_packet,
        parent_id=refreshed["snapshot"].get("monitor_snapshot_id"),
        topic=case.get("topic"),
    )
    record_event(
        case_id,
        "REUNDERWRITE_EVIDENCE_LOCKED",
        entity_id=review_packet_id,
        payload={
            "evidence_count": packet.get("summary", {}).get("evidence_count"),
            "average_quality_score": packet.get("summary", {}).get("average_quality_score"),
        },
    )

    review_case = {
        **case,
        "evidence_packet_id": review_packet_id,
        "evidence": packet.get("items") or [],
        "evidence_summary": packet.get("summary") or {},
    }

    # Lazy import avoids app/router import cycles.
    from main import build_committee, evaluate_decision, submit_paper_order

    committee = build_committee(review_case)
    risk = evaluate_decision(committee)
    execution = submit_paper_order(
        {"risk_authorization_id": risk["risk_authorization_id"]}
    )

    reunderwrite_id = f"full_reunderwrite_{uuid4().hex}"
    result = {
        "full_reunderwrite_id": reunderwrite_id,
        "case_id": case_id,
        "evidence_packet_id": review_packet_id,
        "profile_version": PROFILE_VERSION,
        "topic": case.get("topic"),
        "committee": committee,
        "risk": risk,
        "execution": execution,
        "evidence_summary": packet.get("summary") or {},
        "source_results": refreshed["snapshot"].get("ingestion", {}).get("source_results", []),
        "quote": refreshed["snapshot"].get("quote"),
        "paper_mode": PAPER_MODE,
        "live_execution": False,
    }
    record_object(
        reunderwrite_id,
        "full_reunderwrite",
        case_id,
        result,
        parent_id=committee.get("decision_id"),
        topic=case.get("topic"),
    )
    record_event(
        case_id,
        "FULL_REUNDERWRITE_COMPLETE",
        entity_id=reunderwrite_id,
        payload={
            "decision_id": committee.get("decision_id"),
            "committee_disposition": committee.get("disposition"),
            "committee_confidence": committee.get("confidence"),
            "risk_decision": risk.get("decision"),
            "execution": execution.get("execution"),
        },
    )
    return result


@router.get("/intelligence/templates/semiconductor-memory")
def semiconductor_memory_template():
    return {
        "name": "Semiconductor Memory Intelligence",
        "version": PROFILE_VERSION,
        "source_requests": build_memory_source_requests(),
        "paper_mode": True,
    }


@router.post("/intelligence/semiconductor-memory/{case_id}/refresh")
def semiconductor_memory_refresh(case_id: str):
    return run_memory_refresh(case_id)


@router.post("/intelligence/semiconductor-memory/{case_id}/reunderwrite")
def semiconductor_memory_reunderwrite(case_id: str):
    return run_full_memory_reunderwrite(case_id)
