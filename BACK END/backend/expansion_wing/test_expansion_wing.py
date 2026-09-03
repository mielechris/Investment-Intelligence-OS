from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from expansion_wing.judgment import JudgmentPrinciple, promote_status
from expansion_wing.interviews import InterviewIntake
from expansion_wing.models import Book, Eligibility
from expansion_wing.opportunities import create_passport
from expansion_wing.operations import owner_report
from expansion_wing.pattern_lab import PointInTimeObservation, walk_forward_test
from expansion_wing.portfolio import DualBookPortfolio, FillModel
from expansion_wing.projection import build_living_wall_projection
from expansion_wing.regime import AllocationCandidate, allocation_score, direct_regime
from expansion_wing.resources import ResourceGovernor
from expansion_wing.strictness import observe_counterfactual


class ExpansionWingTests(unittest.TestCase):
    def equity_payload(self):
        return {"instrument": "XYZ", "asset_class": "EQUITY", "provenance": [{"source": "fixture"}],
                "discovery_reason": "dislocation", "expected_horizon": "3 days", "invalidation": "below support",
                "liquidity": {"adv": 1000000}, "volatility": {"atr": 2}, "correlation": {"cluster": "tech"},
                "evidence_freshness": "CURRENT", "confidence": .7, "applicable_book": "TACTICAL"}

    def test_passport_and_observation_only_asset_gates(self):
        self.assertEqual(create_passport(self.equity_payload()).eligibility, Eligibility.ELIGIBLE)
        future = self.equity_payload() | {"asset_class": "FUTURE", "asset_details": {}}
        self.assertEqual(create_passport(future).eligibility, Eligibility.INCOMPLETE)

    def test_dual_book_budgets_and_costs_are_separate(self):
        portfolio = DualBookPortfolio()
        result = portfolio.open_position(book=Book.TACTICAL, instrument="XYZ", quantity=5, reference_price=100,
                                         thesis="catalyst", invalidation="gap closes", fill_model=FillModel(fill_ratio=.5))
        self.assertEqual(result["status"], "PAPER_FILLED")
        snapshot = portfolio.snapshot()
        self.assertEqual(snapshot["strategic"]["cash"], 5000)
        self.assertEqual(snapshot["cash_treasury_reserve"], 2000)
        self.assertEqual(snapshot["total_nav"], 10000)
        self.assertFalse(snapshot["authority"]["live_execution"])

    def test_tactical_eod_is_mandatory(self):
        portfolio = DualBookPortfolio()
        portfolio.open_position(book=Book.TACTICAL, instrument="XYZ", quantity=1, reference_price=100,
                                thesis="x", invalidation="y")
        self.assertEqual(portfolio.classify_tactical_eod("2026-09-03", {})["status"], "INCOMPLETE")

    def test_projection_strips_secrets_and_is_explicit(self):
        now = datetime.now(timezone.utc).isoformat()
        projection = build_living_wall_projection({"service_health": {"observed_at": now, "data": {"ok": True, "token": "no"}}})
        self.assertEqual(projection["sections"]["service_health"]["state"], "CURRENT")
        self.assertNotIn("token", projection["sections"]["service_health"]["data"])
        self.assertEqual(projection["sections"]["radar"]["state"], "UNAVAILABLE")

    def test_regime_fails_transitional_when_incomplete(self):
        self.assertEqual(direct_regime({})["state"], "TRANSITIONAL")
        score = allocation_score(AllocationCandidate("x", .2, .1, .6, .05, 30, .8, .02, .9, .01, .02))
        self.assertFalse(score["projected_return_only_ranking"])

    def test_strictness_never_relaxes_immutable_gates(self):
        result = observe_counterfactual({"research_score": 1, "gates": {"authority": False, "provenance": True,
            "data_integrity": True, "live_execution": True}}, "EXPLORATORY")
        self.assertFalse(result["would_promote_for_research"])

    def test_resource_governor_unknown_cost_fails_closed(self):
        result = ResourceGovernor().admit(priority=7, cpu_pct=1, memory_mb=1, active_ai_tasks=0,
            requests_today=0, known_cost_today=None, queue_depth=0)
        self.assertFalse(result["admitted"])
        self.assertIn("OPTIONAL_JOB_SUSPENDED", result["reasons"])

    def test_walk_forward_uses_costs_and_losses(self):
        rows = [PointInTimeObservation(f"2026-01-0{i}", {"signal": 1}, value, "RISK_ON", .01, .01)
                for i, value in enumerate([.1, .1, -.1, .2], 1)]
        result = walk_forward_test(rows, lambda feature: feature["signal"] > 0)
        self.assertTrue(result["transaction_costs_included"])
        self.assertTrue(result["failures_included"])

    def test_judgment_requires_right_to_use_and_human_review(self):
        principle = JudgmentPrinciple("p", "source", "2026-01-01", "person", "DIRECT", ["EQUITY"], ["RISK_ON"],
            "rule", [], "entry", "size", "exit", "invalid", [], [], .5, {"forward_paper_validation": True}, "reviewer")
        self.assertIn("RIGHT_TO_USE_REQUIRED", principle.validate())
        with self.assertRaises(PermissionError): promote_status(principle, "VALIDATED", human_approved=False)

    def test_interview_consent_and_transcript_approval_fail_closed(self):
        intake = InterviewIntake("i", "Jesse", "AUDIO", "owned://recording", False, [], False)
        self.assertEqual(intake.readiness()["status"], "INCOMPLETE")
        self.assertTrue(intake.review_packet()["max_led"])

    def test_owner_reports_surface_unavailable_sections(self):
        projection = build_living_wall_projection({})
        report = owner_report("OPENING_READINESS", projection)
        self.assertGreater(len(report["exceptions"]), 0)
        self.assertFalse(report["live_execution_authority"])


if __name__ == "__main__":
    unittest.main()
