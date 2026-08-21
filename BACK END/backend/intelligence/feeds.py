from fastapi import APIRouter, HTTPException

from intelligence.evidence_store import evidence_store
from intelligence.ingestion import ingestion_service
from intelligence.providers import CoinGeckoProvider, FredProvider
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
    providers = [FredProvider(), CoinGeckoProvider()]
    return {
        "paper_mode": True,
        "live_execution": False,
        "providers": [_status_dict(provider) for provider in providers],
        "specialized_providers": [sec_ipo_status()],
        "ingestion": ingestion_service.status(),
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
        item = provider.fetch(series_id=series_id.upper())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return item


@router.get("/market/crypto/{asset_id}")
def get_crypto_price(asset_id: str, vs_currency: str = "usd"):
    provider = CoinGeckoProvider()
    try:
        item = provider.fetch(
            asset_id=asset_id.lower(),
            vs_currency=vs_currency.lower(),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return item


@router.get("/ipo/recent")
async def get_recent_ipo_filings(count_per_form: int = 25):
    try:
        return await fetch_recent_ipo_filings(count_per_form=count_per_form)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
