from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

from ledger import DB_PATH, get_object, latest_object


router = APIRouter()
MAX_ANALOGS = 8

REGIME_TERMS = {
    "rates": ("fed", "rate", "yield", "treasury", "duration"),
    "inflation": ("inflation", "cpi", "ppi", "pricing pressure"),
    "credit": ("credit", "spread", "liquidity", "bank", "lending"),
    "ai_capex": ("ai", "data center", "hyperscaler", "hbm", "accelerator"),
    "energy": ("oil", "gas", "permian", "refining", "brent", "wti"),
    "supply": ("supply", "inventory", "capacity", "shortage", "production"),
    "demand": ("demand", "orders", "backlog", "customer", "shipments"),
    "policy": ("tariff", "policy", "regulation", "subsidy", "export control"),
    "geopolitics": ("war", "sanction", "china", "taiwan", "middle east"),
    "weather": ("hurricane", "drought", "wildfire", "storm", "freeze"),
}


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _all_cases() -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? ORDER BY created_at DESC",
            ("case",),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def _text(case: dict[str, Any]) -> str:
    pieces = [str(case.get("topic") or "")]
    for item in case.get("evidence") or []:
        if isinstance(item, dict):
            pieces.extend([
                str(item.get("title") or ""),
                str(item.get("claim") or ""),
                str(item.get("evidence_type") or ""),
            ])
    return " ".join(pieces).lower()


def regime_tags(case: dict[str, Any]) -> list[str]:
    corpus = _text(case)
    return sorted(
        tag for tag, terms in REGIME_TERMS.items()
        if any(term in corpus for term in terms)
    )


def topic_tokens(case: dict[str, Any]) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", str(case.get("topic") or "").lower())
    stop = {"opportunity", "review", "the", "and", "for", "with"}
    return {word for word in words if word not in stop}


def _similarity(current: dict[str, Any], prior: dict[str, Any]) -> float:
    current_tags = set(regime_tags(current))
    prior_tags = set(regime_tags(prior))
    union = current_tags | prior_tags
    regime_score = (len(current_tags & prior_tags) / len(union)) if union else 0.0

    current_tokens = topic_tokens(current)
    prior_tokens = topic_tokens(prior)
    token_union = current_tokens | prior_tokens
    topic_score = (len(current_tokens & prior_tokens) / len(token_union)) if token_union else 0.0
    return round(min(1.0, 0.7 * regime_score + 0.3 * topic_score), 4)


def find_historical_analogs(case_id: str, limit: int = 5) -> dict[str, Any]:
    current = _require_case(case_id)
    limit = max(1, min(int(limit), MAX_ANALOGS))
    rows: list[dict[str, Any]] = []
    for prior in _all_cases():
        prior_id = str(prior.get("case_id") or "")
        if not prior_id or prior_id == case_id:
            continue
        similarity = _similarity(current, prior)
        if similarity <= 0:
            continue
        decision = latest_object("committee_decision", case_id=prior_id) or {}
        postmortem = latest_object("postmortem", case_id=prior_id) or {}
        rows.append({
            "case_id": prior_id,
            "topic": prior.get("topic"),
            "similarity": similarity,
            "shared_regime_tags": sorted(set(regime_tags(current)) & set(regime_tags(prior))),
            "committee_disposition": decision.get("disposition"),
            "committee_confidence": decision.get("confidence"),
            "outcome": postmortem.get("outcome"),
            "historical_outcome_known": bool(postmortem.get("outcome")),
            "realized_return_pct": postmortem.get("realized_return_pct"),
            "analogy_scope": "INTERNAL_IIOS_CASE_MEMORY",
        })
    rows.sort(key=lambda row: float(row.get("similarity") or 0.0), reverse=True)
    return {
        "case_id": case_id,
        "current_regime_tags": regime_tags(current),
        "analogs": rows[:limit],
        "analog_count": min(len(rows), limit),
        "warning": "These are internal IIOS case analogs. They are not historical market outcomes unless historical_outcome_known is true.",
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/intelligence/historical-analogs/{case_id}")
def historical_analogs(case_id: str, limit: int = 5):
    return find_historical_analogs(case_id, limit)
