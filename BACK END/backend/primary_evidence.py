from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from evidence_engine import build_packet
from ledger import get_object, latest_object, list_objects, record_event, record_object
from official_sources import fetch_official_web
from primary_evidence_contracts import CONTRACTS, contract_for_requirement, coverage_for_requirement
from provider_hardening import _request_bytes, fetch_market_quote, fetch_sec_companyfacts


router = APIRouter()
PAPER_MODE = True
MICRON_CIK = "723125"

SEC_FACT_MAP = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": ("micron_financials", "revenue"),
    "Revenues": ("micron_financials", "revenue"),
    "InventoryNet": ("micron_financials", "inventory"),
    "NetCashProvidedByUsedInOperatingActivities": ("micron_financials", "cash_flow"),
    "CashAndCashEquivalentsAtCarryingValue": ("micron_financials", "cash"),
    "PaymentsToAcquirePropertyPlantAndEquipment": ("micron_financials", "capex"),
    "LongTermDebtCurrent": ("micron_financials", "debt"),
    "LongTermDebtNoncurrent": ("micron_financials", "debt"),
    "LongTermDebtAndFinanceLeaseObligationsCurrent": ("micron_financials", "debt"),
    "WeightedAverageNumberOfDilutedSharesOutstanding": ("valuation_market", "diluted_shares"),
}

SEC_TAGS = list(SEC_FACT_MAP)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _requirements(case_id: str) -> list[str]:
    decision = latest_object("committee_decision", case_id=case_id) or {}
    return [str(item).strip() for item in decision.get("required_evidence") or [] if str(item).strip()]


def _requirement_for_lane(case_id: str, lane: str) -> str | None:
    for requirement in _requirements(case_id):
        matched_lane, _ = contract_for_requirement(requirement)
        if matched_lane == lane:
            return requirement
    return None


def _fact_from_sec_title(title: str) -> tuple[str, str] | None:
    for tag, mapping in SEC_FACT_MAP.items():
        if tag.lower() in title.lower():
            return mapping
    return None


def _fact_from_keyword(lane: str, keyword: str) -> str | None:
    value = keyword.lower()
    mappings = {
        "micron_financials": [
            ("hbm", "hbm_margin"),
            ("inventory", "inventory"),
            ("free cash flow", "cash_flow"),
            ("capex", "capex"),
            ("average selling price", "asp_sensitivity"),
            ("asp", "asp_sensitivity"),
            ("pricing", "asp_sensitivity"),
        ],
        "supply_inventory": [
            ("inventory", "inventory"),
            ("bit shipment", "bit_shipments"),
            ("wafer", "wafer_starts"),
            ("utilization", "utilization"),
            ("capacity", "capacity"),
            ("yield", "hbm_packaging_yield"),
            ("hbm", "hbm_packaging_yield"),
        ],
        "hyperscaler_demand": [
            ("capital expenditure", "ai_capex"),
            ("capex", "ai_capex"),
            ("server", "server_activity"),
            ("utilization", "server_activity"),
            ("backlog", "backlog"),
            ("cancellation", "cancellations"),
            ("memory", "memory_terms"),
        ],
        "policy": [
            ("chips", "incentives"),
            ("award", "incentives"),
            ("incentive", "incentives"),
            ("export control", "export_controls"),
            ("advanced computing", "export_controls"),
            ("tariff", "tariffs"),
            ("effective", "effective_dates"),
            ("supply", "transmission"),
            ("demand", "transmission"),
        ],
    }
    for term, fact in mappings.get(lane, []):
        if term in value:
            return fact
    return None


def _source_grade(source_type: str) -> str:
    value = source_type.lower()
    if value in {"official", "regulatory", "filing"}:
        return "PRIMARY_OFFICIAL"
    if value == "company":
        return "PRIMARY_COMPANY"
    if value == "market_data":
        return "HARD_MARKET_DATA"
    return "CONTEXT"


def _persist_record(case_id: str, case: dict[str, Any], lane: str, fact_key: str, item: dict[str, Any]) -> dict[str, Any] | None:
    requirement = _requirement_for_lane(case_id, lane)
    claim = str(item.get("claim") or item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    if not claim or not url:
        return None

    existing = list_objects(case_id, "primary_evidence_record")
    fingerprint = (lane, fact_key, url.lower(), claim.lower())
    for row in existing:
        prior = (
            str(row.get("lane") or ""),
            str(row.get("fact_key") or ""),
            str(row.get("source_url") or "").lower(),
            str(row.get("claim") or "").lower(),
        )
        if prior == fingerprint:
            return row

    source_type = str(item.get("source_type") or "official").lower()
    evidence_type = str(item.get("evidence_type") or ("policy" if lane == "policy" else "fundamental"))
    record_id = f"primary_evidence_{uuid4().hex}"
    record = {
        "primary_evidence_id": record_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "lane": lane,
        "lane_label": CONTRACTS[lane]["label"],
        "fact_key": fact_key,
        "claim": claim,
        "source_name": str(item.get("source") or "Official source"),
        "source_url": url,
        "source_type": source_type,
        "source_grade": _source_grade(source_type),
        "evidence_type": evidence_type,
        "observed_at": item.get("timestamp") or utc_now(),
        "reliability_score": float(item.get("reliability_score") or 0.95),
        "gap_requirement": requirement,
        "gap_resolution_eligible": source_type in {"official", "regulatory", "filing", "company", "market_data"},
        "verified_public_source": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "created_at": utc_now(),
    }
    record_object(record_id, "primary_evidence_record", case_id, record, topic=case.get("topic"))
    record_event(
        case_id,
        "PRIMARY_EVIDENCE_RECORDED",
        entity_id=record_id,
        payload={"lane": lane, "fact_key": fact_key, "source_grade": record["source_grade"], "gap_requirement": requirement},
    )
    return record


def _capture_sec(case_id: str, case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        items = fetch_sec_companyfacts({"cik": MICRON_CIK, "label": "Micron Technology", "tags": SEC_TAGS, "limit": 30})
        for item in items:
            mapping = _fact_from_sec_title(str(item.get("title") or ""))
            if not mapping:
                continue
            lane, fact_key = mapping
            normalized = {**item, "source_type": "filing", "evidence_type": "fundamental"}
            record = _persist_record(case_id, case, lane, fact_key, normalized)
            if record:
                added.append(record)
    except Exception as exc:
        failures.append(f"SEC company facts: {type(exc).__name__}: {exc}")
    return added, failures


def _capture_market(case_id: str, case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    profile = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(profile.get("ticker") or "MU.US")
    try:
        quote = fetch_market_quote(ticker)
        if quote.get("status") == "ok":
            for item in quote.get("items") or []:
                normalized = {**item, "claim": f"{ticker} current market price={quote.get('current_price')}", "source_type": "market_data", "evidence_type": "market_data"}
                record = _persist_record(case_id, case, "valuation_market", "market_price", normalized)
                if record:
                    added.append(record)
        else:
            failures.append(f"Market quote: {quote.get('error') or 'unavailable'}")
    except Exception as exc:
        failures.append(f"Market quote: {type(exc).__name__}: {exc}")
    return added, failures


def _capture_official_page(case_id: str, case: dict[str, Any], lane: str, url: str, label: str, keywords: list[str], reliability: float = 0.94) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        items = fetch_official_web({
            "url": url,
            "label": label,
            "keywords": keywords,
            "limit": min(len(keywords), 6),
            "evidence_type": "policy" if lane == "policy" else "fundamental",
            "reliability_score": reliability,
            "window_chars": 700,
        })
        for item in items:
            keyword = str(item.get("title") or "").split(":")[-1].strip()
            fact_key = _fact_from_keyword(lane, keyword) or _fact_from_keyword(lane, str(item.get("claim") or ""))
            if not fact_key:
                continue
            record = _persist_record(case_id, case, lane, fact_key, item)
            if record:
                added.append(record)
    except Exception as exc:
        failures.append(f"{label}: {type(exc).__name__}: {exc}")
    return added, failures


def _capture_micron_ir(case_id: str, case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    for lane, keywords in (
        ("micron_financials", ["HBM", "inventory", "free cash flow", "capex", "average selling price", "pricing"]),
        ("supply_inventory", ["inventory", "bit shipments", "wafer", "utilization", "capacity", "yield", "HBM"]),
    ):
        records, errors = _capture_official_page(
            case_id,
            case,
            lane,
            "https://investors.micron.com/quarterly-results",
            "Micron Quarterly Results",
            keywords,
            0.95,
        )
        added.extend(records)
        failures.extend(errors)
    return added, failures


def _capture_peer_supply(case_id: str, case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    sources = [
        ("https://news.skhynix.com/", "SK hynix Official Newsroom"),
        ("https://news.samsung.com/global/", "Samsung Global Newsroom"),
    ]
    for url, label in sources:
        records, errors = _capture_official_page(case_id, case, "supply_inventory", url, label, ["HBM", "DRAM", "capacity", "yield", "production", "inventory"], 0.92)
        added.extend(records)
        failures.extend(errors)
    return added, failures


def _capture_hyperscalers(case_id: str, case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    sources = [
        ("https://www.microsoft.com/en-us/Investor", "Microsoft Investor Relations"),
        ("https://investor.atmeta.com/", "Meta Investor Relations"),
        ("https://ir.aboutamazon.com/", "Amazon Investor Relations"),
        ("https://abc.xyz/investor/", "Alphabet Investor Relations"),
    ]
    for url, label in sources:
        records, errors = _capture_official_page(case_id, case, "hyperscaler_demand", url, label, ["capital expenditures", "capex", "AI", "server", "data center", "backlog"], 0.93)
        added.extend(records)
        failures.extend(errors)
    return added, failures


def _federal_register_policy(case_id: str, case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        url = "https://www.federalregister.gov/api/v1/documents.json?" + urlencode({"per_page": 20, "order": "newest", "conditions[term]": "semiconductor export controls tariff"})
        payload = json.loads(_request_bytes(url, provider="federal_register", minimum_interval_seconds=0.4, retries=2, cache_ttl_seconds=30 * 60).decode("utf-8"))
        for row in payload.get("results") or []:
            title = str(row.get("title") or "")
            combined = title.lower()
            fact_key = None
            if "export" in combined or "advanced computing" in combined:
                fact_key = "export_controls"
            elif "tariff" in combined:
                fact_key = "tariffs"
            elif "semiconductor" in combined or "chips" in combined:
                fact_key = "incentives"
            if not fact_key:
                continue
            item = {
                "source": "Federal Register",
                "source_type": "regulatory",
                "evidence_type": "policy",
                "url": row.get("html_url") or row.get("json_url") or url,
                "title": title,
                "claim": f"{title}; publication_date={row.get('publication_date')}; document_number={row.get('document_number')}",
                "timestamp": row.get("publication_date"),
                "reliability_score": 0.99,
            }
            record = _persist_record(case_id, case, "policy", fact_key, item)
            if record:
                added.append(record)
    except Exception as exc:
        failures.append(f"Federal Register: {type(exc).__name__}: {exc}")
    return added, failures


def _capture_policy(case_id: str, case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    for url, label, keywords in [
        ("https://www.nist.gov/chips", "NIST CHIPS for America", ["CHIPS", "award", "incentive", "semiconductor", "capacity"]),
        ("https://www.bis.gov/", "U.S. Bureau of Industry and Security", ["export controls", "advanced computing", "semiconductor", "effective"]),
    ]:
        records, errors = _capture_official_page(case_id, case, "policy", url, label, keywords, 0.98)
        added.extend(records)
        failures.extend(errors)
    records, errors = _federal_register_policy(case_id, case)
    added.extend(records)
    failures.extend(errors)
    return added, failures


def primary_evidence_evidence(case_id: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for record in list_objects(case_id, "primary_evidence_record"):
        if record.get("gap_resolution_eligible") is not True:
            continue
        output.append({
            "source": record.get("source_name"),
            "source_type": record.get("source_type"),
            "evidence_type": record.get("evidence_type"),
            "url": record.get("source_url"),
            "title": f"Primary evidence · {record.get('lane_label')} · {record.get('fact_key')}",
            "claim": record.get("claim"),
            "timestamp": record.get("observed_at"),
            "reliability_score": record.get("reliability_score"),
            "gap_requirement": record.get("gap_requirement"),
            "gap_resolution_eligible": True,
            "primary_evidence_id": record.get("primary_evidence_id"),
            "primary_evidence_lane": record.get("lane"),
            "primary_fact_key": record.get("fact_key"),
            "primary_source_grade": record.get("source_grade"),
        })
    return output


def _lane_status(case_id: str, lane: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    requirement = _requirement_for_lane(case_id, lane)
    lane_records = [row for row in records if row.get("lane") == lane and row.get("gap_resolution_eligible") is True]
    raw = [
        {
            "claim": row.get("claim"),
            "title": row.get("fact_key"),
            "source": row.get("source_name"),
            "url": row.get("source_url"),
            "source_type": row.get("source_type"),
            "evidence_type": row.get("evidence_type"),
            "timestamp": row.get("observed_at"),
            "reliability_score": row.get("reliability_score"),
            "primary_fact_key": row.get("fact_key"),
        }
        for row in lane_records
    ]
    packet = build_packet(raw)
    current_raw = [item.get("raw") for item in packet.get("items") or [] if not item.get("stale") and not item.get("missing_fields") and float(item.get("quality_score") or 0) >= 0.65]
    if requirement:
        coverage = coverage_for_requirement(requirement, [item for item in current_raw if isinstance(item, dict)])
    else:
        contract = CONTRACTS[lane]
        synthetic = f"{contract['label']} {' '.join(contract['match_terms'])}"
        coverage = coverage_for_requirement(synthetic, [item for item in current_raw if isinstance(item, dict)])
    coverage = coverage or {"covered_facts": 0, "total_facts": len(CONTRACTS[lane]["facts"]), "coverage_ratio": 0, "coverage_gate_passed": False, "facts": []}
    pct = int(round(float(coverage.get("coverage_ratio") or 0) * 100))
    status = "COMPLETE_FACT_COVERAGE" if coverage.get("coverage_gate_passed") else "PARTIAL" if pct else "OPEN"
    return {
        "lane": lane,
        "label": CONTRACTS[lane]["label"],
        "requirement": requirement,
        "status": status,
        "coverage_pct": pct,
        "covered_facts": coverage.get("covered_facts"),
        "total_facts": coverage.get("total_facts"),
        "facts": coverage.get("facts") or [],
        "current_high_quality_records": len(current_raw),
        "source_count": len({str(row.get("source_url") or "") for row in lane_records if row.get("source_url")}),
        "latest_records": list(reversed(lane_records[-5:])),
        "note": "Automatic independent memory-pricing providers are not configured; licensed or manually verified hard data is required." if lane == "memory_pricing" else None,
    }


def primary_evidence_status(case_id: str) -> dict[str, Any]:
    _require_case(case_id)
    records = list_objects(case_id, "primary_evidence_record")
    requirements = _requirements(case_id)

    relevant_lanes = {
        matched_lane
        for requirement in requirements
        for matched_lane, _ in [contract_for_requirement(requirement)]
        if matched_lane
    }

    # The v0.12 primary-evidence floor was originally built
    # specifically for Micron. Do not manufacture irrelevant
    # semiconductor requirements for unrelated companies.
    lanes = {
        lane: _lane_status(case_id, lane, records)
        for lane in relevant_lanes
    }
    latest_hunt = latest_object("gap_hunt", case_id=case_id) or {}
    matrix = latest_hunt.get("resolution_matrix") or []
    resolution_by_requirement = {str(row.get("requirement")): row for row in matrix if isinstance(row, dict)}
    for lane in lanes.values():
        requirement = lane.get("requirement")
        lane["latest_resolution"] = resolution_by_requirement.get(str(requirement)) if requirement else None
    return {
        "case_id": case_id,
        "lanes": lanes,
        "records": list(reversed(records[-40:])),
        "paper_mode": True,
        "live_execution": False,
    }


def auto_capture_primary(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    captured: list[dict[str, Any]] = []
    failures: list[str] = []
    for fn in (_capture_sec, _capture_market, _capture_micron_ir, _capture_peer_supply, _capture_hyperscalers, _capture_policy):
        records, errors = fn(case_id, case)
        captured.extend(records)
        failures.extend(errors)
    snapshot_id = f"primary_snapshot_{uuid4().hex}"
    snapshot = {
        "primary_snapshot_id": snapshot_id,
        "case_id": case_id,
        "captured_record_ids": sorted({str(row.get("primary_evidence_id")) for row in captured if row.get("primary_evidence_id")}),
        "records_seen_or_added": len(captured),
        "failures": failures,
        "memory_pricing_auto_provider": "NOT_CONFIGURED_REQUIRES_INDEPENDENT_LICENSED_OR_VERIFIED_SOURCE",
        "created_at": utc_now(),
        "paper_mode": True,
        "trade_execution_permission": False,
    }
    record_object(snapshot_id, "primary_evidence_snapshot", case_id, snapshot, topic=case.get("topic"))
    record_event(case_id, "PRIMARY_EVIDENCE_CAPTURE_COMPLETE", entity_id=snapshot_id, payload={"records": len(captured), "failures": len(failures)})
    return {**snapshot, "status": primary_evidence_status(case_id)}


@router.get("/primary-evidence/{case_id}")
def get_primary_evidence(case_id: str):
    return primary_evidence_status(case_id)


@router.post("/primary-evidence/{case_id}/auto-capture")
def capture_primary_evidence(case_id: str):
    return auto_capture_primary(case_id)
