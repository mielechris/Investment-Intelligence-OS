from __future__ import annotations

from collections import Counter
from typing import Any

from ledger import latest_object
from paper_portfolio_core import (
    STARTING_CASH,
    _rows_by_type,
    build_portfolio_state,
)


POLICY_VERSION = "paper-portfolio-validation-v1"


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _max_drawdown_pct(
    nav_values: list[float],
) -> float:
    if not nav_values:
        return 0.0

    peak = nav_values[0]
    maximum_drawdown = 0.0

    for nav in nav_values:
        if nav > peak:
            peak = nav

        if peak <= 0:
            continue

        drawdown = (
            (peak - nav)
            / peak
            * 100.0
        )

        maximum_drawdown = max(
            maximum_drawdown,
            drawdown,
        )

    return round(
        maximum_drawdown,
        4,
    )


def portfolio_performance_summary() -> dict[str, Any]:
    state = build_portfolio_state()

    snapshots = [
        row
        for row in _rows_by_type(
            "paper_portfolio_snapshot"
        )
        if row.get(
            "paper_portfolio_account_id"
        )
        == state.get(
            "paper_portfolio_account_id"
        )
    ]

    nav_series = [
        STARTING_CASH
    ]

    nav_series.extend(
        _safe_float(row.get("nav"))
        for row in snapshots
        if _safe_float(
            row.get("nav")
        ) > 0
    )

    current_nav = _safe_float(
        state.get("nav"),
        STARTING_CASH,
    )

    if (
        not nav_series
        or abs(
            nav_series[-1]
            - current_nav
        ) > 0.01
    ):
        nav_series.append(
            current_nav
        )

    starting_nav = float(
        STARTING_CASH
    )

    total_return_pct = (
        (
            current_nav
            - starting_nav
        )
        / starting_nav
        * 100.0
        if starting_nav > 0
        else 0.0
    )

    cash = _safe_float(
        state.get("cash")
    )

    gross = _safe_float(
        state.get(
            "gross_exposure"
        )
    )

    cash_pct = (
        cash / current_nav * 100.0
        if current_nav > 0
        else 0.0
    )

    gross_pct = (
        gross / current_nav * 100.0
        if current_nav > 0
        else 0.0
    )

    latest_snapshot = (
        snapshots[-1]
        if snapshots
        else {}
    )

    benchmark = (
        latest_snapshot.get(
            "benchmark"
        )
        or {}
    )

    benchmark_return_pct = (
        benchmark.get(
            "return_pct"
        )
        if isinstance(
            benchmark,
            dict,
        )
        else None
    )

    if benchmark_return_pct is None:
        benchmark_return_pct = (
            latest_snapshot.get(
                "benchmark_return_pct"
            )
        )

    excess_return_pct = None

    if benchmark_return_pct is not None:
        excess_return_pct = round(
            total_return_pct
            - _safe_float(
                benchmark_return_pct
            ),
            4,
        )

    return {
        "policy_version":
            POLICY_VERSION,

        "starting_nav":
            round(
                starting_nav,
                2,
            ),

        "current_nav":
            round(
                current_nav,
                2,
            ),

        "cash":
            round(
                cash,
                2,
            ),

        "cash_pct":
            round(
                cash_pct,
                4,
            ),

        "gross_exposure":
            round(
                gross,
                2,
            ),

        "gross_exposure_pct":
            round(
                gross_pct,
                4,
            ),

        "position_count":
            int(
                state.get(
                    "position_count"
                )
                or 0
            ),

        "transaction_count":
            int(
                state.get(
                    "transaction_count"
                )
                or 0
            ),

        "snapshot_count":
            len(snapshots),

        "total_pnl":
            _safe_float(
                state.get(
                    "total_pnl"
                )
            ),

        "realized_pnl":
            _safe_float(
                state.get(
                    "realized_pnl"
                )
            ),

        "unrealized_pnl":
            _safe_float(
                state.get(
                    "unrealized_pnl"
                )
            ),

        "total_return_pct":
            round(
                total_return_pct,
                4,
            ),

        "maximum_drawdown_pct":
            _max_drawdown_pct(
                nav_series
            ),

        "benchmark_return_pct":
            benchmark_return_pct,

        "excess_return_pct":
            excess_return_pct,

        "portfolio_flags":
            state.get(
                "portfolio_flags"
            )
            or [],

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def portfolio_attribution() -> dict[str, Any]:
    state = build_portfolio_state()

    realized_by_ticker: dict[
        str,
        float,
    ] = {}

    for row in _rows_by_type(
        "paper_portfolio_transaction"
    ):
        ticker = str(
            row.get("ticker")
            or ""
        ).upper()

        if not ticker:
            continue

        realized_by_ticker[
            ticker
        ] = (
            realized_by_ticker.get(
                ticker,
                0.0,
            )
            + _safe_float(
                row.get(
                    "realized_pnl_delta"
                )
            )
        )

    attribution = []

    seen = set()

    for position in (
        state.get("positions")
        or []
    ):
        ticker = str(
            position.get(
                "ticker"
            )
            or ""
        ).upper()

        if not ticker:
            continue

        seen.add(ticker)

        attribution.append({
            "ticker":
                ticker,

            "quantity":
                int(
                    position.get(
                        "quantity"
                    )
                    or 0
                ),

            "cost_basis":
                _safe_float(
                    position.get(
                        "cost_basis"
                    )
                ),

            "market_value":
                _safe_float(
                    position.get(
                        "market_value"
                    )
                ),

            "realized_pnl":
                round(
                    realized_by_ticker.get(
                        ticker,
                        0.0,
                    ),
                    2,
                ),

            "unrealized_pnl":
                _safe_float(
                    position.get(
                        "unrealized_pnl"
                    )
                ),

            "total_pnl":
                round(
                    realized_by_ticker.get(
                        ticker,
                        0.0,
                    )
                    + _safe_float(
                        position.get(
                            "unrealized_pnl"
                        )
                    ),
                    2,
                ),
        })

    for ticker, realized in (
        realized_by_ticker.items()
    ):
        if ticker in seen:
            continue

        attribution.append({
            "ticker":
                ticker,

            "quantity":
                0,

            "cost_basis":
                0.0,

            "market_value":
                0.0,

            "realized_pnl":
                round(
                    realized,
                    2,
                ),

            "unrealized_pnl":
                0.0,

            "total_pnl":
                round(
                    realized,
                    2,
                ),
        })

    attribution.sort(
        key=lambda row:
            abs(
                _safe_float(
                    row.get(
                        "total_pnl"
                    )
                )
            ),
        reverse=True,
    )

    return {
        "attribution":
            attribution,

        "ticker_count":
            len(attribution),

        "measurement_only":
            True,

        "paper_mode":
            True,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def case_pipeline_summary(
    case_id: str,
) -> dict[str, Any]:
    qualification = (
        latest_object(
            "qualification_assessment",
            case_id=case_id,
        )
        or {}
    )

    risk = (
        latest_object(
            "risk_authorization",
            case_id=case_id,
        )
        or {}
    )

    watch = (
        latest_object(
            "capital_entry_watch",
            case_id=case_id,
        )
        or {}
    )

    sizing = (
        latest_object(
            "generic_position_sizing",
            case_id=case_id,
        )
        or latest_object(
            "automatic_paper_sizing",
            case_id=case_id,
        )
        or {}
    )

    authorization = (
        latest_object(
            "paper_authorization",
            case_id=case_id,
        )
        or {}
    )

    execution = (
        latest_object(
            "governed_paper_execution",
            case_id=case_id,
        )
        or {}
    )

    thesis = (
        latest_object(
            "generic_thesis_status",
            case_id=case_id,
        )
        or {}
    )

    return {
        "case_id":
            case_id,

        "qualified":
            qualification.get(
                "qualified_buy_candidate"
            )
            is True,

        "risk_decision":
            risk.get(
                "decision"
            ),

        "thesis_status":
            thesis.get(
                "status"
            ),

        "capital_stage":
            watch.get(
                "stage"
            ),

        "sizing_decision":
            sizing.get(
                "decision"
            ),

        "authorization_decision":
            authorization.get(
                "decision"
            ),

        "paper_execution":
            execution.get(
                "execution"
            ),

        "paper_order_created": (
            execution.get(
                "execution"
            )
            ==
            "PAPER_ORDER_CREATED"
        ),

        "trade_execution_permission":
            bool(
                execution.get(
                    "trade_execution_permission"
                )
            ),

        "live_execution":
            bool(
                execution.get(
                    "live_execution"
                )
            ),
    }


def _candidate_case_ids() -> list[str]:
    case_ids = set()

    for row in _rows_by_type(
        "case"
    ):
        case_id = str(
            row.get("case_id")
            or ""
        ).strip()

        if case_id:
            case_ids.add(
                case_id
            )

    for row in _rows_by_type(
        "paper_portfolio_transaction"
    ):
        case_id = str(
            row.get(
                "source_case_id"
            )
            or ""
        ).strip()

        if case_id:
            case_ids.add(
                case_id
            )

    for row in _rows_by_type(
        "governed_paper_execution"
    ):
        case_id = str(
            row.get("case_id")
            or ""
        ).strip()

        if case_id:
            case_ids.add(
                case_id
            )

    return sorted(
        case_ids
    )


def scale_validation_summary(
    case_ids: list[str]
    | None = None,
) -> dict[str, Any]:
    ids = (
        list(case_ids)
        if case_ids is not None
        else _candidate_case_ids()
    )

    cases = [
        case_pipeline_summary(
            case_id
        )
        for case_id in ids
    ]

    capital_stages = Counter(
        row.get(
            "capital_stage"
        )
        or "NONE"
        for row in cases
    )

    risk_decisions = Counter(
        row.get(
            "risk_decision"
        )
        or "NONE"
        for row in cases
    )

    qualified = sum(
        1
        for row in cases
        if row.get(
            "qualified"
        )
    )

    paper_orders = sum(
        1
        for row in cases
        if row.get(
            "paper_order_created"
        )
    )

    safety_violations = [
        {
            "case_id":
                row["case_id"],

            "trade_execution_permission":
                row[
                    "trade_execution_permission"
                ],

            "live_execution":
                row[
                    "live_execution"
                ],
        }
        for row in cases
        if (
            row.get(
                "trade_execution_permission"
            )
            or row.get(
                "live_execution"
            )
        )
    ]

    return {
        "case_count":
            len(cases),

        "qualified_case_count":
            qualified,

        "paper_order_count":
            paper_orders,

        "capital_stage_counts":
            dict(
                capital_stages
            ),

        "risk_decision_counts":
            dict(
                risk_decisions
            ),

        "safety_violation_count":
            len(
                safety_violations
            ),

        "safety_violations":
            safety_violations,

        "cases":
            cases,

        "paper_mode":
            True,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def grok_ab_summary() -> dict[str, Any]:
    rows = _rows_by_type(
        "grok_experiment_scorecard"
    )

    completed = 0

    for row in rows:
        if (
            row.get(
                "status"
            )
            in {
                "COMPLETE",
                "COMPLETED",
            }
            or row.get(
                "completed"
            )
            is True
        ):
            completed += 1

    return {
        "scorecard_count":
            len(rows),

        "completed_pair_count":
            completed,

        "promotion_ready":
            False,

        "automatic_factory_promotion":
            False,

        "capital_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def postmortem_summary() -> dict[str, Any]:
    rows = _rows_by_type(
        "paper_trade_postmortem"
    )

    completed = sum(
        1
        for row in rows
        if row.get(
            "status"
        )
        in {
            "COMPLETE",
            "COMPLETED",
        }
    )

    return {
        "postmortem_count":
            len(rows),

        "completed_postmortem_count":
            completed,

        "automatic_policy_rewrite":
            False,

        "capital_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def safety_audit() -> dict[str, Any]:
    object_types = [
        "capital_entry_watch",
        "generic_position_sizing",
        "automatic_paper_sizing",
        "paper_authorization",
        "governed_paper_execution",
        "paper_portfolio_snapshot",
    ]

    violations = []

    for object_type in (
        object_types
    ):
        for row in _rows_by_type(
            object_type
        ):
            if row.get(
                "live_execution"
            ) is True:
                violations.append({
                    "object_type":
                        object_type,

                    "reason":
                        "LIVE_EXECUTION_TRUE",

                    "id":
                        row.get(
                            "execution_id"
                        )
                        or row.get(
                            "paper_authorization_id"
                        )
                        or row.get(
                            "case_id"
                        ),
                })

            if row.get(
                "trade_execution_permission"
            ) is True:
                violations.append({
                    "object_type":
                        object_type,

                    "reason":
                        "TRADE_EXECUTION_PERMISSION_TRUE",

                    "id":
                        row.get(
                            "execution_id"
                        )
                        or row.get(
                            "paper_authorization_id"
                        )
                        or row.get(
                            "case_id"
                        ),
                })

            if row.get(
                "auto_trade_authority"
            ) is True:
                violations.append({
                    "object_type":
                        object_type,

                    "reason":
                        "AUTO_TRADE_AUTHORITY_TRUE",

                    "id":
                        row.get(
                            "case_id"
                        ),
                })

    return {
        "objects_checked":
            object_types,

        "violation_count":
            len(violations),

        "violations":
            violations,

        "all_current_safety_invariants_pass":
            not violations,

        "paper_mode":
            True,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def build_validation_scorecard(
    case_ids: list[str]
    | None = None,
) -> dict[str, Any]:
    return {
        "policy_version":
            POLICY_VERSION,

        "performance":
            portfolio_performance_summary(),

        "attribution":
            portfolio_attribution(),

        "scale":
            scale_validation_summary(
                case_ids
            ),

        "grok_ab":
            grok_ab_summary(),

        "postmortems":
            postmortem_summary(),

        "safety":
            safety_audit(),

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


# ============================================================
# Batch 8E-H — normalized Grok A/B measurement
# ============================================================

def grok_ab_summary() -> dict[str, Any]:
    legacy = _rows_by_type(
        "grok_experiment_scorecard"
    )

    normalized = _rows_by_type(
        "paper_grok_ab_pair"
    )

    completed_legacy = sum(
        1
        for row in legacy
        if (
            row.get("status")
            in {
                "COMPLETE",
                "COMPLETED",
            }
            or row.get(
                "completed"
            )
            is True
        )
    )

    completed_normalized = sum(
        1
        for row in normalized
        if (
            row.get("status")
            == "COMPLETE"
            and row.get(
                "measurement_complete"
            )
            is True
        )
    )

    completed = (
        completed_legacy
        + completed_normalized
    )

    return {
        "legacy_scorecard_count":
            len(legacy),

        "normalized_pair_count":
            len(normalized),

        "completed_pair_count":
            completed,

        # Empirical results never self-promote Grok.
        "promotion_ready":
            False,

        "automatic_factory_promotion":
            False,

        "capital_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }
