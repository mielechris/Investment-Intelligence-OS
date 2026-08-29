#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import production_index_universe_resilient as resilient  # noqa: E402


def _iqq_fixture(count: int = 102) -> bytes:
    rows = [
        "iShares Nasdaq 100 ETF",
        'Fund Holdings as of,"Aug 28, 2026"',
        "Ticker,Name,Type,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date",
    ]
    for index in range(count):
        ticker = f"Q{index:03d}"
        rows.append(
            f'"{ticker}","Fixture {index}","EQUITY","Information Technology","Equity","1.00","0.10","1.00","1.00","1.00","United States","NASDAQ","USD","1.00","USD","-"'
        )
    rows.append('"USD","USD CASH","CASH","Cash and/or Derivatives","Cash","1.00","0.01","1.00","1.00","1.00","United States","-","USD","1.00","USD","-"')
    return ("\n".join(rows) + "\n").encode("utf-8")


def main() -> int:
    parsed = resilient._parse_ishares_equity_holdings(_iqq_fixture())
    assert len(parsed) == 102
    assert "USD" not in parsed
    assert resilient.legacy.validate_index_count("NASDAQ100", parsed)[0] is True

    original_fetch = resilient._fetch
    calls: list[str] = []

    def fake_fetch(url: str, *, referer: str | None = None):
        calls.append(url)
        if url == resilient.NASDAQ100_IQQ_MIRROR_URL:
            return _iqq_fixture(), "text/plain"
        # Simulate the current dynamic Nasdaq page exposing only a tiny incomplete set.
        return b'<html><body><table><tr><th>Symbol</th><th>Company Name</th></tr><tr><td>AAPL</td><td>Apple</td></tr></table></body></html>', "text/html"

    resilient._fetch = fake_fetch
    try:
        result = resilient._read_nasdaq100()
    finally:
        resilient._fetch = original_fetch

    assert result["verified_complete"] is True
    assert result["source_mode"] == "GOVERNED_INDEX_TRACKER_MIRROR"
    assert result["source_publisher"] == "BLACKROCK_ISHARES"
    assert result["benchmark"] == "Nasdaq 100 Index"
    assert len(result["symbols"]) == 102
    assert calls[0] == resilient.NASDAQ100_DIRECT_URL
    assert resilient.NASDAQ100_IQQ_MIRROR_URL in calls
    assert "Direct attempt:" in str(result.get("lineage_note") or "")

    # A malformed mirror must still fail closed rather than relaxing the count gate.
    def bad_fetch(url: str, *, referer: str | None = None):
        if url == resilient.NASDAQ100_IQQ_MIRROR_URL:
            return _iqq_fixture(5), "text/plain"
        return b"<html></html>", "text/html"

    resilient._fetch = bad_fetch
    try:
        bad = resilient._read_nasdaq100()
    finally:
        resilient._fetch = original_fetch

    assert bad["verified_complete"] is False
    assert len(bad["symbols"]) == 5
    assert "governed range is 95-110" in str(bad.get("error") or "")

    print("BATCH9E_RESILIENT_INDEX_MIRRORS_OK")
    print("NASDAQ direct -> IQQ mirror failover: PASS")
    print("95-110 governed count gate preserved: PASS")
    print("Yahoo/acceptance proxy fallback: NOT USED")
    print("Live execution authority: FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
