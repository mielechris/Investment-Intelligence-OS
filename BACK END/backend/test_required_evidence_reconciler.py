import unittest

from required_evidence_reconciler import canonical_targets


class RequiredEvidenceReconcilerTests(unittest.TestCase):

    def test_cloud_request_maps_to_hyperscaler_facts(self):
        rows = canonical_targets(
            "Cloud and OEM customer inventory, deployment, memory-content, "
            "order-cancellation, lead-time, and binding-commitment data"
        )
        keys = {(r["lane"], r["fact_key"]) for r in rows}
        self.assertIn(("hyperscaler_demand", "server_activity"), keys)
        self.assertIn(("hyperscaler_demand", "cancellations"), keys)
        self.assertIn(("hyperscaler_demand", "memory_terms"), keys)

    def test_composite_request_maps_to_multiple_lanes(self):
        rows = canonical_targets(
            "Current AI-capex outlook, rates and credit conditions, "
            "relevant export controls or subsidies, and portfolio holdings "
            "and factor overlap"
        )
        keys = {(r["lane"], r["fact_key"]) for r in rows}
        self.assertIn(("hyperscaler_demand", "ai_capex"), keys)
        self.assertIn(("macro_context", "rates"), keys)
        self.assertIn(("macro_context", "credit_conditions"), keys)
        self.assertIn(("policy", "export_controls"), keys)
        self.assertIn(("valuation_market", "portfolio_overlap"), keys)


    def test_fred_credit_spread_series_satisfies_credit_conditions(self):
        from required_evidence_reconciler import _macro_state

        items = [
            {
                "source": "Federal Reserve Bank of St. Louis / FRED",
                "title": "BAMLC0A0CM",
                "claim": "BAMLC0A0CM=0.85",
                "url": "https://fred.stlouisfed.org/",
                "stale": False,
                "missing_fields": [],
            }
        ]

        result = _macro_state(items, "credit_conditions")
        self.assertEqual(result["state"], "SATISFIED")
        self.assertTrue(result["covered"])


    def test_governed_watch_is_nonblocking_for_raw_prose(self):
        from required_evidence_reconciler import reconcile_committee

        committee = {
            "required_evidence": [
                "Supplier wafer starts and utilization"
            ]
        }

        floor = {
            "lanes": {
                "supply_inventory": {
                    "facts": [
                        {
                            "key": "wafer_starts",
                            "covered": False,
                        },
                        {
                            "key": "utilization",
                            "covered": True,
                        },
                    ],
                    "evidence_watch": {
                        "state": "WATCHING_PUBLIC_PRIMARY_SOURCES"
                    },
                }
            }
        }

        result = reconcile_committee(
            committee,
            floor,
            [],
        )

        self.assertEqual(result["blocking_count"], 0)
        self.assertEqual(result["watching_count"], 1)
        self.assertEqual(result["ungoverned_new_scope_count"], 0)
        self.assertTrue(
            result["risk_can_ignore_raw_required_evidence"]
        )

    def test_real_open_fact_remains_blocking(self):
        from required_evidence_reconciler import reconcile_committee

        committee = {
            "required_evidence": [
                "Current rates and credit conditions"
            ]
        }

        result = reconcile_committee(
            committee,
            {"lanes": {}},
            [],
        )

        self.assertGreater(result["blocking_count"], 0)
        self.assertFalse(
            result["risk_can_ignore_raw_required_evidence"]
        )

    def test_ungoverned_new_scope_can_never_be_ignored(self):
        from required_evidence_reconciler import reconcile_committee

        committee = {
            "required_evidence": [
                "Verified lunar mining concession economics"
            ]
        }

        result = reconcile_committee(
            committee,
            {"lanes": {}},
            [],
        )

        self.assertEqual(
            result["ungoverned_new_scope_count"],
            1,
        )
        self.assertFalse(
            result["risk_can_ignore_raw_required_evidence"]
        )


    def test_micron_financial_request_maps_to_existing_governed_facts(self):
        from required_evidence_reconciler import canonical_targets

        rows = canonical_targets(
            "Micron quarterly financial tables, gross-margin sensitivity, "
            "capex, free cash flow, balance-sheet data, and FY2026/FY2027 "
            "consensus estimates"
        )

        keys = {(r["lane"], r["fact_key"]) for r in rows}

        self.assertIn(("micron_financials", "hbm_margin"), keys)
        self.assertIn(("micron_financials", "capex"), keys)
        self.assertIn(("micron_financials", "cash_flow"), keys)
        self.assertIn(("micron_financials", "cash"), keys)
        self.assertIn(("micron_financials", "debt"), keys)
        self.assertIn(("valuation_market", "consensus"), keys)

    def test_independent_confirmation_creates_corroboration_target(self):
        from required_evidence_reconciler import canonical_targets

        rows = canonical_targets(
            "Independent confirmation from hyperscalers, server OEMs, "
            "and competitors of AI-server demand and the economic terms "
            "and durability of customer commitments"
        )

        keys = {(r["lane"], r["fact_key"]) for r in rows}

        self.assertIn(
            (
                "external_demand_context",
                "cross_source_corroboration",
            ),
            keys,
        )
        self.assertIn(
            ("hyperscaler_demand", "memory_terms"),
            keys,
        )
        self.assertIn(
            ("hyperscaler_demand", "cancellations"),
            keys,
        )


if __name__ == "__main__":
    unittest.main()
