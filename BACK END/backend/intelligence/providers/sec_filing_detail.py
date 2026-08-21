import html
import os
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from intelligence.models import EvidenceItem


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)


def _sec_user_agent() -> str:
    value = os.getenv("SEC_USER_AGENT", "").strip()
    if not value:
        raise RuntimeError("SEC_USER_AGENT is required for SEC filing enrichment")
    return value


def html_to_text(document: str, *, max_chars: int = 50000) -> str:
    parser = _VisibleTextParser()
    parser.feed(document)
    text = " ".join(parser.parts)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:max_chars]


def _candidate_document_links(index_html: str, base_url: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', index_html, flags=re.IGNORECASE)
    links: list[str] = []
    for href in hrefs:
        lower = href.lower()
        if not lower.endswith((".htm", ".html")):
            continue
        if "ixviewer" in lower or "javascript:" in lower:
            continue
        absolute = urljoin(base_url, href)
        if absolute not in links:
            links.append(absolute)
    return links


def classify_ipo_filing(detail: dict) -> dict:
    """Conservatively classify enriched SEC text before spending an agent call."""
    text = str(detail.get("filing_text", "")).lower()
    if not text:
        return {
            "classification": "uncertain",
            "likely_ipo": None,
            "signals": [],
            "reason": "No filing text available for qualification.",
        }

    strong_positive = [
        "this is our initial public offering",
        "initial public offering of",
        "our initial public offering",
        "no public market currently exists",
        "no public market for our",
        "we have applied to list",
        "we intend to apply to list",
    ]
    strong_non_ipo = [
        "exchange-traded fund",
        "exchange traded fund",
        "etf shares",
    ]

    positive_hits = [marker for marker in strong_positive if marker in text]
    negative_hits = [marker for marker in strong_non_ipo if marker in text]

    if positive_hits:
        return {
            "classification": "likely_ipo",
            "likely_ipo": True,
            "signals": positive_hits,
            "reason": "Filing contains explicit initial-offering or first-listing language.",
        }

    if negative_hits:
        return {
            "classification": "likely_non_ipo",
            "likely_ipo": False,
            "signals": negative_hits,
            "reason": "Filing appears to be an ETF registration rather than an operating-company IPO.",
        }

    return {
        "classification": "uncertain",
        "likely_ipo": None,
        "signals": [],
        "reason": "No decisive IPO or ETF marker found; specialist review is still required.",
    }


def enrich_sec_filing(item: EvidenceItem) -> dict:
    if not item.url:
        return {"available": False, "reason": "Evidence item has no SEC filing URL."}

    headers = {
        "User-Agent": _sec_user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }
    with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
        index_response = client.get(item.url)
        index_response.raise_for_status()
        index_url = str(index_response.url)
        index_text = html_to_text(index_response.text, max_chars=12000)

        candidates = _candidate_document_links(index_response.text, index_url)
        primary_url = candidates[0] if candidates else index_url
        primary_text = index_text

        if primary_url != index_url:
            primary_response = client.get(primary_url)
            primary_response.raise_for_status()
            primary_url = str(primary_response.url)
            primary_text = html_to_text(primary_response.text, max_chars=50000)

    detail = {
        "available": True,
        "index_url": index_url,
        "primary_document_url": primary_url,
        "index_text": index_text,
        "filing_text": primary_text,
        "filing_text_truncated": len(primary_text) >= 50000,
    }
    detail["ipo_qualification"] = classify_ipo_filing(detail)
    return detail
