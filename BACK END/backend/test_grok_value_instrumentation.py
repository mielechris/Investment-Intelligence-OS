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
    @patch.object(value, "get_object", return_value=None)
    @patch.object(value, "record_object")
    def test_observation_is_measurement_only_and_non_executing(self, record_object, get_object):
        row = value.record_discovery_observation(source="GROK_X", ticker="abc")
        self.assertEqual(row["ticker"], "ABC")
        self.assertTrue(row["first_observation_only"])
        self.assertTrue(row["measurement_only"])
        self.assertFalse(row["qualification_evidence"])
        self.assertFalse(row["trade_signal"])
        self.assertFalse(row["auto_trade_authority"])
        self.assertFalse(row["paper_order_permission"])
        self.assertFalse(row["trade_execution_permission"])
        self.assertFalse(row["live_execution"])
        record_object.assert_called_once()

    @patch.object(value, "get_object", return_value=None)
    @patch.object(value, "record_object")
    def test_observation_cycle_tags_first_seen_without_changing_safety(self, record_object, get_object):
        with value.observation_cycle("cycle_123", "GROK_X_PROBE"):
            row = value.record_discovery_observation(source="GROK_X", ticker="abc")
        self.assertEqual(row["measurement_cycle_id"], "cycle_123")
        self.assertEqual(row["measurement_cycle_phase"], "GROK_X_PROBE")
        self.assertEqual(row["metadata"]["measurement_cycle_id"], "cycle_123")
        self.assertFalse(row["qualification_evidence"])
        self.assertFalse(row["trade_execution_permission"])
        self.assertFalse(row["live_execution"])

    @patch.object(value, "get_object")
    @patch.object(value, "record_object")
    def test_existing_first_seen_observation_is_not_replaced(self, record_object, get_object):
        existing = {
            "discovery_observation_id": "grok_value_first_seen_GROK_X_ABC",
            "source": "GROK_X",
            "ticker": "ABC",
            "observed_at": "2026-01-01T00:00:00+00:00",
        }
        get_object.return_value = existing
        row = value.record_discovery_observation(
            source="GROK_X",
            ticker="ABC",
            observed_at="2026-01-02T00:00:00+00:00",
        )
        self.assertEqual(row, existing)
        record_object.assert_not_called()

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
