from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from evidence_engine import build_packet
from ledger import latest_object, record_event, record_object, utc_now
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE
from source_ingestion import ingest_sources


router = APIRouter()

RADAR_LANES: dict[str, list[dict[str, Any]]] = {
    "policy": [
        {
            "source": "gdelt_news",
            "params": {
                "query": "(tariff OR regulation OR subsidy OR sanction OR export control OR executive order) (US OR United States)",
                "limit": 10,
                "timespan": "24h",
            },
        },
    ],
    "macro": [
        {"source": "fred_series", "params": {"series_id": "DGS10", "limit": 4}},
        {
            "source": "fred_series",
            "params": {
                "series_id": "BAMLH0A0HYM2",
                "limit": 4,
                "freshness_window_hours": 24 * 14,
            },
        },
        {
            "source": "gdelt_news",
            "params": {
                "query": "(Federal Reserve OR inflation OR payrolls OR unemployment OR recession OR Treasury yields)",
                "limit": 8,
                "timespan": "24h",
            },
        },
    ],
    "geopolitics": [
        {
            "source": "gdelt_news",
            "params": {
                "query": "(war OR sanctions OR Taiwan OR China OR Middle East OR Red Sea OR shipping disruption)",
                "limit": 10,
                "timespan": "24h",
            },
        },
    ],
    "commodities": [
        {
            "source": "gdelt_news",
            "params": {
                "query": "(oil OR natural gas OR copper OR soybean OR cattle OR coffee OR corn) (supply OR shortage OR inventory OR production OR drought OR demand)",
                "limit": 10,
                "timespan": "24h",
            },
        },
    ],
    "weather": [
        {"source": "noaa_alerts", "params": {"limit": 20}},
    ],
    "ipo": [
        {
            "source": "gdelt_news",
            "params": {
                "query": "(IPO OR initial public offering) (Nasdaq OR NYSE OR pricing OR files OR debut)",
                "limit": 10,
                "timespan": "48h",
            },
        },
    ],
}


def normalize_lanes(values: Any) -> list[str]:
    if values is None:
        return list(RADAR_LANES)
    if not isinstance(values, list):
        raise ValueError("lanes must be a list")
    output: list[str] = []
    for value in values:
        lane = str(value or "").strip().lower()
        if lane not in RADAR_LANES:
            raise ValueError(f"Unknown radar lane: {lane}")
        if lane not in output:
            output.append(lane)
    if not output:
        raise ValueError("At least one radar lane is required")
    return output


def _context_only(item: dict[str, Any], lane: str) -> dict[str, Any]:
    return {
        **item,
        "radar_lane": lane,
        "context_only": True,
        "gap_resolution_eligible": False,
        "trade_signal": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def run_market_event_radar(lanes: list[str] | None = None) -> dict[str, Any]:
    selected = normalize_lanes(lanes)
    radar_id = f"market_event_radar_{uuid4().hex}"
    lane_results: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []

    for lane in selected:
        ingestion = ingest_sources(RADAR_LANES[lane])
        items = [
            _context_only(item, lane)
            for item in (ingestion.get("evidence_items") or [])
            if isinstance(item, dict)
        ]
        evidence.extend(items)
        lane_results[lane] = {
            "status": "ok" if ingestion.get("failed_sources", 0) == 0 else "partial",
            "requested_sources": ingestion.get("requested_sources", 0),
            "successful_sources": ingestion.get("successful_sources", 0),
            "failed_sources": ingestion.get("failed_sources", 0),
            "item_count": len(items),
            "source_results": ingestion.get("source_results") or [],
        }

    packet = build_packet(evidence)
    payload = {
        "market_event_radar_id": radar_id,
        "lanes": selected,
        "lane_results": lane_results,
        "evidence": evidence,
        "evidence_summary": packet["summary"],
        "event_count": len(evidence),
        "created_at": utc_now(),
        "paper_mode": True,
        "context_only": True,
        "auto_case_creation": False,
        "gap_resolution_eligible": False,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(radar_id, "market_event_radar", OPPORTUNITY_LEDGER_CASE, payload)
    record_event(
        OPPORTUNITY_LEDGER_CASE,
        "MARKET_EVENT_RADAR_COMPLETE",
        entity_id=radar_id,
        payload={
            "lanes": selected,
            "event_count": len(evidence),
            "context_only": True,
            "auto_case_creation": False,
            "auto_trade_authority": False,
            "trade_execution_permission": False,
        },
    )
    return payload


@router.get("/opportunities/radar")
def market_event_radar_status():
    latest = latest_object("market_event_radar", case_id=OPPORTUNITY_LEDGER_CASE)
    return {
        "latest_radar": latest,
        "available_lanes": list(RADAR_LANES),
        "paper_mode": True,
        "context_only": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/opportunities/radar/run")
def run_market_event_radar_api(request: dict[str, Any] = Body(default={})):
    try:
        lanes = request.get("lanes")
        return run_market_event_radar(normalize_lanes(lanes) if lanes is not None else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
