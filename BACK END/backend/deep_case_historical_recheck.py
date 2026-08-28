from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import ledger
from factory_genericization import resolve_case_profile
from historical_pattern_analyst import run_historical_pattern_review
from ledger import get_object, latest_object, record_event, record_object, utc_now
from paper_capital_api import paper_capital_status

POLICY_VERSION = "batch10c-deep-case-historical-recheck-v2"
OBJECT_TYPE = "historical_recheck"
PERIODIC_RECHECK_HOURS = 24.0
PRICE_MOVE_TRIGGER_PCT = 5.0
NEAR_ENTRY_GAP_PCT = 3.0
ACTIVE_ENTRY_STAGES = {"WAIT_FOR_ENTRY", "READY_FOR_POSITION_SIZING"}
MATERIAL_THESIS_FLAGS = {
    "FALSIFIER_TRIGGERED",
    "CATALYST_MISSED",
    "UPDATE_EVIDENCE_CONFLICT",
    "GUIDANCE_BREAK",
    "BALANCE_SHEET_DETERIORATION",
    "REGULATORY_BREAK",
    "FUNDAMENTAL_BREAK",
    "DRAWDOWN_TRIGGERED",
}


def _rows_by_type(object_type: str, limit: int = 1000) -> list[dict[str, Any]]:
    connection = sqlite3.connect(ledger.DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type=? ORDER BY created_at DESC LIMIT ?",
            (object_type, max(1, min(int(limit), 5000))),
        ).fetchall()
    finally:
        connection.close()
    output: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict):
            output.append(payload)
    return output


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_capital_control(
    *,
    qualification: dict[str, Any] | None,
    capital_watch: dict[str, Any] | None,
    capital_status: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    qualification = qualification if isinstance(qualification, dict) else {}
    capital_watch = capital_watch if isinstance(capital_watch, dict) else {}
    capital_status = capital_status if isinstance(capital_status, dict) else {}
    qualified = qualification.get("qualified_buy_candidate") is True

    if capital_watch:
        stage = str(capital_watch.get("stage") or "").upper() or None
        current_price = _safe_float(capital_watch.get("current_price"))
        maximum_entry = _safe_float(capital_watch.get("maximum_qualifying_entry"))
        entry_gap = _safe_float(capital_watch.get("entry_gap"))
        entry_gap_pct = _safe_float(capital_watch.get("entry_gap_pct"))
        failed_checks = capital_watch.get("capital_failed_hard_checks") or []
        source = "CAPITAL_ENTRY_WATCH"
    elif capital_status:
        capital = capital_status.get("capital") if isinstance(capital_status.get("capital"), dict) else {}
        stage = str(capital_status.get("stage") or "").upper() or None
        current_price = _safe_float(capital.get("current_price"))
        maximum_entry = _safe_float(capital.get("maximum_qualifying_entry"))
        failed_checks = capital.get("failed_hard_checks") or []
        source = "PAPER_CAPITAL_STATUS"
        entry_gap = None
        entry_gap_pct = None
        if current_price is not None and maximum_entry is not None:
            entry_gap = max(0.0, current_price - maximum_entry)
            if current_price > 0:
                entry_gap_pct = (entry_gap / current_price) * 100.0
    else:
        return {
            "source": "UNAVAILABLE",
            "stage": None,
            "current_price": None,
            "maximum_qualifying_entry": None,
            "entry_gap": None,
            "entry_gap_pct": None,
            "entry_reference_active": False,
            "entry_reference_status": "UNAVAILABLE",
            "failed_hard_checks": [],
            "error": error,
        }

    active = bool(qualified and stage in ACTIVE_ENTRY_STAGES and maximum_entry is not None)
    if active:
        reference_status = "ACTIVE_GOVERNED_ENTRY"
    elif not qualified or stage == "RESEARCH_NOT_QUALIFIED":
        reference_status = "INACTIVE_UPSTREAM_RESEARCH_GATE"
    elif stage in {"CAPITAL_REJECTED", "THESIS_INVALIDATED"}:
        reference_status = "INACTIVE_CAPITAL_OR_THESIS_GATE"
    elif maximum_entry is not None:
        reference_status = "MODELED_REFERENCE_NOT_ACTIVE"
    else:
        reference_status = "NO_GOVERNED_ENTRY_REFERENCE"

    return {
        "source": source,
        "stage": stage,
        "current_price": current_price,
        "maximum_qualifying_entry": maximum_entry,
        "entry_gap": None if entry_gap is None else round(entry_gap, 4),
        "entry_gap_pct": None if entry_gap_pct is None else round(entry_gap_pct, 4),
        "entry_reference_active": active,
        "entry_reference_status": reference_status,
        "failed_hard_checks": [str(value) for value in failed_checks],
        "error": error,
    }


def _fallback_capital_status(case_id: str, qualification: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Read the authoritative paper-capital status only when doing so will not
    synthesize fresh generic capital inputs during the 15-minute sweep.
    """
    qualified = qualification.get("qualified_buy_candidate") is True
    try:
        identity = resolve_case_profile(case_id)
    except Exception as exc:
        return {}, f"IDENTITY:{type(exc).__name__}: {exc}"

    is_micron = bool(identity.get("is_micron"))
    if qualified:
        required_stress_type = "cycle_valuation_stress" if is_micron else "generic_capital_stress"
        if not latest_object(required_stress_type, case_id=case_id):
            return {}, f"{required_stress_type.upper()}_UNAVAILABLE"

    try:
        return paper_capital_status(case_id), None
    except Exception as exc:
        return {}, f"PAPER_CAPITAL_STATUS:{type(exc).__name__}: {exc}"


def deep_case_state(case_id: str) -> dict[str, Any]:
    case = get_object(case_id) or {}
    committee = latest_object("committee_decision", case_id=case_id) or {}
    qualification = latest_object("qualification_assessment", case_id=case_id) or {}
    risk = latest_object("risk_authorization", case_id=case_id) or {}
    gap_hunt = latest_object("gap_hunt", case_id=case_id) or {}
    if not risk and isinstance(gap_hunt.get("risk"), dict):
        risk = gap_hunt.get("risk") or {}
    capital_watch = latest_object("capital_entry_watch", case_id=case_id) or {}
    position = latest_object("position_monitor", case_id=case_id) or {}
    thesis = latest_object("thesis_monitor", case_id=case_id) or {}
    monitor = latest_object("monitor_profile", case_id=case_id) or {}
    execution = (
        latest_object("governed_paper_execution", case_id=case_id)
        or latest_object("execution", case_id=case_id)
        or {}
    )
    historical = latest_object("historical_pattern_review", case_id=case_id) or {}
    prior_recheck = latest_object(OBJECT_TYPE, case_id=case_id) or {}

    capital_status: dict[str, Any] = {}
    capital_error: str | None = None
    if not capital_watch:
        capital_status, capital_error = _fallback_capital_status(case_id, qualification)
    capital_control = normalize_capital_control(
        qualification=qualification,
        capital_watch=capital_watch,
        capital_status=capital_status,
        error=capital_error,
    )

    reasons: list[str] = []
    if str(committee.get("disposition") or "").upper() == "WATCH":
        reasons.append("COMMITTEE_WATCH")
    if qualification.get("qualified_buy_candidate") is True:
        reasons.append("QUALIFIED_BUY_CANDIDATE")
    if risk:
        reasons.append("RISK_REACHED")
    if capital_watch:
        reasons.append("CAPITAL_ENTRY_WATCH")
    elif capital_control.get("stage") in {
        "WAIT_FOR_ENTRY",
        "READY_FOR_POSITION_SIZING",
        "CAPITAL_REJECTED",
        "CAPITAL_INPUTS_PENDING",
    }:
        reasons.append("CAPITAL_CONTROL_STATE")
    if execution:
        reasons.append("PAPER_EXECUTION_LINEAGE")
    if monitor.get("enabled") is True and committee:
        reasons.append("ACTIVE_MONITORING")

    ticker = str(
        capital_watch.get("ticker")
        or monitor.get("ticker")
        or case.get("ticker")
        or ""
    ).upper() or None

    return {
        "case_id": case_id,
        "ticker": ticker,
        "case": case,
        "committee": committee,
        "qualification": qualification,
        "risk": risk,
        "capital_watch": capital_watch,
        "capital_status": capital_status,
        "capital_control": capital_control,
        "position": position,
        "thesis": thesis,
        "monitor": monitor,
        "execution": execution,
        "historical": historical,
        "prior_recheck": prior_recheck,
        "deep_case": bool(reasons),
        "deep_reasons": reasons,
    }


def recheck_triggers(state: dict[str, Any], *, now: datetime | None = None) -> list[str]:
    if state.get("deep_case") is not True:
        return []
    now = now or datetime.now(timezone.utc)
    prior = state.get("prior_recheck") if isinstance(state.get("prior_recheck"), dict) else {}
    historical = state.get("historical") if isinstance(state.get("historical"), dict) else {}
    thesis = state.get("thesis") if isinstance(state.get("thesis"), dict) else {}
    position = state.get("position") if isinstance(state.get("position"), dict) else {}
    capital = (
        state.get("capital_control")
        if isinstance(state.get("capital_control"), dict)
        else state.get("capital_watch") if isinstance(state.get("capital_watch"), dict) else {}
    )

    triggers: list[str] = []
    if not historical:
        triggers.append("MISSING_HISTORICAL_REVIEW")
    if not prior:
        triggers.append("DEEP_CASE_BASELINE")

    thesis_status = str(thesis.get("thesis_status") or "").upper()
    flags = {str(value).upper() for value in thesis.get("flags") or []}
    if thesis_status in {"THESIS_BROKEN", "REUNDERWRITE_REQUIRED"} or flags & MATERIAL_THESIS_FLAGS:
        triggers.append("MATERIAL_THESIS_CHANGE")

    current_return = _safe_float(position.get("return_pct"))
    prior_return = _safe_float(prior.get("observed_return_pct"))
    if current_return is not None:
        if prior_return is not None and abs(current_return - prior_return) >= PRICE_MOVE_TRIGGER_PCT:
            triggers.append("MATERIAL_PRICE_MOVE")
        elif not prior and abs(current_return) >= PRICE_MOVE_TRIGGER_PCT:
            triggers.append("MATERIAL_PRICE_MOVE")

    stage = str(capital.get("stage") or "").upper()
    prior_stage = str(prior.get("capital_stage") or "").upper()
    if stage and prior_stage and stage != prior_stage:
        triggers.append("CAPITAL_STAGE_CHANGE")
    if stage == "READY_FOR_POSITION_SIZING":
        triggers.append("ENTRY_GATE_READY")
    entry_gap = _safe_float(capital.get("entry_gap_pct"))
    if (
        capital.get("entry_reference_active") is True
        and entry_gap is not None
        and entry_gap <= NEAR_ENTRY_GAP_PCT
    ):
        triggers.append("NEAR_ENTRY_PRICE")

    prior_time = _parse_time(prior.get("created_at") or prior.get("updated_at"))
    if prior_time is not None:
        elapsed_hours = max(0.0, (now.astimezone(timezone.utc) - prior_time).total_seconds() / 3600.0)
        if elapsed_hours >= PERIODIC_RECHECK_HOURS:
            triggers.append("PERIODIC_PRECEDENT_REFRESH")

    return list(dict.fromkeys(triggers))


def run_historical_recheck(case_id: str, *, force: bool = False) -> dict[str, Any]:
    state = deep_case_state(case_id)
    if state.get("deep_case") is not True:
        return {
            "case_id": case_id,
            "ticker": state.get("ticker"),
            "status": "SKIPPED_NOT_DEEP_CASE",
            "triggered": False,
            "deep_reasons": state.get("deep_reasons") or [],
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    triggers = recheck_triggers(state)
    if force and not triggers:
        triggers = ["FORCED_RECHECK"]
    if not triggers:
        return {
            "case_id": case_id,
            "ticker": state.get("ticker"),
            "status": "SKIPPED_NOT_DUE",
            "triggered": False,
            "deep_reasons": state.get("deep_reasons") or [],
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    prior_historical = state.get("historical") if isinstance(state.get("historical"), dict) else {}
    prior_signal = prior_historical.get("historical_signal")
    historical = run_historical_pattern_review(case_id)
    current_signal = historical.get("historical_signal")
    signal_changed = bool(prior_signal and current_signal and prior_signal != current_signal)

    severe = bool(
        set(triggers)
        & {
            "MATERIAL_THESIS_CHANGE",
            "ENTRY_GATE_READY",
            "CAPITAL_STAGE_CHANGE",
            "MATERIAL_PRICE_MOVE",
            "NEAR_ENTRY_PRICE",
        }
    )
    committee_refresh_required = bool(signal_changed or severe)
    reunderwrite_required = bool(
        committee_refresh_required
        or str((state.get("thesis") or {}).get("thesis_status") or "").upper()
        in {"THESIS_BROKEN", "REUNDERWRITE_REQUIRED"}
    )

    capital = state.get("capital_control") if isinstance(state.get("capital_control"), dict) else {}
    recheck_id = f"historical_recheck_{uuid4().hex}"
    payload = {
        "historical_recheck_id": recheck_id,
        "policy_version": POLICY_VERSION,
        "case_id": case_id,
        "ticker": state.get("ticker"),
        "topic": (state.get("case") or {}).get("topic"),
        "deep_reasons": state.get("deep_reasons") or [],
        "triggers": triggers,
        "historical_pattern_review_id": historical.get("historical_pattern_review_id"),
        "prior_historical_signal": prior_signal,
        "historical_signal": current_signal,
        "historical_signal_changed": signal_changed,
        "historical_confidence": historical.get("confidence"),
        "historical_disposition": historical.get("disposition"),
        "analog_stats": historical.get("analog_stats") or {},
        "observed_return_pct": (state.get("position") or {}).get("return_pct"),
        "thesis_status": (state.get("thesis") or {}).get("thesis_status"),
        "thesis_flags": (state.get("thesis") or {}).get("flags") or [],
        "capital_source": capital.get("source"),
        "capital_stage": capital.get("stage"),
        "capital_current_price": capital.get("current_price"),
        "maximum_qualifying_entry": capital.get("maximum_qualifying_entry"),
        "entry_gap_pct": capital.get("entry_gap_pct"),
        "entry_reference_active": capital.get("entry_reference_active") is True,
        "entry_reference_status": capital.get("entry_reference_status"),
        "capital_failed_hard_checks": capital.get("failed_hard_checks") or [],
        "capital_status_error": capital.get("error"),
        "committee_disposition": (state.get("committee") or {}).get("disposition"),
        "committee_confidence": (state.get("committee") or {}).get("confidence"),
        "committee_refresh_required": committee_refresh_required,
        "reunderwrite_required": reunderwrite_required,
        "next_action": (
            "FRESH_GOVERNED_REUNDERWRITE_REQUIRED"
            if reunderwrite_required
            else "CONTINUE_MONITORING"
        ),
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(recheck_id, OBJECT_TYPE, case_id, payload, topic=str(payload.get("topic") or ""))
    record_event(
        case_id,
        "DEEP_CASE_HISTORICAL_RECHECK_COMPLETE",
        entity_id=recheck_id,
        payload={
            "ticker": payload.get("ticker"),
            "triggers": triggers,
            "historical_signal": current_signal,
            "historical_signal_changed": signal_changed,
            "capital_stage": payload.get("capital_stage"),
            "entry_reference_active": payload.get("entry_reference_active"),
            "entry_gap_pct": payload.get("entry_gap_pct"),
            "committee_refresh_required": committee_refresh_required,
            "reunderwrite_required": reunderwrite_required,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )
    return {**payload, "status": "COMPLETE", "triggered": True}


def sweep_deep_cases(*, limit: int = 100, force: bool = False) -> dict[str, Any]:
    cases = _rows_by_type("case", limit)
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id") or "").strip()
        if not case_id or case_id in seen:
            continue
        seen.add(case_id)
        try:
            result = run_historical_recheck(case_id, force=force)
        except Exception as exc:
            result = {
                "case_id": case_id,
                "status": "ERROR",
                "triggered": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trade_execution_permission": False,
                "live_execution": False,
            }
        if result.get("status") != "SKIPPED_NOT_DEEP_CASE":
            results.append(result)

    complete = [row for row in results if row.get("status") == "COMPLETE"]
    required = [row for row in complete if row.get("reunderwrite_required") is True]
    signals = Counter(str(row.get("historical_signal") or "UNKNOWN") for row in complete)
    active_entry = [row for row in complete if row.get("entry_reference_active") is True]
    return {
        "checked_cases": len(seen),
        "deep_cases": len(results),
        "rechecked_cases": len(complete),
        "reunderwrite_required": len(required),
        "active_entry_references": len(active_entry),
        "historical_signals": dict(signals),
        "results": results,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "generated_at": utc_now(),
    }


def historical_recheck_status(limit: int = 100) -> dict[str, Any]:
    rows = _rows_by_type(OBJECT_TYPE, limit)
    return {
        "recheck_count": len(rows),
        "latest": rows[0] if rows else None,
        "rechecks": rows,
        "reunderwrite_required": sum(1 for row in rows if row.get("reunderwrite_required") is True),
        "active_entry_references": sum(1 for row in rows if row.get("entry_reference_active") is True),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
