import unittest

from requirement_lineage_guard import build_requirement_lineage


class RequirementLineageGuardTests(unittest.TestCase):
    def test_resolved_policy_requirement_is_reopened_when_committee_tightens_same_lane(self):
        prior = [
            {
                "requirement": "Primary-source confirmation of semiconductor incentives, export controls, tariffs, procurement commitments, and permitting outcomes with effective dates and measurable supply-demand transmission.",
                "resolved": True,
            }
        ]
        current = [
            "Final tariff scope, effective dates, implementation guidance, and measurable evidence of supply-chain substitution or memory-market transmission."
        ]
        result = build_requirement_lineage(prior, current)
        self.assertEqual(result["prior_resolved_count"], 1)
        self.assertEqual(result["accepted_resolved_count"], 0)
        self.assertEqual(result["reopened_count"], 1)
        self.assertEqual(result["current_open_count"], 1)
        self.assertEqual(result["rows"][0]["status"], "SUPERSEDED_REOPENED")

    def test_resolved_requirement_stays_closed_when_not_reopened(self):
        prior = [
            {
                "requirement": "Primary-source confirmation of semiconductor incentives, export controls, tariffs, procurement commitments, and permitting outcomes with effective dates and measurable supply-demand transmission.",
                "resolved": True,
            }
        ]
        result = build_requirement_lineage(prior, [])
        self.assertEqual(result["accepted_resolved_count"], 1)
        self.assertEqual(result["reopened_count"], 0)
        self.assertTrue(result["rows"][0]["effective_resolved"])


if __name__ == "__main__":
    unittest.main()
