from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin

from provider_hardening import _request_bytes

MICRON_IR_BASE_URL = "https://investors.micron.com/"
MICRON_IR_FILINGS_URL = "https://investors.micron.com/sec-filings"
# Micron's investor-relations site can return a shell page at the short URL. The
# mobile/static table view is much more reliable for server-side research clients.
MICRON_IR_FILINGS_URLS = [
    "https://investors.micron.com/index.php/sec-filings?field_nir_sec_cik_target_id=&field_nir_sec_date_filed_value=&items_per_page=50&items_per_page_toggle=1&mobile=1&order=field_nir_sec_date_filed&sort=desc",
    "https://investors.micron.com/sec-filings?field_nir_sec_cik_target_id=&field_nir_sec_date_filed_value=&items_per_page=50&items_per_page_toggle=1&mobile=1&order=field_nir_sec_date_filed&sort=desc",
    MICRON_IR_FILINGS_URL,
]
IR_FORMS = {"4", "4/A", "144", "SCHEDULE 13G", "SCHEDULE 13G/A", "SC 13G", "SC 13G/A", "SC 13D", "SC 13D/A"}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._cell_parts: list[str] = []
        self._links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._in_row = True
            self._cells = []
            self._links = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell_parts = []
        elif tag == "a" and self._in_row:
            href = dict(attrs).get("href")
            if href:
                self._links.append(href)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            text = re.sub(r"\s+", " ", unescape(data)).strip()
            if text:
                self._cell_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            self._cells.append(" ".join(self._cell_parts).strip())
            self._cell_parts = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._cells:
                self.rows.append({"cells": list(self._cells), "links": list(self._links)})
            self._in_row = False
            self._cells = []
            self._links = []


class _VisibleTextParser(HTMLParser):
    """Fallback for IR templates that expose filing rows outside literal <table> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "noscript"}:
            self._skip += 1
        elif lower == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        elif lower in {"tr", "td", "th", "div", "li", "p", "br"} and self._skip == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        elif lower in {"tr", "td", "th", "div", "li", "p"} and self._skip == 0:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            text = re.sub(r"\s+", " ", unescape(data)).strip()
            if text:
                self.parts.append(text)


def _accession_from_text(text: str) -> str | None:
    match = re.search(r"\b\d{10}-\d{2}-\d{6}\b", text)
    return match.group(0) if match else None


def _record_from_fields(
    filing_date: str,
    form: str,
    description: str,
    filer: str | None,
    links: list[str],
    *,
    ticker: str,
) -> dict[str, Any] | None:
    normalized_form = re.sub(r"\s+", " ", form.upper()).strip()
    if normalized_form not in IR_FORMS:
        return None
    absolute_links = [urljoin(MICRON_IR_BASE_URL, str(link)) for link in links]
    source_url = absolute_links[0] if absolute_links else MICRON_IR_FILINGS_URL
    accession = _accession_from_text(" ".join([filing_date, normalized_form, description, filer or ""] + absolute_links))

    common = {
        "form": normalized_form,
        "ticker": ticker,
        "filing_date": filing_date,
        "accession_number": accession,
        "source_url": source_url,
        "source_name": "Micron Investor Relations SEC Filings",
        "source_type": "company",
        "reliability_score": 0.93,
        "transaction_detail_complete": False,
        "fallback_source": True,
        "description": description,
        "paper_mode": True,
        "trade_execution_permission": False,
    }
    if normalized_form in {"4", "4/A"}:
        return {
            **common,
            "record_kind": "FORM4_FILING_METADATA",
            "reporting_owner": filer,
            "reporting_owner_role": "Reporting owner (role unavailable in IR filing index)",
            "transaction_nature": "FORM4_TRANSACTION_DETAIL_UNAVAILABLE",
            "admission_status": "CONTEXT_ONLY",
        }
    if normalized_form == "144":
        return {
            **common,
            "record_kind": "FORM144_NOTICE",
            "reporting_owner": filer,
            "transaction_nature": "NOTICE_OF_PROPOSED_SALE",
            "admission_status": "CONTEXT_ONLY",
        }
    return {
        **common,
        "record_kind": "BENEFICIAL_OWNERSHIP_FILING",
        "admission_status": "ADMITTED",
    }


def _parse_table_rows(html: str, *, ticker: str) -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(html)
    output: list[dict[str, Any]] = []
    for row in parser.rows:
        cells = [str(cell).strip() for cell in row.get("cells") or []]
        if len(cells) < 3:
            continue
        record = _record_from_fields(
            cells[0],
            cells[1],
            cells[2] if len(cells) >= 3 else "",
            cells[3] if len(cells) >= 4 and cells[3] else None,
            list(row.get("links") or []),
            ticker=ticker,
        )
        if record:
            output.append(record)
    return output


def _parse_visible_text_rows(html: str, *, ticker: str) -> list[dict[str, Any]]:
    """Conservative fallback parser for Micron IR rendering variants.

    It only creates records when a filing date and an allowed form occur together in a
    short visible-text window. It never infers Form 4 transaction direction.
    """
    parser = _VisibleTextParser()
    parser.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    date_pattern = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}$", re.I)
    output: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        if not date_pattern.match(line):
            continue
        window = lines[idx : idx + 8]
        form_idx = None
        form_value = None
        for offset, candidate in enumerate(window[1:], start=1):
            normalized = re.sub(r"\s+", " ", candidate.upper()).strip()
            if normalized in IR_FORMS:
                form_idx = offset
                form_value = normalized
                break
        if form_idx is None or form_value is None:
            continue
        after = window[form_idx + 1 :]
        description = after[0] if after else ""
        filer = None
        if len(after) >= 2:
            candidate = after[1]
            if candidate.lower() not in {"view", "view html"} and not _accession_from_text(candidate):
                filer = candidate
        record = _record_from_fields(line, form_value, description, filer, parser.links, ticker=ticker)
        if record:
            output.append(record)
    return output


def parse_micron_ir_filings(html: str, *, ticker: str = "MU") -> list[dict[str, Any]]:
    output = _parse_table_rows(html, ticker=ticker)
    if output:
        return output
    return _parse_visible_text_rows(html, ticker=ticker)


def fetch_micron_ir_insider_records(ticker: str) -> list[dict[str, Any]]:
    symbol = str(ticker or "").strip().upper().removesuffix(".US")
    if symbol != "MU":
        raise RuntimeError(f"No official-company insider fallback configured for {symbol}")
    errors: list[str] = []
    for url in MICRON_IR_FILINGS_URLS:
        try:
            html = _request_bytes(
                url,
                accept="text/html,application/xhtml+xml",
                provider="micron_ir_insider",
                minimum_interval_seconds=0.5,
                retries=2,
                cache_ttl_seconds=15 * 60,
            ).decode("utf-8", errors="ignore")
            records = parse_micron_ir_filings(html, ticker=symbol)
            if records:
                for record in records:
                    record["fallback_index_url"] = url
                return records
            errors.append(f"{url}: no insider/ownership rows")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Micron IR filing index returned no insider/ownership rows; " + " | ".join(errors))


def install_insider_fallback(module: Any) -> None:
    primary_fetch: Callable[..., list[dict[str, Any]]] = module.fetch_public_insider_records
    primary_auto = module.auto_capture_insider

    def fetch_with_fallback(ticker: str, *, max_form4_filings: int = 12) -> list[dict[str, Any]]:
        try:
            return primary_fetch(ticker, max_form4_filings=max_form4_filings)
        except Exception as primary_error:
            records = fetch_micron_ir_insider_records(ticker)
            for record in records:
                record["direct_sec_error"] = f"{type(primary_error).__name__}: {primary_error}"
            return records

    module.fetch_public_insider_records = fetch_with_fallback

    def auto_capture_with_provider(case_id: str) -> dict[str, Any]:
        result = primary_auto(case_id)
        if result.get("status") == "ok":
            records = module.list_objects(case_id, "insider_activity_record")
            fallback_records = [row for row in records if row.get("fallback_source")]
            if fallback_records:
                return {
                    **result,
                    "status": "fallback_ok",
                    "provider": "MICRON_IR_OFFICIAL_MIRROR",
                    "transaction_detail_complete": False,
                    "provider_note": "Direct SEC EDGAR was unavailable; official Micron IR filing index was used. Form 4 presence is captured, but buy/sell transaction detail is not inferred without the underlying filing detail.",
                }
        return result

    module.auto_capture_insider = auto_capture_with_provider
