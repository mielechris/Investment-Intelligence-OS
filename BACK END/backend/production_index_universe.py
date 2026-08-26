from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_USER_AGENT = os.getenv(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.16.0 research-client",
)

# These are discovery/default pages only. The adapter never assumes that a page
# contains a complete constituent list unless the parsed row count passes the
# governed count validation below.
DEFAULT_NASDAQ_100_URL = (
    "https://www.nasdaq.com/solutions/global-indexes/nasdaq-100/companies"
)
DEFAULT_SP500_URL = (
    "https://www.spglobal.com/spdji/en/indices/equity/sp-500/"
)

EXPECTED_COUNTS = {
    "SP500": (490, 520),
    "NASDAQ100": (95, 110),
}

SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


@dataclass(frozen=True)
class SourceSpec:
    index_key: str
    url_env: str
    file_env: str
    default_url: str


SOURCE_SPECS = (
    SourceSpec(
        index_key="SP500",
        url_env="IIOS_SP500_CONSTITUENTS_URL",
        file_env="IIOS_SP500_CONSTITUENTS_FILE",
        default_url=DEFAULT_SP500_URL,
    ),
    SourceSpec(
        index_key="NASDAQ100",
        url_env="IIOS_NASDAQ100_CONSTITUENTS_URL",
        file_env="IIOS_NASDAQ100_CONSTITUENTS_FILE",
        default_url=DEFAULT_NASDAQ_100_URL,
    ),
)


class _TableParser(HTMLParser):
    """Collect table rows without treating arbitrary HTML text as ticker data."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, str]]]] = []
        self._table: list[list[tuple[str, str]]] | None = None
        self._row: list[tuple[str, str]] | None = None
        self._cell_tag: str | None = None
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        name = tag.lower()
        if name == "table":
            self._table = []
        elif name == "tr" and self._table is not None:
            self._row = []
        elif name in {"td", "th"} and self._row is not None:
            self._cell_tag = name
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_tag is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in {"td", "th"} and self._cell_tag is not None and self._row is not None:
            value = " ".join("".join(self._cell_parts).split())
            self._row.append((self._cell_tag, value))
            self._cell_tag = None
            self._cell_parts = []
        elif name == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif name == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_symbol(value: Any) -> str | None:
    symbol = str(value or "").strip().upper()
    if symbol.endswith(".US"):
        symbol = symbol[:-3]
    symbol = symbol.replace("/", ".")
    if not SYMBOL_PATTERN.fullmatch(symbol):
        return None
    return symbol


def normalize_symbols(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = normalize_symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def _looks_like_symbol_header(value: str) -> bool:
    return value.strip().lower() in {
        "symbol",
        "ticker",
        "ticker symbol",
        "security symbol",
        "constituent symbol",
    }


def _symbol_from_mapping(row: dict[str, Any]) -> str | None:
    for key, value in row.items():
        if _looks_like_symbol_header(str(key)):
            symbol = normalize_symbol(value)
            if symbol:
                return symbol
    for key in ("symbol", "ticker", "Symbol", "Ticker"):
        if key in row:
            symbol = normalize_symbol(row.get(key))
            if symbol:
                return symbol
    return None


def parse_json_symbols(payload: Any) -> list[str]:
    rows: list[Any] = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in (
            "constituents",
            "components",
            "companies",
            "data",
            "rows",
            "results",
            "symbols",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        if not rows:
            rows = list(payload.values())

    symbols: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            symbol = _symbol_from_mapping(row)
        else:
            symbol = normalize_symbol(row)
        if symbol:
            symbols.append(symbol)
    return normalize_symbols(symbols)


def parse_delimited_symbols(text: str) -> list[str]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    symbols: list[str] = []
    if reader.fieldnames:
        for row in reader:
            symbol = _symbol_from_mapping(dict(row))
            if symbol:
                symbols.append(symbol)
    if symbols:
        return normalize_symbols(symbols)

    # Headerless fallback: use first column only. Count validation protects us
    # from accidentally accepting arbitrary prose as an index universe.
    raw_reader = csv.reader(io.StringIO(text), dialect=dialect)
    return normalize_symbols([row[0] for row in raw_reader if row])


def _symbols_from_tables(html: str) -> list[str]:
    parser = _TableParser()
    parser.feed(html)
    output: list[str] = []

    for table in parser.tables:
        header_index: int | None = None
        header_row_index: int | None = None

        for row_index, row in enumerate(table):
            for column_index, (tag, value) in enumerate(row):
                if tag == "th" and _looks_like_symbol_header(value):
                    header_index = column_index
                    header_row_index = row_index
                    break
            if header_index is not None:
                break

        if header_index is None or header_row_index is None:
            continue

        for row in table[header_row_index + 1 :]:
            if header_index >= len(row):
                continue
            symbol = normalize_symbol(row[header_index][1])
            if symbol:
                output.append(symbol)

    return normalize_symbols(output)


def parse_html_symbols(text: str) -> list[str]:
    html = unescape(text)
    candidates: list[str] = []

    # Explicit structured attributes/embedded fields only. We deliberately do not
    # accept every short <td> value because company names can look ticker-like.
    patterns = (
        r'(?i)\b(?:symbol|ticker)\b\s*["\']?\s*[:=]\s*["\']([A-Z][A-Z0-9.\-]{0,11})["\']',
        r'(?i)data-(?:symbol|ticker)=["\']([A-Z][A-Z0-9.\-]{0,11})["\']',
    )
    for pattern in patterns:
        candidates.extend(re.findall(pattern, html))

    candidates.extend(_symbols_from_tables(html))
    return normalize_symbols(candidates)


def parse_symbols_bytes(raw: bytes, content_type: str | None = None) -> list[str]:
    text = raw.decode("utf-8-sig", errors="replace")
    ctype = str(content_type or "").lower()
    stripped = text.lstrip()

    if "json" in ctype or stripped.startswith(("{", "[")):
        try:
            return parse_json_symbols(json.loads(text))
        except json.JSONDecodeError:
            pass

    if "csv" in ctype or "tab-separated" in ctype:
        return parse_delimited_symbols(text)

    if "html" in ctype or "<html" in stripped[:500].lower() or "<table" in stripped.lower():
        return parse_html_symbols(text)

    return parse_delimited_symbols(text)


def _validate_host(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    allow_custom = str(os.getenv("IIOS_ALLOW_CUSTOM_INDEX_SOURCE_HOSTS", "0")).lower() in {
        "1", "true", "yes", "on"
    }
    if allow_custom:
        return
    allowed = (
        "nasdaq.com",
        "www.nasdaq.com",
        "spglobal.com",
        "www.spglobal.com",
        "spdji.com",
        "www.spdji.com",
    )
    if host not in allowed and not any(host.endswith("." + value) for value in allowed):
        raise ValueError(
            f"Index source host {host or '<missing>'} is not an approved official host. "
            "Set IIOS_ALLOW_CUSTOM_INDEX_SOURCE_HOSTS=1 only for a separately governed source."
        )


def _fetch_url(url: str) -> tuple[bytes, str | None]:
    _validate_host(url)
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json,text/csv,text/html;q=0.9,*/*;q=0.5",
        },
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        return response.read(), response.headers.get("Content-Type")


def _read_source(spec: SourceSpec) -> dict[str, Any]:
    file_value = str(os.getenv(spec.file_env) or "").strip()
    url_value = str(os.getenv(spec.url_env) or "").strip()

    if file_value:
        path = Path(file_value).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Configured {spec.index_key} constituent file does not exist: {path}")
        raw = path.read_bytes()
        symbols = parse_symbols_bytes(raw, None)
        return {
            "source_mode": "GOVERNED_LOCAL_FILE",
            "source_ref": str(path),
            "symbols": symbols,
        }

    url = url_value or spec.default_url
    raw, content_type = _fetch_url(url)
    symbols = parse_symbols_bytes(raw, content_type)
    return {
        "source_mode": "OFFICIAL_WEB_SOURCE",
        "source_ref": url,
        "symbols": symbols,
    }


def validate_index_count(index_key: str, symbols: list[str]) -> tuple[bool, str | None]:
    minimum, maximum = EXPECTED_COUNTS[index_key]
    count = len(symbols)
    if count < minimum or count > maximum:
        return False, (
            f"{index_key} parsed {count} symbols; governed range is {minimum}-{maximum}. "
            "Incomplete or malformed source rejected."
        )
    return True, None


def refresh_official_index_universe() -> dict[str, Any]:
    index_results: dict[str, Any] = {}
    merged: list[str] = []
    merged_seen: set[str] = set()
    all_verified = True

    for spec in SOURCE_SPECS:
        try:
            result = _read_source(spec)
            symbols = normalize_symbols(result.get("symbols") or [])
            verified, error = validate_index_count(spec.index_key, symbols)
        except Exception as exc:
            result = {
                "source_mode": "ERROR",
                "source_ref": str(os.getenv(spec.file_env) or os.getenv(spec.url_env) or spec.default_url),
                "symbols": [],
            }
            symbols = []
            verified = False
            error = f"{type(exc).__name__}: {exc}"

        index_results[spec.index_key] = {
            "index": spec.index_key,
            "verified_complete": verified,
            "symbol_count": len(symbols),
            "symbols": symbols if verified else [],
            "source_mode": result.get("source_mode"),
            "source_ref": result.get("source_ref"),
            "error": error,
            "as_of": utc_now(),
        }

        if not verified:
            all_verified = False
            continue

        for symbol in symbols:
            if symbol not in merged_seen:
                merged_seen.add(symbol)
                merged.append(symbol)

    return {
        "status": "CAPTURED" if all_verified else "SOURCE_INCOMPLETE",
        "verified_complete": all_verified,
        "symbols": merged if all_verified else [],
        "symbol_count": len(merged) if all_verified else 0,
        "indexes": index_results,
        "source_lineage": [
            {
                "index": key,
                "source_mode": value.get("source_mode"),
                "source_ref": value.get("source_ref"),
                "symbol_count": value.get("symbol_count"),
                "verified_complete": value.get("verified_complete"),
                "as_of": value.get("as_of"),
            }
            for key, value in index_results.items()
        ],
        "strict_membership": all_verified,
        "fail_closed": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
