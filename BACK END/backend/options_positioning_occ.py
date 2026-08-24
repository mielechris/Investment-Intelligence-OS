from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse

from fastapi import HTTPException

from provider_hardening import _request_bytes


def _symbol(module: Any, case_id: str) -> str:
    profile = module.latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _number(value: Any) -> float | None:
    if value in (None, "", "N/A", "--"):
        return None
    text = str(value).replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _first(row: dict[str, Any], names: set[str]) -> Any:
    normalized = {_norm(key): value for key, value in row.items()}
    for name in names:
        if name in normalized:
            return normalized[name]
    return None


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _side(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"C", "CALL", "CALLS"} or text.startswith("CALL"):
        return "CALL"
    if text in {"P", "PUT", "PUTS"} or text.startswith("PUT"):
        return "PUT"
    return None


def parse_occ_open_interest_csv(text: str, symbol: str, *, report_date: str | None = None) -> dict[str, Any] | None:
    """Aggregate OCC clearing open interest for one underlying symbol.

    OCC's downloadable report schema has changed over time, so field aliases are deliberately
    flexible. The parser requires an explicit call/put side and open-interest value; it never
    infers direction from strike or option symbol text alone.
    """
    target = symbol.strip().upper()
    if not target:
        return None

    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    call_oi = 0
    put_oi = 0
    call_series = 0
    put_series = 0
    expiries: set[str] = set()
    matched = 0

    symbol_fields = {
        "underlyingsymbol",
        "underlying",
        "productsymbol",
        "symbol",
        "rootsymbol",
        "optionsymbol",
    }
    side_fields = {"callput", "putcall", "optiontype", "type", "cp", "right"}
    oi_fields = {"openinterest", "openinterestquantity", "oi", "quantity", "size"}
    expiry_fields = {"expirationdate", "expiration", "contractdate", "seriescontractdate", "maturitydate"}

    for row in reader:
        raw_symbol = _first(row, symbol_fields)
        row_symbol = str(raw_symbol or "").strip().upper()
        if not row_symbol:
            continue
        # Product symbols can include spaces/suffixes. Require the first token/root to match.
        root = row_symbol.split()[0].split("-")[0]
        if row_symbol != target and root != target:
            continue

        side = _side(_first(row, side_fields))
        oi = _integer(_first(row, oi_fields))
        if side is None or oi is None or oi < 0:
            continue

        matched += 1
        expiry_raw = _first(row, expiry_fields)
        expiry = _parse_date(expiry_raw)
        if expiry is not None:
            expiries.add(expiry.date().isoformat())

        if side == "CALL":
            call_oi += oi
            call_series += 1
        else:
            put_oi += oi
            put_series += 1

    if matched == 0 or (call_oi + put_oi) <= 0:
        return None

    ratio = round(put_oi / call_oi, 4) if call_oi > 0 else None
    if ratio is None:
        bias = "PUT_HEAVY"
    elif ratio >= 1.2:
        bias = "PUT_HEAVY"
    elif ratio <= 0.8:
        bias = "CALL_HEAVY"
    else:
        bias = "BALANCED"

    return {
        "report_date": report_date,
        "call_open_interest": call_oi,
        "put_open_interest": put_oi,
        "put_call_oi_ratio": ratio,
        "positioning_bias": bias,
        "call_series": call_series,
        "put_series": put_series,
        "series_count": call_series + put_series,
        "nearest_expiry": min(expiries) if expiries else None,
        "farthest_expiry": max(expiries) if expiries else None,
    }


def _candidate_report_dates(now: datetime | None = None) -> list[datetime]:
    cursor = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dates: list[datetime] = []
    for offset in range(0, 10):
        day = cursor - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        dates.append(day)
        if len(dates) >= 5:
            break
    return dates


def _fetch_occ(symbol: str) -> tuple[dict[str, Any], str]:
    errors: list[str] = []
    for day in _candidate_report_dates():
        report = day.strftime("%m/%d/%Y")
        url = f"https://marketdata.theocc.com/daily-open-interest?reportDate={quote_plus(report)}&action=download&format=csv"
        try:
            text = _request_bytes(
                url,
                accept="text/csv,text/plain,*/*",
                provider="occ_daily_open_interest",
                minimum_interval_seconds=0.5,
                retries=1,
                cache_ttl_seconds=30 * 60,
            ).decode("utf-8-sig", errors="ignore")
            parsed = parse_occ_open_interest_csv(text, symbol, report_date=day.date().isoformat())
            if parsed:
                return parsed, url
            errors.append(f"{day.date().isoformat()}: no {symbol} rows")
        except Exception as exc:
            errors.append(f"{day.date().isoformat()}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors) or "OCC daily open-interest data unavailable")


def _valid_occ_url(value: str) -> bool:
    try:
        host = (urlparse(value).hostname or "").lower()
    except ValueError:
        return False
    return host == "theocc.com" or host.endswith(".theocc.com")


def install_occ_options_positioning(module: Any) -> None:
    """Install OCC clearing open-interest positioning plus a verified OCC fallback."""
    prior_capture = module._capture_market
    prior_lane_status = module._lane_status

    def capture_market_with_occ(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)
        existing = [
            row
            for row in module.list_objects(case_id, "primary_evidence_record")
            if row.get("lane") == "valuation_market"
            and row.get("fact_key") == "options"
            and row.get("gap_resolution_eligible") is True
        ]
        if existing:
            return added, failures

        symbol = _symbol(module, case_id)
        try:
            parsed, source_url = _fetch_occ(symbol)
            item = {
                "source": "OCC Daily Open Interest",
                "source_type": "market_data",
                "evidence_type": "options",
                "url": source_url,
                "title": f"{symbol} OCC options positioning",
                "claim": (
                    f"{symbol} OCC options positioning as of {parsed['report_date']}: "
                    f"call OI={parsed['call_open_interest']}; put OI={parsed['put_open_interest']}; "
                    f"put/call OI={parsed['put_call_oi_ratio']}; bias={parsed['positioning_bias']}; "
                    f"series={parsed['series_count']}; nearest expiry={parsed['nearest_expiry']}."
                ),
                "timestamp": parsed["report_date"],
                "reliability_score": 0.98,
            }
            record = module._persist_record(case_id, case, "valuation_market", "options", item)
            if record:
                added.append(record)
        except Exception as exc:
            failures.append(f"OCC options positioning: {type(exc).__name__}: {exc}")
        return added, failures

    def lane_status_with_occ(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane == "valuation_market":
            facts = {str(row.get("key")): bool(row.get("covered")) for row in result.get("facts") or [] if isinstance(row, dict)}
            base = str(result.get("note") or "").strip()
            suffix = (
                " Options positioning is covered by OCC clearing open-interest data; put/call open interest is treated as positioning context only because options can represent hedges or spreads."
                if facts.get("options")
                else " Options positioning remains OPEN unless OCC open-interest data is captured automatically or verified against an OCC source."
            )
            result["note"] = (base + suffix).strip()
        return result

    module._capture_market = capture_market_with_occ
    module._lane_status = lane_status_with_occ

    if not hasattr(module, "router"):
        return

    @module.router.get("/options-positioning-verification/{case_id}")
    def options_positioning_verification_status(case_id: str):
        case = module.get_object(case_id)
        if not case or not case_id.startswith("case_"):
            raise HTTPException(status_code=404, detail="Unknown case_id")
        ticker = _symbol(module, case_id)
        latest = module.latest_object("user_verified_options_positioning_snapshot", case_id=case_id)
        return {
            "case_id": case_id,
            "ticker": ticker,
            "suggested_source_url": f"https://www.theocc.com/market-data/market-data-reports/series-and-trading-data/series-search?symbol={ticker.lower()}&symbolType=U",
            "latest_snapshot": latest,
            "paper_mode": True,
            "live_execution": False,
        }

    @module.router.post("/options-positioning-verification/{case_id}")
    def record_verified_options_positioning(case_id: str, payload: dict[str, Any]):
        case = module.get_object(case_id)
        if not case or not case_id.startswith("case_"):
            raise HTTPException(status_code=404, detail="Unknown case_id")
        if payload.get("verified_against_source") is not True:
            raise HTTPException(status_code=422, detail="Verify the values against OCC before saving")

        source_url = str(payload.get("source_url") or "").strip()
        if not _valid_occ_url(source_url):
            raise HTTPException(status_code=422, detail="The source URL must be an official OCC source")

        report_dt = _parse_date(payload.get("report_date"))
        if report_dt is None:
            raise HTTPException(status_code=422, detail="Provide a valid OCC report date")
        call_oi = _integer(payload.get("call_open_interest"))
        put_oi = _integer(payload.get("put_open_interest"))
        if call_oi is None or call_oi < 0 or put_oi is None or put_oi < 0:
            raise HTTPException(status_code=422, detail="Call and put open interest must be non-negative numbers")
        if (call_oi + put_oi) <= 0:
            raise HTTPException(status_code=422, detail="At least one side must have positive open interest")

        ratio = round(put_oi / call_oi, 4) if call_oi > 0 else None
        if ratio is None:
            bias = "PUT_HEAVY"
        elif ratio >= 1.2:
            bias = "PUT_HEAVY"
        elif ratio <= 0.8:
            bias = "CALL_HEAVY"
        else:
            bias = "BALANCED"

        ticker = _symbol(module, case_id)
        snapshot_id = f"user_verified_options_positioning_{module.uuid4().hex}"
        snapshot = {
            "user_verified_options_positioning_snapshot_id": snapshot_id,
            "case_id": case_id,
            "ticker": ticker,
            "report_date": report_dt.date().isoformat(),
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "put_call_oi_ratio": ratio,
            "positioning_bias": bias,
            "source_url": source_url,
            "verified_against_source": True,
            "source_class": "USER_VERIFIED_OCC_OPTIONS_POSITIONING",
            "paper_mode": True,
            "trade_execution_permission": False,
            "created_at": module.utc_now(),
        }
        module.record_object(snapshot_id, "user_verified_options_positioning_snapshot", case_id, snapshot, topic=case.get("topic"))

        item = {
            "source": "OCC options open interest · user verified",
            "source_type": "market_data",
            "evidence_type": "options",
            "url": source_url,
            "title": f"{ticker} user-verified OCC options positioning",
            "claim": (
                f"{ticker} OCC options positioning as of {snapshot['report_date']}: call OI={call_oi}; "
                f"put OI={put_oi}; put/call OI={ratio}; bias={bias}. User verified values against cited OCC source."
            ),
            "timestamp": snapshot["report_date"],
            "reliability_score": 0.97,
        }
        record = module._persist_record(case_id, case, "valuation_market", "options", item)
        if not record:
            raise HTTPException(status_code=500, detail="Options-positioning evidence could not be persisted")
        record_id = str(record.get("primary_evidence_id") or "")
        governed = {
            **record,
            "source_grade": "OCC_VERIFIED_OPTIONS_POSITIONING",
            "user_verified_clearing_source": True,
            "trade_execution_permission": False,
        }
        if record_id:
            module.record_object(record_id, "primary_evidence_record", case_id, governed, topic=case.get("topic"))
        module.record_event(
            case_id,
            "USER_VERIFIED_OCC_OPTIONS_POSITIONING_RECORDED",
            entity_id=snapshot_id,
            payload={"ticker": ticker, "report_date": snapshot["report_date"], "primary_evidence_id": record_id},
        )
        return {
            "case_id": case_id,
            "snapshot": snapshot,
            "primary_evidence_id": record_id,
            "source_grade": governed.get("source_grade"),
            "gap_resolution_eligible": governed.get("gap_resolution_eligible"),
            "paper_mode": True,
            "live_execution": False,
        }
