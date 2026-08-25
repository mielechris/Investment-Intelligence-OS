from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from ledger import DB_PATH, utc_now


router = APIRouter()
POLICY_VERSION = "grok-discovery-lead-time-v1"


def _parse_time(value: Any) -> datetime | None:
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


def _rows(object_type: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? ORDER BY created_at ASC",
            (object_type,),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row[0]) for row in rows]


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _first_grok_nominations() -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in _rows("grok_opportunity_candidate"):
        ticker = _ticker(row.get("ticker"))
        observed = _parse_time(row.get("created_at"))
        if not ticker or observed is None or row.get("eligible_for_iios_revalidation") is not True:
            continue
        current = output.get(ticker)
        if current is None or observed < current["observed_at"]:
            output[ticker] = {"observed_at": observed, "row": row}
    return output


def _first_native_iios_candidates() -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in _rows("opportunity_candidate"):
        # Exclude standard candidates created only because Grok nominated them.
        if row.get("source_grok_candidate_id"):
            continue
        ticker = _ticker(row.get("ticker"))
        observed = _parse_time(row.get("created_at"))
        if not ticker or observed is None:
            continue
        current = output.get(ticker)
        if current is None or observed < current["observed_at"]:
            output[ticker] = {"observed_at": observed, "row": row}
    return output


def build_discovery_lead_time_report() -> dict[str, Any]:
    grok = _first_grok_nominations()
    iios = _first_native_iios_candidates()
    tickers = sorted(set(grok) | set(iios))
    rows: list[dict[str, Any]] = []
    measurable_leads: list[float] = []

    for ticker in tickers:
        grok_at = (grok.get(ticker) or {}).get("observed_at")
        iios_at = (iios.get(ticker) or {}).get("observed_at")
        lead_minutes = None
        winner = "UNMEASURED"
        if grok_at is not None and iios_at is not None:
            lead_minutes = round((iios_at - grok_at).total_seconds() / 60.0, 4)
            measurable_leads.append(lead_minutes)
            if lead_minutes > 0:
                winner = "GROK_EARLIER"
            elif lead_minutes < 0:
                winner = "IIOS_EARLIER"
            else:
                winner = "TIE"
        elif grok_at is not None:
            winner = "GROK_ONLY_SO_FAR"
        elif iios_at is not None:
            winner = "IIOS_ONLY_SO_FAR"

        rows.append({
            "ticker": ticker,
            "grok_first_seen_at": grok_at.isoformat() if grok_at else None,
            "iios_first_seen_at": iios_at.isoformat() if iios_at else None,
            "grok_lead_minutes": lead_minutes,
            "winner": winner,
            "measurement_definition": "positive grok_lead_minutes means Grok nomination preceded native IIOS opportunity discovery",
            "trade_signal": False,
            "trade_execution_permission": False,
            "live_execution": False,
        })

    return {
        "policy_version": POLICY_VERSION,
        "status": "MEASURING" if tickers else "NO_DISCOVERY_OBSERVATIONS_YET",
        "ticker_count": len(tickers),
        "measurable_pair_count": len(measurable_leads),
        "grok_earlier_count": sum(1 for value in measurable_leads if value > 0),
        "iios_earlier_count": sum(1 for value in measurable_leads if value < 0),
        "tie_count": sum(1 for value in measurable_leads if value == 0),
        "mean_grok_lead_minutes": round(statistics.mean(measurable_leads), 4) if measurable_leads else None,
        "median_grok_lead_minutes": round(statistics.median(measurable_leads), 4) if measurable_leads else None,
        "rows": rows,
        "automatic_promotion": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.get("/grok/value/lead-time")
def get_grok_discovery_lead_time():
    return build_discovery_lead_time_report()
