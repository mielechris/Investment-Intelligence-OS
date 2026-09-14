from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

import opportunity_acquisition
from grok_discovery_lead_time import build_discovery_lead_time_report
from grok_false_positive_tracker import build_false_positive_report
from grok_paper_value import build_paper_value_report
from grok_shadow_paper import enroll_shadow_pairs, refresh_shadow_pairs, shadow_paper_status
from grok_value_instrumentation import MEASUREMENT_CASE_ID, observation_cycle
from grok_value_probe import run_value_probe
from grok_value_scorecard import build_grok_value_scorecard
from ledger import latest_object, record_object, utc_now


router = APIRouter()
POLICY_VERSION = "grok-forward-value-cycle-v1"
DEFAULT_QUERY = (
    "US public equities with genuinely new market-moving catalysts across earnings, policy, "
    "rates, credit, AI, semiconductors, energy, healthcare, supply chains, capital allocation, "
    "geopolitics and unusual institutional or market-structure discussion"
)
MAX_GROK_CANDIDATES = 5
MAX_NATIVE_SYMBOLS = 20


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _native_universe(values: Any, *, limit: int) -> list[dict[str, str]]:
    if isinstance(values, list):
        symbols = opportunity_acquisition.normalize_universe(values)
    else:
        symbols = opportunity_acquisition.current_universe()
    return symbols[: max(1, min(limit, MAX_NATIVE_SYMBOLS))]


def _run_native_source(
    cycle_id: str,
    universe: list[dict[str, str]],
    *,
    news_limit: int,
    timespan: str,
    max_candidates: int,
) -> dict[str, Any]:
    with observation_cycle(cycle_id, "IIOS_NATIVE_SCAN"):
        return opportunity_acquisition.scan_universe(
            universe,
            news_limit=news_limit,
            timespan=timespan,
            max_candidates=max_candidates,
        )


def _run_grok_source(cycle_id: str, query: str, *, days: int, max_candidates: int) -> dict[str, Any]:
    with observation_cycle(cycle_id, "GROK_X_PROBE"):
        return run_value_probe(query, days=days, max_candidates=max_candidates)


def _run_concurrent_sources(
    cycle_id: str,
    *,
    query: str,
    days: int,
    max_candidates: int,
    universe: list[dict[str, str]],
    news_limit: int,
    timespan: str,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None, str | None]:
    native: dict[str, Any] | None = None
    grok: dict[str, Any] | None = None
    native_error: str | None = None
    grok_error: str | None = None
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="iios-value-cycle") as pool:
        native_future = pool.submit(
            _run_native_source,
            cycle_id,
            universe,
            news_limit=news_limit,
            timespan=timespan,
            max_candidates=max_candidates,
        )
        grok_future = pool.submit(
            _run_grok_source,
            cycle_id,
            query,
            days=days,
            max_candidates=max_candidates,
        )
        try:
            native = native_future.result()
        except Exception as exc:
            native_error = f"{type(exc).__name__}: {exc}"[:1000]
        try:
            grok = grok_future.result()
        except Exception as exc:
            grok_error = f"{type(exc).__name__}: {exc}"[:1000]
    return native, native_error, grok, grok_error


def _safe_shadow_step(function) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return function(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"[:1000]


def run_forward_value_cycle(request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = request or {}
    cycle_id = f"grok_value_cycle_{uuid4().hex}"
    query = " ".join(str(request.get("query") or DEFAULT_QUERY).split()).strip()
    if not query:
        raise ValueError("query is required")
    days = _bounded_int(request.get("days"), default=2, minimum=1, maximum=7)
    max_candidates = _bounded_int(
        request.get("max_candidates"),
        default=MAX_GROK_CANDIDATES,
        minimum=1,
        maximum=MAX_GROK_CANDIDATES,
    )
    native_limit = _bounded_int(
        request.get("native_symbol_limit"),
        default=16,
        minimum=1,
        maximum=MAX_NATIVE_SYMBOLS,
    )
    news_limit = _bounded_int(request.get("native_news_limit"), default=8, minimum=2, maximum=12)
    timespan = str(request.get("native_timespan") or "24h").strip() or "24h"
    universe = _native_universe(request.get("native_universe"), limit=native_limit)
    if not universe:
        raise ValueError("native IIOS universe is empty")

    native, native_error, grok, grok_error = _run_concurrent_sources(
        cycle_id,
        query=query,
        days=days,
        max_candidates=max_candidates,
        universe=universe,
        news_limit=news_limit,
        timespan=timespan,
    )

    enrollment, enrollment_error = _safe_shadow_step(enroll_shadow_pairs)
    refresh, refresh_error = _safe_shadow_step(refresh_shadow_pairs)

    lead_time = build_discovery_lead_time_report()
    false_positive = build_false_positive_report()
    paper = build_paper_value_report()
    scorecard = build_grok_value_scorecard()
    shadow_status = shadow_paper_status()

    source_successes = sum(value is not None for value in (native, grok))
    if source_successes == 2:
        status = "COMPLETE"
    elif source_successes == 1:
        status = "PARTIAL"
    else:
        status = "SOURCE_FAILURE"

    payload = {
        "grok_value_cycle_id": cycle_id,
        "policy_version": POLICY_VERSION,
        "status": status,
        "query": query,
        "native": {
            "status": "ok" if native is not None else "error",
            "error": native_error,
            "universe_count": len(universe),
            "scanned_count": (native or {}).get("scanned_count"),
            "queued_count": (native or {}).get("queued_count"),
            "opportunity_scan_id": (native or {}).get("opportunity_scan_id"),
        },
        "grok": {
            "status": "ok" if grok is not None else "error",
            "error": grok_error,
            "nominated_count": ((grok or {}).get("discovery") or {}).get("nominated_count"),
            "quarantined_count": ((grok or {}).get("discovery") or {}).get("quarantined_count"),
            "resolved_this_probe": (grok or {}).get("resolved_this_probe"),
            "xai_discovery_batches": (grok or {}).get("xai_discovery_batches", 0),
        },
        "measurement_integrity": {
            "sources_started_concurrently": True,
            "same_cycle_pairs_count_as_lead_time": False,
            "minimum_cross_cycle_separation_minutes": lead_time.get("minimum_prospective_separation_minutes"),
            "native_scan_independent_of_grok_nominations": True,
            "grok_revalidation_uses_hardened_standard_iios_gate": True,
            "legacy_rows_cannot_satisfy_prospective_sample": True,
        },
        "lead_time": {
            "raw_forward_pair_count": lead_time.get("raw_forward_pair_count"),
            "same_cycle_pair_count": lead_time.get("same_cycle_pair_count"),
            "prospective_pair_count": lead_time.get("prospective_pair_count"),
            "prospective_grok_earlier_count": lead_time.get("prospective_grok_earlier_count"),
            "prospective_iios_earlier_count": lead_time.get("prospective_iios_earlier_count"),
            "prospective_median_grok_lead_minutes": lead_time.get("prospective_median_grok_lead_minutes"),
        },
        "false_positive": {
            "nomination_count": false_positive.get("nomination_count"),
            "resolved_count": false_positive.get("resolved_count"),
            "validated_count": false_positive.get("validated_count"),
            "rejected_count": false_positive.get("rejected_count"),
            "false_positive_rate": false_positive.get("false_positive_rate"),
        },
        "shadow": {
            "enrollment_error": enrollment_error,
            "refresh_error": refresh_error,
            "enrolled_count": (enrollment or {}).get("enrolled_count"),
            "snapshot_count_created": (refresh or {}).get("snapshot_count"),
            "pair_count": shadow_status.get("pair_count"),
            "total_snapshot_count": shadow_status.get("snapshot_count"),
            "differentiated_action_pair_count": shadow_status.get("differentiated_action_pair_count"),
            "actual_paper_orders_created": 0,
        },
        "paper_value": {
            "cases_with_realized_return": paper.get("cases_with_realized_return"),
            "return_comparison_ready": paper.get("return_comparison_ready"),
        },
        "scorecard": {
            "scorecard_version": scorecard.get("scorecard_version"),
            "status": scorecard.get("status"),
            "milestones": scorecard.get("milestones"),
            "promotion_blockers": scorecard.get("promotion_blockers"),
            "permanent_factory_promotion_ready": False,
        },
        "automatic_case_promotion": False,
        "automatic_agent_run": False,
        "automatic_configuration_change": False,
        "qualification_evidence": False,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(cycle_id, "grok_value_cycle", MEASUREMENT_CASE_ID, payload, topic="BATCH_7C_FORWARD_VALUE")
    return payload


@router.get("/grok/value/cycle/plan")
def forward_value_cycle_plan():
    return {
        "policy_version": POLICY_VERSION,
        "purpose": "one-command forward value observation: concurrent independent native-IIOS scan plus one Grok discovery batch, hardened revalidation, shadow enrollment/refresh, and consolidated scorecard",
        "default_query": DEFAULT_QUERY,
        "max_grok_candidates": MAX_GROK_CANDIDATES,
        "max_native_symbols": MAX_NATIVE_SYMBOLS,
        "same_cycle_pairs_count_as_lead_time": False,
        "automatic_case_promotion": False,
        "automatic_agent_run": False,
        "actual_paper_orders_created": 0,
        "research_only": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/grok/value/cycle/latest")
def latest_forward_value_cycle():
    latest = latest_object("grok_value_cycle", case_id=MEASUREMENT_CASE_ID)
    return latest or {
        "status": "NO_FORWARD_VALUE_CYCLE_YET",
        "research_only": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/grok/value/cycle")
def forward_value_cycle(request: dict[str, Any] = Body(default={})):
    try:
        return run_forward_value_cycle(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}"[:1000])
