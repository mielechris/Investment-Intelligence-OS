from fastapi import APIRouter, HTTPException

from intelligence.providers import CoinGeckoProvider, FredProvider


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
    }


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
