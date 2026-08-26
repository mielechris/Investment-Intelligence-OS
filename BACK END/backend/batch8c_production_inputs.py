from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body

import cme_fedwatch_adapter
import jesse_scheduler
import jesse_source_acquisition
import production_index_universe
from ledger import latest_object, record_event, record_object, utc_now
from macro_policy_intelligence import build_monetary_policy_snapshot


router = APIRouter()
PT = ZoneInfo("America/Los_Angeles")
SOURCE_CASE = jesse_source_acquisition.SOURCE_CASE
UNIVERSE_HEALTH_TYPE = "production_index_universe_snapshot"
INPUT_HEALTH_TYPE = "batch8c_production_input_health"
UNIVERSE_REFRESH_TTL_SECONDS = 30 * 60
UNIVERSE_MAX_AGE_HOURS = 36

_lock = threading.Lock()
_last_refresh_attempt_at: datetime | None = None
_installed = False

_original_read_fed_probability_source = jesse_source_acquisition.read_fed_probability_source
_original_source_acquisition_status = jesse_source_acquisition.source_acquisition_status
_original_current_governed_universe = jesse_source_acquisition.current_governed_universe
_original_run_dislocation_scan = jesse_scheduler.run_dislocation_scan
_original_run_cycle = jesse_scheduler.run_cycle


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_hours(value: Any) -> float | None:
    dt = _parse_time(value)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


def latest_universe_health() -> dict[str, Any] | None:
    return latest_object(UNIVERSE_HEALTH_TYPE, case_id=SOURCE_CASE)


def universe_is_fresh(snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(snapshot, dict) or snapshot.get("verified_complete") is not True:
        return False
    age = _age_hours(snapshot.get("created_at") or snapshot.get("as_of"))
    return age is not None and age <= UNIVERSE_MAX_AGE_HOURS


def _persist_universe_capture(capture: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = f"production_index_universe_{uuid4().hex}"
    snapshot = {
        **capture,
        "production_index_universe_snapshot_id": snapshot_id,
        "created_at": utc_now(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    record_object(snapshot_id, UNIVERSE_HEALTH_TYPE, SOURCE_CASE, snapshot)
    record_event(
        SOURCE_CASE,
        "PRODUCTION_INDEX_UNIVERSE_REFRESH_COMPLETE",
        entity_id=snapshot_id,
        payload={
            "status": snapshot.get("status"),
            "symbol_count": snapshot.get("symbol_count"),
            "verified_complete": snapshot.get("verified_complete"),
            "trade_execution_permission": False,
        },
    )

    if snapshot.get("verified_complete") is True and snapshot.get("symbols"):
        jesse_source_acquisition.save_governed_universe(
            {
                "symbols": snapshot["symbols"],
                "source_name": "OFFICIAL_SP500_PLUS_NASDAQ100_BATCH8C",
                "as_of": snapshot["created_at"],
            }
        )
    return snapshot


def refresh_production_universe(*, force: bool = False) -> dict[str, Any]:
    global _last_refresh_attempt_at
    with _lock:
        now = datetime.now(timezone.utc)
        if not force and _last_refresh_attempt_at is not None:
            elapsed = (now - _last_refresh_attempt_at).total_seconds()
            if elapsed < UNIVERSE_REFRESH_TTL_SECONDS:
                current = latest_universe_health()
                if current:
                    return {**current, "refresh_suppressed_by_ttl": True}
        _last_refresh_attempt_at = now

    capture = production_index_universe.refresh_official_index_universe()
    return _persist_universe_capture(capture)


def current_strict_governed_universe() -> dict[str, Any] | None:
    health = latest_universe_health()
    if not universe_is_fresh(health):
        try:
            health = refresh_production_universe(force=False)
        except Exception:
            health = latest_universe_health()

    if not universe_is_fresh(health):
        return None

    base = _original_current_governed_universe() or {}
    symbols = health.get("symbols") or base.get("symbols") or []
    if not symbols:
        return None
    return {
        **base,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "strict_membership": True,
        "verified_complete": True,
        "production_source_lineage": health.get("source_lineage") or [],
        "production_universe_as_of": health.get("created_at") or health.get("as_of"),
        "production_universe_status": health.get("status"),
    }


def read_production_fed_probability_source() -> dict[str, Any]:
    cme = cme_fedwatch_adapter.fetch_cme_fedwatch()

    if cme.get("status") == "CAPTURED":
        snapshot = build_monetary_policy_snapshot(
            {
                "probabilities": cme["probabilities"],
                "market_implied_source": cme.get("source_name"),
                "probability_source_verified": True,
            }
        )
        return {
            "status": "CAPTURED",
            "source_mode": cme.get("source_mode"),
            "source_verified": True,
            "probabilities_invented": False,
            "cme_configuration": cme.get("configuration"),
            "snapshot": snapshot,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    if cme.get("status") == "SOURCE_ERROR":
        return {
            **cme,
            "source_verified": False,
            "probabilities_invented": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    # Preserve the already-governed generic JSON URL/local-file adapter when CME
    # is not configured. This is an explicit fallback source, never an invented
    # probability distribution.
    fallback = _original_read_fed_probability_source()
    if isinstance(fallback, dict):
        fallback = {
            **fallback,
            "cme_configuration": cme_fedwatch_adapter.configuration_status(),
        }
    return fallback


def production_source_status() -> dict[str, Any]:
    base = _original_source_acquisition_status()
    universe_health = latest_universe_health()
    fed_config = cme_fedwatch_adapter.configuration_status()
    fed_status = latest_object("monetary_policy_snapshot", case_id="jesse_macro_policy_factory") or {}
    return {
        **base,
        "production_index_universe": universe_health,
        "strict_universe_verified": universe_is_fresh(universe_health),
        "strict_universe_freshness_hours": (
            round(_age_hours((universe_health or {}).get("created_at")) or 0.0, 3)
            if universe_health else None
        ),
        "cme_fedwatch": {
            **fed_config,
            "latest_snapshot_source": fed_status.get("market_implied_source"),
            "latest_snapshot_source_verified": fed_status.get("probability_source_verified"),
            "latest_snapshot_at": fed_status.get("created_at"),
        },
        "production_inputs_fail_closed": True,
        "secrets_exposed": False,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def strict_scheduled_dislocation(request: dict[str, Any] | None = None):
    request = dict(request or {})
    symbols = [str(x).upper() for x in request.get("universe_symbols") or [] if str(x).strip()]
    if not symbols:
        raise RuntimeError(
            "STRICT_GOVERNED_UNIVERSE_UNAVAILABLE: scheduled 11AM scan refused proxy fallback"
        )
    request["universe_symbols"] = symbols
    result = _original_run_dislocation_scan(request)
    if result.get("strict_index_membership") is not True:
        raise RuntimeError("STRICT_MEMBERSHIP_ASSERTION_FAILED")
    return result


def _universe_refresh_due(now_pt: datetime) -> bool:
    if now_pt.weekday() >= 5:
        return False
    health = latest_universe_health()
    if not universe_is_fresh(health):
        return True
    stamp = _parse_time((health or {}).get("created_at") or (health or {}).get("as_of"))
    if stamp is None:
        return True
    stamp_pt = stamp.astimezone(PT)
    return stamp_pt.date() != now_pt.date() and (now_pt.hour, now_pt.minute) >= (10, 30)


def run_cycle_with_production_inputs(force_jobs: list[str] | None = None):
    force = {str(x).lower() for x in (force_jobs or [])}
    now_pt = datetime.now(timezone.utc).astimezone(PT)
    production: dict[str, Any] = {}

    if "universe" in force or _universe_refresh_due(now_pt):
        try:
            production["universe"] = refresh_production_universe(force="universe" in force)
        except Exception as exc:
            production["universe"] = {
                "status": "SOURCE_ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "verified_complete": False,
                "paper_mode": True,
                "trade_execution_permission": False,
                "live_execution": False,
            }

    result = _original_run_cycle(force_jobs)
    if isinstance(result, dict):
        result["production_inputs"] = production
        result["strict_scheduled_dislocation"] = True
        result["production_inputs_fail_closed"] = True
    return result


def production_input_health() -> dict[str, Any]:
    status = production_source_status()
    universe_ok = status.get("strict_universe_verified") is True
    fed = status.get("cme_fedwatch") or {}
    latest_verified = fed.get("latest_snapshot_source_verified") is True
    health_id = f"batch8c_input_health_{uuid4().hex}"
    payload = {
        "batch8c_production_input_health_id": health_id,
        "strict_universe_ready": universe_ok,
        "fed_probability_ready": latest_verified,
        "cme_configured": fed.get("configured") is True,
        "cme_mode": fed.get("mode"),
        "software_ready": True,
        "production_inputs_ready": universe_ok and latest_verified,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(health_id, INPUT_HEALTH_TYPE, SOURCE_CASE, payload)
    return payload


def install_batch8c() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    # Patch both the source module and the references captured by Jesse scheduler.
    jesse_source_acquisition.current_governed_universe = current_strict_governed_universe
    jesse_source_acquisition.read_fed_probability_source = read_production_fed_probability_source
    jesse_source_acquisition.source_acquisition_status = production_source_status

    jesse_scheduler.current_governed_universe = current_strict_governed_universe
    jesse_scheduler.read_fed_probability_source = read_production_fed_probability_source
    jesse_scheduler.run_dislocation_scan = strict_scheduled_dislocation
    jesse_scheduler.run_cycle = run_cycle_with_production_inputs


@router.get("/intelligence/production-inputs/status")
def get_production_input_status():
    return {
        "source_status": production_source_status(),
        "health": production_input_health(),
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/intelligence/dislocation/universe/refresh")
def refresh_universe_route(request: dict[str, Any] = Body(default={})):
    return refresh_production_universe(force=bool(request.get("force", True)))


@router.post("/intelligence/fedwatch/run")
def run_fedwatch_route():
    return read_production_fed_probability_source()
