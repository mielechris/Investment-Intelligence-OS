from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from statistics import mean, pstdev
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from ledger import DB_PATH, record_event, record_object, utc_now


router = APIRouter()

EVALUATION_TYPE = "model_task_evaluation"
CALIBRATION_TYPE = "model_task_calibration"
SCALE_RUN_TYPE = "model_scale_validation_run"
CALIBRATION_VERSION = "BATCH_8F_TASK_CALIBRATION_V1"

MODEL_IDS = {
    "IIOS_OPENAI_CORE",
    "KIMI_RESEARCH",
    "GROK_NARRATIVE",
}

TASK_TYPES = {
    "DEEP_RESEARCH",
    "INSTITUTIONAL_SYNTHESIS",
    "NARRATIVE_SENTIMENT",
    "POLICY_MACRO",
    "DISSENT_DETECTION",
    "GENERAL_RESEARCH",
}

METRIC_KEYS = (
    "factual_accuracy",
    "citation_quality",
    "completeness",
    "dissent_detection",
    "committee_usefulness",
)

METRIC_WEIGHTS = {
    "factual_accuracy": 0.30,
    "citation_quality": 0.20,
    "completeness": 0.15,
    "dissent_detection": 0.15,
    "committee_usefulness": 0.20,
}

MIN_SAMPLES_PER_MODEL_TASK = 5
MIN_MATURE_MODELS_PER_TASK = 2
MAX_SCALE_EVALUATIONS = 500
MAX_LEDGER_EVALUATIONS = 5000
MIN_RECOMMENDED_WEIGHT = 0.75
MAX_RECOMMENDED_WEIGHT = 1.25
SYSTEM_CASE_ID = "system_model_calibration"


def _rows(
    object_type: str,
    limit: int = MAX_LEDGER_EVALUATIONS,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), MAX_LEDGER_EVALUATIONS))
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            """
            SELECT payload_json
            FROM ledger_objects
            WHERE object_type=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (object_type, safe_limit),
        ).fetchall()
    finally:
        db.close()
    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            output.append(payload)
    return output


def _identifier(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _score(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number between 0 and 1") from exc
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return round(number, 6)


def _nonnegative(value: Any, label: str) -> float:
    if value in (None, ""):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a nonnegative number") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a nonnegative number")
    return round(number, 6)


def normalize_evaluation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("evaluation must be an object")

    model = _identifier(payload.get("model"))
    if model not in MODEL_IDS:
        raise ValueError(
            "model must be one of: "
            + ", ".join(sorted(MODEL_IDS))
        )

    task_type = _identifier(payload.get("task_type"))
    if task_type not in TASK_TYPES:
        raise ValueError(
            "task_type must be one of: "
            + ", ".join(sorted(TASK_TYPES))
        )

    benchmark_id = str(
        payload.get("benchmark_id") or ""
    ).strip()
    if not benchmark_id:
        raise ValueError("benchmark_id is required")

    if (
        payload.get(
            "human_or_governed_benchmark_attested"
        )
        is not True
    ):
        raise ValueError(
            "human_or_governed_benchmark_attested must be true"
        )

    metrics_input = payload.get("metrics")
    if not isinstance(metrics_input, dict):
        raise ValueError("metrics must be an object")

    metrics = {
        key: _score(metrics_input.get(key), key)
        for key in METRIC_KEYS
    }

    if "latency_ms" not in payload:
        raise ValueError("latency_ms is required")
    if "cost_usd" not in payload:
        raise ValueError("cost_usd is required")

    case_id = str(
        payload.get("case_id") or ""
    ).strip() or None
    source_packet_id = str(
        payload.get("source_packet_id") or ""
    ).strip() or None

    return {
        "model": model,
        "task_type": task_type,
        "benchmark_id": benchmark_id,
        "case_id": case_id,
        "source_packet_id": source_packet_id,
        "metrics": metrics,
        "latency_ms": _nonnegative(
            payload.get("latency_ms"),
            "latency_ms",
        ),
        "cost_usd": _nonnegative(
            payload.get("cost_usd"),
            "cost_usd",
        ),
        "benchmark_source": str(
            payload.get("benchmark_source")
            or "HUMAN_OR_GOVERNED_REVIEW"
        )[:300],
        "human_or_governed_benchmark_attested": True,
        "notes": str(payload.get("notes") or "")[:2000],
        "operational_evaluation_only": True,
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "committee_override": False,
        "risk_override": False,
        "capital_authority": False,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _quality_score(
    evaluation: dict[str, Any],
) -> float:
    metrics = evaluation.get("metrics") or {}
    return round(
        sum(
            float(metrics.get(key) or 0.0)
            * METRIC_WEIGHTS[key]
            for key in METRIC_KEYS
        ),
        6,
    )


def _latency_efficiency(latency_ms: float) -> float:
    # A bounded operational comparison only. It can never
    # outweigh factual/citation quality.
    return 1.0 / (1.0 + max(0.0, latency_ms) / 30000.0)


def _cost_efficiency(cost_usd: float) -> float:
    return 1.0 / (1.0 + max(0.0, cost_usd) / 0.25)


def _composite_score(
    evaluation: dict[str, Any],
) -> float:
    quality = _quality_score(evaluation)
    latency = _latency_efficiency(
        float(evaluation.get("latency_ms") or 0.0)
    )
    cost = _cost_efficiency(
        float(evaluation.get("cost_usd") or 0.0)
    )
    return round(
        (0.90 * quality)
        + (0.07 * latency)
        + (0.03 * cost),
        6,
    )


def _deduplicate(
    evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # One benchmark may contribute at most one observation
    # per model/task in a calibration run.
    seen: set[tuple[str, str, str]] = set()
    output: list[dict[str, Any]] = []
    for row in evaluations:
        key = (
            str(row.get("task_type")),
            str(row.get("model")),
            str(row.get("benchmark_id")),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _model_summary(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    composite = [_composite_score(row) for row in rows]
    metric_means = {
        key: round(
            mean(
                float(
                    (row.get("metrics") or {}).get(key)
                    or 0.0
                )
                for row in rows
            ),
            6,
        )
        for key in METRIC_KEYS
    }
    unique_benchmarks = {
        str(row.get("benchmark_id"))
        for row in rows
    }
    sample_count = len(rows)
    mature = (
        sample_count >= MIN_SAMPLES_PER_MODEL_TASK
        and len(unique_benchmarks)
        >= MIN_SAMPLES_PER_MODEL_TASK
    )
    variability = (
        pstdev(composite)
        if len(composite) > 1
        else 0.0
    )
    reliability = max(0.0, min(1.0, 1.0 - variability))
    return {
        "sample_count": sample_count,
        "unique_benchmark_count": len(unique_benchmarks),
        "mature": mature,
        "metric_means": metric_means,
        "quality_score": round(
            mean(_quality_score(row) for row in rows),
            6,
        ),
        "composite_score": round(mean(composite), 6),
        "reliability_score": round(reliability, 6),
        "mean_latency_ms": round(
            mean(
                float(row.get("latency_ms") or 0.0)
                for row in rows
            ),
            3,
        ),
        "mean_cost_usd": round(
            mean(
                float(row.get("cost_usd") or 0.0)
                for row in rows
            ),
            6,
        ),
    }


def _bounded_task_weights(
    mature: dict[str, dict[str, Any]],
) -> dict[str, float]:
    if len(mature) < MIN_MATURE_MODELS_PER_TASK:
        return {
            model: 1.0
            for model in mature
        }

    score_mean = mean(
        float(summary["composite_score"])
        for summary in mature.values()
    )
    if score_mean <= 0:
        return {
            model: 1.0
            for model in mature
        }

    provisional = {
        model: max(
            MIN_RECOMMENDED_WEIGHT,
            min(
                MAX_RECOMMENDED_WEIGHT,
                float(summary["composite_score"])
                / score_mean,
            ),
        )
        for model, summary in mature.items()
    }

    normalization = mean(provisional.values()) or 1.0
    return {
        model: round(
            max(
                MIN_RECOMMENDED_WEIGHT,
                min(
                    MAX_RECOMMENDED_WEIGHT,
                    value / normalization,
                ),
            ),
            6,
        )
        for model, value in provisional.items()
    }


def build_calibration(
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(evaluations) > MAX_SCALE_EVALUATIONS:
        raise ValueError(
            f"At most {MAX_SCALE_EVALUATIONS} evaluations "
            "may be calibrated in one run"
        )

    normalized = [
        normalize_evaluation(row)
        for row in evaluations
    ]
    unique = _deduplicate(normalized)

    grouped: dict[
        str,
        dict[str, list[dict[str, Any]]],
    ] = defaultdict(lambda: defaultdict(list))
    for row in unique:
        grouped[row["task_type"]][row["model"]].append(row)

    tasks: dict[str, Any] = {}
    for task_type in sorted(grouped):
        model_summaries = {
            model: _model_summary(rows)
            for model, rows
            in sorted(grouped[task_type].items())
        }
        mature = {
            model: summary
            for model, summary in model_summaries.items()
            if summary["mature"]
        }
        weights = _bounded_task_weights(mature)
        ready = (
            len(mature)
            >= MIN_MATURE_MODELS_PER_TASK
        )

        recommendations: dict[str, Any] = {}
        for model in sorted(model_summaries):
            summary = model_summaries[model]
            recommendations[model] = {
                **summary,
                "recommended_task_weight": (
                    weights.get(model, 1.0)
                ),
                "recommendation_active": (
                    ready and summary["mature"]
                ),
                "manual_review_required": True,
                "automatically_applied_to_council": False,
            }

        tasks[task_type] = {
            "status": (
                "READY_FOR_MANUAL_REVIEW"
                if ready
                else "INSUFFICIENT_MATURE_MODELS"
            ),
            "mature_model_count": len(mature),
            "minimum_mature_models_required":
                MIN_MATURE_MODELS_PER_TASK,
            "minimum_samples_per_model_task":
                MIN_SAMPLES_PER_MODEL_TASK,
            "model_recommendations": recommendations,
            "task_specific_only": True,
            "universal_weight": None,
            "manual_promotion_required": True,
            "automatically_applied_to_council": False,
        }

    return {
        "calibration_version": CALIBRATION_VERSION,
        "input_evaluation_count": len(evaluations),
        "deduplicated_evaluation_count": len(unique),
        "duplicate_evaluation_count": (
            len(evaluations) - len(unique)
        ),
        "task_count": len(tasks),
        "tasks": tasks,
        "model_weighting_mode":
            "TASK_SPECIFIC_RECOMMENDATIONS_ONLY",
        "universal_model_weighting": False,
        "manual_promotion_required": True,
        "automatically_applied_to_council": False,
        "governed_iios_committee_remains_authoritative": True,
        "committee_override": False,
        "risk_override": False,
        "operational_evaluation_only": True,
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "capital_authority": False,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def record_evaluation(
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_evaluation(payload)
    evaluation_id = (
        f"model_task_eval_{uuid4().hex}"
    )
    row = {
        "model_task_evaluation_id": evaluation_id,
        **normalized,
        "created_at": utc_now(),
    }
    case_id = (
        normalized.get("case_id")
        or SYSTEM_CASE_ID
    )
    record_object(
        evaluation_id,
        EVALUATION_TYPE,
        case_id,
        row,
        topic="model-task-evaluation",
    )
    record_event(
        case_id,
        "MODEL_TASK_EVALUATION_RECORDED",
        entity_id=evaluation_id,
        payload={
            "model": normalized["model"],
            "task_type": normalized["task_type"],
            "benchmark_id": normalized["benchmark_id"],
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )
    return row


def run_scale_validation(
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = dict(request or {})
    supplied = request.get("evaluations")
    persist = request.get("persist") is not False

    if supplied is None:
        evaluations = _rows(
            EVALUATION_TYPE,
            MAX_SCALE_EVALUATIONS,
        )
        source = "LEDGER"
    else:
        if not isinstance(supplied, list):
            raise ValueError("evaluations must be a list")
        if len(supplied) > MAX_SCALE_EVALUATIONS:
            raise ValueError(
                f"At most {MAX_SCALE_EVALUATIONS} evaluations "
                "may be submitted in one run"
            )
        evaluations = [
            normalize_evaluation(row)
            for row in supplied
        ]
        source = "REQUEST"

    calibration = build_calibration(evaluations)
    run_id = f"model_scale_run_{uuid4().hex}"
    result = {
        "model_scale_validation_run_id": run_id,
        "source": source,
        "persisted": persist,
        "scale_limits": {
            "maximum_evaluations_per_run":
                MAX_SCALE_EVALUATIONS,
            "minimum_samples_per_model_task":
                MIN_SAMPLES_PER_MODEL_TASK,
            "minimum_mature_models_per_task":
                MIN_MATURE_MODELS_PER_TASK,
            "minimum_recommended_weight":
                MIN_RECOMMENDED_WEIGHT,
            "maximum_recommended_weight":
                MAX_RECOMMENDED_WEIGHT,
        },
        **calibration,
        "created_at": utc_now(),
    }

    if persist:
        record_object(
            run_id,
            SCALE_RUN_TYPE,
            SYSTEM_CASE_ID,
            result,
            topic="model-scale-validation",
        )
        calibration_id = (
            f"model_task_calibration_{uuid4().hex}"
        )
        calibration_record = {
            "model_task_calibration_id":
                calibration_id,
            "source_scale_run_id": run_id,
            **calibration,
            "created_at": utc_now(),
        }
        record_object(
            calibration_id,
            CALIBRATION_TYPE,
            SYSTEM_CASE_ID,
            calibration_record,
            topic="model-task-calibration",
        )
        record_event(
            SYSTEM_CASE_ID,
            "MODEL_SCALE_VALIDATION_COMPLETE",
            entity_id=run_id,
            payload={
                "input_evaluation_count":
                    calibration[
                        "input_evaluation_count"
                    ],
                "task_count":
                    calibration["task_count"],
                "manual_promotion_required": True,
                "automatically_applied_to_council":
                    False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        )

    return result


def status() -> dict[str, Any]:
    evaluations = _rows(EVALUATION_TYPE, 1000)
    calibrations = _rows(CALIBRATION_TYPE, 100)
    runs = _rows(SCALE_RUN_TYPE, 100)
    return {
        "name": (
            "IIOS Multi-Model Scale Validation "
            "and Task Calibration"
        ),
        "calibration_version": CALIBRATION_VERSION,
        "evaluation_count": len(evaluations),
        "calibration_count": len(calibrations),
        "scale_run_count": len(runs),
        "latest_calibration": (
            calibrations[0]
            if calibrations
            else None
        ),
        "supported_models": sorted(MODEL_IDS),
        "supported_task_types": sorted(TASK_TYPES),
        "metric_keys": list(METRIC_KEYS),
        "minimum_samples_per_model_task":
            MIN_SAMPLES_PER_MODEL_TASK,
        "minimum_mature_models_per_task":
            MIN_MATURE_MODELS_PER_TASK,
        "maximum_evaluations_per_run":
            MAX_SCALE_EVALUATIONS,
        "recommended_weight_bounds": {
            "minimum": MIN_RECOMMENDED_WEIGHT,
            "maximum": MAX_RECOMMENDED_WEIGHT,
        },
        "model_weighting_mode":
            "TASK_SPECIFIC_RECOMMENDATIONS_ONLY",
        "universal_model_weighting": False,
        "manual_promotion_required": True,
        "automatically_applied_to_council": False,
        "governed_iios_committee_remains_authoritative": True,
        "committee_override": False,
        "risk_override": False,
        "operational_evaluation_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "fact_resolution_authority": False,
        "capital_authority": False,
        "trade_signal": False,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get(
    "/intelligence/model-calibration/status"
)
def get_status():
    return status()


@router.post(
    "/intelligence/model-calibration/evaluations"
)
def create_evaluation(
    request: dict[str, Any] = Body(default={}),
):
    try:
        return record_evaluation(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.post(
    "/intelligence/model-calibration/run"
)
def run_calibration(
    request: dict[str, Any] = Body(default={}),
):
    try:
        return run_scale_validation(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.get(
    "/intelligence/model-calibration/task/{task_type}"
)
def get_task_calibration(task_type: str):
    normalized = _identifier(task_type)
    if normalized not in TASK_TYPES:
        raise HTTPException(
            status_code=404,
            detail="Unknown task_type",
        )
    calibrations = _rows(CALIBRATION_TYPE, 100)
    for calibration in calibrations:
        task = (
            calibration.get("tasks") or {}
        ).get(normalized)
        if task:
            return {
                "task_type": normalized,
                "calibration": task,
                "source_calibration_id":
                    calibration.get(
                        "model_task_calibration_id"
                    ),
                "manual_promotion_required": True,
                "automatically_applied_to_council":
                    False,
                "trade_execution_permission": False,
                "live_execution": False,
            }
    return {
        "task_type": normalized,
        "calibration": None,
        "status": "NO_CALIBRATION_AVAILABLE",
        "manual_promotion_required": True,
        "automatically_applied_to_council": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
