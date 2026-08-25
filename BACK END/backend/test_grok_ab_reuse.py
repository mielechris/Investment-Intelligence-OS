import unittest
from unittest.mock import patch

import grok_ab_reuse as reuse


class GrokABReuseTests(unittest.TestCase):
    def test_validated_context_requires_verified_admitted_and_locked_context(self):
        valid = {
            "grok_social_context_id": "grok_social_1",
            "citation_count": 54,
            "admitted_count": 5,
            "items_by_agent": {"skeptic": [{"claim": "x"}]},
            "qualification_evidence": False,
            "capital_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        with patch.object(reuse, "latest_object", return_value=valid):
            result = reuse.validated_latest_context("case_1")
        self.assertEqual(result["admitted_count"], 5)

        unsafe = {**valid, "capital_authority": True}
        with patch.object(reuse, "latest_object", return_value=unsafe):
            with self.assertRaises(ValueError):
                reuse.validated_latest_context("case_1")

    def test_plan_guarantees_zero_new_xai_search_calls_and_no_execution(self):
        plan = reuse.grok_ab_reuse_plan()
        self.assertEqual(plan["new_xai_search_calls"], 0)
        self.assertTrue(plan["requires_existing_verified_context"])
        self.assertFalse(plan["architecture_promotion_automatic"])
        self.assertFalse(plan["auto_trade_authority"])
        self.assertFalse(plan["paper_order_permission"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])


if __name__ == "__main__":
    unittest.main()
