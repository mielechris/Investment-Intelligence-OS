from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from evidence_engine import build_packet

NEWS_MIN_QUALITY = 0.45
GENERAL_MIN_QUALITY = 0.35
RESOLUTION_MIN_QUALITY = 0.65
MAX_ITEMS_PER_SOURCE = 6


def _source_identity(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    host = urlparse(url).netloc.lower() if url else ""
    source = str(item.get("source") or "").strip().lower()
    return host or source or "unknown"


def _tokens(text: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "current", "latest",
        "data", "evidence", "verified", "reported", "covering", "whether", "terms",
        "spot", "contract", "plans", "volume", "volumes", "market",
    }
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {token for token in cleaned.split() if len(token) >= 4 and token not in stop}


def curate_gap_evidence(raw_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Admit useful evidence without allowing low-quality article volume to dilute the packet.

    Rejected items remain visible in the audit payload; they simply do not count toward the
    qualification packet. This is a quality firewall, not a threshold shortcut.
    """
    normalized_packet = build_packet(raw_items)
    by_source: dict[str, int] = defaultdict(int)
    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    ranked = sorted(
        normalized_packet.get("items") or [],
        key=lambda item: float(item.get("quality_score") or 0.0),
        reverse=True,
    )
    for item in ranked:
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else item
        source_type = str(item.get("source_type") or "unknown").lower()
        quality = float(item.get("quality_score") or 0.0)
        minimum = NEWS_MIN_QUALITY if source_type in {"news_aggregator", "reputable_news", "unknown"} else GENERAL_MIN_QUALITY
        identity = _source_identity(raw)
        reason = None
        if item.get("stale"):
            reason = "STALE"
        elif item.get("missing_fields"):
            reason = "INCOMPLETE"
        elif quality < minimum:
            reason = "QUALITY_BELOW_ADMISSION_FLOOR"
        elif by_source[identity] >= MAX_ITEMS_PER_SOURCE:
            reason = "SOURCE_CONCENTRATION_CAP"

        if reason:
            rejected.append({
                "reason": reason,
                "quality_score": quality,
                "source": item.get("source"),
                "source_type": source_type,
                "claim": item.get("claim"),
                "url": item.get("url"),
                "gap_requirement": raw.get("gap_requirement") if isinstance(raw, dict) else None,
            })
            continue

        by_source[identity] += 1
        admitted.append(raw)

    return {
        "admitted": admitted,
        "rejected": rejected,
        "raw_count": len(raw_items),
        "admitted_count": len(admitted),
        "rejected_count": len(rejected),
    }


def _supports_requirement(raw: dict[str, Any], requirement: str) -> bool:
    tagged = str(raw.get("gap_requirement") or "").strip()
    if tagged and tagged == requirement:
        return True
    requirement_tokens = _tokens(requirement)
    claim_tokens = _tokens(" ".join(str(raw.get(key) or "") for key in ("claim", "title", "source")))
    return len(requirement_tokens & claim_tokens) >= 2


def build_resolution_matrix(requirements: list[str], admitted_raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    for requirement in requirements:
        supporting = [item for item in admitted_raw if _supports_requirement(item, requirement)]
        packet = build_packet(supporting)
        normalized = packet.get("items") or []
        identities = {_source_identity(item.get("raw") if isinstance(item.get("raw"), dict) else item) for item in normalized}
        high_quality = [item for item in normalized if float(item.get("quality_score") or 0.0) >= RESOLUTION_MIN_QUALITY]
        official_like = [
            item for item in high_quality
            if str(item.get("source_type") or "").lower() in {"official", "company", "market_data", "filing", "regulatory"}
        ]
        average_quality = float((packet.get("summary") or {}).get("average_quality_score") or 0.0)

        # Resolution requires quality plus independent corroboration. An official/company/market
        # source can anchor a gap, but still needs at least one independent high-quality corroborator.
        resolved = (
            average_quality >= RESOLUTION_MIN_QUALITY
            and len(high_quality) >= 2
            and len(identities) >= 2
            and (len(official_like) >= 1 or len(high_quality) >= 3)
        )
        blockers: list[str] = []
        if average_quality < RESOLUTION_MIN_QUALITY:
            blockers.append("AVERAGE_QUALITY_BELOW_65")
        if len(high_quality) < 2:
            blockers.append("FEWER_THAN_TWO_HIGH_QUALITY_ITEMS")
        if len(identities) < 2:
            blockers.append("INSUFFICIENT_SOURCE_DIVERSITY")
        if not official_like and len(high_quality) < 3:
            blockers.append("NO_PRIMARY_OR_THREE_SOURCE_CORROBORATION")

        matrix.append({
            "requirement": requirement,
            "resolved": resolved,
            "supporting_items": len(normalized),
            "high_quality_items": len(high_quality),
            "independent_sources": len(identities),
            "official_or_market_items": len(official_like),
            "average_quality": round(average_quality, 4),
            "blockers": blockers,
            "top_support": [
                {
                    "source": item.get("source"),
                    "claim": item.get("claim"),
                    "quality_score": item.get("quality_score"),
                    "url": item.get("url"),
                }
                for item in sorted(normalized, key=lambda row: float(row.get("quality_score") or 0.0), reverse=True)[:3]
            ],
        })
    return matrix
