"""Offline, owner-authorized authentic closed-holiday rehearsal writer."""
from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from .multi_product_research import US_HOLIDAYS, market_session
from .tuesday_controller_state import CONTROLLER_ID, LOCKS, PHASE, ControllerStateStore, _atomic, _hash
from .tuesday_controller_v2 import AUTHENTIC_RECEIPT_SCHEMA, AUTHENTIC_RECEIPT_TYPE, LAST_KNOWN_VALID_NAME, STATE_SCHEMA_V2, _receipt_hash, validate_state_v2

LOCAL_ZONE = ZoneInfo("America/Los_Angeles")
REHEARSAL_DATE = "2026-09-07"
CALENDAR_ID = "IIOS_SOURCE_CONTROLLED_US_MARKET_CALENDAR"
CALENDAR_VERSION = "2026.09"
MAX_OWNER_APPROVAL_AGE_SECONDS = 1800


@dataclass(frozen=True)
class ClockObservation:
    local: datetime
    utc: datetime
    network_time_verification: str


def system_clock() -> ClockObservation:
    utc = datetime.now(timezone.utc)
    local = utc.astimezone(LOCAL_ZONE)
    try:
        result = subprocess.run(
            ["/usr/sbin/systemsetup", "-getusingnetworktime"], shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=3, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}, check=False,
        )
        verified = "VERIFIED" if result.returncode == 0 and result.stdout.strip() == b"Network Time: On" else "UNAVAILABLE"
    except (OSError, subprocess.TimeoutExpired):
        verified = "UNAVAILABLE"
    return ClockObservation(local, utc, verified)


def _calendar(local: datetime) -> tuple[str, str, str]:
    if local.date().isoformat() not in US_HOLIDAYS: raise ValueError("CALENDAR_DATE_MISSING")
    state = market_session("us_large_cap_equities", local.astimezone(timezone.utc).isoformat())["state"]
    if state != "CLOSED_HOLIDAY": raise ValueError("CALENDAR_SESSION_INVALID")
    return CALENDAR_ID, CALENDAR_VERSION, state


def _validate_owner_approval_timestamp(value: str | None, command_utc_time: datetime) -> datetime:
    if value is None or value == "":
        raise ValueError("OWNER_APPROVAL_MISSING")
    try:
        approval = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("OWNER_APPROVAL_TIMESTAMP_INVALID") from exc
    if approval.tzinfo is None or approval.utcoffset() != timezone.utc.utcoffset(approval):
        raise ValueError("OWNER_APPROVAL_TIMESTAMP_INVALID")
    if command_utc_time.tzinfo is None or command_utc_time.utcoffset() != timezone.utc.utcoffset(command_utc_time):
        raise ValueError("SYSTEM_CLOCK_CONTRACT_INVALID")
    age_seconds = (command_utc_time - approval).total_seconds()
    if age_seconds < 0:
        raise ValueError("OWNER_APPROVAL_FUTURE")
    if age_seconds > MAX_OWNER_APPROVAL_AGE_SECONDS:
        raise ValueError("OWNER_APPROVAL_EXPIRED")
    return approval


def _receipt(state: dict, *, approval_identity: str, approval_timestamp: str | None, observation: ClockObservation,
             validated_approval: datetime | None = None) -> dict:
    local, utc = observation.local, observation.utc
    if str(local.tzinfo) != "America/Los_Angeles" or local.date().isoformat() != REHEARSAL_DATE or local.strftime("%A").upper() != "MONDAY": raise ValueError("SYSTEM_CLOCK_CONTRACT_INVALID")
    calendar_id, calendar_version, session = _calendar(local)
    if not isinstance(approval_identity, str) or not 8 <= len(approval_identity) <= 96 or not approval_identity.replace("-", "").replace("_", "").isalnum(): raise ValueError("APPROVAL_IDENTITY_INVALID")
    approval = validated_approval or _validate_owner_approval_timestamp(approval_timestamp, utc)
    seed = f"{REHEARSAL_DATE}|{session}|{approval_identity}|{approval.isoformat()}"
    receipt = {
        "receipt_schema": AUTHENTIC_RECEIPT_SCHEMA, "receipt_type": AUTHENTIC_RECEIPT_TYPE,
        "immutable_receipt_id": "rehearsal-" + hashlib.sha256(seed.encode()).hexdigest(), "classification": "PASSED_CLOSED_HOLIDAY",
        "observed_local_date": REHEARSAL_DATE, "observed_weekday": "MONDAY", "observed_timezone": "America/Los_Angeles",
        "observed_local_timestamp": local.isoformat(), "observed_utc_timestamp": utc.isoformat(), "clock_source": "SYSTEM_WALL_CLOCK",
        "network_time_verification": observation.network_time_verification, "calendar_contract_identity": calendar_id,
        "calendar_contract_version": calendar_version, "session": session, "controller_schema": STATE_SCHEMA_V2,
        "controller_identity": CONTROLLER_ID, "phase_before": PHASE, "phase_after": PHASE,
        "sequence_before": state["sequence"], "sequence_after": state["sequence"] + 1,
        "activated_before": False, "activated_after": False, "released_credits_before": 0, "released_credits_after": 0,
        "requests_before": 0, "requests_after": 0, "confirmed_credits_before": 0, "confirmed_credits_after": 0,
        "ambiguous_credits_before": 0, "ambiguous_credits_after": 0, "candidate_count_before": 0, "candidate_count_after": 0,
        "observation_count_before": 0, "observation_count_after": 0, "paper_positions_before": 0, "paper_positions_after": 0,
        "paper_orders_before": 0, "paper_orders_after": 0, "paper_fills_before": 0, "paper_fills_after": 0,
        "paper_transactions_before": 0, "paper_transactions_after": 0, "authority_before": LOCKS.copy(),
        "authority_after": LOCKS.copy(), "authority_locked_before": True, "authority_locked_after": True,
        "opaque_owner_approval_identity": approval_identity, "approval_utc_timestamp": approval.isoformat(), "immutable": True,
    }
    receipt["canonical_content_hash"] = _receipt_hash(receipt)
    return receipt


def record_authentic_rehearsal(store: ControllerStateStore, *, approval_identity: str, approval_timestamp: str | None,
                                  clock: Callable[[], ClockObservation] = system_clock) -> dict:
    observation = clock()
    approval = _validate_owner_approval_timestamp(approval_timestamp, observation.utc)
    lock = store.acquire()
    try:
        installation, state = store.read(allow_lock=True, recover=False, now=observation.utc)
        validate_state_v2(state, installation, now=observation.utc)
        if state["activated"] or state["released_credit_total"] or state["requests_used"] or any(not row["locked"] for row in state["stages"].values()) or any(state["authority"].values()) or not state["authority_locked"]: raise ValueError("REHEARSAL_PRECONDITION_INVALID")
        candidate = json.loads(json.dumps(state)); receipt = _receipt(state, approval_identity=approval_identity, approval_timestamp=approval_timestamp, observation=observation, validated_approval=approval)
        for prior in state["rehearsal_receipts"]:
            if prior.get("immutable_receipt_id") == receipt["immutable_receipt_id"]: raise ValueError("DUPLICATE_REHEARSAL_RECEIPT")
            if prior.get("observed_local_date") == REHEARSAL_DATE and prior.get("session") == "CLOSED_HOLIDAY": raise ValueError("AMBIGUOUS_REHEARSAL_RECEIPT")
        candidate["rehearsal_receipts"].append(receipt); candidate["sequence"] += 1; candidate["updated_at"] = observation.utc.isoformat()
        candidate["last_known_valid"] = {"schema_version": state["schema_version"], "sequence": state["sequence"], "content_hash": state["content_hash"]}
        candidate["content_hash"] = _hash(candidate); validate_state_v2(candidate, installation, now=observation.utc)
        _atomic(store.root, LAST_KNOWN_VALID_NAME, state); store.write_state(candidate, installation)
        verified = store.read(allow_lock=True, recover=False, now=observation.utc)[1]; _atomic(store.root, LAST_KNOWN_VALID_NAME, verified)
        return verified
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
