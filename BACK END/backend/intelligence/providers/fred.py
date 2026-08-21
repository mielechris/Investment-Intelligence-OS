import os
from datetime import datetime, timezone

import httpx

from intelligence.models import EvidenceItem
from intelligence.providers.base import EvidenceProvider, ProviderStatus


class FredProvider(EvidenceProvider):
    name = "FRED"
    kind = "macro"
    base_url = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self) -> None:
        self.api_key = os.getenv("FRED_API_KEY", "").strip()

    def status(self) -> ProviderStatus:
        configured = bool(self.api_key)
        return ProviderStatus(
            name=self.name,
            kind=self.kind,
            configured=configured,
            live=configured,
            detail=(
                "Configured for live macro observations."
                if configured
                else "Missing FRED_API_KEY."
            ),
        )

    def fetch(self, *, series_id: str) -> EvidenceItem:
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY is not configured")

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }
        response = httpx.get(self.base_url, params=params, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
        observations = payload.get("observations", [])
        if not observations:
            raise RuntimeError(f"No FRED observations returned for {series_id}")

        observation = observations[0]
        observed_at = datetime.now(timezone.utc)
        observation_date = observation.get("date", "unknown date")
        value = observation.get("value", ".")

        return EvidenceItem(
            source_name="Federal Reserve Bank of St. Louis FRED",
            source_kind="macro",
            title=f"FRED {series_id} latest observation",
            url=f"https://fred.stlouisfed.org/series/{series_id}",
            published_at=None,
            observed_at=observed_at,
            summary=f"{series_id} = {value} for observation date {observation_date}.",
            freshness="fresh",
            confidence=0.98,
        )
