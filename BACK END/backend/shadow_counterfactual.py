from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from factory_telemetry import (
    _connect_read_only,
    _parse_time,
    _resolve_db_path,
    _rows_by_type,
)

SCHEMA_VERSION = "batch9i-shadow-counterfactual-v1"
BASELINE_PROMOTION_SCORE = 45.0
BASELINE_RADAR_BREADTH = 8
BASELINE_CASE_CAPACITY = 5
DEFAULT_PROMOTION_SCORES = (40.0, 45.0, 50.0, 55.0, 60.0, 65.0)
DEFAULT_CASE_CAPACITIES = (2, 3, 5)
DEFAULT_RADAR_BREADTHS = (5, 8, 12, 20, 40)
DEFAULT_MIN_COMPLETE_SESSIONS = 5
MAX_LEAD_MINUTES = 390
MAX_LAG_MINUTES = 120
RADAR_CYCLE_TYPE = "high_speed_market_radar_cycle"
HARD_BLOCK_REASON_CODES = {
    "RECENT_GOVERNED_CASE_EXISTS",
}


def _ticker(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text[:-3] if text.endswith(".US") else text


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def _session_bounds(benchmark: dict[str, Any]) -> tuple[datetime, datetime]:
    start = _parse_time(benchmark.get("session_start"))
    end = _parse_time(benchmark.get("session_end"))
    if start is None or end is None or end <= start:
        raise ValueError("Counterfactual benchmark requires valid session bounds")
    return start, end


def _cycle_time(cycle: dict[str, Any]) -> datetime | None:
    return _parse_time(
        cycle.get("last_cycle_completed_at")
        or cycle.get("created_at")
        or cycle.get("_ledger_created_at")
    )


def _session_cycles(
    connection,
    *,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    rows = _rows_by_type(
        connection,
        RADAR_CYCLE_TYPE,
        limit=5000,
        ascending=True,
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        when = _cycle_time(row)
        if when is None:
            continue
        if start <= when <= end + timedelta(minutes=10):
            output.append(row)
    return output


def _benchmark_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    rows = benchmark.get("opportunities")
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = _ticker(row.get("ticker"))
        event_at = _parse_time(row.get("event_at"))
        if not ticker or event_at is None:
            continue
        output.append({**row, "ticker": ticker, "_event_at": event_at})
    return output


def _ranked_rows(cycle: dict[str, Any]) -> list[dict[str, Any]]:
    rows = cycle.get("ranked_candidates")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _promotion_rows(cycle: dict[str, Any]) -> list[dict[str, Any]]:
    rows = cycle.get("promotion_candidates")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _hard_evidence_pass(candidate: dict[str, Any]) -> bool:
    if candidate.get("quote_ok") is not True:
        return False
    if _int(candidate.get("news_count")) < 2:
        return False
    reasons = {
        str(value).strip().upper()
        for value in candidate.get("reason_codes") or []
        if str(value).strip()
    }
    return not bool(reasons & HARD_BLOCK_REASON_CODES)


def _first_matching_time(
    selected: dict[str, list[datetime]],
    *,
    ticker: str,
    event_at: datetime,
) -> datetime | None:
    lower = event_at - timedelta(minutes=MAX_LEAD_MINUTES)
    upper = event_at + timedelta(minutes=MAX_LAG_MINUTES)
    values = sorted(
        when
        for when in selected.get(ticker, [])
        if lower <= when <= upper
    )
    return values[0] if values else None


def _capture_metrics(
    benchmark_rows: list[dict[str, Any]],
    selected: dict[str, list[datetime]],
) -> dict[str, Any]:
    captured: list[str] = []
    captured_high: list[str] = []
    latencies: list[float] = []
    benchmark_tickers = {_ticker(row.get("ticker")) for row in benchmark_rows}

    for row in benchmark_rows:
        ticker = _ticker(row.get("ticker"))
        event_at = row.get("_event_at")
        if not ticker or not isinstance(event_at, datetime):
            continue
        first = _first_matching_time(selected, ticker=ticker, event_at=event_at)
        if first is None:
            continue
        captured.append(ticker)
        if str(row.get("importance") or "").upper() == "HIGH":
            captured_high.append(ticker)
        latencies.append(round((first - event_at).total_seconds() / 60.0, 2))

    selected_tickers = set(selected)
    extras = sorted(selected_tickers - benchmark_tickers)
    return {
        "benchmark_opportunity_count": len(benchmark_rows),
        "captured_count": len(captured),
        "capture_rate_pct": _pct(len(captured), len(benchmark_rows)),
        "captured_high_importance_count": len(captured_high),
        "captured_tickers": sorted(set(captured)),
        "extra_nonbenchmark_ticker_count": len(extras),
        "extra_nonbenchmark_tickers": extras,
        "average_capture_latency_minutes": (
            round(statistics.mean(latencies), 2) if latencies else None
        ),
        "median_capture_latency_minutes": (
            round(statistics.median(latencies), 2) if latencies else None
        ),
    }


def _radar_breadth_analysis(
    cycles: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    breadths: tuple[int, ...],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for breadth in sorted({max(1, int(value)) for value in breadths}):
        selected: dict[str, list[datetime]] = {}
        selection_events = 0
        for cycle in cycles:
            when = _cycle_time(cycle)
            if when is None:
                continue
            for row in _ranked_rows(cycle)[:breadth]:
                ticker = _ticker(row.get("ticker"))
                if not ticker:
                    continue
                selected.setdefault(ticker, []).append(when)
                selection_events += 1
        metrics = _capture_metrics(benchmark_rows, selected)
        output.append(
            {
                "radar_top_n": breadth,
                "selection_events": selection_events,
                "unique_ticker_count": len(selected),
                **metrics,
                "simulation_scope": "PERSISTED_9E_RANKED_CANDIDATES",
                "promotion_inference": False,
            }
        )
    return output


def _promotion_scenario(
    cycles: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    *,
    min_score: float,
    case_capacity: int,
) -> dict[str, Any]:
    selected: dict[str, list[datetime]] = {}
    selection_events = 0
    hard_blocked = 0
    below_score = 0

    for cycle in cycles:
        when = _cycle_time(cycle)
        if when is None:
            continue
        eligible: list[dict[str, Any]] = []
        for candidate in _promotion_rows(cycle)[:BASELINE_RADAR_BREADTH]:
            if not _hard_evidence_pass(candidate):
                hard_blocked += 1
                continue
            if _float(candidate.get("score")) < float(min_score):
                below_score += 1
                continue
            eligible.append(candidate)
        eligible.sort(
            key=lambda row: (
                _float(row.get("radar_rank_score")),
                _float(row.get("score")),
            ),
            reverse=True,
        )
        for candidate in eligible[: max(1, int(case_capacity))]:
            ticker = _ticker(candidate.get("ticker"))
            if not ticker:
                continue
            selected.setdefault(ticker, []).append(when)
            selection_events += 1

    metrics = _capture_metrics(benchmark_rows, selected)
    return {
        "scenario_id": f"score_{float(min_score):.0f}_capacity_{int(case_capacity)}",
        "min_promotion_score": float(min_score),
        "max_cases_per_cycle": int(case_capacity),
        "radar_research_breadth": BASELINE_RADAR_BREADTH,
        "selection_events": selection_events,
        "unique_ticker_count": len(selected),
        "hard_blocked_candidate_events": hard_blocked,
        "below_score_candidate_events": below_score,
        **metrics,
        "hard_evidence_requirements_preserved": True,
        "recent_case_cooldown_preserved": True,
        "simulation_scope": "PERSISTED_9E_PROMOTION_CANDIDATES_TOP_8",
    }


def _scenario_deltas(
    scenarios: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    baseline = next(
        (
            row
            for row in scenarios
            if row.get("min_promotion_score") == BASELINE_PROMOTION_SCORE
            and row.get("max_cases_per_cycle") == BASELINE_CASE_CAPACITY
        ),
        None,
    )
    if baseline is None:
        return None, scenarios

    output: list[dict[str, Any]] = []
    for row in scenarios:
        baseline_events = _int(baseline.get("selection_events"))
        row_events = _int(row.get("selection_events"))
        load_delta_pct = (
            round(((row_events / baseline_events) - 1.0) * 100.0, 2)
            if baseline_events > 0
            else (0.0 if row_events == 0 else 100.0)
        )
        output.append(
            {
                **row,
                "vs_baseline": {
                    "marginal_captured_count": (
                        _int(row.get("captured_count"))
                        - _int(baseline.get("captured_count"))
                    ),
                    "marginal_high_importance_captured_count": (
                        _int(row.get("captured_high_importance_count"))
                        - _int(baseline.get("captured_high_importance_count"))
                    ),
                    "marginal_extra_nonbenchmark_ticker_count": (
                        _int(row.get("extra_nonbenchmark_ticker_count"))
                        - _int(baseline.get("extra_nonbenchmark_ticker_count"))
                    ),
                    "marginal_selection_events": row_events - baseline_events,
                    "selection_load_delta_pct": load_delta_pct,
                },
            }
        )
    return baseline, output


def build_session_counterfactual(
    benchmark: dict[str, Any],
    scorecard: dict[str, Any],
    db_path: str | os.PathLike[str] | None = None,
    *,
    promotion_scores: tuple[float, ...] = DEFAULT_PROMOTION_SCORES,
    case_capacities: tuple[int, ...] = DEFAULT_CASE_CAPACITIES,
    radar_breadths: tuple[int, ...] = DEFAULT_RADAR_BREADTHS,
) -> dict[str, Any]:
    start, end = _session_bounds(benchmark)
    benchmark_complete = benchmark.get("benchmark_complete") is True
    path: Path = _resolve_db_path(db_path)

    benchmark_rows = _benchmark_rows(benchmark)
    if not benchmark_complete:
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": benchmark.get("session_id"),
            "status": "BENCHMARK_INCOMPLETE",
            "benchmark_complete": False,
            "recommendations": [],
            "safety": {
                "shadow_only": True,
                "ledger_mode": "READ_ONLY",
                "auto_apply_threshold_changes": False,
                "live_execution": False,
            },
        }

    with _connect_read_only(path) as connection:
        cycles = _session_cycles(connection, start=start, end=end)

    scenarios = [
        _promotion_scenario(
            cycles,
            benchmark_rows,
            min_score=float(score),
            case_capacity=int(capacity),
        )
        for score in sorted({float(value) for value in promotion_scores})
        for capacity in sorted({max(1, int(value)) for value in case_capacities})
    ]
    baseline, scenarios = _scenario_deltas(scenarios)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": benchmark.get("session_id"),
        "status": "SESSION_COUNTERFACTUAL_COMPLETE",
        "benchmark_complete": True,
        "benchmark_opportunity_count": len(benchmark_rows),
        "persisted_radar_cycle_count": len(cycles),
        "actual_scorecard_metrics": scorecard.get("metrics") or {},
        "baseline": baseline,
        "promotion_scenarios": scenarios,
        "radar_breadth_analysis": _radar_breadth_analysis(
            cycles,
            benchmark_rows,
            radar_breadths,
        ),
        "data_limits": {
            "promotion_threshold_simulation": (
                "Only the persisted top-8 promotion-candidate rows have "
                "deterministic opportunity scores/evidence fields."
            ),
            "radar_breadth_simulation": (
                "Top-40 persisted ranked candidates support breadth/recall "
                "analysis but not inferred promotion eligibility beyond top 8."
            ),
        },
        "safety": {
            "shadow_only": True,
            "ledger_mode": "READ_ONLY",
            "hard_evidence_requirements_preserved": True,
            "auto_apply_threshold_changes": False,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def _aggregate_scenario(
    session_results: list[dict[str, Any]],
    scenario_id: str,
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for session in session_results:
        for row in session.get("promotion_scenarios") or []:
            if row.get("scenario_id") == scenario_id:
                rows.append(row)
                break
    if not rows:
        return None
    return {
        "scenario_id": scenario_id,
        "min_promotion_score": rows[0].get("min_promotion_score"),
        "max_cases_per_cycle": rows[0].get("max_cases_per_cycle"),
        "session_count": len(rows),
        "benchmark_opportunity_count": sum(_int(row.get("benchmark_opportunity_count")) for row in rows),
        "captured_count": sum(_int(row.get("captured_count")) for row in rows),
        "captured_high_importance_count": sum(_int(row.get("captured_high_importance_count")) for row in rows),
        "extra_nonbenchmark_ticker_count": sum(_int(row.get("extra_nonbenchmark_ticker_count")) for row in rows),
        "selection_events": sum(_int(row.get("selection_events")) for row in rows),
    }


def _add_aggregate_rates(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "capture_rate_pct": _pct(row.get("captured_count", 0), row.get("benchmark_opportunity_count", 0)),
        "high_importance_capture_rate_pct": _pct(
            row.get("captured_high_importance_count", 0),
            max(1, row.get("captured_high_importance_count", 0)),
        ) if row.get("captured_high_importance_count", 0) else 0.0,
    }


def aggregate_counterfactual_sessions(
    session_results: list[dict[str, Any]],
    *,
    min_complete_sessions: int = DEFAULT_MIN_COMPLETE_SESSIONS,
) -> dict[str, Any]:
    complete = [
        row
        for row in session_results
        if row.get("status") == "SESSION_COUNTERFACTUAL_COMPLETE"
        and row.get("benchmark_complete") is True
    ]
    complete.sort(key=lambda row: str(row.get("session_id") or ""))
    min_complete_sessions = max(1, int(min_complete_sessions))

    scenario_ids = sorted(
        {
            str(scenario.get("scenario_id"))
            for session in complete
            for scenario in session.get("promotion_scenarios") or []
            if scenario.get("scenario_id")
        }
    )
    aggregated = [
        _aggregate_scenario(complete, scenario_id)
        for scenario_id in scenario_ids
    ]
    aggregated = [
        _add_aggregate_rates(row)
        for row in aggregated
        if isinstance(row, dict)
    ]

    baseline = next(
        (
            row
            for row in aggregated
            if row.get("min_promotion_score") == BASELINE_PROMOTION_SCORE
            and row.get("max_cases_per_cycle") == BASELINE_CASE_CAPACITY
        ),
        None,
    )

    for row in aggregated:
        if baseline is None:
            row["vs_baseline"] = {}
            continue
        row["vs_baseline"] = {
            "marginal_captured_count": _int(row.get("captured_count")) - _int(baseline.get("captured_count")),
            "marginal_high_importance_captured_count": _int(row.get("captured_high_importance_count")) - _int(baseline.get("captured_high_importance_count")),
            "marginal_extra_nonbenchmark_ticker_count": _int(row.get("extra_nonbenchmark_ticker_count")) - _int(baseline.get("extra_nonbenchmark_ticker_count")),
            "marginal_selection_events": _int(row.get("selection_events")) - _int(baseline.get("selection_events")),
        }

    ready = len(complete) >= min_complete_sessions
    frontier: list[dict[str, Any]] = []
    if ready and baseline is not None:
        baseline_events = max(1, _int(baseline.get("selection_events")))
        for row in aggregated:
            delta = row.get("vs_baseline") or {}
            marginal_capture = _int(delta.get("marginal_captured_count"))
            marginal_extra = _int(delta.get("marginal_extra_nonbenchmark_ticker_count"))
            event_load = _int(row.get("selection_events")) / baseline_events
            if marginal_capture <= 0:
                continue
            if event_load > 1.50:
                continue
            if marginal_extra > max(5, marginal_capture * 5):
                continue
            frontier.append(row)
        frontier.sort(
            key=lambda row: (
                _int((row.get("vs_baseline") or {}).get("marginal_captured_count")),
                -_int((row.get("vs_baseline") or {}).get("marginal_extra_nonbenchmark_ticker_count")),
                -_int(row.get("selection_events")),
            ),
            reverse=True,
        )

    recommendations: list[dict[str, Any]] = []
    if ready:
        if frontier:
            for row in frontier[:3]:
                recommendations.append(
                    {
                        "type": "REVIEW_SHADOW_SCENARIO",
                        "scenario_id": row.get("scenario_id"),
                        "reason": (
                            "Counterfactual captured additional benchmark opportunities "
                            "within the governed shadow-load limits."
                        ),
                        "evidence": row.get("vs_baseline"),
                        "action": "HUMAN_REVIEW_ONLY",
                    }
                )
        else:
            recommendations.append(
                {
                    "type": "KEEP_CURRENT_PROMOTION_CONFIGURATION",
                    "reason": (
                        "No tested scenario produced a governed capture improvement "
                        "without unacceptable shadow load/noise."
                    ),
                    "action": "NO_CHANGE",
                }
            )

    return {
        "schema_version": "batch9i-shadow-counterfactual-rollup-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": (
            "ADVISORY_READY"
            if ready
            else "WARMUP_COLLECTING_COMPLETE_SESSIONS"
        ),
        "complete_session_count": len(complete),
        "minimum_complete_sessions_for_advice": min_complete_sessions,
        "session_ids": [row.get("session_id") for row in complete],
        "baseline": baseline,
        "scenario_rollup": aggregated,
        "advisory_frontier": frontier,
        "recommendations": recommendations,
        "safety": {
            "shadow_only": True,
            "advisory_only": True,
            "auto_apply_threshold_changes": False,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
