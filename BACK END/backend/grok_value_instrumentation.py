from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from ledger import get_object, record_object, utc_now


MEASUREMENT_CASE_ID = "grok_value_measurement"
POLICY_VERSION = "grok-forward-discovery-observation-v4"
_CYCLE_ID: ContextVar[str | None] = ContextVar("grok_value_cycle_id", default=None)
_CYCLE_PHASE: ContextVar[str | None] = ContextVar("grok_value_cycle_phase", default=None)


def _observation_id(source: str, ticker: str) -> str:
    safe_source = re.sub(r"[^A-Z0-9]+", "_", source.upper()).strip("_") or "UNKNOWN"
    safe_ticker = re.sub(r"[^A-Z0-9]+", "_", ticker.upper()).strip("_") or "UNKNOWN"
    return f"grok_value_first_seen_{safe_source}_{safe_ticker}"


@contextmanager
def observation_cycle(cycle_id: str, phase: str):
    cycle_token = _CYCLE_ID.set(str(cycle_id or "").strip() or None)
    phase_token = _CYCLE_PHASE.set(str(phase or "").strip().upper() or None)
    try:
        yield
    finally:
        _CYCLE_PHASE.reset(phase_token)
        _CYCLE_ID.reset(cycle_token)


def record_discovery_observation(
    *,
    source: str,
    ticker: Any,
    source_object_id: Any = None,
    observed_at: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized = str(ticker or "").strip().upper()
    normalized_source = str(source or "").strip().upper()
    if not normalized or not normalized_source:
        return None
    observation_id = _observation_id(normalized_source, normalized)
    existing = get_object(observation_id)
    if existing:
        return existing
    cycle_id = _CYCLE_ID.get()
    cycle_phase = _CYCLE_PHASE.get()
    merged_metadata = dict(metadata or {})
    if cycle_id:
        merged_metadata["measurement_cycle_id"] = cycle_id
    if cycle_phase:
        merged_metadata["measurement_cycle_phase"] = cycle_phase
    payload = {
        "discovery_observation_id": observation_id,
        "policy_version": POLICY_VERSION,
        "source": normalized_source,
        "ticker": normalized,
        "source_object_id": str(source_object_id or "").strip() or None,
        "observed_at": str(observed_at or utc_now()),
        "measurement_cycle_id": cycle_id,
        "measurement_cycle_phase": cycle_phase,
        "metadata": merged_metadata,
        "first_observation_only": True,
        "measurement_only": True,
        "qualification_evidence": False,
        "trade_signal": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(
        observation_id,
        "grok_value_discovery_observation",
        MEASUREMENT_CASE_ID,
        payload,
        topic=normalized,
    )
    return payload


def install_grok_value_instrumentation(opportunity_module, grok_opportunity_module) -> None:
    if getattr(opportunity_module, "_iios_grok_value_instrumented", False):
        return

    original_scan = opportunity_module.scan_universe
    original_discover = grok_opportunity_module.discover_grok_opportunities

    def instrumented_scan(*args, **kwargs):
        result = original_scan(*args, **kwargs)
        for candidate in result.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            record_discovery_observation(
                source="IIOS_NATIVE",
                ticker=candidate.get("ticker"),
                source_object_id=candidate.get("opportunity_candidate_id"),
                observed_at=candidate.get("created_at"),
                metadata={
                    "score": candidate.get("score"),
                    "eligible_for_promotion": candidate.get("eligible_for_promotion"),
                },
            )
        return result

    def instrumented_discover(*args, **kwargs):
        result = original_discover(*args, **kwargs)
        for candidate in result.get("nominations") or []:
            if not isinstance(candidate, dict):
                continue
            record_discovery_observation(
                source="GROK_X",
                ticker=candidate.get("ticker"),
                source_object_id=candidate.get("grok_opportunity_candidate_id"),
                observed_at=candidate.get("created_at"),
                metadata={
                    "source_count": candidate.get("source_count"),
                    "advisory_confidence": candidate.get("advisory_confidence"),
                },
            )
        return result

    opportunity_module.scan_universe = instrumented_scan
    grok_opportunity_module.discover_grok_opportunities = instrumented_discover
    opportunity_module._iios_grok_value_instrumented = True
    grok_opportunity_module._iios_grok_value_instrumented = True
