from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Body, HTTPException

from evidence_engine import build_packet
from ledger import get_object, record_event, record_object, utc_now
from provider_hardening import SEC_USER_AGENT, _request_bytes


router = APIRouter()
IPO_LEDGER_CASE = "ipo_monitor"
IPO_FORMS = ("S-1", "S-1/A", "F-1", "F-1/A", "EFFECT", "424B4")
DEFAULT_COUNT_PER_FORM = 10
MAX_COUNT_PER_FORM = 25
SEC_CURRENT_FILINGS_URL = "https://www.sec.gov/cgi-bin/browse-edgar"


def _feed_url(form_type: str, count: int) -> str:
    query = urlencode({
        "action": "getcurrent",
        "type": form_type,
        "owner": "include",
        "count": max(1, min(int(count), MAX_COUNT_PER_FORM)),
        "output": "atom",
    })
    return f"{SEC_CURRENT_FILINGS_URL}?{query}"


def _text(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text.strip()


def _filing_id(form_type: str, url: str | None, title: str) -> str:
    digest = hashlib.sha256(f"{form_type}\0{url or ''}\0{title}".encode("utf-8")).hexdigest()
    return f"ipo_filing_{digest[:32]}"


def parse_atom_filings(xml_text: str, *, form_type: str, observed_at: str | None = None) -> list[dict[str, Any]]:
    observed_at = observed_at or utc_now()
    root = ET.fromstring(xml_text)
    namespace = {"a": "http://www.w3.org/2005/Atom"}
    items: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", namespace):
        title = _text(entry.find("a:title", namespace)) or f"{form_type} filing"
        summary = _text(entry.find("a:summary", namespace))
        updated = _text(entry.find("a:updated", namespace)) or None
        link_node = entry.find("a:link", namespace)
        url = link_node.attrib.get("href") if link_node is not None else None
        filing_id = _filing_id(form_type, url, title)
        items.append({
            "ipo_filing_id": filing_id,
            "form_type": form_type,
            "title": title,
            "summary": summary,
            "url": url,
            "published_at": updated,
            "observed_at": observed_at,
            "source": "SEC EDGAR",
            "source_type": "official_filing",
            "evidence_type": "ipo_filing",
            "reliability_score": 0.99,
            "promoted_case_id": None,
            "research_only": True,
            "trade_signal": False,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": observed_at,
        })
    return items


def scan_recent_ipo_filings(count_per_form: int = DEFAULT_COUNT_PER_FORM) -> dict[str, Any]:
    count_per_form = max(1, min(int(count_per_form), MAX_COUNT_PER_FORM))
    observed_at = utc_now()
    items: list[dict[str, Any]] = []
    provider_results: list[dict[str, Any]] = []

    for form_type in IPO_FORMS:
        url = _feed_url(form_type, count_per_form)
        try:
            body = _request_bytes(
                url,
                accept="application/atom+xml, application/xml, text/xml",
                user_agent=SEC_USER_AGENT,
                provider="sec_ipo",
                minimum_interval_seconds=0.25,
                retries=2,
                cache_ttl_seconds=5 * 60,
            ).decode("utf-8", errors="replace")
            rows = parse_atom_filings(body, form_type=form_type, observed_at=observed_at)
            provider_results.append({"form_type": form_type, "status": "ok", "item_count": len(rows), "error": None})
            items.extend(rows)
        except Exception as exc:
            provider_results.append({"form_type": form_type, "status": "error", "item_count": 0, "error": f"{type(exc).__name__}: {exc}"})

    latest_by_id: dict[str, dict[str, Any]] = {}
    for row in items:
        latest_by_id[str(row["ipo_filing_id"])] = row
    unique = sorted(latest_by_id.values(), key=lambda row: str(row.get("published_at") or row.get("observed_at") or ""), reverse=True)

    for row in unique:
        prior = get_object(str(row["ipo_filing_id"]))
        if prior and prior.get("promoted_case_id"):
            row["promoted_case_id"] = prior.get("promoted_case_id")
        record_object(str(row["ipo_filing_id"]), "ipo_filing_observation", IPO_LEDGER_CASE, row, topic=row.get("title"))

    scan_id = f"ipo_scan_{hashlib.sha256(observed_at.encode()).hexdigest()[:24]}"
    scan = {
        "ipo_scan_id": scan_id,
        "forms": list(IPO_FORMS),
        "count_per_form": count_per_form,
        "filing_count": len(unique),
        "filings": unique,
        "provider_results": provider_results,
        "successful_forms": sum(1 for row in provider_results if row["status"] == "ok"),
        "failed_forms": sum(1 for row in provider_results if row["status"] != "ok"),
        "automatic_promotion": False,
        "automatic_agent_run": False,
        "research_only": True,
        "trade_signal": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": observed_at,
    }
    record_object(scan_id, "ipo_monitor_scan", IPO_LEDGER_CASE, scan)
    record_event(IPO_LEDGER_CASE, "IPO_MONITOR_SCAN_COMPLETE", entity_id=scan_id, payload={"filing_count": len(unique), "failed_forms": scan["failed_forms"], "trade_execution_permission": False})
    return scan


def _filing_evidence(filing: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "SEC EDGAR",
        "source_type": "official_filing",
        "evidence_type": "ipo_filing",
        "url": filing.get("url"),
        "title": filing.get("title"),
        "claim": f"SEC {filing.get('form_type')} filing observed: {filing.get('title')}. {filing.get('summary') or ''}".strip(),
        "timestamp": filing.get("published_at") or filing.get("observed_at"),
        "reliability_score": 0.99,
        "form": filing.get("form_type"),
        "ipo_filing_id": filing.get("ipo_filing_id"),
    }


def promote_ipo_filing(filing_id: str) -> dict[str, Any]:
    filing = get_object(filing_id)
    if not filing or not str(filing_id).startswith("ipo_filing_"):
        raise HTTPException(status_code=404, detail="IPO filing observation not found")
    if filing.get("promoted_case_id"):
        existing = get_object(str(filing["promoted_case_id"]))
        if existing:
            return {"case": existing, "filing": filing, "already_promoted": True, "paper_mode": True, "trade_execution_permission": False}

    from uuid import uuid4

    case_id = f"case_{uuid4().hex}"
    packet_id = f"packet_{uuid4().hex}"
    evidence = [_filing_evidence(filing)]
    packet = {**build_packet(evidence), "evidence_packet_id": packet_id, "case_id": case_id}
    topic = f"IPO review — {filing.get('title') or filing.get('form_type') or filing_id}"
    case = {
        "case_id": case_id,
        "topic": topic,
        "evidence_packet_id": packet_id,
        "evidence": packet.get("items") or [],
        "evidence_summary": packet.get("summary") or {},
        "source_ipo_filing_id": filing_id,
        "created_by": "SEC_IPO_MONITOR_V1",
        "created_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(case_id, "case", case_id, case, topic=topic)
    record_object(packet_id, "evidence_packet", case_id, packet, parent_id=case_id, topic=topic)

    updated = {**filing, "promoted_case_id": case_id, "promoted_at": utc_now()}
    record_object(filing_id, "ipo_filing_observation", IPO_LEDGER_CASE, updated, topic=filing.get("title"))
    record_event(case_id, "IPO_FILING_PROMOTED_TO_GOVERNED_CASE", entity_id=case_id, payload={"source_ipo_filing_id": filing_id, "automatic_agent_run": False, "trade_execution_permission": False})
    return {"case": case, "filing": updated, "already_promoted": False, "next_step": f"POST /orchestration/{case_id}/run", "paper_mode": True, "trade_execution_permission": False, "live_execution": False}


def ipo_monitor_plan() -> dict[str, Any]:
    return {
        "provider": "SEC_EDGAR_CURRENT_FILINGS",
        "forms": list(IPO_FORMS),
        "count_per_form_default": DEFAULT_COUNT_PER_FORM,
        "count_per_form_max": MAX_COUNT_PER_FORM,
        "source_user_agent_configured": bool(SEC_USER_AGENT),
        "automatic_scan": False,
        "automatic_promotion": False,
        "automatic_agent_run": False,
        "promotion_target": "STANDARD_IIOS_GOVERNED_CASE",
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/ipo-monitor/plan")
def get_ipo_monitor_plan():
    return ipo_monitor_plan()


@router.post("/ipo-monitor/scan")
def run_ipo_monitor_scan(request: dict[str, Any] = Body(default={})):
    return scan_recent_ipo_filings(int(request.get("count_per_form") or DEFAULT_COUNT_PER_FORM))


@router.post("/ipo-monitor/filings/{filing_id}/promote")
def promote_ipo_monitor_filing(filing_id: str):
    return promote_ipo_filing(filing_id)
