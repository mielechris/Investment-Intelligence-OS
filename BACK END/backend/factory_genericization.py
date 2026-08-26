from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from generic_coverage_v2 import COMPANY_PROFILES
from generic_primary_evidence import generic_primary_status
from ledger import get_object, latest_object
from monitoring_engine import _default_sources, configure_profile
from opportunity_acquisition import opportunity_queue
from paper_portfolio_core import build_portfolio_state
from provider_hardening import fetch_market_quote


router = APIRouter()
POLICY_VERSION = "factory-genericization-v1"


def resolve_case_profile(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Unknown case_id",
        )

    monitor = (
        latest_object(
            "monitor_profile",
            case_id=case_id,
        )
        or {}
    )

    ticker = str(
        monitor.get("ticker")
        or case.get("ticker")
        or ""
    ).strip().upper()

    candidate = {}

    candidate_id = str(
        case.get("source_candidate_id")
        or ""
    ).strip()

    if candidate_id:
        candidate = (
            get_object(candidate_id)
            or {}
        )

        if not ticker:
            ticker = str(
                candidate.get("ticker")
                or ""
            ).strip().upper()

    topic = str(
        case.get("topic")
        or ""
    ).strip()

    if not ticker:
        match = re.search(
            r"\(([A-Z][A-Z0-9.\-]{0,9})\)",
            topic,
        )

        if match:
            ticker = match.group(1)

    if ticker.endswith(".US"):
        ticker = ticker[:-3]

    profile = (
        COMPANY_PROFILES.get(ticker)
        or {}
    )

    company = str(
        profile.get("company")
        or candidate.get("company")
        or candidate.get("name")
        or ""
    ).strip()

    if not company and topic:
        company = (
            topic.split("(", 1)[0]
            .replace("opportunity review", "")
            .strip()
        )

    sector = str(
        profile.get("sector")
        or candidate.get("sector")
        or "GENERIC_PUBLIC_COMPANY"
    ).strip()

    return {
        "case_id": case_id,
        "topic": topic,
        "ticker": ticker or None,
        "company": company or ticker or None,
        "sector_profile": sector,
        "is_micron": ticker == "MU",
        "monitoring_enabled":
            monitor.get("enabled") is True,
        "monitor_interval_minutes":
            monitor.get("interval_minutes"),
        "monitor_profile_id":
            monitor.get("monitor_profile_id"),
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def paper_portfolio_truth(
    case_id: str,
) -> dict[str, Any]:
    identity = resolve_case_profile(
        case_id
    )

    state = build_portfolio_state()

    ticker = str(
        identity.get("ticker")
        or ""
    ).upper()

    nav = float(
        state.get("nav")
        or 0.0
    )

    exact_market_value = sum(
        float(
            row.get("market_value")
            or 0.0
        )
        for row in (
            state.get("positions")
            or []
        )
        if str(
            row.get("ticker")
            or ""
        ).upper()
        == ticker
    )

    exact_overlap_pct = (
        exact_market_value
        / nav
        * 100.0
        if nav > 0
        else 0.0
    )

    return {
        "case_id": case_id,
        "ticker": ticker or None,
        "nav": state.get("nav"),
        "cash": state.get("cash"),
        "position_count":
            state.get("position_count"),
        "positions":
            state.get("positions") or [],
        "exact_candidate_overlap_pct":
            round(
                exact_overlap_pct,
                4,
            ),
        "accounting_scope":
            state.get(
                "accounting_scope"
            ),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get(
    "/factory-genericization/{case_id}/profile"
)
def case_profile_route(
    case_id: str,
):
    return resolve_case_profile(
        case_id
    )


@router.get(
    "/factory-genericization/{case_id}/evidence"
)
def case_evidence_route(
    case_id: str,
):
    identity = resolve_case_profile(
        case_id
    )

    if identity["is_micron"]:
        return {
            "mode":
                "MICRON_SPECIALIZED",
            "profile":
                identity,
            "paper_mode":
                True,
            "live_execution":
                False,
        }

    status = generic_primary_status(
        case_id
    )

    return {
        "mode":
            "GENERIC_PUBLIC_COMPANY",
        "profile":
            identity,
        "record_count":
            status.get(
                "record_count"
            ),
        "lane_counts":
            status.get(
                "lane_counts"
            )
            or {},
        "records":
            status.get(
                "records"
            )
            or [],
        "latest_snapshot":
            status.get(
                "latest_snapshot"
            ),
        "paper_mode":
            True,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
    }


@router.get(
    "/factory-genericization/{case_id}/portfolio"
)
def portfolio_truth_route(
    case_id: str,
):
    return paper_portfolio_truth(
        case_id
    )


@router.post(
    "/factory-genericization/arm-monitoring"
)
def arm_existing_monitoring(
    request: dict[str, Any] = Body(
        default={}
    ),
):
    interval = max(
        60,
        int(
            request.get(
                "interval_minutes",
                240,
            )
        ),
    )

    limit = max(
        1,
        min(
            int(
                request.get(
                    "limit",
                    30,
                )
            ),
            100,
        ),
    )

    queue = opportunity_queue(
        limit
    )

    armed = []
    preserved = []
    skipped = []

    for row in queue:
        case_id = str(
            row.get(
                "promoted_case_id"
            )
            or ""
        ).strip()

        if not case_id:
            continue

        try:
            identity = (
                resolve_case_profile(
                    case_id
                )
            )

            ticker = str(
                identity.get("ticker")
                or ""
            ).strip()

            if not ticker:
                skipped.append({
                    "case_id": case_id,
                    "reason":
                        "TICKER_NOT_RESOLVED",
                })
                continue

            existing = (
                latest_object(
                    "monitor_profile",
                    case_id=case_id,
                )
                or {}
            )

            if (
                existing.get("enabled")
                is True
                and str(
                    existing.get(
                        "ticker"
                    )
                    or ""
                ).replace(
                    ".US",
                    "",
                ).upper()
                == ticker.upper()
            ):
                preserved.append({
                    "case_id": case_id,
                    "ticker": ticker,
                })
                continue

            case = (
                get_object(case_id)
                or {}
            )

            topic = str(
                case.get("topic")
                or identity.get("topic")
                or f"{ticker} opportunity review"
            )

            quote = fetch_market_quote(
                ticker
            )

            reference_price = (
                quote.get(
                    "current_price"
                )
                if quote.get(
                    "status"
                )
                == "ok"
                else None
            )

            configured = (
                configure_profile({
                    "case_id":
                        case_id,
                    "enabled":
                        True,
                    "interval_minutes":
                        interval,
                    "source_requests":
                        _default_sources(
                            topic
                        ),
                    "ticker":
                        ticker,
                    "direction":
                        "UNSPECIFIED",
                    "reference_price":
                        reference_price,
                    "analysis_mode":
                        "deterministic",
                })
            )

            armed.append({
                "case_id": case_id,
                "ticker": ticker,
                "monitor_profile_id":
                    configured.get(
                        "monitor_profile_id"
                    ),
            })

        except Exception as exc:
            skipped.append({
                "case_id": case_id,
                "reason":
                    f"{type(exc).__name__}: {exc}",
            })

    return {
        "status":
            "COMPLETE",
        "armed":
            armed,
        "preserved":
            preserved,
        "skipped":
            skipped,
        "armed_count":
            len(armed),
        "preserved_count":
            len(preserved),
        "skipped_count":
            len(skipped),
        "paper_mode":
            True,
        "auto_trade_authority":
            False,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
    }
