import os
from datetime import datetime, timezone
from typing import Any

import httpx

from intelligence.models import EvidenceItem
from intelligence.providers.base import EvidenceProvider, ProviderStatus


class AlphaVantageProvider(EvidenceProvider):
    name = "Alpha Vantage"
    kind = "market"
    base_url = "https://www.alphavantage.co/query"

    def __init__(self) -> None:
        self.api_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()

    def status(self) -> ProviderStatus:
        configured = bool(self.api_key)
        return ProviderStatus(
            name=self.name,
            kind=self.kind,
            configured=configured,
            live=configured,
            detail=(
                "Configured for equity daily OHLCV history."
                if configured
                else "Missing ALPHAVANTAGE_API_KEY."
            ),
        )

    def fetch(self, **kwargs: Any) -> EvidenceItem:
        symbol = str(kwargs.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("symbol is required")
        return self.fetch_latest_daily(symbol=symbol)

    def fetch_latest_daily(self, *, symbol: str) -> EvidenceItem:
        payload = self.fetch_daily_history(symbol=symbol, outputsize="compact")
        latest_date = sorted(payload.keys(), reverse=True)[0]
        row = payload[latest_date]
        return EvidenceItem(
            source_name="Alpha Vantage",
            source_kind="market",
            title=f"{symbol.upper()} latest daily market bar",
            url="https://www.alphavantage.co/",
            published_at=datetime.fromisoformat(f"{latest_date}T00:00:00+00:00"),
            observed_at=datetime.now(timezone.utc),
            summary=(
                f"{symbol.upper()} {latest_date}: open={row['1. open']}, high={row['2. high']}, "
                f"low={row['3. low']}, close={row['4. close']}, volume={row['5. volume']}."
            ),
            freshness="fresh",
            confidence=0.95,
        )

    def fetch_daily_history(self, *, symbol: str, outputsize: str = "compact") -> dict:
        if not self.api_key:
            raise RuntimeError("ALPHAVANTAGE_API_KEY is not configured")

        response = httpx.get(
            self.base_url,
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol.upper(),
                "outputsize": outputsize,
                "apikey": self.api_key,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        if "Error Message" in payload:
            raise RuntimeError(payload["Error Message"])
        if "Note" in payload or "Information" in payload:
            raise RuntimeError(payload.get("Note") or payload.get("Information"))
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict) or not series:
            raise RuntimeError(f"No daily equity history returned for {symbol}")
        return series
