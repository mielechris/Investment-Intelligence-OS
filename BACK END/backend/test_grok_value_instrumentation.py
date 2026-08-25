import unittest
from unittest.mock import patch

import grok_value_instrumentation as value


class FakeOpportunityModule:
    def scan_universe(self, *args, **kwargs):
        return {
            "candidates": [
                {
                    "ticker": "ABC",
                    "opportunity_candidate_id": "opportunity_1",
                    "created_at": "2026-01-01T00:01:00+00:00",
                    "score": 70,
                    "eligible_for_promotion": True,
                }
            ]
        }


class FakeGrokModule:
    def discover_grok_opportunities(self, *args, **kwargs):
        return {
            "nominations": [
                {
                    "ticker": "ABC",
                    "grok_opportunity_candidate_id": "grok_opportunity_1",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "source_count": 2,
                    "advisory_confidence": 0.5,
                }
            ]
        }


class GrokValueInstrumentationTests(unittest.TestCase):
    @patch.object(value, "record_object")
    def test_observation_is_measurement_only_and_non_executing(self, record_object):
        row = value.record_discovery_observation(source="GROK_X", ticker="abc")
        self.assertEqual(row["ticker"], "ABC")
        self.assertTrue(row["measurement_only"])
        self.assertFalse(row["qualification_evidence"])
        self.assertFalse(row["trade_signal"])
        self.assertFalse(row["auto_trade_authority"])
        self.assertFalse(row["paper_order_permission"])
        self.assertFalse(row["trade_execution_permission"])
        self.assertFalse(row["live_execution"])
        record_object.assert_called_once()

    def test_installed_wrappers_record_both_sources(self):
        opportunity = FakeOpportunityModule()
        grok = FakeGrokModule()
        with patch.object(value, "record_discovery_observation") as recorder:
            value.install_grok_value_instrumentation(opportunity, grok)
            opportunity.scan_universe()
            grok.discover_grok_opportunities("test")
        sources = [call.kwargs["source"] for call in recorder.call_args_list]
        self.assertEqual(sources, ["IIOS_NATIVE", "GROK_X"])


if __name__ == "__main__":
    unittest.main()
