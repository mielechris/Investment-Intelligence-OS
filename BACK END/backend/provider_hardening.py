from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

import certifi


DEFAULT_TIMEOUT_SECONDS = 15
SEC_USER_AGENT = os.getenv(
    "IIOS_SEC_USER_AGENT",
    "Investment-Intelligence-OS/0.7 research mielechris@users.noreply.github.com",
)
GENERIC_USER_AGENT = os.getenv(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.7 research-client github.com/mielechris/Investment-Intelligence-OS",
)

_CACHE: dict[str, tuple[float, bytes]] = {}
_CACHE_LOCK = threading.Lock()
_PROVIDER_LOCK = threading.Lock()
_LAST_PROVIDER_CALL: dict[str, float] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ssl_context():
    import ssl

    return ssl.create_default_context(cafile=certifi.where())


def _pace(provider: str, minimum_interval_seconds: float) -> None:
    if minimum_interval_seconds <= 0:
        return
    with _PROVIDER_LOCK:
        now = time.monotonic()
        previous = _LAST_PROVIDER_CALL.get(provider, 0.0)
        wait_for = minimum_interval_seconds - (now - previous)
        if wait_for > 0:
            time.sleep(wait_for)
        _LAST_PROVIDER_CALL[provider] = time.monotonic()


def _request_bytes(
    url: str,
    *,
    accept: str = "application/json",
    user_agent: str | None = None,
    provider: str = "generic",
    minimum_interval_seconds: float = 0.0,
    retries: int = 2,
    cache_ttl_seconds: int = 0,
) -> bytes:
    if cache_ttl_seconds > 0:
        with _CACHE_LOCK:
            cached = _CACHE.get(url)
            if cached and (time.time() - cached[0]) <= cache_ttl_seconds:
                return cached[1]

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        _pace(provider, minimum_interval_seconds)
        request = Request(
            url,
            headers={
                "User-Agent": user_agent or GENERIC_USER_AGENT,
                "Accept": accept,
                "Accept-Encoding": "identity",
                "From": "mielechris@users.noreply.github.com",
            },
        )
        try:
            with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS, context=_ssl_context()) as response:
                body = response.read()
            if cache_ttl_seconds > 0:
                with _CACHE_LOCK:
                    _CACHE[url] = (time.time(), body)
            return body
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else 1.5 * (2**attempt)
            except (TypeError, ValueError):
                delay = 1.5 * (2**attempt)
            time.sleep(min(max(delay, 1.0), 8.0))
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(min(1.0 * (2**attempt), 4.0))
    if last_error:
        raise last_error
    raise RuntimeError("Provider request failed without an exception")


def _json_request(**kwargs) -> Any:
    return json.loads(_request_bytes(**kwargs).decode("utf-8"))


def _iso_gdelt_timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None



def fetch_google_news_rss(
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    query = str(
        params.get("query") or ""
    ).strip()

    if len(query) < 2:
        raise ValueError(
            "Google News RSS requires query"
        )

    limit = max(
        1,
        min(
            int(params.get("limit") or 10),
            50,
        ),
    )

    qs = urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )

    url = (
        "https://news.google.com/rss/search?"
        + qs
    )

    body = _request_bytes(
        url,
        accept=(
            "application/rss+xml,"
            "application/xml,text/xml"
        ),
        provider="google_news_rss",
        minimum_interval_seconds=0.75,
        retries=2,
        cache_ttl_seconds=15 * 60,
    )

    root = ET.fromstring(body)

    output: list[dict[str, Any]] = []

    for item in root.findall(
        ".//channel/item"
    )[:limit]:
        title = (
            item.findtext("title") or ""
        ).strip()

        link = (
            item.findtext("link") or ""
        ).strip()

        published = (
            item.findtext("pubDate") or ""
        ).strip()

        source_node = item.find("source")

        source = (
            (
                source_node.text or ""
            ).strip()
            if source_node is not None
            else "Google News"
        )

        if not title:
            continue

        output.append(
            {
                "source":
                    source
                    or "Google News",
                "source_type":
                    "news_aggregator",
                "evidence_type":
                    "news",
                "url":
                    link or url,
                "title":
                    title,
                "claim":
                    title,
                "timestamp":
                    published or None,
                "reliability_score":
                    0.55,
                "gap_resolution_eligible":
                    False,
                "trade_signal":
                    False,
                "trade_execution_permission":
                    False,
            }
        )

    return output


def fetch_gdelt_news(params: dict[str, Any]) -> list[dict[str, Any]]:
    query = str(params.get("query", "")).strip()
    if len(query) < 2:
        raise ValueError("GDELT source requires query")
    maxrecords = max(1, min(int(params.get("limit", 25)), 100))
    timespan = str(params.get("timespan", "24h"))
    qs = urlencode(
        {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "sort": "datedesc",
            "maxrecords": maxrecords,
            "timespan": timespan,
        }
    )
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + qs
    payload = _json_request(
        url=url,
        provider="gdelt",
        minimum_interval_seconds=2.25,
        retries=3,
        cache_ttl_seconds=15 * 60,
    )
    output: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for article in payload.get("articles", [])[:maxrecords]:
        article_url = str(article.get("url") or "").strip()
        if article_url and article_url in seen_urls:
            continue
        if article_url:
            seen_urls.add(article_url)
        output.append(
            {
                "source": article.get("domain") or "GDELT",
                "source_type": "news_aggregator",
                "evidence_type": "news",
                "url": article_url or None,
                "title": article.get("title"),
                "claim": article.get("title"),
                "timestamp": _iso_gdelt_timestamp(article.get("seendate")),
                "language": article.get("language"),
                "source_country": article.get("sourcecountry"),
                "reliability_score": 0.55,
            }
        )
    return output


def _fact_timestamp(obs: dict[str, Any]) -> str:
    return str(obs.get("filed") or obs.get("end") or "")


def fetch_sec_companyfacts(params: dict[str, Any]) -> list[dict[str, Any]]:
    cik = str(params.get("cik", "")).strip().lstrip("0")
    if not cik.isdigit():
        raise ValueError("SEC source requires numeric cik")
    cik10 = cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    payload = _json_request(
        url=url,
        user_agent=SEC_USER_AGENT,
        provider="sec",
        minimum_interval_seconds=0.2,
        retries=2,
        cache_ttl_seconds=15 * 60,
    )
    entity_name = payload.get("entityName") or str(params.get("label") or f"CIK {cik10}")
    facts = payload.get("facts", {})
    selected_tags = params.get("tags") or [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "NetIncomeLoss",
        "Assets",
        "Liabilities",
        "CashAndCashEquivalentsAtCarryingValue",
    ]
    limit = max(1, min(int(params.get("limit", 12)), 60))

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    us_gaap = facts.get("us-gaap", {})
    for tag in selected_tags:
        concept = us_gaap.get(tag)
        if not concept:
            continue
        tag_rows: list[dict[str, Any]] = []
        for unit_name, observations in concept.get("units", {}).items():
            for obs in observations:
                form = str(obs.get("form") or "")
                if form and form not in {"10-K", "10-Q", "8-K", "20-F", "40-F"}:
                    continue
                key = (tag, str(obs.get("end") or ""), str(obs.get("val")))
                if key in seen:
                    continue
                seen.add(key)
                tag_rows.append(
                    {
                        "source": "SEC EDGAR",
                        "source_type": "official",
                        "evidence_type": "fundamental",
                        "url": url,
                        "title": f"{entity_name} {tag}",
                        "claim": f"{tag}={obs.get('val')} {unit_name}",
                        "value": obs.get("val"),
                        "unit": unit_name,
                        "period_start": obs.get("start"),
                        "period_end": obs.get("end"),
                        "timestamp": obs.get("filed") or obs.get("end"),
                        "form": obs.get("form"),
                        "accession": obs.get("accn"),
                        "reliability_score": 0.98,
                    }
                )
        tag_rows.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        candidates.extend(tag_rows[:2])

    candidates.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return candidates[:limit]


def _parse_csv_row(text: str) -> dict[str, str]:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("No market-data rows returned")
    return rows[-1]


def _stooq_symbol(symbol: str) -> str:
    text = symbol.strip().lower()
    if not text:
        return text
    if "." not in text:
        return f"{text}.us"
    return text


def _yahoo_symbol(symbol: str) -> str:
    text = symbol.strip().upper()
    if text.endswith(".US"):
        return text[:-3]
    return text


def _quote_item(provider: str, symbol: str, price: float, timestamp: str | None, url: str) -> dict[str, Any]:
    return {
        "source": provider,
        "source_type": "market_data",
        "evidence_type": "market_data",
        "url": url,
        "title": f"{symbol.upper()} market snapshot",
        "claim": f"{symbol.upper()} price={price}",
        "timestamp": timestamp,
        "value": price,
        "symbol": symbol.upper(),
        "reliability_score": 0.78,
    }


def _fetch_stooq_current(symbol: str) -> tuple[float, str | None, str]:
    normalized = _stooq_symbol(symbol)
    url = f"https://stooq.com/q/l/?s={quote_plus(normalized)}&f=sd2t2ohlcv&h&e=csv"
    text = _request_bytes(
        url,
        accept="text/csv",
        provider="stooq",
        minimum_interval_seconds=0.25,
        retries=1,
        cache_ttl_seconds=5 * 60,
    ).decode("utf-8-sig")
    row = _parse_csv_row(text)
    close = float(row.get("Close") or row.get("close") or "nan")
    date = row.get("Date") or row.get("date")
    time_value = row.get("Time") or row.get("time")
    timestamp = f"{date}T{time_value}Z" if date and time_value else date
    return close, timestamp, url


def _fetch_stooq_history(symbol: str) -> tuple[float, str | None, str]:
    normalized = _stooq_symbol(symbol)
    url = f"https://stooq.com/q/d/l/?s={quote_plus(normalized)}&i=d"
    text = _request_bytes(
        url,
        accept="text/csv",
        provider="stooq",
        minimum_interval_seconds=0.25,
        retries=1,
        cache_ttl_seconds=5 * 60,
    ).decode("utf-8-sig")
    row = _parse_csv_row(text)
    close = float(row.get("Close") or row.get("close") or "nan")
    return close, row.get("Date") or row.get("date"), url


def _fetch_yahoo_chart(symbol: str) -> tuple[float, str | None, str]:
    normalized = _yahoo_symbol(symbol)
    if not normalized:
        raise ValueError("Ticker is required")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote_plus(normalized)}?range=5d&interval=1d"
    payload = _json_request(
        url=url,
        provider="yahoo",
        minimum_interval_seconds=0.25,
        retries=1,
        cache_ttl_seconds=5 * 60,
    )
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        raise ValueError("Yahoo chart returned no result")
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    timestamp_value = meta.get("regularMarketTime")
    if price is None:
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
        price = next((value for value in reversed(closes) if value is not None), None)
    if price is None:
        raise ValueError("Yahoo chart returned no usable price")
    timestamp = None
    if timestamp_value:
        timestamp = datetime.fromtimestamp(float(timestamp_value), tz=timezone.utc).isoformat()
    return float(price), timestamp, url


def fetch_market_quote(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip()
    if not symbol:
        return {"status": "skipped", "items": [], "current_price": None, "error": None, "provider": None}

    errors: list[str] = []
    for provider_name, fetcher in (
        ("Stooq", _fetch_stooq_current),
        ("Stooq", _fetch_stooq_history),
        ("Yahoo Finance", _fetch_yahoo_chart),
    ):
        try:
            price, timestamp, url = fetcher(symbol)
            if price != price:  # NaN guard
                raise ValueError("Provider returned NaN price")
            item = _quote_item(provider_name, symbol, price, timestamp, url)
            return {
                "status": "ok",
                "items": [item],
                "current_price": price,
                "error": None,
                "provider": provider_name,
            }
        except Exception as exc:
            errors.append(f"{provider_name}: {type(exc).__name__}: {exc}")

    return {
        "status": "error",
        "items": [],
        "current_price": None,
        "error": " | ".join(errors),
        "provider": None,
    }
