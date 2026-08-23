from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin

from provider_hardening import _request_bytes

MICRON_IR_FILINGS_URL = "https://investors.micron.com/sec-filings"
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
            text = re.sub(r"\s+", " ", data).strip()
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


def _accession_from_text(text: str) -> str | None:
    match = re.search(r"\b\d{10}-\d{2}-\d{6}\b", text)
    return match.group(0) if match else None


def parse_micron_ir_filings(html: str, *, ticker: str = "MU") -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(html)
    output: list[dict[str, Any]] = []
    for row in parser.rows:
        cells = [str(cell).strip() for cell in row.get("cells") or []]
        if len(cells) < 3:
            continue
        # The Micron IR table is: Filing date | Form | Description | Filer | View.
        filing_date = cells[0]
        form = cells[1].upper()
        if form not in IR_FORMS:
            continue
        description = cells[2] if len(cells) >= 3 else ""
        filer = cells[3] if len(cells) >= 4 and cells[3] else None
        links = [urljoin(MICRON_IR_FILINGS_URL, str(link)) for link in row.get("links") or []]
        source_url = links[0] if links else MICRON_IR_FILINGS_URL
        accession = _accession_from_text(" ".join(cells + links))

        if form in {"4", "4/A"}:
            output.append(
                {
                    "record_kind": "FORM4_FILING_METADATA",
                    "form": form,
                    "ticker": ticker,
                    "reporting_owner": filer,
                    "reporting_owner_role": "Reporting owner (role unavailable in IR filing index)",
                    "filing_date": filing_date,
                    "transaction_nature": "FORM4_TRANSACTION_DETAIL_UNAVAILABLE",
                    "accession_number": accession,
                    "source_url": source_url,
                    "source_name": "Micron Investor Relations SEC Filings",
                    "source_type": "company",
                    "reliability_score": 0.93,
                    "admission_status": "CONTEXT_ONLY",
                    "transaction_detail_complete": False,
                    "fallback_source": True,
                    "description": description,
                    "paper_mode": True,
                    "trade_execution_permission": False,
                }
            )
        elif form == "144":
            output.append(
                {
                    "record_kind": "FORM144_NOTICE",
                    "form": form,
                    "ticker": ticker,
                    "reporting_owner": filer,
                    "filing_date": filing_date,
                    "transaction_nature": "NOTICE_OF_PROPOSED_SALE",
                    "accession_number": accession,
                    "source_url": source_url,
                    "source_name": "Micron Investor Relations SEC Filings",
                    "source_type": "company",
                    "reliability_score": 0.93,
                    "admission_status": "CONTEXT_ONLY",
                    "transaction_detail_complete": False,
                    "fallback_source": True,
                    "description": description,
                    "paper_mode": True,
                    "trade_execution_permission": False,
                }
            )
        else:
            output.append(
                {
                    "record_kind": "BENEFICIAL_OWNERSHIP_FILING",
                    "form": form,
                    "ticker": ticker,
                    "filing_date": filing_date,
                    "accession_number": accession,
                    "source_url": source_url,
                    "source_name": "Micron Investor Relations SEC Filings",
                    "source_type": "company",
                    "reliability_score": 0.93,
                    "admission_status": "ADMITTED",
                    "transaction_detail_complete": False,
                    "fallback_source": True,
                    "description": description,
                    "paper_mode": True,
                    "trade_execution_permission": False,
                }
            )
    return output


def fetch_micron_ir_insider_records(ticker: str) -> list[dict[str, Any]]:
    symbol = str(ticker or "").strip().upper().removesuffix(".US")
    if symbol != "MU":
        raise RuntimeError(f"No official-company insider fallback configured for {symbol}")
    html = _request_bytes(
        MICRON_IR_FILINGS_URL,
        accept="text/html,application/xhtml+xml",
        provider="micron_ir_insider",
        minimum_interval_seconds=0.5,
        retries=2,
        cache_ttl_seconds=15 * 60,
    ).decode("utf-8", errors="ignore")
    records = parse_micron_ir_filings(html, ticker=symbol)
    if not records:
        raise RuntimeError("Micron IR filing index returned no insider/ownership rows")
    return records


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
