from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


MATCHER_VERSION = "x-status-id-source-match-v1"


def _status_identity(value: Any, module) -> tuple[str | None, str | None, str | None]:
    """Return (normalized_url, status_id, author) for an X/Twitter status URL.

    xAI citations commonly use https://x.com/i/status/<id> while Grok's structured
    claim output may use https://x.com/<account>/status/<id>. They refer to the same
    post when the numeric status id matches.
    """
    normalized = module._normalize_url(value)
    if not normalized or not module._is_x_url(normalized):
        return normalized, None, None
    try:
        path = urlsplit(normalized).path.strip("/")
    except ValueError:
        return normalized, None, None
    match = re.search(r"(?:^|/)status/(\d+)(?:/|$)", path)
    if not match:
        return normalized, None, None
    status_id = match.group(1)
    parts = path.split("/")
    author = None
    if len(parts) >= 3 and parts[-2] == "status":
        candidate = parts[-3].strip().lower()
        if candidate and candidate not in {"i", "web"}:
            author = candidate
    return normalized, status_id, author


def _expanded_citation_urls(raw_claims: Any, citation_urls: set[str], module) -> set[str]:
    """Add account-form URLs only when their status id exists in xAI citations."""
    expanded = set(citation_urls)
    cited_status_ids = {
        status_id
        for url in citation_urls
        for _, status_id, _ in [_status_identity(url, module)]
        if status_id
    }
    rows = raw_claims if isinstance(raw_claims, list) else []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        requested = raw.get("source_urls") if isinstance(raw.get("source_urls"), list) else []
        for value in requested:
            normalized, status_id, _ = _status_identity(value, module)
            if normalized and status_id and status_id in cited_status_ids:
                expanded.add(normalized)
    return expanded


def _distinct_authors(urls: list[str], module) -> set[str]:
    authors: set[str] = set()
    for value in urls:
        _, _, author = _status_identity(value, module)
        if author:
            authors.add(author)
    return authors


def install_grok_status_matcher(module) -> None:
    """Teach the existing firewall xAI's canonical /i/status URL shape.

    The original firewall still decides citation admission, prompt-injection
    quarantine, confidence capping, and minimum source count. This shim only
    expands exact-match citation aliases by identical numeric X status id, then
    adds a stricter distinct-account check to prevent one account repeating itself
    from satisfying the multi-source rule.
    """
    if getattr(module, "_grok_status_matcher_installed", False):
        return
    module._grok_status_matcher_installed = True

    original_filter = module.filter_grok_claims

    def matched_filter(raw_claims: Any, citation_urls: set[str]) -> dict[str, Any]:
        expanded = _expanded_citation_urls(raw_claims, set(citation_urls or set()), module)
        result = original_filter(raw_claims, expanded)

        admitted: list[dict[str, Any]] = []
        quarantined = list(result.get("quarantined") or [])
        for item in result.get("admitted") or []:
            urls = item.get("source_urls") if isinstance(item.get("source_urls"), list) else []
            authors = _distinct_authors(urls, module)
            if len(authors) < module.MIN_ADMITTED_SOURCES:
                updated = {
                    **item,
                    "context_admitted": False,
                    "quarantine_reasons": list(item.get("quarantine_reasons") or [])
                    + ["INSUFFICIENT_INDEPENDENT_X_ACCOUNTS"],
                    "independent_account_count": len(authors),
                }
                quarantined.append(updated)
            else:
                admitted.append({**item, "independent_account_count": len(authors)})

        return {
            "admitted": admitted,
            "quarantined": quarantined,
            "admitted_count": len(admitted),
            "quarantined_count": len(quarantined),
        }

    module.filter_grok_claims = matched_filter
