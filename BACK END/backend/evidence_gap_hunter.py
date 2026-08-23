from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from evidence_engine import build_packet
from ledger import get_object, latest_object, list_objects, record_event, record_object
from provider_hardening import fetch_market_quote
from source_ingestion import ingest_sources


router = APIRouter()
PAPER_MODE = True
QUALIFIED_MIN_COMMITTEE_CONFIDENCE = 0.80
QUALIFIED_MIN_EVIDENCE_QUALITY = 0.65
QUALIFIED_MIN_EVIDENCE_COUNT = 12
QUALIFIED_MIN_WATCH_DESKS = 6

AGENT_ORDER = [
    "policy",
    "macro",
    "fundamentals",
    "market_structure",
    "commodities",
    "geo_weather",
    "skeptic",
    "portfolio",
]


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not case_id.startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _latest_decision(case_id: str) -> dict[str, Any]:
    decision = latest_object("committee_decision", case_id=case_id)
    if not decision:
        raise HTTPException(status_code=409, detail="Committee decision required before evidence-gap research")
    return decision


def _raw_items_from_packet(packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in (packet or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        raw = item.get("raw")
        output.append(raw if isinstance(raw, dict) else item)
    return output


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("url") or "").strip().lower(),
            str(item.get("claim") or item.get("title") or "").strip().lower(),
            str(item.get("timestamp") or item.get("published_at") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _desk_keys_for_gap(text: str) -> list[str]:
    value = text.lower()
    keys: list[str] = []
    mappings = [
        ("policy", ("policy", "tariff", "regulation", "government", "legislation", "subsidy")),
        ("macro", ("rate", "fed", "inflation", "macro", "liquidity", "credit", "dollar")),
        ("fundamentals", ("revenue", "earnings", "margin", "inventory", "capacity", "capex", "guidance", "demand", "valuation")),
        ("market_structure", ("price", "technical", "positioning", "crowding", "flow", "multiple", "market")),
        ("commodities", ("supply", "freight", "commodity", "materials", "production", "capacity")),
        ("geo_weather", ("war", "sanction", "geopolit", "weather", "drought", "taiwan", "china")),
        ("skeptic", ("risk", "falsif", "alternative", "assumption", "downside", "bear")),
        ("portfolio", ("portfolio", "correlation", "exposure", "concentration", "drawdown")),
    ]
    for key, terms in mappings:
        if any(term in value for term in terms):
            keys.append(key)
    if not keys:
        keys = ["fundamentals", "skeptic"]
    return keys


def build_gap_plan(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    decision = _latest_decision(case_id)
    requirements = [str(item).strip() for item in decision.get("required_evidence") or [] if str(item).strip()]
    if not requirements:
        requirements = [f"Confirm the current evidence supporting and contradicting: {case.get('topic', '')}"]

    monitor = latest_object("monitor_profile", case_id=case_id) or {}
    ticker = str(monitor.get("ticker") or "").strip()
    requests: list[dict[str, Any]] = []

    # One targeted current-news query per explicit evidence requirement.
    for requirement in requirements[:5]:
        requests.append(
            {
                "source": "google_news_rss",
                "params": {
                    "query": f"{case.get('topic', '')} {requirement}"[:350],
                    "limit": 5,
                },
                "gap": requirement,
            }
        )

    combined = " ".join(requirements).lower()
    if any(term in combined for term in ("rate", "fed", "yield", "macro", "credit")):
        requests.append({"source": "fred_series", "params": {"series_id": "DGS10", "limit": 4}, "gap": "macro/rates context"})

    # Known official-company research lane for the current Micron case.
    if ticker.upper() in {"MU", "MU.US"} or "micron" in str(case.get("topic", "")).lower():
        requests.extend(
            [
                {
                    "source": "official_web",
                    "params": {
                        "url": "https://investors.micron.com/overview/default.aspx",
                        "label": "Micron Investor Relations",
                        "keywords": ["HBM", "Strategic Customer Agreements", "investing", "demand"],
                        "limit": 4,
                        "evidence_type": "fundamental",
                        "reliability_score": 0.93,
                    },
                    "gap": "official company evidence",
                },
                {
                    "source": "official_web",
                    "params": {
                        "url": "https://investors.micron.com/quarterly-results",
                        "label": "Micron Quarterly Results",
                        "keywords": ["Revenue", "Prepared Remarks", "guidance", "Form 10-Q"],
                        "limit": 4,
                        "evidence_type": "fundamental",
                        "reliability_score": 0.93,
                    },
                    "gap": "official financial evidence",
                },
            ]
        )

    desk_keys: list[str] = []
    for requirement in requirements:
        for key in _desk_keys_for_gap(requirement):
            if key not in desk_keys:
                desk_keys.append(key)

    return {
        "case_id": case_id,
        "topic": case.get("topic"),
        "decision_id": decision.get("decision_id"),
        "requirements": requirements,
        "targeted_desks": desk_keys,
        "source_requests": requests,
        "ticker": ticker,
        "paper_mode": PAPER_MODE,
    }


def _qualification_assessment(
    committee: dict[str, Any], risk: dict[str, Any]
) -> dict[str, Any]:
    summary = committee.get("evidence_summary") or {}
    agents = committee.get("agents") or {}
    evidence_quality = float(summary.get("average_quality_score") or 0.0)
    evidence_count = int(summary.get("evidence_count") or 0)
    confidence = float(committee.get("confidence") or 0.0)
    required_evidence = [str(item) for item in committee.get("required_evidence") or [] if str(item).strip()]
    watch_desks = sum(1 for key in AGENT_ORDER if (agents.get(key) or {}).get("disposition") == "WATCH")

    checks = {
        "committee_watch": committee.get("disposition") == "WATCH",
        "committee_confidence": confidence >= QUALIFIED_MIN_COMMITTEE_CONFIDENCE,
        "evidence_quality": evidence_quality >= QUALIFIED_MIN_EVIDENCE_QUALITY,
        "evidence_count": evidence_count >= QUALIFIED_MIN_EVIDENCE_COUNT,
        "no_critical_flags": not bool(summary.get("critical_flags")),
        "required_evidence_resolved": len(required_evidence) == 0,
        "risk_clear_for_watch": risk.get("decision") == "WATCH_ONLY" and not (risk.get("triggered_rules") or []),
        "watch_desk_quorum": watch_desks >= QUALIFIED_MIN_WATCH_DESKS,
        "fundamentals_watch": (agents.get("fundamentals") or {}).get("disposition") == "WATCH",
        "skeptic_watch": (agents.get("skeptic") or {}).get("disposition") == "WATCH",
    }
    unmet = [key for key, passed in checks.items() if not passed]
    qualified = not unmet
    return {
        "stage": "QUALIFIED_BUY_CANDIDATE" if qualified else str(committee.get("disposition") or "NO_TRADE"),
        "qualified_buy_candidate": qualified,
        "paper_buy_enabled": False,
        "checks": checks,
        "unmet_requirements": unmet,
        "thresholds": {
            "committee_confidence": QUALIFIED_MIN_COMMITTEE_CONFIDENCE,
            "evidence_quality": QUALIFIED_MIN_EVIDENCE_QUALITY,
            "evidence_count": QUALIFIED_MIN_EVIDENCE_COUNT,
            "watch_desk_quorum": QUALIFIED_MIN_WATCH_DESKS,
        },
        "observed": {
            "committee_confidence": confidence,
            "evidence_quality": evidence_quality,
            "evidence_count": evidence_count,
            "watch_desks": watch_desks,
            "remaining_required_evidence": required_evidence,
        },
        "paper_mode": True,
        "live_execution": False,
    }


def run_gap_hunt(case_id: str) -> dict[str, Any]:
    case = _require_case(case_id)
    plan = build_gap_plan(case_id)
    prior_decision = _latest_decision(case_id)
    prior_packet = get_object(str(prior_decision.get("evidence_packet_id") or ""))
    prior_raw = _raw_items_from_packet(prior_packet)

    ingestion_requests = [
        {"source": item["source"], "params": item.get("params") or {}}
        for item in plan["source_requests"]
    ]
    ingestion = ingest_sources(ingestion_requests)
    quote = fetch_market_quote(str(plan.get("ticker") or ""))
    new_raw = list(ingestion.get("evidence_items") or []) + list(quote.get("items") or [])
    combined = _dedupe(prior_raw + new_raw)
    packet = build_packet(combined)

    packet_id = f"packet_gap_{uuid4().hex}"
    persisted_packet = {
        **packet,
        "evidence_packet_id": packet_id,
        "case_id": case_id,
        "purpose": "EVIDENCE_GAP_HUNT",
        "gap_requirements": plan["requirements"],
    }
    record_object(packet_id, "evidence_packet", case_id, persisted_packet, parent_id=prior_decision.get("decision_id"), topic=case.get("topic"))
    record_event(case_id, "EVIDENCE_GAP_PACKET_LOCKED", entity_id=packet_id, payload={"requirements": plan["requirements"], "evidence_count": packet["summary"]["evidence_count"], "average_quality_score": packet["summary"]["average_quality_score"]})

    from main import build_committee, evaluate_decision, run_specialist, submit_paper_order

    targeted_results = []
    for agent_key in plan["targeted_desks"]:
        result = run_specialist(agent_key, str(case.get("topic") or ""), packet["items"])
        result_id = f"gap_agent_{uuid4().hex}"
        persisted = {**result, "gap_agent_result_id": result_id, "case_id": case_id, "evidence_packet_id": packet_id}
        record_object(result_id, "gap_agent_result", case_id, persisted, parent_id=packet_id, topic=case.get("topic"))
        targeted_results.append(persisted)

    review_case = {
        **case,
        "evidence_packet_id": packet_id,
        "evidence": packet["items"],
        "evidence_summary": packet["summary"],
    }
    committee = build_committee(review_case)
    risk = evaluate_decision(committee)
    execution = submit_paper_order({"risk_authorization_id": risk["risk_authorization_id"]})
    assessment = _qualification_assessment(committee, risk)

    assessment_id = f"qualification_{uuid4().hex}"
    assessment_payload = {
        **assessment,
        "qualification_assessment_id": assessment_id,
        "case_id": case_id,
        "decision_id": committee.get("decision_id"),
        "evidence_packet_id": packet_id,
    }
    record_object(assessment_id, "qualification_assessment", case_id, assessment_payload, parent_id=committee.get("decision_id"), topic=case.get("topic"))

    hunt_id = f"gap_hunt_{uuid4().hex}"
    hunt = {
        "gap_hunt_id": hunt_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "plan": plan,
        "ingestion": ingestion,
        "quote": quote,
        "evidence_summary": packet["summary"],
        "targeted_desk_results": targeted_results,
        "committee": committee,
        "risk": risk,
        "execution": execution,
        "qualification": assessment_payload,
        "paper_mode": True,
        "live_execution": False,
    }
    record_object(hunt_id, "gap_hunt", case_id, hunt, parent_id=assessment_id, topic=case.get("topic"))
    record_event(case_id, "EVIDENCE_GAP_HUNT_COMPLETE", entity_id=hunt_id, payload={"stage": assessment["stage"], "qualified_buy_candidate": assessment["qualified_buy_candidate"], "unmet_requirements": assessment["unmet_requirements"]})
    return hunt


@router.get("/gap-hunter/{case_id}/plan")
def gap_plan(case_id: str):
    return build_gap_plan(case_id)


@router.post("/gap-hunter/{case_id}/run")
def gap_run(case_id: str):
    return run_gap_hunt(case_id)
