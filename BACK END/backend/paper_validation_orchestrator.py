from __future__ import annotations

import json
import urllib.error
import urllib.request

from datetime import (
    datetime,
    timezone,
)
from typing import Any
from uuid import uuid4

from ledger import (
    latest_object,
    record_event,
    record_object,
    utc_now,
)

from paper_portfolio_core import (
    record_live_portfolio_snapshot,
)

from paper_portfolio_validation import (
    _candidate_case_ids,
    build_validation_scorecard,
)

from paper_trade_postmortem import (
    build_trade_postmortem,
)


POLICY_VERSION = "paper-validation-orchestrator-v1"

BASE_URL = "http://127.0.0.1:8002"

MIN_SNAPSHOT_INTERVAL_MINUTES = 60


def _parse_time(
    value: Any,
) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def _http_json(
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 1200,
) -> dict[str, Any]:

    body = None

    headers = {
        "Content-Type":
            "application/json",
    }

    if payload is not None:
        body = json.dumps(
            payload
        ).encode("utf-8")

    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            return json.load(
                response
            )

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        return {
            "status": "HTTP_ERROR",
            "http_status": exc.code,
            "error": raw,
        }

    except Exception as exc:
        return {
            "status": "ERROR",
            "error":
                f"{type(exc).__name__}: {exc}",
        }


def record_forward_snapshot_if_due(
    *,
    minimum_interval_minutes: int =
        MIN_SNAPSHOT_INTERVAL_MINUTES,
) -> dict[str, Any]:

    latest = latest_object(
        "paper_portfolio_snapshot",
        case_id="paper_portfolio",
    ) or {}

    last_time = (
        _parse_time(
            latest.get("created_at")
        )
        or _parse_time(
            latest.get("generated_at")
        )
    )

    now = datetime.now(
        timezone.utc
    )

    if last_time is not None:
        age_minutes = (
            now - last_time
        ).total_seconds() / 60.0

        if (
            age_minutes
            < minimum_interval_minutes
        ):
            return {
                "status":
                    "NOT_DUE",

                "age_minutes":
                    round(
                        age_minutes,
                        2,
                    ),

                "minimum_interval_minutes":
                    minimum_interval_minutes,

                "snapshot_recorded":
                    False,

                "paper_mode":
                    True,

                "trade_execution_permission":
                    False,

                "live_execution":
                    False,
            }

    snapshot = (
        record_live_portfolio_snapshot()
    )

    return {
        "status":
            "RECORDED",

        "snapshot_recorded":
            True,

        "paper_portfolio_snapshot_id":
            snapshot.get(
                "paper_portfolio_snapshot_id"
            ),

        "nav":
            snapshot.get("nav"),

        "position_count":
            snapshot.get(
                "position_count"
            ),

        "paper_mode":
            True,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def scan_opportunities(
    *,
    max_candidates: int = 10,
) -> dict[str, Any]:

    return _http_json(
        method="POST",
        path="/opportunities/scan",
        payload={
            "news_limit": 12,
            "timespan": "24h",
            "max_candidates":
                int(max_candidates),
        },
        timeout=300,
    )


def _eligible_candidates(
    scan: dict[str, Any],
) -> list[dict[str, Any]]:

    queue = (
        scan.get("queue")
        or scan.get("candidates")
        or []
    )

    candidates = []

    seen = set()

    for row in queue:
        if not isinstance(
            row,
            dict,
        ):
            continue

        candidate_id = str(
            row.get(
                "opportunity_candidate_id"
            )
            or row.get(
                "candidate_id"
            )
            or ""
        ).strip()

        if not candidate_id:
            continue

        if candidate_id in seen:
            continue

        seen.add(
            candidate_id
        )

        if row.get(
            "promoted_case_id"
        ):
            continue

        eligible = row.get(
            "eligible_for_promotion"
        )

        # Explicit False blocks dispatch.
        if eligible is False:
            continue

        candidates.append(
            row
        )

    return candidates


def dispatch_real_candidates(
    *,
    scan: dict[str, Any],
    max_dispatch: int = 3,
) -> dict[str, Any]:

    candidates = (
        _eligible_candidates(
            scan
        )
    )

    results = []

    for row in candidates[
        :max(
            0,
            int(max_dispatch),
        )
    ]:

        candidate_id = str(
            row.get(
                "opportunity_candidate_id"
            )
            or row.get(
                "candidate_id"
            )
        )

        result = _http_json(
            method="POST",
            path=(
                f"/opportunities/"
                f"{candidate_id}/dispatch"
            ),
            payload={
                "force_research_rerun":
                    False,
            },
            timeout=1200,
        )

        case = (
            result.get("case")
            or {}
        )

        results.append({
            "candidate_id":
                candidate_id,

            "ticker":
                row.get("ticker"),

            "status":
                result.get(
                    "status"
                )
                or (
                    "COMPLETE"
                    if case
                    else "UNKNOWN"
                ),

            "case_id":
                case.get(
                    "case_id"
                )
                or result.get(
                    "case_id"
                ),

            "committee_disposition":
                (
                    result.get(
                        "committee"
                    )
                    or {}
                ).get(
                    "disposition"
                ),

            "paper_order_permission":
                bool(
                    result.get(
                        "paper_order_permission"
                    )
                ),

            "trade_execution_permission":
                bool(
                    result.get(
                        "trade_execution_permission"
                    )
                ),

            "live_execution":
                bool(
                    result.get(
                        "live_execution"
                    )
                ),
        })

    violations = [
        row
        for row in results
        if (
            row[
                "trade_execution_permission"
            ]
            or row[
                "live_execution"
            ]
        )
    ]

    return {
        "requested_dispatches":
            int(max_dispatch),

        "eligible_candidates":
            len(candidates),

        "completed_dispatches":
            len(results),

        "results":
            results,

        "safety_violation_count":
            len(violations),

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def reconcile_closed_trade_postmortems(
) -> dict[str, Any]:

    complete = 0
    open_positions = 0
    blocked = 0

    results = []

    for case_id in (
        _candidate_case_ids()
    ):
        result = (
            build_trade_postmortem(
                case_id
            )
        )

        status = result.get(
            "status"
        )

        if status == "COMPLETE":
            complete += 1

        elif status == "OPEN_POSITION":
            open_positions += 1

        else:
            blocked += 1

        results.append({
            "case_id":
                case_id,

            "status":
                status,

            "ticker":
                result.get(
                    "ticker"
                ),

            "outcome":
                result.get(
                    "outcome"
                ),
        })

    return {
        "completed_postmortems":
            complete,

        "open_positions":
            open_positions,

        "blocked":
            blocked,

        "results":
            results,

        "automatic_policy_rewrite":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def record_grok_ab_pair(
    *,
    case_id: str,
    baseline_result: dict[str, Any],
    grok_result: dict[str, Any],
    measurement_label: str,
) -> dict[str, Any]:

    if (
        not isinstance(
            baseline_result,
            dict,
        )
        or not baseline_result
        or not isinstance(
            grok_result,
            dict,
        )
        or not grok_result
    ):
        return {
            "status":
                "BLOCKED",

            "reason":
                "BOTH_AB_RESULTS_REQUIRED",

            "capital_authority":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        }

    label = str(
        measurement_label
        or ""
    ).strip()

    if not label:
        return {
            "status":
                "BLOCKED",

            "reason":
                "MEASUREMENT_LABEL_REQUIRED",

            "capital_authority":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        }

    pair_id = (
        f"paper_grok_ab_pair_"
        f"{uuid4().hex}"
    )

    baseline_committee = (
        baseline_result.get(
            "committee"
        )
        or {}
    )

    grok_committee = (
        grok_result.get(
            "committee"
        )
        or {}
    )

    pair = {
        "paper_grok_ab_pair_id":
            pair_id,

        "policy_version":
            "paper-grok-ab-v1",

        "status":
            "COMPLETE",

        "case_id":
            case_id,

        "measurement_label":
            label,

        "baseline": {
            "disposition":
                baseline_committee.get(
                    "disposition"
                )
                or baseline_result.get(
                    "disposition"
                ),

            "confidence":
                baseline_committee.get(
                    "confidence"
                )
                or baseline_result.get(
                    "confidence"
                ),

            "paper_order_permission":
                bool(
                    baseline_result.get(
                        "paper_order_permission"
                    )
                ),
        },

        "grok_augmented": {
            "disposition":
                grok_committee.get(
                    "disposition"
                )
                or grok_result.get(
                    "disposition"
                ),

            "confidence":
                grok_committee.get(
                    "confidence"
                )
                or grok_result.get(
                    "confidence"
                ),

            "paper_order_permission":
                bool(
                    grok_result.get(
                        "paper_order_permission"
                    )
                ),
        },

        "measurement_complete":
            True,

        # Measurement cannot promote Grok.
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

        "created_at":
            utc_now(),
    }

    record_object(
        pair_id,
        "paper_grok_ab_pair",
        case_id,
        pair,
    )

    record_event(
        case_id,
        "PAPER_GROK_AB_PAIR_RECORDED",
        entity_id=pair_id,
        payload={
            "measurement_label":
                label,

            "promotion_ready":
                False,

            "capital_authority":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },
    )

    return pair


def run_validation_cycle(
    *,
    scan: bool = False,
    max_candidates: int = 10,
    max_dispatch: int = 0,
) -> dict[str, Any]:

    snapshot = (
        record_forward_snapshot_if_due()
    )

    postmortems = (
        reconcile_closed_trade_postmortems()
    )

    scale = {
        "status":
            "NOT_REQUESTED",
    }

    if scan:
        scan_result = (
            scan_opportunities(
                max_candidates=
                    max_candidates
            )
        )

        scale = (
            dispatch_real_candidates(
                scan=scan_result,
                max_dispatch=
                    max_dispatch,
            )
        )

    scorecard = (
        build_validation_scorecard()
    )

    cycle_id = (
        f"paper_validation_cycle_"
        f"{uuid4().hex}"
    )

    result = {
        "paper_validation_cycle_id":
            cycle_id,

        "policy_version":
            POLICY_VERSION,

        "snapshot":
            snapshot,

        "postmortems":
            postmortems,

        "scale":
            scale,

        "scorecard":
            scorecard,

        "paper_mode":
            True,

        "auto_trade_authority":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,

        "created_at":
            utc_now(),
    }

    record_object(
        cycle_id,
        "paper_validation_cycle",
        "paper_portfolio",
        result,
        topic=
            "PAPER_VALIDATION",
    )

    return result
