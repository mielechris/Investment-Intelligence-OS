#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "batch10b-paper-performance-qualification-v1"
MIN_COMPLETE_SESSIONS = 20
MIN_PAPER_TRANSACTIONS = 30
MIN_MATURE_5D_OUTCOMES = 30
MAX_ABS_DRAWDOWN_PCT = 10.0
MIN_CUMULATIVE_RETURN_PCT = 0.0


def _int(value: Any) -> int:
    try: return int(value or 0)
    except (TypeError, ValueError): return 0


def _float(value: Any) -> float | None:
    try: return float(value)
    except (TypeError, ValueError): return None


def build_qualification(*, telemetry: dict[str, Any], learning: dict[str, Any], scorecard: dict[str, Any], generated_at: datetime | None = None) -> dict[str, Any]:
    fund = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
    sessions = _int(learning.get("complete_session_count"))
    transactions = _int(fund.get("transaction_count"))
    mature = _int(learning.get("mature_5d_count"))
    cumulative_return = _float(fund.get("cumulative_return_pct"))
    max_drawdown = _float(fund.get("max_drawdown_pct"))
    metrics = scorecard.get("metrics") if isinstance(scorecard.get("metrics"), dict) else {}
    detection_rate = _float(metrics.get("detection_rate_pct"))

    sample_sessions_pass = sessions >= MIN_COMPLETE_SESSIONS
    transaction_pass = transactions >= MIN_PAPER_TRANSACTIONS
    mature_pass = mature >= MIN_MATURE_5D_OUTCOMES
    drawdown_measurable = max_drawdown is not None
    drawdown_pass = drawdown_measurable and abs(min(0.0, max_drawdown or 0.0)) <= MAX_ABS_DRAWDOWN_PCT
    return_measurable = cumulative_return is not None
    return_pass = return_measurable and cumulative_return >= MIN_CUMULATIVE_RETURN_PCT
    sample_ready = sample_sessions_pass and transaction_pass and mature_pass

    if not sample_ready:
        status = "INSUFFICIENT_PAPER_SAMPLE"
    elif not drawdown_pass:
        status = "FAILED_RISK_QUALIFICATION"
    elif not return_pass:
        status = "FAILED_PERFORMANCE_QUALIFICATION"
    else:
        status = "PAPER_QUALIFIED_FOR_HUMAN_READINESS_REVIEW"

    def gate(name: str, observed: Any, required: str, passed: bool, waiting: bool = False) -> dict[str, Any]:
        return {"gate": name, "observed": observed, "required": required, "state": "WAITING" if waiting else ("PASS" if passed else "FAIL")}

    gates = [
        gate("COMPLETE_VALIDATION_SESSIONS", sessions, f">= {MIN_COMPLETE_SESSIONS}", sample_sessions_pass),
        gate("GOVERNED_PAPER_TRANSACTIONS", transactions, f">= {MIN_PAPER_TRANSACTIONS}", transaction_pass),
        gate("MATURE_5D_OUTCOMES", mature, f">= {MIN_MATURE_5D_OUTCOMES}", mature_pass),
        gate("MAX_DRAWDOWN", max_drawdown, f"absolute drawdown <= {MAX_ABS_DRAWDOWN_PCT}%", drawdown_pass, not drawdown_measurable),
        gate("CUMULATIVE_PAPER_RETURN", cumulative_return, f">= {MIN_CUMULATIVE_RETURN_PCT}% after sample gate", return_pass, not return_measurable),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": status,
        "rubric": "10B_V1_GOVERNED_PAPER_QUALIFICATION",
        "sample_ready": sample_ready,
        "paper_nav": _float(fund.get("nav")),
        "paper_positions": _int(fund.get("position_count")),
        "paper_transactions": transactions,
        "complete_validation_sessions": sessions,
        "mature_5d_outcomes": mature,
        "cumulative_return_pct": cumulative_return,
        "max_drawdown_pct": max_drawdown,
        "9h_detection_rate_pct": detection_rate,
        "gates": gates,
        "readiness_meaning": "Passing 10B permits only a human capital-readiness review in 10E. It does not authorize funding, brokerage, orders, or live execution.",
        "safety": {
            "paper_only": True,
            "qualification_only": True,
            "auto_advance_to_live": False,
            "capital_authority": False,
            "broker_connection_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }
