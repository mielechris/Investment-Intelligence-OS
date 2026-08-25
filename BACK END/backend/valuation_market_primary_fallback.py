from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any
from urllib.parse import quote_plus

import evidence_engine
import primary_evidence_contracts as contracts
from provider_hardening import _json_request


YAHOO_SUMMARY_MODULES = ",".join(
    [
        "price",
        "summaryDetail",
        "defaultKeyStatistics",
        "financialData",
        "earningsTrend",
    ]
)


def _raw(value: Any, default: Any = None) -> Any:
    if isinstance(value, dict) and "raw" in value:
        return value.get("raw", default)
    return default if value is None else value


def _float(value: Any) -> float | None:
    raw = _raw(value)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    raw = _raw(value)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _epoch_iso(value: Any) -> str | None:
    raw = _raw(value)
    if raw in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _symbol(module: Any, case_id: str) -> str:
    profile = module.latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


def _yahoo_json(urls: list[str], *, provider: str) -> tuple[dict[str, Any], str]:
    errors: list[str] = []
    for url in urls:
        try:
            payload = _json_request(
                url=url,
                provider=provider,
                minimum_interval_seconds=0.35,
                retries=1,
                cache_ttl_seconds=10 * 60,
            )
            if isinstance(payload, dict):
                return payload, url
            raise ValueError("provider returned non-object JSON")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors) or "market-data provider unavailable")


def _fetch_summary(symbol: str) -> tuple[dict[str, Any], str]:
    encoded = quote_plus(symbol)
    path = f"/v10/finance/quoteSummary/{encoded}?modules={YAHOO_SUMMARY_MODULES}"
    payload, url = _yahoo_json(
        [f"https://query2.finance.yahoo.com{path}", f"https://query1.finance.yahoo.com{path}"],
        provider="yahoo_valuation_primary",
    )
    result = (((payload.get("quoteSummary") or {}).get("result") or [None])[0])
    if not isinstance(result, dict):
        error = (payload.get("quoteSummary") or {}).get("error")
        raise ValueError(f"quoteSummary returned no result: {error}")
    return result, url


def _fetch_options(symbol: str) -> tuple[dict[str, Any], str]:
    encoded = quote_plus(symbol)
    path = f"/v7/finance/options/{encoded}"
    payload, url = _yahoo_json(
        [f"https://query2.finance.yahoo.com{path}", f"https://query1.finance.yahoo.com{path}"],
        provider="yahoo_valuation_options",
    )
    result = (((payload.get("optionChain") or {}).get("result") or [None])[0])
    if not isinstance(result, dict):
        error = (payload.get("optionChain") or {}).get("error")
        raise ValueError(f"options endpoint returned no result: {error}")
    return result, url


def _summary_records(symbol: str, summary: dict[str, Any], url: str, now_iso: str) -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    stats = summary.get("defaultKeyStatistics") or {}
    detail = summary.get("summaryDetail") or {}
    price = summary.get("price") or {}
    financial = summary.get("financialData") or {}

    market_price = _float(price.get("regularMarketPrice")) or _float(financial.get("currentPrice"))
    forward_pe = _float(detail.get("forwardPE")) or _float(stats.get("forwardPE"))
    trailing_pe = _float(detail.get("trailingPE")) or _float(stats.get("trailingPE"))
    price_to_book = _float(stats.get("priceToBook"))
    enterprise_to_ebitda = _float(stats.get("enterpriseToEbitda"))

    trends = ((summary.get("earningsTrend") or {}).get("trend") or [])
    selected: dict[str, Any] | None = None
    for preferred_period in ("+1y", "0y", "+1q", "0q"):
        selected = next(
            (row for row in trends if isinstance(row, dict) and str(row.get("period")) == preferred_period),
            None,
        )
        if selected:
            break
    if selected is None:
        selected = next((row for row in trends if isinstance(row, dict)), None)

    eps_current = None
    eps_30d = None
    revenue_avg = None
    period = None
    if selected:
        period = selected.get("period")
        eps = selected.get("epsTrend") or {}
        revenue = selected.get("revenueEstimate") or {}
        eps_current = _float(eps.get("current"))
        eps_30d = _float(eps.get("30daysAgo"))
        revenue_avg = _float(revenue.get("avg"))
        if eps_current is not None or revenue_avg is not None:
            records.append(
                (
                    "consensus",
                    {
                        "source": "Yahoo Finance public analyst-consensus data",
                        "source_type": "market_data",
                        "evidence_type": "analyst_consensus",
                        "url": url,
                        "title": f"{symbol} forward revenue / EPS consensus",
                        "claim": (
                            f"{symbol} consensus period={period}; revenue consensus={revenue_avg}; "
                            f"EPS consensus={eps_current}; EPS 30 days ago={eps_30d}."
                        ),
                        "timestamp": now_iso,
                        "reliability_score": 0.90,
                    },
                )
            )

    if forward_pe is None and market_price is not None and eps_current not in (None, 0):
        forward_pe = market_price / float(eps_current)
    if any(value is not None for value in (forward_pe, trailing_pe, price_to_book, enterprise_to_ebitda)):
        records.append(
            (
                "valuation",
                {
                    "source": "Yahoo Finance public market data",
                    "source_type": "market_data",
                    "evidence_type": "market_session",
                    "url": url,
                    "title": f"{symbol} valuation multiples",
                    "claim": (
                        f"{symbol} forward P/E={forward_pe}; trailing P/E={trailing_pe}; "
                        f"price/book={price_to_book}; enterprise/EBITDA={enterprise_to_ebitda}."
                    ),
                    "timestamp": now_iso,
                    "reliability_score": 0.90,
                },
            )
        )

    shares_short = _int(stats.get("sharesShort"))
    prior_short = _int(stats.get("sharesShortPriorMonth"))
    short_ratio = _float(stats.get("shortRatio"))
    short_float = _float(stats.get("shortPercentOfFloat"))
    short_date = _epoch_iso(stats.get("dateShortInterest"))
    if any(value is not None for value in (shares_short, prior_short, short_ratio, short_float, short_date)):
        change = None
        if shares_short is not None and prior_short not in (None, 0):
            change = (shares_short - prior_short) / prior_short
        records.append(
            (
                "short_interest",
                {
                    "source": "Yahoo Finance public short-interest data",
                    "source_type": "market_data",
                    "evidence_type": "short_interest",
                    "url": url,
                    "title": f"{symbol} short interest",
                    "claim": (
                        f"{symbol} shares short={shares_short}; short ratio={short_ratio}; "
                        f"short percent of float={short_float}; change vs prior month={change}."
                    ),
                    "timestamp": short_date or now_iso,
                    "reliability_score": 0.90,
                },
            )
        )

    return records


def _options_record(symbol: str, result: dict[str, Any], url: str, now_iso: str) -> tuple[str, dict[str, Any]] | None:
    option_sets = result.get("options") or []
    if not isinstance(option_sets, list) or not option_sets:
        return None
    chain = option_sets[0] if isinstance(option_sets[0], dict) else {}
    calls = [row for row in (chain.get("calls") or []) if isinstance(row, dict)]
    puts = [row for row in (chain.get("puts") or []) if isinstance(row, dict)]
    if not calls and not puts:
        return None

    call_oi = sum(_int(row.get("openInterest")) or 0 for row in calls)
    put_oi = sum(_int(row.get("openInterest")) or 0 for row in puts)
    call_volume = sum(_int(row.get("volume")) or 0 for row in calls)
    put_volume = sum(_int(row.get("volume")) or 0 for row in puts)
    put_call_oi = (put_oi / call_oi) if call_oi else None
    put_call_volume = (put_volume / call_volume) if call_volume else None
    iv_values = [
        value
        for value in (_float(row.get("impliedVolatility")) for row in [*calls, *puts])
        if value is not None
    ]
    median_iv = float(median(iv_values)) if iv_values else None
    expiration = _epoch_iso(chain.get("expirationDate"))
    return (
        "options",
        {
            "source": "Yahoo Finance public options chain",
            "source_type": "market_data",
            "evidence_type": "options",
            "url": url,
            "title": f"{symbol} nearest-expiry options positioning",
            "claim": (
                f"{symbol} nearest expiration={expiration}; put/call open-interest ratio={put_call_oi}; "
                f"put/call volume ratio={put_call_volume}; median implied volatility={median_iv}."
            ),
            "timestamp": now_iso,
            "reliability_score": 0.88,
        },
    )


def install_valuation_market_primary_fallback(module: Any) -> None:
    """Install reusable ticker-driven valuation/market evidence with honest freshness semantics."""
    # The current Committee explicitly asks for portfolio-factor overlap; add it to the
    # contract rather than letting the older six-fact card silently omit a required risk fact.
    valuation_contract = contracts.CONTRACTS["valuation_market"]
    if not any(str(fact.get("key")) == "portfolio_overlap" for fact in valuation_contract["facts"]):
        valuation_contract["facts"].append(
            {
                "key": "portfolio_overlap",
                "label": "Portfolio factor overlap",
                "terms": ("portfolio factor", "factor overlap", "portfolio overlap", "sector exposure"),
            }
        )

    prior_critical = contracts._critical_fact_keys

    def critical_fact_keys(requirement: str, lane: str) -> set[str]:
        critical = set(prior_critical(requirement, lane))
        lowered = str(requirement or "").lower()
        if lane == "valuation_market" and "portfolio" in lowered and "overlap" in lowered:
            critical.add("portfolio_overlap")
        return critical

    contracts._critical_fact_keys = critical_fact_keys

    # Market-session closes remain valid over weekends/holidays. Analyst consensus and
    # short-interest are periodic datasets rather than minute-by-minute observations.
    evidence_engine.FRESHNESS_WINDOWS_HOURS.update(
        {
            "market_session": 24 * 5,
            "analyst_consensus": 24 * 14,
            "short_interest": 24 * 45,
            "options": 24 * 4,
        }
    )
    evidence_engine.PERIODIC_EVIDENCE_TYPES.update({"market_session", "analyst_consensus", "short_interest"})

    prior_capture = module._capture_market
    prior_lane_status = module._lane_status

    def repair_fact_records(case_id: str, case: dict[str, Any], fact_key: str, evidence_type: str, reliability: float, source_type: str | None = None):
        repaired_rows: list[dict[str, Any]] = []
        for row in module.list_objects(case_id, "primary_evidence_record"):
            if row.get("lane") != "valuation_market" or row.get("fact_key") != fact_key:
                continue
            needs_repair = (
                str(row.get("evidence_type") or "") != evidence_type
                or float(row.get("reliability_score") or 0) < reliability
                or (source_type is not None and str(row.get("source_type") or "") != source_type)
            )
            if not needs_repair:
                repaired_rows.append(row)
                continue
            repaired = {
                **row,
                "evidence_type": evidence_type,
                "reliability_score": reliability,
                "classification_repaired_at": module.utc_now(),
                "classification_repair": "VALUATION_MARKET_FRESHNESS_CLASS",
            }
            if source_type is not None:
                repaired["source_type"] = source_type
                repaired["source_grade"] = module._source_grade(source_type)
            record_id = str(repaired.get("primary_evidence_id") or "")
            if record_id:
                module.record_object(record_id, "primary_evidence_record", case_id, repaired, topic=case.get("topic"))
                module.record_event(
                    case_id,
                    "PRIMARY_EVIDENCE_CLASSIFICATION_REPAIRED",
                    entity_id=record_id,
                    payload={"lane": "valuation_market", "fact_key": fact_key, "evidence_type": evidence_type},
                )
            repaired_rows.append(repaired)
        return repaired_rows

    def capture_market_governed(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)

        # SEC diluted-share observations are quarterly filing facts, not fast-moving market data.
        repaired_diluted = repair_fact_records(
            case_id,
            case,
            "diluted_shares",
            "quarterly_filing",
            0.98,
            source_type="filing",
        )
        added.extend(repaired_diluted)

        # A Friday close remains the latest completed market session on a weekend.
        repaired_price = repair_fact_records(
            case_id,
            case,
            "market_price",
            "market_session",
            0.90,
            source_type="market_data",
        )
        added.extend(repaired_price)

        symbol = _symbol(module, case_id)
        now_iso = module.utc_now()
        try:
            summary, summary_url = _fetch_summary(symbol)
            for fact_key, item in _summary_records(symbol, summary, summary_url, now_iso):
                record = module._persist_record(case_id, case, "valuation_market", fact_key, item)
                if record:
                    added.append(record)
        except Exception as exc:
            failures.append(f"Valuation/consensus/short data: {type(exc).__name__}: {exc}")

        try:
            options, options_url = _fetch_options(symbol)
            parsed = _options_record(symbol, options, options_url, now_iso)
            if parsed:
                fact_key, item = parsed
                record = module._persist_record(case_id, case, "valuation_market", fact_key, item)
                if record:
                    added.append(record)
        except Exception as exc:
            failures.append(f"Options chain: {type(exc).__name__}: {exc}")

        return added, failures

    def lane_status_market(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane == "valuation_market":
            facts = {str(row.get("key")): bool(row.get("covered")) for row in result.get("facts") or [] if isinstance(row, dict)}
            result["note"] = (
                "Price and valuation use latest-completed-market-session freshness; diluted shares use quarterly-filing freshness; "
                "consensus, short interest and options retain their natural reporting windows. Secondary institutional fallbacks remain context-only. "
                + ("Portfolio factor overlap is OPEN until a governed portfolio/holdings snapshot exists." if not facts.get("portfolio_overlap") else "Portfolio factor overlap is covered by governed portfolio data.")
            )
        return result

    module._capture_market = capture_market_governed
    module._lane_status = lane_status_market
