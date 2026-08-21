import asyncio

from fastapi import APIRouter, HTTPException

from intelligence.committee_escalation import committee_escalations
from intelligence.dispatcher import dispatcher
from intelligence.evidence_store import evidence_store
from intelligence.ingestion import ingestion_service
from intelligence.providers import CoinGeckoProvider, FredProvider
from intelligence.providers.alpha_vantage import AlphaVantageProvider
from intelligence.providers.sec_company import fetch_recent_company_filings
from intelligence.providers.sec_ipo import fetch_recent_ipo_filings, sec_ipo_status


router = APIRouter(prefix="/intelligence/feeds", tags=["intelligence-feeds"])


def _status_dict(provider):
    status = provider.status()
    return {
        "name": status.name,
        "kind": status.kind,
        "configured": status.configured,
        "live": status.live,
        "detail": status.detail,
    }


@router.get("/status")
def get_feed_status():
    providers = [FredProvider(), CoinGeckoProvider(), AlphaVantageProvider()]
    return {
        "paper_mode": True,
        "live_execution": False,
        "providers": [_status_dict(provider) for provider in providers],
        "specialized_providers": [sec_ipo_status()],
        "ingestion": ingestion_service.status(),
        "dispatcher": dispatcher.counts(),
        "committee_escalations": committee_escalations.counts(),
    }


@router.get("/inbox")
def get_evidence_inbox(limit: int = 100, source_kind: str | None = None):
    items = evidence_store.recent(limit=limit, source_kind=source_kind)
    return {
        "count": len(items),
        "total_persisted": evidence_store.count(),
        "items": items,
        "paper_mode": True,
    }


@router.get("/dispatch")
def get_dispatch_queue(limit: int = 100):
    return {
        "counts": dispatcher.counts(),
        "items": dispatcher.recent(limit=limit),
        "paper_mode": True,
    }


@router.post("/dispatch/process")
def process_dispatch_queue(limit: int = 5):
    return {
        "processing": dispatcher.process_pending(limit=max(1, min(limit, 50))),
        "counts": dispatcher.counts(),
        "committee_counts": committee_escalations.counts(),
        "paper_mode": True,
    }


@router.get("/committee-escalations")
def get_committee_escalations(limit: int = 100):
    return {
        "counts": committee_escalations.counts(),
        "items": committee_escalations.recent(limit=limit),
        "paper_mode": True,
    }


@router.post("/committee-escalations/process")
def process_committee_escalations(limit: int = 3):
    return {
        "processing": committee_escalations.process_pending(limit=max(1, min(limit, 20))),
        "counts": committee_escalations.counts(),
        "paper_mode": True,
    }


@router.post("/ingestion/run-now")
async def run_ingestion_now():
    for job in ingestion_service.jobs:
        job.next_run_at = None
    await ingestion_service.run_once()
    return ingestion_service.status()


@router.get("/macro/fred/{series_id}")
def get_fred_series(series_id: str):
    provider = FredProvider()
    try:
        return provider.fetch(series_id=series_id.upper())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/market/crypto/{asset_id}")
def get_crypto_price(asset_id: str, vs_currency: str = "usd"):
    provider = CoinGeckoProvider()
    try:
        return provider.fetch(asset_id=asset_id.lower(), vs_currency=vs_currency.lower())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/market/equity/{symbol}")
def get_equity_latest(symbol: str):
    provider = AlphaVantageProvider()
    try:
        return provider.fetch_latest_daily(symbol=symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/history/equity/{symbol}")
def get_equity_history(symbol: str, outputsize: str = "compact"):
    provider = AlphaVantageProvider()
    if outputsize not in {"compact", "full"}:
        raise HTTPException(status_code=400, detail="outputsize must be compact or full")
    try:
        series = provider.fetch_daily_history(symbol=symbol.upper(), outputsize=outputsize)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"symbol": symbol.upper(), "daily": series, "paper_mode": True}


@router.get("/company/recent")
async def get_recent_company_filings(count_per_form: int = 40):
    try:
        return await fetch_recent_company_filings(count_per_form=count_per_form)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/ipo/recent")
async def get_recent_ipo_filings(count_per_form: int = 25):
    try:
        return await fetch_recent_ipo_filings(count_per_form=count_per_form)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/ipo/replay")
async def replay_recent_ipo_candidate(index: int = 0, count_per_form: int = 5):
    """Deep-analyze an existing recent SEC registration without creating duplicate queue work."""
    if index < 0:
        raise HTTPException(status_code=400, detail="index must be zero or greater")
    try:
        packet = await fetch_recent_ipo_filings(count_per_form=max(1, min(count_per_form, 25)))
        if index >= len(packet.items):
            raise HTTPException(
                status_code=404,
                detail=f"index {index} is outside the {len(packet.items)} returned candidates",
            )
        item = packet.items[index]
        result = await asyncio.to_thread(dispatcher.analyze_ipo_item_now, item)
        return {
            "candidate_index": index,
            "candidate": item,
            "analysis": result,
            "paper_mode": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
