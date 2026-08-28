import unittest
from unittest.mock import patch

import options_shadow_observation as shadow


class OptionsShadowObservationTests(unittest.TestCase):
    @patch.object(shadow, "latest_object")
    @patch.object(shadow, "list_objects")
    @patch.object(shadow, "resolve_case_profile")
    @patch.object(shadow, "get_object")
    def test_shadow_status_is_read_only_and_uses_governed_occ_context(
        self,
        get_object,
        resolve_case_profile,
        list_objects,
        latest_object,
    ):
        get_object.return_value = {"case_id": "case_mu", "topic": "Micron"}
        resolve_case_profile.return_value = {"ticker": "MU", "company": "Micron Technology"}
        list_objects.return_value = [
            {
                "primary_evidence_id": "e1",
                "lane": "valuation_market",
                "fact_key": "options",
                "gap_resolution_eligible": True,
                "source_name": "OCC Daily Open Interest",
                "source_url": "https://marketdata.theocc.com/example",
                "source_grade": "HARD_MARKET_DATA",
                "claim": "MU call OI=100; put OI=80",
                "observed_at": "2026-08-27",
                "evidence_type": "options",
            },
            {
                "primary_evidence_id": "e2",
                "lane": "valuation_market",
                "fact_key": "short_interest",
                "gap_resolution_eligible": True,
            },
        ]
        latest_object.return_value = {}

        result = shadow.build_options_shadow_status("case_mu")

        self.assertEqual(result["mode"], "SHADOW_OBSERVATION_ONLY")
        self.assertEqual(result["observation_count"], 1)
        self.assertTrue(result["batch10d"]["shadow_observation_enabled"])
        self.assertFalse(result["batch10d"]["options_paper_orders_enabled"])
        self.assertFalse(result["option_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_initial_options_scope_excludes_undefined_risk_and_0dte(self):
        with patch.object(shadow, "get_object", return_value={"case_id": "case_x"}), \
             patch.object(shadow, "resolve_case_profile", return_value={"ticker": "XYZ"}), \
             patch.object(shadow, "list_objects", return_value=[]), \
             patch.object(shadow, "latest_object", return_value={}):
            result = shadow.build_options_shadow_status("case_x")

        prohibited = set(result["batch10e_gate"]["prohibited_initial_scope"])
        self.assertIn("NAKED_SHORT_CALL", prohibited)
        self.assertIn("NAKED_SHORT_PUT", prohibited)
        self.assertIn("0DTE", prohibited)
        self.assertIn("LIVE_OPTIONS_EXECUTION", prohibited)

    def test_routes_do_not_expose_order_or_execution_actions(self):
        paths = {route.path.lower() for route in shadow.router.routes}
        self.assertIn("/options-shadow/plan", paths)
        self.assertIn("/options-shadow/{case_id}/status", paths)
        self.assertFalse(any("order" in path or "execute" in path or "broker" in path for path in paths))


if __name__ == "__main__":
    unittest.main()
