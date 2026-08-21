import os
from datetime import datetime, timezone

import httpx

from intelligence.models import EvidenceItem
from intelligence.providers.base import EvidenceProvider, ProviderStatus


class CoinGeckoProvider(EvidenceProvider):
    name = "CoinGecko"
    kind = "market"
    base_url = "https://api.coingecko.com/api/v3/simple/price"

    def __init__(self) -> None:
        self.demo_key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind=self.kind,
            configured=True,
            live=True,
            detail=(
                "Live crypto pricing enabled; demo key configured."
                if self.demo_key
                else "Live crypto pricing enabled without a demo key; provider rate limits may be tighter."
            ),
        )

    def fetch(self, *, asset_id: str, vs_currency: str = "usd") -> EvidenceItem:
        headers = {}
        if self.demo_key:
            headers["x-cg-demo-api-key"] = self.demo_key

        params = {
            "ids": asset_id,
            "vs_currencies": vs_currency,
            "include_last_updated_at": "true",
        }
        response = httpx.get(
            self.base_url,
            params=params,
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        asset = payload.get(asset_id)
        if not asset or vs_currency not in asset:
            raise RuntimeError(f"No CoinGecko price returned for {asset_id}")

        price = asset[vs_currency]
        updated_epoch = asset.get("last_updated_at")
        published_at = (
            datetime.fromtimestamp(updated_epoch, tz=timezone.utc)
            if updated_epoch
            else None
        )

        return EvidenceItem(
            source_name="CoinGecko",
            source_kind="market",
            title=f"{asset_id} spot price",
            url=f"https://www.coingecko.com/en/coins/{asset_id}",
            published_at=published_at,
            observed_at=datetime.now(timezone.utc),
            summary=f"{asset_id} spot price = {price} {vs_currency.upper()}.",
            freshness="fresh",
            confidence=0.95,
        )
