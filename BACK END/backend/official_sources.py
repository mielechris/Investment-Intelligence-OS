from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree

from provider_hardening import _request_bytes


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _page_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _keyword_windows(text: str, keywords: list[str], max_items: int, window_chars: int) -> list[tuple[str, str]]:
    lower = text.lower()
    hits: list[tuple[int, str]] = []
    for keyword in keywords:
        idx = lower.find(keyword.lower())
        if idx >= 0:
            hits.append((idx, keyword))
    hits.sort(key=lambda item: item[0])

    results: list[tuple[str, str]] = []
    used_ranges: list[tuple[int, int]] = []
    for idx, keyword in hits:
        start = max(0, idx - window_chars // 3)
        end = min(len(text), idx + (window_chars * 2 // 3))
        if any(abs(start - previous_start) < 180 for previous_start, _ in used_ranges):
            continue
        snippet = text[start:end].strip()
        if len(snippet) < 80:
            continue
        used_ranges.append((start, end))
        results.append((keyword, snippet))
        if len(results) >= max_items:
            break

    if not results and text:
        results.append(("page", text[:window_chars].strip()))
    return results


def fetch_official_web(params: dict[str, Any]) -> list[dict[str, Any]]:
    url = str(params.get("url", "")).strip()
    if not url.startswith("https://"):
        raise ValueError("official_web requires an https URL")
    label = str(params.get("label") or url).strip()
    keywords = params.get("keywords") if isinstance(params.get("keywords"), list) else []
    keywords = [str(item).strip() for item in keywords if str(item).strip()]
    max_items = max(1, min(int(params.get("limit", 4)), 8))
    window_chars = max(300, min(int(params.get("window_chars", 900)), 1800))
    reliability = max(0.0, min(float(params.get("reliability_score", 0.93)), 1.0))
    evidence_type = str(params.get("evidence_type", "fundamental")).strip() or "fundamental"

    html = _request_bytes(
        url,
        accept="text/html,application/xhtml+xml",
        provider="official_web",
        minimum_interval_seconds=0.35,
        retries=2,
        cache_ttl_seconds=30 * 60,
    ).decode("utf-8", errors="ignore")
    text = _page_text(html)
    observed_at = utc_now()
    output: list[dict[str, Any]] = []
    for keyword, snippet in _keyword_windows(text, keywords, max_items, window_chars):
        output.append(
            {
                "source": label,
                "source_type": "company",
                "evidence_type": evidence_type,
                "url": url,
                "title": f"{label}: {keyword}",
                "claim": snippet,
                "timestamp": observed_at,
                "reliability_score": reliability,
            }
        )
    return output


def _rss_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def fetch_google_news_rss(params: dict[str, Any]) -> list[dict[str, Any]]:
    query = str(params.get("query", "")).strip()
    if len(query) < 2:
        raise ValueError("google_news_rss requires query")
    limit = max(1, min(int(params.get("limit", 8)), 20))
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    xml_bytes = _request_bytes(
        url,
        accept="application/rss+xml,application/xml,text/xml",
        provider="google_news",
        minimum_interval_seconds=0.5,
        retries=2,
        cache_ttl_seconds=15 * 60,
    )
    root = ElementTree.fromstring(xml_bytes)
    output: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        source_node = item.find("source")
        source = (source_node.text or "Google News") if source_node is not None else "Google News"
        output.append(
            {
                "source": source.strip(),
                "source_type": "news_aggregator",
                "evidence_type": "news",
                "url": (item.findtext("link") or url).strip(),
                "title": title,
                "claim": title,
                "timestamp": _rss_timestamp(item.findtext("pubDate")),
                "reliability_score": 0.60,
            }
        )
        if len(output) >= limit:
            break
    return output
