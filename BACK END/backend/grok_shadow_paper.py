from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException

from ledger import DB_PATH, get_object, record_object, utc_now
from opportunity_evidence import fetch_crosschecked_quote


router = APIRouter()
POLICY_VERSION = "grok-dual-arm-shadow-paper-v2"


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


def _latest_valid_ab_results() -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in _rows("grok_ab_result"):
        comparison = row.get("comparison") if isinstance(row.get("comparison"), dict) else {}
        case_id = str(row.get("case_id") or "").strip()
        if not case_id or comparison.get("experiment_valid") is not True or int(row.get("runs_per_arm") or 0) < 2:
            continue
        current = selected.get(case_id)
        if current is None or str(row.get("created_at") or "") > str(current.get("created_at") or ""):
            selected[case_id] = row
    return list(selected.values())


def _resolve_ticker(case_id: str) -> str | None:
    case = get_object(case_id) or {}
    source_id = str(case.get("source_candidate_id") or "").strip()
    source = get_object(source_id) if source_id else None
    ticker = str((source or {}).get("ticker") or "").strip().upper()
    if ticker:
        return ticker
    topic = str(case.get("topic") or "")
    match = re.search(r"\(([A-Z0-9.\-]{1,12})\)", topic.upper())
    return match.group(1) if match else None


def _arm_state(disposition: Any) -> str:
    value = str(disposition or "").upper()
    if value == "NO_TRADE":
        return "CASH_NO_POSITION"
    if value == "WATCH":
        return "WATCH_ONLY_NO_POSITION"
    return "UNKNOWN_NO_POSITION"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def enroll_shadow_pairs() -> dict[str, Any]:
    enrolled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for result in _latest_valid_ab_results():
        case_id = str(result.get("case_id") or "")
        object_id = f"grok_shadow_pair_{case_id}"
        existing = get_object(object_id)
        if existing:
            enrolled.append(existing)
            continue
        ticker = _resolve_ticker(case_id)
        if not ticker:
            skipped.append({"case_id": case_id, "reason": "TICKER_UNRESOLVED"})
            continue
        quote = fetch_crosschecked_quote(ticker)
        price = _safe_float(quote.get("current_price"))
        if quote.get("status") != "ok" or quote.get("cross_checked") is not True or price is None or price <= 0:
            skipped.append({
                "case_id": case_id,
                "ticker": ticker,
                "reason": "CROSSCHECKED_REFERENCE_QUOTE_UNAVAILABLE",
                "quote_status": quote.get("status"),
                "quote_quality": quote.get("quote_quality"),
                "quote_provider_count": quote.get("provider_count"),
            })
            continue
        comparison = result.get("comparison") or {}
        baseline = comparison.get("baseline") or {}
        grok = comparison.get("iios_plus_grok") or {}
        baseline_disposition = comparison.get("baseline_disposition") or ((baseline.get("dispositions") or [None])[0])
        grok_disposition = comparison.get("grok_disposition") or ((grok.get("dispositions") or [None])[0])
        pair = {
            "shadow_pair_id": object_id,
            "policy_version": POLICY_VERSION,
            "case_id": case_id,
            "ticker": ticker,
            "source_grok_ab_result_id": result.get("grok_ab_result_id"),
            "reference_price": price,
            "reference_quote_provider": quote.get("provider"),
            "reference_quote_providers": list(quote.get("providers") or []),
            "reference_quote_provider_count": quote.get("provider_count"),
            "reference_quote_cross_checked": quote.get("cross_checked") is True,
            "reference_quote_spread_pct": quote.get("spread_pct"),
            "reference_quote_quality": quote.get("quote_quality"),
            "reference_at": utc_now(),
            "baseline_disposition": baseline_disposition,
            "grok_disposition": grok_disposition,
            "baseline_confidence": baseline.get("median_confidence"),
            "grok_confidence": grok.get("median_confidence"),
            "baseline_state": _arm_state(baseline_disposition),
            "grok_state": _arm_state(grok_disposition),
            "differentiated_action": str(baseline_disposition) != str(grok_disposition),
            "arm_specific_position_created": False,
            "measurement_only": True,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(object_id, "grok_shadow_paper_pair", case_id, pair, parent_id=result.get("grok_ab_result_id"), topic=ticker)
        enrolled.append(pair)
    return {
        "policy_version": POLICY_VERSION,
        "enrolled_count": len(enrolled),
        "skipped_count": len(skipped),
        "pairs": enrolled,
        "skipped": skipped,
        "reference_quote_policy": "TWO_SOURCE_CROSSCHECK_REQUIRED",
        "actual_paper_orders_created": 0,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def refresh_shadow_pairs() -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    for pair in _rows("grok_shadow_paper_pair"):
        ticker = str(pair.get("ticker") or "").strip().upper()
        case_id = str(pair.get("case_id") or "")
        quote = fetch_crosschecked_quote(ticker)
        quote_ok = quote.get("status") == "ok" and quote.get("cross_checked") is True
        current = _safe_float(quote.get("current_price")) if quote_ok else None
        reference = _safe_float(pair.get("reference_price"))
        underlying_return = None
        if current is not None and reference is not None and reference > 0:
            underlying_return = round(((current - reference) / reference) * 100.0, 4)
        baseline_state = str(pair.get("baseline_state") or "")
        grok_state = str(pair.get("grok_state") or "")
        baseline_cash_return = 0.0 if baseline_state == "CASH_NO_POSITION" else None
        grok_cash_return = 0.0 if grok_state == "CASH_NO_POSITION" else None
        snapshot_id = f"grok_shadow_snapshot_{case_id}_{utc_now().replace(':', '').replace('+', '_')}"
        snapshot = {
            "shadow_snapshot_id": snapshot_id,
            "shadow_pair_id": pair.get("shadow_pair_id"),
            "case_id": case_id,
            "ticker": ticker,
            "reference_price": reference,
            "current_price": current,
            "current_quote_status": quote.get("status"),
            "current_quote_quality": quote.get("quote_quality"),
            "current_quote_providers": list(quote.get("providers") or []),
            "current_quote_provider_count": quote.get("provider_count"),
            "current_quote_cross_checked": quote.get("cross_checked") is True,
            "current_quote_spread_pct": quote.get("spread_pct"),
            "underlying_return_pct": underlying_return,
            "baseline_state": baseline_state,
            "grok_state": grok_state,
            "baseline_cash_return_pct": baseline_cash_return,
            "grok_cash_return_pct": grok_cash_return,
            "differentiated_action": pair.get("differentiated_action") is True,
            "arm_specific_pnl_available": False,
            "interpretation": "NO_TRADE is tracked as cash/no position; WATCH remains watch-only until the governed paper chain creates a position. Underlying returns require a fresh two-source cross-checked quote.",
            "measurement_only": True,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }
        record_object(snapshot_id, "grok_shadow_paper_snapshot", case_id, snapshot, parent_id=pair.get("shadow_pair_id"), topic=ticker)
        snapshots.append(snapshot)
    return {
        "policy_version": POLICY_VERSION,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "reference_quote_policy": "TWO_SOURCE_CROSSCHECK_REQUIRED",
        "actual_paper_orders_created": 0,
        "arm_specific_pnl_available": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def shadow_paper_status() -> dict[str, Any]:
    pairs = _rows("grok_shadow_paper_pair")
    snapshots = _rows("grok_shadow_paper_snapshot")
    return {
        "policy_version": POLICY_VERSION,
        "pair_count": len(pairs),
        "snapshot_count": len(snapshots),
        "differentiated_action_pair_count": sum(1 for row in pairs if row.get("differentiated_action") is True),
        "crosschecked_reference_pair_count": sum(1 for row in pairs if row.get("reference_quote_cross_checked") is True),
        "arm_specific_pnl_available": False,
        "actual_paper_orders_created": 0,
        "reference_quote_policy": "TWO_SOURCE_CROSSCHECK_REQUIRED",
        "interpretation": "This is a decision-shadow ledger only. It does not convert WATCH into a position and does not create paper or live orders.",
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


@router.get("/grok/value/shadow-paper/status")
def get_shadow_paper_status():
    return shadow_paper_status()


@router.post("/grok/value/shadow-paper/enroll")
def enroll_shadow_paper():
    try:
        return enroll_shadow_pairs()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000])


@router.post("/grok/value/shadow-paper/refresh")
def refresh_shadow_paper():
    try:
        return refresh_shadow_pairs()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:1000])
