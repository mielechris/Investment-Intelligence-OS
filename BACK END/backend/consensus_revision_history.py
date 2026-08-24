from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from ledger import list_objects, record_event, record_object, utc_now


MIN_HISTORY_HOURS = 72


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
    except ValueError:
        return None


def _eps(claim: str) -> float | None:
    match = re.search(
        r"\bEPS\s*=\s*([0-9]+(?:\.[0-9]+)?)",
        str(claim or ""),
        flags=re.I,
    )
    return float(match.group(1)) if match else None


def build_consensus_revision_history(
    case_id: str,
) -> dict[str, Any]:
    rows = []

    for record in list_objects(
        case_id,
        "primary_evidence_record",
    ):
        if record.get("lane") != "valuation_market":
            continue
        if record.get("fact_key") != "consensus":
            continue
        if record.get("gap_resolution_eligible") is False:
            continue

        eps = _eps(str(record.get("claim") or ""))
        stamp = _parse_time(record.get("observed_at"))

        if eps is None or stamp is None:
            continue

        rows.append(
            {
                "eps": eps,
                "observed_at": stamp,
                "observed_at_iso": stamp.isoformat(),
                "source": record.get("source_name"),
                "record_id": record.get(
                    "primary_evidence_id"
                ),
            }
        )

    rows.sort(key=lambda row: row["observed_at"])

    if len(rows) < 2:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "verified_revision_history": False,
            "observations": len(rows),
        }

    first = rows[0]
    latest = rows[-1]

    age_hours = (
        latest["observed_at"]
        - first["observed_at"]
    ).total_seconds() / 3600.0

    if age_hours < MIN_HISTORY_HOURS:
        return {
            "status": "INSUFFICIENT_TIME_DEPTH",
            "verified_revision_history": False,
            "observations": len(rows),
            "history_hours": round(age_hours, 2),
        }

    change = latest["eps"] - first["eps"]
    pct = (
        change / first["eps"] * 100.0
        if first["eps"]
        else None
    )

    direction = (
        "REVISING_UP"
        if change > 0
        else "REVISING_DOWN"
        if change < 0
        else "FLAT"
    )

    history_id = f"consensus_revision_{uuid4().hex}"

    payload = {
        "consensus_revision_history_id": history_id,
        "case_id": case_id,
        "analysis_type":
            "GOVERNED_CONSENSUS_REVISION_HISTORY_V1",
        "status": "CURRENT",
        "verified_revision_history": True,
        "direction": direction,
        "first_eps": first["eps"],
        "latest_eps": latest["eps"],
        "eps_change": round(change, 4),
        "eps_change_pct": (
            round(pct, 4)
            if pct is not None
            else None
        ),
        "history_hours": round(age_hours, 2),
        "observations": len(rows),
        "first_observation": {
            k: v for k, v in first.items()
            if k != "observed_at"
        },
        "latest_observation": {
            k: v for k, v in latest.items()
            if k != "observed_at"
        },
        "may_resolve_primary_fact": False,
        "may_authorize_trade": False,
        "paper_buy_enabled": False,
        "created_at": utc_now(),
    }

    record_object(
        history_id,
        "consensus_revision_history",
        case_id,
        payload,
    )

    record_event(
        case_id,
        "CONSENSUS_REVISION_HISTORY_BUILT",
        entity_id=history_id,
        payload={
            "direction": direction,
            "history_hours": payload["history_hours"],
            "observations": payload["observations"],
        },
    )

    return payload


def consensus_revision_evidence(
    case_id: str,
) -> list[dict[str, Any]]:
    result = build_consensus_revision_history(case_id)

    if not result.get("verified_revision_history"):
        return []

    return [
        {
            "source":
                "IIOS Governed Consensus Revision Ledger",
            "source_type": "governed_analysis",
            "evidence_type":
                "analyst_consensus_revision_history",
            "url": "iios://consensus-revision-history",
            "title":
                "MU governed forward EPS revision history",
            "claim": (
                f"Observed governed forward EPS changed from "
                f"{result['first_eps']} to "
                f"{result['latest_eps']} across "
                f"{result['history_hours']} hours; "
                f"direction={result['direction']}. "
                "This is an IIOS observed consensus-history "
                "comparison, not an inferred analyst revision."
            ),
            "timestamp": result["created_at"],
            "reliability_score": 0.90,
            "analysis_type":
                "GOVERNED_CONSENSUS_REVISION_HISTORY_V1",
            "verified_revision_history": True,
            "may_resolve_primary_fact": False,
            "may_authorize_trade": False,
            "paper_buy_enabled": False,
        }
    ]
