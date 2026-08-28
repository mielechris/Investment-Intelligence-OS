#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch9t-market-regime-intelligence-v1"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _benchmark_rows(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    source = scorecard.get("input") if isinstance(scorecard.get("input"), dict) else {}
    rows = _rows(source.get("opportunities"))
    if rows:
        return rows
    return _rows(scorecard.get("opportunities"))


def _classification(rows: list[dict[str, Any]], benchmark_complete: bool) -> dict[str, Any]:
    moves = [value for value in (_float(row.get("move_pct")) for row in rows) if value is not None]
    sample = len(moves)
    up = sum(1 for value in moves if value >= 0.5)
    down = sum(1 for value in moves if value <= -0.5)
    neutral = sample - up - down
    up_share = (up / sample) if sample else 0.0
    down_share = (down / sample) if sample else 0.0
    abs_moves = [abs(value) for value in moves]
    median_abs = round(statistics.median(abs_moves), 2) if abs_moves else None
    mean_abs = round(statistics.mean(abs_moves), 2) if abs_moves else None
    signed_mean = round(statistics.mean(moves), 2) if moves else None
    high_importance = sum(1 for row in rows if str(row.get("importance") or "").upper() == "HIGH")
    extreme = sum(1 for value in moves if abs(value) >= 7.0)

    if sample < 8:
        label = "INSUFFICIENT_SIGNIFICANT_MOVER_SAMPLE"
    elif up_share >= 0.68 and (median_abs or 0.0) >= 3.5:
        label = "UPSIDE_SIGNIFICANT_MOVER_DOMINANCE"
    elif down_share >= 0.68 and (median_abs or 0.0) >= 3.5:
        label = "DOWNSIDE_SIGNIFICANT_MOVER_DOMINANCE"
    elif up_share >= 0.25 and down_share >= 0.25 and (median_abs or 0.0) >= 4.0:
        label = "BIDIRECTIONAL_HIGH_DISPERSION"
    elif (median_abs or 0.0) >= 5.0:
        label = "HIGH_DISPERSION_MIXED_DIRECTION"
    else:
        label = "MODERATE_SIGNIFICANT_MOVER_DISPERSION"

    evidence_level = (
        "HIGH" if benchmark_complete and sample >= 25
        else "MEDIUM" if benchmark_complete and sample >= 12
        else "LOW"
    )
    return {
        "regime_label": label,
        "evidence_level": evidence_level,
        "scope": "9H_SIGNIFICANT_MOVER_CROSS_SECTION_ONLY",
        "sample_count": sample,
        "upside_count": up,
        "downside_count": down,
        "neutral_count": neutral,
        "upside_share_pct": round(up_share * 100.0, 2),
        "downside_share_pct": round(down_share * 100.0, 2),
        "median_absolute_move_pct": median_abs,
        "mean_absolute_move_pct": mean_abs,
        "signed_mean_move_pct": signed_mean,
        "high_importance_count": high_importance,
        "extreme_move_count": extreme,
        "benchmark_complete": benchmark_complete,
    }


def build_regime(
    *,
    scorecard: dict[str, Any],
    learning: dict[str, Any],
    league: dict[str, Any],
    telemetry: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    input_block = scorecard.get("input") if isinstance(scorecard.get("input"), dict) else {}
    rows = _benchmark_rows(scorecard)
    benchmark_complete = bool(input_block.get("benchmark_complete"))
    current = _classification(rows, benchmark_complete)
    metrics = scorecard.get("metrics") if isinstance(scorecard.get("metrics"), dict) else {}
    agent_rows = _rows(league.get("agent_standings"))
    mature_agents = [row for row in agent_rows if row.get("status") in {"OFFICIAL", "PROVISIONAL"}]
    outcome_count = _int(learning.get("outcome_count"))

    dimensions = [
        {
            "dimension": "CROSS_SECTIONAL_DIRECTION",
            "state": "MEASURED",
            "value": current["regime_label"],
            "evidence": f"{current['upside_count']} upside vs {current['downside_count']} downside significant movers.",
        },
        {
            "dimension": "MOVE_INTENSITY_DISPERSION",
            "state": "MEASURED",
            "value": current.get("median_absolute_move_pct"),
            "evidence": "Derived only from persisted independent 9H significant-mover opportunities.",
        },
        {
            "dimension": "RATES_LIQUIDITY",
            "state": "MEASUREMENT_GAP",
            "value": None,
            "evidence": "No validated structured rates/liquidity regime series is persisted under the 9T contract yet.",
        },
        {
            "dimension": "VOLATILITY_INDEX_TERM_STRUCTURE",
            "state": "MEASUREMENT_GAP",
            "value": None,
            "evidence": "9R must validate a volatility/regime input before 9T can classify it.",
        },
        {
            "dimension": "INFLATION_GROWTH_MACRO",
            "state": "MEASUREMENT_GAP",
            "value": None,
            "evidence": "Official macro-release feeds are research candidates in 9R, not production regime inputs.",
        },
        {
            "dimension": "GEOPOLITICAL_STRESS",
            "state": "MEASUREMENT_GAP",
            "value": None,
            "evidence": "No governed composite geopolitical-stress series is persisted for regime labeling.",
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": "MARKET_REGIME_INTELLIGENCE_ACTIVE" if current["sample_count"] else "MARKET_REGIME_INTELLIGENCE_WARM_UP",
        "current_regime": current,
        "dimensions": dimensions,
        "regime_tag_contract": {
            "tag_new_sessions": True,
            "tagging_scope": "ADVISORY_METADATA_ONLY",
            "historical_backfill_available": False,
            "agent_regime_performance_available": bool(mature_agents and outcome_count),
            "agent_regime_performance_note": (
                "Agent rankings become regime-specific only after exact outcomes are persisted with a 9T regime tag."
            ),
        },
        "factory_context": {
            "9h_detection_rate_pct": _float(metrics.get("detection_rate_pct")),
            "9h_miss_rate_pct": _float(metrics.get("opportunity_miss_rate_pct")),
            "9j_outcome_count": outcome_count,
            "9s_official_or_provisional_agents": len(mature_agents),
            "9g_generated_at": telemetry.get("generated_at"),
        },
        "recommended_next_measurements": [
            "Persist validated rates/liquidity regime inputs through 9R.",
            "Persist validated volatility/term-structure inputs through 9R.",
            "Tag future 9H/9J sessions with the 9T regime snapshot for outcome attribution.",
            "Route any regime-specific threshold or weighting proposal through 9P → 9Q → human approval.",
        ],
        "safety": {
            "classification_only": True,
            "advisory_only": True,
            "auto_change_thresholds": False,
            "auto_change_agent_weights": False,
            "auto_change_model_routing": False,
            "auto_change_portfolio_exposure": False,
            "committee_change_authority": False,
            "risk_rule_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }


def build_from_state(state_dir: Path, telemetry_dir: Path) -> dict[str, Any]:
    return build_regime(
        scorecard=_read_json(state_dir / "latest_market_validation.json"),
        learning=_read_json(state_dir / "latest_outcome_learning.json"),
        league=_read_json(state_dir / "browser" / "agent_performance_league.json"),
        telemetry=_read_json(telemetry_dir / "latest.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Batch 9T read-only Market Regime Intelligence artifact.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(DEFAULT_TELEMETRY_DIR))
    parser.add_argument("--output")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    payload = build_from_state(Path(args.state_dir).expanduser(), Path(args.telemetry_dir).expanduser())
    if args.output:
        _atomic_write(Path(args.output).expanduser(), payload)
    print(json.dumps(payload if args.stdout or not args.output else {"status": payload["status"], "output": args.output}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
