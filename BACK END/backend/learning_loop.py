from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from evidence_engine import build_packet
from ledger import DB_PATH, get_audit, get_object, latest_object, list_objects, record_event, record_object


router = APIRouter()
PAPER_MODE = True
DEFAULT_DRAWDOWN_TRIGGER_PCT = 5.0
OUTCOMES = {"SUPPORTED", "INVALIDATED", "INCONCLUSIVE"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _require_case(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    return case


def _latest(case_id: str, object_type: str) -> dict[str, Any] | None:
    return latest_object(object_type, case_id=case_id)


def _position_mode(case_id: str) -> str:
    executions = list_objects(case_id, "execution")
    if any(item.get("execution") == "PAPER_ORDER_CREATED" for item in executions):
        return "PAPER_POSITION"
    return "SHADOW_CASE"


def _return_pct(direction: str, reference_price: float | None, current_price: float | None) -> float | None:
    if reference_price is None or current_price is None or reference_price <= 0:
        return None
    raw = ((current_price - reference_price) / reference_price) * 100.0
    if direction == "SHORT":
        raw *= -1
    if direction not in {"LONG", "SHORT"}:
        return None
    return round(raw, 4)


def record_position_monitor(request: dict[str, Any]) -> dict[str, Any]:
    case_id = str(request.get("case_id", "")).strip()
    case = _require_case(case_id)
    direction = str(request.get("direction", "UNSPECIFIED")).upper()
    if direction not in {"LONG", "SHORT", "UNSPECIFIED"}:
        raise HTTPException(status_code=422, detail="direction must be LONG, SHORT, or UNSPECIFIED")

    reference_price = _safe_float(request.get("reference_price"))
    current_price = _safe_float(request.get("current_price"))
    update_packet = build_packet(request.get("evidence") if isinstance(request.get("evidence"), list) else [])
    return_pct = _return_pct(direction, reference_price, current_price)
    flags: list[str] = []
    mode = _position_mode(case_id)
    if mode == "SHADOW_CASE":
        flags.append("NO_PAPER_ORDER_EXISTS")
    if return_pct is None:
        flags.append("RETURN_NOT_COMPUTABLE")

    monitor_id = f"position_{uuid4().hex}"
    parent = _latest(case_id, "execution") or _latest(case_id, "committee_decision") or case
    parent_id = parent.get("execution_id") or parent.get("decision_id") or case_id
    monitor = {
        "position_monitor_id": monitor_id,
        "case_id": case_id,
        "topic": case.get("topic"),
        "mode": mode,
        "direction": direction,
        "reference_price": reference_price,
        "current_price": current_price,
        "return_pct": return_pct,
        "observations": request.get("observations") if isinstance(request.get("observations"), list) else [],
        "evidence_update": update_packet,
        "flags": flags,
        "status": "OBSERVING",
        "paper_mode": PAPER_MODE,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(monitor_id, "position_monitor", case_id, monitor, parent_id=parent_id, topic=case.get("topic"))
    record_event(case_id, "POSITION_MONITORED", entity_id=monitor_id, payload={"mode": mode, "return_pct": return_pct, "flags": flags})
    return monitor


def record_thesis_monitor(request: dict[str, Any]) -> dict[str, Any]:
    case_id = str(request.get("case_id", "")).strip()
    case = _require_case(case_id)
    decision = _latest(case_id, "committee_decision")
    if not decision:
        raise HTTPException(status_code=409, detail="Committee decision required before thesis monitoring")

    latest_position = _latest(case_id, "position_monitor")
    falsifiers_triggered = [str(item) for item in (request.get("falsifiers_triggered") or []) if str(item).strip()]
    catalyst_status = str(request.get("catalyst_status", "UNKNOWN")).upper()
    if catalyst_status not in {"ON_TRACK", "MISSED", "UNKNOWN", "ACHIEVED"}:
        raise HTTPException(status_code=422, detail="Invalid catalyst_status")

    update_packet = build_packet(request.get("evidence") if isinstance(request.get("evidence"), list) else [])
    update_flags = set(update_packet["summary"].get("critical_flags") or [])
    drawdown_trigger = abs(_safe_float(request.get("drawdown_trigger_pct")) or DEFAULT_DRAWDOWN_TRIGGER_PCT)
    return_pct = _safe_float((latest_position or {}).get("return_pct"))

    flags: list[str] = []
    if falsifiers_triggered:
        flags.append("FALSIFIER_TRIGGERED")
    if catalyst_status == "MISSED":
        flags.append("CATALYST_MISSED")
    if "ALL_EVIDENCE_STALE" in update_flags:
        flags.append("UPDATE_EVIDENCE_STALE")
    if "CONFLICTING_EVIDENCE_PRESENT" in update_flags:
        flags.append("UPDATE_EVIDENCE_CONFLICT")
    if return_pct is not None and return_pct <= -drawdown_trigger:
        flags.append("DRAWDOWN_TRIGGERED")

    if "FALSIFIER_TRIGGERED" in flags:
        thesis_status = "THESIS_BROKEN"
    elif flags:
        thesis_status = "REUNDERWRITE_REQUIRED"
    else:
        thesis_status = "INTACT"

    agent_falsifiers = {
        item.get("agent_key"): item.get("falsifier")
        for item in list_objects(case_id, "agent_result")
        if item.get("agent_key")
    }
    monitor_id = f"thesis_{uuid4().hex}"
    parent_id = (latest_position or {}).get("position_monitor_id") or decision.get("decision_id")
    monitor = {
        "thesis_monitor_id": monitor_id,
        "case_id": case_id,
        "decision_id": decision.get("decision_id"),
        "topic": case.get("topic"),
        "thesis_status": thesis_status,
        "flags": flags,
        "falsifiers_triggered": falsifiers_triggered,
        "agent_falsifiers": agent_falsifiers,
        "catalyst_status": catalyst_status,
        "drawdown_trigger_pct": drawdown_trigger,
        "observed_return_pct": return_pct,
        "evidence_update": update_packet,
        "notes": str(request.get("notes", "")),
        "paper_mode": PAPER_MODE,
        "created_at": utc_now(),
    }
    record_object(monitor_id, "thesis_monitor", case_id, monitor, parent_id=parent_id, topic=case.get("topic"))
    record_event(case_id, "THESIS_MONITORED", entity_id=monitor_id, payload={"thesis_status": thesis_status, "flags": flags})
    if thesis_status == "THESIS_BROKEN":
        record_event(case_id, "THESIS_BREAK_TRIGGERED", entity_id=monitor_id, payload={"falsifiers_triggered": falsifiers_triggered})
    return monitor


def record_reunderwrite(request: dict[str, Any]) -> dict[str, Any]:
    case_id = str(request.get("case_id", "")).strip()
    case = _require_case(case_id)
    thesis = _latest(case_id, "thesis_monitor")
    if not thesis:
        raise HTTPException(status_code=409, detail="Thesis monitor required before re-underwrite")

    update_packet = build_packet(request.get("evidence") if isinstance(request.get("evidence"), list) else [])
    status = thesis.get("thesis_status")
    if status == "THESIS_BROKEN":
        action = "EXIT_SHADOW_CASE"
    elif status == "REUNDERWRITE_REQUIRED":
        action = "PAUSE_AND_REUNDERWRITE"
    else:
        action = "MAINTAIN_WATCH"

    reunderwrite_id = f"reunderwrite_{uuid4().hex}"
    result = {
        "reunderwrite_id": reunderwrite_id,
        "case_id": case_id,
        "thesis_monitor_id": thesis.get("thesis_monitor_id"),
        "topic": case.get("topic"),
        "prior_thesis_status": status,
        "action": action,
        "evidence_update": update_packet,
        "notes": str(request.get("notes", "")),
        "paper_mode": PAPER_MODE,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(reunderwrite_id, "reunderwrite", case_id, result, parent_id=thesis.get("thesis_monitor_id"), topic=case.get("topic"))
    record_event(case_id, "REUNDERWRITE_COMPLETE", entity_id=reunderwrite_id, payload={"action": action, "prior_thesis_status": status})
    return result


def _call_correct(disposition: str, outcome: str) -> bool | None:
    if outcome == "INCONCLUSIVE":
        return None
    if outcome == "SUPPORTED":
        return disposition == "WATCH"
    return disposition == "NO_TRADE"


def _calibration_score(confidence: float, correct: bool | None) -> float:
    if correct is None:
        return 0.5
    target = 1.0 if correct else 0.0
    return round(max(0.0, 1.0 - abs(confidence - target)), 4)


def record_postmortem(request: dict[str, Any]) -> dict[str, Any]:
    case_id = str(request.get("case_id", "")).strip()
    case = _require_case(case_id)
    outcome = str(request.get("outcome", "INCONCLUSIVE")).upper()
    if outcome not in OUTCOMES:
        raise HTTPException(status_code=422, detail="outcome must be SUPPORTED, INVALIDATED, or INCONCLUSIVE")

    decision = _latest(case_id, "committee_decision")
    if not decision:
        raise HTTPException(status_code=409, detail="Committee decision required before post-mortem")
    agents = list_objects(case_id, "agent_result")
    realized_return_pct = _safe_float(request.get("realized_return_pct"))
    postmortem_id = f"postmortem_{uuid4().hex}"

    entries: list[dict[str, Any]] = []
    for agent in agents:
        confidence = max(0.0, min(1.0, _safe_float(agent.get("confidence")) or 0.0))
        disposition = str(agent.get("disposition", "NO_TRADE")).upper()
        correct = _call_correct(disposition, outcome)
        entry = {
            "judgment_entry_id": f"judgment_{uuid4().hex}",
            "postmortem_id": postmortem_id,
            "case_id": case_id,
            "agent_key": agent.get("agent_key"),
            "agent": agent.get("agent"),
            "original_disposition": disposition,
            "original_confidence": confidence,
            "outcome": outcome,
            "correct": correct,
            "calibration_score": _calibration_score(confidence, correct),
            "realized_return_pct": realized_return_pct,
            "paper_mode": PAPER_MODE,
            "created_at": utc_now(),
        }
        entries.append(entry)

    avg_calibration = round(sum(item["calibration_score"] for item in entries) / len(entries), 4) if entries else 0.0
    ranked = sorted(entries, key=lambda item: item["calibration_score"], reverse=True)
    decision_confidence = max(0.0, min(1.0, _safe_float(decision.get("confidence")) or 0.0))
    decision_correct = _call_correct(str(decision.get("disposition", "NO_TRADE")).upper(), outcome)
    postmortem = {
        "postmortem_id": postmortem_id,
        "case_id": case_id,
        "decision_id": decision.get("decision_id"),
        "topic": case.get("topic"),
        "outcome": outcome,
        "realized_return_pct": realized_return_pct,
        "horizon_days": _safe_float(request.get("horizon_days")),
        "committee_disposition": decision.get("disposition"),
        "committee_confidence": decision_confidence,
        "committee_correct": decision_correct,
        "committee_calibration_score": _calibration_score(decision_confidence, decision_correct),
        "agent_count": len(entries),
        "average_agent_calibration": avg_calibration,
        "best_calibrated_agent": ranked[0].get("agent_key") if ranked else None,
        "worst_calibrated_agent": ranked[-1].get("agent_key") if ranked else None,
        "notes": str(request.get("notes", "")),
        "paper_mode": PAPER_MODE,
        "created_at": utc_now(),
    }
    parent = _latest(case_id, "reunderwrite") or _latest(case_id, "thesis_monitor") or decision
    parent_id = parent.get("reunderwrite_id") or parent.get("thesis_monitor_id") or decision.get("decision_id")
    record_object(postmortem_id, "postmortem", case_id, postmortem, parent_id=parent_id, topic=case.get("topic"))
    for entry in entries:
        record_object(entry["judgment_entry_id"], "judgment_entry", case_id, entry, parent_id=postmortem_id, topic=case.get("topic"))
    record_event(case_id, "POST_MORTEM_COMPLETE", entity_id=postmortem_id, payload={"outcome": outcome, "average_agent_calibration": avg_calibration})
    record_event(case_id, "JUDGMENT_BANK_UPDATED", entity_id=postmortem_id, payload={"entries_added": len(entries)})
    return {"postmortem": postmortem, "judgment_entries": entries}


def _all_judgment_entries() -> list[dict[str, Any]]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type = ? ORDER BY created_at ASC",
            ("judgment_entry",),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def build_agent_scorecards() -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in _all_judgment_entries():
        key = str(entry.get("agent_key") or "unknown")
        groups[key].append(entry)

    scorecards: list[dict[str, Any]] = []
    for agent_key, entries in groups.items():
        decisive = [item for item in entries if item.get("correct") is not None]
        correct_count = sum(1 for item in decisive if item.get("correct") is True)
        accuracy = round(correct_count / len(decisive), 4) if decisive else None
        avg_confidence = round(sum(float(item.get("original_confidence", 0.0)) for item in entries) / len(entries), 4)
        avg_calibration = round(sum(float(item.get("calibration_score", 0.0)) for item in entries) / len(entries), 4)
        scorecards.append({
            "agent_key": agent_key,
            "agent": entries[-1].get("agent"),
            "observations": len(entries),
            "decisive_observations": len(decisive),
            "correct_calls": correct_count,
            "accuracy": accuracy,
            "average_confidence": avg_confidence,
            "average_calibration_score": avg_calibration,
            "paper_mode": PAPER_MODE,
        })
    return sorted(scorecards, key=lambda item: item["average_calibration_score"], reverse=True)


@router.post("/monitor/position")
def monitor_position(request: dict = Body(...)):
    return record_position_monitor(request)


@router.post("/monitor/thesis")
def monitor_thesis(request: dict = Body(...)):
    return record_thesis_monitor(request)


@router.post("/reunderwrite/run")
def run_reunderwrite(request: dict = Body(...)):
    return record_reunderwrite(request)


@router.post("/post-mortem/run")
def run_postmortem(request: dict = Body(...)):
    return record_postmortem(request)


@router.get("/judgment-bank/{case_id}")
def get_judgment_bank_case(case_id: str):
    _require_case(case_id)
    return {
        "case_id": case_id,
        "position_monitors": list_objects(case_id, "position_monitor"),
        "thesis_monitors": list_objects(case_id, "thesis_monitor"),
        "reunderwrites": list_objects(case_id, "reunderwrite"),
        "postmortems": list_objects(case_id, "postmortem"),
        "judgment_entries": list_objects(case_id, "judgment_entry"),
    }


@router.get("/judgment-bank/scorecards/all")
def get_agent_scorecards():
    return {"scorecards": build_agent_scorecards(), "paper_mode": PAPER_MODE}


@router.get("/learning-loop/audit/{case_id}")
def get_learning_audit(case_id: str):
    _require_case(case_id)
    audit = get_audit(case_id)
    return {
        "case_id": case_id,
        "position_monitors": list_objects(case_id, "position_monitor"),
        "thesis_monitors": list_objects(case_id, "thesis_monitor"),
        "reunderwrites": list_objects(case_id, "reunderwrite"),
        "postmortems": list_objects(case_id, "postmortem"),
        "judgment_entries": list_objects(case_id, "judgment_entry"),
        "events": audit["events"],
    }


@router.post("/learning-loop/run")
def run_learning_loop(request: dict = Body(...)):
    case_id = str(request.get("case_id", "")).strip()
    _require_case(case_id)
    position_payload = {"case_id": case_id, **(request.get("position") or {})}
    thesis_payload = {"case_id": case_id, **(request.get("thesis") or {})}
    reunderwrite_payload = {"case_id": case_id, **(request.get("reunderwrite") or {})}
    position = record_position_monitor(position_payload)
    thesis = record_thesis_monitor(thesis_payload)
    reunderwrite = record_reunderwrite(reunderwrite_payload)
    result: dict[str, Any] = {
        "case_id": case_id,
        "position": position,
        "thesis": thesis,
        "reunderwrite": reunderwrite,
        "chain": ["POSITION_MONITORED", "THESIS_MONITORED", "REUNDERWRITE_COMPLETE"],
        "paper_mode": PAPER_MODE,
    }
    postmortem_payload = request.get("postmortem")
    if isinstance(postmortem_payload, dict) and postmortem_payload:
        postmortem = record_postmortem({"case_id": case_id, **postmortem_payload})
        result["postmortem"] = postmortem
        result["chain"].extend(["POST_MORTEM_COMPLETE", "JUDGMENT_BANK_UPDATED"])
    return result
