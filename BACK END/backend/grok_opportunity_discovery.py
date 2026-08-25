from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from grok_social_intelligence import fetch_grok_social_context, grok_plan
from ledger import get_object, record_event, record_object, utc_now
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE, score_candidate
from provider_hardening import fetch_gdelt_news, fetch_market_quote


router = APIRouter()
GROK_EXPERIMENT_LEDGER_CASE = "grok_experiment"
MAX_GROK_CANDIDATES = 8
MIN_NOMINATION_SOURCES = 2


def _clean_ticker(value: Any) -> str | None:
    ticker = str(value or "").strip().upper()
    if not ticker or len(ticker) > 12:
        return None
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,11}", ticker):
        return None
    return ticker


def _normalize_urls(values: Any, verified: set[str]) -> list[str]:
    raw = values if isinstance(values, list) else []
    output: list[str] = []
    for value in raw:
        text = str(value or "").strip()
        normalized = text.split("?", 1)[0].rstrip("/")
        if normalized in verified and normalized not in output:
            output.append(normalized)
    return output


def _confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return round(max(0.0, min(0.60, score)), 4)


def discover_grok_opportunities(query: str, *, days: int = 2, max_candidates: int = 5, persist: bool = True) -> dict[str, Any]:
    query = " ".join(str(query or "").split()).strip()
    if not query:
        raise ValueError("query is required")
    plan = grok_plan()
    if not plan["enabled"]:
        raise RuntimeError("Grok experiment is disabled")
    if not plan["api_key_configured"]:
        raise RuntimeError("XAI_API_KEY is not configured")

    context = fetch_grok_social_context(
        f"Find public-market tickers receiving unusually important, differentiated, or fast-moving discussion relevant to: {query}",
        days=days,
    )
    verified = {str(url).split("?", 1)[0].rstrip("/") for url in context.get("citation_urls") or []}
    raw_candidates = context.get("raw_candidate_tickers") if isinstance(context.get("raw_candidate_tickers"), list) else []
    max_candidates = max(1, min(int(max_candidates), MAX_GROK_CANDIDATES))
    admitted: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        ticker = _clean_ticker(raw.get("ticker"))
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        source_urls = _normalize_urls(raw.get("source_urls"), verified)
        reasons = []
        if len(source_urls) < MIN_NOMINATION_SOURCES:
            reasons.append("INSUFFICIENT_VERIFIED_X_SOURCE_DIVERSITY")
        rationale = " ".join(str(raw.get("rationale") or "").split()).strip()
        if not rationale:
            reasons.append("MISSING_RATIONALE")

        candidate_id = f"grok_opportunity_{uuid4().hex}"
        candidate = {
            "grok_opportunity_candidate_id": candidate_id,
            "ticker": ticker,
            "rationale": rationale,
            "advisory_confidence": _confidence(raw.get("confidence")),
            "source_urls": source_urls,
            "source_count": len(source_urls),
            "status": "QUARANTINED" if reasons else "NOMINATED_FOR_IIOS_REVALIDATION",
            "quarantine_reasons": reasons,
            "eligible_for_iios_revalidation": not reasons,
            "eligible_for_standard_promotion": False,
            "standard_candidate_id": None,
            "created_by": "GROK_X_EXPERIMENT",
            "untrusted_social_nomination": True,
            "qualification_evidence": False,
            "gap_resolution_eligible": False,
            "trade_signal": False,
            "direction": "UNSPECIFIED",
            "research_only": True,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        if persist:
            record_object(candidate_id, "grok_opportunity_candidate", GROK_EXPERIMENT_LEDGER_CASE, candidate, topic=ticker)
        if reasons:
            quarantined.append(candidate)
        elif len(admitted) < max_candidates:
            admitted.append(candidate)

    if persist:
        record_event(GROK_EXPERIMENT_LEDGER_CASE, "GROK_OPPORTUNITY_DISCOVERY_COMPLETE", payload={
            "query": query,
            "nominated_count": len(admitted),
            "quarantined_count": len(quarantined),
            "automatic_promotion": False,
            "trade_execution_permission": False,
        })
    return {
        "query": query,
        "nominations": admitted,
        "quarantined": quarantined,
        "nominated_count": len(admitted),
        "quarantined_count": len(quarantined),
        "grok_usage": context.get("usage") or {},
        "next_step": "MANUAL_IIOS_STANDARD_REVALIDATION",
        "automatic_promotion": False,
        "agents_started": 0,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def revalidate_grok_candidate(candidate_id: str) -> dict[str, Any]:
    candidate = get_object(candidate_id)
    if not candidate or not str(candidate_id).startswith("grok_opportunity_"):
        raise ValueError("Unknown Grok opportunity candidate")
    if candidate.get("eligible_for_iios_revalidation") is not True:
        raise ValueError("Grok candidate did not pass the social-source nomination firewall")
    if candidate.get("standard_candidate_id"):
        existing = get_object(str(candidate.get("standard_candidate_id")))
        if existing:
            return {
                "grok_candidate": candidate,
                "standard_candidate": existing,
                "already_revalidated": True,
                "automatic_promotion": False,
                "agents_started": 0,
            }

    ticker = str(candidate.get("ticker") or "").upper()
    quote = fetch_market_quote(ticker)
    try:
        news = fetch_gdelt_news({"query": f"{ticker} {candidate.get('rationale') or ''}"[:300], "limit": 10, "timespan": "24h"})
        news_error = None
    except Exception as exc:
        news = []
        news_error = f"{type(exc).__name__}: {exc}"[:1000]

    scored = score_candidate(ticker=ticker, quote=quote, news_items=news)
    evidence = list(quote.get("items") or []) + list(news)
    standard_id = f"opportunity_{uuid4().hex}"
    standard_candidate = {
        "opportunity_candidate_id": standard_id,
        "opportunity_scan_id": None,
        "ticker": ticker,
        "label": ticker,
        "query": ticker,
        **scored,
        "current_price": quote.get("current_price"),
        "quote_provider": quote.get("provider"),
        "quote_error": quote.get("error"),
        "news_error": news_error,
        "evidence": evidence,
        "evidence_count": len(evidence),
        "promoted_case_id": None,
        "source_grok_candidate_id": candidate_id,
        "created_by": "GROK_NOMINATION_REVALIDATED_BY_STANDARD_IIOS",
        "created_at": utc_now(),
    }
    record_object(standard_id, "opportunity_candidate", OPPORTUNITY_LEDGER_CASE, standard_candidate, topic=ticker)
    updated = {
        **candidate,
        "standard_candidate_id": standard_id,
        "standard_revalidated_at": utc_now(),
        "eligible_for_standard_promotion": standard_candidate.get("eligible_for_promotion") is True,
    }
    record_object(candidate_id, "grok_opportunity_candidate", GROK_EXPERIMENT_LEDGER_CASE, updated, topic=ticker)
    record_event(GROK_EXPERIMENT_LEDGER_CASE, "GROK_OPPORTUNITY_REVALIDATED_BY_IIOS", entity_id=candidate_id, payload={
        "ticker": ticker,
        "standard_candidate_id": standard_id,
        "standard_score": standard_candidate.get("score"),
        "standard_promotion_available": standard_candidate.get("eligible_for_promotion") is True,
        "automatic_promotion": False,
        "agents_started": 0,
        "trade_execution_permission": False,
    })
    return {
        "grok_candidate": updated,
        "standard_candidate": standard_candidate,
        "already_revalidated": False,
        "standard_promotion_available": standard_candidate.get("eligible_for_promotion") is True,
        "next_step": f"POST /opportunities/{standard_id}/promote" if standard_candidate.get("eligible_for_promotion") is True else "RESEARCH_GATE_NOT_MET",
        "automatic_promotion": False,
        "agents_started": 0,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/grok/opportunities/plan")
def grok_opportunity_plan():
    return {
        "mode": "GROK_NOMINATION_THEN_STANDARD_IIOS_REVALIDATION",
        "minimum_verified_x_sources": MIN_NOMINATION_SOURCES,
        "grok_can_create_governed_case_directly": False,
        "standard_quote_required": True,
        "standard_news_required": True,
        "standard_opportunity_score_required": True,
        "automatic_promotion": False,
        "automatic_agent_run": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/grok/opportunities/discover")
def grok_discover(request: dict[str, Any] = Body(...)):
    try:
        return discover_grok_opportunities(
            str(request.get("query") or ""),
            days=int(request.get("days") or 2),
            max_candidates=int(request.get("max_candidates") or 5),
            persist=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000])


@router.post("/grok/opportunities/{candidate_id}/revalidate")
def grok_revalidate(candidate_id: str):
    try:
        return revalidate_grok_candidate(candidate_id)
    except ValueError as exc:
        status = 404 if "Unknown" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))
