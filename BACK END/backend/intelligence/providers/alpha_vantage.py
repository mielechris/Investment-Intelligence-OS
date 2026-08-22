import csv
import io
import json
import os
import re
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
                "Configured for equity history, company overview, earnings, estimates, calendar, and macro indicators."
                if configured
                else "Missing ALPHAVANTAGE_API_KEY."
            ),
        )

    def fetch(self, **kwargs: Any) -> EvidenceItem:
        symbol = str(kwargs.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("symbol is required")
        return self.fetch_latest_daily(symbol=symbol)

    def _safe_provider_message(self, value: object) -> str:
        text = str(value or "Alpha Vantage request failed")
        if self.api_key:
            text = text.replace(self.api_key, "[REDACTED_API_KEY]")
        text = re.sub(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b", "[REDACTED_API_KEY]", text)
        lower = text.lower()
        if any(marker in lower for marker in (
            "25 requests per day",
            "rate limit",
            "requests per day",
            "request per second",
            "call frequency",
        )):
            return "Alpha Vantage rate limit reached. Retry later or use a higher-quota Alpha Vantage plan."
        return text[:500]

    def _request(self, params: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("ALPHAVANTAGE_API_KEY is not configured")
        response = httpx.get(
            self.base_url,
            params={**params, "apikey": self.api_key},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        if "Error Message" in payload:
            raise RuntimeError(self._safe_provider_message(payload["Error Message"]))
        if "Note" in payload or "Information" in payload:
            raise RuntimeError(self._safe_provider_message(payload.get("Note") or payload.get("Information")))
        if not isinstance(payload, dict) or not payload:
            raise RuntimeError("Alpha Vantage returned no data")
        return payload

    def _request_csv(self, params: dict, *, allow_empty: bool = False) -> list[dict]:
        if not self.api_key:
            raise RuntimeError("ALPHAVANTAGE_API_KEY is not configured")
        response = httpx.get(
            self.base_url,
            params={**params, "apikey": self.api_key},
            timeout=20.0,
        )
        response.raise_for_status()
        text = response.text.strip()
        lower = text.lower()
        if any(marker in lower for marker in (
            "thank you for using alpha vantage",
            "rate limit",
            "requests per day",
            "request per second",
        )):
            raise RuntimeError(self._safe_provider_message(text))
        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                message = payload.get("Information") or payload.get("Note") or payload.get("Error Message")
                if message:
                    raise RuntimeError(self._safe_provider_message(message))
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows and not allow_empty:
            raise RuntimeError("Alpha Vantage returned no CSV rows")
        return rows

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
        payload = self._request({
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "outputsize": outputsize,
        })
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict) or not series:
            raise RuntimeError(f"No daily equity history returned for {symbol}")
        return series

    def fetch_company_overview(self, *, symbol: str) -> dict:
        payload = self._request({
            "function": "OVERVIEW",
            "symbol": symbol.upper(),
        })
        if not payload.get("Symbol"):
            raise RuntimeError(f"No company overview returned for {symbol}")
        return payload

    def fetch_earnings(self, *, symbol: str) -> dict:
        payload = self._request({
            "function": "EARNINGS",
            "symbol": symbol.upper(),
        })
        if not payload.get("quarterlyEarnings") and not payload.get("annualEarnings"):
            raise RuntimeError(f"No earnings history returned for {symbol}")
        return payload

    def fetch_earnings_estimates(self, *, symbol: str) -> dict:
        payload = self._request({
            "function": "EARNINGS_ESTIMATES",
            "symbol": symbol.upper(),
        })
        if not any(isinstance(value, list) and value for value in payload.values()):
            raise RuntimeError(f"No earnings estimates returned for {symbol}")
        return payload

    def fetch_earnings_calendar(self, *, symbol: str, horizon: str = "3month") -> list[dict]:
        rows = self._request_csv({
            "function": "EARNINGS_CALENDAR",
            "symbol": symbol.upper(),
            "horizon": horizon,
        }, allow_empty=True)
        if rows:
            return rows
        if horizon != "12month":
            rows = self._request_csv({
                "function": "EARNINGS_CALENDAR",
                "symbol": symbol.upper(),
                "horizon": "12month",
            }, allow_empty=True)
        if not rows:
            raise RuntimeError(f"No earnings-calendar rows returned for {symbol} across the requested/12-month horizon")
        return rows

    def fetch_economic_indicator(self, *, function: str, **params: str) -> dict:
        payload = self._request({"function": function, **params})
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise RuntimeError(f"No economic-indicator data returned for {function}")
        return payload
