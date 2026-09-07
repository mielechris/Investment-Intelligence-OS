"""Strict, offline operational state contract for the disabled Tuesday controller."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .tuesday_controller_state import CONTROLLER_ID, LOCKS, PHASE, _atomic, _hash, _timestamp, validate_installation, validate_state_v1
from .tuesday_whole_factory import DAILY_CEILING, PER_ENDPOINT_LIMIT, PER_INSTRUMENT_LIMIT, STAGE_LIMITS, core_request_plan

STATE_SCHEMA_V2 = "iios-tuesday-controller-state-v2"
BROWSER_SCHEMA_V2 = "iios-tuesday-controller-browser-v2"
LAST_KNOWN_VALID_NAME = "controller-state.last-known-valid.json"
V1_ROLLBACK_NAME = "controller-state.v1.rollback.json"
MIGRATION_STATUS = "MIGRATED_FROM_VALID_V1"
STAGE_FIELDS = {"maximum", "released", "locked", "approval_identity", "approval_timestamp", "draft_request_identities"}
V2_FIELDS = {
    "schema_version", "controller_identity", "installation_identity", "created_at", "updated_at", "sequence", "phase",
    "phase_history", "rehearsal_receipts", "confirmed_credits", "ambiguous_credits", "reserved_credits", "requests_used",
    "request_identities", "per_instrument_accounting", "per_endpoint_accounting", "daily_hard_ceiling",
    "released_credit_total", "stages", "installed", "running", "activated", "restart_recovery_status",
    "migration_status", "integrity_state", "authority", "authority_locked", "last_known_valid", "failure_category",
    "automatic_release", "automatic_retry", "automatic_reload", "browser_invocation", "content_hash",
}


def _identities(value: Any, *, exact: int | None = None) -> list[str]:
    if not isinstance(value, list) or len(value) > 200 or (exact is not None and len(value) != exact):
        raise ValueError("REQUEST_IDENTITY_INVALID")
    if len(value) != len(set(value)):
        raise ValueError("DUPLICATE_REQUEST_IDENTITY")
    if any(not isinstance(x, str) or not 8 <= len(x) <= 96 or any(ord(c) < 33 or ord(c) > 126 for c in x) for x in value):
        raise ValueError("REQUEST_IDENTITY_INVALID")
    return value


def _accounting(value: Any, category: str) -> dict[str, int]:
    if not isinstance(value, dict) or len(value) > 64 or any(
        not isinstance(k, str) or not 1 <= len(k) <= 64 or not isinstance(v, int) or isinstance(v, bool) or v < 0
        for k, v in value.items()
    ):
        raise ValueError(category)
    return value


def validate_state_v2(value: Any, installation: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    validate_installation(installation, now=now)
    if not isinstance(value, dict) or set(value) != V2_FIELDS or value.get("schema_version") != STATE_SCHEMA_V2:
        raise ValueError("STATE_V2_SCHEMA_INVALID")
    if value.get("controller_identity") != CONTROLLER_ID or value.get("installation_identity") != installation["installation_identity"]:
        raise ValueError("CONTROLLER_OR_INSTALLATION_IDENTITY_INVALID")
    created, updated = _timestamp(value.get("created_at"), now), _timestamp(value.get("updated_at"), now)
    if updated < created:
        raise ValueError("TIMESTAMP_ORDER_INVALID")
    history = value.get("phase_history")
    if value.get("phase") != PHASE or not isinstance(history, list) or not history or len(history) > 64 or history[-1] != PHASE:
        raise ValueError("PHASE_HISTORY_INVALID")
    if any(not isinstance(x, str) or len(x) > 64 for x in history):
        raise ValueError("PHASE_HISTORY_INVALID")
    if not isinstance(value.get("sequence"), int) or isinstance(value["sequence"], bool) or value["sequence"] < len(history) - 1:
        raise ValueError("SEQUENCE_INVALID")
    receipts = value.get("rehearsal_receipts")
    if not isinstance(receipts, list) or not receipts or len(receipts) > 64:
        raise ValueError("REHEARSAL_RECEIPTS_MISSING")
    for receipt in receipts:
        if not isinstance(receipt, dict) or set(receipt) != {"classification", "timestamp", "source_schema", "immutable"}:
            raise ValueError("REHEARSAL_RECEIPT_INVALID")
        if receipt["classification"] != "PASSED_CLOSED_HOLIDAY" or receipt["source_schema"] != "iios-tuesday-controller-state-v1" or receipt["immutable"] is not True:
            raise ValueError("REHEARSAL_RECEIPT_INVALID")
        _timestamp(receipt["timestamp"], now)
    identities = _identities(value.get("request_identities"))
    for key in ("confirmed_credits", "ambiguous_credits", "reserved_credits", "requests_used"):
        if not isinstance(value.get(key), int) or isinstance(value[key], bool) or value[key] < 0:
            raise ValueError("ACCOUNTING_INVALID")
    if value["requests_used"] != len(identities) or value["confirmed_credits"] + value["ambiguous_credits"] + value["reserved_credits"] > value["requests_used"]:
        raise ValueError("ACCOUNTING_DISAGREEMENT")
    instruments = _accounting(value.get("per_instrument_accounting"), "INSTRUMENT_ACCOUNTING_INVALID")
    endpoints = _accounting(value.get("per_endpoint_accounting"), "ENDPOINT_ACCOUNTING_INVALID")
    if any(x > PER_INSTRUMENT_LIMIT for x in instruments.values()) or any(x > PER_ENDPOINT_LIMIT for x in endpoints.values()):
        raise ValueError("ACCOUNTING_LIMIT_EXCEEDED")
    if value.get("daily_hard_ceiling") != DAILY_CEILING or value.get("released_credit_total") != 0:
        raise ValueError("BUDGET_CONTRACT_INVALID")
    stages = value.get("stages")
    expected = [row["request_identity"] for row in core_request_plan()]
    if not isinstance(stages, dict) or set(stages) != set(STAGE_LIMITS):
        raise ValueError("STAGE_SCHEMA_INVALID")
    for stage, maximum in STAGE_LIMITS.items():
        row = stages[stage]
        if not isinstance(row, dict) or set(row) != STAGE_FIELDS or row["maximum"] != maximum:
            raise ValueError("STAGE_SCHEMA_INVALID")
        if row["released"] != 0 or row["locked"] is not True or row["approval_identity"] is not None or row["approval_timestamp"] is not None:
            raise ValueError("STAGE_RELEASE_INVALID")
        draft = _identities(row["draft_request_identities"], exact=50 if stage == "A" else 0)
        if stage == "A" and draft != expected:
            raise ValueError("STAGE_A_DRAFT_INVALID")
    if sum(row["maximum"] for row in stages.values()) != DAILY_CEILING:
        raise ValueError("STAGE_TOTAL_INVALID")
    if value.get("installed") is not installation["installed"] or value.get("running") is not installation["process_running"] or value.get("activated") is not False:
        raise ValueError("CONTROLLER_STATE_INVALID")
    if value.get("authority") != LOCKS or value.get("authority_locked") is not True:
        raise ValueError("AUTHORITY_INVALID")
    if any(value.get(k) is not False for k in ("automatic_release", "automatic_retry", "automatic_reload", "browser_invocation")):
        raise ValueError("AUTOMATION_INVALID")
    if value.get("migration_status") not in {MIGRATION_STATUS, "V2_DISABLED_RECOVERY"} or value.get("integrity_state") != "VALID":
        raise ValueError("MIGRATION_OR_INTEGRITY_INVALID")
    if value.get("restart_recovery_status") not in {"NOT_REQUIRED", "RESTORED_EXACT_DISABLED_V2_STATE"}:
        raise ValueError("RECOVERY_CATEGORY_INVALID")
    lkv = value.get("last_known_valid")
    if not isinstance(lkv, dict) or set(lkv) != {"schema_version", "sequence", "content_hash"} or not isinstance(lkv["sequence"], int) or not isinstance(lkv["content_hash"], str) or len(lkv["content_hash"]) != 64:
        raise ValueError("LAST_KNOWN_VALID_INVALID")
    if value.get("failure_category") is not None or value.get("content_hash") != _hash(value):
        raise ValueError("STATE_V2_HASH_OR_FAILURE_INVALID")
    return value


def migrate_v1_to_v2(state: dict[str, Any], installation: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    validate_state_v1(state, installation)
    when = _timestamp(timestamp).isoformat()
    stages = {stage: {"maximum": maximum, "released": 0, "locked": True, "approval_identity": None,
                      "approval_timestamp": None, "draft_request_identities": [x["request_identity"] for x in core_request_plan()] if stage == "A" else []}
              for stage, maximum in STAGE_LIMITS.items()}
    value = {
        "schema_version": STATE_SCHEMA_V2, "controller_identity": CONTROLLER_ID, "installation_identity": state["installation_identity"],
        "created_at": state["updated_at"], "updated_at": when, "sequence": state["sequence"] + 1, "phase": state["phase"],
        "phase_history": list(state["phase_history"]), "rehearsal_receipts": [{"classification": state["monday_rehearsal_status"],
        "timestamp": state["updated_at"], "source_schema": state["schema_version"], "immutable": True}],
        "confirmed_credits": state["credits_used"], "ambiguous_credits": state["requests_used"] - state["credits_used"],
        "reserved_credits": 0, "requests_used": state["requests_used"], "request_identities": list(state["request_identities"]),
        "per_instrument_accounting": {}, "per_endpoint_accounting": {}, "daily_hard_ceiling": 200,
        "released_credit_total": 0, "stages": stages, "installed": state["installed"], "running": state["running"],
        "activated": False, "restart_recovery_status": "NOT_REQUIRED", "migration_status": MIGRATION_STATUS,
        "integrity_state": "VALID", "authority": LOCKS.copy(), "authority_locked": True,
        "last_known_valid": {"schema_version": state["schema_version"], "sequence": state["sequence"], "content_hash": state["content_hash"]},
        "failure_category": None, "automatic_release": False, "automatic_retry": False, "automatic_reload": False,
        "browser_invocation": False,
    }
    value["content_hash"] = _hash(value)
    return validate_state_v2(value, installation)


def recovered_v2(prior: dict[str, Any], prior_installation: dict[str, Any], installation: dict[str, Any], *, running: bool, timestamp: str) -> dict[str, Any]:
    validate_state_v2(prior, prior_installation)
    value = json.loads(json.dumps(prior))
    value.update({"running": running, "updated_at": _timestamp(timestamp).isoformat(), "sequence": prior["sequence"] + 1,
                  "restart_recovery_status": "RESTORED_EXACT_DISABLED_V2_STATE", "migration_status": "V2_DISABLED_RECOVERY",
                  "last_known_valid": {"schema_version": prior["schema_version"], "sequence": prior["sequence"], "content_hash": prior["content_hash"]}})
    value["content_hash"] = _hash(value)
    return validate_state_v2(value, installation)


def migrate_store_atomic(store: Any, *, timestamp: str) -> dict[str, Any]:
    lock = store.acquire()
    try:
        installation, state = store.read(allow_lock=True, recover=False)
        if state.get("schema_version") == STATE_SCHEMA_V2:
            raise ValueError("ALREADY_MIGRATED")
        migrated = migrate_v1_to_v2(state, installation, timestamp=timestamp)
        _atomic(store.root, V1_ROLLBACK_NAME, state)
        _atomic(store.root, "controller-state.json", migrated)
        verified = store.read(allow_lock=True, recover=False)[1]
        _atomic(store.root, LAST_KNOWN_VALID_NAME, verified)
        return verified
    finally:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def browser_projection_v2(state: dict[str, Any], *, running: bool) -> dict[str, Any]:
    return {"schema_version": BROWSER_SCHEMA_V2, "state": "INSTALLED_BUT_DISABLED", "installed": state["installed"],
            "running": running, "activated": False, "controller_schema": state["schema_version"], "phase": state["phase"],
            "integrity": "VALID", "daily_hard_ceiling": 200, "released_now": 0,
            "stage_a": {"draft_count": 50, "maximum": 100, "state": "NOT_RELEASED"},
            "stage_b": {"maximum": 50, "state": "LOCKED"}, "stage_c": {"maximum": 50, "state": "LOCKED"},
            "requests_today": state["requests_used"], "credits_today": state["confirmed_credits"] + state["ambiguous_credits"],
            "authority_locked": True, "migration_status": state["migration_status"],
            "restart_recovery": state["restart_recovery_status"],
            "monday_rehearsal_status": state["rehearsal_receipts"][-1]["classification"],
            "human_gate": "AWAITING_TUESDAY_OWNER_AUTHORIZATION", "next_action": "OWNER_STAGE_A_AUTHORIZATION",
            "last_update": state["updated_at"], "error_category": None}
