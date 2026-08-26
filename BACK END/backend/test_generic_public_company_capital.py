import unittest
from unittest.mock import patch

import generic_public_company_capital as capital


class GenericPublicCompanyCapitalTests(unittest.TestCase):

    def test_required_entry_hits_minimum_reward_risk(self):
        upside = 300.219
        downside = 156.636
        minimum = 1.50

        entry = capital.required_entry_for_reward_risk(
            upside_value=upside,
            downside_value=downside,
            minimum_reward_risk=minimum,
        )

        rr = (
            (upside - entry)
            / (entry - downside)
        )

        self.assertAlmostEqual(
            rr,
            minimum,
            places=6,
        )

    def test_amzn_measurement_waits_for_entry_and_has_no_authority(self):
        quote = {
            "status": "ok",
            "provider": "Yahoo Finance",
            "current_price": 261.06,
            "items": [
                {
                    "timestamp":
                        "2026-08-25T20:00:01+00:00",
                }
            ],
        }

        consensus_record = {
            "primary_evidence_id":
                "primary_evidence_test_consensus",
            "source_name":
                "StockAnalysis analyst forecast aggregation",
        }

        with patch.object(
            capital,
            "get_object",
            return_value={"topic": "Amazon opportunity review"},
        ), patch.object(
            capital,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            capital,
            "_forward_eps",
            return_value=(12.48, consensus_record),
        ), patch.object(
            capital,
            "fetch_market_quote",
            return_value=quote,
        ), patch.object(
            capital,
            "record_object",
        ), patch.object(
            capital,
            "record_event",
        ):

            result = (
                capital
                .build_generic_public_company_stress(
                    "case_test_amzn"
                )
            )

        measurement = result[
            "capital_measurement"
        ]

        self.assertEqual(
            result["model"],
            "GENERIC_PUBLIC_COMPANY_CAPITAL_STRESS_V1",
        )

        self.assertEqual(
            measurement["scenario_decision"],
            "WAIT_FOR_ENTRY",
        )

        self.assertAlmostEqual(
            measurement["reward_risk"],
            0.375,
            places=3,
        )

        self.assertAlmostEqual(
            measurement[
                "maximum_qualifying_entry"
            ],
            214.0692,
            places=3,
        )

        self.assertTrue(
            result["governance"]["measurement_only"]
        )

        self.assertFalse(
            result[
                "governance"
            ]["capital_allocation_allowed"]
        )

        self.assertFalse(
            result[
                "governance"
            ]["position_sizing_allowed"]
        )

        self.assertFalse(
            result["paper_order_permission"]
        )

        self.assertFalse(
            result["trade_execution_permission"]
        )

        self.assertFalse(
            result["live_execution"]
        )


if __name__ == "__main__":
    unittest.main()
