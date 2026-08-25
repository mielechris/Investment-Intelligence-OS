from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any, Callable

from provider_hardening import _request_bytes

MARKETBEAT_INSIDER_URL = "https://www.marketbeat.com/stocks/NASDAQ/MU/insider-trades/"


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        lower = tag.lower()
        if lower == "tr":
            self._in_row = True
            self._cells = []
        elif lower in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._parts = []
        elif lower == "br" and self._in_cell:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            text = re.sub(r"\s+", " ", unescape(data)).strip()
            if text:
                self._parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"td", "th"} and self._in_cell:
            self._cells.append(re.sub(r"\s+", " ", " ".join(self._parts)).strip())
            self._parts = []
            self._in_cell = False
        elif lower == "tr" and self._in_row:
            if self._cells:
                self.rows.append(list(self._cells))
            self._in_row = False
            self._cells = []


def _number(text: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", str(text or ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_transaction_date(text: str) -> bool:
    return bool(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", str(text or "").strip()))


def _date_iso(text: str) -> str:
    value = str(text or "").strip()
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
    if match:
        month, day, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return value


def _is_political_trade_label(value: str) -> bool:
    """Reject congressional/political-trading rows from a corporate-insider feed.

    Some public aggregator pages place company insider transactions and congressional
    trades on the same page. Those are different datasets and must never be mixed.
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    upper = text.upper()
    political_terms = (
        " SENATE ",
        " HOUSE ",
        " SENATOR ",
        " REPRESENTATIVE ",
        " CONGRESS ",
        " CONGRESSMAN ",
        " CONGRESSWOMAN ",
    )
    padded = f" {upper} "
    if any(term in padded for term in political_terms):
        return True
    # Typical aggregator labels: "Name House (D-CA)" or "Name Senate (R-AR)".
    if re.search(r"\b(?:HOUSE|SENATE)\s*\([RID]-[A-Z]{2}\)", upper):
        return True
    return False


def parse_marketbeat_insider_rows(html: str, *, ticker: str = "MU") -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(html)
    output: list[dict[str, Any]] = []
    for cells in parser.rows:
        if len(cells) < 6:
            continue
        date, insider, side, shares_text, avg_price_text, total_text = cells[:6]
        side_upper = side.upper()
        # Header and unrelated-table guardrails. A governed transaction must have an
        # actual transaction date; labels such as "Transaction Date" cannot pass.
        if not _is_transaction_date(date):
            continue
        if "BUY" not in side_upper and "SELL" not in side_upper:
            continue
        if _is_political_trade_label(insider):
            continue

        nature = "OPEN_MARKET_PURCHASE" if "BUY" in side_upper else "OPEN_MARKET_SALE"
        shares = _number(shares_text)
        price = _number(avg_price_text)
        total = _number(total_text)
        owner = insider.strip()
        role = None
        # MarketBeat often renders name and title in the same cell.
        role_terms = (
            "CEO", "CFO", "COO", "CTO", "CAO", "CLO", "CMO",
            "DIRECTOR", "VP", "SVP", "EVP", "PRESIDENT", "OFFICER",
            "GENERAL", "COUNSEL", "CHAIR", "CHAIRMAN",
        )
        words = owner.split()
        for index, word in enumerate(words):
            if word.upper().strip(".,") in role_terms:
                role = " ".join(words[index:]).strip()
                owner = " ".join(words[:index]).strip() or owner
                break
        output.append(
            {
                "record_kind": "SECONDARY_PUBLIC_INSIDER_TRANSACTION",
                "form": "SECONDARY",
                "ticker": ticker,
                "reporting_owner": owner,
                "reporting_owner_role": role or "Role reported by secondary public source",
                "transaction_date": _date_iso(date),
                "filing_date": _date_iso(date),
                "transaction_nature": nature,
                "shares": shares,
                "price_per_share": price,
                "dollar_value": total,
                "shares_owned_after": None,
                "plan_10b5_1": None,
                "accession_number": None,
                "source_url": MARKETBEAT_INSIDER_URL,
                "source_name": "MarketBeat public insider activity",
                "source_type": "secondary_public_aggregator",
                "reliability_score": 0.72,
                "admission_status": "CONTEXT_ONLY",
                "secondary_source": True,
                "subject_scope": "CORPORATE_INSIDER",
                "requires_primary_corroboration": True,
                "transaction_detail_complete": True,
                "paper_mode": True,
                "trade_execution_permission": False,
            }
        )
    return output


def fetch_marketbeat_insider_records(ticker: str) -> list[dict[str, Any]]:
    symbol = str(ticker or "").strip().upper().removesuffix(".US")
    if symbol != "MU":
        raise RuntimeError(f"No secondary public insider fallback configured for {symbol}")
    html = _request_bytes(
        MARKETBEAT_INSIDER_URL,
        accept="text/html,application/xhtml+xml",
        provider="marketbeat_insider",
        minimum_interval_seconds=0.5,
        retries=2,
        cache_ttl_seconds=15 * 60,
    ).decode("utf-8", errors="ignore")
    records = parse_marketbeat_insider_rows(html, ticker=symbol)
    if not records:
        raise RuntimeError("Secondary public insider page returned no corporate-insider transaction rows")
    return records


def install_secondary_insider_fallback(module: Any) -> None:
    prior_fetch: Callable[..., list[dict[str, Any]]] = module.fetch_public_insider_records
    prior_auto = module.auto_capture_insider

    def fetch_with_secondary(ticker: str, *, max_form4_filings: int = 12) -> list[dict[str, Any]]:
        try:
            return prior_fetch(ticker, max_form4_filings=max_form4_filings)
        except Exception as upstream_error:
            records = fetch_marketbeat_insider_records(ticker)
            for record in records:
                record["upstream_provider_error"] = f"{type(upstream_error).__name__}: {upstream_error}"
            return records

    module.fetch_public_insider_records = fetch_with_secondary

    def auto_capture_with_secondary_provider(case_id: str) -> dict[str, Any]:
        result = prior_auto(case_id)
        if result.get("status") in {"ok", "fallback_ok"}:
            records = module.list_objects(case_id, "insider_activity_record")
            secondary_records = [row for row in records if row.get("secondary_source") and row.get("subject_scope") != "EXCLUDED_NON_CORPORATE"]
            if secondary_records:
                return {
                    **result,
                    "status": "secondary_fallback_ok",
                    "provider": "MARKETBEAT_PUBLIC_SECONDARY",
                    "transaction_detail_complete": True,
                    "provider_note": "Direct SEC and official Micron IR were unavailable locally. A secondary public insider source was used for corporate-insider context only; congressional/political trades and non-transaction table rows are excluded. These records require primary-source corroboration and cannot resolve qualification gaps by themselves.",
                }
        return result

    module.auto_capture_insider = auto_capture_with_secondary_provider
