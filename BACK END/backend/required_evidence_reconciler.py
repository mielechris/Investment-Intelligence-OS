from __future__ import annotations

from typing import Any


WATCH_STATE = "WATCHING_PUBLIC_PRIMARY_SOURCES"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("–", "-").split())


FACT_PATTERNS = (
    # Memory pricing
    ("memory_pricing", "hbm_pricing", ("hbm", "price")),
    ("memory_pricing", "dram_pricing", ("dram", "price")),
    ("memory_pricing", "nand_pricing", ("nand", "price")),

    # Supply
    ("supply_inventory", "wafer_starts", ("wafer start",)),
    ("supply_inventory", "bit_shipments", ("bit growth", "bit shipment")),
    ("supply_inventory", "utilization", ("utilization",)),
    ("supply_inventory", "inventory", ("inventory days",)),
    ("supply_inventory", "capacity", ("hbm allocation", "capacity", "supplier capex")),

    # Hyperscaler
    ("hyperscaler_demand", "ai_capex", ("ai-capex", "ai capex")),
    ("hyperscaler_demand", "server_activity", ("deployment", "server shipment")),
    ("hyperscaler_demand", "backlog", ("backlog", "lead-time", "lead time")),
    ("hyperscaler_demand", "cancellations", ("cancellation", "order-cancellation", "pushout")),
    ("hyperscaler_demand", "memory_terms", ("memory-content", "memory content", "binding-commitment", "binding commitment")),

    # Valuation / market
    ("valuation_market", "market_price", ("current mu price",)),
    ("valuation_market", "diluted_shares", ("validated share count", "diluted share count", "diluted shares")),
    ("valuation_market", "consensus", ("consensus revision", "earnings expectations", "forward eps")),
    ("valuation_market", "valuation", ("current valuation", "valuation multiple")),
    ("valuation_market", "portfolio_overlap", ("factor overlap", "portfolio holdings")),

    # Governed analytical context
    ("institutional_context", "analyst_revisions", ("forward eps revisions", "earnings revisions", "estimate revisions")),
    ("cycle_valuation_context", "normalized_cycle_stress", ("normalized-cycle earnings", "normalized cycle earnings", "valuation sensitivity", "lower memory asps", "lower memory asp")),
    ("demand_quality_context", "restocking_discrimination", ("end consumption", "restocking", "channel inventory", "supplier inventory")),

    # Policy
    ("policy", "export_controls", ("export control",)),
    ("policy", "incentives", ("subsidies", "subsidy", "incentive")),
)


def canonical_targets(requirement: str) -> list[dict[str, str]]:
    text = _norm(requirement)
    targets: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for lane, fact_key, patterns in FACT_PATTERNS:
        if any(pattern in text for pattern in patterns):
            key = (lane, fact_key)
            if key not in seen:
                seen.add(key)
                targets.append({"lane": lane, "fact_key": fact_key})

    if "independent" in text and any(x in text for x in ("hbm", "dram", "nand")):
        targets.append({"lane": "memory_pricing", "fact_key": "independent_sources"})

    if any(x in text for x in ("rates", "rate outlook", "interest rate")):
        targets.append({"lane": "macro_context", "fact_key": "rates"})

    if "credit condition" in text or "credit conditions" in text:
        targets.append({"lane": "macro_context", "fact_key": "credit_conditions"})

    # Micron-specific financial requests should map to the already-governed
    # filing and valuation facts instead of becoming new prose scope.
    if "micron" in text and any(
        term in text
        for term in (
            "financial table",
            "gross-margin",
            "gross margin",
            "free cash flow",
            "balance-sheet",
            "balance sheet",
            "consensus estimate",
        )
    ):
        micron_map = (
            ("revenue", ("financial table", "revenue")),
            ("hbm_margin", ("gross-margin", "gross margin")),
            ("capex", ("capex",)),
            ("cash_flow", ("free cash flow",)),
            ("cash", ("balance-sheet", "balance sheet")),
            ("debt", ("balance-sheet", "balance sheet")),
            ("asp_sensitivity", ("asp trend", "realized asp", "margin sensitivity")),
        )

        for fact_key, patterns in micron_map:
            if any(pattern in text for pattern in patterns):
                key = ("micron_financials", fact_key)
                if key not in seen:
                    seen.add(key)
                    targets.append(
                        {
                            "lane": "micron_financials",
                            "fact_key": fact_key,
                        }
                    )

        if any(
            term in text
            for term in (
                "consensus estimate",
                "fy2026",
                "fy2027",
            )
        ):
            key = ("valuation_market", "consensus")
            if key not in seen:
                seen.add(key)
                targets.append(
                    {
                        "lane": "valuation_market",
                        "fact_key": "consensus",
                    }
                )

    # A request for independent confirmation from hyperscalers, server OEMs,
    # and memory competitors is a real source-diversity requirement.
    if "independent confirmation" in text and any(
        term in text
        for term in ("server oem", "competitor", "hyperscaler")
    ):
        key = (
            "external_demand_context",
            "cross_source_corroboration",
        )
        if key not in seen:
            seen.add(key)
            targets.append(
                {
                    "lane": "external_demand_context",
                    "fact_key": "cross_source_corroboration",
                }
            )

        for fact_key in (
            "server_activity",
            "backlog",
            "memory_terms",
            "cancellations",
        ):
            key = ("hyperscaler_demand", fact_key)
            if key not in seen:
                seen.add(key)
                targets.append(
                    {
                        "lane": "hyperscaler_demand",
                        "fact_key": fact_key,
                    }
                )

    return targets


def _fact_state(live_floor: dict[str, Any], lane: str, fact_key: str) -> dict[str, Any]:
    lane_row = (live_floor.get("lanes") or {}).get(lane) or {}
    watch_state = (lane_row.get("evidence_watch") or {}).get("state")

    fact = next(
        (
            row for row in lane_row.get("facts") or []
            if str(row.get("key")) == fact_key
        ),
        None,
    )

    if fact and fact.get("covered"):
        return {"state": "SATISFIED", "covered": True}

    if watch_state == WATCH_STATE:
        return {
            "state": "WATCHING",
            "covered": False,
            "watch_state": watch_state,
        }

    return {"state": "OPEN", "covered": False}


def _external_demand_state(
    live_floor: dict[str, Any],
    packet_items: list[dict[str, Any]],
) -> dict[str, Any]:
    current = [
        item
        for item in packet_items
        if isinstance(item, dict)
        and not item.get("stale")
        and not item.get("missing_fields")
    ]

    blobs = [
        _norm(
            " ".join(
                str(item.get(k) or "")
                for k in ("source", "claim", "title", "url")
            )
        )
        for item in current
    ]

    server_oem = any(
        any(
            host in blob
            for host in (
                "delltechnologies.com",
                "supermicro.com",
                "hpe.com",
            )
        )
        and "ai" in blob
        and any(
            term in blob
            for term in (
                "order",
                "backlog",
                "server revenue",
                "demand",
            )
        )
        for blob in blobs
    )

    memory_peer = any(
        any(
            host in blob
            for host in (
                "skhynix.com",
                "samsung.com",
            )
        )
        and any(
            term in blob
            for term in (
                "ai demand",
                "ai server",
                "hbm",
                "server dram",
            )
        )
        for blob in blobs
    )

    hyper = (
        (live_floor.get("lanes") or {})
        .get("hyperscaler_demand", {})
    )

    hyper_facts = {
        str(row.get("key")): bool(row.get("covered"))
        for row in hyper.get("facts") or []
        if isinstance(row, dict)
    }

    hyperscaler_primary = all(
        hyper_facts.get(key)
        for key in (
            "ai_capex",
            "server_activity",
            "backlog",
        )
    )

    passed = (
        server_oem
        and memory_peer
        and hyperscaler_primary
    )

    return {
        "state": "SATISFIED" if passed else "OPEN",
        "covered": passed,
        "server_oem_primary": server_oem,
        "memory_peer_primary": memory_peer,
        "hyperscaler_primary": hyperscaler_primary,
    }


def _institutional_state(
    packet_items: list[dict[str, Any]],
    fact_key: str,
) -> dict[str, Any]:
    if fact_key != "analyst_revisions":
        return {"state": "OPEN", "covered": False}

    for item in packet_items:
        if not isinstance(item, dict):
            continue

        raw = (
            item.get("raw")
            if isinstance(item.get("raw"), dict)
            else item
        )

        if item.get("stale"):
            continue

        analysis_type = str(
            raw.get("analysis_type")
            or item.get("analysis_type")
            or ""
        )

        # Our own governed time-series comparison is allowed.
        if analysis_type == "GOVERNED_CONSENSUS_REVISION_HISTORY_V1":
            if bool(
                raw.get("verified_revision_history")
                or item.get("verified_revision_history")
            ):
                return {
                    "state": "SATISFIED",
                    "covered": True,
                    "source_type":
                        "GOVERNED_CONSENSUS_REVISION_HISTORY",
                }

        lane = str(
            raw.get("institutional_lane")
            or item.get("institutional_lane")
            or ""
        )

        if lane != "analyst_revisions":
            continue

        details = raw.get("details") or {}

        # Secondary rating/target actions are explicitly NOT
        # a true EPS revision series.
        true_series = bool(
            details.get("true_eps_revision_series")
            or raw.get("true_eps_revision_series")
            or item.get("true_eps_revision_series")
        )

        if true_series:
            return {
                "state": "SATISFIED",
                "covered": True,
                "source_type":
                    "TRUE_EPS_REVISION_SERIES",
            }

    return {
        "state": "OPEN",
        "covered": False,
    }


def _cycle_valuation_state(
    packet_items: list[dict[str, Any]],
    fact_key: str,
) -> dict[str, Any]:
    if fact_key != "normalized_cycle_stress":
        return {"state": "OPEN", "covered": False}

    for item in packet_items:
        if not isinstance(item, dict):
            continue

        raw = (
            item.get("raw")
            if isinstance(item.get("raw"), dict)
            else item
        )

        analysis_type = str(
            raw.get("analysis_type")
            or item.get("analysis_type")
            or ""
        )

        if (
            analysis_type
            != "MU_CYCLE_NORMALIZED_DOWNSIDE_STRESS_V1"
        ):
            continue

        verified = bool(
            raw.get("verified_inputs_complete")
            or item.get("verified_inputs_complete")
        )

        explicit = bool(
            raw.get("assumptions_explicit")
            or item.get("assumptions_explicit")
        )

        may_trade = bool(
            raw.get("may_authorize_trade")
            or item.get("may_authorize_trade")
        )

        may_resolve = bool(
            raw.get("may_resolve_primary_fact")
            or item.get("may_resolve_primary_fact")
        )

        passed = (
            verified
            and explicit
            and not may_trade
            and not may_resolve
        )

        return {
            "state": (
                "SATISFIED"
                if passed
                else "OPEN"
            ),
            "covered": passed,
            "analysis_only": True,
        }

    return {
        "state": "OPEN",
        "covered": False,
    }


def _demand_quality_state(
    packet_items: list[dict[str, Any]],
    fact_key: str,
) -> dict[str, Any]:
    if fact_key != "restocking_discrimination":
        return {
            "state": "OPEN",
            "covered": False,
        }

    for item in packet_items:
        if not isinstance(item, dict):
            continue

        raw = (
            item.get("raw")
            if isinstance(item.get("raw"), dict)
            else item
        )

        analysis_type = str(
            raw.get("analysis_type")
            or item.get("analysis_type")
            or ""
        )

        if (
            analysis_type
            != "DEMAND_QUALITY_RESTOCKING_ASSESSMENT_V1"
        ):
            continue

        state = str(
            raw.get("state")
            or item.get("state")
            or ""
        )

        direct = bool(
            raw.get(
                "direct_channel_inventory_supported"
            )
            or item.get(
                "direct_channel_inventory_supported"
            )
        )

        supplier = bool(
            raw.get("supplier_inventory_supported")
            or item.get("supplier_inventory_supported")
        )

        demand = bool(
            raw.get("end_demand_supported")
            or item.get("end_demand_supported")
        )

        if (
            state == "SATISFIED"
            and direct
            and supplier
            and demand
        ):
            return {
                "state": "SATISFIED",
                "covered": True,
                "analysis_only": True,
            }

        if (
            state == "WATCHING"
            and supplier
            and demand
            and not direct
        ):
            return {
                "state": "WATCHING",
                "covered": False,
                "watch_state":
                    "WATCHING_PUBLIC_PRIMARY_SOURCES",
                "missing_fact":
                    "channel_inventory",
                "analysis_only": True,
            }

    return {
        "state": "OPEN",
        "covered": False,
    }


def _macro_state(packet_items: list[dict[str, Any]], fact_key: str) -> dict[str, Any]:
    current = [
        item for item in packet_items
        if isinstance(item, dict)
        and not item.get("stale")
        and not item.get("missing_fields")
    ]

    blobs = [
        _norm(
            " ".join(
                str(item.get(k) or "")
                for k in ("source", "claim", "title", "url")
            )
        )
        for item in current
    ]

    if fact_key == "rates":
        passed = any(
            ("fred" in blob or "treasury" in blob)
            and any(x in blob for x in ("dgs10", "10-year", "10 year", "yield"))
            for blob in blobs
        )
        return {"state": "SATISFIED" if passed else "OPEN", "covered": passed}

    if fact_key == "credit_conditions":
        passed = any(
            any(
                x in blob
                for x in (
                    "credit spread",
                    "option-adjusted spread",
                    "oas",
                    "baa",
                    "high yield spread",
                    "bamlc0a0cm",
                    "bamlh0a0hym2",
                )
            )
            for blob in blobs
        )
        return {"state": "SATISFIED" if passed else "OPEN", "covered": passed}

    return {"state": "OPEN", "covered": False}



def _generic_company_targets(requirement: str) -> list[dict[str, str]]:
    """Map normal public-company underwriting requests without
    pretending semiconductor-specific contracts apply universally.
    """
    text = _norm(requirement)
    targets: list[dict[str, str]] = []

    def add(lane: str, fact_key: str):
        key = (lane, fact_key)
        if key not in {
            (row["lane"], row["fact_key"])
            for row in targets
        }:
            targets.append(
                {"lane": lane, "fact_key": fact_key}
            )

    if any(
        term in text
        for term in (
            "10-q",
            "10-k",
            "earnings material",
            "revenue",
            "free cash flow",
            "cash flow",
            "capex",
            "depreciation",
            "balance sheet",
            "diluted shares",
            "operating income",
            "margin",
        )
    ):
        add("generic_company_financials", "filing_financials")

    if any(
        term in text
        for term in (
            "current price",
            "volume",
            "volatility",
            "relative strength",
            "market price",
        )
    ):
        add("generic_market_context", "current_market")

    if any(
        term in text
        for term in (
            "valuation",
            "multiple",
            "enterprise value",
            "forward eps",
            "forward revenue",
            "consensus",
        )
    ):
        add("generic_market_context", "valuation_consensus")

    if any(
        term in text
        for term in (
            "short interest",
            "options positioning",
            "put/call",
            "institutional or etf flows",
            "institutional flows",
            "etf flows",
        )
    ):
        add(
            "generic_market_context",
            "market_positioning",
        )

    if any(
        term in text
        for term in (
            "aws",
            "cloud",
            "advertising",
            "retail profitability",
            "customer adoption",
            "bookings",
            "backlog",
            "utilization",
            "pricing",
        )
    ):
        add("generic_operating_context", "operating_kpis")

    if any(
        term in text
        for term in (
            "government documentation",
            "procurement",
            "award",
            "regulatory",
            "antitrust",
            "policy",
        )
    ):
        add("generic_policy_context", "official_policy")

    if any(
        term in text
        for term in (
            "portfolio holdings",
            "portfolio exposure",
            "factor exposure",
            "correlation",
            "drawdown stress",
            "benchmark",
        )
    ):
        add("generic_portfolio_context", "portfolio_state")

    return targets


def _packet_blob(item: dict[str, Any]) -> str:
    raw = (
        item.get("raw")
        if isinstance(item.get("raw"), dict)
        else item
    )
    return _norm(
        " ".join(
            str(raw.get(k) or item.get(k) or "")
            for k in (
                "source",
                "source_type",
                "evidence_type",
                "claim",
                "title",
                "url",
                "form",
            )
        )
    )


def _generic_state(
    packet_items: list[dict[str, Any]],
    lane: str,
    fact_key: str,
) -> dict[str, Any]:
    current = [
        item
        for item in packet_items
        if isinstance(item, dict)
        and not item.get("stale")
        and not item.get("missing_fields")
    ]

    blobs = [_packet_blob(item) for item in current]

    if lane == "generic_company_financials":
        sec_items = [
            blob
            for blob in blobs
            if (
                "sec edgar" in blob
                or "data.sec.gov" in blob
            )
            and any(
                term in blob
                for term in (
                    "10-q",
                    "10-k",
                    "revenue",
                    "operatingincome",
                    "operating income",
                    "cash",
                    "assets",
                    "liabilities",
                    "diluted",
                    "propertyplant",
                    "property plant",
                    "depreciation",
                )
            )
        ]
        passed = len(sec_items) >= 2
        return {
            "state": "SATISFIED" if passed else "OPEN",
            "covered": passed,
            "primary_filing_items": len(sec_items),
        }

    if lane == "generic_market_context":
        if fact_key == "current_market":
            passed = any(
                (
                    "market snapshot" in blob
                    or "market price" in blob
                    or "yahoo finance" in blob
                    or "stooq" in blob
                )
                for blob in blobs
            )
            return {
                "state": "SATISFIED" if passed else "OPEN",
                "covered": passed,
            }

        if fact_key == "market_positioning":
            passed = any(
                any(
                    term in blob
                    for term in (
                        "short interest",
                        "put/call",
                        "open interest",
                        "options positioning",
                        "institutional flows",
                        "etf flows",
                    )
                )
                and any(
                    source in blob
                    for source in (
                        "market_data",
                        "exchange",
                        "research",
                        "nasdaq",
                        "cboe",
                        "finra",
                    )
                )
                for blob in blobs
            )

            return {
                "state": (
                    "SATISFIED"
                    if passed
                    else "OPEN"
                ),
                "covered": passed,
            }

        if fact_key == "valuation_consensus":
            # A price alone cannot prove valuation/consensus.
            passed = any(
                any(
                    term in blob
                    for term in (
                        "forward eps",
                        "consensus revenue",
                        "consensus eps",
                        "enterprise value",
                        "ev/",
                        "p/e",
                        "valuation multiple",
                    )
                )
                and (
                    "official" in blob
                    or "market_data" in blob
                    or "research" in blob
                )
                for blob in blobs
            )
            return {
                "state": "SATISFIED" if passed else "OPEN",
                "covered": passed,
            }

    if lane == "generic_operating_context":
        # News can discover these facts, but cannot resolve the gap.
        primary = [
            blob
            for blob in blobs
            if (
                "amazon investor" in blob
                or "ir.aboutamazon.com" in blob
                or "sec edgar" in blob
                or "data.sec.gov" in blob
            )
            and any(
                term in blob
                for term in (
                    "aws",
                    "advertising",
                    "bookings",
                    "backlog",
                    "utilization",
                    "customer adoption",
                    "segment",
                )
            )
        ]

        if primary:
            return {
                "state": "SATISFIED",
                "covered": True,
                "primary_operating_items": len(primary),
            }

        context = any(
            any(
                term in blob
                for term in (
                    "aws",
                    "advertising",
                    "bookings",
                    "backlog",
                    "customer adoption",
                )
            )
            for blob in blobs
        )

        return {
            "state": (
                "WATCHING"
                if context
                else "OPEN"
            ),
            "covered": False,
            "watch_state": (
                WATCH_STATE
                if context
                else None
            ),
        }

    if lane == "generic_policy_context":
        passed = any(
            any(
                host in blob
                for host in (
                    ".gov",
                    "federalregister.gov",
                    "ftc.gov",
                    "justice.gov",
                )
            )
            for blob in blobs
        )
        return {
            "state": "SATISFIED" if passed else "OPEN",
            "covered": passed,
        }

    if lane == "generic_portfolio_context":
        # Portfolio state may only be resolved by first-party
        # governed portfolio evidence. News, filings, consensus,
        # and agent opinion cannot satisfy this gate.
        governed = []

        for item in current:
            raw = (
                item.get("raw")
                if isinstance(item.get("raw"), dict)
                else item
            )

            source_type = str(
                raw.get("source_type")
                or item.get("source_type")
                or ""
            ).lower()

            evidence_type = str(
                raw.get("evidence_type")
                or item.get("evidence_type")
                or ""
            ).lower()

            fact_key = str(
                raw.get("primary_fact_key")
                or item.get("primary_fact_key")
                or ""
            ).lower()

            source_grade = str(
                raw.get("primary_source_grade")
                or item.get("primary_source_grade")
                or ""
            ).upper()

            blob = _packet_blob(item)

            if (
                source_type == "portfolio_data"
                and evidence_type == "portfolio_snapshot"
                and fact_key == "portfolio_overlap"
                and source_grade == "FIRST_PARTY_GOVERNED"
                and "prospective" in blob
                and "drawdown" in blob
                and "cash" in blob
                and "overlap" in blob
            ):
                governed.append(item)

        passed = bool(governed)

        return {
            "state": "SATISFIED" if passed else "OPEN",
            "covered": passed,
            "governed_portfolio_observations": len(governed),
        }

    return {
        "state": "OPEN",
        "covered": False,
    }


def reconcile_requirement(
    requirement: str,
    live_floor: dict[str, Any],
    packet_items: list[dict[str, Any]],
    *,
    use_legacy_semiconductor: bool = True,
) -> dict[str, Any]:
    if use_legacy_semiconductor:
        targets = canonical_targets(requirement)

        if not targets:
            targets = _generic_company_targets(requirement)

    else:
        # Non-semiconductor companies must not inherit Micron's
        # HBM / DRAM / NAND / wafer / hyperscaler contracts.
        targets = _generic_company_targets(requirement)

        # Preserve genuinely generic governed context already
        # implemented by the legacy reconciler.
        safe_legacy_lanes = {
            "macro_context",
            "institutional_context",
        }

        for target in canonical_targets(requirement):
            if target.get("lane") not in safe_legacy_lanes:
                continue

            key = (
                target.get("lane"),
                target.get("fact_key"),
            )

            existing = {
                (
                    row.get("lane"),
                    row.get("fact_key"),
                )
                for row in targets
            }

            if key not in existing:
                targets.append(target)

    results = []

    for target in targets:
        lane = target["lane"]
        fact_key = target["fact_key"]

        if lane == "macro_context":
            state = _macro_state(packet_items, fact_key)
        elif lane == "external_demand_context":
            state = _external_demand_state(
                live_floor,
                packet_items,
            )
        elif lane == "institutional_context":
            state = _institutional_state(
                packet_items,
                fact_key,
            )
        elif lane == "cycle_valuation_context":
            state = _cycle_valuation_state(
                packet_items,
                fact_key,
            )
        elif lane == "demand_quality_context":
            state = _demand_quality_state(
                packet_items,
                fact_key,
            )
        elif lane.startswith("generic_"):
            state = _generic_state(
                packet_items,
                lane,
                fact_key,
            )
        else:
            state = _fact_state(
                live_floor,
                lane,
                fact_key,
            )

        results.append({**target, **state})

    states = {row["state"] for row in results}

    if not results:
        overall = "UNGOVERNED_NEW_SCOPE"
    elif "OPEN" in states:
        overall = "BLOCKING_OPEN"
    elif "WATCHING" in states:
        overall = "SATISFIED_WITH_WATCH"
    else:
        overall = "SATISFIED"

    return {
        "requirement": requirement,
        "overall": overall,
        "targets": results,
    }


def reconcile_committee(
    committee: dict[str, Any],
    live_floor: dict[str, Any],
    packet_items: list[dict[str, Any]],
) -> dict[str, Any]:
    topic = _norm(committee.get("topic"))

    use_legacy_semiconductor = any(
        token in topic
        for token in (
            "micron",
            "(mu)",
            "mu.us",
        )
    )

    rows = [
        reconcile_requirement(
            req,
            live_floor,
            packet_items,
            use_legacy_semiconductor=(
                use_legacy_semiconductor
            ),
        )
        for req in committee.get("required_evidence") or []
        if str(req).strip()
    ]

    blocking = [
        row for row in rows
        if row["overall"] == "BLOCKING_OPEN"
    ]

    watching = [
        row for row in rows
        if row["overall"] == "SATISFIED_WITH_WATCH"
    ]

    ungoverned = [
        row for row in rows
        if row["overall"] == "UNGOVERNED_NEW_SCOPE"
    ]

    return {
        "reconciliation_profile": (
            "MICRON_SEMICONDUCTOR"
            if use_legacy_semiconductor
            else "GENERIC_PUBLIC_COMPANY"
        ),
        "requirements": rows,
        "blocking_count": len(blocking),
        "watching_count": len(watching),
        "ungoverned_new_scope_count": len(ungoverned),
        "risk_can_ignore_raw_required_evidence": (
            len(blocking) == 0
            and len(ungoverned) == 0
        ),
    }
