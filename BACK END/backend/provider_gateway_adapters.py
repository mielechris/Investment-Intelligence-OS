"""Six logical adapters with public-data-only projections, no network clients."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from provider_gateway_contract import PILOT, safe_document

ENDPOINTS = {
    "MASSIVE": ("BULK_SNAPSHOT",),
    "ALPACA": ("MULTI_SYMBOL_SNAPSHOT",),
    "FINANCIAL_DATASETS": ("COMPANY_FACTS", "PRICE_HISTORY", "FINANCIAL_STATEMENTS", "FINANCIAL_METRICS", "FILINGS"),
    "ALPHA_VANTAGE": ("ENRICHMENT",),
    "BIGDATA": ("COMPANY_RESEARCH", "NEWS", "FILINGS", "TRANSCRIPTS", "CATALYSTS", "NARRATIVE"),
    "YAHOO": ("SCREENER_DISCOVERY",),
}
FEEDS = {
    "ALPACA": {"sip": "REAL_TIME", "iex": "IEX_ONLY", "delayed_sip": "DELAYED", "unavailable": "UNAVAILABLE"},
    "MASSIVE": {"real_time": "REAL_TIME", "delayed": "DELAYED", "unavailable": "UNAVAILABLE"},
    "FINANCIAL_DATASETS": {"corporate_historical": "HISTORICAL"},
    "BIGDATA": {"research": "RESEARCH"},
    "ALPHA_VANTAGE": {"enrichment": "SECONDARY"},
    "YAHOO": {"screener": "DISCOVERY"},
}
FD_FIELDS = {
    "COMPANY_FACTS": ("name", "sector", "industry", "exchange"),
    "PRICE_HISTORY": ("time", "open", "high", "low", "close", "volume"),
    "FINANCIAL_STATEMENTS": ("report_period", "filing_date", "revenue", "net_income", "total_assets", "total_debt", "operating_cash_flow"),
    "FINANCIAL_METRICS": ("report_period", "price_to_earnings", "return_on_equity"),
    "FILINGS": ("filing_date", "report_period", "filing_type", "accession_number", "source_url"),
}


def _stamp(value, unit):
    if value is None:
        return None
    if unit == "ISO8601":
        return value if isinstance(value, str) else None
    if type(value) is not int:
        return None
    divisor = {"NANOSECONDS": 1_000_000_000, "MILLISECONDS": 1000, "SECONDS": 1}[unit]
    seconds, remainder = divmod(value, divisor)
    try:
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds, microseconds=(remainder * 1_000_000) // divisor)
        return dt.isoformat()
    except (ValueError, OverflowError):
        return None


def _quote(row, provider):
    massive = provider == "MASSIVE"
    q = row.get("lastQuote" if massive else "latestQuote")
    t = row.get("lastTrade" if massive else "latestTrade")
    q = q if isinstance(q, dict) else {}
    t = t if isinstance(t, dict) else {}
    fields = {"bid": q.get("p" if massive else "bp"), "ask": q.get("P" if massive else "ap"),
              "trade_price": t.get("p")}
    for value in fields.values():
        if value is not None and (type(value) not in (int, float) or value <= 0):
            raise ValueError("PRICE_FIELD_INVALID")
    raw = {"quote": q.get("t"), "trade": t.get("t"), "updated": row.get("updated"),
           "minute_bar": (row.get("min" if massive else "minuteBar") or {}).get("t")}
    unit = "NANOSECONDS" if massive else "ISO8601"
    return {"fields": fields, "absent_fields": [k for k, v in fields.items() if v is None],
            "provider_event_timestamps": raw, "event_time": _stamp(raw["quote"], unit),
            "event_time_basis": "PROVIDER_QUOTE", "timestamp_unit": unit,
            "publication_time": None, "source_references": []}


def _reference(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment


def normalize(provider, endpoint, payload):
    """Input is a sanitized public JSON body; unknown provider errors never echo."""
    safe_document(payload)
    if provider not in ENDPOINTS or endpoint not in ENDPOINTS[provider] or not isinstance(payload, dict):
        raise ValueError("ADAPTER_ENDPOINT_INVALID")
    if any(k in payload for k in ("error", "errors", "message", "code")):
        raise ValueError("PROVIDER_ERROR")
    status = payload.get("status", "OK")
    if status not in ("OK", "DELAYED", "PARTIAL"):
        raise ValueError("PROVIDER_STATUS_INVALID")
    delay = payload.get("delay_minutes")
    if delay is not None and (type(delay) not in (int, float) or delay < 0):
        raise ValueError("PROVIDER_DELAY_INVALID")
    if provider == "MASSIVE":
        rows = payload.get("tickers")
    elif provider == "ALPACA":
        rows = [{**v, "ticker": k} for k, v in payload.items() if isinstance(v, dict)]
        if len(rows) != len(payload):
            raise ValueError("SNAPSHOT_MAP_INVALID")
    elif provider == "YAHOO":
        rows = payload.get("candidates")  # existing collector output; never reranked
    else:
        rows = payload.get("records")  # public corporate/research transport contract
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError("OBSERVATIONS_REQUIRED")
    if "count" in payload and payload["count"] != len(rows):
        raise ValueError("RESPONSE_COUNT_MISMATCH")
    observations = []
    for row in rows:
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            raise ValueError("RESPONSE_SYMBOL_INVALID")
        if provider in ("MASSIVE", "ALPACA"):
            obs = _quote(row, provider)
        else:
            event = row.get("observation_time")
            refs = row.get("source_references", [])
            if not isinstance(refs, list) or any(not _reference(ref) for ref in refs):
                raise ValueError("SOURCE_REFERENCE_INVALID")
            if provider == "FINANCIAL_DATASETS":
                if ticker not in PILOT:
                    raise ValueError("PILOT_SYMBOL_REQUIRED")
                fields = {key: row.get(key) for key in FD_FIELDS[endpoint]}
                if ticker != "MU" and endpoint == "COMPANY_FACTS":
                    fields["sector"] = fields["industry"] = None
                if "source_url" in fields and fields["source_url"] is not None and not _reference(fields["source_url"]):
                    raise ValueError("SOURCE_REFERENCE_INVALID")
            elif provider == "BIGDATA":
                # Reference-first receipt interface, no unbounded narrative storage.
                fields = {"evidence_kind": endpoint, "document_identity": row.get("document_identity")}
            elif provider == "ALPHA_VANTAGE":
                fields = {"indicator": row.get("indicator"), "value": row.get("value")}
            else:
                fields = {key: row.get(key) for key in ("price", "change_pct", "volume_ratio", "screeners")}
                event = _stamp(row.get("regularMarketTime"), "SECONDS")
            obs = {"fields": fields, "absent_fields": [k for k, v in fields.items() if v is None],
                   "provider_event_timestamps": {"observation": event, "publication": row.get("publication_time")},
                   "event_time": event, "event_time_basis": "PROVIDER_OBSERVATION", "timestamp_unit": "ISO8601",
                   "publication_time": row.get("publication_time"), "source_references": refs}
        observations.append({"ticker": ticker, **obs})
    counts = Counter(r["ticker"] for r in observations)
    return {"observations": observations, "duplicates": sorted(k for k, n in counts.items() if n > 1),
            "status": status, "provider_reported_delay": payload.get("delay_minutes"),
            "partial_response": status == "PARTIAL" or (provider == "YAHOO" and payload.get("snapshot_complete") is not True)}
