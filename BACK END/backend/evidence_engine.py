from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


RELIABILITY_DEFAULTS = {
    "official": 0.95,
    "regulatory": 0.95,
    "filing": 0.95,
    "exchange": 0.90,
    "company": 0.85,
    "reputable_news": 0.80,
    "research": 0.80,
    "market_data": 0.85,
    "social": 0.40,
    "unknown": 0.50,
}

FRESHNESS_WINDOWS_HOURS = {
    "market_data": 1,
    "news": 24,
    "policy": 72,
    "filing": 24 * 14,
    "quarterly_filing": 24 * 180,
    "quarterly_company": 24 * 180,
    "annual_filing": 24 * 400,
    "macro": 24 * 45,
    "fundamental": 24 * 120,
    "weather": 6,
    "research": 24 * 30,
    # OCC open interest is a prior-settlement periodic dataset. The latest
    # Friday settlement must remain admissible through weekends/holidays.
    "options": 24 * 4,
    "other": 24 * 7,
}
PERIODIC_EVIDENCE_TYPES = {"quarterly_filing", "quarterly_company", "annual_filing", "options"}
PERIODIC_FRESHNESS_FLOOR = 0.75


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clamp_score(value: Any, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def infer_source_type(item: dict[str, Any]) -> str:
    explicit = str(item.get("source_type", "")).strip().lower()
    if explicit:
        return explicit
    url = str(item.get("url", "")).strip().lower()
    source = str(item.get("source", "")).strip().lower()
    host = urlparse(url).netloc.lower() if url else ""
    combined = f"{host} {source}"
    if any(token in combined for token in ("sec.gov", "federalreserve.gov", "bls.gov", "bea.gov", "treasury.gov", "whitehouse.gov")):
        return "official"
    if any(token in combined for token in ("reuters", "bloomberg", "apnews", "wsj", "ft.com")):
        return "reputable_news"
    return "unknown"


def infer_evidence_type(item: dict[str, Any]) -> str:
    # Governed primary-fact classification is authoritative for narrow market
    # facts. This prevents an older/generic adapter label such as market_data
    # from making a verified OCC options record expire on the 1-hour quote window.
    primary_fact_key = str(item.get("primary_fact_key") or "").strip().lower()
    if primary_fact_key == "options":
        return "options"

    explicit = str(item.get("evidence_type", "")).strip().lower()
    if explicit:
        return explicit
    text = " ".join(str(item.get(key, "")) for key in ("title", "claim", "summary", "source")).lower()
    if any(token in text for token in ("price", "yield", "volume", "spread", "volatility")):
        return "market_data"
    if any(token in text for token in ("fed", "inflation", "jobs", "cpi", "gdp", "unemployment")):
        return "macro"
    if any(token in text for token in ("executive order", "tariff", "regulation", "policy", "legislation")):
        return "policy"
    if any(token in text for token in ("10-k", "10-q", "earnings", "revenue", "margin", "guidance")):
        return "filing"
    if any(token in text for token in ("hurricane", "drought", "weather", "temperature", "rainfall")):
        return "weather"
    return "other"


def freshness_window_hours(evidence_type: str) -> int:
    return FRESHNESS_WINDOWS_HOURS.get(evidence_type, FRESHNESS_WINDOWS_HOURS["other"])


def normalize_item(item: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    source_type = infer_source_type(item)
    evidence_type = infer_evidence_type(item)
    observed_at = parse_timestamp(item.get("observed_at") or item.get("published_at") or item.get("timestamp"))
    age_hours = None
    freshness_score = 0.0
    stale = True
    if observed_at:
        age_hours = max(0.0, (now - observed_at).total_seconds() / 3600)
        window = freshness_window_hours(evidence_type)
        stale = age_hours > window
        linear_freshness = max(0.0, min(1.0, 1 - (age_hours / window)))
        if evidence_type in PERIODIC_EVIDENCE_TYPES and not stale:
            freshness_score = max(PERIODIC_FRESHNESS_FLOOR, linear_freshness)
        else:
            freshness_score = linear_freshness

    reliability_default = RELIABILITY_DEFAULTS.get(source_type, RELIABILITY_DEFAULTS["unknown"])
    reliability_score = clamp_score(item.get("reliability_score"), reliability_default)
    claim = str(item.get("claim") or item.get("summary") or item.get("title") or "").strip()
    missing_fields = []
    if not claim:
        missing_fields.append("claim")
    if not str(item.get("source", "")).strip() and not str(item.get("url", "")).strip():
        missing_fields.append("source")
    if not observed_at:
        missing_fields.append("timestamp")

    quality_score = reliability_score * (freshness_score if observed_at else 0.25)
    normalized = {
        "evidence_id": str(item.get("evidence_id") or f"evidence_{uuid4().hex}"),
        "claim": claim,
        "source": str(item.get("source", "")).strip() or None,
        "url": str(item.get("url", "")).strip() or None,
        "source_type": source_type,
        "evidence_type": evidence_type,
        "observed_at": observed_at.isoformat() if observed_at else None,
        "ingested_at": now.isoformat(),
        "age_hours": round(age_hours, 3) if age_hours is not None else None,
        "freshness_window_hours": freshness_window_hours(evidence_type),
        "freshness_score": round(freshness_score, 4),
        "reliability_score": round(reliability_score, 4),
        "quality_score": round(quality_score, 4),
        "stale": stale,
        "conflict_group": item.get("conflict_group"),
        "stance": str(item.get("stance", "neutral")).lower(),
        "missing_fields": missing_fields,
        "raw": item,
    }
    return normalized


def detect_conflicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        group = item.get("conflict_group")
        if group:
            groups.setdefault(str(group), []).append(item)
    conflicts = []
    for group, members in groups.items():
        stances = {str(member.get("stance", "neutral")).lower() for member in members}
        directional = {stance for stance in stances if stance in {"bullish", "bearish", "supports", "contradicts"}}
        if len(directional) > 1:
            conflicts.append({
                "conflict_group": group,
                "evidence_ids": [member["evidence_id"] for member in members],
                "stances": sorted(directional),
            })
    return conflicts


def build_packet(raw_items: list[dict[str, Any]] | None) -> dict[str, Any]:
    now = utc_now()
    items = [normalize_item(item, now=now) for item in (raw_items or []) if isinstance(item, dict)]
    conflicts = detect_conflicts(items)
    stale_count = sum(1 for item in items if item["stale"])
    incomplete_count = sum(1 for item in items if item["missing_fields"])
    avg_quality = round(sum(item["quality_score"] for item in items) / len(items), 4) if items else 0.0
    critical_missing = []
    if not items:
        critical_missing.append("NO_EVIDENCE_SUPPLIED")
    if items and all(item["stale"] for item in items):
        critical_missing.append("ALL_EVIDENCE_STALE")
    if any("timestamp" in item["missing_fields"] for item in items):
        critical_missing.append("UNTIMED_EVIDENCE_PRESENT")
    if conflicts:
        critical_missing.append("CONFLICTING_EVIDENCE_PRESENT")

    return {
        "packet_version": "0.4.0",
        "generated_at": now.isoformat(),
        "items": items,
        "summary": {
            "evidence_count": len(items),
            "stale_count": stale_count,
            "incomplete_count": incomplete_count,
            "conflict_count": len(conflicts),
            "average_quality_score": avg_quality,
            "critical_flags": critical_missing,
        },
        "conflicts": conflicts,
    }
