import time
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Literal

from intelligence.council_router import CouncilSimulationRequest, simulate_full_council
from intelligence.evidence_store import evidence_store
from intelligence.providers.alpha_vantage import AlphaVantageProvider
from intelligence.providers.fred import FredProvider
from intelligence.providers.sec_company_profile import (
    fetch_company_facts_evidence,
    fetch_company_sec_evidence,
)


router = APIRouter(prefix="/intelligence/council", tags=["eight-agent-council-live"])


class LiveCouncilSimulationRequest(BaseModel):
    topic: str
    asset: str
    aliases: list[str] = Field(default_factory=list)
    direction: Literal["LONG", "SHORT", "WATCH"] = "WATCH"
    horizon: str = "1-3 months"
    thesis: str
    catalysts: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    simulated_notional: float = Field(default=10000.0, ge=0.0, le=1_000_000.0)


def _market_history_evidence(symbol: str, series: dict) -> dict:
    dates = sorted(series.keys(), reverse=True)[:30]
    rows = [(date, series[date]) for date in dates]
    closes = [float(row[1]["4. close"]) for row in rows]
    highs = [float(row[1]["2. high"]) for row in rows]
    lows = [float(row[1]["3. low"]) for row in rows]
    volumes = [float(row[1]["5. volume"]) for row in rows]
    latest_date, latest = rows[0]
    oldest_date, oldest = rows[-1]
    latest_close = float(latest["4. close"])
    oldest_close = float(oldest["4. close"])
    period_return = ((latest_close / oldest_close) - 1.0) * 100.0 if oldest_close else 0.0
    return {
        "source": "Alpha Vantage daily history",
        "source_kind": "market",
        "symbol": symbol.upper(),
        "latest_date": latest_date,
        "latest_open": float(latest["1. open"]),
        "latest_high": float(latest["2. high"]),
        "latest_low": float(latest["3. low"]),
        "latest_close": latest_close,
        "latest_volume": float(latest["5. volume"]),
        "window_start": oldest_date,
        "window_sessions": len(rows),
        "window_return_pct": round(period_return, 3),
        "window_high": max(highs),
        "window_low": min(lows),
        "average_volume": round(sum(volumes) / len(volumes), 2),
        "detail": (
            f"{symbol.upper()} latest close {latest_close} on {latest_date}; "
            f"{len(rows)}-session return {period_return:.2f}%; high {max(highs)}; "
            f"low {min(lows)}; average volume {sum(volumes)/len(volumes):.0f}."
        ),
    }


def _overview_evidence(symbol: str, overview: dict) -> dict:
    fields = [
        "Name", "Exchange", "Currency", "Country", "Sector", "Industry",
        "MarketCapitalization", "EBITDA", "PERatio", "ForwardPE", "PEGRatio",
        "PriceToSalesRatioTTM", "PriceToBookRatio", "EVToRevenue", "EVToEBITDA",
        "EPS", "RevenueTTM", "GrossProfitTTM", "ProfitMargin", "OperatingMarginTTM",
        "ReturnOnAssetsTTM", "ReturnOnEquityTTM", "RevenuePerShareTTM",
        "QuarterlyEarningsGrowthYOY", "QuarterlyRevenueGrowthYOY", "AnalystTargetPrice",
        "52WeekHigh", "52WeekLow", "50DayMovingAverage", "200DayMovingAverage",
        "SharesOutstanding", "DividendYield", "Beta",
    ]
    selected = {key: overview.get(key) for key in fields if overview.get(key) not in (None, "", "None")}
    return {
        "source": "Alpha Vantage company overview",
        "source_kind": "company",
        "symbol": symbol.upper(),
        "metrics": selected,
        "detail": "Live company overview and valuation/fundamental snapshot from Alpha Vantage.",
    }


def _earnings_evidence(symbol: str, payload: dict) -> dict:
    quarters = []
    for row in (payload.get("quarterlyEarnings") or [])[:8]:
        quarters.append({
            key: row.get(key)
            for key in (
                "fiscalDateEnding", "reportedDate", "reportedEPS", "estimatedEPS",
                "surprise", "surprisePercentage",
            )
        })
    latest = quarters[0] if quarters else {}
    return {
        "source": "Alpha Vantage earnings history",
        "source_kind": "company",
        "symbol": symbol.upper(),
        "quarterly_earnings": quarters,
        "detail": (
            f"Latest reported earnings date {latest.get('reportedDate')}; reported EPS "
            f"{latest.get('reportedEPS')} versus estimate {latest.get('estimatedEPS')}; "
            f"surprise {latest.get('surprisePercentage')}%."
        ),
    }


def _earnings_estimates_evidence(symbol: str, payload: dict) -> dict:
    collections: dict[str, list[dict]] = {}
    revision_snapshot: list[dict] = []
    for key, value in payload.items():
        if not isinstance(value, list):
            continue
        rows = [row for row in value[:8] if isinstance(row, dict)]
        if not rows:
            continue
        collections[key] = rows
        for row in rows[:4]:
            selected = {
                field: field_value
                for field, field_value in row.items()
                if any(token in field.lower() for token in (
                    "revision", "estimate", "analyst", "horizon", "date", "fiscal",
                ))
            }
            if selected:
                revision_snapshot.append({"collection": key, **selected})

    return {
        "source": "Alpha Vantage earnings estimates",
        "source_kind": "company",
        "symbol": symbol.upper(),
        "estimate_collections": collections,
        "revision_snapshot": revision_snapshot[:12],
        "detail": "Analyst EPS/revenue estimates, analyst counts, and estimate-revision fields returned by Alpha Vantage.",
    }


def _earnings_calendar_evidence(symbol: str, rows: list[dict]) -> dict:
    entries = rows[:5]
    first = entries[0] if entries else {}
    return {
        "source": "Alpha Vantage earnings calendar",
        "source_kind": "company",
        "symbol": symbol.upper(),
        "calendar_entries": entries,
        "issuer_confirmed": False,
        "detail": (
            f"Provider calendar lists the next earnings date as {first.get('reportDate') or first.get('report_date') or 'unknown'}. "
            "Treat this as provider-supplied calendar evidence unless separately confirmed by the issuer."
        ),
    }


def _macro_evidence(label: str, payload: dict) -> dict:
    rows = (payload.get("data") or [])[:5]
    latest = rows[0] if rows else {}
    return {
        "source": "Alpha Vantage economic indicator",
        "source_kind": "macro",
        "indicator": label,
        "name": payload.get("name"),
        "interval": payload.get("interval"),
        "unit": payload.get("unit"),
        "observations": rows,
        "detail": f"{label} latest observation: {latest.get('value')} on {latest.get('date')}.",
    }


def _matching_archive_evidence(asset: str, aliases: list[str], limit: int = 12) -> list[dict]:
    terms = {asset.lower(), *(alias.lower() for alias in aliases if alias.strip())}
    matches = []
    for item in evidence_store.recent(limit=1000):
        text = " ".join([item.source_name, item.title, item.summary, item.url or ""]).lower()
        if any(term and term in text for term in terms):
            matches.append({
                "source": item.source_name,
                "source_kind": item.source_kind,
                "title": item.title,
                "summary": item.summary,
                "url": item.url,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "observed_at": item.observed_at.isoformat(),
                "freshness": item.freshness,
                "confidence": item.confidence,
            })
        if len(matches) >= limit:
            break
    return matches


def _alpha_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in (
        "thank you for using alpha vantage",
        "rate limit",
        "request per second",
        "requests per day",
        "call frequency",
    ))


def _alpha_call_with_retry(callable_fn, *, pause_seconds: float = 1.25):
    try:
        return callable_fn(), False
    except Exception as exc:
        if not _alpha_rate_limited(exc):
            raise
        time.sleep(pause_seconds)
        return callable_fn(), True


@router.post("/simulate-live")
def simulate_live_council(request: LiveCouncilSimulationRequest):
    evidence: list[dict] = []
    diagnostics = {
        "alpha_vantage_history": "not_attempted",
        "alpha_vantage_overview": "not_attempted",
        "alpha_vantage_earnings": "not_attempted",
        "alpha_vantage_earnings_estimates": "not_attempted",
        "alpha_vantage_earnings_calendar": "not_attempted",
        "alpha_vantage_macro": {},
        "alpha_vantage_pacing_seconds": 1.25,
        "sec_company": "not_attempted",
        "sec_filings": 0,
        "sec_company_facts": "not_attempted",
        "fred": {},
        "archive_matches": 0,
    }

    try:
        sec_packet = fetch_company_sec_evidence(
            symbol=request.asset,
            forms=("10-Q", "10-K", "8-K"),
            limit=3,
            text_chars=8000,
        )
        evidence.extend(sec_packet.get("evidence", []))
        diagnostics["sec_company"] = "ok"
        diagnostics["sec_filings"] = int(sec_packet.get("count", 0))
    except Exception as exc:
        diagnostics["sec_company"] = f"error: {exc}"

    try:
        evidence.append(fetch_company_facts_evidence(symbol=request.asset))
        diagnostics["sec_company_facts"] = "ok"
    except Exception as exc:
        diagnostics["sec_company_facts"] = f"error: {exc}"

    alpha = AlphaVantageProvider()
    last_alpha_call_at: float | None = None

    def alpha_call(callable_fn):
        nonlocal last_alpha_call_at
        if last_alpha_call_at is not None:
            wait = 1.25 - (time.monotonic() - last_alpha_call_at)
            if wait > 0:
                time.sleep(wait)
        try:
            return _alpha_call_with_retry(callable_fn)
        finally:
            last_alpha_call_at = time.monotonic()

    if alpha.status().configured:
        try:
            history, retried = alpha_call(
                lambda: alpha.fetch_daily_history(symbol=request.asset, outputsize="compact")
            )
            evidence.append(_market_history_evidence(request.asset, history))
            diagnostics["alpha_vantage_history"] = "ok_after_retry" if retried else "ok"
        except Exception as exc:
            diagnostics["alpha_vantage_history"] = f"error: {exc}"

        try:
            overview, retried = alpha_call(lambda: alpha.fetch_company_overview(symbol=request.asset))
            evidence.append(_overview_evidence(request.asset, overview))
            diagnostics["alpha_vantage_overview"] = "ok_after_retry" if retried else "ok"
        except Exception as exc:
            diagnostics["alpha_vantage_overview"] = f"error: {exc}"

        try:
            earnings, retried = alpha_call(lambda: alpha.fetch_earnings(symbol=request.asset))
            evidence.append(_earnings_evidence(request.asset, earnings))
            diagnostics["alpha_vantage_earnings"] = "ok_after_retry" if retried else "ok"
        except Exception as exc:
            diagnostics["alpha_vantage_earnings"] = f"error: {exc}"

        try:
            estimates, retried = alpha_call(lambda: alpha.fetch_earnings_estimates(symbol=request.asset))
            evidence.append(_earnings_estimates_evidence(request.asset, estimates))
            diagnostics["alpha_vantage_earnings_estimates"] = "ok_after_retry" if retried else "ok"
        except Exception as exc:
            diagnostics["alpha_vantage_earnings_estimates"] = f"error: {exc}"

        try:
            calendar, retried = alpha_call(
                lambda: alpha.fetch_earnings_calendar(symbol=request.asset, horizon="12month")
            )
            evidence.append(_earnings_calendar_evidence(request.asset, calendar))
            diagnostics["alpha_vantage_earnings_calendar"] = "ok_after_retry" if retried else "ok"
        except Exception as exc:
            diagnostics["alpha_vantage_earnings_calendar"] = f"error: {exc}"

        macro_calls = (
            ("10Y Treasury", lambda: alpha.fetch_economic_indicator(function="TREASURY_YIELD", interval="daily", maturity="10year")),
            ("Federal Funds Rate", lambda: alpha.fetch_economic_indicator(function="FEDERAL_FUNDS_RATE", interval="daily")),
            ("CPI", lambda: alpha.fetch_economic_indicator(function="CPI", interval="monthly")),
        )
        for label, callable_fn in macro_calls:
            try:
                payload, retried = alpha_call(callable_fn)
                evidence.append(_macro_evidence(label, payload))
                diagnostics["alpha_vantage_macro"][label] = "ok_after_retry" if retried else "ok"
            except Exception as exc:
                diagnostics["alpha_vantage_macro"][label] = f"error: {exc}"
    else:
        diagnostics["alpha_vantage_history"] = "not_configured"
        diagnostics["alpha_vantage_overview"] = "not_configured"
        diagnostics["alpha_vantage_earnings"] = "not_configured"
        diagnostics["alpha_vantage_earnings_estimates"] = "not_configured"
        diagnostics["alpha_vantage_earnings_calendar"] = "not_configured"
        diagnostics["alpha_vantage_macro"]["status"] = "not_configured"

    archived = _matching_archive_evidence(request.asset, request.aliases)
    evidence.extend(archived)
    diagnostics["archive_matches"] = len(archived)

    fred = FredProvider()
    if fred.status().configured:
        for series_id in ("DGS10", "FEDFUNDS", "CPIAUCSL"):
            try:
                item = fred.fetch(series_id=series_id)
                evidence.append({
                    "source": item.source_name,
                    "source_kind": item.source_kind,
                    "title": item.title,
                    "summary": item.summary,
                    "url": item.url,
                    "freshness": item.freshness,
                    "confidence": item.confidence,
                })
                diagnostics["fred"][series_id] = "ok"
            except Exception as exc:
                diagnostics["fred"][series_id] = f"error: {exc}"
    else:
        diagnostics["fred"]["status"] = "not_configured"

    council_request = CouncilSimulationRequest(
        topic=request.topic,
        asset=request.asset.upper(),
        direction=request.direction,
        horizon=request.horizon,
        thesis=request.thesis,
        catalysts=request.catalysts,
        invalidation=request.invalidation,
        evidence=evidence,
        simulated_notional=request.simulated_notional,
    )
    result = simulate_full_council(council_request)
    result["live_evidence_enrichment"] = {
        "requested_asset": request.asset.upper(),
        "aliases": request.aliases,
        "evidence_item_count": len(evidence),
        "diagnostics": diagnostics,
        "provider_evidence": evidence,
    }
    return result
