from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter

from ledger import (
    get_object,
    latest_object,
    list_objects,
    utc_now,
)
from opportunity_acquisition import (
    opportunity_queue,
)
from paper_portfolio_freeze import (
    build_paper_portfolio_freeze_manifest,
)
from paper_portfolio_validation import (
    _candidate_case_ids,
    build_validation_scorecard,
)


router = APIRouter()


def _ticker(
    case_id: str,
    case: dict[str, Any],
) -> str | None:
    profile = latest_object(
        "monitor_profile",
        case_id=case_id,
    ) or {}

    ticker = str(
        profile.get("ticker")
        or case.get("ticker")
        or ""
    ).strip().upper()

    if not ticker:
        candidate_id = str(
            case.get("source_candidate_id")
            or ""
        )

        if candidate_id:
            candidate = (
                get_object(candidate_id)
                or {}
            )

            ticker = str(
                candidate.get("ticker")
                or ""
            ).strip().upper()

    if ticker.endswith(".US"):
        ticker = ticker[:-3]

    return ticker or None


def _case_row(
    case_id: str,
) -> dict[str, Any]:
    case = (
        get_object(case_id)
        or {}
    )

    committee = (
        latest_object(
            "committee_decision",
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

    qualification = (
        latest_object(
            "qualification_assessment",
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

    agent_count = (
        len(
            list_objects(
                case_id,
                "agent_result",
            )
        )
        + len(
            list_objects(
                case_id,
                "gap_agent_result",
            )
        )
    )

    if (
        execution.get("execution")
        == "PAPER_ORDER_CREATED"
    ):
        stage = "PAPER_PORTFOLIO"

    elif (
        authorization.get("decision")
        == "AUTHORIZED_FOR_PAPER_HANDOFF"
    ):
        stage = "AUTHORIZATION"

    elif (
        sizing.get("decision")
        == "SIZE_READY"
    ):
        stage = "POSITION_SIZING"

    elif watch.get("stage"):
        stage = "CAPITAL"

    elif qualification.get(
        "qualified_buy_candidate"
    ) is True:
        stage = "QUALIFIED"

    elif risk.get("decision"):
        stage = "RISK"

    elif committee.get("disposition"):
        stage = "COMMITTEE"

    elif agent_count:
        stage = "EIGHT_DESKS"

    else:
        stage = "EVIDENCE"

    return {
        "case_id":
            case_id,

        "ticker":
            _ticker(
                case_id,
                case,
            ),

        "topic":
            case.get("topic"),

        "stage":
            stage,

        "agent_count":
            agent_count,

        "committee":
            committee.get(
                "disposition"
            ),

        "committee_confidence":
            committee.get(
                "confidence"
            ),

        "risk":
            risk.get(
                "decision"
            ),

        "qualified":
            qualification.get(
                "qualified_buy_candidate"
            )
            is True,

        "capital":
            watch.get("stage"),

        "sizing":
            sizing.get("decision"),

        "authorization":
            authorization.get(
                "decision"
            ),

        "paper_execution":
            execution.get(
                "execution"
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


@router.get(
    "/factory-room/status"
)
def factory_room_status():
    queue = opportunity_queue(
        20
    )

    intake = [
        row
        for row in queue
        if (
            row.get(
                "eligible_for_promotion"
            )
            is True
            and not row.get(
                "promoted_case_id"
            )
        )
    ]

    cases = [
        _case_row(case_id)
        for case_id
        in _candidate_case_ids()
    ]

    stage_counts = Counter(
        row["stage"]
        for row in cases
    )

    scorecard = (
        build_validation_scorecard()
    )

    manifest = (
        build_paper_portfolio_freeze_manifest(
            scorecard=scorecard
        )
    )

    performance = (
        scorecard.get(
            "performance"
        )
        or {}
    )

    rooms = [
        {
            "key":
                "INTAKE",
            "label":
                "Opportunity Intake",
            "count":
                len(intake),
        },
        {
            "key":
                "EVIDENCE",
            "label":
                "Evidence Acquisition",
            "count":
                stage_counts.get(
                    "EVIDENCE",
                    0,
                ),
        },
        {
            "key":
                "EIGHT_DESKS",
            "label":
                "8 Specialist Desks",
            "count":
                stage_counts.get(
                    "EIGHT_DESKS",
                    0,
                ),
        },
        {
            "key":
                "COMMITTEE",
            "label":
                "Investment Committee",
            "count":
                stage_counts.get(
                    "COMMITTEE",
                    0,
                ),
        },
        {
            "key":
                "RISK",
            "label":
                "Risk Inspection",
            "count":
                stage_counts.get(
                    "RISK",
                    0,
                ),
        },
        {
            "key":
                "CAPITAL",
            "label":
                "Capital Control",
            "count":
                (
                    stage_counts.get(
                        "QUALIFIED",
                        0,
                    )
                    + stage_counts.get(
                        "CAPITAL",
                        0,
                    )
                    + stage_counts.get(
                        "POSITION_SIZING",
                        0,
                    )
                    + stage_counts.get(
                        "AUTHORIZATION",
                        0,
                    )
                ),
        },
        {
            "key":
                "PAPER_PORTFOLIO",
            "label":
                "Paper Portfolio",
            "count":
                stage_counts.get(
                    "PAPER_PORTFOLIO",
                    0,
                ),
        },
    ]

    safety = (
        scorecard.get("safety")
        or {}
    )

    return {
        "generated_at":
            utc_now(),

        "rooms":
            rooms,

        "intake":
            intake,

        "cases":
            cases[-40:],

        "portfolio": {
            "nav":
                performance.get(
                    "current_nav"
                ),

            "cash":
                performance.get(
                    "cash"
                ),

            "positions":
                performance.get(
                    "position_count"
                ),

            "return_pct":
                performance.get(
                    "total_return_pct"
                ),

            "drawdown_pct":
                performance.get(
                    "maximum_drawdown_pct"
                ),
        },

        "validation": {
            "cases":
                (
                    scorecard.get(
                        "scale"
                    )
                    or {}
                ).get(
                    "case_count"
                ),

            "case_target":
                50,

            "paper_orders":
                (
                    scorecard.get(
                        "scale"
                    )
                    or {}
                ).get(
                    "paper_order_count"
                ),

            "paper_order_target":
                10,

            "snapshots":
                performance.get(
                    "snapshot_count"
                ),

            "snapshot_target":
                20,

            "postmortems":
                (
                    scorecard.get(
                        "postmortems"
                    )
                    or {}
                ).get(
                    "completed_postmortem_count"
                ),

            "postmortem_target":
                5,

            "grok_pairs":
                (
                    scorecard.get(
                        "grok_ab"
                    )
                    or {}
                ).get(
                    "completed_pair_count"
                ),

            "grok_target":
                10,

            "structural_ready":
                manifest.get(
                    "structural_freeze_ready"
                ),

            "empirical_ready":
                manifest.get(
                    "empirical_validation_ready"
                ),

            "freeze_blockers":
                manifest.get(
                    "freeze_blockers"
                )
                or [],
        },

        "safety": {
            "violations":
                safety.get(
                    "violation_count"
                ),

            "all_invariants":
                safety.get(
                    "all_current_safety_invariants_pass"
                ),

            "auto_trade_authority":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },

        "paper_mode":
            True,

        "live_execution":
            False,
    }
