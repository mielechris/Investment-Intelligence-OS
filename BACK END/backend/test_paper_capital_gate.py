import unittest

from paper_capital_gate import (
    assess_paper_capital,
    required_entry_for_reward_risk,
)


def qualification(
    qualified=True,
):
    return {
        "qualified_buy_candidate": qualified,
        "unmet_requirements":
            [] if qualified else ["committee_watch"],
    }


def risk():
    return {
        "decision": "WATCH_ONLY",
        "triggered_rules": [],
        "required_evidence_reconciliation": {
            "blocking_count": 0,
            "ungoverned_new_scope_count": 0,
        },
        "watch_obligations": [
            {
                "lane": "supply_inventory",
                "fact_key": "wafer_starts",
            },
            {
                "lane": "hyperscaler_demand",
                "fact_key": "cancellations",
            },
            {
                "lane": "demand_quality_context",
                "fact_key":
                    "restocking_discrimination",
            },
        ],
    }


def stress(price=914.44):
    return {
        "baseline": {
            "current_price": price,
        },
        "normalized_cycle": {
            "mid_eps": 58.8,
        },
        "scenarios": [
            {
                "asp_decline_pct": 20.0,
                "earnings_elasticity_to_asp": 2.0,
                "stressed_eps": 44.016,
            }
        ],
        "input_lineage": {
            "quote_origin":
                "GAP_HUNTER_EXACT_QUOTE",
        },
    }


class PaperCapitalGateTests(unittest.TestCase):

    def test_current_mu_setup_waits_for_entry(self):
        result = assess_paper_capital(
            qualification=qualification(),
            risk=risk(),
            stress=stress(),
        )

        self.assertEqual(
            result["decision"],
            "WAIT_FOR_ENTRY",
        )

        self.assertFalse(
            result["paper_order_permission"]
        )

        self.assertEqual(
            result["allowed_notional"],
            0.0,
        )

    def test_better_entry_can_pass_capital_economics(self):
        result = assess_paper_capital(
            qualification=qualification(),
            risk=risk(),
            stress=stress(price=800.0),
        )

        self.assertEqual(
            result["decision"],
            "APPROVED",
        )

        # Approval still cannot execute yet.
        self.assertFalse(
            result["paper_order_permission"]
        )

        self.assertEqual(
            result["allowed_notional"],
            0.0,
        )

    def test_unqualified_case_is_rejected(self):
        result = assess_paper_capital(
            qualification=qualification(False),
            risk=risk(),
            stress=stress(price=800.0),
        )

        self.assertEqual(
            result["decision"],
            "REJECTED",
        )

    def test_ungoverned_scope_rejects(self):
        r = risk()

        r[
            "required_evidence_reconciliation"
        ][
            "ungoverned_new_scope_count"
        ] = 1

        result = assess_paper_capital(
            qualification=qualification(),
            risk=r,
            stress=stress(price=800.0),
        )

        self.assertEqual(
            result["decision"],
            "REJECTED",
        )

    def test_stale_quote_lineage_rejects(self):
        s = stress(price=800.0)

        s["input_lineage"][
            "quote_origin"
        ] = "MONITOR_SNAPSHOT"

        result = assess_paper_capital(
            qualification=qualification(),
            risk=risk(),
            stress=s,
        )

        self.assertEqual(
            result["decision"],
            "REJECTED",
        )

    def test_required_entry_math(self):
        entry = required_entry_for_reward_risk(
            upside_value=1058.4,
            downside_value=660.24,
            minimum_reward_risk=1.5,
        )

        self.assertAlmostEqual(
            entry,
            819.504,
            places=3,
        )


if __name__ == "__main__":
    unittest.main()
