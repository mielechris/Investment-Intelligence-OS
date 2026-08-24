import unittest
from unittest.mock import patch

import market_event_radar as radar


class MarketEventRadarTests(unittest.TestCase):

    def test_default_lanes_cover_original_factory_domains(self):
        lanes = radar.normalize_lanes(None)
        for required in ("policy", "macro", "geopolitics", "commodities", "weather", "ipo"):
            self.assertIn(required, lanes)

    def test_unknown_lane_rejected(self):
        with self.assertRaises(ValueError):
            radar.normalize_lanes(["policy", "not-a-lane"])

    def test_context_wrapper_can_never_be_trade_evidence(self):
        item = radar._context_only(
            {"source": "test", "claim": "event"},
            "policy",
        )
        self.assertTrue(item["context_only"])
        self.assertFalse(item["gap_resolution_eligible"])
        self.assertFalse(item["trade_signal"])
        self.assertFalse(item["paper_order_permission"])
        self.assertFalse(item["trade_execution_permission"])
        self.assertFalse(item["live_execution"])

    @patch("market_event_radar.record_event")
    @patch("market_event_radar.record_object")
    @patch("market_event_radar.ingest_sources")
    def test_radar_is_context_only_and_creates_no_cases(self, ingest, record_object, record_event):
        ingest.return_value = {
            "requested_sources": 1,
            "successful_sources": 1,
            "failed_sources": 0,
            "source_results": [],
            "evidence_items": [
                {
                    "source": "test",
                    "source_type": "official",
                    "evidence_type": "news",
                    "title": "Policy event",
                    "claim": "Policy event",
                    "timestamp": "2026-08-24T19:00:00+00:00",
                    "reliability_score": 0.9,
                }
            ],
        }
        result = radar.run_market_event_radar(["policy", "ipo"])
        self.assertEqual(result["lanes"], ["policy", "ipo"])
        self.assertEqual(result["event_count"], 2)
        self.assertTrue(result["context_only"])
        self.assertFalse(result["auto_case_creation"])
        self.assertFalse(result["gap_resolution_eligible"])
        self.assertFalse(result["trade_signal"])
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])
        for item in result["evidence"]:
            self.assertFalse(item["gap_resolution_eligible"])
            self.assertFalse(item["trade_signal"])

    def test_radar_routes_have_no_execution_or_authorization(self):
        paths = {route.path.lower() for route in radar.router.routes}
        self.assertIn("/opportunities/radar", paths)
        self.assertIn("/opportunities/radar/run", paths)
        self.assertFalse(
            any(
                "paper-authorization" in path
                or "governed-paper-execution" in path
                or "broker" in path
                or "live" in path
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
