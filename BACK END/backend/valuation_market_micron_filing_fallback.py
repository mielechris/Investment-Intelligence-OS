from __future__ import annotations

import re
from typing import Any


MICRON_Q3_2026_10Q_URL = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/mu-20260528.htm"
MICRON_FY2025_10K_URL = "https://www.sec.gov/Archives/edgar/data/723125/000072312525000038/mu-20251125.htm"

MICRON_Q3_2026_DILUTED_SHARES_M = 1145.0
MICRON_FY2025_DILUTED_EPS = 7.59
MICRON_9M_FY2025_DILUTED_EPS = 4.75
MICRON_9M_FY2026_DILUTED_EPS = 41.40


def micron_ttm_eps() -> float:
    """TTM GAAP diluted EPS through fiscal Q3 2026 from filed periods.

    FY2025 diluted EPS less the first nine months of FY2025 plus the first nine months
    of FY2026. This avoids mixing analyst estimates into a filing-backed valuation fact.
    """
    return round(
        MICRON_FY2025_DILUTED_EPS
        - MICRON_9M_FY2025_DILUTED_EPS
        + MICRON_9M_FY2026_DILUTED_EPS,
        4,
    )


def derive_ttm_pe(price: float) -> float:
    eps = micron_ttm_eps()
    if eps <= 0:
        raise ValueError("TTM EPS must be positive for P/E derivation")
    return round(float(price) / eps, 4)


def _market_price_from_claim(claim: str) -> float | None:
    text = str(claim or "")
    match = re.search(r"(?:market\s+price|current\s+price|price)\s*=\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.I)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def install_micron_valuation_filing_fallback(module: Any) -> None:
    """Add Micron filing-backed fallbacks without weakening the generic market adapter.

    The generic valuation adapter remains ticker-driven. This fallback activates only for
    MU when local SEC/Yahoo provider paths fail, using source-linked filed facts already
    available publicly. Consensus, short interest and options remain open unless their
    direct providers succeed; Cboe delayed quote pages are not auto-scraped.
    """
    prior_capture = module._capture_market
    prior_lane_status = module._lane_status

    def capture_market_with_micron_filing_fallback(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)
        profile = module.latest_object("monitor_profile", case_id=case_id) or {}
        ticker = str(profile.get("ticker") or "MU.US").strip().upper()
        symbol = ticker[:-3] if ticker.endswith(".US") else ticker
        if symbol != "MU":
            return added, failures

        diluted = module._persist_record(
            case_id,
            case,
            "valuation_market",
            "diluted_shares",
            {
                "source": "Micron Fiscal Q3 2026 Form 10-Q",
                "source_type": "filing",
                "evidence_type": "quarterly_filing",
                "url": MICRON_Q3_2026_10Q_URL,
                "title": "Micron Q3 2026 diluted share count",
                "claim": (
                    "Micron reported 1,145 million diluted shares used in the quarter-ended May 28, 2026 "
                    "earnings-per-share calculation."
                ),
                "timestamp": "2026-06-25T00:00:00+00:00",
                "reliability_score": 0.995,
                "capture_method": "CURATED_SOURCE_LINKED_SEC_FILING_FALLBACK",
            },
        )
        if diluted:
            added.append(diluted)

        # Derive a trailing GAAP P/E only from an already-admitted latest-session price
        # and filed EPS periods. If price is unavailable, valuation stays open.
        price_record = None
        price_value = None
        for row in reversed(module.list_objects(case_id, "primary_evidence_record")):
            if row.get("lane") != "valuation_market" or row.get("fact_key") != "market_price":
                continue
            candidate = _market_price_from_claim(str(row.get("claim") or ""))
            if candidate is not None:
                price_record = row
                price_value = candidate
                break

        if price_record is not None and price_value is not None:
            ttm_eps = micron_ttm_eps()
            ttm_pe = derive_ttm_pe(price_value)
            valuation = module._persist_record(
                case_id,
                case,
                "valuation_market",
                "valuation",
                {
                    "source": "Derived from admitted market session + Micron SEC filings",
                    "source_type": "market_data",
                    "evidence_type": "market_session",
                    "url": str(price_record.get("source_url") or MICRON_Q3_2026_10Q_URL),
                    "title": "MU filing-backed trailing GAAP P/E",
                    "claim": (
                        f"MU latest admitted market-session price={price_value}; filing-backed TTM diluted EPS={ttm_eps}; "
                        f"derived trailing GAAP P/E={ttm_pe}. TTM EPS derivation: FY2025 EPS {MICRON_FY2025_DILUTED_EPS} "
                        f"- 9M FY2025 EPS {MICRON_9M_FY2025_DILUTED_EPS} + 9M FY2026 EPS {MICRON_9M_FY2026_DILUTED_EPS}. "
                        f"Supporting SEC filings: {MICRON_FY2025_10K_URL} and {MICRON_Q3_2026_10Q_URL}."
                    ),
                    "timestamp": str(price_record.get("observed_at") or module.utc_now()),
                    "reliability_score": 0.93,
                    "capture_method": "DERIVED_FROM_ADMITTED_MARKET_PRICE_AND_SEC_FILINGS",
                },
            )
            if valuation:
                added.append(valuation)

        return added, failures

    def lane_status_with_micron_filing_fallback(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane != "valuation_market":
            return result
        facts = {
            str(row.get("key")): bool(row.get("covered"))
            for row in result.get("facts") or []
            if isinstance(row, dict)
        }
        base = str(result.get("note") or "").strip()
        filing_note = (
            " MU-specific fallback uses the latest filed diluted-share count and a transparent trailing GAAP P/E derived from "
            "the admitted market-session price plus filed EPS periods. Consensus, short interest and options remain open when direct providers fail; "
            "Cboe delayed quote pages are not auto-scraped."
        )
        if not facts.get("portfolio_overlap"):
            filing_note += " Portfolio overlap remains open until governed holdings exist."
        result["note"] = (base + filing_note).strip()
        return result

    module._capture_market = capture_market_with_micron_filing_fallback
    module._lane_status = lane_status_with_micron_filing_fallback
