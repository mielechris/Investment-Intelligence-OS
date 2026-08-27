from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from historical_regime_memory import find_historical_analogs
from ledger import get_object, latest_object, record_event, record_object, utc_now


router = APIRouter()

AGENT_KEY = "historical_pattern"
AGENT_NAME = "Historical Pattern & Precedent Analyst"
ROOM = "Pattern Archive"
POLICY_VERSION = "batch10c-historical-pattern-agent-v1"
MAX_ANALOGS = 8


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _enrich_outcome(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    if enriched.get("historical_outcome_known"):
        return enriched

    case_id = str(enriched.get("case_id") or "").strip()
    if not case_id:
        return enriched

    postmortem = latest_object("paper_trade_postmortem", case_id=case_id) or {}
    if not postmortem:
        return enriched

    enriched["outcome"] = postmortem.get("outcome")
    enriched["realized_return_pct"] = postmortem.get("realized_return_pct")
    enriched["historical_outcome_known"] = bool(postmortem.get("outcome"))
    enriched["outcome_source"] = "IIOS_PAPER_TRADE_POSTMORTEM"
    return enriched


def _score_analogs(analogs: list[dict[str, Any]]) -> dict[str, Any]:
    known: list[dict[str, Any]] = []
    for row in analogs:
        if row.get("historical_outcome_known"):
            known.append(row)

    total_similarity = sum(max(0.0, float(row.get("similarity") or 0.0)) for row in known)
    positive_weight = 0.0
    negative_weight = 0.0
    flat_weight = 0.0
    return_weight = 0.0
    weighted_return_sum = 0.0

    for row in known:
        similarity = max(0.0, float(row.get("similarity") or 0.0))
        realized = _safe_float(row.get("realized_return_pct"))
        outcome = str(row.get("outcome") or "").upper()

        if realized is not None:
            weighted_return_sum += realized * similarity
            return_weight += similarity
            if realized > 0:
                positive_weight += similarity
            elif realized < 0:
                negative_weight += similarity
            else:
                flat_weight += similarity
        elif outcome == "WIN":
            positive_weight += similarity
        elif outcome == "LOSS":
            negative_weight += similarity
        else:
            flat_weight += similarity

    directional_weight = positive_weight + negative_weight + flat_weight
    positive_share = (
        positive_weight / directional_weight
        if directional_weight > 0
        else None
    )
    weighted_mean_return = (
        weighted_return_sum / return_weight
        if return_weight > 0
        else None
    )
    mean_similarity = (
        total_similarity / len(known)
        if known
        else 0.0
    )

    return {
        "analog_count": len(analogs),
        "known_outcome_count": len(known),
        "outcome_coverage": round(len(known) / len(analogs), 4) if analogs else 0.0,
        "mean_known_similarity": round(mean_similarity, 4),
        "positive_similarity_share": round(positive_share, 4) if positive_share is not None else None,
        "weighted_mean_realized_return_pct": round(weighted_mean_return, 4) if weighted_mean_return is not None else None,
    }


def _classification(stats: dict[str, Any]) -> tuple[str, str, float]:
    analog_count = int(stats.get("analog_count") or 0)
    known_count = int(stats.get("known_outcome_count") or 0)
    coverage = float(stats.get("outcome_coverage") or 0.0)
    similarity = float(stats.get("mean_known_similarity") or 0.0)
    positive_share = stats.get("positive_similarity_share")
    mean_return = stats.get("weighted_mean_realized_return_pct")

    if analog_count == 0:
        return "INSUFFICIENT_PRECEDENT", "NO_TRADE", 0.15
    if known_count == 0:
        return "ANALOGS_WITHOUT_REALIZED_OUTCOMES", "NO_TRADE", 0.25

    confidence = min(0.80, 0.30 + 0.25 * coverage + 0.25 * similarity)
    positive_share_value = float(positive_share) if positive_share is not None else 0.5
    mean_return_value = float(mean_return) if mean_return is not None else 0.0

    if positive_share_value >= 0.60 and mean_return_value >= 0.0:
        return "HISTORICAL_SUPPORT", "WATCH", round(confidence, 4)
    if positive_share_value <= 0.40 or mean_return_value < 0.0:
        return "HISTORICAL_CAUTION", "NO_TRADE", round(confidence, 4)
    return "MIXED_PRECEDENT", "NO_TRADE", round(confidence, 4)


def build_historical_pattern_review(case_id: str, limit: int = 5) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise ValueError("Unknown case_id")

    limit = max(1, min(int(limit), MAX_ANALOGS))
    analog_packet = find_historical_analogs(case_id, limit=limit)
    analogs = [_enrich_outcome(row) for row in analog_packet.get("analogs") or []]
    stats = _score_analogs(analogs)
    classification, disposition, confidence = _classification(stats)

    known = int(stats.get("known_outcome_count") or 0)
    analog_count = int(stats.get("analog_count") or 0)
    weighted_return = stats.get("weighted_mean_realized_return_pct")
    positive_share = stats.get("positive_similarity_share")

    if classification == "INSUFFICIENT_PRECEDENT":
        view = "No sufficiently similar prior IIOS cases were found. Historical precedent is therefore unavailable and must not be invented."
        missing = ["similar prior governed IIOS cases with realized outcomes"]
    elif classification == "ANALOGS_WITHOUT_REALIZED_OUTCOMES":
        view = f"Found {analog_count} similar governed IIOS case(s), but none has a realized outcome suitable for precedent scoring."
        missing = ["realized outcomes for comparable prior cases"]
    else:
        view = (
            f"Found {analog_count} similar governed IIOS case(s), including {known} with realized outcomes. "
            f"Similarity-weighted positive share={positive_share}; weighted realized return={weighted_return}%. "
            f"Classification={classification}."
        )
        missing = []

    return {
        "agent_key": AGENT_KEY,
        "agent": AGENT_NAME,
        "room": ROOM,
        "policy_version": POLICY_VERSION,
        "status": "complete",
        "topic": str(case.get("topic") or ""),
        "headline": classification.replace("_", " ").title(),
        "view": view,
        "confidence": confidence,
        "disposition": disposition,
        "missing_evidence": missing,
        "falsifier": "Treat the analogy as invalid if new evidence shows the current catalyst, regime, balance-sheet condition, or transmission path is materially different from the cited precedents.",
        "floor_comment": "History gets a vote, not a time machine.",
        "historical_signal": classification,
        "current_regime_tags": analog_packet.get("current_regime_tags") or [],
        "analog_stats": stats,
        "analogs": analogs,
        "analogy_scope": "INTERNAL_IIOS_CASE_MEMORY",
        "warning": "This desk uses governed IIOS case history and realized IIOS paper-trade outcomes when available. It does not claim an external market backtest.",
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def run_historical_pattern_review(case_id: str, limit: int = 5) -> dict[str, Any]:
    review = build_historical_pattern_review(case_id, limit=limit)
    review_id = f"historical_pattern_{uuid4().hex}"
    persistent = {
        **review,
        "historical_pattern_review_id": review_id,
        "case_id": case_id,
        "created_at": utc_now(),
    }
    record_object(
        review_id,
        "historical_pattern_review",
        case_id,
        persistent,
        parent_id=str((get_object(case_id) or {}).get("evidence_packet_id") or "") or None,
        topic=str(review.get("topic") or ""),
    )
    record_event(
        case_id,
        "HISTORICAL_PATTERN_REVIEW_COMPLETE",
        entity_id=review_id,
        payload={
            "historical_signal": review.get("historical_signal"),
            "analog_count": (review.get("analog_stats") or {}).get("analog_count"),
            "known_outcome_count": (review.get("analog_stats") or {}).get("known_outcome_count"),
            "disposition": review.get("disposition"),
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )
    return persistent


@router.get("/intelligence/historical-pattern/{case_id}")
def historical_pattern_status(case_id: str):
    case = get_object(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case_id")
    latest = latest_object("historical_pattern_review", case_id=case_id)
    return {
        "case_id": case_id,
        "latest_review": latest,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
