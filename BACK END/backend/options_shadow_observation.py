from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from factory_genericization import resolve_case_profile
from ledger import get_object, list_objects, latest_object


router = APIRouter()
POLICY_VERSION = "options-shadow-observation-v1"
MODE = "SHADOW_OBSERVATION_ONLY"


def _options_records(case_id: str) -> list[dict[str, Any]]:
    records = []
    for row in list_objects(case_id, "primary_evidence_record"):
        if not isinstance(row, dict):
            continue
        if row.get("lane") != "valuation_market" or row.get("fact_key") != "options":
            continue
        if row.get("gap_resolution_eligible") is not True:
            continue
        records.append(
            {
                "primary_evidence_id": row.get("primary_evidence_id"),
                "source_name": row.get("source_name"),
                "source_url": row.get("source_url"),
                "source_grade": row.get("source_grade"),
                "claim": row.get("claim"),
                "observed_at": row.get("observed_at"),
                "evidence_type": row.get("evidence_type"),
            }
        )
    return list(reversed(records[-20:]))


def build_options_shadow_status(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise ValueError("Unknown case_id")

    identity = resolve_case_profile(case_id)
    records = _options_records(case_id)
    verified = latest_object(
        "user_verified_options_positioning_snapshot",
        case_id=case_id,
    ) or {}

    return {
        "policy_version": POLICY_VERSION,
        "mode": MODE,
        "case_id": case_id,
        "ticker": identity.get("ticker"),
        "company": identity.get("company"),
        "observation_count": len(records),
        "options_positioning_records": records,
        "latest_verified_occ_snapshot": verified or None,
        "observation_scope": [
            "OCC clearing open interest",
            "put/call open-interest positioning",
            "expiry-range context when available",
        ],
        "interpretation_boundary": (
            "Options positioning is market context only. Open interest may represent hedges, spreads, "
            "covered positions or speculation and is not a directional trade instruction."
        ),
        "batch10d": {
            "shadow_observation_enabled": True,
            "equity_paper_expression_authoritative": True,
            "contract_selection_enabled": False,
            "strike_selection_enabled": False,
            "expiration_selection_enabled": False,
            "greeks_required_for_execution": True,
            "options_paper_orders_enabled": False,
        },
        "batch10e_gate": {
            "requires_chain_and_contract_data": True,
            "requires_bid_ask_liquidity": True,
            "requires_greeks_and_iv_regime": True,
            "requires_realistic_fill_model": True,
            "requires_defined_max_loss_sizing": True,
            "initial_strategy_scope": [
                "LONG_CALL",
                "LONG_PUT",
                "BULL_CALL_SPREAD",
                "BEAR_PUT_SPREAD",
                "COVERED_CALL_WHEN_UNDERLYING_OWNED",
            ],
            "prohibited_initial_scope": [
                "NAKED_SHORT_CALL",
                "NAKED_SHORT_PUT",
                "UNDEFINED_RISK",
                "0DTE",
                "LIVE_OPTIONS_EXECUTION",
            ],
        },
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "option_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/options-shadow/plan")
def options_shadow_plan():
    return {
        "policy_version": POLICY_VERSION,
        "mode": MODE,
        "purpose": "Observe options context during Batch 10D before governed options paper execution in Batch 10E.",
        "options_paper_orders_enabled": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/options-shadow/{case_id}/status")
def options_shadow_status(case_id: str):
    try:
        return build_options_shadow_status(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
