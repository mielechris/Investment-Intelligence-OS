from __future__ import annotations

from typing import Any


MIN_REWARD_RISK = 1.50
MAX_WATCH_OBLIGATIONS = 4

# Explicit model assumptions — not observed facts.
UPSIDE_NORMALIZED_MULTIPLE = 18.0
DOWNSIDE_STRESS_MULTIPLE = 15.0

# Portfolio sizing policy for future paper authorization.
MAX_POSITION_PCT = 0.05
MAX_PORTFOLIO_RISK_PCT = 0.005


def _positive(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric")

    if result <= 0:
        raise ValueError(f"{name} must be positive")

    return result


def _severe_downside_scenario(
    stress: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Use the explicitly modeled severe scenario:
      ASP -20%
      earnings elasticity 2.0x
    """

    for row in stress.get("scenarios") or []:
        if not isinstance(row, dict):
            continue

        if (
            float(row.get("asp_decline_pct") or 0.0)
            == 20.0
            and float(
                row.get(
                    "earnings_elasticity_to_asp"
                )
                or 0.0
            )
            == 2.0
        ):
            return row

    return None


def required_entry_for_reward_risk(
    *,
    upside_value: float,
    downside_value: float,
    minimum_reward_risk: float,
) -> float:
    """
    Solve:

      (upside - entry)
      ---------------- >= R
      (entry - downside)

    for the maximum qualifying entry price.
    """

    upside_value = _positive(
        upside_value,
        "upside_value",
    )

    downside_value = _positive(
        downside_value,
        "downside_value",
    )

    minimum_reward_risk = _positive(
        minimum_reward_risk,
        "minimum_reward_risk",
    )

    if upside_value <= downside_value:
        raise ValueError(
            "upside_value must exceed downside_value"
        )

    return (
        upside_value
        + minimum_reward_risk * downside_value
    ) / (1.0 + minimum_reward_risk)


def assess_paper_capital(
    *,
    qualification: dict[str, Any],
    risk: dict[str, Any],
    stress: dict[str, Any],
    thesis_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Capital-underwriting gate.

    This function CANNOT create a paper order.

    It judges:
      1. research qualification,
      2. governed Risk status,
      3. quote/stress integrity,
      4. modeled upside/downside,
      5. reward/risk at the current entry,
      6. unresolved watch burden.
    """

    baseline = stress.get("baseline") or {}
    normalized = stress.get(
        "normalized_cycle"
    ) or {}

    current_price = _positive(
        baseline.get("current_price"),
        "current_price",
    )

    normalized_mid_eps = _positive(
        normalized.get("mid_eps"),
        "normalized_mid_eps",
    )

    severe = _severe_downside_scenario(stress)

    if not severe:
        raise ValueError(
            "Required severe downside scenario missing"
        )

    stressed_eps = _positive(
        severe.get("stressed_eps"),
        "severe_stressed_eps",
    )

    upside_value = (
        normalized_mid_eps
        * UPSIDE_NORMALIZED_MULTIPLE
    )

    downside_value = (
        stressed_eps
        * DOWNSIDE_STRESS_MULTIPLE
    )

    upside_dollars = upside_value - current_price
    downside_dollars = current_price - downside_value

    reward_risk = (
        upside_dollars / downside_dollars
        if upside_dollars > 0
        and downside_dollars > 0
        else 0.0
    )

    max_entry = required_entry_for_reward_risk(
        upside_value=upside_value,
        downside_value=downside_value,
        minimum_reward_risk=MIN_REWARD_RISK,
    )

    reconciliation = (
        risk.get(
            "required_evidence_reconciliation"
        )
        or {}
    )

    watch_obligations = [
        row
        for row in risk.get(
            "watch_obligations"
        )
        or []
        if isinstance(row, dict)
    ]

    quote_origin = str(
        (
            stress.get("input_lineage")
            or {}
        ).get("quote_origin")
        or ""
    )

    thesis_status = (
        thesis_status
        if isinstance(thesis_status, dict)
        else {}
    )

    thesis_state = str(
        thesis_status.get("status")
        or ""
    )

    thesis_governance = (
        thesis_status.get("governance")
        or {}
    )

    thesis_breached_rules = [
        str(rule)
        for rule in (
            thesis_status.get("breached_rules")
            or []
        )
        if str(rule).strip()
    ]

    checks = {
        "qualified_buy_candidate": bool(
            qualification.get(
                "qualified_buy_candidate"
            )
        ),
        "research_unmet_clear": not bool(
            qualification.get(
                "unmet_requirements"
            )
        ),
        "risk_watch_only": (
            risk.get("decision")
            == "WATCH_ONLY"
        ),
        "risk_rules_clear": not bool(
            risk.get("triggered_rules")
        ),
        "governed_blockers_clear": (
            int(
                reconciliation.get(
                    "blocking_count"
                )
                or 0
            )
            == 0
        ),
        "governed_scope_clear": (
            int(
                reconciliation.get(
                    "ungoverned_new_scope_count"
                )
                or 0
            )
            == 0
        ),
        "quote_lineage_current": (
            quote_origin
            == "GAP_HUNTER_EXACT_QUOTE"
        ),
        "watch_burden_within_policy": (
            len(watch_obligations)
            <= MAX_WATCH_OBLIGATIONS
        ),

        # Thesis validity is a separate hard gate.
        "thesis_status_present": bool(
            thesis_status
        ),
        "thesis_mapper_deterministic": (
            thesis_governance.get(
                "deterministic_mapper"
            )
            is True
            and thesis_governance.get(
                "llm_can_trigger_rule"
            )
            is False
        ),
        "thesis_status_allowed": (
            thesis_state
            in {
                "ACTIVE_CLEAR",
                "ACTIVE_WITH_WATCHES",
            }
        ),
        "thesis_not_invalidated": (
            thesis_status.get(
                "thesis_invalidated"
            )
            is False
            and not thesis_breached_rules
        ),

        "positive_upside": (
            upside_value > current_price
        ),
        "reward_risk_passed": (
            reward_risk >= MIN_REWARD_RISK
        ),
    }

    hard_fail_keys = (
        "qualified_buy_candidate",
        "research_unmet_clear",
        "risk_watch_only",
        "risk_rules_clear",
        "governed_blockers_clear",
        "governed_scope_clear",
        "quote_lineage_current",
        "watch_burden_within_policy",
        "thesis_status_present",
        "thesis_mapper_deterministic",
        "thesis_status_allowed",
        "thesis_not_invalidated",
    )

    hard_failed = [
        key
        for key in hard_fail_keys
        if not checks[key]
    ]

    if hard_failed:
        decision = "REJECTED"
    elif not checks["positive_upside"]:
        decision = "WAIT_FOR_ENTRY"
    elif not checks["reward_risk_passed"]:
        decision = "WAIT_FOR_ENTRY"
    else:
        decision = "APPROVED"

    # IMPORTANT:
    # Even APPROVED here is only capital-gate approval.
    # Execution wiring is intentionally disabled.
    allowed_notional = 0.0

    return {
        "decision":
            decision,
        "checks":
            checks,
        "failed_hard_checks":
            hard_failed,
        "current_price":
            round(current_price, 4),
        "upside_reference_value":
            round(upside_value, 4),
        "downside_reference_value":
            round(downside_value, 4),
        "upside_dollars":
            round(upside_dollars, 4),
        "downside_dollars":
            round(downside_dollars, 4),
        "reward_risk":
            round(reward_risk, 4),
        "minimum_reward_risk":
            MIN_REWARD_RISK,
        "maximum_qualifying_entry":
            round(max_entry, 4),
        "watch_obligation_count":
            len(watch_obligations),
        "watch_obligations":
            watch_obligations,

        "thesis_status":
            thesis_state,
        "thesis_invalidated":
            thesis_status.get(
                "thesis_invalidated"
            ),
        "thesis_breached_rules":
            thesis_breached_rules,
        "thesis_watching_rules":
            thesis_status.get(
                "watching_rules"
            )
            or [],

        "model_policy": {
            "upside_method":
                "NORMALIZED_MID_EPS_X_18",
            "downside_method":
                "ASP_MINUS_20_ELASTICITY_2X_EPS_X_15",
            "upside_multiple":
                UPSIDE_NORMALIZED_MULTIPLE,
            "downside_multiple":
                DOWNSIDE_STRESS_MULTIPLE,
            "max_position_pct":
                MAX_POSITION_PCT,
            "max_portfolio_risk_pct":
                MAX_PORTFOLIO_RISK_PCT,
        },
        "allowed_notional":
            allowed_notional,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
    }
