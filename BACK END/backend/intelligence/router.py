from fastapi import APIRouter

from intelligence.models import EvidencePacket, TradeThesis


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/status")
def intelligence_status():
    return {
        "version": "1.1",
        "mode": "PAPER",
        "live_intelligence_foundation": True,
        "capabilities": {
            "evidence_packets": True,
            "trade_thesis_schema": True,
            "source_freshness": True,
            "external_live_feeds": False,
            "paper_portfolio": False,
            "live_execution": False,
        },
        "next_gate": "connect approved live evidence providers",
    }


@router.post("/evidence/validate")
def validate_evidence(packet: EvidencePacket):
    kinds = sorted({item.source_kind for item in packet.items})
    return {
        "topic": packet.topic,
        "source_count": packet.source_count,
        "fresh_source_count": packet.fresh_source_count,
        "source_kinds": kinds,
        "has_multiple_source_types": len(kinds) >= 2,
        "paper_mode": True,
    }


@router.post("/thesis/validate")
def validate_thesis(thesis: TradeThesis):
    missing = []

    if not thesis.catalysts:
        missing.append("catalysts")
    if not thesis.invalidation:
        missing.append("invalidation")
    if not thesis.evidence_required:
        missing.append("evidence_required")

    eligible_for_risk_review = (
        thesis.direction in {"LONG", "SHORT", "WATCH"}
        and thesis.confidence >= 0.65
        and not missing
    )

    return {
        "topic": thesis.topic,
        "asset": thesis.asset,
        "direction": thesis.direction,
        "confidence": thesis.confidence,
        "missing_fields": missing,
        "eligible_for_risk_review": eligible_for_risk_review,
        "paper_mode": True,
        "live_execution": False,
    }
