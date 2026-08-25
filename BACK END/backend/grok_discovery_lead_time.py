from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from ledger import DB_PATH, utc_now


router = APIRouter()
POLICY_VERSION = "grok-discovery-lead-time-v2"


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


def _first_forward_observations(source: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in _rows("grok_value_discovery_observation"):
        if str(row.get("source") or "").upper() != source:
            continue
        ticker = _ticker(row.get("ticker"))
        observed = _parse_time(row.get("observed_at") or row.get("created_at"))
        if not ticker or observed is None:
            continue
        current = output.get(ticker)
        if current is None or observed < current["observed_at"]:
            output[ticker] = {"observed_at": observed, "row": row}
    return output


def _first_legacy_grok_nominations() -> dict[str, dict[str, Any]]:
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


def _first_legacy_native_iios_candidates() -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in _rows("opportunity_candidate"):
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


def _merged_first_seen(
    forward: dict[str, dict[str, Any]],
    legacy: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for ticker in set(forward) | set(legacy):
        candidates: list[dict[str, Any]] = []
        if ticker in forward:
            candidates.append({**forward[ticker], "measurement_mode": "FORWARD_INSTRUMENTED"})
        if ticker in legacy:
            candidates.append({**legacy[ticker], "measurement_mode": "LEGACY_LEDGER_FALLBACK"})
        candidates.sort(key=lambda item: item["observed_at"])
        output[ticker] = candidates[0]
    return output


def build_discovery_lead_time_report() -> dict[str, Any]:
    forward_grok = _first_forward_observations("GROK_X")
    forward_iios = _first_forward_observations("IIOS_NATIVE")
    grok = _merged_first_seen(forward_grok, _first_legacy_grok_nominations())
    iios = _merged_first_seen(forward_iios, _first_legacy_native_iios_candidates())
    tickers = sorted(set(grok) | set(iios))
    rows: list[dict[str, Any]] = []
    measurable_leads: list[float] = []
    prospective_leads: list[float] = []

    for ticker in tickers:
        grok_entry = grok.get(ticker) or {}
        iios_entry = iios.get(ticker) or {}
        grok_at = grok_entry.get("observed_at")
        iios_at = iios_entry.get("observed_at")
        lead_minutes = None
        winner = "UNMEASURED"
        prospective_pair = (
            grok_entry.get("measurement_mode") == "FORWARD_INSTRUMENTED"
            and iios_entry.get("measurement_mode") == "FORWARD_INSTRUMENTED"
        )
        if grok_at is not None and iios_at is not None:
            lead_minutes = round((iios_at - grok_at).total_seconds() / 60.0, 4)
            measurable_leads.append(lead_minutes)
            if prospective_pair:
                prospective_leads.append(lead_minutes)
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
            "grok_measurement_mode": grok_entry.get("measurement_mode"),
            "iios_measurement_mode": iios_entry.get("measurement_mode"),
            "prospective_pair": prospective_pair,
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
        "prospective_pair_count": len(prospective_leads),
        "grok_earlier_count": sum(1 for value in measurable_leads if value > 0),
        "iios_earlier_count": sum(1 for value in measurable_leads if value < 0),
        "tie_count": sum(1 for value in measurable_leads if value == 0),
        "prospective_grok_earlier_count": sum(1 for value in prospective_leads if value > 0),
        "prospective_iios_earlier_count": sum(1 for value in prospective_leads if value < 0),
        "mean_grok_lead_minutes": round(statistics.mean(measurable_leads), 4) if measurable_leads else None,
        "median_grok_lead_minutes": round(statistics.median(measurable_leads), 4) if measurable_leads else None,
        "prospective_median_grok_lead_minutes": round(statistics.median(prospective_leads), 4) if prospective_leads else None,
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
