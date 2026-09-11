import unittest

from market_baseline_plan import checkpoint_state, monday_plan
from provider_gateway_contract import content_hash


class BaselinePlanTests(unittest.TestCase):
    def setUp(self):
        self.universe = {"symbols": [f"S{i:03}" for i in range(517)]}
        self.calendar = {"calendar": "XNYS", "session": "2026-09-14", "open": "2026-09-14T13:30:00+00:00", "close": "2026-09-14T20:00:00+00:00"}

    def plan(self):
        return monday_plan(self.universe, content_hash(self.universe), self.calendar, content_hash(self.calendar))

    def test_exact_three_bulk_requests_not_three_credits(self):
        value = self.plan()
        self.assertEqual(value["maximum_requests"], 3)
        self.assertIsNone(value["maximum_credits"])
        self.assertEqual([r["target"] for r in value["checkpoints"]], ["2026-09-14T13:30:30+00:00", "2026-09-14T16:30:00+00:00", "2026-09-14T20:00:30+00:00"])
        self.assertTrue(all(r["retry_count"] == 0 for r in value["checkpoints"]))

    def test_missing_or_substituted_independent_pin(self):
        with self.assertRaises(ValueError):
            monday_plan(self.universe, "a" * 64, self.calendar, content_hash(self.calendar))

    def test_not_517_or_duplicate_rejected(self):
        self.universe["symbols"][-1] = self.universe["symbols"][0]
        with self.assertRaises(ValueError):
            self.plan()

    def test_wrong_date_calendar_rejected(self):
        self.calendar["session"] = "2026-09-11"
        with self.assertRaises(ValueError):
            self.plan()

    def test_missed_observation_is_never_backfilled(self):
        row = self.plan()["checkpoints"][0]
        self.assertEqual(checkpoint_state(row, "2026-09-14T13:31:01+00:00"), "MISSED_PARTIAL_SESSION")
        self.assertEqual(checkpoint_state(row, "2026-09-14T13:30:30+00:00"), "DUE_REQUIRES_SEPARATE_AUTHORITY")
        self.assertEqual(checkpoint_state(row, "2026-09-14T13:29:30+00:00"), "WAIT")

    def test_deterministic_plan_and_optional_filter(self):
        self.assertEqual(self.plan(), self.plan())
        value = monday_plan(self.universe, content_hash(self.universe), self.calendar, content_hash(self.calendar), mode="FILTERED")
        self.assertEqual(len(value["symbols"]), 517)
        self.assertEqual(value["checkpoints"][0]["mode"], "FILTERED")
