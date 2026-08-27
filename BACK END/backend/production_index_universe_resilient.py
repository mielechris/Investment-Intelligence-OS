from __future__ import annotations

import csv
import io
import os
import re
import ssl
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import production_index_universe as legacy


NASDAQ100_DIRECT_URL = "https://www.nasdaq.com/products/global-indexes/nasdaq-100/companies"
SP500_DIRECT_URLS = (
    "https://www.spglobal.com/spdji/en/indices/equity/sp-500/?index=&p=",
    "https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
)
SP500_IVV_MIRROR_URL = "https://www.ishares.com/us/products/239726/ishares-core-s-p-500-etf/latest-holdings.csv"

BROWSER_USER_AGENT = os.getenv(
    "IIOS_INDEX_BROWSER_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/26.5 Safari/605.1.15",
)

ALLOWED_HOSTS = {
    "www.nasdaq.com",
    "nasdaq.com",
    "www.spglobal.com",
    "spglobal.com",
    "www.ishares.com",
    "ishares.com",
}

CLASS_SHARE_ALIASES = {
    "BRKB": "BRK.B",
    "BFB": "BF.B",
}


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(str(data or "").split())
        if value:
            self.parts.append(value)


def _ssl_context() -> ssl.SSLContext:
    cafile = str(os.getenv("SSL_CERT_FILE") or "").strip()
    context = ssl.create_default_context(cafile=cafile if cafile and Path(cafile).is_file() else None)
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError("INDEX_SOURCE_TLS_VERIFICATION_NOT_ENFORCED")
    return context


def _validate_host(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"INDEX_SOURCE_HOST_NOT_ALLOWED: {host or '<missing>'}")


def _fetch(url: str, *, referer: str | None = None) -> tuple[bytes, str | None]:
    _validate_host(url)
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json,text/csv;q=0.9,*/*;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "close",
    }
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    with urlopen(request, timeout=legacy.DEFAULT_TIMEOUT_SECONDS, context=_ssl_context()) as response:
        return response.read(), response.headers.get("Content-Type")


def _normalize_symbol(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    raw = CLASS_SHARE_ALIASES.get(raw, raw)
    return legacy.normalize_symbol(raw)


def _normalize_symbols(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = _normalize_symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def _nasdaq_visible_company_symbols(raw: bytes) -> list[str]:
    """Parse the publisher's visible Nasdaq-100 Symbol | Company Name list.

    The Nasdaq page is not a conventional HTML table in every render. Treating
    every short uppercase text node as a ticker over-collects company-name words
    such as APPLE, COSTCO, INTUIT, etc. The publisher section is explicitly a
    two-column Symbol / Company Name list, so consume the bounded section as
    symbol/company pairs and validate the resulting count before use.
    """
    text = raw.decode("utf-8", errors="replace")
    parser = _TextCollector()
    parser.feed(unescape(text))
    parts = parser.parts

    section_start: int | None = None
    section_end: int | None = None
    for idx, value in enumerate(parts):
        lower = value.lower()
        if section_start is None and "nasdaq-100 company breakdown" in lower:
            section_start = idx
        if section_start is not None and lower.startswith("last updated"):
            section_end = idx
            break
    if section_start is None:
        return []

    end = section_end if section_end is not None else min(len(parts), section_start + 500)
    scope = parts[section_start:end]

    # Find the exact two-column header. Some renders emit the header cells as
    # separate text nodes; others include both labels in one node.
    data_start: int | None = None
    for idx, value in enumerate(scope):
        normalized = " ".join(value.lower().split())
        if normalized == "symbol":
            if idx + 1 < len(scope) and "company name" in scope[idx + 1].lower():
                data_start = idx + 2
                break
        if "symbol" in normalized and "company name" in normalized:
            data_start = idx + 1
            break
    if data_start is None:
        return []

    rows = scope[data_start:]
    symbols: list[str] = []

    # Primary path: each publisher row contributes [symbol, company name].
    for idx in range(0, len(rows) - 1, 2):
        token = rows[idx].strip().upper()
        symbol = _normalize_symbol(token)
        if symbol and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,7}", token):
            symbols.append(symbol)

    paired = _normalize_symbols(symbols)
    if legacy.validate_index_count("NASDAQ100", paired)[0]:
        return paired

    # Defensive fallback for a render that inserts extra text nodes: select only
    # ticker-looking nodes whose immediate successor looks like a company label,
    # while rejecting known UI/category labels. Count validation remains the gate.
    rejected = {
        "SYMBOL", "ALL", "TECHNOLOGY", "INDUSTRIALS", "UTILITIES",
        "TELECOMMUNICATIONS", "HEALTH", "CARE", "BASIC", "MATERIALS",
        "CONSUMER", "STAPLES", "DISCRETIONARY", "COMPANY", "NAME",
    }
    fallback: list[str] = []
    for idx, value in enumerate(rows[:-1]):
        token = value.strip().upper()
        if token in rejected or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,7}", token):
            continue
        next_value = rows[idx + 1].strip()
        # Company labels normally contain lowercase after normalization, spaces,
        # punctuation, or are longer than plausible ticker symbols.
        if (
            " " in next_value
            or any(ch in next_value for ch in ".,'&()")
            or len(next_value) > 8
        ):
            symbol = _normalize_symbol(token)
            if symbol:
                fallback.append(symbol)
    return _normalize_symbols(fallback)


def _read_nasdaq100() -> dict[str, Any]:
    url = str(os.getenv("IIOS_NASDAQ100_CONSTITUENTS_URL") or NASDAQ100_DIRECT_URL).strip()
    raw, content_type = _fetch(url, referer="https://www.nasdaq.com/")

    # Prefer the publisher's explicitly labeled complete company list. Generic
    # page parsers can see navigation/marketing symbols and therefore over-count.
    visible = _nasdaq_visible_company_symbols(raw)
    if legacy.validate_index_count("NASDAQ100", visible)[0]:
        symbols = visible
    else:
        symbols = _normalize_symbols(legacy.parse_symbols_bytes(raw, content_type))

    symbols = _normalize_symbols(symbols)
    verified, error = legacy.validate_index_count("NASDAQ100", symbols)
    return {
        "source_mode": "OFFICIAL_WEB_SOURCE",
        "source_ref": url,
        "source_publisher": "NASDAQ",
        "symbols": symbols,
        "verified_complete": verified,
        "error": error,
    }


def _read_sp500_direct() -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    configured = str(os.getenv("IIOS_SP500_CONSTITUENTS_URL") or "").strip()
    urls = (configured,) if configured else SP500_DIRECT_URLS
    for url in urls:
        try:
            raw, content_type = _fetch(url, referer="https://www.spglobal.com/")
            symbols = _normalize_symbols(legacy.parse_symbols_bytes(raw, content_type))
            verified, error = legacy.validate_index_count("SP500", symbols)
            if verified:
                return {
                    "source_mode": "OFFICIAL_WEB_SOURCE",
                    "source_ref": url,
                    "source_publisher": "S&P_DOW_JONES_INDICES",
                    "symbols": symbols,
                    "verified_complete": True,
                    "error": None,
                }, errors
            errors.append(f"{url}: {error}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    return None, errors


def _parse_ivv_holdings(raw: bytes) -> list[str]:
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_index = None
    for idx, line in enumerate(lines):
        if line.startswith("Ticker,Name,Sector,Asset Class,"):
            header_index = idx
            break
    if header_index is None:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    symbols: list[str] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        asset_class = str(row.get("Asset Class") or "").strip().lower()
        if asset_class != "equity":
            continue
        ticker = _normalize_symbol(row.get("Ticker"))
        if ticker:
            symbols.append(ticker)
    return _normalize_symbols(symbols)


def _read_sp500_mirror(direct_errors: list[str]) -> dict[str, Any]:
    raw, _content_type = _fetch(SP500_IVV_MIRROR_URL, referer="https://www.ishares.com/")
    symbols = _parse_ivv_holdings(raw)
    verified, error = legacy.validate_index_count("SP500", symbols)
    lineage_note = (
        "S&P publisher direct source was attempted first but did not provide a complete machine-readable list. "
        "Fallback is BlackRock iShares IVV first-party holdings; IVV declares S&P 500 Index (USD) as its benchmark."
    )
    if direct_errors:
        lineage_note += " Direct attempt: " + " | ".join(direct_errors)[:1500]
    return {
        "source_mode": "GOVERNED_INDEX_TRACKER_MIRROR",
        "source_ref": SP500_IVV_MIRROR_URL,
        "source_publisher": "BLACKROCK_ISHARES",
        "benchmark": "S&P 500 Index (USD)",
        "symbols": symbols,
        "verified_complete": verified,
        "error": error,
        "lineage_note": lineage_note,
    }


def _read_sp500() -> dict[str, Any]:
    file_value = str(os.getenv("IIOS_SP500_CONSTITUENTS_FILE") or "").strip()
    if file_value:
        path = Path(file_value).expanduser()
        if not path.exists():
            raise FileNotFoundError(path)
        symbols = _normalize_symbols(legacy.parse_symbols_bytes(path.read_bytes(), None))
        verified, error = legacy.validate_index_count("SP500", symbols)
        return {
            "source_mode": "GOVERNED_LOCAL_FILE",
            "source_ref": str(path),
            "source_publisher": "OPERATOR_GOVERNED_FILE",
            "symbols": symbols,
            "verified_complete": verified,
            "error": error,
        }

    direct, errors = _read_sp500_direct()
    if direct is not None:
        return direct
    return _read_sp500_mirror(errors)


def refresh_official_index_universe() -> dict[str, Any]:
    index_results: dict[str, Any] = {}
    merged: list[str] = []
    seen: set[str] = set()
    all_verified = True

    for key, reader in (("SP500", _read_sp500), ("NASDAQ100", _read_nasdaq100)):
        try:
            result = reader()
            symbols = _normalize_symbols(result.get("symbols") or [])
            verified = result.get("verified_complete") is True
            error = result.get("error")
        except Exception as exc:  # noqa: BLE001
            result = {
                "source_mode": "ERROR",
                "source_ref": None,
                "source_publisher": None,
                "symbols": [],
            }
            symbols = []
            verified = False
            error = f"{type(exc).__name__}: {exc}"

        index_results[key] = {
            "index": key,
            "verified_complete": verified,
            "symbol_count": len(symbols),
            "symbols": symbols if verified else [],
            "source_mode": result.get("source_mode"),
            "source_ref": result.get("source_ref"),
            "source_publisher": result.get("source_publisher"),
            "benchmark": result.get("benchmark"),
            "lineage_note": result.get("lineage_note"),
            "error": error,
            "as_of": legacy.utc_now(),
        }

        if not verified:
            all_verified = False
            continue
        for symbol in symbols:
            if symbol not in seen:
                seen.add(symbol)
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
                "source_mode": row.get("source_mode"),
                "source_ref": row.get("source_ref"),
                "source_publisher": row.get("source_publisher"),
                "benchmark": row.get("benchmark"),
                "symbol_count": row.get("symbol_count"),
                "verified_complete": row.get("verified_complete"),
                "as_of": row.get("as_of"),
            }
            for key, row in index_results.items()
        ],
        "strict_membership": all_verified,
        "fail_closed": True,
        "acceptance_screener_fallback_used": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": legacy.utc_now(),
    }


def install_into_legacy_module() -> None:
    """Replace only the production refresh entry point; preserve legacy parsers/contracts."""
    legacy.refresh_official_index_universe = refresh_official_index_universe
