import unittest

import dynamic_agent_factory as factory


class DynamicAgentFactoryTests(unittest.TestCase):
    def test_only_approved_low_risk_judgments_are_eligible(self):
        rows = [
            {"professional_judgment_id": "professional_judgment_good", "human_approved": True, "research_only": True, "restriction_risk": "LOW"},
            {"professional_judgment_id": "professional_judgment_high", "human_approved": True, "research_only": True, "restriction_risk": "HIGH"},
            {"professional_judgment_id": "professional_judgment_unapproved", "human_approved": False, "research_only": True, "restriction_risk": "LOW"},
        ]
        result = factory.eligible_source_judgments(rows)
        self.assertEqual([row["professional_judgment_id"] for row in result], ["professional_judgment_good"])

    def test_proposal_strips_dangerous_permissions_and_is_nonvoting(self):
        source = [{"professional_judgment_id": "professional_judgment_good"}]
        proposal = factory.normalize_agent_proposal(
            {
                "name": "Test Specialist",
                "role": "Research",
                "mission": "Research a narrow topic",
                "permissions": ["read_evidence", "execute_trade", "authorize_capital", "submit_committee_view"],
            },
            interview_id="interview_test",
            source_judgments=source,
        )
        self.assertEqual(set(proposal["permissions"]), {"read_evidence", "submit_committee_view"})
        self.assertFalse(proposal["committee_quorum_member"])
        self.assertFalse(proposal["automatic_committee_injection"])
        self.assertFalse(proposal["auto_trade_authority"])
        self.assertFalse(proposal["position_sizing_permission"])
        self.assertFalse(proposal["paper_order_permission"])
        self.assertFalse(proposal["trade_execution_permission"])
        self.assertFalse(proposal["live_execution"])

    def test_output_fails_closed_to_no_trade(self):
        result = factory.normalize_agent_output({"disposition": "BUY", "confidence": 99, "view": "test"})
        self.assertEqual(result["disposition"], "NO_TRADE")
        self.assertEqual(result["confidence"], 1.0)

    def test_plan_exposes_no_capital_or_execution_authority(self):
        plan = factory.dynamic_agent_plan()
        self.assertTrue(plan["human_approval_required_for_source_judgment"])
        self.assertTrue(plan["human_approval_required_for_agent"])
        self.assertFalse(plan["committee_quorum_member"])
        self.assertFalse(plan["automatic_committee_injection"])
        self.assertFalse(plan["capital_authority"])
        self.assertFalse(plan["position_sizing_permission"])
        self.assertFalse(plan["paper_order_permission"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])


if __name__ == "__main__":
    unittest.main()
