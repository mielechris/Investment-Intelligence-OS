from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Literal

from intelligence.council_router import CouncilSimulationRequest, simulate_full_council
from intelligence.evidence_store import evidence_store
from intelligence.providers.alpha_vantage import AlphaVantageProvider
from intelligence.providers.fred import FredProvider


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


@router.post("/simulate-live")
def simulate_live_council(request: LiveCouncilSimulationRequest):
    evidence: list[dict] = []
    diagnostics = {
        "alpha_vantage_history": "not_attempted",
        "alpha_vantage_overview": "not_attempted",
        "fred": {},
        "archive_matches": 0,
    }

    alpha = AlphaVantageProvider()
    if alpha.status().configured:
        try:
            history = alpha.fetch_daily_history(symbol=request.asset, outputsize="compact")
            evidence.append(_market_history_evidence(request.asset, history))
            diagnostics["alpha_vantage_history"] = "ok"
        except Exception as exc:
            diagnostics["alpha_vantage_history"] = f"error: {exc}"
        try:
            overview = alpha.fetch_company_overview(symbol=request.asset)
            evidence.append(_overview_evidence(request.asset, overview))
            diagnostics["alpha_vantage_overview"] = "ok"
        except Exception as exc:
            diagnostics["alpha_vantage_overview"] = f"error: {exc}"
    else:
        diagnostics["alpha_vantage_history"] = "not_configured"
        diagnostics["alpha_vantage_overview"] = "not_configured"

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
