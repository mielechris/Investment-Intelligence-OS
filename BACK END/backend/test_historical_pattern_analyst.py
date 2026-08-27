import unittest
from unittest.mock import patch

import historical_pattern_analyst as history


class HistoricalPatternAnalystTests(unittest.TestCase):

    def _case(self):
        return {
            "case_id": "case_current",
            "topic": "Semiconductor demand dislocation",
            "evidence_packet_id": "packet_current",
        }

    def test_no_analogs_is_explicit_unknown_not_invented_history(self):
        with patch.object(history, "get_object", return_value=self._case()), patch.object(
            history,
            "find_historical_analogs",
            return_value={
                "case_id": "case_current",
                "current_regime_tags": ["demand"],
                "analogs": [],
            },
        ):
            result = history.build_historical_pattern_review("case_current")

        self.assertEqual(result["historical_signal"], "INSUFFICIENT_PRECEDENT")
        self.assertEqual(result["disposition"], "NO_TRADE")
        self.assertEqual(result["analog_stats"]["analog_count"], 0)
        self.assertIn("must not be invented", result["view"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_supportive_realized_analogs_can_return_watch_context(self):
        analogs = [
            {
                "case_id": "case_a",
                "similarity": 0.8,
                "historical_outcome_known": True,
                "outcome": "WIN",
                "realized_return_pct": 6.0,
            },
            {
                "case_id": "case_b",
                "similarity": 0.7,
                "historical_outcome_known": True,
                "outcome": "WIN",
                "realized_return_pct": 3.0,
            },
            {
                "case_id": "case_c",
                "similarity": 0.4,
                "historical_outcome_known": True,
                "outcome": "LOSS",
                "realized_return_pct": -1.0,
            },
        ]
        with patch.object(history, "get_object", return_value=self._case()), patch.object(
            history,
            "find_historical_analogs",
            return_value={
                "case_id": "case_current",
                "current_regime_tags": ["demand", "ai_capex"],
                "analogs": analogs,
            },
        ):
            result = history.build_historical_pattern_review("case_current")

        self.assertEqual(result["historical_signal"], "HISTORICAL_SUPPORT")
        self.assertEqual(result["disposition"], "WATCH")
        self.assertEqual(result["analog_stats"]["known_outcome_count"], 3)
        self.assertGreater(result["analog_stats"]["weighted_mean_realized_return_pct"], 0)

    def test_negative_precedent_returns_caution_not_trade_authority(self):
        analogs = [
            {
                "case_id": "case_a",
                "similarity": 0.9,
                "historical_outcome_known": True,
                "outcome": "LOSS",
                "realized_return_pct": -5.0,
            },
            {
                "case_id": "case_b",
                "similarity": 0.6,
                "historical_outcome_known": True,
                "outcome": "LOSS",
                "realized_return_pct": -2.0,
            },
        ]
        with patch.object(history, "get_object", return_value=self._case()), patch.object(
            history,
            "find_historical_analogs",
            return_value={
                "case_id": "case_current",
                "current_regime_tags": ["rates"],
                "analogs": analogs,
            },
        ):
            result = history.build_historical_pattern_review("case_current")

        self.assertEqual(result["historical_signal"], "HISTORICAL_CAUTION")
        self.assertEqual(result["disposition"], "NO_TRADE")
        self.assertFalse(result["auto_trade_authority"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])

    def test_missing_analog_outcome_can_use_governed_paper_postmortem(self):
        row = {
            "case_id": "case_prior",
            "similarity": 0.75,
            "historical_outcome_known": False,
            "outcome": None,
            "realized_return_pct": None,
        }
        with patch.object(
            history,
            "latest_object",
            return_value={"outcome": "WIN", "realized_return_pct": 4.25},
        ):
            enriched = history._enrich_outcome(row)

        self.assertTrue(enriched["historical_outcome_known"])
        self.assertEqual(enriched["outcome"], "WIN")
        self.assertEqual(enriched["realized_return_pct"], 4.25)
        self.assertEqual(enriched["outcome_source"], "IIOS_PAPER_TRADE_POSTMORTEM")


if __name__ == "__main__":
    unittest.main()
