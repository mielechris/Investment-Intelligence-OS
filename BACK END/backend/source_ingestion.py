from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = os.getenv(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.5 contact=admin@example.invalid",
)
DEFAULT_TIMEOUT_SECONDS = 12

SOURCE_REGISTRY = {
    "sec_companyfacts": {
        "name": "SEC EDGAR Company Facts",
        "source_type": "official",
        "evidence_type": "fundamentals",
        "requires_key": False,
    },
    "noaa_alerts": {
        "name": "NOAA/NWS Active Alerts",
        "source_type": "official",
        "evidence_type": "weather",
        "requires_key": False,
    },
    "gdelt_news": {
        "name": "GDELT DOC 2.0",
        "source_type": "news_aggregator",
        "evidence_type": "news",
        "requires_key": False,
    },
    "fred_series": {
        "name": "FRED Graph CSV",
        "source_type": "official",
        "evidence_type": "macro",
        "requires_key": False,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(url: str, *, accept: str = "application/json") -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": accept,
        },
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        return response.read()


def _json_request(url: str) -> Any:
    return json.loads(_request(url).decode("utf-8"))


def _safe_fetch(fetcher, source_key: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        items = fetcher(params)
        return {
            "source_key": source_key,
            "status": "ok",
            "fetched_at": utc_now(),
            "items": items,
            "error": None,
        }
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {
            "source_key": source_key,
            "status": "error",
            "fetched_at": utc_now(),
            "items": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_sec_companyfacts(params: dict[str, Any]) -> list[dict[str, Any]]:
    cik = str(params.get("cik", "")).strip().lstrip("0")
    if not cik.isdigit():
        raise ValueError("SEC source requires numeric cik")
    cik10 = cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    payload = _json_request(url)
    entity_name = payload.get("entityName") or f"CIK {cik10}"
    facts = payload.get("facts", {})

    selected_tags = params.get("tags") or [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "NetIncomeLoss",
        "Assets",
        "Liabilities",
        "CashAndCashEquivalentsAtCarryingValue",
    ]
    limit = max(1, min(int(params.get("limit", 12)), 50))
    output: list[dict[str, Any]] = []

    us_gaap = facts.get("us-gaap", {})
    for tag in selected_tags:
        concept = us_gaap.get(tag)
        if not concept:
            continue
        for unit_name, observations in concept.get("units", {}).items():
            for obs in list(observations)[-limit:]:
                output.append(
                    {
                        "source": "SEC EDGAR",
                        "source_type": "official",
                        "evidence_type": "fundamentals",
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
                        "reliability": 0.98,
                        "freshness_window_hours": 24 * 120,
                    }
                )
    return output[-limit:]


def fetch_noaa_alerts(params: dict[str, Any]) -> list[dict[str, Any]]:
    area = str(params.get("area", "")).strip().upper()
    query = {"status": "actual"}
    if area:
        query["area"] = area
    url = "https://api.weather.gov/alerts/active?" + urlencode(query)
    payload = _json_request(url)
    limit = max(1, min(int(params.get("limit", 20)), 100))
    output = []
    for feature in payload.get("features", [])[:limit]:
        p = feature.get("properties", {})
        output.append(
            {
                "source": "NOAA/NWS",
                "source_type": "official",
                "evidence_type": "weather",
                "url": p.get("@id") or feature.get("id") or url,
                "title": p.get("headline") or p.get("event") or "NWS alert",
                "claim": p.get("description") or p.get("headline") or p.get("event"),
                "timestamp": p.get("sent") or p.get("effective") or p.get("onset"),
                "expires_at": p.get("expires"),
                "severity": p.get("severity"),
                "certainty": p.get("certainty"),
                "urgency": p.get("urgency"),
                "area_desc": p.get("areaDesc"),
                "reliability": 0.98,
                "freshness_window_hours": 24,
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
    payload = _json_request(url)
    output = []
    for article in payload.get("articles", [])[:maxrecords]:
        output.append(
            {
                "source": article.get("domain") or "GDELT",
                "source_type": "news_aggregator",
                "evidence_type": "news",
                "url": article.get("url"),
                "title": article.get("title"),
                "claim": article.get("title"),
                "timestamp": article.get("seendate"),
                "language": article.get("language"),
                "source_country": article.get("sourcecountry"),
                "reliability": 0.55,
                "freshness_window_hours": 48,
            }
        )
    return output


def fetch_fred_series(params: dict[str, Any]) -> list[dict[str, Any]]:
    series_id = str(params.get("series_id", "")).strip().upper()
    if not series_id:
        raise ValueError("FRED source requires series_id")
    limit = max(1, min(int(params.get("limit", 30)), 500))
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={quote_plus(series_id)}"
    text = _request(url, accept="text/csv").decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    output = []
    for row in rows[-limit:]:
        value = row.get(series_id)
        if value in (None, ".", ""):
            continue
        output.append(
            {
                "source": "Federal Reserve Bank of St. Louis / FRED",
                "source_type": "official",
                "evidence_type": "macro",
                "url": url,
                "title": series_id,
                "claim": f"{series_id}={value}",
                "value": value,
                "timestamp": row.get("observation_date") or row.get("DATE"),
                "reliability": 0.97,
                "freshness_window_hours": int(params.get("freshness_window_hours", 24 * 45)),
            }
        )
    return output


FETCHERS = {
    "sec_companyfacts": fetch_sec_companyfacts,
    "noaa_alerts": fetch_noaa_alerts,
    "gdelt_news": fetch_gdelt_news,
    "fred_series": fetch_fred_series,
}


def ingest_sources(requests: list[dict[str, Any]]) -> dict[str, Any]:
    source_results = []
    all_items: list[dict[str, Any]] = []
    for request in requests:
        source_key = str(request.get("source", "")).strip()
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        fetcher = FETCHERS.get(source_key)
        if not fetcher:
            source_results.append(
                {
                    "source_key": source_key,
                    "status": "error",
                    "fetched_at": utc_now(),
                    "items": [],
                    "error": "Unknown source",
                }
            )
            continue
        result = _safe_fetch(fetcher, source_key, params)
        source_results.append(result)
        all_items.extend(result["items"])

    return {
        "fetched_at": utc_now(),
        "requested_sources": len(requests),
        "successful_sources": sum(1 for result in source_results if result["status"] == "ok"),
        "failed_sources": sum(1 for result in source_results if result["status"] != "ok"),
        "evidence_items": all_items,
        "source_results": source_results,
    }
