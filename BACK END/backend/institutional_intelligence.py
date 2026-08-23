from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ledger import get_object, latest_object, list_objects, record_event, record_object
from provider_hardening import _json_request


router = APIRouter()
PAPER_MODE = True

LANES = {
    "institutional_ownership": {
        "label": "Institutional Ownership / 13F Context",
        "freshness_days": 150,
        "reliability": 0.74,
    },
    "analyst_revisions": {
        "label": "Analyst Estimate Revisions",
        "freshness_days": 14,
        "reliability": 0.76,
    },
    "short_interest": {
        "label": "Short Interest / Borrow Pressure",
        "freshness_days": 35,
        "reliability": 0.78,
    },
    "options_positioning": {
        "label": "Options Positioning",
        "freshness_days": 3,
        "reliability": 0.72,
    },
    "catalyst_calendar": {
        "label": "Catalyst Calendar",
        "freshness_days": 10,
        "reliability": 0.76,
    },
}

QUOTE_SUMMARY_MODULES = ",".join(
    [
        "institutionOwnership",
        "fundOwnership",
        "earningsTrend",
        "recommendationTrend",
        "upgradeDowngradeHistory",
        "defaultKeyStatistics",
        "calendarEvents",
    ]
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _symbol(case_id: str) -> str:
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


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


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_days(value: Any, *, now: datetime | None = None) -> int | None:
    stamp = _parse_iso(value)
    if stamp is None:
        return None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return max(0, int((current - stamp).total_seconds() // 86400))


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
            if not isinstance(payload, dict):
                raise ValueError("provider returned non-object JSON")
            return payload, url
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors) or "public market-data provider unavailable")


def fetch_quote_summary(symbol: str) -> tuple[dict[str, Any], str]:
    encoded = quote_plus(symbol)
    path = f"/v10/finance/quoteSummary/{encoded}?modules={QUOTE_SUMMARY_MODULES}"
    payload, url = _yahoo_json(
        [f"https://query2.finance.yahoo.com{path}", f"https://query1.finance.yahoo.com{path}"],
        provider="yahoo_institutional",
    )
    result = (((payload.get("quoteSummary") or {}).get("result") or [None])[0])
    if not isinstance(result, dict):
        error = (payload.get("quoteSummary") or {}).get("error")
        raise ValueError(f"quoteSummary returned no result: {error}")
    return result, url


def fetch_options(symbol: str) -> tuple[dict[str, Any], str]:
    encoded = quote_plus(symbol)
    path = f"/v7/finance/options/{encoded}"
    payload, url = _yahoo_json(
        [f"https://query2.finance.yahoo.com{path}", f"https://query1.finance.yahoo.com{path}"],
        provider="yahoo_options",
    )
    result = (((payload.get("optionChain") or {}).get("result") or [None])[0])
    if not isinstance(result, dict):
        error = (payload.get("optionChain") or {}).get("error")
        raise ValueError(f"options endpoint returned no result: {error}")
    return result, url


def parse_institutional_ownership(summary: dict[str, Any]) -> dict[str, Any] | None:
    module = summary.get("institutionOwnership") or {}
    rows = module.get("ownershipList") or []
    if not isinstance(rows, list) or not rows:
        return None
    holders: list[dict[str, Any]] = []
    dates: list[str] = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        report_date = _epoch_iso(row.get("reportDate"))
        if report_date:
            dates.append(report_date)
        holders.append(
            {
                "organization": row.get("organization"),
                "position": _int(row.get("position")),
                "value": _float(row.get("value")),
                "pct_held": _float(row.get("pctHeld")),
                "pct_change": _float(row.get("pctChange")),
                "report_date": report_date,
            }
        )
    latest = max(dates) if dates else None
    rising = sum(1 for row in holders if (row.get("pct_change") or 0) > 0)
    falling = sum(1 for row in holders if (row.get("pct_change") or 0) < 0)
    return {
        "data_as_of": latest,
        "summary": f"Top institutional holder context: {rising} increasing, {falling} decreasing among {len(holders)} reported holders; 13F-style ownership data is lagged.",
        "directional_context": "ACCUMULATION_BIAS" if rising > falling else "REDUCTION_BIAS" if falling > rising else "MIXED",
        "details": {"holders": holders, "increasing_holders": rising, "decreasing_holders": falling},
    }


def _trend_row(row: dict[str, Any]) -> dict[str, Any]:
    eps = row.get("epsTrend") or {}
    revenue = row.get("revenueEstimate") or {}
    earnings = row.get("earningsEstimate") or {}
    return {
        "period": row.get("period"),
        "end_date": row.get("endDate"),
        "growth": _float(row.get("growth")),
        "eps_current": _float(eps.get("current")),
        "eps_7d_ago": _float(eps.get("7daysAgo")),
        "eps_30d_ago": _float(eps.get("30daysAgo")),
        "eps_60d_ago": _float(eps.get("60daysAgo")),
        "eps_90d_ago": _float(eps.get("90daysAgo")),
        "revenue_average": _float(revenue.get("avg")),
        "earnings_average": _float(earnings.get("avg")),
    }


def parse_analyst_revisions(summary: dict[str, Any]) -> dict[str, Any] | None:
    rows = ((summary.get("earningsTrend") or {}).get("trend") or [])
    if not isinstance(rows, list) or not rows:
        return None
    trends = [_trend_row(row) for row in rows[:6] if isinstance(row, dict)]
    comparable = [row for row in trends if row.get("eps_current") is not None and row.get("eps_30d_ago") is not None]
    up = sum(1 for row in comparable if float(row["eps_current"]) > float(row["eps_30d_ago"]))
    down = sum(1 for row in comparable if float(row["eps_current"]) < float(row["eps_30d_ago"]))
    if up > down:
        direction = "REVISING_UP"
    elif down > up:
        direction = "REVISING_DOWN"
    elif comparable:
        direction = "MIXED_OR_FLAT"
    else:
        direction = "UNKNOWN"
    return {
        "data_as_of": utc_now(),
        "summary": f"Analyst EPS trend versus 30 days ago: {up} periods revised up, {down} revised down across {len(comparable)} comparable periods.",
        "directional_context": direction,
        "details": {"trends": trends, "revised_up": up, "revised_down": down},
    }


def parse_short_interest(summary: dict[str, Any]) -> dict[str, Any] | None:
    stats = summary.get("defaultKeyStatistics") or {}
    shares_short = _int(stats.get("sharesShort"))
    prior = _int(stats.get("sharesShortPriorMonth"))
    ratio = _float(stats.get("shortRatio"))
    pct_float = _float(stats.get("shortPercentOfFloat"))
    date = _epoch_iso(stats.get("dateShortInterest"))
    if all(value is None for value in (shares_short, prior, ratio, pct_float, date)):
        return None
    change_pct = None
    if shares_short is not None and prior not in (None, 0):
        change_pct = (shares_short - prior) / prior
    direction = "SHORTS_INCREASING" if (change_pct or 0) > 0.05 else "SHORTS_DECREASING" if (change_pct or 0) < -0.05 else "STABLE_OR_UNKNOWN"
    return {
        "data_as_of": date,
        "summary": f"Short interest: shares short={shares_short}, short ratio={ratio}, short % float={pct_float}, change vs prior month={change_pct}.",
        "directional_context": direction,
        "details": {
            "shares_short": shares_short,
            "shares_short_prior_month": prior,
            "short_ratio": ratio,
            "short_percent_float": pct_float,
            "change_vs_prior_month": change_pct,
            "date_short_interest": date,
        },
    }


def _median_iv(rows: list[dict[str, Any]]) -> float | None:
    values = [_float(row.get("impliedVolatility")) for row in rows if isinstance(row, dict)]
    clean = [value for value in values if value is not None]
    return float(median(clean)) if clean else None


def parse_options_positioning(result: dict[str, Any]) -> dict[str, Any] | None:
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
    oi_ratio = (put_oi / call_oi) if call_oi else None
    volume_ratio = (put_volume / call_volume) if call_volume else None
    call_iv = _median_iv(calls)
    put_iv = _median_iv(puts)
    expiration = _epoch_iso(chain.get("expirationDate"))
    direction = "PUT_HEAVY" if oi_ratio is not None and oi_ratio > 1.25 else "CALL_HEAVY" if oi_ratio is not None and oi_ratio < 0.75 else "BALANCED_OR_UNKNOWN"
    return {
        "data_as_of": utc_now(),
        "summary": f"Nearest-expiry options: put/call OI={oi_ratio}, put/call volume={volume_ratio}; options may reflect hedging rather than directional conviction.",
        "directional_context": direction,
        "details": {
            "expiration": expiration,
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "put_call_open_interest_ratio": oi_ratio,
            "call_volume": call_volume,
            "put_volume": put_volume,
            "put_call_volume_ratio": volume_ratio,
            "median_call_iv": call_iv,
            "median_put_iv": put_iv,
        },
    }


def parse_catalyst_calendar(summary: dict[str, Any]) -> dict[str, Any] | None:
    events = summary.get("calendarEvents") or {}
    earnings = events.get("earnings") or {}
    dates = earnings.get("earningsDate") or []
    parsed_dates = [_epoch_iso(item) for item in dates]
    parsed_dates = [item for item in parsed_dates if item]
    ex_div = _epoch_iso(events.get("exDividendDate"))
    div_date = _epoch_iso(events.get("dividendDate"))
    if not parsed_dates and not ex_div and not div_date:
        return None
    now = datetime.now(timezone.utc)
    future = [item for item in parsed_dates if (_parse_iso(item) or now - timedelta(days=1)) >= now]
    next_earnings = min(future) if future else (max(parsed_dates) if parsed_dates else None)
    return {
        "data_as_of": utc_now(),
        "summary": f"Catalyst calendar: next reported earnings window={next_earnings}; event dates require refresh because company schedules can change.",
        "directional_context": "CATALYST_PENDING" if next_earnings else "NO_NEAR_TERM_EVENT_CONFIRMED",
        "details": {
            "earnings_dates": parsed_dates,
            "next_earnings": next_earnings,
            "earnings_average": _float(earnings.get("earningsAverage")),
            "earnings_low": _float(earnings.get("earningsLow")),
            "earnings_high": _float(earnings.get("earningsHigh")),
            "revenue_average": _float(earnings.get("revenueAverage")),
            "revenue_low": _float(earnings.get("revenueLow")),
            "revenue_high": _float(earnings.get("revenueHigh")),
            "ex_dividend_date": ex_div,
            "dividend_date": div_date,
        },
    }


def _latest_requirement(case_id: str) -> str | None:
    decision = latest_object("committee_decision", case_id=case_id) or {}
    requirements = [str(item).strip() for item in decision.get("required_evidence") or [] if str(item).strip()]
    for requirement in requirements:
        lowered = requirement.lower()
        if any(term in lowered for term in ("valuation", "consensus", "options", "short interest", "positioning", "portfolio", "price")):
            return requirement
    return None


def _record_lane(
    case_id: str,
    case: dict[str, Any],
    symbol: str,
    snapshot_id: str,
    lane: str,
    parsed: dict[str, Any],
    source_url: str,
) -> dict[str, Any]:
    config = LANES[lane]
    record_id = f"institutional_{uuid4().hex}"
    data_as_of = parsed.get("data_as_of") or utc_now()
    age = _age_days(data_as_of)
    fresh = age is None or age <= int(config["freshness_days"])
    record = {
        "institutional_signal_id": record_id,
        "institutional_snapshot_id": snapshot_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "ticker": symbol,
        "lane": lane,
        "lane_label": config["label"],
        "summary": parsed.get("summary"),
        "directional_context": parsed.get("directional_context"),
        "details": parsed.get("details") or {},
        "data_as_of": data_as_of,
        "age_days": age,
        "freshness_days": config["freshness_days"],
        "fresh": fresh,
        "source_name": "Yahoo Finance public market data",
        "source_url": source_url,
        "source_type": "market_data",
        "source_tier": "SECONDARY_PUBLIC_MARKET_DATA",
        "reliability_score": config["reliability"],
        "admission_status": "CORROBORATING_CONTEXT" if fresh else "STALE_CONTEXT",
        "gap_requirement": _latest_requirement(case_id),
        "gap_resolution_eligible": False,
        "primary_corroboration_required": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }
    record_object(record_id, "institutional_signal_record", case_id, record, parent_id=snapshot_id, topic=case.get("topic"))
    return record


def institutional_evidence(case_id: str) -> list[dict[str, Any]]:
    records = list_objects(case_id, "institutional_signal_record")
    latest_by_lane: dict[str, dict[str, Any]] = {}
    for record in records:
        lane = str(record.get("lane") or "")
        current = latest_by_lane.get(lane)
        if current is None or str(record.get("created_at") or "") > str(current.get("created_at") or ""):
            latest_by_lane[lane] = record
    output: list[dict[str, Any]] = []
    for record in latest_by_lane.values():
        if record.get("admission_status") != "CORROBORATING_CONTEXT" or not record.get("fresh"):
            continue
        output.append(
            {
                "source": record.get("source_name"),
                "source_type": "market_data",
                "evidence_type": "market_context",
                "url": record.get("source_url"),
                "title": f"Institutional context · {record.get('lane_label')}",
                "claim": record.get("summary"),
                "timestamp": record.get("data_as_of"),
                "reliability_score": record.get("reliability_score"),
                "gap_requirement": record.get("gap_requirement"),
                "gap_resolution_eligible": False,
                "institutional_signal_id": record.get("institutional_signal_id"),
                "institutional_lane": record.get("lane"),
                "directional_context": record.get("directional_context"),
                "primary_corroboration_required": True,
            }
        )
    return output


def institutional_status(case_id: str) -> dict[str, Any]:
    _require_case(case_id)
    records = list_objects(case_id, "institutional_signal_record")
    latest_by_lane: dict[str, dict[str, Any]] = {}
    for record in records:
        lane = str(record.get("lane") or "")
        current = latest_by_lane.get(lane)
        if current is None or str(record.get("created_at") or "") > str(current.get("created_at") or ""):
            latest_by_lane[lane] = record
    lanes = {}
    for lane, config in LANES.items():
        record = latest_by_lane.get(lane)
        lanes[lane] = {
            "label": config["label"],
            "status": "CURRENT" if record and record.get("fresh") else "STALE" if record else "NO_DATA",
            "record": record,
        }
    snapshot = latest_object("institutional_snapshot", case_id=case_id)
    return {
        "case_id": case_id,
        "lanes": lanes,
        "latest_snapshot": snapshot,
        "paper_mode": True,
        "trade_execution_permission": False,
    }


def auto_capture_institutional(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    symbol = _symbol(case_id)
    snapshot_id = f"institutional_snapshot_{uuid4().hex}"
    captured: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    summary: dict[str, Any] | None = None
    summary_url: str | None = None
    try:
        summary, summary_url = fetch_quote_summary(symbol)
    except Exception as exc:
        errors["quote_summary"] = f"{type(exc).__name__}: {exc}"

    if summary is not None and summary_url:
        parsers = {
            "institutional_ownership": parse_institutional_ownership,
            "analyst_revisions": parse_analyst_revisions,
            "short_interest": parse_short_interest,
            "catalyst_calendar": parse_catalyst_calendar,
        }
        for lane, parser in parsers.items():
            try:
                parsed = parser(summary)
                if parsed:
                    captured.append(_record_lane(case_id, case, symbol, snapshot_id, lane, parsed, summary_url))
                else:
                    errors[lane] = "Provider returned no usable lane data"
            except Exception as exc:
                errors[lane] = f"{type(exc).__name__}: {exc}"

    try:
        options, options_url = fetch_options(symbol)
        parsed_options = parse_options_positioning(options)
        if parsed_options:
            captured.append(_record_lane(case_id, case, symbol, snapshot_id, "options_positioning", parsed_options, options_url))
        else:
            errors["options_positioning"] = "Provider returned no usable options chain"
    except Exception as exc:
        errors["options_positioning"] = f"{type(exc).__name__}: {exc}"

    snapshot = {
        "institutional_snapshot_id": snapshot_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "ticker": symbol,
        "captured_lanes": [record.get("lane") for record in captured],
        "failed_lanes": errors,
        "records_added": len(captured),
        "source_tier": "SECONDARY_PUBLIC_MARKET_DATA",
        "primary_corroboration_required": True,
        "gap_resolution_eligible": False,
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }
    record_object(snapshot_id, "institutional_snapshot", case_id, snapshot, topic=case.get("topic"))
    record_event(
        case_id,
        "INSTITUTIONAL_EXPECTATIONS_CAPTURED",
        entity_id=snapshot_id,
        payload={"captured_lanes": snapshot["captured_lanes"], "failed_lanes": list(errors), "records_added": len(captured)},
    )
    return {**snapshot, "records": captured}


@router.get("/institutional/{case_id}")
def get_institutional(case_id: str):
    return institutional_status(case_id)


@router.post("/institutional/{case_id}/auto-capture")
def capture_institutional(case_id: str):
    return auto_capture_institutional(case_id)
