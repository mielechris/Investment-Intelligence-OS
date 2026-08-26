import unittest
from unittest.mock import patch

import generic_public_company_capital as capital


ANCHOR = {
    "generic_capital_valuation_anchor_id":
        "anchor_test_amzn",
    "ticker": "AMZN",
    "anchor_price": 261.06,
    "anchor_forward_eps": 12.48,
    "anchor_forward_pe": 261.06 / 12.48,
    "anchor_source":
        "PRIOR_QUALIFIED_GENERIC_CAPITAL_STRESS",
}


class GenericPublicCompanyCapitalTests(unittest.TestCase):

    def test_required_entry_hits_minimum_reward_risk(self):
        upside = 300.219
        downside = 156.636

        entry = (
            capital.required_entry_for_reward_risk(
                upside_value=upside,
                downside_value=downside,
                minimum_reward_risk=1.50,
            )
        )

        rr = (
            (upside - entry)
            / (entry - downside)
        )

        self.assertAlmostEqual(
            rr,
            1.50,
            places=6,
        )

    def _run_at_price(self, price):
        quote = {
            "status": "ok",
            "provider": "Yahoo Finance",
            "current_price": price,
            "items": [
                {
                    "timestamp":
                        "2026-08-25T20:00:01+00:00",
                }
            ],
        }

        consensus = {
            "primary_evidence_id":
                "primary_evidence_test_consensus",
            "source_name":
                "StockAnalysis analyst forecast aggregation",
        }

        with patch.object(
            capital,
            "get_object",
            return_value={
                "topic":
                    "Amazon opportunity review"
            },
        ), patch.object(
            capital,
            "_ticker_for_case",
            return_value="AMZN",
        ), patch.object(
            capital,
            "_forward_eps",
            return_value=(12.48, consensus),
        ), patch.object(
            capital,
            "fetch_market_quote",
            return_value=quote,
        ), patch.object(
            capital,
            "_get_or_create_valuation_anchor",
            return_value=ANCHOR,
        ), patch.object(
            capital,
            "record_object",
        ), patch.object(
            capital,
            "record_event",
        ):
            return (
                capital
                .build_generic_public_company_stress(
                    "case_test_amzn"
                )
            )

    def test_current_price_waits_for_entry(self):
        result = self._run_at_price(261.06)
        measurement = result[
            "capital_measurement"
        ]

        self.assertEqual(
            result["model"],
            "GENERIC_PUBLIC_COMPANY_CAPITAL_STRESS_V1_1",
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

    def test_frozen_anchor_allows_entry_to_improve(self):
        result = self._run_at_price(214.00)
        measurement = result[
            "capital_measurement"
        ]

        # The reference values must stay anchored even
        # though the market price fell.
        self.assertAlmostEqual(
            result[
                "upside_scenario"
            ]["reference_value"],
            300.219,
            places=3,
        )

        self.assertAlmostEqual(
            result[
                "downside_scenario"
            ]["reference_value"],
            156.636,
            places=3,
        )

        self.assertGreaterEqual(
            measurement["reward_risk"],
            1.50,
        )

        self.assertEqual(
            measurement["scenario_decision"],
            "ENTRY_TEST_PASSES",
        )

        self.assertAlmostEqual(
            measurement[
                "maximum_qualifying_entry"
            ],
            214.0692,
            places=3,
        )

    def test_existing_anchor_is_immutable(self):
        existing = dict(ANCHOR)

        with patch.object(
            capital,
            "latest_object",
            return_value=existing,
        ), patch.object(
            capital,
            "record_object",
        ) as record_object_mock, patch.object(
            capital,
            "record_event",
        ) as record_event_mock:

            result = (
                capital
                ._get_or_create_valuation_anchor(
                    case_id="case_test",
                    ticker="AMZN",
                    current_price=200.00,
                    forward_eps=12.48,
                    consensus_record={},
                )
            )

        self.assertEqual(
            result["anchor_price"],
            261.06,
        )

        record_object_mock.assert_not_called()
        record_event_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
