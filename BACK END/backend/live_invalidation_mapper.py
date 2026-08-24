from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from ledger import (
    latest_object,
    list_objects,
    record_event,
    record_object,
    utc_now,
)
from thesis_invalidation_contract import (
    assess_mu_thesis,
)


EPS_REVISION_BREAK_PCT = -10.0


def _claims(
    records: list[dict[str, Any]],
    lane: str,
    fact_keys: set[str],
) -> list[dict[str, Any]]:
    return [
        row
        for row in records
        if row.get("lane") == lane
        and row.get("fact_key") in fact_keys
        and row.get("gap_resolution_eligible") is True
    ]


def _source_domain(row: dict[str, Any]) -> str:
    url = str(row.get("source_url") or "")
    domain = urlparse(url).netloc.lower()

    if domain:
        return domain

    return str(
        row.get("source_name") or ""
    ).strip().lower()


def _direction(text: str) -> str:
    """
    Conservative deterministic text classifier.

    This is not an LLM judgment.
    It recognizes only explicit directional wording.
    """

    value = " ".join(
        str(text or "").lower().split()
    )

    negative_patterns = (
        r"\bdecreased\b",
        r"\bdecreasing\b",
        r"\bdeclined\b",
        r"\bdeclining\b",
        r"\bfalling\b",
        r"\bfell\b",
        r"\blower prices\b",
        r"\bprice cuts\b",
        r"\bweaker pricing\b",
        r"\bpricing weakened\b",
        r"\boversupply\b",
    )

    positive_patterns = (
        r"\bincreased\b",
        r"\bincreasing\b",
        r"\brising\b",
        r"\bprice increases\b",
        r"\btight supply\b",
        r"\bvery tight\b",
        r"\bdemand exceeded supply\b",
        r"\bsupply constraints\b",
    )

    negative = any(
        re.search(pattern, value)
        for pattern in negative_patterns
    )

    positive = any(
        re.search(pattern, value)
        for pattern in positive_patterns
    )

    if negative and not positive:
        return "NEGATIVE"

    if positive and not negative:
        return "POSITIVE"

    if positive and negative:
        return "MIXED"

    return "UNKNOWN"


def _fact_covered(
    floor: dict[str, Any],
    lane: str,
    fact_key: str,
) -> bool:
    lane_data = (
        floor.get("lanes") or {}
    ).get(lane) or {}

    for row in lane_data.get("facts") or []:
        if not isinstance(row, dict):
            continue

        if row.get("key") == fact_key:
            return bool(row.get("covered"))

    return False


def _memory_pricing_state(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = _claims(
        records,
        "memory_pricing",
        {
            "hbm_pricing",
            "dram_pricing",
            "nand_pricing",
        },
    )

    fact_directions: dict[str, set[str]] = {}
    negative_sources: set[str] = set()

    for row in rows:
        fact_key = str(
            row.get("fact_key") or ""
        )

        direction = _direction(
            str(row.get("claim") or "")
        )

        fact_directions.setdefault(
            fact_key,
            set(),
        ).add(direction)

        if direction == "NEGATIVE":
            negative_sources.add(
                _source_domain(row)
            )

    negative_facts = {
        key
        for key, directions
        in fact_directions.items()
        if "NEGATIVE" in directions
    }

    positive_facts = {
        key
        for key, directions
        in fact_directions.items()
        if "POSITIVE" in directions
    }

    # Hard breach requires broad deterioration,
    # not one adverse print.
    breached = (
        len(negative_facts) >= 2
        and len(negative_sources) >= 2
    )

    if breached:
        state = "BREACHED"
    elif negative_facts:
        state = "WATCHING"
    elif len(positive_facts) >= 2:
        state = "CLEAR"
    else:
        state = "WATCHING"

    return {
        "state": state,
        "negative_fact_keys":
            sorted(negative_facts),
        "positive_fact_keys":
            sorted(positive_facts),
        "negative_source_count":
            len(negative_sources),
        "record_count": len(rows),
        "breach_boolean": breached,
    }


def _supply_demand_state(
    records: list[dict[str, Any]],
    demand_quality: dict[str, Any],
) -> dict[str, Any]:
    inventory_rows = _claims(
        records,
        "supply_inventory",
        {"inventory"},
    )

    bit_rows = _claims(
        records,
        "supply_inventory",
        {"bit_shipments"},
    )

    inventory_negative = any(
        _direction(
            str(row.get("claim") or "")
        )
        == "NEGATIVE"
        for row in inventory_rows
    )

    # Only explicit supply-over-demand language
    # may satisfy this condition.
    bit_supply_outgrowing_demand = any(
        any(
            phrase in str(
                row.get("claim") or ""
            ).lower()
            for phrase in (
                "supply exceeds demand",
                "supply outgrowing demand",
                "inventory build",
                "excess supply",
                "oversupply",
            )
        )
        for row in bit_rows
    )

    end_demand_weakening = (
        str(
            demand_quality.get("state") or ""
        )
        == "BREACHED"
        or str(
            demand_quality.get("conclusion") or ""
        )
        == "END_DEMAND_WEAKENING"
    )

    breached = (
        inventory_negative
        and bit_supply_outgrowing_demand
        and end_demand_weakening
    )

    if breached:
        state = "BREACHED"
    elif (
        demand_quality.get("state")
        == "SATISFIED"
        and not inventory_negative
        and not bit_supply_outgrowing_demand
    ):
        state = "CLEAR"
    else:
        # Current missing channel inventory lands here.
        state = "WATCHING"

    return {
        "state": state,
        "supplier_inventory_rising":
            inventory_negative,
        "bit_supply_outgrowing_demand":
            bit_supply_outgrowing_demand,
        "verified_end_demand_weakening":
            end_demand_weakening,
        "demand_quality_state":
            demand_quality.get("state"),
        "breach_boolean": breached,
    }


def _hyperscaler_state(
    records: list[dict[str, Any]],
    floor: dict[str, Any],
) -> dict[str, Any]:
    cancellation_rows = _claims(
        records,
        "hyperscaler_demand",
        {"cancellations"},
    )

    server_rows = _claims(
        records,
        "hyperscaler_demand",
        {"server_activity"},
    )

    cancellations_covered = _fact_covered(
        floor,
        "hyperscaler_demand",
        "cancellations",
    )

    server_covered = _fact_covered(
        floor,
        "hyperscaler_demand",
        "server_activity",
    )

    cancellations_material = any(
        any(
            phrase in str(
                row.get("claim") or ""
            ).lower()
            for phrase in (
                "material cancellations",
                "cancelled deployments",
                "canceled deployments",
                "material pushouts",
                "reduced deployment",
            )
        )
        for row in cancellation_rows
    )

    server_activity_weakening = any(
        _direction(
            str(row.get("claim") or "")
        )
        == "NEGATIVE"
        for row in server_rows
    )

    breached = (
        cancellations_material
        and server_activity_weakening
    )

    if breached:
        state = "BREACHED"
    elif (
        cancellations_covered
        and server_covered
        and not cancellations_material
        and not server_activity_weakening
    ):
        state = "CLEAR"
    else:
        # This is the expected current condition because
        # cancellations/pushouts remain an open watch.
        state = "WATCHING"

    return {
        "state": state,
        "cancellations_covered":
            cancellations_covered,
        "server_activity_covered":
            server_covered,
        "hyperscaler_cancellations_material":
            cancellations_material,
        "server_activity_weakening":
            server_activity_weakening,
        "breach_boolean": breached,
    }


def _earnings_quality_state(
    records: list[dict[str, Any]],
    consensus_history: dict[str, Any],
    cycle_stress: dict[str, Any],
) -> dict[str, Any]:
    margin_rows = _claims(
        records,
        "micron_financials",
        {
            "hbm_margin",
            "asp_sensitivity",
        },
    )

    eps_change_pct = (
        consensus_history.get(
            "eps_change_pct"
        )
    )

    eps_revisions_deteriorating = False

    if (
        consensus_history.get(
            "verified_revision_history"
        )
        and eps_change_pct is not None
    ):
        eps_revisions_deteriorating = (
            float(eps_change_pct)
            <= EPS_REVISION_BREAK_PCT
        )

    margin_asp_quality_break = any(
        _direction(
            str(row.get("claim") or "")
        )
        == "NEGATIVE"
        for row in margin_rows
    )

    # The current stress object is a scenario model,
    # not observed deterioration. It cannot itself trigger
    # normalized_cycle_break.
    normalized_cycle_break = bool(
        cycle_stress.get(
            "observed_normalized_cycle_break"
        )
        is True
    )

    break_count = sum(
        (
            eps_revisions_deteriorating,
            normalized_cycle_break,
            margin_asp_quality_break,
        )
    )

    breached = break_count >= 2

    history_valid = bool(
        consensus_history.get(
            "verified_revision_history"
        )
    )

    stress_valid = bool(
        cycle_stress.get(
            "verified_inputs_complete"
        )
    )

    if breached:
        state = "BREACHED"
    elif (
        history_valid
        and stress_valid
        and margin_rows
        and break_count == 0
    ):
        state = "CLEAR"
    else:
        state = "WATCHING"

    return {
        "state": state,
        "eps_revisions_deteriorating":
            eps_revisions_deteriorating,
        "normalized_cycle_break":
            normalized_cycle_break,
        "margin_asp_quality_break":
            margin_asp_quality_break,
        "eps_change_pct":
            eps_change_pct,
        "break_signal_count":
            break_count,
        "breach_boolean": breached,
    }


def map_invalidation_from_inputs(
    *,
    records: list[dict[str, Any]],
    floor: dict[str, Any],
    consensus_history: dict[str, Any],
    cycle_stress: dict[str, Any],
    demand_quality: dict[str, Any],
) -> dict[str, Any]:
    memory = _memory_pricing_state(
        records
    )

    supply = _supply_demand_state(
        records,
        demand_quality,
    )

    hyper = _hyperscaler_state(
        records,
        floor,
    )

    earnings = _earnings_quality_state(
        records,
        consensus_history,
        cycle_stress,
    )

    contract_result = assess_mu_thesis(
        memory_pricing_break=
            memory["breach_boolean"],
        supplier_inventory_rising=
            supply[
                "supplier_inventory_rising"
            ],
        bit_supply_outgrowing_demand=
            supply[
                "bit_supply_outgrowing_demand"
            ],
        verified_end_demand_weakening=
            supply[
                "verified_end_demand_weakening"
            ],
        hyperscaler_cancellations_material=
            hyper[
                "hyperscaler_cancellations_material"
            ],
        server_activity_weakening=
            hyper[
                "server_activity_weakening"
            ],
        eps_revisions_deteriorating=
            earnings[
                "eps_revisions_deteriorating"
            ],
        normalized_cycle_break=
            earnings[
                "normalized_cycle_break"
            ],
        margin_asp_quality_break=
            earnings[
                "margin_asp_quality_break"
            ],
    )

    rules = {
        "MEMORY_PRICING_BREAK": memory,
        "SUPPLY_DEMAND_REVERSAL": supply,
        "HYPERSCALER_DEMAND_BREAK": hyper,
        "EARNINGS_QUALITY_BREAK": earnings,
    }

    breached = [
        rule
        for rule, row in rules.items()
        if row["state"] == "BREACHED"
    ]

    watching = [
        rule
        for rule, row in rules.items()
        if row["state"] == "WATCHING"
    ]

    if breached:
        overall = "INVALIDATED"
    elif watching:
        overall = "ACTIVE_WITH_WATCHES"
    else:
        overall = "ACTIVE_CLEAR"

    return {
        "status": overall,
        "thesis_invalidated":
            bool(breached),
        "breached_rules": breached,
        "watching_rules": watching,
        "rules": rules,
        "contract_assessment":
            contract_result,
        "governance": {
            "deterministic_mapper": True,
            "llm_can_trigger_rule": False,
            "automatic_sell_order": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
        },
    }


def build_live_invalidation_status(
    case_id: str,
) -> dict[str, Any]:
    import primary_evidence

    floor = (
        primary_evidence
        .primary_evidence_status(case_id)
    )

    records = list_objects(
        case_id,
        "primary_evidence_record",
    )

    consensus = latest_object(
        "consensus_revision_history",
        case_id=case_id,
    ) or {}

    stress = latest_object(
        "cycle_valuation_stress",
        case_id=case_id,
    ) or {}

    demand_quality = latest_object(
        "demand_quality_assessment",
        case_id=case_id,
    ) or {}

    result = map_invalidation_from_inputs(
        records=records,
        floor=floor,
        consensus_history=consensus,
        cycle_stress=stress,
        demand_quality=demand_quality,
    )

    status_id = (
        f"thesis_invalidation_status_"
        f"{uuid4().hex}"
    )

    payload = {
        **result,
        "thesis_invalidation_status_id":
            status_id,
        "case_id": case_id,
        "created_at": utc_now(),
        "paper_mode": True,
        "live_execution": False,
    }

    record_object(
        status_id,
        "thesis_invalidation_status",
        case_id,
        payload,
    )

    record_event(
        case_id,
        "THESIS_INVALIDATION_MAPPED",
        entity_id=status_id,
        payload={
            "status": payload["status"],
            "breached_rules":
                payload["breached_rules"],
            "watching_rules":
                payload["watching_rules"],
            "trade_execution_permission":
                False,
        },
    )

    return payload
