from __future__ import annotations

from typing import Any
from uuid import uuid4

from ledger import record_event, record_object, utc_now


WATCH_STATE = "WATCHING_PUBLIC_PRIMARY_SOURCES"


def _fact_map(lane: dict[str, Any]) -> dict[str, bool]:
    return {
        str(row.get("key") or ""): bool(row.get("covered"))
        for row in lane.get("facts") or []
        if isinstance(row, dict)
    }


def assess_demand_quality(
    live_floor: dict[str, Any],
    *,
    direct_channel_inventory: bool = False,
) -> dict[str, Any]:
    """
    Determine whether IIOS can distinguish genuine end consumption
    from precautionary restocking.

    Supplier inventory and downstream demand are not enough by
    themselves. Direct channel/customer inventory is required
    before this analytical question may be considered resolved.
    """

    lanes = live_floor.get("lanes") or {}

    supply = lanes.get("supply_inventory") or {}
    hyper = lanes.get("hyperscaler_demand") or {}

    supply_facts = _fact_map(supply)
    hyper_facts = _fact_map(hyper)

    supplier_inventory_supported = bool(
        supply_facts.get("inventory")
    )

    end_demand_supported = all(
        bool(hyper_facts.get(key))
        for key in (
            "server_activity",
            "backlog",
        )
    )

    direct_channel_inventory = bool(
        direct_channel_inventory
    )

    resolved = (
        supplier_inventory_supported
        and end_demand_supported
        and direct_channel_inventory
    )

    if resolved:
        state = "SATISFIED"
        conclusion = (
            "DIRECT_CHANNEL_AND_SUPPLIER_DATA_AVAILABLE"
        )
    else:
        state = "WATCHING"
        conclusion = (
            "CANNOT_YET_DISTINGUISH_END_CONSUMPTION_"
            "FROM_PRECAUTIONARY_RESTOCKING"
        )

    return {
        "analysis_type":
            "DEMAND_QUALITY_RESTOCKING_ASSESSMENT_V1",
        "state": state,
        "covered": resolved,
        "conclusion": conclusion,
        "supplier_inventory_supported":
            supplier_inventory_supported,
        "end_demand_supported":
            end_demand_supported,
        "direct_channel_inventory_supported":
            direct_channel_inventory,
        "missing_direct_fact": (
            None
            if direct_channel_inventory
            else "channel_inventory"
        ),
        "watch_state": (
            None
            if resolved
            else WATCH_STATE
        ),
        "governance": {
            "inference_allowed": False,
            "may_resolve_primary_fact": False,
            "may_authorize_trade": False,
            "paper_buy_enabled": False,
        },
    }


def build_live_demand_quality(
    case_id: str,
) -> dict[str, Any]:
    import primary_evidence

    floor = primary_evidence.primary_evidence_status(
        case_id
    )

    result = assess_demand_quality(
        floor,
        direct_channel_inventory=False,
    )

    assessment_id = (
        f"demand_quality_{uuid4().hex}"
    )

    payload = {
        **result,
        "demand_quality_assessment_id":
            assessment_id,
        "case_id": case_id,
        "created_at": utc_now(),
        "paper_mode": True,
        "trade_execution_permission": False,
    }

    record_object(
        assessment_id,
        "demand_quality_assessment",
        case_id,
        payload,
    )

    record_event(
        case_id,
        "DEMAND_QUALITY_ASSESSED",
        entity_id=assessment_id,
        payload={
            "state": result["state"],
            "conclusion": result["conclusion"],
            "supplier_inventory_supported":
                result[
                    "supplier_inventory_supported"
                ],
            "end_demand_supported":
                result["end_demand_supported"],
            "direct_channel_inventory_supported":
                result[
                    "direct_channel_inventory_supported"
                ],
            "trade_execution_permission": False,
        },
    )

    return payload


def demand_quality_evidence(
    case_id: str,
) -> list[dict[str, Any]]:
    result = build_live_demand_quality(case_id)

    claim = (
        "Governed demand-quality assessment: "
        f"supplier inventory evidence="
        f"{result['supplier_inventory_supported']}; "
        f"independent server/backlog demand evidence="
        f"{result['end_demand_supported']}; "
        f"direct channel/customer inventory evidence="
        f"{result['direct_channel_inventory_supported']}. "
    )

    if result["state"] == "WATCHING":
        claim += (
            "IIOS cannot currently distinguish genuine "
            "end consumption from precautionary restocking "
            "without direct channel/customer inventory data. "
            "This remains an explicit governed watch "
            "obligation; no inference is allowed."
        )
    else:
        claim += (
            "Direct channel inventory evidence is present, "
            "allowing the demand-quality requirement to be "
            "treated as analytically satisfied."
        )

    return [
        {
            "source":
                "IIOS Governed Demand Quality Watch",
            "source_type": "governed_analysis",
            "evidence_type": "demand_quality_watch",
            "url": "iios://demand-quality-watch",
            "title":
                "End consumption vs restocking assessment",
            "claim": claim,
            "timestamp": result["created_at"],
            "reliability_score": 0.90,
            "analysis_type":
                "DEMAND_QUALITY_RESTOCKING_ASSESSMENT_V1",
            "state": result["state"],
            "watch_state": result["watch_state"],
            "supplier_inventory_supported":
                result[
                    "supplier_inventory_supported"
                ],
            "end_demand_supported":
                result["end_demand_supported"],
            "direct_channel_inventory_supported":
                result[
                    "direct_channel_inventory_supported"
                ],
            "gap_resolution_eligible": False,
            "may_resolve_primary_fact": False,
            "may_authorize_trade": False,
            "paper_buy_enabled": False,
        }
    ]
