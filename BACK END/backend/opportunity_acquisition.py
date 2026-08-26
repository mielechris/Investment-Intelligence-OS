from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from evidence_engine import build_packet
from ledger import DB_PATH, get_object, latest_object, record_event, record_object, utc_now
from provider_hardening import fetch_gdelt_news, fetch_google_news_rss, fetch_market_quote


router = APIRouter()

PAPER_MODE = True
OPPORTUNITY_LEDGER_CASE = "opportunity_factory"
MAX_SCAN_SYMBOLS = 20
MAX_QUEUE_SIZE = 20
MIN_PROMOTION_SCORE = 45.0
DEFAULT_NEWS_LIMIT = 10

# Small, liquid, cross-sector starter universe. It is a research universe only,
# not a recommendation list. The API can replace it with a governed universe.
DEFAULT_UNIVERSE = [
    {"ticker": "SPY", "label": "S&P 500 ETF", "query": "S&P 500 US stocks"},
    {"ticker": "QQQ", "label": "Nasdaq 100 ETF", "query": "Nasdaq 100 technology stocks"},
    {"ticker": "IWM", "label": "Russell 2000 ETF", "query": "Russell 2000 small cap stocks"},
    {"ticker": "NVDA", "label": "NVIDIA", "query": "NVIDIA AI chips"},
    {"ticker": "MU", "label": "Micron Technology", "query": "Micron Technology memory HBM DRAM NAND"},
    {"ticker": "AMD", "label": "Advanced Micro Devices", "query": "AMD AI chips data center"},
    {"ticker": "AVGO", "label": "Broadcom", "query": "Broadcom AI networking semiconductors"},
    {"ticker": "TSM", "label": "Taiwan Semiconductor", "query": "TSMC semiconductor foundry"},
    {"ticker": "MSFT", "label": "Microsoft", "query": "Microsoft Azure AI cloud"},
    {"ticker": "AMZN", "label": "Amazon", "query": "Amazon AWS AI cloud"},
    {"ticker": "GOOGL", "label": "Alphabet", "query": "Google Alphabet AI cloud"},
    {"ticker": "META", "label": "Meta Platforms", "query": "Meta AI data center"},
    {"ticker": "XOM", "label": "Exxon Mobil", "query": "Exxon Mobil oil energy"},
    {"ticker": "CAT", "label": "Caterpillar", "query": "Caterpillar industrial construction mining"},
    {"ticker": "JPM", "label": "JPMorgan Chase", "query": "JPMorgan banks credit economy"},
    {"ticker": "LLY", "label": "Eli Lilly", "query": "Eli Lilly pharmaceuticals obesity diabetes"},
]

CATALYST_TERMS = {
    "earnings": ("earnings", "revenue", "guidance", "margin", "profit", "forecast"),
    "policy": ("tariff", "regulation", "executive order", "subsidy", "sanction", "export control"),
    "macro": ("federal reserve", "fed", "interest rate", "inflation", "jobs", "treasury", "recession"),
    "supply": ("shortage", "inventory", "capacity", "supply", "shipment", "production", "wafer"),
    "demand": ("orders", "backlog", "demand", "sales", "customer", "contract"),
    "capital": ("buyback", "dividend", "acquisition", "merger", "capex", "investment"),
    "geopolitics": ("war", "sanction", "china", "taiwan", "middle east", "export", "trade restriction"),
    "weather": ("hurricane", "drought", "flood", "wildfire", "storm", "heat wave", "freeze"),
}


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_universe_item(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        ticker = value.strip().upper()
        label = ticker
        query = ticker
    elif isinstance(value, dict):
        ticker = str(value.get("ticker") or "").strip().upper()
        label = str(value.get("label") or ticker).strip()
        query = str(value.get("query") or label or ticker).strip()
    else:
        return None

    if not ticker or len(ticker) > 12:
        return None
    if not all(ch.isalnum() or ch in {".", "-"} for ch in ticker):
        return None
    return {"ticker": ticker, "label": label or ticker, "query": query or ticker}


def normalize_universe(values: Any) -> list[dict[str, str]]:
    raw = values if isinstance(values, list) else []
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in raw:
        item = _clean_universe_item(value)
        if not item or item["ticker"] in seen:
            continue
        seen.add(item["ticker"])
        output.append(item)
        if len(output) >= MAX_SCAN_SYMBOLS:
            break
    return output


def catalyst_categories(news_items: list[dict[str, Any]]) -> list[str]:
    corpus = " ".join(
        f"{item.get('title') or ''} {item.get('claim') or ''}".lower()
        for item in news_items
        if isinstance(item, dict)
    )
    return sorted(
        category
        for category, terms in CATALYST_TERMS.items()
        if any(term in corpus for term in terms)
    )


def score_candidate(
    *,
    ticker: str,
    quote: dict[str, Any],
    news_items: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Deterministic research-priority score. It is never a trade signal."""
    now = now or datetime.now(timezone.utc)
    score = 0.0
    reasons: list[str] = []

    quote_ok = (
        quote.get("status") == "ok"
        and quote.get("current_price") is not None
    )
    if quote_ok:
        score += 20.0
        reasons.append("CURRENT_MARKET_QUOTE")
    else:
        reasons.append("QUOTE_UNAVAILABLE")

    news_count = len(news_items)
    score += min(news_count * 3.0, 24.0)
    if news_count:
        reasons.append("CURRENT_NEWS_COVERAGE")
    else:
        score -= 10.0
        reasons.append("NO_CURRENT_NEWS")

    sources = {
        str(item.get("source") or "").strip().lower()
        for item in news_items
        if isinstance(item, dict) and str(item.get("source") or "").strip()
    }
    score += min(len(sources) * 2.0, 12.0)
    if len(sources) >= 3:
        reasons.append("MULTI_SOURCE_COVERAGE")

    categories = catalyst_categories(news_items)
    score += min(len(categories) * 6.0, 24.0)
    if categories:
        reasons.append("CATALYST_DIVERSITY")

    recent_count = 0
    for item in news_items:
        observed = _parse_time(item.get("timestamp")) if isinstance(item, dict) else None
        if observed is not None:
            age_hours = max(0.0, (now - observed).total_seconds() / 3600.0)
            if age_hours <= 24.0:
                recent_count += 1
    score += min(recent_count * 2.0, 10.0)
    if recent_count:
        reasons.append("RECENT_24H_COVERAGE")

    score = round(max(0.0, min(100.0, score)), 2)
    if score >= 65.0:
        priority = "HIGH"
    elif score >= MIN_PROMOTION_SCORE:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    eligible = bool(
        quote_ok
        and news_count >= 2
        and score >= MIN_PROMOTION_SCORE
    )

    return {
        "ticker": ticker.upper(),
        "score": score,
        "priority": priority,
        "eligible_for_promotion": eligible,
        "reason_codes": reasons,
        "catalyst_categories": categories,
        "news_count": news_count,
        "source_count": len(sources),
        "recent_24h_count": recent_count,
        "quote_ok": quote_ok,
        "trade_signal": False,
        "direction": "UNSPECIFIED",
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def current_universe() -> list[dict[str, str]]:
    saved = latest_object("opportunity_universe", case_id=OPPORTUNITY_LEDGER_CASE) or {}
    values = normalize_universe(saved.get("symbols"))
    return values or list(DEFAULT_UNIVERSE)


def save_universe(values: Any) -> dict[str, Any]:
    symbols = normalize_universe(values)
    if not symbols:
        raise ValueError("Provide at least one valid ticker")
    payload = {
        "opportunity_universe_id": "opportunity_universe_default",
        "symbols": symbols,
        "symbol_count": len(symbols),
        "updated_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
    }
    record_object(
        "opportunity_universe_default",
        "opportunity_universe",
        OPPORTUNITY_LEDGER_CASE,
        payload,
    )
    record_event(
        OPPORTUNITY_LEDGER_CASE,
        "OPPORTUNITY_UNIVERSE_UPDATED",
        entity_id="opportunity_universe_default",
        payload={"symbol_count": len(symbols), "auto_trade_authority": False},
    )
    return payload


def _rows_by_type(object_type: str, limit: int = 100) -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? ORDER BY created_at DESC LIMIT ?",
            (object_type, max(1, min(int(limit), 500))),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def opportunity_queue(limit: int = 10) -> list[dict[str, Any]]:
    rows = _rows_by_type("opportunity_candidate", 250)
    latest_by_ticker: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker and ticker not in latest_by_ticker:
            latest_by_ticker[ticker] = row
    ranked = sorted(
        latest_by_ticker.values(),
        key=lambda row: (float(row.get("score") or 0.0), str(row.get("created_at") or "")),
        reverse=True,
    )
    return ranked[: max(1, min(int(limit), MAX_QUEUE_SIZE))]


def scan_universe(
    universe: list[dict[str, str]] | None = None,
    *,
    news_limit: int = DEFAULT_NEWS_LIMIT,
    timespan: str = "24h",
    max_candidates: int = 10,
) -> dict[str, Any]:
    symbols = normalize_universe(universe) if universe is not None else current_universe()
    if not symbols:
        raise ValueError("Opportunity universe is empty")

    news_limit = max(2, min(int(news_limit), 20))
    max_candidates = max(1, min(int(max_candidates), MAX_QUEUE_SIZE))
    scan_id = f"opportunity_scan_{uuid4().hex}"
    rows: list[dict[str, Any]] = []

    for item in symbols[:MAX_SCAN_SYMBOLS]:
        ticker = item["ticker"]
        quote = fetch_market_quote(ticker)
        # Opportunity discovery must not depend on one
        # news aggregator. GDELT remains primary, with
        # hardened Google News RSS as the fallback.
        news: list[dict[str, Any]] = []
        news_errors: list[str] = []

        try:
            news = fetch_gdelt_news(
                {
                    "query": item["query"],
                    "limit": news_limit,
                    "timespan": timespan,
                }
            )
        except Exception as exc:
            news_errors.append(
                f"GDELT:{type(exc).__name__}:{exc}"
            )

        # Promotion requires at least two news records.
        # If GDELT is unavailable or thin, supplement
        # with Google News RSS rather than manufacturing
        # eligibility or lowering the promotion gate.
        if len(news) < 2:
            try:
                fallback = fetch_google_news_rss(
                    {
                        "query": item["query"],
                        "limit": news_limit,
                    }
                )

                seen = {
                    (
                        str(row.get("url") or ""),
                        str(row.get("title") or ""),
                    )
                    for row in news
                    if isinstance(row, dict)
                }

                for row in fallback:
                    if not isinstance(row, dict):
                        continue

                    key = (
                        str(row.get("url") or ""),
                        str(row.get("title") or ""),
                    )

                    if key in seen:
                        continue

                    seen.add(key)
                    news.append(row)

                    if len(news) >= news_limit:
                        break

            except Exception as exc:
                news_errors.append(
                    f"GOOGLE_NEWS:{type(exc).__name__}:{exc}"
                )

        news_error = (
            " | ".join(news_errors)
            if news_errors
            else None
        )

        scored = score_candidate(ticker=ticker, quote=quote, news_items=news)
        candidate_id = f"opportunity_{uuid4().hex}"
        evidence = list(quote.get("items") or []) + list(news)
        candidate = {
            "opportunity_candidate_id": candidate_id,
            "opportunity_scan_id": scan_id,
            "ticker": ticker,
            "label": item["label"],
            "query": item["query"],
            **scored,
            "current_price": quote.get("current_price"),
            "quote_provider": quote.get("provider"),
            "quote_error": quote.get("error"),
            "news_error": news_error,
            "evidence": evidence,
            "evidence_count": len(evidence),
            "promoted_case_id": None,
            "created_at": utc_now(),
        }
        record_object(candidate_id, "opportunity_candidate", OPPORTUNITY_LEDGER_CASE, candidate, topic=item["label"])
        rows.append(candidate)

    ranked = sorted(rows, key=lambda row: float(row.get("score") or 0.0), reverse=True)
    queued = [row for row in ranked if row.get("eligible_for_promotion")][:max_candidates]
    scan = {
        "opportunity_scan_id": scan_id,
        "universe_count": len(symbols),
        "scanned_count": len(rows),
        "queued_count": len(queued),
        "candidates": ranked,
        "queue": queued,
        "created_at": utc_now(),
        "paper_mode": True,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(scan_id, "opportunity_scan", OPPORTUNITY_LEDGER_CASE, scan)
    record_event(
        OPPORTUNITY_LEDGER_CASE,
        "OPPORTUNITY_SCAN_COMPLETE",
        entity_id=scan_id,
        payload={
            "scanned_count": len(rows),
            "queued_count": len(queued),
            "trade_signal": False,
            "auto_trade_authority": False,
        },
    )
    return scan


def promote_candidate(candidate_id: str) -> dict[str, Any]:
    candidate = get_object(candidate_id)
    if not candidate or not str(candidate_id).startswith("opportunity_"):
        raise ValueError("Unknown opportunity candidate")
    if candidate.get("promoted_case_id"):
        existing = get_object(str(candidate["promoted_case_id"]))
        if existing:
            return {"case": existing, "candidate": candidate, "already_promoted": True}
    if candidate.get("eligible_for_promotion") is not True:
        raise ValueError("Candidate has not met the research-promotion gate")

    packet_id = f"packet_{uuid4().hex}"
    case_id = f"case_{uuid4().hex}"
    packet = {
        **build_packet(candidate.get("evidence") or []),
        "evidence_packet_id": packet_id,
        "case_id": case_id,
    }
    topic = f"{candidate.get('label') or candidate.get('ticker')} ({candidate.get('ticker')}) opportunity review"
    case = {
        "case_id": case_id,
        "topic": topic,
        "evidence_packet_id": packet_id,
        "evidence": packet["items"],
        "evidence_summary": packet["summary"],
        "source_candidate_id": candidate_id,
        "opportunity_score": candidate.get("score"),
        "opportunity_priority": candidate.get("priority"),
        "created_by": "OPPORTUNITY_ACQUISITION_V1",
        "created_at": utc_now(),
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(case_id, "case", case_id, case, topic=topic)
    record_object(packet_id, "evidence_packet", case_id, packet, parent_id=case_id, topic=topic)

    updated_candidate = {**candidate, "promoted_case_id": case_id, "promoted_at": utc_now()}
    record_object(candidate_id, "opportunity_candidate", OPPORTUNITY_LEDGER_CASE, updated_candidate, topic=candidate.get("label"))
    record_event(case_id, "OPPORTUNITY_PROMOTED_TO_CASE", entity_id=case_id, payload={
        "source_candidate_id": candidate_id,
        "opportunity_score": candidate.get("score"),
        "paper_mode": True,
        "trade_execution_permission": False,
    })
    return {"case": case, "candidate": updated_candidate, "already_promoted": False}


@router.get("/opportunities/universe")
def get_opportunity_universe():
    symbols = current_universe()
    return {
        "symbols": symbols,
        "symbol_count": len(symbols),
        "max_scan_symbols": MAX_SCAN_SYMBOLS,
        "paper_mode": True,
        "auto_trade_authority": False,
    }


@router.post("/opportunities/universe")
def update_opportunity_universe(request: dict[str, Any] = Body(...)):
    try:
        return save_universe(request.get("symbols"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/opportunities/scan")
def run_opportunity_scan(request: dict[str, Any] = Body(default={})):
    supplied = request.get("universe")
    universe = normalize_universe(supplied) if isinstance(supplied, list) else None
    try:
        return scan_universe(
            universe,
            news_limit=int(request.get("news_limit") or DEFAULT_NEWS_LIMIT),
            timespan=str(request.get("timespan") or "24h"),
            max_candidates=int(request.get("max_candidates") or 10),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/opportunities/queue")
def get_opportunity_queue(limit: int = 10):
    return {
        "queue": opportunity_queue(limit),
        "paper_mode": True,
        "trade_signal": False,
        "auto_trade_authority": False,
    }


@router.get("/opportunities/status")
def opportunity_status():
    latest = latest_object("opportunity_scan", case_id=OPPORTUNITY_LEDGER_CASE)
    return {
        "latest_scan": latest,
        "queue": opportunity_queue(10),
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/opportunities/{candidate_id}/promote")
def promote_opportunity(candidate_id: str):
    try:
        return promote_candidate(candidate_id)
    except ValueError as exc:
        status = 404 if "Unknown" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))
