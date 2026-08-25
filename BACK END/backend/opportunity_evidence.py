from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from official_sources import fetch_google_news_rss
from provider_hardening import (
    _fetch_yahoo_chart,
    _json_request,
    _quote_item,
    fetch_gdelt_news,
)


DEFAULT_QUOTE_TOLERANCE_PCT = 2.0
MAX_NEWS_PER_PROVIDER = 12


def _safe_price(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "").replace("$", "")
    try:
        price = float(text)
    except (TypeError, ValueError):
        return None
    if price != price or price <= 0:
        return None
    return price


def _cnbc_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if text.endswith(".US"):
        return text[:-3]
    return text


def _fetch_cnbc_quote(symbol: str) -> tuple[float, str | None, str]:
    normalized = _cnbc_symbol(symbol)
    if not normalized:
        raise ValueError("Ticker is required")

    url = (
        "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
        f"?symbols={quote_plus(normalized)}"
        "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
    )
    payload = _json_request(
        url=url,
        provider="cnbc_quote",
        minimum_interval_seconds=0.25,
        retries=2,
        cache_ttl_seconds=2 * 60,
    )
    result = payload.get("FormattedQuoteResult") or {}
    rows = result.get("FormattedQuote") or result.get("formattedQuote") or []
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not rows:
        raise ValueError("CNBC quote returned no result")

    row = next(
        (
            item
            for item in rows
            if isinstance(item, dict)
            and str(item.get("symbol") or "").strip().upper() == normalized
        ),
        rows[0] if isinstance(rows[0], dict) else None,
    )
    if not isinstance(row, dict):
        raise ValueError("CNBC quote returned an invalid result")
    if row.get("code") not in (None, 0, "0"):
        raise ValueError(f"CNBC quote returned code {row.get('code')}")

    price = _safe_price(row.get("last"))
    if price is None:
        raise ValueError("CNBC quote returned no usable price")
    timestamp = str(row.get("last_time") or row.get("last_timedate") or "").strip() or None
    return price, timestamp, url


def _cnbc_observation(symbol: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        price, timestamp, url = _fetch_cnbc_quote(symbol)
        return {
            "provider": "CNBC",
            "price": price,
            "timestamp": timestamp,
            "url": url,
            "mode": "quote_cache",
            "item": _quote_item("CNBC", symbol, price, timestamp, url),
        }, []
    except Exception as exc:
        return None, [f"CNBC: {type(exc).__name__}: {exc}"]


def _yahoo_observation(symbol: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        price, timestamp, url = _fetch_yahoo_chart(symbol)
        price = _safe_price(price)
        if price is None:
            raise ValueError("Yahoo Finance returned an invalid price")
        return {
            "provider": "Yahoo Finance",
            "price": price,
            "timestamp": timestamp,
            "url": url,
            "mode": "chart",
            "item": _quote_item("Yahoo Finance", symbol, price, timestamp, url),
        }, []
    except Exception as exc:
        return None, [f"Yahoo Finance: {type(exc).__name__}: {exc}"]


def fetch_crosschecked_quote(
    symbol: str,
    *,
    tolerance_pct: float = DEFAULT_QUOTE_TOLERANCE_PCT,
) -> dict[str, Any]:
    """Fetch two independent public quote observations for research admission.

    CNBC and Yahoo Finance are queried independently. A single-source price may
    be displayed, but it cannot satisfy the opportunity-promotion quote gate.
    Material provider disagreement fails closed.
    """
    symbol = str(symbol or "").strip()
    if not symbol:
        return {
            "status": "skipped",
            "items": [],
            "current_price": None,
            "provider": None,
            "provider_count": 0,
            "providers": [],
            "cross_checked": False,
            "spread_pct": None,
            "agreement_threshold_pct": tolerance_pct,
            "quote_quality": "NO_QUOTE",
            "error": None,
        }

    tolerance_pct = max(0.1, min(float(tolerance_pct), 10.0))
    observations: list[dict[str, Any]] = []
    errors: list[str] = []

    cnbc, cnbc_errors = _cnbc_observation(symbol)
    errors.extend(cnbc_errors)
    if cnbc:
        observations.append(cnbc)

    yahoo, yahoo_errors = _yahoo_observation(symbol)
    errors.extend(yahoo_errors)
    if yahoo:
        observations.append(yahoo)

    items = [obs["item"] for obs in observations]
    providers = [str(obs["provider"]) for obs in observations]

    if not observations:
        return {
            "status": "error",
            "items": [],
            "current_price": None,
            "provider": None,
            "provider_count": 0,
            "providers": [],
            "cross_checked": False,
            "spread_pct": None,
            "agreement_threshold_pct": tolerance_pct,
            "quote_quality": "NO_QUOTE",
            "error": " | ".join(errors) or "No quote provider returned a usable price",
        }

    if len(observations) == 1:
        only = observations[0]
        return {
            "status": "single_source",
            "items": items,
            "current_price": only["price"],
            "provider": only["provider"],
            "provider_count": 1,
            "providers": providers,
            "cross_checked": False,
            "spread_pct": None,
            "agreement_threshold_pct": tolerance_pct,
            "quote_quality": "SINGLE_SOURCE",
            "error": " | ".join(errors) or "Second independent quote provider unavailable",
        }

    prices = [float(obs["price"]) for obs in observations]
    midpoint = sum(prices) / len(prices)
    spread_pct = 0.0 if midpoint <= 0 else ((max(prices) - min(prices)) / midpoint) * 100.0
    spread_pct = round(spread_pct, 4)

    if spread_pct > tolerance_pct:
        return {
            "status": "conflict",
            "items": items,
            "current_price": None,
            "provider": None,
            "provider_count": len(observations),
            "providers": providers,
            "cross_checked": False,
            "spread_pct": spread_pct,
            "agreement_threshold_pct": tolerance_pct,
            "quote_quality": "PROVIDER_CONFLICT",
            "observations": [
                {
                    "provider": obs["provider"],
                    "price": obs["price"],
                    "timestamp": obs["timestamp"],
                    "mode": obs["mode"],
                }
                for obs in observations
            ],
            "error": (
                f"Independent quote providers disagree by {spread_pct:.4f}% "
                f"which exceeds the {tolerance_pct:.4f}% research threshold"
            ),
        }

    preferred = next(
        (obs for obs in observations if obs["provider"] == "Yahoo Finance"),
        observations[0],
    )
    return {
        "status": "ok",
        "items": items,
        "current_price": preferred["price"],
        "provider": preferred["provider"],
        "provider_count": len(observations),
        "providers": providers,
        "cross_checked": True,
        "spread_pct": spread_pct,
        "agreement_threshold_pct": tolerance_pct,
        "quote_quality": "CROSSCHECKED",
        "observations": [
            {
                "provider": obs["provider"],
                "price": obs["price"],
                "timestamp": obs["timestamp"],
                "mode": obs["mode"],
            }
            for obs in observations
        ],
        "error": " | ".join(errors) or None,
    }


def _normalized_title(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+-\s+[^-]{2,80}$", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _dedupe_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        title_key = _normalized_title(item.get("title") or item.get("claim"))
        url_key = str(item.get("url") or "").strip().lower()
        if title_key and title_key in seen_titles:
            continue
        if url_key and url_key in seen_urls:
            continue
        if title_key:
            seen_titles.add(title_key)
        if url_key:
            seen_urls.add(url_key)
        output.append(item)
    return output


def fetch_news_bundle(
    query: str,
    *,
    limit: int = 8,
    timespan: str = "24h",
) -> dict[str, Any]:
    """Fetch news from GDELT and Google News RSS, failing soft by provider."""
    query = str(query or "").strip()
    if len(query) < 2:
        raise ValueError("Opportunity news bundle requires query")
    limit = max(1, min(int(limit), MAX_NEWS_PER_PROVIDER))

    provider_results: list[dict[str, Any]] = []
    combined: list[dict[str, Any]] = []

    for provider_name, fetcher, params in (
        (
            "GDELT",
            fetch_gdelt_news,
            {"query": query, "limit": limit, "timespan": timespan},
        ),
        (
            "GOOGLE_NEWS_RSS",
            fetch_google_news_rss,
            {"query": query, "limit": limit},
        ),
    ):
        try:
            items = fetcher(params)
            provider_results.append(
                {
                    "provider": provider_name,
                    "status": "ok",
                    "item_count": len(items),
                    "error": None,
                }
            )
            combined.extend(items)
        except Exception as exc:
            provider_results.append(
                {
                    "provider": provider_name,
                    "status": "error",
                    "item_count": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    items = _dedupe_news(combined)
    successful = [row for row in provider_results if row["status"] == "ok"]
    return {
        "items": items,
        "provider_results": provider_results,
        "provider_count": len(successful),
        "successful_providers": [row["provider"] for row in successful],
        "failed_providers": [row["provider"] for row in provider_results if row["status"] != "ok"],
        "item_count": len(items),
        "status": "ok" if items else ("empty" if successful else "error"),
        "paper_mode": True,
        "trade_signal": False,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
