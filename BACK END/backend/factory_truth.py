from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import factory_telemetry_v2


SCHEMA_VERSION = "factory-truth-contract-v1"
RECENT_CHECKPOINT_SECONDS = 15 * 60


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


def _checkpoint(
    telemetry: dict[str, Any],
    key: str,
    now: datetime,
) -> dict[str, Any]:
    cadence = telemetry.get("cadence")
    cadence = cadence if isinstance(cadence, dict) else {}
    worker = cadence.get(key)
    worker = worker if isinstance(worker, dict) else {}
    completed = _parse_time(worker.get("last_completed_at"))
    age_seconds = (
        max(0, int((now - completed).total_seconds()))
        if completed is not None
        else None
    )
    return {
        "worker": worker.get("worker"),
        "last_completed_at": (
            completed.isoformat() if completed is not None else None
        ),
        "checkpoint_age_seconds": age_seconds,
        "checkpoint_state": (
            "RECENT_CHECKPOINT"
            if age_seconds is not None and age_seconds <= RECENT_CHECKPOINT_SECONDS
            else "STALE_CHECKPOINT"
            if age_seconds is not None
            else "NO_CHECKPOINT"
        ),
        "cadence_state": worker.get("cadence_state") or "UNKNOWN",
        "next_due_at": worker.get("next_due_at"),
    }


def _identity(
    value: dict[str, Any] | None,
    *,
    default_checkout: Path | None = None,
) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    checkout = str(value.get("checkout") or default_checkout or "").strip()
    ledger_path = str(value.get("ledger_path") or "").strip()
    return {
        "pid": value.get("pid"),
        "checkout": checkout or None,
        "ledger_path": ledger_path or None,
        "observed": value.get("observed") is True,
    }


def build_factory_truth(
    db_path: str | os.PathLike[str] | None = None,
    *,
    runtime_identity: dict[str, Any] | None = None,
    sidecar_identity: dict[str, Any] | None = None,
    backend_probe: Callable[[], dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a presentation-safe truth contract from enforced read-only telemetry."""
    ledger_path = factory_telemetry_v2._resolve_db_path(db_path)
    telemetry = factory_telemetry_v2.build_factory_telemetry(ledger_path)
    now = now or datetime.now(timezone.utc)
    runtime = _identity(runtime_identity, default_checkout=ledger_path.parent.parent.parent)
    sidecar = _identity(sidecar_identity)
    probe = backend_probe() if backend_probe is not None else {"responsive": None}
    probe = probe if isinstance(probe, dict) else {"responsive": None}
    backend_responsive = probe.get("responsive") is True

    mismatches: list[str] = []
    runtime_checkout = runtime.get("checkout")
    sidecar_checkout = sidecar.get("checkout")
    if runtime_checkout and sidecar_checkout and runtime_checkout != sidecar_checkout:
        mismatches.append("CHECKOUT_MISMATCH")
    for identity_name, identity in (("RUNTIME", runtime), ("SIDECAR", sidecar)):
        identity_ledger = identity.get("ledger_path")
        if identity_ledger and Path(str(identity_ledger)).resolve() != ledger_path:
            mismatches.append(f"{identity_name}_LEDGER_MISMATCH")

    telemetry_health = telemetry.get("health")
    telemetry_health = telemetry_health if isinstance(telemetry_health, dict) else {}
    telemetry_available = telemetry_health.get("state") == "HEALTHY"
    checkpoints = {
        "9E": _checkpoint(telemetry, "radar", now),
        "9A": _checkpoint(telemetry, "observation", now),
        "9B": _checkpoint(telemetry, "paper_trading", now),
    }
    runners = {
        key: {
            "state": "RUNNER OBSERVED" if row.get("observed") else "RUNNER UNVERIFIED",
            "pid": row.get("pid"),
        }
        for key, row in (runtime_identity or {}).get("runners", {}).items()
        if isinstance(row, dict)
    }
    for key in checkpoints:
        runners.setdefault(key, {"state": "RUNNER UNVERIFIED", "pid": None})

    truth_states = [
        "TELEMETRY AVAILABLE" if telemetry_available else "TELEMETRY UNAVAILABLE",
        "BACKEND RESPONSIVE" if backend_responsive else "BACKEND DEGRADED",
        "EXTERNAL ARTIFACT" if mismatches else "LOCAL ARTIFACT",
    ]
    safety = telemetry.get("safety")
    safety = safety if isinstance(safety, dict) else {}
    invariants = {
        "broker_connected": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "telemetry_read_only": True,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "truth_states": truth_states,
        "source": {
            "mode": "FACTORY_TELEMETRY_V2_SQLITE_READ_ONLY",
            "ledger_path": str(ledger_path),
            "ledger_fingerprint": telemetry.get("fingerprint"),
            "telemetry_generated_at": telemetry.get("generated_at"),
        },
        "runtime": runtime,
        "sidecar": sidecar,
        "backend": {
            "state": "BACKEND RESPONSIVE" if backend_responsive else "BACKEND DEGRADED",
            "detail": str(probe.get("detail") or "")[:500] or None,
            "get_only": True,
        },
        "artifact": {
            "state": "EXTERNAL ARTIFACT" if mismatches else "LOCAL ARTIFACT",
            "mismatches": mismatches,
            "age_seconds": probe.get("artifact_age_seconds"),
        },
        "checkpoints": checkpoints,
        "runners": runners,
        "paper_account": telemetry.get("paper_fund") or {},
        "live_authority_invariants": {
            **invariants,
            "verified": (
                safety.get("broker_connected") is False
                and safety.get("trade_execution_permission") is False
                and safety.get("live_execution") is False
                and safety.get("telemetry_read_only") is True
            ),
        },
    }