from __future__ import annotations

import math
from typing import Any


MAX_PORTFOLIO_RISK_PCT = 0.005

LOW_OVERLAP_MAX_POSITION_PCT = 0.05
MODERATE_OVERLAP_MAX_POSITION_PCT = 0.025

HIGH_OVERLAP_THRESHOLD_PCT = 50.0
MODERATE_OVERLAP_THRESHOLD_PCT = 25.0


def _positive(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric")

    if result <= 0:
        raise ValueError(f"{name} must be positive")

    return result


def _overlap_pct(
    portfolio_snapshot: dict[str, Any],
) -> float:
    overlap = portfolio_snapshot.get("overlap") or {}

    try:
        return float(
            overlap.get(
                "combined_overlap_weight_pct"
            )
            or 0.0
        )
    except (TypeError, ValueError):
        raise ValueError(
            "Portfolio overlap must be numeric"
        )


def _position_cap_pct(
    overlap_pct: float,
) -> float:
    if overlap_pct >= HIGH_OVERLAP_THRESHOLD_PCT:
        return 0.0

    if overlap_pct >= MODERATE_OVERLAP_THRESHOLD_PCT:
        return MODERATE_OVERLAP_MAX_POSITION_PCT

    return LOW_OVERLAP_MAX_POSITION_PCT


def size_paper_position(
    *,
    capital_gate: dict[str, Any],
    portfolio_snapshot: dict[str, Any] | None,
    portfolio_nav: float,
    invalidation_price: float,
    invalidation_basis: str,
) -> dict[str, Any]:
    """
    Deterministic paper-position sizing.

    This module calculates a proposed size only.

    It CANNOT:
      - create an execution authorization,
      - create a paper order,
      - spend real money,
      - infer an invalidation level.

    The invalidation price and its basis must be supplied
    explicitly.
    """

    nav = _positive(
        portfolio_nav,
        "portfolio_nav",
    )

    entry = _positive(
        capital_gate.get("current_price"),
        "current_price",
    )

    invalidation = _positive(
        invalidation_price,
        "invalidation_price",
    )

    basis = str(
        invalidation_basis or ""
    ).strip()

    if not basis:
        raise ValueError(
            "invalidation_basis is required"
        )

    if invalidation >= entry:
        raise ValueError(
            "invalidation_price must be below entry price"
        )

    if not portfolio_snapshot:
        return {
            "decision": "BLOCKED",
            "reason":
                "PORTFOLIO_SNAPSHOT_REQUIRED",
            "proposed_shares": 0,
            "proposed_notional": 0.0,
            "paper_order_permission": False,
            "trade_execution_permission": False,
        }

    overlap_pct = _overlap_pct(
        portfolio_snapshot
    )

    if capital_gate.get("decision") != "APPROVED":
        return {
            "decision": "BLOCKED",
            "reason":
                "CAPITAL_GATE_NOT_APPROVED",
            "capital_decision":
                capital_gate.get("decision"),
            "proposed_shares": 0,
            "proposed_notional": 0.0,
            "paper_order_permission": False,
            "trade_execution_permission": False,
        }

    if overlap_pct >= HIGH_OVERLAP_THRESHOLD_PCT:
        return {
            "decision": "BLOCKED",
            "reason":
                "PORTFOLIO_OVERLAP_TOO_HIGH",
            "combined_overlap_weight_pct":
                round(overlap_pct, 4),
            "proposed_shares": 0,
            "proposed_notional": 0.0,
            "paper_order_permission": False,
            "trade_execution_permission": False,
        }

    max_position_pct = _position_cap_pct(
        overlap_pct
    )

    risk_budget = (
        nav * MAX_PORTFOLIO_RISK_PCT
    )

    risk_per_share = (
        entry - invalidation
    )

    shares_by_risk = math.floor(
        risk_budget / risk_per_share
    )

    max_position_notional = (
        nav * max_position_pct
    )

    shares_by_position_cap = math.floor(
        max_position_notional / entry
    )

    proposed_shares = max(
        0,
        min(
            shares_by_risk,
            shares_by_position_cap,
        ),
    )

    proposed_notional = (
        proposed_shares * entry
    )

    proposed_loss_at_invalidation = (
        proposed_shares * risk_per_share
    )

    proposed_position_pct = (
        proposed_notional / nav
        if nav
        else 0.0
    )

    proposed_risk_pct = (
        proposed_loss_at_invalidation / nav
        if nav
        else 0.0
    )

    if proposed_shares <= 0:
        decision = "BLOCKED"
        reason = "NO_POSITION_WITHIN_RISK_LIMIT"
        binding_constraint = "RISK_OR_POSITION_CAP"
    else:
        decision = "SIZE_READY"
        reason = None

        if (
            shares_by_position_cap
            < shares_by_risk
        ):
            binding_constraint = (
                "PORTFOLIO_CONCENTRATION_CAP"
            )
        elif (
            shares_by_risk
            < shares_by_position_cap
        ):
            binding_constraint = (
                "MAX_LOSS_RISK_BUDGET"
            )
        else:
            binding_constraint = (
                "BOTH_LIMITS_BIND"
            )

    return {
        "decision": decision,
        "reason": reason,
        "entry_price": round(entry, 4),
        "invalidation_price":
            round(invalidation, 4),
        "invalidation_basis": basis,
        "risk_per_share":
            round(risk_per_share, 4),
        "portfolio_nav": round(nav, 2),

        "combined_overlap_weight_pct":
            round(overlap_pct, 4),
        "max_position_pct":
            round(max_position_pct, 4),
        "max_portfolio_risk_pct":
            MAX_PORTFOLIO_RISK_PCT,

        "risk_budget":
            round(risk_budget, 2),
        "max_position_notional":
            round(max_position_notional, 2),

        "shares_by_risk":
            shares_by_risk,
        "shares_by_position_cap":
            shares_by_position_cap,

        "proposed_shares":
            proposed_shares,
        "proposed_notional":
            round(proposed_notional, 2),
        "proposed_position_pct":
            round(proposed_position_pct, 6),

        "proposed_loss_at_invalidation":
            round(
                proposed_loss_at_invalidation,
                2,
            ),
        "proposed_portfolio_risk_pct":
            round(proposed_risk_pct, 6),

        "binding_constraint":
            binding_constraint,

        "governance": {
            "invalidation_is_explicit": True,
            "invalidation_is_inferred": False,
            "sizing_is_recommendation_only": True,
            "authorization_created": False,
        },

        "allowed_notional": 0.0,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
