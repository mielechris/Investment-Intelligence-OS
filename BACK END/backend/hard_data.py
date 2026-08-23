from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ledger import get_object, latest_object, list_objects, record_event, record_object
from provider_hardening import fetch_market_quote


router = APIRouter()
PAPER_MODE = True

LANES = {
    "memory_pricing": {
        "label": "Memory Pricing",
        "evidence_type": "market_data",
        "keywords": ("dram", "hbm", "nand", "price", "pricing", "spot", "contract"),
    },
    "supply_inventory": {
        "label": "Supply / Inventory",
        "evidence_type": "fundamental",
        "keywords": ("inventory", "bit shipment", "wafer", "utilization", "capacity", "supply", "starts"),
    },
    "hyperscaler_demand": {
        "label": "Hyperscaler Demand",
        "evidence_type": "fundamental",
        "keywords": ("hyperscaler", "order", "customer agreement", "ai-capex", "capex", "shipment", "qualification"),
    },
    "valuation_positioning": {
        "label": "Valuation / Positioning",
        "evidence_type": "market_data",
        "keywords": ("mu price", "valuation", "multiple", "consensus", "volume", "options", "portfolio", "positioning"),
    },
    "policy": {
        "label": "Policy",
        "evidence_type": "policy",
        "keywords": ("policy", "export control", "tariff", "incentive", "procurement", "government", "chips"),
    },
}

SOURCE_KINDS = {
    "official": {"reliability": 0.98, "source_type": "official", "admissible": True},
    "company_ir": {"reliability": 0.93, "source_type": "company", "admissible": True},
    "regulated_filing": {"reliability": 0.98, "source_type": "filing", "admissible": True},
    "exchange": {"reliability": 0.95, "source_type": "exchange", "admissible": True},
    "market_data": {"reliability": 0.90, "source_type": "market_data", "admissible": True},
    "licensed_data": {"reliability": 0.90, "source_type": "market_data", "admissible": True},
    "research": {"reliability": 0.80, "source_type": "research", "admissible": True},
    "manual_observation": {"reliability": 0.50, "source_type": "unknown", "admissible": False},
}


class HardDataCreateRequest(BaseModel):
    lane: str
    metric: str
    value_text: str
    unit: str | None = None
    period: str | None = None
    observed_at: str | None = None
    source_name: str
    source_url: str
    source_kind: str
    notes: str | None = None
    gap_requirement: str | None = None
    verified_against_source: bool = False
    permitted_use: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _validate_timestamp(value: str | None) -> str:
    if not value:
        return utc_now()
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="observed_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _match_requirement(case_id: str, lane: str, explicit: str | None = None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    decision = latest_object("committee_decision", case_id=case_id) or {}
    requirements = [str(item).strip() for item in decision.get("required_evidence") or [] if str(item).strip()]
    keywords = LANES.get(lane, {}).get("keywords", ())
    for requirement in requirements:
        lowered = requirement.lower()
        if any(keyword in lowered for keyword in keywords):
            return requirement
    return None


def create_hard_data(case_id: str, request: HardDataCreateRequest) -> dict[str, Any]:
    case = _require_case(case_id)
    lane = request.lane.strip().lower()
    source_kind = request.source_kind.strip().lower()
    if lane not in LANES:
        raise HTTPException(status_code=400, detail=f"Unknown hard-data lane: {lane}")
    if source_kind not in SOURCE_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown source_kind: {source_kind}")
    if len(request.metric.strip()) < 2 or len(request.value_text.strip()) < 1:
        raise HTTPException(status_code=400, detail="metric and value_text are required")
    parsed_url = urlparse(request.source_url.strip())
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise HTTPException(status_code=400, detail="source_url must be a valid https URL")
    if not request.verified_against_source:
        raise HTTPException(status_code=400, detail="Hard data must be explicitly verified against the cited source")
    if not request.permitted_use:
        raise HTTPException(status_code=400, detail="User must attest the source/data may be used for IIOS research")

    source_config = SOURCE_KINDS[source_kind]
    admitted = bool(source_config["admissible"])
    record_id = f"hard_data_{uuid4().hex}"
    record = {
        "hard_data_id": record_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "lane": lane,
        "lane_label": LANES[lane]["label"],
        "metric": request.metric.strip(),
        "value_text": request.value_text.strip(),
        "unit": (request.unit or "").strip() or None,
        "period": (request.period or "").strip() or None,
        "observed_at": _validate_timestamp(request.observed_at),
        "source_name": request.source_name.strip(),
        "source_url": request.source_url.strip(),
        "source_kind": source_kind,
        "source_type": source_config["source_type"],
        "reliability_score": source_config["reliability"],
        "notes": (request.notes or "").strip() or None,
        "gap_requirement": _match_requirement(case_id, lane, request.gap_requirement),
        "verified_against_source": True,
        "permitted_use": True,
        "admission_status": "ADMITTED" if admitted else "CONTEXT_ONLY",
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }
    record_object(record_id, "hard_data_record", case_id, record, topic=case.get("topic"))
    record_event(
        case_id,
        "HARD_DATA_RECORDED",
        entity_id=record_id,
        payload={
            "lane": lane,
            "source_kind": source_kind,
            "admission_status": record["admission_status"],
            "gap_requirement": record["gap_requirement"],
        },
    )
    return record


def _claim(record: dict[str, Any]) -> str:
    value = str(record.get("value_text") or "").strip()
    unit = str(record.get("unit") or "").strip()
    period = str(record.get("period") or "").strip()
    pieces = [f"{record.get('metric')}={value}"]
    if unit:
        pieces.append(unit)
    if period:
        pieces.append(f"period={period}")
    return " ".join(pieces)


def hard_data_evidence(case_id: str) -> list[dict[str, Any]]:
    records = list_objects(case_id, "hard_data_record")
    output: list[dict[str, Any]] = []
    for record in records:
        if record.get("admission_status") != "ADMITTED":
            continue
        lane = str(record.get("lane") or "")
        lane_config = LANES.get(lane)
        if not lane_config:
            continue
        output.append(
            {
                "source": record.get("source_name"),
                "source_type": record.get("source_type"),
                "evidence_type": lane_config["evidence_type"],
                "url": record.get("source_url"),
                "title": f"Hard data · {record.get('lane_label')} · {record.get('metric')}",
                "claim": _claim(record),
                "timestamp": record.get("observed_at"),
                "reliability_score": record.get("reliability_score"),
                "gap_requirement": record.get("gap_requirement"),
                "hard_data_id": record.get("hard_data_id"),
                "hard_data_lane": lane,
                "hard_data_verified": True,
            }
        )
    return output


def hard_data_status(case_id: str) -> dict[str, Any]:
    _require_case(case_id)
    records = list_objects(case_id, "hard_data_record")
    lanes = {}
    for key, config in LANES.items():
        lane_records = [item for item in records if item.get("lane") == key]
        admitted = [item for item in lane_records if item.get("admission_status") == "ADMITTED"]
        lanes[key] = {
            "label": config["label"],
            "total_records": len(lane_records),
            "admitted_records": len(admitted),
            "latest_record": admitted[-1] if admitted else (lane_records[-1] if lane_records else None),
        }
    return {
        "case_id": case_id,
        "lanes": lanes,
        "records": list(reversed(records[-30:])),
        "admitted_evidence_count": len(hard_data_evidence(case_id)),
        "paper_mode": True,
    }


def auto_capture_market_snapshot(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US").strip()
    quote = fetch_market_quote(ticker)
    added: list[dict[str, Any]] = []
    if quote.get("status") == "ok" and quote.get("current_price") is not None:
        item = (quote.get("items") or [{}])[0]
        request = HardDataCreateRequest(
            lane="valuation_positioning",
            metric=f"{ticker} market price",
            value_text=str(quote.get("current_price")),
            unit="USD/share",
            period="current market snapshot",
            observed_at=item.get("timestamp"),
            source_name=str(item.get("source") or quote.get("provider") or "Market data provider"),
            source_url=str(item.get("url") or "https://finance.yahoo.com/"),
            source_kind="market_data",
            notes="Automatically captured public market-price snapshot.",
            verified_against_source=True,
            permitted_use=True,
        )
        added.append(create_hard_data(case_id, request))
    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "ticker": ticker,
        "quote": quote,
        "records_added": added,
        "paper_mode": True,
    }


@router.get("/hard-data/schema")
def hard_data_schema():
    return {
        "lanes": LANES,
        "source_kinds": SOURCE_KINDS,
        "paper_mode": True,
        "paper_buy_enabled": False,
    }


@router.get("/hard-data/{case_id}")
def get_hard_data(case_id: str):
    return hard_data_status(case_id)


@router.post("/hard-data/{case_id}")
def add_hard_data(case_id: str, request: HardDataCreateRequest):
    return create_hard_data(case_id, request)


@router.post("/hard-data/{case_id}/auto-capture")
def auto_capture(case_id: str):
    return auto_capture_market_snapshot(case_id)
