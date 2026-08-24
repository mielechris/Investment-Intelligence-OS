from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse

from fastapi import HTTPException

from provider_hardening import _json_request


NASDAQ_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 "
    "IIOS-Research/0.13.3"
)


def _symbol(module: Any, case_id: str) -> str:
    profile = module.latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


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


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _norm_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _first_value(row: dict[str, Any], names: set[str]) -> Any:
    normalized = {_norm_key(key): value for key, value in row.items()}
    for name in names:
        if name in normalized:
            return normalized[name]
    return None


def _candidate_rows(node: Any) -> list[dict[str, Any]]:
    """Find the row list inside Nasdaq's public response without hard-coding one UI schema."""
    candidates: list[list[dict[str, Any]]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            rows = [item for item in value if isinstance(item, dict)]
            if rows:
                score = 0
                for row in rows[:3]:
                    keys = {_norm_key(key) for key in row}
                    if keys & {"settlementdate", "shortinterest", "interest", "currentsharesreport", "daystocover"}:
                        score += 1
                if score:
                    candidates.append(rows)
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(node)
    if not candidates:
        return []
    return max(candidates, key=len)


def parse_nasdaq_short_interest(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = _candidate_rows(payload.get("data") if isinstance(payload, dict) else payload)
    parsed_rows: list[dict[str, Any]] = []
    for row in rows:
        settlement_raw = _first_value(row, {"settlementdate", "date", "reportdate"})
        settlement = _parse_date(settlement_raw)
        current = _integer(
            _first_value(
                row,
                {
                    "shortinterest",
                    "interest",
                    "currentsharesreport",
                    "currentshortpositionquantity",
                    "currentshortsharenumber",
                    "currentshort",
                },
            )
        )
        avg_volume = _integer(
            _first_value(row, {"avgdailysharevolume", "averagedailyvolumequantity", "avgdailyvolume"})
        )
        days_to_cover = _number(_first_value(row, {"daystocover", "daystocoverquantity"}))
        previous = _integer(
            _first_value(
                row,
                {"previoussharesreport", "previousshortpositionquantity", "previousshortsharenumber", "previousshort"},
            )
        )
        change_pct = _number(_first_value(row, {"percentchange", "changepercent", "pctchange"}))
        if settlement is None or current is None:
            continue
        parsed_rows.append(
            {
                "settlement_at": settlement,
                "settlement_date": settlement.date().isoformat(),
                "current_short": current,
                "previous_short": previous,
                "avg_daily_volume": avg_volume,
                "days_to_cover": days_to_cover,
                "change_percent": change_pct,
            }
        )

    if not parsed_rows:
        return None
    parsed_rows.sort(key=lambda item: item["settlement_at"], reverse=True)
    latest = dict(parsed_rows[0])
    if latest.get("previous_short") is None and len(parsed_rows) > 1:
        latest["previous_short"] = parsed_rows[1]["current_short"]
    if latest.get("change_percent") is None and latest.get("previous_short") not in (None, 0):
        latest["change_percent"] = round(
            (latest["current_short"] - latest["previous_short"]) / latest["previous_short"] * 100.0,
            4,
        )
    if latest.get("days_to_cover") is None and latest.get("avg_daily_volume") not in (None, 0):
        latest["days_to_cover"] = round(latest["current_short"] / latest["avg_daily_volume"], 4)
    latest.pop("settlement_at", None)
    return latest


def _fetch_nasdaq(symbol: str) -> tuple[dict[str, Any], str, str]:
    encoded = quote_plus(symbol.strip().upper())
    api_url = f"https://api.nasdaq.com/api/quote/{encoded}/short-interest?assetclass=stocks"
    public_url = f"https://www.nasdaq.com/market-activity/stocks/{encoded.lower()}/short-interest"
    payload = _json_request(
        url=api_url,
        user_agent=NASDAQ_BROWSER_USER_AGENT,
        provider="nasdaq_short_interest",
        minimum_interval_seconds=0.6,
        retries=2,
        cache_ttl_seconds=30 * 60,
    )
    if not isinstance(payload, dict):
        raise ValueError("Nasdaq returned non-object JSON")
    parsed = parse_nasdaq_short_interest(payload)
    if not parsed:
        raise ValueError("Nasdaq returned no usable short-interest rows")
    return parsed, api_url, public_url


def _valid_nasdaq_url(value: str) -> bool:
    try:
        host = (urlparse(value).hostname or "").lower()
    except ValueError:
        return False
    return host == "nasdaq.com" or host.endswith(".nasdaq.com") or host == "nasdaqtrader.com" or host.endswith(".nasdaqtrader.com")


def install_short_interest_fallback(module: Any) -> None:
    """Install exchange-first short-interest evidence plus a Nasdaq-only verified fallback."""
    prior_capture = module._capture_market
    prior_lane_status = module._lane_status

    def capture_market_with_short_interest(case_id: str, case: dict[str, Any]):
        added, failures = prior_capture(case_id, case)
        existing = [
            row
            for row in module.list_objects(case_id, "primary_evidence_record")
            if row.get("lane") == "valuation_market"
            and row.get("fact_key") == "short_interest"
            and row.get("gap_resolution_eligible") is True
        ]
        if existing:
            return added, failures

        symbol = _symbol(module, case_id)
        try:
            parsed, api_url, public_url = _fetch_nasdaq(symbol)
            current = parsed["current_short"]
            previous = parsed.get("previous_short")
            change = parsed.get("change_percent")
            avg = parsed.get("avg_daily_volume")
            days = parsed.get("days_to_cover")
            item = {
                "source": "Nasdaq Short Interest Report",
                "source_type": "market_data",
                "evidence_type": "short_interest",
                "url": public_url,
                "title": f"{symbol} Nasdaq short interest",
                "claim": (
                    f"{symbol} Nasdaq short interest as of {parsed['settlement_date']}: current shares short={current}; "
                    f"previous={previous}; change={change}%; average daily volume={avg}; days to cover={days}; "
                    f"exchange API={api_url}."
                ),
                "timestamp": parsed["settlement_date"],
                "reliability_score": 0.97,
            }
            record = module._persist_record(case_id, case, "valuation_market", "short_interest", item)
            if record:
                added.append(record)
        except Exception as exc:
            failures.append(f"Nasdaq short interest: {type(exc).__name__}: {exc}")
        return added, failures

    def lane_status_with_short_interest(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane == "valuation_market":
            facts = {str(row.get("key")): bool(row.get("covered")) for row in result.get("facts") or [] if isinstance(row, dict)}
            base = str(result.get("note") or "").strip()
            suffix = (
                " Short interest is covered by current Nasdaq exchange-reported data; it is periodic sentiment/risk evidence and has no execution authority."
                if facts.get("short_interest")
                else " Short interest remains OPEN unless Nasdaq exchange data is captured automatically or verified against the Nasdaq short-interest page."
            )
            result["note"] = (base + suffix).strip()
        return result

    module._capture_market = capture_market_with_short_interest
    module._lane_status = lane_status_with_short_interest

    # The real Primary Evidence module owns a FastAPI router. Test doubles may not.
    if not hasattr(module, "router"):
        return

    @module.router.get("/short-interest-verification/{case_id}")
    def short_interest_verification_status(case_id: str):
        case = module.get_object(case_id)
        if not case or not case_id.startswith("case_"):
            raise HTTPException(status_code=404, detail="Unknown case_id")
        ticker = _symbol(module, case_id)
        latest = module.latest_object("user_verified_short_interest_snapshot", case_id=case_id)
        return {
            "case_id": case_id,
            "ticker": ticker,
            "suggested_source_url": f"https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}/short-interest",
            "latest_snapshot": latest,
            "paper_mode": True,
            "live_execution": False,
        }

    @module.router.post("/short-interest-verification/{case_id}")
    def record_verified_short_interest(case_id: str, payload: dict[str, Any]):
        case = module.get_object(case_id)
        if not case or not case_id.startswith("case_"):
            raise HTTPException(status_code=404, detail="Unknown case_id")
        if payload.get("verified_against_source") is not True:
            raise HTTPException(status_code=422, detail="Verify the values against Nasdaq before saving")

        source_url = str(payload.get("source_url") or "").strip()
        if not _valid_nasdaq_url(source_url):
            raise HTTPException(status_code=422, detail="The source URL must be an official Nasdaq/NasdaqTrader short-interest page")

        settlement = _parse_date(payload.get("settlement_date"))
        if settlement is None:
            raise HTTPException(status_code=422, detail="Provide a valid short-interest settlement date")
        current = _integer(payload.get("current_short"))
        previous = _integer(payload.get("previous_short"))
        avg_volume = _integer(payload.get("avg_daily_volume"))
        days_to_cover = _number(payload.get("days_to_cover"))
        if current is None or current < 0:
            raise HTTPException(status_code=422, detail="Current shares short must be a non-negative number")
        if previous is not None and previous < 0:
            raise HTTPException(status_code=422, detail="Previous shares short must be non-negative")
        if avg_volume is not None and avg_volume <= 0:
            raise HTTPException(status_code=422, detail="Average daily volume must be greater than zero")
        if days_to_cover is not None and days_to_cover < 0:
            raise HTTPException(status_code=422, detail="Days to cover must be non-negative")
        if days_to_cover is None and avg_volume not in (None, 0):
            days_to_cover = round(current / avg_volume, 4)
        change_pct = None
        if previous not in (None, 0):
            change_pct = round((current - previous) / previous * 100.0, 4)

        ticker = _symbol(module, case_id)
        snapshot_id = f"user_verified_short_interest_{module.uuid4().hex}"
        snapshot = {
            "user_verified_short_interest_snapshot_id": snapshot_id,
            "case_id": case_id,
            "ticker": ticker,
            "settlement_date": settlement.date().isoformat(),
            "current_short": current,
            "previous_short": previous,
            "change_percent": change_pct,
            "avg_daily_volume": avg_volume,
            "days_to_cover": days_to_cover,
            "source_url": source_url,
            "verified_against_source": True,
            "source_class": "USER_VERIFIED_NASDAQ_SHORT_INTEREST",
            "paper_mode": True,
            "trade_execution_permission": False,
            "created_at": module.utc_now(),
        }
        module.record_object(snapshot_id, "user_verified_short_interest_snapshot", case_id, snapshot, topic=case.get("topic"))

        item = {
            "source": "Nasdaq Short Interest Report · user verified",
            "source_type": "market_data",
            "evidence_type": "short_interest",
            "url": source_url,
            "title": f"{ticker} user-verified Nasdaq short interest",
            "claim": (
                f"{ticker} Nasdaq short interest as of {snapshot['settlement_date']}: current shares short={current}; "
                f"previous={previous}; change={change_pct}%; average daily volume={avg_volume}; days to cover={days_to_cover}. "
                "User verified values against cited Nasdaq source."
            ),
            "timestamp": snapshot["settlement_date"],
            "reliability_score": 0.96,
        }
        record = module._persist_record(case_id, case, "valuation_market", "short_interest", item)
        if not record:
            raise HTTPException(status_code=500, detail="Short-interest evidence could not be persisted")
        record_id = str(record.get("primary_evidence_id") or "")
        governed = {
            **record,
            "source_grade": "EXCHANGE_VERIFIED_SHORT_INTEREST",
            "user_verified_exchange_source": True,
            "trade_execution_permission": False,
        }
        if record_id:
            module.record_object(record_id, "primary_evidence_record", case_id, governed, topic=case.get("topic"))
        module.record_event(
            case_id,
            "USER_VERIFIED_NASDAQ_SHORT_INTEREST_RECORDED",
            entity_id=snapshot_id,
            payload={
                "ticker": ticker,
                "settlement_date": snapshot["settlement_date"],
                "primary_evidence_id": record_id,
            },
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
