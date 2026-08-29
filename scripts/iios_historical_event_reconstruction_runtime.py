#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, time as dt_time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode

import iios_historical_event_reconstruction as core

DOC_SEARCH_START = date(2017, 1, 1)
EVENT_ANALOGS_PER_SYMBOL = 4
SYSTEM_CURL = Path("/usr/bin/curl")
USER_AGENT = "Investment-Intelligence-OS/1.0 historical-event-provider-mesh"
MESH_CACHE_SECONDS_CURRENT = 30 * 60
MESH_CACHE_SECONDS_HISTORICAL = 180 * 24 * 60 * 60


def _window(center: date, span_days: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime.combine(center - timedelta(days=span_days), dt_time(0, 0, 0), tzinfo=timezone.utc)
    requested_end = datetime.combine(center + timedelta(days=span_days), dt_time(23, 59, 59), tzinfo=timezone.utc)
    end = min(requested_end, now)
    if start > end:
        start = end - timedelta(days=max(1, span_days * 2))
    return start, end


def _bounded_gdelt_url(symbol: str, label: str, center: date, span_days: int) -> str:
    start_dt, end_dt = _window(center, span_days)
    start_dt = max(start_dt, datetime.combine(DOC_SEARCH_START, dt_time(0, 0, 0), tzinfo=timezone.utc))
    if start_dt > end_dt:
        start_dt = end_dt
    params = {
        "query": core._query_for(symbol, label),
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "maxrecords": "40",
        "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end_dt.strftime("%Y%m%d%H%M%S"),
    }
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(params)


def _google_news_url(symbol: str, label: str, center: date, span_days: int) -> str:
    start_dt, end_dt = _window(center, span_days)
    # Google News before:/after: are day-granularity search operators. Widen by
    # one day at the query boundary, then verify every returned pubDate against
    # the exact governed window before accepting the article.
    after = (start_dt.date() - timedelta(days=1)).isoformat()
    before = (end_dt.date() + timedelta(days=1)).isoformat()
    base_query = core._query_for(symbol, label)
    query = f"{base_query} after:{after} before:{before}"
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urlencode(params)


def _system_curl_text(url: str) -> str:
    command = str(SYSTEM_CURL if SYSTEM_CURL.exists() else "curl")
    last_detail = "curl failed"
    for attempt in range(2):
        result = subprocess.run(
            [
                command,
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--connect-timeout",
                "8",
                "--max-time",
                "35",
                "--user-agent",
                USER_AGENT,
                url,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        last_detail = (result.stderr or result.stdout or "curl failed").strip()[:800]
        if attempt == 0:
            time.sleep(0.4)
    raise RuntimeError(f"system curl failed: {last_detail}")


def _cache_key(provider: str, url: str) -> str:
    return hashlib.sha256(f"{provider}|{url}".encode("utf-8")).hexdigest()[:28]


def _read_json(path: Path) -> dict[str, Any]:
    return core._read_json(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    core._atomic_write(path, payload)


def _normalize_gdelt(text: str) -> list[dict[str, Any]]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("GDELT returned non-object JSON")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for article in core._rows(value.get("articles")):
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        if not title:
            continue
        key = url or title.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "title": title,
            "url": url or None,
            "domain": article.get("domain"),
            "seen_at": article.get("seendate"),
            "language": article.get("language"),
            "source_country": article.get("sourcecountry"),
            "provider": "GDELT_DOC_2",
        })
    return output


def _normalize_google_rss(text: str, start_dt: datetime, end_dt: datetime) -> list[dict[str, Any]]:
    root = ET.fromstring(text)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        source_node = item.find("source")
        source = (source_node.text or "").strip() if source_node is not None and source_node.text else None
        if not title or not pub_raw:
            continue
        try:
            published = parsedate_to_datetime(pub_raw)
        except (TypeError, ValueError, OverflowError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        published = published.astimezone(timezone.utc)
        # Critical truthfulness gate: search engines may return stale/out-of-range
        # results. Only accept evidence whose actual published timestamp is inside
        # the governed event window.
        if published < start_dt or published > end_dt:
            continue
        key = link or title.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "title": title,
            "url": link or None,
            "domain": source,
            "seen_at": published.isoformat(),
            "language": "English",
            "source_country": None,
            "provider": "GOOGLE_NEWS_RSS",
        })
    return output


def _provider_cached_fetch(
    *,
    provider: str,
    url: str,
    event_dir: Path,
    current: bool,
    parser,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache_dir = event_dir / "provider-mesh-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{_cache_key(provider, url)}.json"
    ttl = MESH_CACHE_SECONDS_CURRENT if current else MESH_CACHE_SECONDS_HISTORICAL
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) <= ttl:
        payload = _read_json(cache_path)
        return core._rows(payload.get("articles")), {
            "provider": provider,
            "status": "OK",
            "cache_hit": True,
            "error": None,
            "url": url,
        }
    try:
        text = _system_curl_text(url)
        articles = parser(text)
        _write_json(cache_path, {
            "generated_at": core._utc_now(),
            "provider": provider,
            "url": url,
            "articles": articles,
        })
        return articles, {
            "provider": provider,
            "status": "OK" if articles else "NO_MATCHING_ARTICLES",
            "cache_hit": False,
            "error": None,
            "url": url,
        }
    except Exception as exc:  # noqa: BLE001 - provider failover is intentional
        if cache_path.exists():
            payload = _read_json(cache_path)
            cached = core._rows(payload.get("articles"))
            if cached:
                return cached, {
                    "provider": provider,
                    "status": "STALE_VERIFIED_CACHE",
                    "cache_hit": True,
                    "error": f"{type(exc).__name__}: {exc}"[:800],
                    "url": url,
                }
        return [], {
            "provider": provider,
            "status": "PROVIDER_ERROR",
            "cache_hit": False,
            "error": f"{type(exc).__name__}: {exc}"[:800],
            "url": url,
        }


def _fetch_articles_mesh(
    *,
    symbol: str,
    label: str,
    center: date,
    event_dir: Path,
    span_days: int = 2,
    current: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start_dt, end_dt = _window(center, span_days)
    attempts: list[dict[str, Any]] = []

    if center >= DOC_SEARCH_START:
        gdelt_url = _bounded_gdelt_url(symbol, label, center, span_days)
        gdelt_articles, gdelt_meta = _provider_cached_fetch(
            provider="GDELT_DOC_2",
            url=gdelt_url,
            event_dir=event_dir,
            current=current,
            parser=_normalize_gdelt,
        )
        attempts.append(gdelt_meta)
        if gdelt_articles:
            return gdelt_articles, {
                **gdelt_meta,
                "provider_mesh": True,
                "attempts": attempts,
                "coverage_contract": "GDELT_DOC_FIXED_SEARCH_COVERAGE_FROM_2017_01_01",
            }
    else:
        attempts.append({
            "provider": "GDELT_DOC_2",
            "status": "OUTSIDE_PROVIDER_COVERAGE",
            "cache_hit": False,
            "error": None,
            "coverage_start": DOC_SEARCH_START.isoformat(),
        })

    google_url = _google_news_url(symbol, label, center, span_days)
    google_articles, google_meta = _provider_cached_fetch(
        provider="GOOGLE_NEWS_RSS",
        url=google_url,
        event_dir=event_dir,
        current=current,
        parser=lambda text: _normalize_google_rss(text, start_dt, end_dt),
    )
    attempts.append(google_meta)
    if google_articles:
        return google_articles, {
            **google_meta,
            "provider_mesh": True,
            "attempts": attempts,
            "coverage_contract": "RESULT_PUBLISHED_DATE_VERIFIED_PER_WINDOW_NO_GLOBAL_CORPUS_START_CLAIM",
        }

    errors = [str(row.get("error")) for row in attempts if row.get("error")]
    any_reachable = any(row.get("status") in {"OK", "NO_MATCHING_ARTICLES"} for row in attempts)
    return [], {
        "provider": "EVENT_PROVIDER_MESH",
        "status": "NO_GOVERNED_EVENT_EVIDENCE" if any_reachable else "PROVIDER_MESH_ERROR",
        "cache_hit": False,
        "error": " | ".join(errors)[:800] if errors else None,
        "provider_mesh": True,
        "attempts": attempts,
        "coverage_contract": "NEVER_INFER_EVENT_EVIDENCE_WHEN_ALL_PROVIDERS_ARE_EMPTY_OR_UNAVAILABLE",
    }


def _eligible_event_analogs(study: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_analogs = core._rows(study.get("analogs"))
    inside: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    for analog in all_analogs:
        analog_date = core._parse_date(analog.get("date"))
        if analog_date is not None and analog_date >= DOC_SEARCH_START:
            inside.append(analog)
        else:
            outside.append(analog)
    # Prefer GDELT-compatible dates, but do not discard older price analogs: the
    # Google News fallback may still surface date-verified historical evidence.
    ordered = inside + outside
    selected = ordered[:EVENT_ANALOGS_PER_SYMBOL]
    return selected, {
        "price_analogs_available": len(all_analogs),
        "inside_doc_corpus": len(inside),
        "outside_doc_corpus": len(outside),
        "selected_for_event_reconstruction": len(selected),
        "selection_policy": "PREFER_GDELT_COVERED_ANALOGS_THEN_GOOGLE_NEWS_DATE_VERIFIED_FALLBACK",
        "doc_search_start": DOC_SEARCH_START.isoformat(),
    }


def _reconstruct_study(study: dict[str, Any], event_dir: Path) -> dict[str, Any]:
    selected, selection = _eligible_event_analogs(study)
    scoped = dict(study)
    scoped["analogs"] = selected
    result = _ORIGINAL_RECONSTRUCT_STUDY(scoped, event_dir)
    result["event_analog_selection"] = selection
    result["provider_mesh_policy"] = "GDELT_THEN_GOOGLE_NEWS_RSS_DATE_VERIFIED"
    return result


_ORIGINAL_RECONSTRUCT_STUDY = core.reconstruct_study


def install_runtime_patch() -> None:
    core.MIN_GDELT_DATE = DOC_SEARCH_START
    core.ANALOGS_PER_SYMBOL = EVENT_ANALOGS_PER_SYMBOL
    core._gdelt_url = _bounded_gdelt_url
    core._fetch_articles = _fetch_articles_mesh
    core.reconstruct_study = _reconstruct_study


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Batch 10J with a governed multi-provider historical-event evidence mesh.")
    parser.add_argument("--historical-dir", default=str(core.DEFAULT_HISTORICAL_DIR))
    parser.add_argument("--event-dir", default=str(core.DEFAULT_EVENT_DIR))
    parser.add_argument("--symbols-per-cycle", type=int, default=1)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    install_runtime_patch()
    payload = core.run_cycle(
        historical_dir=Path(args.historical_dir).expanduser(),
        event_dir=Path(args.event_dir).expanduser(),
        symbols_per_cycle=max(1, min(args.symbols_per_cycle, 8)),
    )
    output = payload if args.stdout else {
        "status": payload.get("status"),
        "processed": (payload.get("cycle") or {}).get("processed_symbols"),
        "symbols_ready": (payload.get("research_summary") or {}).get("symbols_ready"),
        "current_contexts_ready": (payload.get("research_summary") or {}).get("current_contexts_ready"),
        "analog_contexts_ready": (payload.get("research_summary") or {}).get("analog_contexts_ready"),
        "doc_search_start": DOC_SEARCH_START.isoformat(),
        "provider_mesh": "GDELT_DOC_2_THEN_GOOGLE_NEWS_RSS_DATE_VERIFIED",
        "live_execution": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
