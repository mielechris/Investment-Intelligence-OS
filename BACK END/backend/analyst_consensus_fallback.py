from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus

from provider_hardening import _request_bytes


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", unescape(data)).strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


def _symbol(module: Any, case_id: str) -> str:
    profile = module.latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


def _iso_date(text: str | None) -> str | None:
    value = str(text or "").strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None


def _scaled_number(value: str | None, suffix: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    multiplier = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(str(suffix or "").upper(), 1.0)
    return round(number * multiplier, 4)


def parse_stockanalysis_consensus(html: str, *, current_year: int | None = None) -> dict[str, Any] | None:
    """Parse only explicit forecast averages from StockAnalysis' public forecast page.

    StockAnalysis attributes these forecast tables to S&P Global Market Intelligence and
    TipRanks. This parser intentionally ignores rating/price-target prose and extracts only
    revenue/EPS consensus values plus the page's update date.
    """
    parser = _TextParser()
    parser.feed(html)
    text = parser.text()
    flat = re.sub(r"\s+", " ", text)
    year = int(current_year or datetime.now(timezone.utc).year)

    revenue_block = re.search(r"Revenue\s+Forecast(?P<body>.{0,4500}?)(?:Revenue\s+Growth|EPS\s+Forecast|$)", flat, re.I)
    eps_block = re.search(r"EPS\s+Forecast(?P<body>.{0,4500}?)(?:EPS\s+Growth|Revenue\s+Forecast|$)", flat, re.I)

    def avg_from_block(match: re.Match[str] | None, *, money_scale: bool) -> float | None:
        if not match:
            return None
        body = match.group("body")
        if str(year) not in body:
            return None
        avg = re.search(r"\bAvg\b\s*\$?([0-9][0-9,.]*)(?:\s*([KMBT]))?", body, re.I)
        if not avg:
            return None
        if money_scale:
            return _scaled_number(avg.group(1), avg.group(2))
        try:
            return float(avg.group(1).replace(",", ""))
        except ValueError:
            return None

    revenue = avg_from_block(revenue_block, money_scale=True)
    eps = avg_from_block(eps_block, money_scale=False)

    updated_match = re.search(r"Last\s+updated\s*:?\s*([A-Za-z]{3,9}\.?\s+\d{1,2},\s+\d{4})", flat, re.I)
    updated_at = _iso_date(updated_match.group(1)) if updated_match else None

    attribution = None
    source_match = re.search(r"Data\s+Sources?\s*:?\s*([^\n]{1,180})", text, re.I)
    if source_match:
        attribution = re.sub(r"\s+", " ", source_match.group(1)).strip()

    if revenue is None and eps is None:
        return None

    return {
        "year": year,
        "revenue_consensus": revenue,
        "eps_consensus": eps,
        "updated_at": updated_at,
        "attribution": attribution or "S&P Global Market Intelligence / TipRanks",
    }


def _fetch_stockanalysis(symbol: str) -> tuple[dict[str, Any], str]:
    normalized = symbol.strip().lower()
    if not normalized:
        raise ValueError("Ticker is required")
    url = f"https://stockanalysis.com/stocks/{quote_plus(normalized)}/forecast/"
    # Keep the client identifiable while using a standards-compatible browser-shaped UA.
    # StockAnalysis robots.txt permits /stocks/.../forecast/; this is not an anti-bot bypass.
    user_agent = (
        "Mozilla/5.0 (compatible; Investment-Intelligence-OS/0.13.2; "
        "+https://github.com/mielechris/Investment-Intelligence-OS)"
    )
    html = _request_bytes(
        url,
        accept="text/html,application/xhtml+xml",
        user_agent=user_agent,
        provider="stockanalysis_consensus",
        minimum_interval_seconds=0.8,
        retries=2,
        cache_ttl_seconds=30 * 60,
    ).decode("utf-8", errors="ignore")
    parsed = parse_stockanalysis_consensus(html)
    if not parsed:
        raise ValueError("StockAnalysis forecast page returned no usable revenue/EPS consensus")
    return parsed, url


def install_analyst_consensus_fallback(module: Any) -> None:
    """Add a ticker-driven consensus fallback after direct market-data providers fail.

    Consensus is inherently aggregated market data. The record is therefore classified as
    GOVERNED_CONSENSUS rather than PRIMARY_OFFICIAL/HARD_MARKET_DATA, is eligible only for
    the valuation-market `consensus` fact, and never carries execution authority.
    """
    prior_capture = module._capture_market
    prior_lane_status = module._lane_status
    prior_persist = module._persist_record

    def persist_record_with_consensus(case_id: str, case: dict[str, Any], lane: str, fact_key: str, item: dict[str, Any]):
        record = prior_persist(case_id, case, lane, fact_key, item)
        if not record:
            return record
        if str(item.get("source_type") or "").lower() != "consensus_data":
            return record
        if lane != "valuation_market" or fact_key != "consensus":
            return record

        governed = {
            **record,
            "source_type": "consensus_data",
            "source_grade": "GOVERNED_CONSENSUS",
            "gap_resolution_eligible": True,
            "verified_public_source": True,
            "consensus_aggregator": True,
            "primary_official_source": False,
            "trade_execution_permission": False,
            "classification_repaired_at": module.utc_now(),
            "classification_repair": "CONSENSUS_SOURCE_CLASS_EXCEPTION",
        }
        record_id = str(governed.get("primary_evidence_id") or "")
        if record_id:
            module.record_object(record_id, "primary_evidence_record", case_id, governed, topic=case.get("topic"))
            module.record_event(
                case_id,
                "CONSENSUS_PRIMARY_EVIDENCE_CLASSIFIED",
                entity_id=record_id,
                payload={"lane": lane, "fact_key": fact_key, "source_grade": "GOVERNED_CONSENSUS"},
            )
        return governed

    module._persist_record = persist_record_with_consensus

    def capture_market_with_consensus(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)
        existing = [
            row
            for row in module.list_objects(case_id, "primary_evidence_record")
            if row.get("lane") == "valuation_market"
            and row.get("fact_key") == "consensus"
            and row.get("gap_resolution_eligible") is True
        ]
        if existing:
            return added, failures

        symbol = _symbol(module, case_id)
        try:
            parsed, url = _fetch_stockanalysis(symbol)
            revenue = parsed.get("revenue_consensus")
            eps = parsed.get("eps_consensus")
            item = {
                "source": "StockAnalysis analyst forecast aggregation",
                "source_type": "consensus_data",
                "evidence_type": "analyst_consensus",
                "url": url,
                "title": f"{symbol} governed revenue / EPS consensus",
                "claim": (
                    f"{symbol} analyst consensus for {parsed['year']}: "
                    f"revenue={revenue}; EPS={eps}; underlying forecast attribution={parsed['attribution']}."
                ),
                "timestamp": parsed.get("updated_at") or module.utc_now(),
                "reliability_score": 0.84,
            }
            record = module._persist_record(case_id, case, "valuation_market", "consensus", item)
            if record:
                added.append(record)
        except Exception as exc:
            failures.append(f"Analyst consensus fallback: {type(exc).__name__}: {exc}")
        return added, failures

    def lane_status_with_consensus(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane == "valuation_market":
            facts = {str(row.get("key")): bool(row.get("covered")) for row in result.get("facts") or [] if isinstance(row, dict)}
            base = str(result.get("note") or "").strip()
            suffix = (
                " Revenue/EPS consensus is covered by a governed consensus aggregator because consensus is inherently aggregated market data; "
                "the record has no execution authority and cannot satisfy any other market fact."
                if facts.get("consensus")
                else " Revenue/EPS consensus remains OPEN unless a governed consensus provider or user-verified consensus snapshot returns current forecast values."
            )
            result["note"] = (base + suffix).strip()
        return result

    module._capture_market = capture_market_with_consensus
    module._lane_status = lane_status_with_consensus
