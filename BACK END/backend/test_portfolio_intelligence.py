import unittest
from unittest.mock import patch

import portfolio_intelligence as portfolio


class PortfolioIntelligenceTests(unittest.TestCase):
    @patch.object(portfolio, "latest_object")
    @patch.object(portfolio, "get_object")
    def test_rank_is_research_only(self, get_object, latest_object):
        get_object.side_effect = lambda case_id: {
            "case_id": case_id,
            "topic": case_id,
            "opportunity_score": 80 if case_id == "case_a" else 60,
        }

        def latest(object_type, case_id=None, **kwargs):
            if object_type == "committee_decision":
                return {"disposition": "WATCH", "confidence": 0.8 if case_id == "case_a" else 0.6}
            if object_type == "qualification_assessment":
                return {"qualified_buy_candidate": case_id == "case_a"}
            if object_type == "portfolio_snapshot":
                return {"overlap": {"combined_overlap_weight_pct": 10 if case_id == "case_a" else 40}}
            return {}

        latest_object.side_effect = latest
        result = portfolio.rank_portfolio_research(["case_a", "case_b"])
        self.assertEqual(result["ranking"][0]["case_id"], "case_a")
        self.assertFalse(result["capital_allocation_allowed"])
        self.assertFalse(result["position_sizing_allowed"])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    @patch.object(portfolio, "latest_object", return_value={"disposition": "NO_TRADE", "confidence": 0.9})
    @patch.object(portfolio, "get_object", return_value={"case_id": "case_x", "topic": "x", "opportunity_score": 100})
    def test_no_trade_case_cannot_rank_as_high_conviction(self, get_object, latest_object):
        row = portfolio.score_case_for_portfolio_research("case_x")
        self.assertLessEqual(row["research_rank_score"], 30.0)
        self.assertEqual(row["ranking_scope"], "RESEARCH_PRIORITY_ONLY")


if __name__ == "__main__":
    unittest.main()
