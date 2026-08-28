from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from official_sources import fetch_official_web


WATCH_SPECS = (
    {
        "lane": "supply_inventory",
        "fact_key": "wafer_starts",
        "label": "Wafer starts",
        "keywords": [
            "wafer starts",
            "wafer start",
            "wafers per month",
            "monthly wafer output",
        ],
        "sources": [
            (
                "Micron Investor Relations",
                "https://investors.micron.com/quarterly-results",
            ),
            (
                "SK hynix Official Newsroom",
                "https://news.skhynix.com/",
            ),
            (
                "Samsung Global Newsroom",
                "https://news.samsung.com/global/",
            ),
        ],
    },
    {
        "lane": "hyperscaler_demand",
        "fact_key": "cancellations",
        "label": "Cancellations / pushouts",
        "keywords": [
            "cancellation",
            "cancelled",
            "canceled",
            "pushout",
            "push-out",
            "deferral",
            "deferred",
        ],
        "sources": [
            (
                "Microsoft Investor Relations",
                "https://www.microsoft.com/en-us/Investor",
            ),
            (
                "Meta Investor Relations",
                "https://investor.atmeta.com/",
            ),
            (
                "Amazon Investor Relations",
                "https://ir.aboutamazon.com/",
            ),
            (
                "Alphabet Investor Relations",
                "https://abc.xyz/investor/",
            ),
        ],
    },
)


def _contains_number(text: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\b", str(text or "")))


def candidate_qualifies(fact_key: str, text: str) -> bool:
    value = str(text or "").lower()

    if fact_key == "wafer_starts":
        return (
            "wafer" in value
            and any(term in value for term in ("start", "starts", "per month", "monthly"))
            and _contains_number(value)
        )

    if fact_key == "cancellations":
        event = any(
            term in value
            for term in (
                "cancel",
                "cancellation",
                "pushout",
                "push-out",
                "defer",
                "deferral",
            )
        )
        infrastructure = any(
            term in value
            for term in (
                "ai",
                "data center",
                "datacenter",
                "capacity",
                "server",
                "lease",
                "infrastructure",
            )
        )
        return event and infrastructure and _contains_number(value)

    return False


def _fact_is_open(primary_module: Any, case_id: str, lane: str, fact_key: str) -> bool:
    status = primary_module.primary_evidence_status(case_id)
    lane_status = (status.get("lanes") or {}).get(lane) or {}
    for row in lane_status.get("facts") or []:
        if str(row.get("key")) == fact_key:
            return not bool(row.get("covered"))
    return True


def run_watch_cycle(primary_module: Any, case_id: str) -> dict[str, Any]:
    case = primary_module.get_object(case_id)
    if not case:
        raise ValueError(f"Unknown case: {case_id}")

    checked_sources = 0
    candidates_added = 0
    errors: list[str] = []
    watched: list[str] = []

    for spec in WATCH_SPECS:
        lane = str(spec["lane"])
        fact_key = str(spec["fact_key"])

        if not _fact_is_open(primary_module, case_id, lane, fact_key):
            continue

        watched.append(f"{lane}:{fact_key}")

        for source_name, url in spec["sources"]:
            checked_sources += 1
            try:
                items = fetch_official_web(
                    {
                        "url": url,
                        "label": source_name,
                        "keywords": list(spec["keywords"]),
                        "limit": 6,
                        "window_chars": 1200,
                        "evidence_type": "research_watch",
                        "reliability_score": 0.95,
                    }
                )

                for item in items:
                    claim = str(item.get("claim") or "")
                    if not candidate_qualifies(fact_key, claim):
                        continue

                    candidate_id = f"evidence_watch_candidate_{uuid4().hex}"
                    candidate = {
                        "evidence_watch_candidate_id": candidate_id,
                        "case_id": case_id,
                        "lane": lane,
                        "fact_key": fact_key,
                        "fact_label": spec["label"],
                        "source_name": item.get("source") or source_name,
                        "source_url": item.get("url") or url,
                        "claim": claim,
                        "observed_at": item.get("timestamp"),
                        "candidate_only": True,
                        "gap_resolution_eligible": False,
                        "auto_close_allowed": False,
                        "requires_governed_verification": True,
                        "created_at": primary_module.utc_now(),
                    }
                    primary_module.record_object(
                        candidate_id,
                        "evidence_watch_candidate",
                        case_id,
                        candidate,
                        topic=case.get("topic"),
                    )
                    candidates_added += 1

            except Exception as exc:
                errors.append(
                    f"{fact_key} · {source_name}: {type(exc).__name__}: {exc}"
                )

    snapshot_id = f"evidence_watch_snapshot_{uuid4().hex}"
    snapshot = {
        "evidence_watch_snapshot_id": snapshot_id,
        "case_id": case_id,
        "watched_facts": watched,
        "checked_sources": checked_sources,
        "candidates_added": candidates_added,
        "errors": errors,
        "state": "WATCHING_PUBLIC_PRIMARY_SOURCES" if watched else "NO_OPEN_WATCH_FACTS",
        "auto_close_allowed": False,
        "created_at": primary_module.utc_now(),
    }
    primary_module.record_object(
        snapshot_id,
        "evidence_watch_snapshot",
        case_id,
        snapshot,
        topic=case.get("topic"),
    )
    primary_module.record_event(
        case_id,
        "OPEN_EVIDENCE_WATCH_REFRESH",
        entity_id=snapshot_id,
        payload={
            "watched_facts": watched,
            "checked_sources": checked_sources,
            "candidates_added": candidates_added,
        },
    )
    return snapshot


def install_open_evidence_watch(primary_module: Any, monitoring_module: Any) -> None:
    prior_lane_status = primary_module._lane_status
    prior_refresh_profile = monitoring_module.refresh_profile

    def lane_status_with_watch(case_id: str, lane: str, records: list[dict[str, Any]]):
        result = prior_lane_status(case_id, lane, records)
        facts = {
            str(row.get("key")): bool(row.get("covered"))
            for row in result.get("facts") or []
            if isinstance(row, dict)
        }

        watched = [
            spec
            for spec in WATCH_SPECS
            if spec["lane"] == lane and not facts.get(str(spec["fact_key"]))
        ]

        if watched:
            latest = primary_module.latest_object(
                "evidence_watch_snapshot",
                case_id=case_id,
            ) or {}

            result["evidence_watch"] = {
                "state": "WATCHING_PUBLIC_PRIMARY_SOURCES",
                "facts": [
                    {
                        "fact_key": spec["fact_key"],
                        "label": spec["label"],
                        "auto_close_allowed": False,
                    }
                    for spec in watched
                ],
                "last_checked_at": latest.get("created_at"),
                "last_candidates_added": latest.get("candidates_added"),
            }

            labels = ", ".join(str(spec["label"]) for spec in watched)
            base = str(result.get("note") or "").strip()
            suffix = (
                f" AUTO WATCH ACTIVE: {labels}. The scheduler will continue checking "
                "public primary sources. Watch candidates cannot resolve a fact until "
                "they pass governed verification."
            )
            result["note"] = (base + suffix).strip()

        return result

    def refresh_profile_with_evidence_watch(profile: dict[str, Any]):
        result = prior_refresh_profile(profile)
        case_id = str(profile.get("case_id") or "")
        try:
            result["evidence_watch"] = run_watch_cycle(primary_module, case_id)
        except Exception as exc:
            result["evidence_watch"] = {
                "state": "WATCH_ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "auto_close_allowed": False,
            }
        return result

    primary_module._lane_status = lane_status_with_watch
    monitoring_module.refresh_profile = refresh_profile_with_evidence_watch

    # Batch 10D paper-fund portfolio context runs before Deep Watch. That makes the
    # current governed paper book available to the portfolio obligation in the same
    # monitoring cycle, without asking the user to enter holdings manually.
    from paper_fund_portfolio_context_bridge import (
        install_paper_fund_portfolio_context_bridge,
        router as paper_fund_portfolio_context_router,
    )

    install_paper_fund_portfolio_context_bridge(monitoring_module)
    monitoring_module.router.include_router(paper_fund_portfolio_context_router)

    # Deep Watch extends this exact monitor chain. The mapping upgrade keeps the six
    # Committee requirements human-readable while allowing one obligation to watch
    # multiple authoritative primary-evidence lanes when its scope spans them.
    import deep_watch_obligations as deep_watch_module
    from deep_watch_lane_mapping import install_deep_watch_lane_mapping

    install_deep_watch_lane_mapping(deep_watch_module)
    deep_watch_module.install_deep_watch_obligation_engine(primary_module, monitoring_module)
    monitoring_module.router.include_router(deep_watch_module.router)

    # Options are observation-only during Batch 10D. Mounting this read-only surface
    # exposes governed OCC positioning context but provides no contract selection,
    # option order, broker, authorization or live-execution capability.
    from options_shadow_observation import router as options_shadow_router

    monitoring_module.router.include_router(options_shadow_router)
