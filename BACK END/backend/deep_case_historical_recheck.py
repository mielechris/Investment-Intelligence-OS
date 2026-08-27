from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import ledger
from historical_pattern_analyst import run_historical_pattern_review
from ledger import get_object, latest_object, record_event, record_object, utc_now

POLICY_VERSION = "batch10c-deep-case-historical-recheck-v1"
OBJECT_TYPE = "historical_recheck"
PERIODIC_RECHECK_HOURS = 24.0
PRICE_MOVE_TRIGGER_PCT = 5.0
NEAR_ENTRY_GAP_PCT = 3.0
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

    reasons: list[str] = []
    if str(committee.get("disposition") or "").upper() == "WATCH":
        reasons.append("COMMITTEE_WATCH")
    if qualification.get("qualified_buy_candidate") is True:
        reasons.append("QUALIFIED_BUY_CANDIDATE")
    if risk:
        reasons.append("RISK_REACHED")
    if capital_watch:
        reasons.append("CAPITAL_ENTRY_WATCH")
    if execution:
        reasons.append("PAPER_EXECUTION_LINEAGE")
    if monitor.get("enabled") is True and committee:
        reasons.append("ACTIVE_MONITORING")

    return {
        "case_id": case_id,
        "case": case,
        "committee": committee,
        "qualification": qualification,
        "risk": risk,
        "capital_watch": capital_watch,
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
    capital = state.get("capital_watch") if isinstance(state.get("capital_watch"), dict) else {}

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
    if entry_gap is not None and entry_gap <= NEAR_ENTRY_GAP_PCT:
        triggers.append("NEAR_ENTRY_PRICE")

    prior_time = _parse_time(prior.get("created_at") or prior.get("updated_at"))
    if prior_time is not None:
        elapsed_hours = max(0.0, (now.astimezone(timezone.utc) - prior_time).total_seconds() / 3600.0)
        if elapsed_hours >= PERIODIC_RECHECK_HOURS:
            triggers.append("PERIODIC_PRECEDENT_REFRESH")

    return list(dict.fromkeys(triggers))


def run_historical_recheck(case_id: str, *, force: bool = False) -> dict[str, Any]:
    state = deep_case_state(case_id)
    if state.get("deep_case") is not True and not force:
        return {
            "case_id": case_id,
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
        }
    )
    committee_refresh_required = bool(signal_changed or severe)
    reunderwrite_required = bool(
        committee_refresh_required
        or str((state.get("thesis") or {}).get("thesis_status") or "").upper()
        in {"THESIS_BROKEN", "REUNDERWRITE_REQUIRED"}
    )

    recheck_id = f"historical_recheck_{uuid4().hex}"
    payload = {
        "historical_recheck_id": recheck_id,
        "policy_version": POLICY_VERSION,
        "case_id": case_id,
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
        "capital_stage": (state.get("capital_watch") or {}).get("stage"),
        "entry_gap_pct": (state.get("capital_watch") or {}).get("entry_gap_pct"),
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
            "triggers": triggers,
            "historical_signal": current_signal,
            "historical_signal_changed": signal_changed,
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
    return {
        "checked_cases": len(seen),
        "deep_cases": len(results),
        "rechecked_cases": len(complete),
        "reunderwrite_required": len(required),
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
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
