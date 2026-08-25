from __future__ import annotations

import json
import ssl
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

import certifi

from options_positioning_occ import install_occ_options_positioning


FINRA_DATA_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
FINRA_PUBLIC_URL = "https://www.finra.org/finra-data/browse-catalog/equity-short-interest/data"
FINRA_USER_AGENT = "Investment-Intelligence-OS/0.13.4 research-client github.com/mielechris/Investment-Intelligence-OS"


def _symbol(module: Any, case_id: str) -> str:
    profile = module.latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US").strip().upper()
    return ticker[:-3] if ticker.endswith(".US") else ticker


def _number(value: Any) -> float | None:
    if value in (None, "", "N/A", "--"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
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


def parse_finra_short_interest(payload: Any, symbol: str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("results") or payload.get("rows") or []
    else:
        rows = payload
    if not isinstance(rows, list):
        return None

    wanted = symbol.strip().upper()
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = str(row.get("symbolCode") or row.get("issueSymbolIdentifier") or row.get("symbol") or "").strip().upper()
        if row_symbol and row_symbol != wanted:
            continue
        settlement = _parse_date(row.get("settlementDate"))
        current = _integer(row.get("currentShortPositionQuantity") or row.get("currentShortShareNumber"))
        if settlement is None or current is None:
            continue
        previous = _integer(row.get("previousShortPositionQuantity") or row.get("previousShortShareNumber"))
        avg_volume = _integer(row.get("averageDailyVolumeQuantity") or row.get("averageShortShareNumber"))
        days_to_cover = _number(row.get("daysToCoverQuantity") or row.get("daysToCoverNumber"))
        change_percent = _number(row.get("changePercent"))
        if change_percent is None and previous not in (None, 0):
            change_percent = round((current - previous) / previous * 100.0, 4)
        if days_to_cover is None and avg_volume not in (None, 0):
            days_to_cover = round(current / avg_volume, 4)
        parsed.append(
            {
                "settlement_at": settlement,
                "settlement_date": settlement.date().isoformat(),
                "current_short": current,
                "previous_short": previous,
                "avg_daily_volume": avg_volume,
                "days_to_cover": days_to_cover,
                "change_percent": change_percent,
                "market": row.get("marketClassCode") or row.get("marketCategoryCode"),
                "revision_flag": row.get("revisionFlag"),
            }
        )

    if not parsed:
        return None
    parsed.sort(key=lambda item: item["settlement_at"], reverse=True)
    latest = dict(parsed[0])
    latest.pop("settlement_at", None)
    return latest


def _fetch_finra(symbol: str) -> tuple[dict[str, Any], str, str]:
    payload = {
        "limit": 25,
        "compareFilters": [
            {
                "compareType": "EQUAL",
                "fieldName": "symbolCode",
                "fieldValue": symbol.strip().upper(),
            }
        ],
    }
    request = Request(
        FINRA_DATA_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "User-Agent": FINRA_USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=15, context=context) as response:
        body = json.loads(response.read().decode("utf-8"))
    parsed = parse_finra_short_interest(body, symbol)
    if not parsed:
        raise ValueError("FINRA consolidated short-interest dataset returned no usable rows")
    return parsed, FINRA_DATA_URL, FINRA_PUBLIC_URL


def install_finra_short_interest_fallback(module: Any) -> None:
    """Try FINRA consolidated short interest after Nasdaq, then install OCC options positioning."""
    prior_capture = module._capture_market
    prior_lane_status = module._lane_status

    def capture_market_with_finra(case_id: str, case: dict[str, Any]):
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
            parsed, api_url, public_url = _fetch_finra(symbol)
            current = parsed["current_short"]
            previous = parsed.get("previous_short")
            change = parsed.get("change_percent")
            avg = parsed.get("avg_daily_volume")
            days = parsed.get("days_to_cover")
            item = {
                "source": "FINRA Consolidated Short Interest",
                "source_type": "regulatory",
                "evidence_type": "short_interest",
                "url": public_url,
                "title": f"{symbol} FINRA consolidated short interest",
                "claim": (
                    f"{symbol} FINRA consolidated short interest as of {parsed['settlement_date']}: "
                    f"current shares short={current}; previous={previous}; change={change}%; "
                    f"average daily volume={avg}; days to cover={days}; market={parsed.get('market')}; "
                    f"revision flag={parsed.get('revision_flag')}; regulatory API={api_url}."
                ),
                "timestamp": parsed["settlement_date"],
                "reliability_score": 0.98,
            }
            record = module._persist_record(case_id, case, "valuation_market", "short_interest", item)
            if record:
                added.append(record)
        except Exception as exc:
            failures.append(f"FINRA consolidated short interest: {type(exc).__name__}: {exc}")
        return added, failures

    def lane_status_with_finra(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        if lane == "valuation_market":
            facts = {str(row.get("key")): bool(row.get("covered")) for row in result.get("facts") or [] if isinstance(row, dict)}
            base = str(result.get("note") or "").strip()
            suffix = (
                " Short interest is covered by exchange/regulatory reported data from Nasdaq or FINRA; it is periodic risk evidence and has no execution authority."
                if facts.get("short_interest")
                else " Short interest remains OPEN after Nasdaq and FINRA regulatory provider attempts; do not substitute daily short-sale volume for short-interest positions."
            )
            result["note"] = (base + suffix).strip()
        return result

    module._capture_market = capture_market_with_finra
    module._lane_status = lane_status_with_finra

    # OCC is installed last so options positioning is independent of the Nasdaq/FINRA
    # short-interest provider chain and sees the final market-capture result.
    install_occ_options_positioning(module)
