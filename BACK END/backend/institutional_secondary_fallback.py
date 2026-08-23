from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any

from provider_hardening import _request_bytes

BASE = "https://www.marketbeat.com/stocks/NASDAQ/MU"
URLS = {
    "institutional_ownership": f"{BASE}/institutional-ownership/",
    "analyst_revisions": f"{BASE}/forecast/",
    "short_interest": f"{BASE}/short-interest/",
    "options_positioning": f"{BASE}/options/",
    "catalyst_calendar": f"{BASE}/earnings/",
}


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", unescape(data)).strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        lower = tag.lower()
        if lower == "tr":
            self._in_row = True
            self._cells = []
        elif lower in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._parts = []
        elif lower == "br" and self._in_cell:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            text = re.sub(r"\s+", " ", unescape(data)).strip()
            if text:
                self._parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"td", "th"} and self._in_cell:
            self._cells.append(re.sub(r"\s+", " ", " ".join(self._parts)).strip())
            self._parts = []
            self._in_cell = False
        elif lower == "tr" and self._in_row:
            if self._cells:
                self.rows.append(list(self._cells))
            self._in_row = False
            self._cells = []


def _page(url: str, provider: str) -> tuple[str, str]:
    html = _request_bytes(
        url,
        accept="text/html,application/xhtml+xml",
        provider=provider,
        minimum_interval_seconds=0.45,
        retries=2,
        cache_ttl_seconds=10 * 60,
    ).decode("utf-8", errors="ignore")
    parser = _TextParser()
    parser.feed(html)
    return html, parser.text()


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(text))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _int(text: str | None) -> int | None:
    value = _num(text)
    return int(value) if value is not None else None


def _money(text: str | None) -> float | None:
    if text is None:
        return None
    match = re.search(r"\$?\s*([0-9,.]+)\s*([KMBT]?)", str(text), re.I)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    multiplier = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(match.group(2).upper(), 1.0)
    return value * multiplier


def _iso_date(text: str | None) -> str | None:
    value = re.sub(r"(?<=\d)(st|nd|rd|th)", "", str(text or ""), flags=re.I).strip()
    for fmt in ("%m/%d/%Y", "%B %d, %Y", "%b. %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None


def _latest_date(text: str) -> str | None:
    found = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
    parsed = [_iso_date(item) for item in found]
    parsed = [item for item in parsed if item]
    return max(parsed) if parsed else None


def parse_marketbeat_ownership(html: str, text: str) -> dict[str, Any] | None:
    ownership = re.search(r"Current\s+Institutional\s+Ownership\s+Percentage\s*([0-9.]+)%", text, re.I | re.S)
    buyers = re.search(r"Number\s+of\s+Institutional\s+Buyers(?:\s*\(last\s+12\s+months\))?\s*([0-9][0-9,]*)", text, re.I | re.S)
    inflows = re.search(r"Total\s+Institutional\s+Inflows.*?(\$[0-9.,]+\s*[KMBT]?)", text, re.I | re.S)
    sellers = re.search(r"Number\s+of\s+Institutional\s+Sellers(?:\s*\(last\s+12\s+months\))?\s*([0-9][0-9,]*)", text, re.I | re.S)
    outflows = re.search(r"Total\s+Institutional\s+Outflows.*?(\$[0-9.,]+\s*[KMBT]?)", text, re.I | re.S)
    values = {
        "institutional_ownership_pct": _num(ownership.group(1)) if ownership else None,
        "buyers_12m": _int(buyers.group(1)) if buyers else None,
        "inflows_12m": _money(inflows.group(1)) if inflows else None,
        "sellers_12m": _int(sellers.group(1)) if sellers else None,
        "outflows_12m": _money(outflows.group(1)) if outflows else None,
    }
    if all(value is None for value in values.values()):
        return None
    b = values["buyers_12m"] or 0
    s = values["sellers_12m"] or 0
    inflow = values["inflows_12m"] or 0.0
    outflow = values["outflows_12m"] or 0.0
    direction = "ACCUMULATION_BIAS" if b > s and inflow > outflow else "REDUCTION_BIAS" if s > b and outflow > inflow else "MIXED"
    return {
        "data_as_of": _latest_date(text) or datetime.now(timezone.utc).isoformat(),
        "summary": f"Secondary 13F context: institutional ownership={values['institutional_ownership_pct']}%, buyers={values['buyers_12m']}, sellers={values['sellers_12m']}; 13F data is lagged and does not represent current positioning.",
        "directional_context": direction,
        "details": {**values, "fallback_scope": "13F-derived ownership context; reporting lag applies"},
    }


def parse_marketbeat_analyst(html: str, text: str) -> dict[str, Any] | None:
    consensus = re.search(r"Consensus\s+Rating\s*(Strong Buy|Buy|Moderate Buy|Hold|Reduce|Sell|Strong Sell)", text, re.I | re.S)
    analysts = re.search(r"Based\s+on\s+([0-9]+)\s+Analyst\s+Ratings", text, re.I)
    target = re.search(r"Consensus\s+Price\s+Target\s*\$([0-9,.]+)", text, re.I | re.S)
    upside = re.search(r"Consensus\s+Price\s+Target\s*\$[0-9,.]+\s*([0-9.\-]+)%\s*(Upside|Downside)", text, re.I | re.S)
    parser = _TableParser(); parser.feed(html)
    recent_rows: list[dict[str, Any]] = []
    positive = negative = 0
    for cells in parser.rows:
        if not cells or not re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", cells[0]):
            continue
        blob = " | ".join(cells)
        action = next((name for name in ("Upgrade", "Downgrade", "Boost Target", "Lower Target", "Initiated Coverage", "Reiterated Rating") if name.lower() in blob.lower()), None)
        if not action:
            continue
        if action in {"Upgrade", "Boost Target"}:
            positive += 1
        elif action in {"Downgrade", "Lower Target"}:
            negative += 1
        recent_rows.append({"date": _iso_date(cells[0]), "action": action, "row": cells[:7]})
        if len(recent_rows) >= 12:
            break
    if not any((consensus, analysts, target, recent_rows)):
        return None
    rating = consensus.group(1).upper().replace(" ", "_") if consensus else "UNKNOWN"
    if positive > negative:
        direction = "REVISION_BIAS_POSITIVE"
    elif negative > positive:
        direction = "REVISION_BIAS_NEGATIVE"
    else:
        direction = f"CONSENSUS_{rating}"
    return {
        "data_as_of": max((row["date"] for row in recent_rows if row.get("date")), default=datetime.now(timezone.utc).isoformat()),
        "summary": f"Secondary analyst context: consensus={consensus.group(1) if consensus else 'unknown'}, analysts={_int(analysts.group(1)) if analysts else None}, target=${target.group(1) if target else 'unknown'}; recent rating/target actions positive={positive}, negative={negative}. This fallback is ratings/price-target context, not a point-in-time EPS revision series.",
        "directional_context": direction,
        "details": {
            "consensus_rating": consensus.group(1) if consensus else None,
            "analyst_count": _int(analysts.group(1)) if analysts else None,
            "consensus_price_target": _num(target.group(1)) if target else None,
            "forecast_pct": (_num(upside.group(1)) * (-1 if upside and upside.group(2).lower() == "downside" else 1)) if upside else None,
            "positive_recent_actions": positive,
            "negative_recent_actions": negative,
            "recent_actions": recent_rows,
            "fallback_scope": "analyst ratings and target changes; not true EPS-estimate revision history",
        },
    }


def parse_marketbeat_short_interest(html: str, text: str) -> dict[str, Any] | None:
    current = re.search(r"Current\s+Short\s+Interest\s*([0-9,.]+)\s*shares", text, re.I | re.S)
    previous = re.search(r"Previous\s+Short\s+Interest\s*([0-9,.]+)\s*shares", text, re.I | re.S)
    change = re.search(r"Change\s+Vs\.\s+Previous\s+Month\s*([+\-]?[0-9.]+)%", text, re.I | re.S)
    ratio = re.search(r"Short\s+Interest\s+Ratio\s*([0-9.]+)\s*Days?\s+to\s+Cover", text, re.I | re.S)
    pct = re.search(r"Short\s+Percent\s+of\s+Float\s*([0-9.]+)%", text, re.I | re.S)
    date = re.search(r"Last\s+Record\s+Date\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I | re.S)
    if not any((current, previous, change, ratio, pct, date)):
        return None
    change_value = _num(change.group(1)) if change else None
    direction = "SHORTS_INCREASING" if change_value is not None and change_value > 5 else "SHORTS_DECREASING" if change_value is not None and change_value < -5 else "STABLE_OR_UNKNOWN"
    return {
        "data_as_of": _iso_date(date.group(1)) if date else None,
        "summary": f"Secondary short-interest context: {_int(current.group(1)) if current else None} shares short, {_num(pct.group(1)) if pct else None}% of float, change={change_value}%, days-to-cover={_num(ratio.group(1)) if ratio else None}.",
        "directional_context": direction,
        "details": {
            "shares_short": _int(current.group(1)) if current else None,
            "shares_short_prior": _int(previous.group(1)) if previous else None,
            "change_pct": change_value,
            "days_to_cover": _num(ratio.group(1)) if ratio else None,
            "short_percent_float": _num(pct.group(1)) if pct else None,
            "fallback_scope": "published short-interest report; periodic and lagged",
        },
    }


def parse_marketbeat_options(html: str, text: str) -> dict[str, Any] | None:
    parser = _TableParser(); parser.feed(html)
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for cells in parser.rows:
        if len(cells) < 8:
            continue
        expiry = _iso_date(cells[0])
        if not expiry:
            continue
        expiry_dt = datetime.fromisoformat(expiry).date()
        if expiry_dt < today:
            continue
        side = str(cells[3]).strip().upper()
        if side not in {"PUT", "CALL"}:
            continue
        rows.append({
            "expiry": expiry,
            "side": side,
            "volume": _int(cells[4]) or 0,
            "open_interest": _int(cells[7]) or 0,
        })
    if not rows:
        return None
    nearest = min(row["expiry"] for row in rows)
    selected = [row for row in rows if row["expiry"] == nearest]
    call_oi = sum(row["open_interest"] for row in selected if row["side"] == "CALL")
    put_oi = sum(row["open_interest"] for row in selected if row["side"] == "PUT")
    call_vol = sum(row["volume"] for row in selected if row["side"] == "CALL")
    put_vol = sum(row["volume"] for row in selected if row["side"] == "PUT")
    oi_ratio = put_oi / call_oi if call_oi else None
    vol_ratio = put_vol / call_vol if call_vol else None
    direction = "PUT_HEAVY" if oi_ratio is not None and oi_ratio > 1.25 else "CALL_HEAVY" if oi_ratio is not None and oi_ratio < 0.75 else "BALANCED_OR_UNKNOWN"
    return {
        "data_as_of": datetime.now(timezone.utc).isoformat(),
        "summary": f"Secondary options context for nearest available expiry {nearest[:10]}: put/call OI={oi_ratio}, put/call volume={vol_ratio}. Options activity may reflect hedging rather than directional conviction.",
        "directional_context": direction,
        "details": {
            "expiration": nearest,
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "put_call_open_interest_ratio": oi_ratio,
            "call_volume": call_vol,
            "put_volume": put_vol,
            "put_call_volume_ratio": vol_ratio,
            "contracts_parsed": len(selected),
            "fallback_scope": "secondary end-of-day options context; hedging ambiguity applies",
        },
    }


def parse_marketbeat_catalyst(html: str, text: str) -> dict[str, Any] | None:
    next_match = re.search(r"next\s+earnings\s+date\s+is\s+estimated\s+for\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4})", text, re.I | re.S)
    if not next_match:
        next_match = re.search(r"Next\s+Earnings\s*\(Estimated\)\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", text, re.I | re.S)
    if not next_match:
        return None
    next_date = _iso_date(next_match.group(1))
    if not next_date:
        return None
    return {
        "data_as_of": datetime.now(timezone.utc).isoformat(),
        "summary": f"Secondary catalyst calendar: next earnings is estimated for {next_date[:10]}. Estimated dates can change until confirmed by the company.",
        "directional_context": "CATALYST_PENDING",
        "details": {"next_earnings": next_date, "estimated_not_confirmed": True, "fallback_scope": "estimated earnings calendar; company confirmation required"},
    }


PARSERS = {
    "institutional_ownership": parse_marketbeat_ownership,
    "analyst_revisions": parse_marketbeat_analyst,
    "short_interest": parse_marketbeat_short_interest,
    "options_positioning": parse_marketbeat_options,
    "catalyst_calendar": parse_marketbeat_catalyst,
}


def fetch_marketbeat_lane(lane: str) -> tuple[dict[str, Any], str]:
    if lane not in PARSERS:
        raise RuntimeError(f"No secondary institutional fallback configured for {lane}")
    url = URLS[lane]
    html, text = _page(url, f"marketbeat_institutional_{lane}")
    parsed = PARSERS[lane](html, text)
    if not parsed:
        raise RuntimeError(f"Secondary public {lane} page returned no usable governed context")
    return parsed, url


def install_institutional_secondary_fallback(module: Any) -> None:
    prior_auto = module.auto_capture_institutional

    def auto_capture_with_fallback(case_id: str) -> dict[str, Any]:
        result = prior_auto(case_id)
        case = module._require_case(case_id)
        symbol = module._symbol(case_id)
        snapshot_id = str(result.get("institutional_snapshot_id") or f"institutional_snapshot_{module.uuid4().hex}")
        captured = list(result.get("records") or [])
        captured_lanes = {str(row.get("lane") or "") for row in captured}
        errors = dict(result.get("failed_lanes") or {})
        fallback_lanes: list[str] = []

        for lane in module.LANES:
            if lane in captured_lanes:
                continue
            try:
                parsed, source_url = fetch_marketbeat_lane(lane)
                record = module._record_lane(case_id, case, symbol, snapshot_id, lane, parsed, source_url)
                updated = {
                    **record,
                    "source_name": "MarketBeat public market context",
                    "source_type": "secondary_public_aggregator",
                    "source_tier": "SECONDARY_PUBLIC_CONTEXT",
                    "reliability_score": min(float(record.get("reliability_score") or 0.7), 0.72),
                    "admission_status": "CORROBORATING_CONTEXT" if record.get("fresh") else "STALE_CONTEXT",
                    "gap_resolution_eligible": False,
                    "primary_corroboration_required": True,
                    "secondary_source": True,
                }
                module.record_object(str(updated["institutional_signal_id"]), "institutional_signal_record", case_id, updated, parent_id=snapshot_id, topic=case.get("topic"))
                captured.append(updated)
                captured_lanes.add(lane)
                fallback_lanes.append(lane)
                errors.pop(lane, None)
            except Exception as exc:
                errors[lane] = f"{type(exc).__name__}: {exc}"

        snapshot = {
            **result,
            "institutional_snapshot_id": snapshot_id,
            "captured_lanes": [lane for lane in module.LANES if lane in captured_lanes],
            "failed_lanes": errors,
            "records_added": len(captured),
            "source_tier": "MIXED_SECONDARY_PUBLIC_CONTEXT" if fallback_lanes else result.get("source_tier"),
            "fallback_lanes": fallback_lanes,
            "primary_corroboration_required": True,
            "gap_resolution_eligible": False,
            "paper_mode": True,
            "trade_execution_permission": False,
            "created_at": result.get("created_at") or module.utc_now(),
        }
        module.record_object(snapshot_id, "institutional_snapshot", case_id, snapshot, topic=case.get("topic"))
        module.record_event(case_id, "INSTITUTIONAL_SECONDARY_FALLBACK_COMPLETE", entity_id=snapshot_id, payload={"fallback_lanes": fallback_lanes, "failed_lanes": list(errors)})
        return {**snapshot, "records": captured}

    module.auto_capture_institutional = auto_capture_with_fallback
