import unittest
from unittest.mock import patch

import grok_shadow_paper as shadow


class GrokShadowPaperTests(unittest.TestCase):
    def test_arm_state_never_creates_position(self):
        self.assertEqual(shadow._arm_state("NO_TRADE"), "CASH_NO_POSITION")
        self.assertEqual(shadow._arm_state("WATCH"), "WATCH_ONLY_NO_POSITION")

    @patch.object(shadow, "_rows")
    def test_status_remains_measurement_only(self, rows):
        rows.side_effect = lambda object_type: [
            {"differentiated_action": False, "reference_quote_cross_checked": True}
        ] if object_type == "grok_shadow_paper_pair" else []
        out = shadow.shadow_paper_status()
        self.assertEqual(out["pair_count"], 1)
        self.assertEqual(out["crosschecked_reference_pair_count"], 1)
        self.assertEqual(out["actual_paper_orders_created"], 0)
        self.assertFalse(out["arm_specific_pnl_available"])
        self.assertFalse(out["auto_trade_authority"])
        self.assertFalse(out["paper_order_permission"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])

    @patch.object(shadow, "record_object")
    @patch.object(shadow, "fetch_crosschecked_quote")
    @patch.object(shadow, "_resolve_ticker", return_value="ABC")
    @patch.object(shadow, "get_object", return_value=None)
    @patch.object(shadow, "_latest_valid_ab_results")
    def test_enrollment_requires_crosschecked_reference_quote(self, results, get_object, resolve, quote, record):
        results.return_value = [{
            "case_id": "case_1",
            "grok_ab_result_id": "ab_1",
            "comparison": {
                "baseline_disposition": "NO_TRADE",
                "grok_disposition": "NO_TRADE",
                "baseline": {"median_confidence": 0.5},
                "iios_plus_grok": {"median_confidence": 0.6},
            },
        }]
        quote.return_value = {
            "status": "single_source",
            "current_price": 10.0,
            "cross_checked": False,
            "quote_quality": "SINGLE_SOURCE",
            "provider_count": 1,
        }
        out = shadow.enroll_shadow_pairs()
        self.assertEqual(out["enrolled_count"], 0)
        self.assertEqual(out["skipped_count"], 1)
        self.assertEqual(out["skipped"][0]["reason"], "CROSSCHECKED_REFERENCE_QUOTE_UNAVAILABLE")
        record.assert_not_called()

    @patch.object(shadow, "record_object")
    @patch.object(shadow, "fetch_crosschecked_quote")
    @patch.object(shadow, "_resolve_ticker", return_value="ABC")
    @patch.object(shadow, "get_object", return_value=None)
    @patch.object(shadow, "_latest_valid_ab_results")
    def test_crosschecked_reference_quote_is_recorded_without_order(self, results, get_object, resolve, quote, record):
        results.return_value = [{
            "case_id": "case_1",
            "grok_ab_result_id": "ab_1",
            "comparison": {
                "baseline_disposition": "NO_TRADE",
                "grok_disposition": "WATCH",
                "baseline": {"median_confidence": 0.5},
                "iios_plus_grok": {"median_confidence": 0.6},
            },
        }]
        quote.return_value = {
            "status": "ok",
            "current_price": 10.0,
            "provider": "Yahoo Finance",
            "providers": ["CNBC", "Yahoo Finance"],
            "provider_count": 2,
            "cross_checked": True,
            "spread_pct": 0.1,
            "quote_quality": "CROSSCHECKED",
        }
        out = shadow.enroll_shadow_pairs()
        self.assertEqual(out["enrolled_count"], 1)
        pair = out["pairs"][0]
        self.assertTrue(pair["reference_quote_cross_checked"])
        self.assertEqual(pair["baseline_state"], "CASH_NO_POSITION")
        self.assertEqual(pair["grok_state"], "WATCH_ONLY_NO_POSITION")
        self.assertTrue(pair["differentiated_action"])
        self.assertEqual(out["actual_paper_orders_created"], 0)
        self.assertFalse(out["trade_execution_permission"])


if __name__ == "__main__":
    unittest.main()
