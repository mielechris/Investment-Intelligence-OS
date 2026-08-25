import unittest
from unittest.mock import patch

import grok_value_probe as probe


class GrokValueProbeTests(unittest.TestCase):
    @patch.object(probe, "build_discovery_lead_time_report")
    @patch.object(probe, "build_false_positive_report")
    @patch.object(probe.grok_opportunity_discovery, "revalidate_grok_candidate")
    @patch.object(probe.grok_opportunity_discovery, "discover_grok_opportunities")
    def test_probe_revalidates_without_promoting_or_running_agents(self, discover, revalidate, fp, lead):
        discover.return_value = {
            "nominations": [{
                "grok_opportunity_candidate_id": "grok_opportunity_1",
                "ticker": "ABC",
            }],
            "nominated_count": 1,
            "quarantined_count": 0,
            "grok_usage": {},
        }
        revalidate.return_value = {
            "standard_candidate": {
                "opportunity_candidate_id": "opportunity_1",
                "score": 70,
            },
            "standard_promotion_available": True,
        }
        fp.return_value = {
            "nomination_count": 1,
            "resolved_count": 1,
            "validated_count": 1,
            "rejected_count": 0,
            "false_positive_rate": 0.0,
        }
        lead.return_value = {
            "measurable_pair_count": 0,
            "prospective_pair_count": 0,
            "median_grok_lead_minutes": None,
            "prospective_median_grok_lead_minutes": None,
        }
        out = probe.run_value_probe("test", max_candidates=1)
        self.assertEqual(out["resolved_this_probe"], 1)
        self.assertEqual(out["xai_discovery_batches"], 1)
        self.assertTrue(out["automatic_standard_revalidation"])
        self.assertFalse(out["automatic_case_promotion"])
        self.assertFalse(out["automatic_agent_run"])
        self.assertFalse(out["qualification_evidence"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])


if __name__ == "__main__":
    unittest.main()
