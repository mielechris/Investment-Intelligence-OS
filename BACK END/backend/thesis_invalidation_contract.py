from __future__ import annotations

from typing import Any


CONTRACT_VERSION = "MU_THESIS_INVALIDATION_V1"

HARD_INVALIDATION_RULES = (
    "MEMORY_PRICING_BREAK",
    "SUPPLY_DEMAND_REVERSAL",
    "HYPERSCALER_DEMAND_BREAK",
    "EARNINGS_QUALITY_BREAK",
)


def build_mu_invalidation_contract() -> dict[str, Any]:
    """
    Governed MU thesis invalidation contract.

    These are evidence conditions, NOT price stops.

    A thesis may be invalidated while the stock price is high.
    A stock price may fall without the thesis being invalidated.
    """

    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": "MU",
        "rules": [
            {
                "rule_id": "MEMORY_PRICING_BREAK",
                "severity": "HARD",
                "description": (
                    "Independent HBM/server-DRAM/DRAM/NAND "
                    "pricing evidence shows sustained material "
                    "deterioration inconsistent with the thesis."
                ),
                "required_evidence": [
                    "independent_memory_pricing",
                ],
                "price_stop": False,
            },
            {
                "rule_id": "SUPPLY_DEMAND_REVERSAL",
                "severity": "HARD",
                "description": (
                    "Supplier inventories or bit supply rise "
                    "faster than verified underlying demand, "
                    "indicating a material memory-cycle reversal."
                ),
                "required_evidence": [
                    "supplier_inventory",
                    "bit_supply",
                    "verified_end_demand",
                ],
                "price_stop": False,
            },
            {
                "rule_id": "HYPERSCALER_DEMAND_BREAK",
                "severity": "HARD",
                "description": (
                    "Verified hyperscaler/server-OEM evidence "
                    "shows meaningful cancellations, pushouts, "
                    "reduced deployment or materially weaker "
                    "memory demand."
                ),
                "required_evidence": [
                    "hyperscaler_cancellations",
                    "server_activity",
                ],
                "price_stop": False,
            },
            {
                "rule_id": "EARNINGS_QUALITY_BREAK",
                "severity": "HARD",
                "description": (
                    "Evidence shows Micron earnings strength is "
                    "primarily temporary pricing/mix leverage and "
                    "normalized-cycle earnings deteriorate enough "
                    "to break the investment case."
                ),
                "required_evidence": [
                    "forward_eps_revisions",
                    "normalized_cycle_stress",
                    "micron_margin_and_asp",
                ],
                "price_stop": False,
            },
        ],
        "governance": {
            "automatic_execution": False,
            "automatic_sell_order": False,
            "price_only_invalidation_allowed": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
        },
    }


def assess_mu_thesis(
    *,
    memory_pricing_break: bool = False,
    supplier_inventory_rising: bool = False,
    bit_supply_outgrowing_demand: bool = False,
    verified_end_demand_weakening: bool = False,
    hyperscaler_cancellations_material: bool = False,
    server_activity_weakening: bool = False,
    eps_revisions_deteriorating: bool = False,
    normalized_cycle_break: bool = False,
    margin_asp_quality_break: bool = False,
) -> dict[str, Any]:
    """
    Evaluate explicit evidence states against the contract.

    Inputs must come from governed evidence/analysis upstream.
    This function does not fetch, infer, or manufacture them.
    """

    triggered: list[str] = []

    if memory_pricing_break:
        triggered.append(
            "MEMORY_PRICING_BREAK"
        )

    if (
        supplier_inventory_rising
        and bit_supply_outgrowing_demand
        and verified_end_demand_weakening
    ):
        triggered.append(
            "SUPPLY_DEMAND_REVERSAL"
        )

    if (
        hyperscaler_cancellations_material
        and server_activity_weakening
    ):
        triggered.append(
            "HYPERSCALER_DEMAND_BREAK"
        )

    earnings_break_count = sum(
        (
            bool(eps_revisions_deteriorating),
            bool(normalized_cycle_break),
            bool(margin_asp_quality_break),
        )
    )

    # Require at least two independent earnings-quality
    # symptoms before declaring this hard invalidation.
    if earnings_break_count >= 2:
        triggered.append(
            "EARNINGS_QUALITY_BREAK"
        )

    invalidated = bool(triggered)

    return {
        "contract_version": CONTRACT_VERSION,
        "status": (
            "INVALIDATED"
            if invalidated
            else "ACTIVE"
        ),
        "thesis_invalidated": invalidated,
        "triggered_rules": triggered,
        "trigger_count": len(triggered),

        "observed_conditions": {
            "memory_pricing_break":
                memory_pricing_break,
            "supplier_inventory_rising":
                supplier_inventory_rising,
            "bit_supply_outgrowing_demand":
                bit_supply_outgrowing_demand,
            "verified_end_demand_weakening":
                verified_end_demand_weakening,
            "hyperscaler_cancellations_material":
                hyperscaler_cancellations_material,
            "server_activity_weakening":
                server_activity_weakening,
            "eps_revisions_deteriorating":
                eps_revisions_deteriorating,
            "normalized_cycle_break":
                normalized_cycle_break,
            "margin_asp_quality_break":
                margin_asp_quality_break,
        },

        "governance": {
            "automatic_execution": False,
            "automatic_sell_order": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
        },
    }
