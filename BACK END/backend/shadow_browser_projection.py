from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch9i-browser-shadow-strategy-v1"
OUTPUT_FIELDS = frozenset({
    "schema_version", "generated_at", "source_session", "source_artifact_hash", "status",
    "truth_state", "complete_sessions", "required_sessions", "maturity_state",
    "five_session_mature_count", "advice_issued", "observational_only",
    "automatic_threshold_changes", "automatic_weight_changes", "judgment_bank_auto_write",
    "ledger_read", "ledger_write", "trade_execution_permission", "broker_connected",
    "live_execution", "reason",
})
SOURCE_FIELDS = frozenset({
    "generated_at", "status", "complete_session_count", "minimum_complete_sessions_for_advice",
    "latest_session_id", "session_ids", "advice_issued", "five_session_mature_count", "safety",
})
SAFETY_FIELDS = frozenset({
    "ledger_mode", "auto_apply_threshold_changes", "automatic_agent_weight_changes",
    "auto_write_judgment_bank", "trade_execution_permission", "broker_connected", "live_execution",
})
SOURCE_STATUS = frozenset({"ADVISORY_READY", "WARMUP_COLLECTING_COMPLETE_SESSIONS"})
SESSION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
HASH_RE = re.compile(r"^[a-f0-9]{64}$")


class ProjectionRejected(ValueError):
    pass


def _reject(category: str = "SANITIZATION_FAILED") -> None:
    raise ProjectionRejected(category)


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        _reject()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _reject()
    if parsed.tzinfo is None:
        _reject()
    return parsed.astimezone(timezone.utc)


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 60:
        _reject()
    return value


def private_artifact_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def private_artifact_hash(payload: Any) -> str:
    return hashlib.sha256(private_artifact_bytes(payload)).hexdigest()


def unavailable(generated_at: str, reason: str = "SANITIZATION_FAILED") -> dict[str, Any]:
    if reason not in {"SANITIZATION_FAILED", "SESSION_MISMATCH"}:
        reason = "SANITIZATION_FAILED"
    try:
        generated = _timestamp(generated_at).isoformat()
    except ProjectionRejected:
        generated = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION, "generated_at": generated, "source_session": "UNAVAILABLE",
        "source_artifact_hash": hashlib.sha256(b"").hexdigest(), "status": "UNAVAILABLE",
        "truth_state": "UNAVAILABLE", "complete_sessions": 0, "required_sessions": 5,
        "maturity_state": "UNAVAILABLE", "five_session_mature_count": 0, "advice_issued": False,
        "observational_only": True, "automatic_threshold_changes": False,
        "automatic_weight_changes": False, "judgment_bank_auto_write": False, "ledger_read": True,
        "ledger_write": False, "trade_execution_permission": False, "broker_connected": False,
        "live_execution": False, "reason": reason,
    }


def project(source: Any, source_hash: str, *, now: datetime | None = None,
            stale_after_seconds: int = 86_400) -> dict[str, Any]:
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        _reject()
    if not isinstance(source_hash, str) or not HASH_RE.fullmatch(source_hash):
        _reject()
    safety = source["safety"]
    if not isinstance(safety, dict) or set(safety) != SAFETY_FIELDS:
        _reject()
    generated = _timestamp(source["generated_at"])
    session, sessions = source["latest_session_id"], source["session_ids"]
    if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
        _reject()
    if not isinstance(sessions, list) or not sessions or len(sessions) > 60:
        _reject()
    if any(not isinstance(item, str) or not SESSION_RE.fullmatch(item) for item in sessions):
        _reject()
    if session != sessions[-1]:
        _reject("SESSION_MISMATCH")
    complete, required, mature = map(_integer, (
        source["complete_session_count"], source["minimum_complete_sessions_for_advice"],
        source["five_session_mature_count"],
    ))
    if required < 1 or complete != len(sessions) or mature > complete:
        _reject()
    if (complete < 5 and mature != 0) or (complete >= 5 and mature < 1):
        _reject()
    if source["status"] not in SOURCE_STATUS or not isinstance(source["advice_issued"], bool):
        _reject()
    if safety["ledger_mode"] != "READ_ONLY":
        _reject()
    for key in SAFETY_FIELDS - {"ledger_mode"}:
        if not isinstance(safety[key], bool) or safety[key]:
            _reject()
    if not isinstance(stale_after_seconds, int) or stale_after_seconds < 1:
        _reject()
    if ((now or datetime.now(timezone.utc)).astimezone(timezone.utc) - generated).total_seconds() > stale_after_seconds:
        status, truth, maturity, reason = "UNAVAILABLE", "STALE", "UNAVAILABLE", "STALE_SOURCE"
    elif complete < required:
        status, truth, maturity, reason = "WARMUP", "INCOMPLETE", "WARMUP", "WARMUP"
    elif not source["advice_issued"]:
        status, truth, maturity, reason = "NO_ADVICE", "CURRENT", "FIVE_SESSION_MATURE", "NO_ADVICE"
    else:
        status, truth, maturity, reason = "READY", "CURRENT", "FIVE_SESSION_MATURE", "READY"
    return {
        "schema_version": SCHEMA_VERSION, "generated_at": generated.isoformat(), "source_session": session,
        "source_artifact_hash": source_hash, "status": status, "truth_state": truth,
        "complete_sessions": complete, "required_sessions": required, "maturity_state": maturity,
        "five_session_mature_count": mature, "advice_issued": source["advice_issued"],
        "observational_only": True, "automatic_threshold_changes": False,
        "automatic_weight_changes": False, "judgment_bank_auto_write": False, "ledger_read": True,
        "ledger_write": False, "trade_execution_permission": False, "broker_connected": False,
        "live_execution": False, "reason": reason,
    }


def project_or_unavailable(source: Any, source_hash: str, *, generated_at: str,
                           now: datetime | None = None) -> dict[str, Any]:
    try:
        return project(source, source_hash, now=now)
    except Exception as exc:
        reason = "SESSION_MISMATCH" if isinstance(exc, ProjectionRejected) and str(exc) == "SESSION_MISMATCH" else "SANITIZATION_FAILED"
        return unavailable(generated_at, reason)


def projection_bytes(payload: dict[str, Any]) -> bytes:
    if not isinstance(payload, dict) or set(payload) != OUTPUT_FIELDS:
        _reject()
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def publish(path: Path, payload: dict[str, Any]) -> None:
    encoded = projection_bytes(payload)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
