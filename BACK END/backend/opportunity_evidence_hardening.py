from __future__ import annotations

from typing import Any

from opportunity_evidence import fetch_crosschecked_quote, fetch_news_bundle


def _multi_provider_news(params: dict[str, Any]) -> list[dict[str, Any]]:
    bundle = fetch_news_bundle(
        str(params.get("query") or ""),
        limit=int(params.get("limit") or 8),
        timespan=str(params.get("timespan") or "24h"),
    )
    return list(bundle.get("items") or [])


def install_opportunity_evidence_hardening(module) -> None:
    """Install research-only evidence hardening onto opportunity acquisition.

    The scanner keeps its original deterministic scoring and promotion gates, but
    its quote gate now requires two agreeing public providers and its news intake
    uses two independent public aggregation feeds. No trading module is touched.
    """
    module.fetch_market_quote = fetch_crosschecked_quote
    module.fetch_gdelt_news = _multi_provider_news
