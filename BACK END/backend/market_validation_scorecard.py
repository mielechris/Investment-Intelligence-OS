from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from factory_telemetry import (
    _case_lineage,
    _connect_read_only,
    _parse_time,
    _resolve_db_path,
    _rows_by_type,
)
from factory_telemetry_v2 import build_factory_telemetry

SCHEMA_VERSION = "batch9g-market-validation-scorecard-v1"
DEFAULT_MAX_LEAD_MINUTES = 390
DEFAULT_MAX_LAG_MINUTES = 120

_ALLOWED_OPPORTUNITY_KEYS = {
    "opportunity_id",
    "ticker",
    "event_at",
    "label",
    "move_pct",
    "importance",
    "source",
}


def _safe_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if ticker.endswith(".US"):
        ticker = ticker[:-3]
    return ticker


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def _candidate_time(candidate: dict[str, Any]) -> datetime | None:
    return _parse_time(
        candidate.get("detected_at")
        or candidate.get("created_at")
        or candidate.get("_ledger_created_at")
    )


def _sanitize_opportunity_set(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Opportunity set must be a JSON object")

    session_start = _parse_time(payload.get("session_start"))
    session_end = _parse_time(payload.get("session_end"))
    if session_start is None or session_end is None:
        raise ValueError(
            "Opportunity set requires ISO session_start and session_end"
        )
    if session_end <= session_start:
        raise ValueError("session_end must be after session_start")

    raw_opportunities = payload.get("opportunities")
    if not isinstance(raw_opportunities, list):
        raise ValueError("opportunities must be a list")

    opportunities: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_opportunities):
        if not isinstance(raw, dict):
            raise ValueError(
                f"Opportunity at index {index} must be an object"
            )
        ticker = _safe_ticker(raw.get("ticker"))
        event_at = _parse_time(raw.get("event_at"))
        if not ticker:
            raise ValueError(
                f"Opportunity at index {index} requires ticker"
            )
        if event_at is None:
            raise ValueError(
                f"Opportunity at index {index} requires ISO event_at"
            )

        clean = {
            key: raw.get(key)
            for key in _ALLOWED_OPPORTUNITY_KEYS
            if key in raw
        }
        clean["opportunity_id"] = str(
            raw.get("opportunity_id")
            or f"market_opportunity_{index + 1}"
        )[:160]
        clean["ticker"] = ticker
        clean["event_at"] = event_at.isoformat()
        if "label" in clean:
            clean["label"] = str(clean["label"] or "")[:240]
        if "source" in clean:
            clean["source"] = str(clean["source"] or "")[:160]
        if "importance" in clean:
            clean["importance"] = str(
                clean["importance"] or ""
            )[:40]
        if "move_pct" in clean:
            clean["move_pct"] = _safe_float(clean["move_pct"])
        opportunities.append(clean)

    return {
        "session_id": str(
            payload.get("session_id")
            or session_start.date().isoformat()
        )[:160],
        "session_start": session_start.isoformat(),
        "session_end": session_end.isoformat(),
        "benchmark_complete": bool(
            payload.get("benchmark_complete", False)
        ),
        "opportunities": opportunities,
    }


def _session_candidates(
    candidates: list[dict[str, Any]],
    *,
    session_start: datetime,
    session_end: datetime,
) -> list[dict[str, Any]]:
    output = []
    for candidate in candidates:
        when = _candidate_time(candidate)
        if when is None:
            continue
        if session_start <= when <= session_end:
            output.append(candidate)
    return output


def _best_candidate(
    candidates: list[dict[str, Any]],
    *,
    ticker: str,
    event_at: datetime,
    max_lead_minutes: int,
    max_lag_minutes: int,
) -> dict[str, Any] | None:
    lower = event_at - timedelta(minutes=max_lead_minutes)
    upper = event_at + timedelta(minutes=max_lag_minutes)
    matches: list[tuple[datetime, dict[str, Any]]] = []
    for candidate in candidates:
        if _safe_ticker(candidate.get("ticker")) != ticker:
            continue
        when = _candidate_time(candidate)
        if when is None or when < lower or when > upper:
            continue
        matches.append((when, candidate))

    if not matches:
        return None

    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def _paper_fill_by_execution(
    connection,
) -> dict[str, dict[str, Any]]:
    fills = _rows_by_type(
        connection,
        "paper_portfolio_transaction",
        limit=5000,
    )
    output: dict[str, dict[str, Any]] = {}
    for fill in fills:
        execution_id = str(
            fill.get("source_execution_id") or ""
        ).strip()
        if not execution_id or execution_id in output:
            continue
        output[execution_id] = {
            "fill_id": fill.get(
                "paper_portfolio_transaction_id"
            ),
            "source_execution_id": execution_id,
            "ticker": fill.get("ticker"),
            "side": fill.get("side"),
            "quantity": fill.get("quantity"),
            "price": fill.get("price"),
            "notional": fill.get("notional"),
            "created_at": fill.get("created_at")
            or fill.get("_ledger_created_at"),
            "fill_semantics": (
                "PERSISTED_GOVERNED_PAPER_TRANSACTION"
            ),
            "live_execution": False,
        }
    return output


def build_market_validation_scorecard(
    opportunity_set: dict[str, Any],
    db_path: str | os.PathLike[str] | None = None,
    *,
    max_lead_minutes: int = DEFAULT_MAX_LEAD_MINUTES,
    max_lag_minutes: int = DEFAULT_MAX_LAG_MINUTES,
) -> dict[str, Any]:
    clean_input = _sanitize_opportunity_set(opportunity_set)
    max_lead_minutes = max(0, int(max_lead_minutes))
    max_lag_minutes = max(0, int(max_lag_minutes))
    path: Path = _resolve_db_path(db_path)

    session_start = _parse_time(clean_input["session_start"])
    session_end = _parse_time(clean_input["session_end"])
    assert session_start is not None
    assert session_end is not None

    with _connect_read_only(path) as connection:
        all_candidates = _rows_by_type(
            connection,
            "opportunity_candidate",
            limit=5000,
            ascending=True,
        )
        session_candidates = _session_candidates(
            all_candidates,
            session_start=session_start,
            session_end=session_end,
        )
        fill_by_execution = _paper_fill_by_execution(connection)

        results: list[dict[str, Any]] = []
        latencies: list[float] = []

        for opportunity in clean_input["opportunities"]:
            ticker = opportunity["ticker"]
            event_at = _parse_time(opportunity["event_at"])
            assert event_at is not None

            candidate = _best_candidate(
                session_candidates,
                ticker=ticker,
                event_at=event_at,
                max_lead_minutes=max_lead_minutes,
                max_lag_minutes=max_lag_minutes,
            )

            if candidate is None:
                results.append(
                    {
                        **opportunity,
                        "detected": False,
                        "missed": True,
                        "candidate_id": None,
                        "detected_at": None,
                        "detection_latency_minutes": None,
                        "promoted": False,
                        "case_id": None,
                        "committee": {},
                        "risk": {},
                        "paper_order": {},
                        "paper_fill": {},
                    }
                )
                continue

            detected_at = _candidate_time(candidate)
            assert detected_at is not None
            latency = round(
                (detected_at - event_at).total_seconds() / 60.0,
                2,
            )
            latencies.append(latency)

            lineage = _case_lineage(connection, candidate)
            case_id = str(lineage.get("case_id") or "").strip()
            execution = lineage.get("paper_execution")
            execution = (
                execution if isinstance(execution, dict) else {}
            )
            execution_id = str(
                execution.get("execution_id") or ""
            ).strip()
            fill = fill_by_execution.get(execution_id, {})

            results.append(
                {
                    **opportunity,
                    "detected": True,
                    "missed": False,
                    "candidate_id": candidate.get(
                        "opportunity_candidate_id"
                    ),
                    "detected_at": detected_at.isoformat(),
                    "detection_latency_minutes": latency,
                    "candidate_score": candidate.get("score"),
                    "radar_rank_score": candidate.get(
                        "radar_rank_score"
                    ),
                    "promoted": bool(case_id),
                    "case_id": case_id or None,
                    "promoted_at": candidate.get("promoted_at"),
                    "agents": lineage.get("agents") or {},
                    "committee": lineage.get("committee") or {},
                    "qualification": (
                        lineage.get("qualification") or {}
                    ),
                    "risk": lineage.get("risk") or {},
                    "paper_order": execution,
                    "paper_fill": fill,
                }
            )

    telemetry = build_factory_telemetry(path)

    opportunity_count = len(results)
    detected_count = sum(1 for row in results if row["detected"])
    missed_count = opportunity_count - detected_count
    promoted_count = sum(1 for row in results if row["promoted"])
    committee_count = sum(
        1
        for row in results
        if (row.get("committee") or {}).get("disposition")
        is not None
    )
    risk_count = sum(
        1
        for row in results
        if (row.get("risk") or {}).get("decision") is not None
    )
    order_count = sum(
        1
        for row in results
        if (row.get("paper_order") or {}).get("execution")
        == "PAPER_ORDER_CREATED"
    )
    fill_count = sum(
        1
        for row in results
        if bool((row.get("paper_fill") or {}).get("fill_id"))
    )

    benchmark_tickers = {
        row["ticker"] for row in clean_input["opportunities"]
    }
    factory_candidate_tickers = {
        _safe_ticker(row.get("ticker"))
        for row in session_candidates
        if _safe_ticker(row.get("ticker"))
    }
    unmatched_tickers = sorted(
        factory_candidate_tickers - benchmark_tickers
    )
    benchmark_complete = clean_input["benchmark_complete"]

    cadence = telemetry.get("cadence")
    cadence = cadence if isinstance(cadence, dict) else {}
    cadence_states = [
        str((value or {}).get("cadence_state") or "UNKNOWN")
        for value in cadence.values()
        if isinstance(value, dict)
    ]
    on_cadence_count = sum(
        1 for state in cadence_states if state == "ON_CADENCE"
    )

    providers = telemetry.get("providers")
    providers = providers if isinstance(providers, dict) else {}
    paper_fund = telemetry.get("paper_fund")
    paper_fund = (
        paper_fund if isinstance(paper_fund, dict) else {}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "mode": "LOCAL_LEDGER_READ_ONLY",
            "market_opportunity_set": "SUPPLIED_FOR_EVALUATION",
            "ledger_path_exported": False,
            "live_execution": False,
        },
        "evaluation_window": {
            "max_lead_minutes": max_lead_minutes,
            "max_lag_minutes": max_lag_minutes,
        },
        "input": clean_input,
        "metrics": {
            "opportunity_count": opportunity_count,
            "detected_count": detected_count,
            "missed_count": missed_count,
            "detection_rate_pct": _pct(
                detected_count,
                opportunity_count,
            ),
            "opportunity_miss_rate_pct": _pct(
                missed_count,
                opportunity_count,
            ),
            "promoted_count": promoted_count,
            "promotion_rate_of_detected_pct": _pct(
                promoted_count,
                detected_count,
            ),
            "committee_decision_count": committee_count,
            "committee_throughput_of_promoted_pct": _pct(
                committee_count,
                promoted_count,
            ),
            "risk_decision_count": risk_count,
            "risk_throughput_of_promoted_pct": _pct(
                risk_count,
                promoted_count,
            ),
            "paper_order_count": order_count,
            "paper_fill_count": fill_count,
            "paper_fill_rate_of_orders_pct": _pct(
                fill_count,
                order_count,
            ),
            "average_detection_latency_minutes": (
                round(statistics.mean(latencies), 2)
                if latencies
                else None
            ),
            "median_detection_latency_minutes": (
                round(statistics.median(latencies), 2)
                if latencies
                else None
            ),
            "factory_candidate_ticker_count": len(
                factory_candidate_tickers
            ),
            "unmatched_factory_candidate_ticker_count": len(
                unmatched_tickers
            ),
            "false_positive_rate_pct": (
                _pct(
                    len(unmatched_tickers),
                    len(factory_candidate_tickers),
                )
                if benchmark_complete
                else None
            ),
            "cadence_on_count": on_cadence_count,
            "cadence_worker_count": len(cadence_states),
            "cadence_reliability_pct": _pct(
                on_cadence_count,
                len(cadence_states),
            ),
            "provider_error_count": int(
                providers.get("provider_error_count") or 0
            ),
            "nav": paper_fund.get("nav"),
            "total_pnl": paper_fund.get("total_pnl"),
            "current_drawdown_pct": paper_fund.get(
                "current_drawdown_pct"
            ),
            "max_drawdown_pct": paper_fund.get(
                "max_drawdown_pct"
            ),
        },
        "unmatched_factory_candidate_tickers": unmatched_tickers,
        "opportunities": results,
        "factory_snapshot": {
            "fingerprint": telemetry.get("fingerprint"),
            "health": telemetry.get("health"),
            "cadence": cadence,
            "providers": providers,
            "paper_fund": paper_fund,
            "recent_paper_fills": telemetry.get(
                "recent_paper_fills"
            ),
        },
        "safety": {
            "paper_mode": True,
            "telemetry_read_only": True,
            "scorecard_read_only": True,
            "broker_connected": False,
            "live_capital_locked": True,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
