from __future__ import annotations

from typing import Any

from ledger import get_object, record_object, utc_now


OBSERVATION_CASE_ID = "grok_governed_observation"
OBSERVATION_ID = "grok_governed_observation_status"
POLICY_VERSION = "grok-governed-observation-v1"


def advisory_read_model(context: dict[str, Any]) -> dict[str, Any]:
    """Expose advisory metadata only; raw Grok content remains quarantined from authority paths."""
    return {
        "label": "UNTRUSTED ADVISORY RESEARCH",
        "case_id": context.get("case_id"),
        "grok_social_context_id": context.get("grok_social_context_id"),
        "query_fingerprint": context.get("query_fingerprint"),
        "retrieved_at": context.get("created_at"),
        "model": context.get("model"),
        "citation_count": int(context.get("citation_count") or 0),
        "admitted_count": int(context.get("admitted_count") or 0),
        "quarantined_count": int(context.get("quarantined_count") or 0),
        "quarantine_reasons": list(context.get("quarantine_reasons") or []),
        "cost_source": context.get("cost_source"),
        "estimated_cost_ticks": context.get("reserved_cost_ticks"),
        "actual_cost_ticks": context.get("actual_cost_ticks"),
        "reservation_id": context.get("reservation_id"),
        "settlement_id": context.get("settlement_id"),
        "qualification_evidence": False,
        "promotion_authority": False,
        "committee_override": False,
        "capital_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def record_observation(context: dict[str, Any], *, outcome: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = get_object(OBSERVATION_ID) or {}
    entries = list(previous.get("entries") or [])[-99:]
    entry = advisory_read_model(context)
    entry["observed_at"] = utc_now()
    entry["citation_valid"] = entry["citation_count"] >= 2 and entry["admitted_count"] > 0
    entry["useful_insight"] = bool(context.get("new_information_added"))
    entry["duplicate_with_existing_evidence"] = bool(context.get("duplicate_with_existing_evidence"))
    entry["later_price_outcome_agreement"] = (outcome or {}).get("later_price_outcome_agreement")
    entry["false_positive"] = (outcome or {}).get("false_positive")
    entry["time_advantage"] = (outcome or {}).get("time_advantage")
    entries.append(entry)
    payload = {
        "observation_id": OBSERVATION_ID,
        "policy_version": POLICY_VERSION,
        "window_start": previous.get("window_start") or entry["observed_at"],
        "window_end": entry["observed_at"],
        "entries": entries,
        "pricing_verified": False,
        "provider_activation_state": "DISABLED_PENDING_OWNER_VERIFICATION",
        "qualification_evidence": False,
        "promotion_authority": False,
        "committee_override": False,
        "capital_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(OBSERVATION_ID, "grok_governed_observation", OBSERVATION_CASE_ID, payload)
    return payload


def observation_status() -> dict[str, Any]:
    payload = get_object(OBSERVATION_ID) or {"entries": []}
    entries = list(payload.get("entries") or [])
    return {
        "policy_version": POLICY_VERSION,
        "pricing_verified": False,
        "provider_activation_state": "DISABLED_PENDING_OWNER_VERIFICATION",
        "window_start": payload.get("window_start"),
        "window_end": payload.get("window_end"),
        "requests_observed": len(entries),
        "requests_admitted": sum(1 for entry in entries if entry.get("admitted_count")),
        "requests_denied": sum(1 for entry in entries if entry.get("denied")),
        "requests_cancelled": sum(1 for entry in entries if entry.get("cancelled")),
        "requests_settled": sum(1 for entry in entries if entry.get("settlement_id")),
        "integrity_blocked": sum(1 for entry in entries if entry.get("integrity_blocked")),
        "total_actual_cost_ticks": sum(int(entry.get("actual_cost_ticks") or 0) for entry in entries),
        "useful_insight_count": sum(1 for entry in entries if entry.get("useful_insight")),
        "false_positive_count": sum(1 for entry in entries if entry.get("false_positive") is True),
        "quarantined_count": sum(int(entry.get("quarantined_count") or 0) for entry in entries),
        "qualification_evidence": False,
        "promotion_authority": False,
        "committee_override": False,
        "capital_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }