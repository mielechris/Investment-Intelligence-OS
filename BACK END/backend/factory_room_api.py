from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from ledger import (
    get_audit,
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


ACTIVITY_WINDOW_SECONDS = 300


def _parse_time(value: Any):
    text = str(value or "").strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    except ValueError:
        return None


def _event_room(
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> str:
    event = str(
        event_type or ""
    ).upper()

    payload = payload or {}

    if any(
        token in event
        for token in (
            "PAPER_EXECUTION",
            "PAPER_ORDER",
        )
    ):
        return "PAPER_PORTFOLIO"

    if any(
        token in event
        for token in (
            "CAPITAL",
            "POSITION_SIZ",
            "AUTHORIZATION",
        )
    ):
        return "CAPITAL"

    if any(
        token in event
        for token in (
            "RISK_",
            "RISK_COMPLETE",
            "RECONCILED",
        )
    ):
        return "RISK"

    if "COMMITTEE" in event:
        return "COMMITTEE"

    if (
        "AGENT_COMPLETE" in event
        or "SPECIALIST" in event
        or "DESK" in event
    ):
        return "EIGHT_DESKS"

    if any(
        token in event
        for token in (
            "EVIDENCE",
            "GAP_PACKET",
            "PRIMARY_",
            "INGEST",
        )
    ):
        return "EVIDENCE"

    if any(
        token in event
        for token in (
            "OPPORTUNITY",
            "CANDIDATE",
            "CASE_CREATED",
        )
    ):
        return "INTAKE"

    return "SYSTEM"


def _live_activity(
    case_ids: list[str],
) -> dict[str, Any]:
    now = datetime.now(
        timezone.utc
    )

    events = []

    for case_id in case_ids:
        audit = get_audit(
            case_id
        )

        for event in (
            audit.get("events")
            or []
        )[-80:]:
            event_at = _parse_time(
                event.get("created_at")
            )

            age_seconds = (
                (now - event_at)
                .total_seconds()
                if event_at
                else None
            )

            room = _event_room(
                event.get("event_type"),
                event.get("payload"),
            )

            events.append({
                **event,
                "room":
                    room,
                "age_seconds":
                    round(
                        age_seconds,
                        2,
                    )
                    if age_seconds
                    is not None
                    else None,
            })

    events.sort(
        key=lambda row:
            str(
                row.get("created_at")
                or ""
            ),
        reverse=True,
    )

    recent = [
        row
        for row in events
        if (
            row.get("age_seconds")
            is not None
            and row[
                "age_seconds"
            ]
            <= ACTIVITY_WINDOW_SECONDS
        )
    ]

    by_room = Counter(
        row["room"]
        for row in recent
    )

    agent_completions = sum(
        1
        for row in recent
        if (
            "AGENT_COMPLETE"
            in str(
                row.get(
                    "event_type"
                )
                or ""
            ).upper()
        )
    )

    committee_completions = sum(
        1
        for row in recent
        if (
            "COMMITTEE_COMPLETE"
            in str(
                row.get(
                    "event_type"
                )
                or ""
            ).upper()
        )
    )

    risk_completions = sum(
        1
        for row in recent
        if (
            "RISK_COMPLETE"
            in str(
                row.get(
                    "event_type"
                )
                or ""
            ).upper()
        )
    )

    latest = (
        events[0]
        if events
        else None
    )

    case_latest = {}

    for row in recent:
        case_id = str(
            row.get("case_id")
            or ""
        )

        if (
            case_id
            and case_id
            not in case_latest
        ):
            case_latest[
                case_id
            ] = row

    return {
        "window_seconds":
            ACTIVITY_WINDOW_SECONDS,

        "recent_event_count":
            len(recent),

        "agent_completions":
            agent_completions,

        "committee_completions":
            committee_completions,

        "risk_completions":
            risk_completions,

        "by_room":
            dict(by_room),

        "latest_event":
            latest,

        "case_latest":
            case_latest,

        "recent_events":
            recent[:40],
    }


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

    case_ids = list(
        _candidate_case_ids()
    )

    activity = _live_activity(
        case_ids
    )

    cases = [
        _case_row(case_id)
        for case_id
        in case_ids
    ]

    for row in cases:
        live = (
            activity.get(
                "case_latest"
            )
            or {}
        ).get(
            row["case_id"]
        )

        row[
            "active_room"
        ] = (
            live.get("room")
            if live
            else None
        )

        row[
            "latest_event"
        ] = (
            live.get(
                "event_type"
            )
            if live
            else None
        )

        row[
            "latest_event_at"
        ] = (
            live.get(
                "created_at"
            )
            if live
            else None
        )

    stage_counts = Counter(
        row["stage"]
        for row in cases
    )

    # The governed-case projection is the authoritative floor inventory. Keep
    # it observable even if the heavier validation/freeze summary experiences
    # a transient failure. Previously an exception here caused Factory
    # Intelligence to collapse a real case ledger into `cases: []`.
    validation_error = None

    try:
        scorecard = (
            build_validation_scorecard()
        )

        manifest = (
            build_paper_portfolio_freeze_manifest(
                scorecard=scorecard
            )
        )
    except Exception as exc:  # noqa: BLE001 - preserve core read-only view
        scorecard = {}
        manifest = {}
        validation_error = {
            "availability":
                "OFFLINE",

            "error_type":
                type(exc).__name__,
        }

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
            "activity_count":
                int(
                    (
                        activity.get(
                            "by_room"
                        )
                        or {}
                    ).get(
                        "INTAKE",
                        0,
                    )
                ),
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
            "activity_count":
                int(
                    (
                        activity.get(
                            "by_room"
                        )
                        or {}
                    ).get(
                        "EVIDENCE",
                        0,
                    )
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
            "activity_count":
                int(
                    (
                        activity.get(
                            "by_room"
                        )
                        or {}
                    ).get(
                        "EIGHT_DESKS",
                        0,
                    )
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
            "activity_count":
                int(
                    (
                        activity.get(
                            "by_room"
                        )
                        or {}
                    ).get(
                        "COMMITTEE",
                        0,
                    )
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
            "activity_count":
                int(
                    (
                        activity.get(
                            "by_room"
                        )
                        or {}
                    ).get(
                        "RISK",
                        0,
                    )
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
            "activity_count":
                int(
                    (
                        activity.get(
                            "by_room"
                        )
                        or {}
                    ).get(
                        "CAPITAL",
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
            "activity_count":
                int(
                    (
                        activity.get(
                            "by_room"
                        )
                        or {}
                    ).get(
                        "PAPER_PORTFOLIO",
                        0,
                    )
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

        "activity":
            activity,

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
            "availability":
                (
                    "OFFLINE"
                    if validation_error
                    else "AVAILABLE"
                ),

            "error_type":
                (
                    validation_error.get(
                        "error_type"
                    )
                    if validation_error
                    else None
                ),

            "case_projection_available":
                True,

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
