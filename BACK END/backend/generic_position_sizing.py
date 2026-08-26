from __future__ import annotations

from typing import Any
from uuid import uuid4

from generic_public_company_capital import _ticker_for_case
from ledger import (
    get_object,
    latest_object,
    record_event,
    record_object,
    utc_now,
)
from paper_portfolio_core import build_portfolio_state
from paper_position_sizing import size_paper_position


POLICY_VERSION = "generic-position-sizing-v1"

CAPITAL_DOWNSIDE_REFERENCE = "CAPITAL_DOWNSIDE_REFERENCE"
MANUAL_APPROVED = "MANUAL_APPROVED"

ALLOWED_INVALIDATION_MODES = {
    CAPITAL_DOWNSIDE_REFERENCE,
    MANUAL_APPROVED,
}


def _blocked(
    *,
    case_id: str,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "policy_version": POLICY_VERSION,
        "decision": "BLOCKED",
        "reason": reason,
        "proposed_shares": 0,
        "proposed_notional": 0.0,
        **extra,
        "paper_mode": True,
        "position_sizing_is_proposal_only": True,
        "paper_authorization_ready": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def configure_generic_sizing_profile(
    case_id: str,
    *,
    invalidation_mode: str = CAPITAL_DOWNSIDE_REFERENCE,
    manual_invalidation_price: float | None = None,
    invalidation_basis: str | None = None,
    enabled: bool = True,
    human_approved: bool = False,
) -> dict[str, Any]:
    case = get_object(case_id)

    if not case:
        raise ValueError("Unknown case_id")

    mode = str(invalidation_mode or "").upper()

    if mode not in ALLOWED_INVALIDATION_MODES:
        raise ValueError(
            "Unsupported invalidation_mode"
        )

    if mode == MANUAL_APPROVED:
        if human_approved is not True:
            raise ValueError(
                "Manual invalidation requires "
                "human_approved=True"
            )

        if (
            manual_invalidation_price is None
            or float(manual_invalidation_price) <= 0
        ):
            raise ValueError(
                "Valid manual invalidation price required"
            )

        if not str(invalidation_basis or "").strip():
            raise ValueError(
                "Manual invalidation basis required"
            )

    existing = latest_object(
        "generic_sizing_profile",
        case_id=case_id,
    ) or {}

    profile_id = (
        existing.get("generic_sizing_profile_id")
        or f"generic_sizing_profile_{uuid4().hex}"
    )

    profile = {
        "generic_sizing_profile_id": profile_id,
        "case_id": case_id,
        "policy_version": POLICY_VERSION,
        "enabled": bool(enabled),
        "invalidation_mode": mode,
        "manual_invalidation_price": (
            float(manual_invalidation_price)
            if manual_invalidation_price is not None
            else None
        ),
        "invalidation_basis": (
            str(invalidation_basis).strip()
            if invalidation_basis
            else None
        ),
        "human_approved": bool(human_approved),
        "whole_shares_only": True,
        "max_portfolio_risk_pct": 0.005,
        "low_overlap_max_position_pct": 0.05,
        "automatic_authorization": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": (
            existing.get("created_at")
            or utc_now()
        ),
        "updated_at": utc_now(),
    }

    record_object(
        profile_id,
        "generic_sizing_profile",
        case_id,
        profile,
        topic=case.get("topic"),
    )

    record_event(
        case_id,
        "GENERIC_SIZING_PROFILE_CONFIGURED",
        entity_id=profile_id,
        payload={
            "invalidation_mode": mode,
            "enabled": bool(enabled),
            "human_approved": bool(human_approved),
            "paper_order_permission": False,
            "trade_execution_permission": False,
        },
    )

    return profile


def _ensure_profile(
    case_id: str,
) -> dict[str, Any]:
    existing = latest_object(
        "generic_sizing_profile",
        case_id=case_id,
    )

    if existing:
        return existing

    # Conservative default:
    # explicitly use the frozen Capital downside
    # reference as the risk boundary.
    return configure_generic_sizing_profile(
        case_id,
        invalidation_mode=CAPITAL_DOWNSIDE_REFERENCE,
        enabled=True,
        human_approved=False,
    )


def _resolve_invalidation(
    *,
    profile: dict[str, Any],
    capital_gate: dict[str, Any],
) -> tuple[float, str]:
    entry = float(
        capital_gate.get("current_price") or 0
    )

    if entry <= 0:
        raise ValueError(
            "Capital entry price unavailable"
        )

    mode = str(
        profile.get("invalidation_mode") or ""
    ).upper()

    if mode == CAPITAL_DOWNSIDE_REFERENCE:
        invalidation = float(
            capital_gate.get(
                "downside_reference_value"
            )
            or 0
        )

        basis = (
            "Frozen Generic Capital downside "
            "reference; deterministic risk boundary, "
            "not an LLM-inferred stop"
        )

    elif mode == MANUAL_APPROVED:
        if profile.get("human_approved") is not True:
            raise ValueError(
                "Manual invalidation is not approved"
            )

        invalidation = float(
            profile.get(
                "manual_invalidation_price"
            )
            or 0
        )

        basis = str(
            profile.get("invalidation_basis") or ""
        ).strip()

        if not basis:
            raise ValueError(
                "Manual invalidation basis missing"
            )

    else:
        raise ValueError(
            "Invalidation mode unavailable"
        )

    if invalidation <= 0:
        raise ValueError(
            "Invalidation price unavailable"
        )

    if invalidation >= entry:
        raise ValueError(
            "Invalidation must be below entry"
        )

    return invalidation, basis


def _live_sizing_snapshot(
    *,
    case_id: str,
    ticker: str,
) -> dict[str, Any]:
    state = build_portfolio_state()

    nav = float(state.get("nav") or 0)
    positions = state.get("positions") or []

    if nav <= 0:
        raise ValueError(
            "Paper portfolio NAV unavailable"
        )

    exact_overlap_pct = 0.0

    for position in positions:
        if (
            str(position.get("ticker") or "")
            .upper()
            != ticker.upper()
        ):
            continue

        market_value = float(
            position.get("market_value") or 0
        )

        exact_overlap_pct = (
            market_value / nav * 100.0
            if nav > 0
            else 0.0
        )

    if not positions:
        combined_overlap_pct = 0.0
        overlap_source = "EMPTY_PORTFOLIO"

    else:
        observation = latest_object(
            "prospective_portfolio_observation",
            case_id=case_id,
        ) or {}

        if not observation:
            raise ValueError(
                "PORTFOLIO_OVERLAP_CONTEXT_REQUIRED"
            )

        observed_count = int(
            observation.get(
                "existing_position_count"
            )
            or 0
        )

        if observed_count != len(positions):
            raise ValueError(
                "PORTFOLIO_OVERLAP_CONTEXT_STALE"
            )

        components = [
            exact_overlap_pct,
            float(
                observation.get(
                    "same_sector_overlap_pct"
                )
                or 0
            ),
            float(
                observation.get(
                    "factor_overlap_pct"
                )
                or 0
            ),
        ]

        # Avoid double-counting overlapping exposure
        # categories while remaining conservative.
        combined_overlap_pct = max(components)

        overlap_source = (
            observation.get(
                "prospective_portfolio_observation_id"
            )
            or "GOVERNED_PORTFOLIO_OBSERVATION"
        )

    return {
        "portfolio_snapshot_id":
            f"generic_sizing_snapshot_{uuid4().hex}",
        "case_id": case_id,
        "ticker": ticker,
        "nav": round(nav, 2),
        "cash": state.get("cash"),
        "position_count": len(positions),
        "positions": positions,
        "overlap": {
            "exact_ticker_overlap_pct":
                round(exact_overlap_pct, 4),
            "combined_overlap_weight_pct":
                round(combined_overlap_pct, 4),
            "overlap_source":
                overlap_source,
        },
        "paper_mode": True,
        "measurement_only": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def calculate_generic_position_sizing(
    *,
    case_id: str,
    capital_gate: dict[str, Any],
) -> dict[str, Any]:
    if capital_gate.get("decision") != "APPROVED":
        return _blocked(
            case_id=case_id,
            reason="CAPITAL_GATE_NOT_APPROVED",
            capital_decision=capital_gate.get(
                "decision"
            ),
        )

    try:
        ticker = _ticker_for_case(case_id)
    except Exception as exc:
        return _blocked(
            case_id=case_id,
            reason="TICKER_UNAVAILABLE",
            error=str(exc),
        )

    try:
        profile = _ensure_profile(case_id)

        if profile.get("enabled") is not True:
            return _blocked(
                case_id=case_id,
                reason="GENERIC_SIZING_PROFILE_DISABLED",
            )

        invalidation, basis = (
            _resolve_invalidation(
                profile=profile,
                capital_gate=capital_gate,
            )
        )

        portfolio_snapshot = (
            _live_sizing_snapshot(
                case_id=case_id,
                ticker=ticker,
            )
        )

        sizing = size_paper_position(
            capital_gate=capital_gate,
            portfolio_snapshot=portfolio_snapshot,
            portfolio_nav=float(
                portfolio_snapshot["nav"]
            ),
            invalidation_price=invalidation,
            invalidation_basis=basis,
        )

    except (TypeError, ValueError) as exc:
        return _blocked(
            case_id=case_id,
            reason=str(exc),
        )

    sizing_id = (
        f"generic_position_sizing_"
        f"{uuid4().hex}"
    )

    result = {
        **sizing,
        "generic_position_sizing_id":
            sizing_id,
        "case_id": case_id,
        "ticker": ticker,
        "policy_version": POLICY_VERSION,
        "generic_sizing_profile_id":
            profile.get(
                "generic_sizing_profile_id"
            ),
        "invalidation_mode":
            profile.get(
                "invalidation_mode"
            ),
        "portfolio_snapshot":
            portfolio_snapshot,
        "whole_shares_only": True,
        "position_sizing_is_proposal_only": True,
        "paper_authorization_ready": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
        "paper_mode": True,
    }

    record_object(
        sizing_id,
        "generic_position_sizing",
        case_id,
        result,
    )

    record_event(
        case_id,
        "GENERIC_POSITION_SIZING_CALCULATED",
        entity_id=sizing_id,
        payload={
            "decision": result.get("decision"),
            "proposed_shares":
                result.get("proposed_shares"),
            "proposed_notional":
                result.get("proposed_notional"),
            "binding_constraint":
                result.get(
                    "binding_constraint"
                ),
            "paper_authorization_ready": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )

    return result
