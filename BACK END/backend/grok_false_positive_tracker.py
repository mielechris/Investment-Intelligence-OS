from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter

from ledger import DB_PATH, get_object, utc_now


router = APIRouter()
POLICY_VERSION = "grok-false-positive-tracker-v1"


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


def build_false_positive_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    validated = 0
    rejected = 0
    pending = 0

    for candidate in _rows("grok_opportunity_candidate"):
        if candidate.get("eligible_for_iios_revalidation") is not True:
            continue
        standard_id = str(candidate.get("standard_candidate_id") or "").strip()
        standard = get_object(standard_id) if standard_id else None
        if standard is None:
            verdict = "PENDING_STANDARD_IIOS_REVALIDATION"
            pending += 1
        elif standard.get("eligible_for_promotion") is True:
            verdict = "VALIDATED_BY_STANDARD_IIOS_GATE"
            validated += 1
        else:
            verdict = "REJECTED_BY_STANDARD_IIOS_GATE"
            rejected += 1

        rows.append({
            "grok_opportunity_candidate_id": candidate.get("grok_opportunity_candidate_id"),
            "ticker": candidate.get("ticker"),
            "grok_source_count": candidate.get("source_count"),
            "grok_advisory_confidence": candidate.get("advisory_confidence"),
            "standard_candidate_id": standard_id or None,
            "standard_score": (standard or {}).get("score"),
            "standard_promotion_eligible": (standard or {}).get("eligible_for_promotion"),
            "verdict": verdict,
            "false_positive_definition": "Grok nomination that passed the social-source firewall but failed independent standard IIOS quote/news promotion gating",
            "automatic_promotion": False,
            "trade_signal": False,
            "trade_execution_permission": False,
            "live_execution": False,
        })

    resolved = validated + rejected
    false_positive_rate = round(rejected / resolved, 4) if resolved else None
    validation_rate = round(validated / resolved, 4) if resolved else None
    return {
        "policy_version": POLICY_VERSION,
        "status": "MEASURING" if rows else "NO_GROK_NOMINATIONS_YET",
        "nomination_count": len(rows),
        "resolved_count": resolved,
        "validated_count": validated,
        "rejected_count": rejected,
        "pending_count": pending,
        "false_positive_rate": false_positive_rate,
        "validation_rate": validation_rate,
        "rows": rows,
        "automatic_promotion": False,
        "automatic_agent_run": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.get("/grok/value/false-positive")
def get_grok_false_positive_report():
    return build_false_positive_report()
