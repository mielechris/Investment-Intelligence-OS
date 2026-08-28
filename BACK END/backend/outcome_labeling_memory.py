from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from factory_telemetry import (
    _connect_read_only,
    _parse_time,
    _resolve_db_path,
    _rows_by_type,
)

SCHEMA_VERSION = "batch9j-outcome-learning-memory-v1"
BROWSER_SCHEMA_VERSION = "batch9j-browser-outcome-summary-v1"
NEW_YORK = ZoneInfo("America/New_York")

HORIZON_ORDER = ("plus_1h", "session_close", "next_session_close", "fifth_session_close")
UPSIDE_THRESHOLD_PCT = 2.0
STRONG_UPSIDE_THRESHOLD_PCT = 5.0
DOWNSIDE_THRESHOLD_PCT = -2.0
STRONG_DOWNSIDE_THRESHOLD_PCT = -5.0


def _ticker(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text[:-3] if text.endswith(".US") else text


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _return_pct(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start <= 0:
        return None
    return round(((end - start) / start) * 100.0, 4)


def _bar_time(row: dict[str, Any]) -> datetime | None:
    return _parse_time(row.get("timestamp") or row.get("at"))


def normalize_price_bars(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        at = _bar_time(row)
        close = _safe_float(row.get("close"))
        if at is None or close is None or close <= 0:
            continue
        output.append({"timestamp": at.isoformat(), "close": close})
    output.sort(key=lambda row: str(row["timestamp"]))
    return output


def parse_yahoo_chart(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = (chart or {}).get("result") if isinstance(chart, dict) else None
    result = results[0] if isinstance(results, list) and results else None
    if not isinstance(result, dict):
        return []
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    quote = quotes[0] if isinstance(quotes, list) and quotes else {}
    closes = quote.get("close") if isinstance(quote, dict) else []
    output: list[dict[str, Any]] = []
    for index, raw_ts in enumerate(timestamps if isinstance(timestamps, list) else []):
        try:
            ts = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
        raw_close = closes[index] if isinstance(closes, list) and index < len(closes) else None
        close = _safe_float(raw_close)
        if close is None or close <= 0:
            continue
        output.append({"timestamp": ts.isoformat(), "close": close})
    return normalize_price_bars(output)


def _nearest_bar(
    bars: list[dict[str, Any]],
    target: datetime,
    *,
    max_distance_minutes: int,
) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    limit = max(1, int(max_distance_minutes)) * 60
    for row in bars:
        at = _bar_time(row)
        if at is None:
            continue
        distance = abs((at - target).total_seconds())
        if distance > limit:
            continue
        if best is None or distance < best[0]:
            best = (distance, row)
    return best[1] if best else None


def _last_regular_bar_for_date(
    bars: list[dict[str, Any]],
    local_date,
) -> dict[str, Any] | None:
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for row in bars:
        at = _bar_time(row)
        if at is None:
            continue
        local = at.astimezone(NEW_YORK)
        if local.date() != local_date:
            continue
        if (local.hour, local.minute) < (9, 30) or (local.hour, local.minute) > (16, 5):
            continue
        rows.append((at, row))
    rows.sort(key=lambda item: item[0])
    return rows[-1][1] if rows else None


def _daily_bars_after(
    bars: list[dict[str, Any]],
    local_date,
) -> list[dict[str, Any]]:
    rows: list[tuple[datetime, dict[str, Any]]] = []
    seen_dates: set[Any] = set()
    for row in bars:
        at = _bar_time(row)
        if at is None:
            continue
        date_value = at.astimezone(NEW_YORK).date()
        if date_value <= local_date or date_value in seen_dates:
            continue
        seen_dates.add(date_value)
        rows.append((at, row))
    rows.sort(key=lambda item: item[0])
    return [row for _, row in rows]


def _horizon_row(
    *,
    name: str,
    anchor_price: float | None,
    row: dict[str, Any] | None,
    pending: bool,
) -> dict[str, Any]:
    close = _safe_float((row or {}).get("close"))
    return {
        "horizon": name,
        "status": "PENDING" if pending and row is None else ("AVAILABLE" if row else "DATA_UNAVAILABLE"),
        "observed_at": (row or {}).get("timestamp"),
        "price": close,
        "return_pct": _return_pct(anchor_price, close),
    }


def build_price_horizons(
    opportunity: dict[str, Any],
    *,
    intraday_bars: list[dict[str, Any]] | None,
    daily_bars: list[dict[str, Any]] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    event_at = _parse_time(opportunity.get("event_at"))
    if event_at is None:
        raise ValueError("Outcome opportunity requires event_at")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    intraday = normalize_price_bars(intraday_bars)
    daily = normalize_price_bars(daily_bars)
    local_event = event_at.astimezone(NEW_YORK)

    anchor = _nearest_bar(intraday, event_at, max_distance_minutes=20)
    anchor_price = _safe_float((anchor or {}).get("close"))
    plus_1h_target = event_at + timedelta(hours=1)
    plus_1h = _nearest_bar(intraday, plus_1h_target, max_distance_minutes=20)
    session_close = _last_regular_bar_for_date(intraday, local_event.date())
    future_daily = _daily_bars_after(daily, local_event.date())
    next_close = future_daily[0] if len(future_daily) >= 1 else None
    fifth_close = future_daily[4] if len(future_daily) >= 5 else None

    local_close = local_event.replace(hour=16, minute=5, second=0, microsecond=0).astimezone(timezone.utc)
    plus_1h_pending = now < plus_1h_target + timedelta(minutes=30)
    session_pending = now < local_close + timedelta(minutes=20)
    next_pending = len(future_daily) < 1
    fifth_pending = len(future_daily) < 5

    horizons = {
        "plus_1h": _horizon_row(
            name="plus_1h",
            anchor_price=anchor_price,
            row=plus_1h,
            pending=plus_1h_pending,
        ),
        "session_close": _horizon_row(
            name="session_close",
            anchor_price=anchor_price,
            row=session_close,
            pending=session_pending,
        ),
        "next_session_close": _horizon_row(
            name="next_session_close",
            anchor_price=anchor_price,
            row=next_close,
            pending=next_pending,
        ),
        "fifth_session_close": _horizon_row(
            name="fifth_session_close",
            anchor_price=anchor_price,
            row=fifth_close,
            pending=fifth_pending,
        ),
    }
    return {
        "event_at": event_at.isoformat(),
        "anchor": {
            "status": "AVAILABLE" if anchor_price is not None else "DATA_UNAVAILABLE",
            "observed_at": (anchor or {}).get("timestamp"),
            "price": anchor_price,
        },
        "horizons": horizons,
        "five_session_mature": horizons["fifth_session_close"]["status"] == "AVAILABLE",
    }


def _longest_available_return(price_path: dict[str, Any]) -> tuple[str | None, float | None]:
    horizons = price_path.get("horizons") if isinstance(price_path, dict) else {}
    horizons = horizons if isinstance(horizons, dict) else {}
    for name in reversed(HORIZON_ORDER):
        row = horizons.get(name)
        if not isinstance(row, dict):
            continue
        value = _safe_float(row.get("return_pct"))
        if value is not None:
            return name, value
    return None, None


def classify_market_outcome(return_pct: float | None) -> str:
    if return_pct is None:
        return "PENDING"
    if return_pct >= STRONG_UPSIDE_THRESHOLD_PCT:
        return "STRONG_UPSIDE"
    if return_pct >= UPSIDE_THRESHOLD_PCT:
        return "UPSIDE"
    if return_pct <= STRONG_DOWNSIDE_THRESHOLD_PCT:
        return "STRONG_DOWNSIDE"
    if return_pct <= DOWNSIDE_THRESHOLD_PCT:
        return "DOWNSIDE"
    return "NEUTRAL"


def classify_decision_quality(
    *,
    detected: bool,
    committee_disposition: str | None,
    paper_fill: dict[str, Any] | None,
    forward_return_pct: float | None,
) -> str:
    outcome = classify_market_outcome(forward_return_pct)
    if outcome == "PENDING":
        return "PENDING"
    if not detected:
        if outcome in {"STRONG_UPSIDE", "UPSIDE"}:
            return "FACTORY_MISS_WITH_UPSIDE"
        if outcome in {"STRONG_DOWNSIDE", "DOWNSIDE"}:
            return "MISSED_MOVE_THAT_REVERSED_OR_FELL"
        return "FACTORY_MISS_NEUTRAL"

    fill = paper_fill if isinstance(paper_fill, dict) else {}
    if fill.get("fill_id"):
        if outcome in {"STRONG_UPSIDE", "UPSIDE"}:
            return "PAPER_ENTRY_FAVORABLE"
        if outcome in {"STRONG_DOWNSIDE", "DOWNSIDE"}:
            return "PAPER_ENTRY_ADVERSE"
        return "PAPER_ENTRY_NEUTRAL"

    disposition = str(committee_disposition or "").upper()
    if disposition == "NO_TRADE":
        if outcome in {"STRONG_UPSIDE", "UPSIDE"}:
            return "NO_TRADE_FOREGONE_UPSIDE"
        if outcome in {"STRONG_DOWNSIDE", "DOWNSIDE"}:
            return "NO_TRADE_AVOIDED_DOWNSIDE"
        return "NO_TRADE_NEUTRAL"
    if disposition == "WATCH":
        if outcome in {"STRONG_UPSIDE", "UPSIDE"}:
            return "WATCH_VALIDATED_BY_UPSIDE"
        if outcome in {"STRONG_DOWNSIDE", "DOWNSIDE"}:
            return "WATCH_FALSE_POSITIVE_OR_REVERSAL"
        return "WATCH_NEUTRAL"
    return f"UNCLASSIFIED_DECISION_{outcome}"


def _agent_alignment(disposition: str, forward_return_pct: float | None) -> str:
    outcome = classify_market_outcome(forward_return_pct)
    if outcome == "PENDING" or outcome == "NEUTRAL":
        return "INCONCLUSIVE"
    disposition = str(disposition or "").upper()
    if disposition == "WATCH":
        return "ALIGNED" if outcome in {"UPSIDE", "STRONG_UPSIDE"} else "MISALIGNED"
    if disposition == "NO_TRADE":
        return "ALIGNED" if outcome in {"DOWNSIDE", "STRONG_DOWNSIDE"} else "MISALIGNED"
    return "INCONCLUSIVE"


def _agent_rows_for_case(connection, case_id: str) -> list[dict[str, Any]]:
    if not case_id:
        return []
    rows = _rows_by_type(connection, "agent_result", limit=10000, ascending=True)
    return [row for row in rows if str(row.get("case_id") or "") == case_id]


def _agent_learning(
    connection,
    case_id: str | None,
    forward_return_pct: float | None,
) -> list[dict[str, Any]]:
    if not case_id:
        return []
    output: list[dict[str, Any]] = []
    for row in _agent_rows_for_case(connection, case_id):
        output.append(
            {
                "agent_key": row.get("agent_key"),
                "agent": row.get("agent"),
                "disposition": row.get("disposition"),
                "confidence": _safe_float(row.get("confidence")),
                "headline": str(row.get("headline") or "")[:500],
                "falsifier": str(row.get("falsifier") or "")[:700],
                "alignment": _agent_alignment(str(row.get("disposition") or ""), forward_return_pct),
            }
        )
    return output


def build_session_outcome_memory(
    benchmark: dict[str, Any],
    scorecard: dict[str, Any],
    price_data_by_ticker: dict[str, dict[str, list[dict[str, Any]]]],
    db_path: str | os.PathLike[str] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if benchmark.get("benchmark_complete") is not True:
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": benchmark.get("session_id"),
            "status": "BENCHMARK_INCOMPLETE",
            "outcomes": [],
            "judgment_bank_candidates": [],
            "safety": {
                "outcome_memory_only": True,
                "ledger_mode": "READ_ONLY",
                "auto_write_judgment_bank": False,
                "live_execution": False,
            },
        }

    score_rows = scorecard.get("opportunities") if isinstance(scorecard, dict) else []
    score_rows = score_rows if isinstance(score_rows, list) else []
    by_id = {
        str(row.get("opportunity_id") or ""): row
        for row in score_rows
        if isinstance(row, dict)
    }
    path: Path = _resolve_db_path(db_path)
    outcomes: list[dict[str, Any]] = []

    with _connect_read_only(path) as connection:
        for opportunity in benchmark.get("opportunities") or []:
            if not isinstance(opportunity, dict):
                continue
            opportunity_id = str(opportunity.get("opportunity_id") or "")
            ticker = _ticker(opportunity.get("ticker"))
            scored = by_id.get(opportunity_id, {})
            price_input = price_data_by_ticker.get(ticker) or {}
            price_path = build_price_horizons(
                opportunity,
                intraday_bars=price_input.get("intraday"),
                daily_bars=price_input.get("daily"),
                now=now,
            )
            horizon_name, forward_return = _longest_available_return(price_path)
            committee = scored.get("committee") if isinstance(scored.get("committee"), dict) else {}
            paper_fill = scored.get("paper_fill") if isinstance(scored.get("paper_fill"), dict) else {}
            detected = scored.get("detected") is True
            case_id = str(scored.get("case_id") or "") or None
            quality = classify_decision_quality(
                detected=detected,
                committee_disposition=committee.get("disposition"),
                paper_fill=paper_fill,
                forward_return_pct=forward_return,
            )
            agents = _agent_learning(connection, case_id, forward_return)
            outcomes.append(
                {
                    "opportunity_id": opportunity_id,
                    "ticker": ticker,
                    "event_at": opportunity.get("event_at"),
                    "benchmark_move_pct": _safe_float(opportunity.get("move_pct")),
                    "importance": opportunity.get("importance"),
                    "detected": detected,
                    "candidate_id": scored.get("candidate_id"),
                    "case_id": case_id,
                    "detected_at": scored.get("detected_at"),
                    "detection_latency_minutes": scored.get("detection_latency_minutes"),
                    "committee": committee,
                    "risk": scored.get("risk") if isinstance(scored.get("risk"), dict) else {},
                    "paper_order": scored.get("paper_order") if isinstance(scored.get("paper_order"), dict) else {},
                    "paper_fill": paper_fill,
                    "price_path": price_path,
                    "longest_available_horizon": horizon_name,
                    "forward_return_pct": forward_return,
                    "market_outcome": classify_market_outcome(forward_return),
                    "decision_quality": quality,
                    "agents": agents,
                    "five_session_mature": price_path.get("five_session_mature") is True,
                    "postmortem_ready": price_path.get("five_session_mature") is True,
                    "judgment_bank_auto_write": False,
                }
            )

    candidates = [
        {
            "opportunity_id": row.get("opportunity_id"),
            "ticker": row.get("ticker"),
            "case_id": row.get("case_id"),
            "decision_quality": row.get("decision_quality"),
            "forward_return_pct": row.get("forward_return_pct"),
            "human_review_required": True,
            "governed_postmortem_required": True,
            "auto_write_judgment_bank": False,
        }
        for row in outcomes
        if row.get("five_session_mature") is True
        and row.get("decision_quality") not in {"PENDING", "NO_TRADE_NEUTRAL", "WATCH_NEUTRAL"}
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "session_id": benchmark.get("session_id"),
        "status": "OUTCOME_MEMORY_UPDATED",
        "benchmark_complete": True,
        "outcome_count": len(outcomes),
        "mature_5d_count": sum(1 for row in outcomes if row.get("five_session_mature") is True),
        "outcomes": outcomes,
        "judgment_bank_candidates": candidates,
        "safety": {
            "outcome_memory_only": True,
            "price_collection_sidecar_only": True,
            "ledger_mode": "READ_ONLY",
            "auto_write_judgment_bank": False,
            "human_review_required": True,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def aggregate_outcome_memory(session_memories: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in session_memories if row.get("status") == "OUTCOME_MEMORY_UPDATED"]
    outcomes = [
        item
        for session in valid
        for item in session.get("outcomes") or []
        if isinstance(item, dict)
    ]
    quality_counts = Counter(str(row.get("decision_quality") or "UNKNOWN") for row in outcomes)
    market_counts = Counter(str(row.get("market_outcome") or "UNKNOWN") for row in outcomes)

    agent_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        for agent in outcome.get("agents") or []:
            if not isinstance(agent, dict):
                continue
            key = str(agent.get("agent_key") or "unknown")
            agent_rows[key].append(agent)

    agent_scorecards: list[dict[str, Any]] = []
    for key, rows in agent_rows.items():
        decisive = [row for row in rows if row.get("alignment") in {"ALIGNED", "MISALIGNED"}]
        aligned = sum(1 for row in decisive if row.get("alignment") == "ALIGNED")
        confidences = [value for value in (_safe_float(row.get("confidence")) for row in rows) if value is not None]
        agent_scorecards.append(
            {
                "agent_key": key,
                "agent": rows[-1].get("agent"),
                "observations": len(rows),
                "decisive_outcomes": len(decisive),
                "aligned_outcomes": aligned,
                "alignment_rate_pct": round((aligned / len(decisive)) * 100.0, 2) if decisive else None,
                "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
                "automatic_weight_change_authority": False,
                "human_review_required": True,
            }
        )
    agent_scorecards.sort(key=lambda row: (row.get("alignment_rate_pct") is not None, row.get("alignment_rate_pct") or 0.0), reverse=True)

    mature = [row for row in outcomes if row.get("five_session_mature") is True]
    review_candidates = [
        candidate
        for session in valid
        for candidate in session.get("judgment_bank_candidates") or []
        if isinstance(candidate, dict)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "OUTCOME_LEARNING_MEMORY_AVAILABLE" if outcomes else "WAITING_FOR_COMPLETE_9H_SESSIONS",
        "complete_session_count": len(valid),
        "outcome_count": len(outcomes),
        "mature_5d_count": len(mature),
        "pending_5d_count": len(outcomes) - len(mature),
        "decision_quality_counts": dict(sorted(quality_counts.items())),
        "market_outcome_counts": dict(sorted(market_counts.items())),
        "agent_scorecards": agent_scorecards,
        "judgment_bank_review_queue": review_candidates,
        "recent_outcomes": sorted(outcomes, key=lambda row: str(row.get("event_at") or ""), reverse=True)[:30],
        "safety": {
            "learning_memory_only": True,
            "auto_write_judgment_bank": False,
            "automatic_agent_weight_changes": False,
            "human_review_required": True,
            "live_execution": False,
        },
    }


def build_browser_summary(memory: dict[str, Any]) -> dict[str, Any]:
    recent = memory.get("recent_outcomes") if isinstance(memory.get("recent_outcomes"), list) else []
    return {
        "schema_version": BROWSER_SCHEMA_VERSION,
        "generated_at": memory.get("generated_at"),
        "status": memory.get("status"),
        "complete_session_count": memory.get("complete_session_count", 0),
        "outcome_count": memory.get("outcome_count", 0),
        "mature_5d_count": memory.get("mature_5d_count", 0),
        "pending_5d_count": memory.get("pending_5d_count", 0),
        "decision_quality_counts": memory.get("decision_quality_counts") or {},
        "market_outcome_counts": memory.get("market_outcome_counts") or {},
        "agent_scorecards": memory.get("agent_scorecards") or [],
        "judgment_bank_review_queue_count": len(memory.get("judgment_bank_review_queue") or []),
        "recent_outcomes": [
            {
                "ticker": row.get("ticker"),
                "event_at": row.get("event_at"),
                "detected": row.get("detected"),
                "committee_disposition": (row.get("committee") or {}).get("disposition") if isinstance(row.get("committee"), dict) else None,
                "forward_return_pct": row.get("forward_return_pct"),
                "longest_available_horizon": row.get("longest_available_horizon"),
                "market_outcome": row.get("market_outcome"),
                "decision_quality": row.get("decision_quality"),
                "five_session_mature": row.get("five_session_mature"),
            }
            for row in recent[:20]
            if isinstance(row, dict)
        ],
        "safety": {
            "read_only_browser_payload": True,
            "auto_write_judgment_bank": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
