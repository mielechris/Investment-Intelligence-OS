import unittest

from live_invalidation_mapper import (
    map_invalidation_from_inputs,
)


def record(
    lane,
    fact_key,
    claim,
    source="https://example.com/a",
):
    return {
        "lane": lane,
        "fact_key": fact_key,
        "claim": claim,
        "source_url": source,
        "gap_resolution_eligible": True,
    }


def floor(
    cancellations=False,
    server_activity=True,
):
    return {
        "lanes": {
            "hyperscaler_demand": {
                "facts": [
                    {
                        "key": "cancellations",
                        "covered": cancellations,
                    },
                    {
                        "key": "server_activity",
                        "covered": server_activity,
                    },
                ]
            }
        }
    }


def consensus(
    pct=0.0,
):
    return {
        "verified_revision_history": True,
        "eps_change_pct": pct,
        "direction": (
            "REVISING_DOWN"
            if pct < 0
            else "FLAT"
        ),
    }


def stress():
    return {
        "verified_inputs_complete": True,
    }


def demand_quality(
    state="WATCHING",
):
    return {
        "state": state,
        "conclusion":
            "CANNOT_YET_DISTINGUISH_END_CONSUMPTION_FROM_PRECAUTIONARY_RESTOCKING",
    }


class LiveInvalidationMapperTests(
    unittest.TestCase
):

    def test_current_style_evidence_is_active_with_watches(self):
        records = [
            record(
                "memory_pricing",
                "hbm_pricing",
                "HBM contract prices are rising.",
                "https://trendforce.com/hbm",
            ),
            record(
                "memory_pricing",
                "nand_pricing",
                "NAND contract prices are increasing.",
                "https://trendforce.com/nand",
            ),
            record(
                "memory_pricing",
                "dram_pricing",
                "DRAM ASPs increased materially.",
                "https://micron.com/dram",
            ),
            record(
                "micron_financials",
                "asp_sensitivity",
                "Gross margin improved as ASPs increased.",
                "https://micron.com/q3",
            ),
        ]

        result = map_invalidation_from_inputs(
            records=records,
            floor=floor(
                cancellations=False,
                server_activity=True,
            ),
            consensus_history=consensus(0.0),
            cycle_stress=stress(),
            demand_quality=demand_quality(
                "WATCHING"
            ),
        )

        self.assertEqual(
            result["status"],
            "ACTIVE_WITH_WATCHES",
        )

        self.assertFalse(
            result["thesis_invalidated"]
        )

        self.assertEqual(
            result["rules"][
                "MEMORY_PRICING_BREAK"
            ]["state"],
            "CLEAR",
        )

        self.assertEqual(
            result["rules"][
                "HYPERSCALER_DEMAND_BREAK"
            ]["state"],
            "WATCHING",
        )

    def test_two_category_two_source_pricing_break_breaches(self):
        records = [
            record(
                "memory_pricing",
                "hbm_pricing",
                "HBM pricing declined materially.",
                "https://source-a.com/hbm",
            ),
            record(
                "memory_pricing",
                "dram_pricing",
                "Server DRAM pricing is falling.",
                "https://source-b.com/dram",
            ),
        ]

        result = map_invalidation_from_inputs(
            records=records,
            floor=floor(),
            consensus_history=consensus(),
            cycle_stress=stress(),
            demand_quality=demand_quality(),
        )

        self.assertTrue(
            result["thesis_invalidated"]
        )

        self.assertIn(
            "MEMORY_PRICING_BREAK",
            result["breached_rules"],
        )

    def test_single_negative_pricing_signal_only_watches(self):
        records = [
            record(
                "memory_pricing",
                "hbm_pricing",
                "HBM pricing declined.",
                "https://source-a.com/hbm",
            ),
        ]

        result = map_invalidation_from_inputs(
            records=records,
            floor=floor(),
            consensus_history=consensus(),
            cycle_stress=stress(),
            demand_quality=demand_quality(),
        )

        self.assertFalse(
            result["thesis_invalidated"]
        )

        self.assertEqual(
            result["rules"][
                "MEMORY_PRICING_BREAK"
            ]["state"],
            "WATCHING",
        )

    def test_hyperscaler_unknown_cancellations_stays_watch(self):
        result = map_invalidation_from_inputs(
            records=[],
            floor=floor(
                cancellations=False,
                server_activity=True,
            ),
            consensus_history=consensus(),
            cycle_stress=stress(),
            demand_quality=demand_quality(),
        )

        self.assertEqual(
            result["rules"][
                "HYPERSCALER_DEMAND_BREAK"
            ]["state"],
            "WATCHING",
        )

    def test_earnings_break_requires_two_negative_signals(self):
        records = [
            record(
                "micron_financials",
                "asp_sensitivity",
                "Margins declined because pricing weakened.",
                "https://micron.com/q",
            ),
        ]

        result = map_invalidation_from_inputs(
            records=records,
            floor=floor(),
            consensus_history=consensus(
                -15.0
            ),
            cycle_stress=stress(),
            demand_quality=demand_quality(),
        )

        self.assertTrue(
            result["thesis_invalidated"]
        )

        self.assertIn(
            "EARNINGS_QUALITY_BREAK",
            result["breached_rules"],
        )

    def test_mapper_never_executes(self):
        result = map_invalidation_from_inputs(
            records=[],
            floor=floor(),
            consensus_history=consensus(),
            cycle_stress=stress(),
            demand_quality=demand_quality(),
        )

        self.assertFalse(
            result["governance"][
                "automatic_sell_order"
            ]
        )

        self.assertFalse(
            result["governance"][
                "trade_execution_permission"
            ]
        )


if __name__ == "__main__":
    unittest.main()
