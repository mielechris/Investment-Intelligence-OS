import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from jesse_scheduler import should_run_daily
from jesse_source_acquisition import normalize_universe
from macro_policy_intelligence import policy_distribution_summary

PT = ZoneInfo("America/Los_Angeles")


class GroupBatch8BTests(unittest.TestCase):
    def test_universe_normalization(self):
        self.assertEqual(normalize_universe(["nvda", "NVDA.US", "MSFT"]), ["NVDA", "MSFT"])

    def test_11am_scheduler_due(self):
        now = datetime(2026, 8, 26, 11, 5, tzinfo=PT)
        self.assertTrue(should_run_daily(None, hour=11, minute=0, now_pt=now))
        self.assertFalse(should_run_daily("2026-08-26", hour=11, minute=0, now_pt=now))

    def test_before_11_not_due(self):
        now = datetime(2026, 8, 26, 10, 59, tzinfo=PT)
        self.assertFalse(should_run_daily(None, hour=11, minute=0, now_pt=now))

    def test_weekend_not_due(self):
        now = datetime(2026, 8, 29, 11, 30, tzinfo=PT)
        self.assertFalse(should_run_daily(None, hour=11, minute=0, now_pt=now))

    def test_fed_probabilities_remain_governed(self):
        result = policy_distribution_summary({"CUT_25": 60, "HOLD": 40})
        self.assertAlmostEqual(sum(result["probabilities"].values()), 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
