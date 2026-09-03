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
    "schema_version", "generated_at", "source_session", "source_artifact_hash",
    "status", "truth_state", "complete_sessions", "required_sessions",
    "maturity_state", "five_session_mature_count", "advice_issued",
    "observational_only", "automatic_threshold_changes", "automatic_weight_changes",
    "judgment_bank_auto_write", "ledger_read", "ledger_write",
    "trade_execution_permission", "broker_connected", "live_execution", "reason",
})
SOURCE_FIELDS = frozenset({
    "generated_at", "status", "complete_session_count",
    "minimum_complete_sessions_for_advice", "latest_session_id", "session_ids",
    "advice_issued", "five_session_mature_count", "safety",
})
SAFETY_FIELDS = frozenset({
    "ledger_mode", "auto_apply_threshold_changes", "automatic_agent_weight_changes",
    "auto_write_judgment_bank", "trade_execution_permission", "broker_connected",
    "live_execution",
})
STATUS = frozenset({"READY", "WARMUP", "NO_ADVICE", "UNAVAILABLE"})
TRUTH = frozenset({"CURRENT", "INCOMPLETE", "STALE", "UNAVAILABLE"})
MATURITY = frozenset({"FIVE_SESSION_MATURE", "WARMUP", "UNAVAILABLE"})
REASONS = frozenset({"READY", "WARMUP", "NO_ADVICE", "STALE_SOURCE", "SESSION_MISMATCH", "SANITIZATION_FAILED"})
SOURCE_STATUS = frozenset({"ADVISORY_READY", "WARMUP_COLLECTING_COMPLETE_SESSIONS"})
SESSION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
HASH_RE = re.compile(r"^[a-f0-9]{64}$")


class ProjectionRejected(ValueError):
    """Fixed-message rejection that never includes source content."""


def _reject() -> None:
    raise ProjectionRejected("BATCH9I_BROWSER_PROJECTION_REJECTED")


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        _reject()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _reject()
    if parsed.tzinfo is None:
        _reject()
    return parsed.astimezone(timezone.utc)


def _bounded_int(value: Any, maximum: int = 10_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        _reject()
    return value


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        _reject()
    return value


def _validate_source(source: Any, source_hash: str) -> tuple[datetime, str, int, int, int, bool, dict[str, Any]]:
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS or not isinstance(source_hash, str) or not HASH_RE.fullmatch(source_hash):
        _reject()
    safety = source["safety"]
    if not isinstance(safety, dict) or set(safety) != SAFETY_FIELDS:
        _reject()
    generated = _time(source["generated_at"])
    session = source["latest_session_id"]
    sessions = source["session_ids"]
    if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
        _reject()
    if not isinstance(sessions, list) or not sessions or len(sessions) > 60:
        _reject()
    if any(not isinstance(item, str) or not SESSION_RE.fullmatch(item) for item in sessions):
        _reject()
    if session != sessions[-1]:
        raise ProjectionRejected("BATCH9I_BROWSER_SESSION_MISMATCH")
    complete = _bounded_int(source["complete_session_count"], 60)
    required = _bounded_int(source["minimum_complete_sessions_for_advice"], 60)
    mature = _bounded_int(source["five_session_mature_count"], 60)
    advice = _bool(source["advice_issued"])
    if required < 1 or complete != len(sessions) or mature > complete:
        _reject()
    if (complete < 5 and mature != 0) or (complete >= 5 and mature < 1):
        _reject()
    if safety["ledger_mode"] != "READ_ONLY":
        _reject()
    for key in SAFETY_FIELDS - {"ledger_mode"}:
        if _bool(safety[key]):
            _reject()
    status = source["status"]
    if status not in SOURCE_STATUS:
        _reject()
    return generated, session, complete, required, mature, advice, safety


def build_projection(source: Any, source_artifact_hash: str, *, now: datetime | None = None,
                     stale_after_seconds: int = 86_400) -> dict[str, Any]:
    generated, session, complete, required, mature, advice, _ = _validate_source(source, source_artifact_hash)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if stale_after_seconds < 1:
        _reject()
    if (current - generated).total_seconds() > stale_after_seconds:
        status, truth, maturity, reason = "UNAVAILABLE", "STALE", "UNAVAILABLE", "STALE_SOURCE"
    elif complete < required:
        status, truth, maturity, reason = "WARMUP", "INCOMPLETE", "WARMUP", "WARMUP"
    elif not advice:
        status, truth, maturity, reason = "NO_ADVICE", "CURRENT", "FIVE_SESSION_MATURE", "NO_ADVICE"
    else:
        status, truth, maturity, reason = "READY", "CURRENT", "FIVE_SESSION_MATURE", "READY"
    payload = {
        "schema_version": SCHEMA_VERSION, "generated_at": generated.isoformat(),
        "source_session": session, "source_artifact_hash": source_artifact_hash,
        "status": status, "truth_state": truth, "complete_sessions": complete,
        "required_sessions": required, "maturity_state": maturity,
        "five_session_mature_count": mature, "advice_issued": advice,
        "observational_only": True, "automatic_threshold_changes": False,
        "automatic_weight_changes": False, "judgment_bank_auto_write": False,
        "ledger_read": True, "ledger_write": False, "trade_execution_permission": False,
        "broker_connected": False, "live_execution": False, "reason": reason,
    }
    validate_projection(payload)
    return payload


def unavailable_projection(generated_at: str, *, reason: str = "SANITIZATION_FAILED") -> dict[str, Any]:
    if reason not in {"SANITIZATION_FAILED", "SESSION_MISMATCH"}:
        _reject()
    generated = _time(generated_at).isoformat()
    payload = {
        "schema_version": SCHEMA_VERSION, "generated_at": generated,
        "source_session": "UNAVAILABLE", "source_artifact_hash": hashlib.sha256(b"").hexdigest(),
        "status": "UNAVAILABLE", "truth_state": "UNAVAILABLE", "complete_sessions": 0,
        "required_sessions": 5, "maturity_state": "UNAVAILABLE", "five_session_mature_count": 0,
        "advice_issued": False, "observational_only": True,
        "automatic_threshold_changes": False, "automatic_weight_changes": False,
        "judgment_bank_auto_write": False, "ledger_read": True, "ledger_write": False,
        "trade_execution_permission": False, "broker_connected": False,
        "live_execution": False, "reason": reason,
    }
    validate_projection(payload)
    return payload


def build_or_unavailable(source: Any, source_artifact_hash: str, *, generated_at: str,
                         now: datetime | None = None, stale_after_seconds: int = 86_400) -> dict[str, Any]:
    try:
        return build_projection(source, source_artifact_hash, now=now, stale_after_seconds=stale_after_seconds)
    except ProjectionRejected as exc:
        reason = "SESSION_MISMATCH" if str(exc) == "BATCH9I_BROWSER_SESSION_MISMATCH" else "SANITIZATION_FAILED"
        return unavailable_projection(generated_at, reason=reason)


def validate_projection(payload: Any) -> None:
    if not isinstance(payload, dict) or set(payload) != OUTPUT_FIELDS:
        _reject()
    if payload["schema_version"] != SCHEMA_VERSION or payload["status"] not in STATUS:
        _reject()
    if payload["truth_state"] not in TRUTH or payload["maturity_state"] not in MATURITY or payload["reason"] not in REASONS:
        _reject()
    _time(payload["generated_at"])
    if not isinstance(payload["source_session"], str) or not SESSION_RE.fullmatch(payload["source_session"]):
        _reject()
    if not HASH_RE.fullmatch(str(payload["source_artifact_hash"])):
        _reject()
    for key in ("complete_sessions", "required_sessions", "five_session_mature_count"):
        _bounded_int(payload[key], 60)
    for key in OUTPUT_FIELDS - {"schema_version", "generated_at", "source_session", "source_artifact_hash", "status", "truth_state", "complete_sessions", "required_sessions", "maturity_state", "five_session_mature_count", "reason"}:
        _bool(payload[key])
    if payload["observational_only"] is not True or payload["ledger_read"] is not True:
        _reject()
    if any(payload[key] for key in ("automatic_threshold_changes", "automatic_weight_changes", "judgment_bank_auto_write", "ledger_write", "trade_execution_permission", "broker_connected", "live_execution")):
        _reject()


def deterministic_bytes(payload: dict[str, Any]) -> bytes:
    validate_projection(payload)
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def private_artifact_hash(payload: Any) -> str:
    """Hash the exact deterministic bytes written by the existing private producer."""
    encoded = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def publish_projection(path: Path, payload: dict[str, Any]) -> str:
    encoded = deterministic_bytes(payload)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return hashlib.sha256(encoded).hexdigest()
