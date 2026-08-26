from __future__ import annotations

from typing import Any

from paper_portfolio_validation import (
    build_validation_scorecard,
)


FREEZE_VERSION = (
    "paper-portfolio-performance-v1"
)

MIN_SCALE_CASES = 50
MIN_PAPER_ORDERS = 10
MIN_SNAPSHOTS = 20
MIN_POSTMORTEMS = 5
MIN_GROK_AB_PAIRS = 10


def build_paper_portfolio_freeze_manifest(
    *,
    scorecard: dict[str, Any]
    | None = None,
) -> dict[str, Any]:

    scorecard = (
        scorecard
        if scorecard is not None
        else build_validation_scorecard()
    )

    performance = (
        scorecard.get(
            "performance"
        )
        or {}
    )

    scale = (
        scorecard.get(
            "scale"
        )
        or {}
    )

    grok = (
        scorecard.get(
            "grok_ab"
        )
        or {}
    )

    postmortems = (
        scorecard.get(
            "postmortems"
        )
        or {}
    )

    safety = (
        scorecard.get(
            "safety"
        )
        or {}
    )

    checks = {
        "paper_mode_only":
            scorecard.get(
                "paper_mode"
            )
            is True,

        "no_auto_trade_authority":
            scorecard.get(
                "auto_trade_authority"
            )
            is False,

        "no_trade_execution_permission":
            scorecard.get(
                "trade_execution_permission"
            )
            is False,

        "no_live_execution":
            scorecard.get(
                "live_execution"
            )
            is False,

        "safety_audit_clean":
            safety.get(
                "all_current_safety_invariants_pass"
            )
            is True,

        "scale_case_sample":
            int(
                scale.get(
                    "case_count"
                )
                or 0
            )
            >= MIN_SCALE_CASES,

        "paper_order_sample":
            int(
                scale.get(
                    "paper_order_count"
                )
                or 0
            )
            >= MIN_PAPER_ORDERS,

        "portfolio_snapshot_sample":
            int(
                performance.get(
                    "snapshot_count"
                )
                or 0
            )
            >= MIN_SNAPSHOTS,

        "postmortem_sample":
            int(
                postmortems.get(
                    "completed_postmortem_count"
                )
                or 0
            )
            >= MIN_POSTMORTEMS,

        "grok_ab_sample":
            int(
                grok.get(
                    "completed_pair_count"
                )
                or 0
            )
            >= MIN_GROK_AB_PAIRS,
    }

    blockers = [
        name
        for name, passed
        in checks.items()
        if not passed
    ]

    structural_checks = [
        "paper_mode_only",
        "no_auto_trade_authority",
        "no_trade_execution_permission",
        "no_live_execution",
        "safety_audit_clean",
    ]

    structural_ready = all(
        checks[name]
        for name in structural_checks
    )

    empirical_ready = all(
        checks[name]
        for name in checks
        if name not in structural_checks
    )

    frozen = (
        structural_ready
        and empirical_ready
    )

    return {
        "freeze_version":
            FREEZE_VERSION,

        "checks":
            checks,

        "freeze_blockers":
            blockers,

        "structural_freeze_ready":
            structural_ready,

        "empirical_validation_ready":
            empirical_ready,

        "paper_portfolio_v1_frozen":
            frozen,

        "minimum_samples": {
            "scale_cases":
                MIN_SCALE_CASES,

            "paper_orders":
                MIN_PAPER_ORDERS,

            "portfolio_snapshots":
                MIN_SNAPSHOTS,

            "postmortems":
                MIN_POSTMORTEMS,

            "grok_ab_pairs":
                MIN_GROK_AB_PAIRS,
        },

        "measurement_only":
            True,

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }
