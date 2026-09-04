from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "iios-sanitized-scanner-batch-v1"
SCANNER_ID = "EXISTING_IIOS_519_SYMBOL_SCANNER"
AUTHORITY = {
    "automatic_promotion": False,
    "paper_order": False,
    "ledger_write": False,
    "broker": False,
    "live_execution": False,
}
ALLOWED_MISSING_FIELDS = ("company_profile", "identifiers")
SUCCESS_STATUSES = {None, "COMPLETE", "SUCCESS"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("RADAR_LINEAGE_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise ValueError("RADAR_LINEAGE_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "state": "UNAVAILABLE", "reason": reason, "source_cycle_id": None,
        "source_artifact_hash": None, "candidate_batch": None,
        "promotion_candidate_count": None, "authority": AUTHORITY.copy(),
    }


def _candidate_id(cycle_id: str, source_id: str, ticker: str, discovered_at: str) -> str:
    digest = hashlib.sha256(_canonical([cycle_id, source_id, ticker, discovered_at])).hexdigest()[:16]
    return f"candidate_{digest}"


def project_candidate_lineage(
    state: dict[str, Any] | None,
    cycle: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 900,
    historical: bool = False,
) -> dict[str, Any]:
    if not isinstance(state, dict) or not isinstance(cycle, dict):
        return _unavailable("EXACT_CYCLE_NOT_AVAILABLE")
    cycle_id = state.get("last_cycle_id")
    cycle_object_id = cycle.get("high_speed_market_radar_cycle_id")
    completed = state.get("last_cycle_completed_at")
    cycle_completed = cycle.get("last_cycle_completed_at")
    if not isinstance(cycle_id, str) or "failed" in cycle_id.lower() or state.get("last_cycle_status") not in SUCCESS_STATUSES:
        return _unavailable("FAILED_CYCLE_HAS_NO_LINEAGE")
    if cycle_id != cycle_object_id or completed != cycle_completed:
        return _unavailable("STATE_CYCLE_MISMATCH")
    try:
        completed_at = _time(completed)
    except ValueError:
        return _unavailable("CYCLE_TIMESTAMP_INVALID")
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not historical and (clock - completed_at).total_seconds() > stale_after_seconds:
        return _unavailable("CYCLE_STALE")
    rows = cycle.get("promotion_candidates")
    if not isinstance(rows, list):
        return _unavailable("CANDIDATE_LIST_INVALID")
    projected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            return _unavailable("CANDIDATE_CONTRACT_INVALID")
        ticker = row.get("ticker")
        discovered = row.get("created_at") or row.get("discovered_at")
        source_id = row.get("opportunity_candidate_id")
        producer = row.get("created_by")
        scan_id = row.get("source_scan_id") or row.get("scan_id")
        if (not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", str(ticker)) or
                not isinstance(source_id, str) or not source_id or
                producer != "BATCH_9E_HIGH_SPEED_MARKET_RADAR" or
                not isinstance(scan_id, str) or not scan_id):
            return _unavailable("CANDIDATE_CONTRACT_INVALID")
        try:
            discovered_time = _time(discovered)
        except ValueError:
            return _unavailable("CANDIDATE_CONTRACT_INVALID")
        if discovered_time > completed_at:
            return _unavailable("CANDIDATE_CONTRACT_INVALID")
        key = (source_id, str(ticker))
        if key in seen:
            continue
        seen.add(key)
        if len(projected) < 5:
            projected.append({
                "candidate_id": _candidate_id(cycle_id, source_id, str(ticker), str(discovered)),
                "ticker": ticker, "discovered_at": discovered,
                "missing_fields": list(ALLOWED_MISSING_FIELDS),
            })
    source_value = {key: value for key, value in cycle.items() if key != "_ledger_created_at"}
    source_hash = hashlib.sha256(_canonical(source_value)).hexdigest()
    batch_seed = [cycle_id, source_hash, projected]
    batch = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": f"batch_{hashlib.sha256(_canonical(batch_seed)).hexdigest()[:16]}",
        "generated_at": completed,
        "originating_scanner": SCANNER_ID,
        "candidates": projected,
    }
    return {
        "state": "HISTORICAL_REPLAY_ONLY" if historical else ("CURRENT" if projected else "AVAILABLE_EMPTY"),
        "reason": "HISTORICAL_REPLAY_ONLY" if historical else None,
        "source_cycle_id": cycle_id, "source_artifact_hash": source_hash,
        "candidate_batch": batch, "promotion_candidate_count": len(seen),
        "authority": AUTHORITY.copy(),
    }


def replay_historical_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    state = {
        "last_cycle_id": cycle.get("high_speed_market_radar_cycle_id"),
        "last_cycle_completed_at": cycle.get("last_cycle_completed_at"),
        "last_cycle_status": "COMPLETE",
    }
    return project_candidate_lineage(state, cycle, historical=True)
