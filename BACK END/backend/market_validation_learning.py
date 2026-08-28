from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "batch9h-market-validation-learning-v1"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_learning_report(
    scorecard: dict[str, Any],
    *,
    benchmark_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = scorecard.get("metrics") if isinstance(scorecard.get("metrics"), dict) else {}
    benchmark_meta = benchmark_meta if isinstance(benchmark_meta, dict) else {}
    benchmark_complete = bool((scorecard.get("input") or {}).get("benchmark_complete"))

    detection = _safe_float(metrics.get("detection_rate_pct"))
    miss = _safe_float(metrics.get("opportunity_miss_rate_pct"))
    false_positive = _safe_float(metrics.get("false_positive_rate_pct"))
    median_latency = _safe_float(metrics.get("median_detection_latency_minutes"))
    promotion_rate = _safe_float(metrics.get("promotion_rate_of_detected_pct"))
    cadence = _safe_float(metrics.get("cadence_reliability_pct"))
    provider_errors = int(metrics.get("provider_error_count") or 0)

    recommendations: list[dict[str, Any]] = []

    def recommend(code: str, rationale: str, action: str, priority: str = "MEDIUM") -> None:
        recommendations.append(
            {
                "code": code,
                "priority": priority,
                "rationale": rationale,
                "recommended_action": action,
                "authority": "ADVISORY_ONLY",
                "auto_apply": False,
            }
        )

    if not benchmark_complete:
        recommend(
            "BENCHMARK_INCOMPLETE",
            "The independent market benchmark did not meet its full-session coverage contract.",
            "Do not use false-positive conclusions for tuning; improve benchmark collection coverage first.",
            "HIGH",
        )
    else:
        if miss is not None and miss >= 35.0:
            recommend(
                "MISS_RATE_HIGH",
                f"Opportunity miss rate is {miss:.2f}%.",
                "Review 9E screener coverage, radar ranking weights, and pre-case evidence thresholds. Do not weaken Committee or Risk gates.",
                "HIGH",
            )
        elif detection is not None and detection >= 80.0:
            recommend(
                "DETECTION_STRONG",
                f"Detection rate is {detection:.2f}%.",
                "Keep the current discovery coverage as the control baseline and focus tuning on ranking quality and downstream conversion.",
                "LOW",
            )

        if false_positive is not None and false_positive >= 70.0:
            recommend(
                "FALSE_POSITIVE_RATE_HIGH",
                f"Factory candidate false-positive rate is {false_positive:.2f}% against the complete benchmark.",
                "Review 9E radar-score and promotion-ranking thresholds for precision. Any numeric threshold change requires a separate governed change review.",
                "MEDIUM",
            )

    if median_latency is not None and median_latency > 20.0:
        recommend(
            "DETECTION_LATENCY_HIGH",
            f"Median detection latency is {median_latency:.2f} minutes.",
            "Review collection cadence, provider latency, and ranking queue delay before changing investment decision thresholds.",
            "HIGH",
        )

    if promotion_rate is not None and detection is not None and detection >= 60.0 and promotion_rate < 10.0:
        recommend(
            "LOW_PROMOTION_CONVERSION",
            f"Detection is {detection:.2f}% but only {promotion_rate:.2f}% of detected benchmark opportunities were promoted.",
            "Audit pre-case evidence and eligibility filters for excessive rejection. Preserve Committee/Risk authority.",
            "MEDIUM",
        )

    if cadence is not None and cadence < 100.0:
        recommend(
            "FACTORY_CADENCE_DEGRADED",
            f"Factory cadence reliability is {cadence:.2f}% in the scorecard snapshot.",
            "Resolve worker cadence health before interpreting investment-intelligence quality metrics.",
            "HIGH",
        )

    if provider_errors > 0:
        recommend(
            "PROVIDER_ERRORS_PRESENT",
            f"The factory snapshot reports {provider_errors} provider error(s).",
            "Separate provider/data failures from model or decision-quality failures before tuning thresholds.",
            "HIGH",
        )

    opportunities = scorecard.get("opportunities") if isinstance(scorecard.get("opportunities"), list) else []
    missed = [
        {
            "ticker": row.get("ticker"),
            "event_at": row.get("event_at"),
            "move_pct": row.get("move_pct"),
            "importance": row.get("importance"),
        }
        for row in opportunities
        if isinstance(row, dict) and row.get("missed") is True
    ]
    detected_not_promoted = [
        {
            "ticker": row.get("ticker"),
            "candidate_id": row.get("candidate_id"),
            "candidate_score": row.get("candidate_score"),
            "radar_rank_score": row.get("radar_rank_score"),
        }
        for row in opportunities
        if isinstance(row, dict) and row.get("detected") is True and row.get("promoted") is not True
    ]

    status = "VALIDATION_INCOMPLETE" if not benchmark_complete else (
        "REVIEW_REQUIRED" if any(row["priority"] == "HIGH" for row in recommendations) else "HEALTHY_LEARNING_CYCLE"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "benchmark_complete": benchmark_complete,
        "benchmark_meta": benchmark_meta,
        "metrics": metrics,
        "missed_opportunities": missed,
        "detected_not_promoted": detected_not_promoted,
        "recommendations": recommendations,
        "learning_contract": {
            "recommendations_are_advisory_only": True,
            "auto_apply_threshold_changes": False,
            "committee_gate_change_authority": False,
            "risk_gate_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
