#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, time as clock_time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "batch9o-daily-factory-episode-v1"
NEW_YORK = ZoneInfo("America/New_York")
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"
FINAL_WINDOW = clock_time(16, 45)

BEST_QUALITY = {
    "PAPER_ENTRY_FAVORABLE",
    "WATCH_VALIDATED_BY_UPSIDE",
}
SAVE_QUALITY = {
    "NO_TRADE_AVOIDED_DOWNSIDE",
}
DUMB_QUALITY = {
    "PAPER_ENTRY_ADVERSE",
    "WATCH_FALSE_POSITIVE_OR_REVERSAL",
    "NO_TRADE_FOREGONE_UPSIDE",
}
MISS_QUALITY = {
    "FACTORY_MISS_WITH_UPSIDE",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _session_id(scorecard: dict[str, Any], learning: dict[str, Any]) -> str | None:
    for value in (
        scorecard.get("session_id"),
        (scorecard.get("input") or {}).get("session_id") if isinstance(scorecard.get("input"), dict) else None,
        learning.get("latest_session_id"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return None


def _session_outcomes(learning: dict[str, Any], session_id: str | None) -> list[dict[str, Any]]:
    rows = learning.get("recent_outcomes")
    rows = rows if isinstance(rows, list) else []
    clean = [row for row in rows if isinstance(row, dict)]
    if not session_id:
        return clean
    matched = [row for row in clean if str(row.get("session_id") or "") == session_id]
    return matched if matched else []


def _outcome_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": _ticker(row.get("ticker")),
        "case_id": row.get("case_id"),
        "session_id": row.get("session_id"),
        "decision_quality": row.get("decision_quality"),
        "market_outcome": row.get("market_outcome"),
        "final_disposition": row.get("final_disposition"),
        "longest_available_horizon": row.get("longest_available_horizon"),
        "forward_return_pct": _safe_float(row.get("forward_return_pct")),
        "benchmark_return_pct": _safe_float(row.get("benchmark_return_pct")),
        "relative_return_pct": _safe_float(row.get("relative_return_pct")),
        "benchmark_source": row.get("benchmark_source"),
        "measured_at": row.get("measured_at"),
        "label_provenance": row.get("label_provenance"),
    }


def _return_sort(row: dict[str, Any]) -> float:
    relative = _safe_float(row.get("relative_return_pct"))
    forward = _safe_float(row.get("forward_return_pct"))
    return relative if relative is not None else (forward if forward is not None else 0.0)


def _build_decision_sections(outcomes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    cards = [_outcome_card(row) for row in outcomes]
    best = [row for row in cards if str(row.get("decision_quality") or "") in BEST_QUALITY]
    saves = [row for row in cards if str(row.get("decision_quality") or "") in SAVE_QUALITY]
    dumb = [row for row in cards if str(row.get("decision_quality") or "") in DUMB_QUALITY]
    learned_misses = [row for row in cards if str(row.get("decision_quality") or "") in MISS_QUALITY]
    best.sort(key=_return_sort, reverse=True)
    saves.sort(key=_return_sort)
    dumb.sort(key=lambda row: abs(_return_sort(row)), reverse=True)
    learned_misses.sort(key=_return_sort, reverse=True)
    return {
        "best_calls": best[:8],
        "saves": saves[:8],
        "dumb_calls": dumb[:8],
        "learning_misses": learned_misses[:8],
    }


def _validation_misses(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    rows = scorecard.get("opportunities")
    rows = rows if isinstance(rows, list) else []
    misses: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        detected = row.get("eventually_detected")
        if detected is None:
            detected = row.get("detected")
        if detected is True:
            continue
        misses.append(
            {
                "opportunity_id": row.get("opportunity_id"),
                "ticker": _ticker(row.get("ticker")),
                "move_pct": _safe_float(row.get("move_pct")),
                "importance": row.get("importance"),
                "source": row.get("source"),
                "event_at": row.get("event_at"),
                "detected_by_radar": row.get("detected_by_radar", row.get("detected")),
                "eventually_detected": row.get("eventually_detected", row.get("detected")),
                "promoted_to_case": row.get("promoted_to_case", row.get("promoted")),
                "case_id": row.get("case_id"),
                "miss_reason": row.get("miss_reason") or "NOT_DETECTED_IN_VALIDATION_WINDOW",
            }
        )
    misses.sort(key=lambda row: abs(_safe_float(row.get("move_pct")) or 0.0), reverse=True)
    return misses[:12]


def _paper_performance(telemetry: dict[str, Any]) -> dict[str, Any]:
    fund = telemetry.get("paper_fund")
    fund = fund if isinstance(fund, dict) else {}
    return {
        "snapshot_id": fund.get("snapshot_id"),
        "snapshot_as_of": fund.get("snapshot_as_of"),
        "starting_cash": _safe_float(fund.get("starting_cash")),
        "nav": _safe_float(fund.get("nav")),
        "cash": _safe_float(fund.get("cash")),
        "market_value": _safe_float(fund.get("market_value")),
        "realized_pnl": _safe_float(fund.get("realized_pnl")),
        "unrealized_pnl": _safe_float(fund.get("unrealized_pnl")),
        "total_pnl": _safe_float(fund.get("total_pnl")),
        "gross_exposure": _safe_float(fund.get("gross_exposure")),
        "position_count": _safe_int(fund.get("position_count")),
        "transaction_count": _safe_int(fund.get("transaction_count")),
        "cumulative_return_pct": _safe_float(fund.get("cumulative_return_pct")),
        "current_drawdown_pct": _safe_float(fund.get("current_drawdown_pct")),
        "max_drawdown_pct": _safe_float(fund.get("max_drawdown_pct")),
        "data_source": fund.get("data_source"),
    }


def _validation_metrics(scorecard: dict[str, Any]) -> dict[str, Any]:
    metrics = scorecard.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    return {
        "benchmark_opportunity_count": _safe_int(
            metrics.get("benchmark_opportunity_count", metrics.get("opportunity_count"))
        ),
        "detected_count": _safe_int(
            metrics.get("eventual_detected_count", metrics.get("radar_detected_count", metrics.get("detected_count")))
        ),
        "promoted_count": _safe_int(
            metrics.get("eventual_promotion_count", metrics.get("promotion_count", metrics.get("promoted_count")))
        ),
        "detection_rate_pct": _safe_float(
            metrics.get("eventual_detection_rate_pct", metrics.get("detection_rate_pct"))
        ),
        "opportunity_miss_rate_pct": _safe_float(
            metrics.get("eventual_opportunity_miss_rate_pct", metrics.get("opportunity_miss_rate_pct"))
        ),
        "false_positive_rate_pct": _safe_float(metrics.get("false_positive_rate_pct")),
        "average_detection_latency_minutes": _safe_float(metrics.get("average_detection_latency_minutes")),
        "provider_error_count": _safe_int(metrics.get("provider_error_count")),
    }


def _tomorrow_focus(
    *,
    validation: dict[str, Any],
    shadow: dict[str, Any],
    learning: dict[str, Any],
    telemetry: dict[str, Any],
    misses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    miss_rate = _safe_float(validation.get("opportunity_miss_rate_pct"))
    if misses:
        output.append(
            {
                "priority": "RADAR_MISS_REVIEW",
                "why": f"{len(misses)} persisted validation miss(es) are visible; miss rate {miss_rate if miss_rate is not None else 'unreported'}%.",
                "action": "REVIEW_MISSES_BEFORE_ANY_THRESHOLD_CHANGE",
                "authority": "HUMAN_REVIEW_ONLY",
            }
        )

    recommendations = shadow.get("recommendations")
    recommendations = recommendations if isinstance(recommendations, list) else []
    for recommendation in recommendations[:3]:
        if not isinstance(recommendation, dict):
            continue
        output.append(
            {
                "priority": recommendation.get("type") or "SHADOW_REVIEW",
                "why": recommendation.get("reason") or "9I produced a persisted advisory recommendation.",
                "action": recommendation.get("action") or "HUMAN_REVIEW_ONLY",
                "scenario_id": recommendation.get("scenario_id"),
                "authority": "ADVISORY_ONLY",
            }
        )

    providers = telemetry.get("providers")
    providers = providers if isinstance(providers, dict) else {}
    provider_errors = _safe_int(providers.get("provider_error_count"))
    if provider_errors:
        output.append(
            {
                "priority": "PROVIDER_RELIABILITY",
                "why": f"9G reports {provider_errors} provider error(s).",
                "action": "REVIEW_PROVIDER_ERRORS",
                "authority": "OPERATIONS_REVIEW_ONLY",
            }
        )

    learning_status = str(learning.get("status") or "WARM-UP")
    if "WARM" in learning_status.upper() or not learning.get("recent_outcomes"):
        output.append(
            {
                "priority": "OUTCOME_MATURITY",
                "why": "9J has not produced enough mature outcome evidence for a complete daily learning read.",
                "action": "COLLECT_MORE_PERSISTED_OUTCOMES",
                "authority": "NO_CHANGE",
            }
        )

    if not output:
        output.append(
            {
                "priority": "HOLD_GOVERNED_BASELINE",
                "why": "No persisted miss, provider, shadow or learning condition requires a new focus item.",
                "action": "KEEP_CURRENT_GOVERNED_CONFIGURATION",
                "authority": "NO_CHANGE",
            }
        )
    return output[:5]


def _story_lines(
    *,
    sections: dict[str, list[dict[str, Any]]],
    validation: dict[str, Any],
    paper: dict[str, Any],
    misses: list[dict[str, Any]],
) -> list[dict[str, str]]:
    best = sections["best_calls"]
    saves = sections["saves"]
    dumb = sections["dumb_calls"]
    lines: list[dict[str, str]] = []
    lines.append(
        {
            "speaker": "MAX",
            "line": (
                f"Factory close: {validation.get('benchmark_opportunity_count', 0)} benchmark opportunities, "
                f"{validation.get('detected_count', 0)} detected, {len(misses)} still sitting in the 'we should have seen that' pile."
            ),
            "basis": "9H persisted validation metrics and miss rows.",
        }
    )
    if best:
        row = best[0]
        lines.append(
            {
                "speaker": "MAX",
                "line": f"Best measured call: {row.get('ticker')} · {row.get('decision_quality')} · forward return {row.get('forward_return_pct')}%. Nice work. Nobody gets a statue.",
                "basis": "9J persisted decision-quality and forward-return fields.",
            }
        )
    if saves:
        row = saves[0]
        lines.append(
            {
                "speaker": "SKEPTIC",
                "line": f"Save of the day: {row.get('ticker')} stayed out and later measured {row.get('forward_return_pct')}%. Sometimes the sexiest trade is the one we didn't screw up.",
                "basis": "9J persisted NO_TRADE_AVOIDED_DOWNSIDE label.",
            }
        )
    if dumb:
        row = dumb[0]
        lines.append(
            {
                "speaker": "SKEPTIC",
                "line": f"Dumb-call file: {row.get('ticker')} · {row.get('decision_quality')}. Put it under glass and learn from the damn thing.",
                "basis": "9J persisted adverse/foregone-upside decision-quality label.",
            }
        )
    nav = _safe_float(paper.get("nav"))
    pnl = _safe_float(paper.get("total_pnl"))
    if nav is not None:
        lines.append(
            {
                "speaker": "PORTFOLIO",
                "line": f"Paper book closed this snapshot at NAV ${nav:,.2f}, total P&L ${pnl or 0.0:,.2f}. Paper is measurement, not permission to get cocky with real capital.",
                "basis": "9G persisted governed paper portfolio snapshot.",
            }
        )
    return lines


def build_daily_episode(
    *,
    scorecard: dict[str, Any],
    shadow: dict[str, Any],
    learning: dict[str, Any],
    telemetry: dict[str, Any],
    generated_at: datetime | None = None,
    final_requested: bool = False,
) -> dict[str, Any]:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    session_id = _session_id(scorecard, learning)
    outcomes = _session_outcomes(learning, session_id)
    sections = _build_decision_sections(outcomes)
    misses = _validation_misses(scorecard)
    validation = _validation_metrics(scorecard)
    paper = _paper_performance(telemetry)
    quality_counts = Counter(str(row.get("decision_quality") or "UNKNOWN") for row in outcomes)
    learning_session_match = bool(session_id and outcomes)
    status = "FINAL" if final_requested and learning_session_match else (
        "FINAL_WITH_LEARNING_WARMUP" if final_requested else "LIVE_DRAFT"
    )
    tomorrow = _tomorrow_focus(
        validation=validation,
        shadow=shadow,
        learning=learning,
        telemetry=telemetry,
        misses=misses,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "episode_session_id": session_id,
        "status": status,
        "title": f"IIOS Daily Factory Episode · {session_id or 'SESSION WARM-UP'}",
        "source_freshness": {
            "scorecard_generated_at": scorecard.get("generated_at"),
            "shadow_generated_at": shadow.get("generated_at"),
            "learning_generated_at": learning.get("generated_at"),
            "telemetry_generated_at": telemetry.get("generated_at"),
            "learning_session_match": learning_session_match,
        },
        "scoreboard": {
            "validation": validation,
            "paper": paper,
            "best_call_count": len(sections["best_calls"]),
            "save_count": len(sections["saves"]),
            "dumb_call_count": len(sections["dumb_calls"]),
            "validation_miss_count": len(misses),
            "learning_outcome_count": len(outcomes),
        },
        "best_calls": sections["best_calls"],
        "saves": sections["saves"],
        "dumb_calls": sections["dumb_calls"],
        "misses": misses,
        "learning_misses": sections["learning_misses"],
        "what_we_learned": {
            "decision_quality_counts": dict(sorted(quality_counts.items())),
            "learning_status": learning.get("status"),
            "complete_session_count": learning.get("complete_session_count"),
            "outcome_count": learning.get("outcome_count"),
            "mature_5d_count": learning.get("mature_5d_count"),
            "shadow_status": shadow.get("status"),
            "shadow_complete_session_count": shadow.get("complete_session_count"),
        },
        "tomorrow_focus": tomorrow,
        "story": _story_lines(
            sections=sections,
            validation=validation,
            paper=paper,
            misses=misses,
        ),
        "safety": {
            "report_only": True,
            "source_mode": "PERSISTED_9G_9H_9I_9J_READ_ONLY",
            "direct_ledger_access": False,
            "auto_apply_threshold_changes": False,
            "agent_weight_change_authority": False,
            "committee_change_authority": False,
            "risk_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }


def build_from_state(
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
    telemetry_dir: Path = DEFAULT_TELEMETRY_DIR,
    generated_at: datetime | None = None,
    final_requested: bool = False,
) -> dict[str, Any]:
    scorecard = _read_json(state_dir / "latest_market_validation.json") or {}
    shadow = _read_json(state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json") or {}
    learning = _read_json(state_dir / "browser" / "outcome_learning.json") or {}
    telemetry = _read_json(telemetry_dir / "latest.json") or {}
    if not scorecard and not telemetry:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
            "status": "WAITING_FOR_PERSISTED_FACTORY_STATE",
            "episode_session_id": None,
            "safety": {
                "report_only": True,
                "direct_ledger_access": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        }
    return build_daily_episode(
        scorecard=scorecard,
        shadow=shadow,
        learning=learning,
        telemetry=telemetry,
        generated_at=generated_at,
        final_requested=final_requested,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Batch 9O persisted-data daily IIOS factory episode."
    )
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--preview", action="store_true", help="Build a read-only LIVE_DRAFT and do not write final episode JSON")
    parser.add_argument("--force", action="store_true", help="Allow final generation before the normal 16:45 ET window")
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser()
    telemetry_dir = Path(args.telemetry_dir).expanduser()
    now_ny = datetime.now(NEW_YORK)
    output_path = state_dir / "browser" / "daily_factory_episode.json"

    if args.preview:
        payload = build_from_state(
            state_dir=state_dir,
            telemetry_dir=telemetry_dir,
            generated_at=now_ny.astimezone(timezone.utc),
            final_requested=False,
        )
        print(json.dumps(payload, indent=2 if args.stdout else None, sort_keys=True, default=str))
        return 0

    if not args.force:
        if now_ny.weekday() >= 5:
            print(json.dumps({"status": "SKIPPED_NON_MARKET_DAY", "as_of": now_ny.isoformat()}))
            return 0
        if now_ny.time().replace(tzinfo=None) < FINAL_WINDOW:
            print(json.dumps({"status": "SKIPPED_BEFORE_EPISODE_WINDOW", "as_of": now_ny.isoformat()}))
            return 0

    payload = build_from_state(
        state_dir=state_dir,
        telemetry_dir=telemetry_dir,
        generated_at=now_ny.astimezone(timezone.utc),
        final_requested=True,
    )
    if payload.get("status") == "WAITING_FOR_PERSISTED_FACTORY_STATE":
        print(json.dumps(payload, sort_keys=True))
        return 0

    previous = _read_json(output_path)
    if (
        previous
        and previous.get("episode_session_id") == payload.get("episode_session_id")
        and previous.get("status") == "FINAL"
        and payload.get("status") == "FINAL"
        and not args.force
    ):
        print(json.dumps({"status": "SKIPPED_EPISODE_ALREADY_FINAL", "episode_session_id": payload.get("episode_session_id")}))
        return 0

    _atomic_write(output_path, payload)
    summary = {
        "status": "BATCH9O_DAILY_FACTORY_EPISODE_WRITTEN",
        "episode_status": payload.get("status"),
        "episode_session_id": payload.get("episode_session_id"),
        "output": str(output_path),
        "best_call_count": len(payload.get("best_calls") or []),
        "save_count": len(payload.get("saves") or []),
        "dumb_call_count": len(payload.get("dumb_calls") or []),
        "validation_miss_count": len(payload.get("misses") or []),
        "direct_ledger_access": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    print(json.dumps(payload if args.stdout else summary, indent=2 if args.stdout else None, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
