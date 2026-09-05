from __future__ import annotations

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from expansion_wing.engine import ExpansionWingEngine
from expansion_wing.interviews import InterviewIntake
from expansion_wing.judgment import JudgmentPrinciple, promote_status
from expansion_wing.models import Book
from expansion_wing.opportunities import create_passport
from expansion_wing.pattern_lab import PointInTimeObservation, walk_forward_test
from expansion_wing.portfolio import DualBookPortfolio, FillModel
from expansion_wing.projection import build_living_wall_projection, state_for
from expansion_wing.resources import ResourceBudget, ResourceGovernor
from expansion_wing.sources import InvestorSourceNote
from expansion_wing.strictness import POLICIES, observe_counterfactual

ROOT = Path(__file__).resolve().parents[3]


def equity_payload(book: str = "TACTICAL"):
    return {"instrument": "FIX", "asset_class": "EQUITY", "observed_at": "2026-09-03T12:00:00Z",
        "provenance": [{"source": "SYNTHETIC_FIXTURE_NON_LIVE", "observed_at": "2026-09-03T12:00:00Z"}],
        "discovery_reason": "synthetic dislocation fixture", "catalyst": "synthetic fixture catalyst",
        "expected_horizon": "3 days", "upside_range_pct": [2, 5], "downside_range_pct": [-4, -1],
        "invalidation": "fixture invalidation", "liquidity": {"adv": 1_000_000},
        "volatility": {"atr": 2}, "correlation": {"cluster": "fixture-tech"},
        "evidence_freshness": "CURRENT", "confidence": .7, "applicable_book": book}


class EndToEndFixtureTests(unittest.TestCase):
    def test_actual_api_mount_and_frontend_fetch(self):
        app_text = (ROOT / "BACK END/backend/app.py").read_text()
        ast.parse(app_text)
        self.assertIn("app.include_router(expansion_wing_router)", app_text)
        frontend = (ROOT / "FRONT END/src/ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertIn('"/snapshot"', frontend)
        self.assertIn("VITE_BACKEND_RECOVERY_GREEN", frontend)

    def test_passport_to_book_end_to_end_and_fund_conservation(self):
        engine = ExpansionWingEngine({"total_nav": 10_000, "fixture_label": "SYNTHETIC_FIXTURE_NON_LIVE"})
        passport = engine.ingest_opportunity(equity_payload())
        result = engine.request_paper_simulation(passport["passport_id"], quantity=2, reference_price=100,
                                                 thesis="fixture thesis", invalidation="fixture invalidation")
        self.assertEqual(result["status"], "PAPER_FILLED")
        state = engine.portfolio.snapshot()
        self.assertEqual(state["strategic"]["cash"], 5000)
        self.assertEqual(state["cash_treasury_reserve"], 2000)
        self.assertEqual(state["total_nav"], 10000)

    def test_books_cannot_cross_spend(self):
        portfolio = DualBookPortfolio()
        rejected = portfolio.open_position(book=Book.TACTICAL, instrument="FIX", quantity=31, reference_price=100,
            thesis="fixture", invalidation="fixture", fill_model=FillModel(0, 0, 1))
        self.assertIn("INSUFFICIENT_BOOK_CASH", rejected["reasons"])
        self.assertEqual(portfolio.strategic.cash, 5000)

    def test_loss_concurrent_and_correlation_limits(self):
        portfolio = DualBookPortfolio()
        portfolio.tactical.daily_realized_pnl = -90
        self.assertIn("DAILY_LOSS_LIMIT", portfolio.validate_open(Book.TACTICAL, "X", 10))
        for index in range(5):
            portfolio.tactical.positions[str(index)] = type("P", (), {"market_value": 1})()
        self.assertIn("CONCURRENT_EXPOSURE_LIMIT", portfolio.validate_open(Book.TACTICAL, "X", 10))
        portfolio = DualBookPortfolio()
        portfolio.strategic.positions["A"] = type("P", (), {"market_value": 2000, "correlation_cluster": "same"})()
        self.assertIn("CORRELATION_CLUSTER_LIMIT", portfolio.validate_open(Book.STRATEGIC, "B", 500, "same"))

    def test_cost_and_partial_fill(self):
        quantity, price = FillModel(spread_bps=10, slippage_bps=20, fill_ratio=.25).fill("BUY", 8, 100)
        self.assertEqual(quantity, 2)
        self.assertGreater(price, 100)

    def test_observation_assets_cannot_create_orders(self):
        engine = ExpansionWingEngine({"total_nav": 10_000, "fixture_label": "SYNTHETIC_FIXTURE_NON_LIVE"})
        details = {
            "IPO": {"listing_date": "2026-01-01", "lockup": "180d", "float": 10, "price_range": [1, 2]},
            "BOND": {"yield": 4, "duration": 5, "maturity": "2031", "credit_quality": "AA"},
            "FUTURE": {"contract_size": 100, "initial_margin": 5000, "leverage": 5, "expiry": "2026-12",
                       "rollover": "fixture plan", "overnight_risk": "fixture risk"},
        }
        for asset, asset_details in details.items():
            passport = engine.ingest_opportunity(equity_payload() | {"asset_class": asset, "asset_details": asset_details})
            result = engine.request_paper_simulation(passport["passport_id"], quantity=1, reference_price=10,
                                                     thesis="fixture", invalidation="fixture")
            self.assertEqual(result["status"], "REJECTED")

    def test_futures_require_all_mechanics(self):
        passport = create_passport(equity_payload() | {"asset_class": "FUTURE", "asset_details": {"contract_size": 1}})
        self.assertIn("MISSING_EXPIRY", passport.gate_reasons)
        self.assertIn("MISSING_LEVERAGE", passport.gate_reasons)
        self.assertIn("MISSING_ROLLOVER", passport.gate_reasons)

    def test_look_ahead_is_rejected(self):
        rows = [PointInTimeObservation(f"2026-01-0{i}T00:00:00Z", {"signal": 1}, .1, "RISK_ON",
                feature_observed_at={"signal": "2027-01-01T00:00:00Z"} if i == 3 else {"signal": f"2026-01-0{i}T00:00:00Z"}) for i in range(1, 4)]
        self.assertEqual(walk_forward_test(rows, lambda _: True)["reason"], "LOOK_AHEAD_FEATURE_DETECTED")

    def test_interview_and_judgment_lifecycle(self):
        intake = InterviewIntake("fixture", "Jesse", "TEXT", "fixture://interview", True, ["research"], True,
                                 "approved fixture transcript", ["Jesse"], True, "reviewer")
        self.assertEqual(intake.readiness()["status"], "READY_FOR_REVIEW")
        principle = JudgmentPrinciple("p", "fixture://source", "2026-01-01", "Jesse", "PARAPHRASED", ["EQUITY"],
            ["RISK_ON"], "rule", [], "entry", "size", "exit", "invalid", [], [], .7,
            {"forward_paper_validation": True}, "reviewer", permissions={"right_to_use": True, "confidential": False})
        promote_status(principle, "PROVISIONAL", human_approved=True)
        promote_status(principle, "VALIDATED", human_approved=True)
        self.assertEqual(principle.status, "VALIDATED")

    def test_copyright_safe_source_storage(self):
        note = InvestorSourceNote("Fixture", "fixture://public", "Fixture Publisher", "2026-01-01", "2026-01-02",
            "INTERVIEW", "Short governed paraphrase.", "Short quotation.", True)
        self.assertFalse(note.governed_record()["complete_work_stored"])
        with self.assertRaises(ValueError):
            InvestorSourceNote("x", "fixture://x", "p", "d", "d", "BOOK", "note", "x" * 281, True).governed_record()

    def test_policy_is_immutable_and_resource_limits_fail_closed(self):
        before = {key: dict(value) for key, value in POLICIES.items()}
        observe_counterfactual({"research_score": 1, "gates": dict.fromkeys(("authority", "provenance", "data_integrity", "live_execution"), True)}, "BALANCED")
        self.assertEqual(POLICIES, before)
        governor = ResourceGovernor(ResourceBudget(provider_cost_per_day=1, max_queue_depth=1))
        self.assertFalse(governor.admit(priority=7, cpu_pct=1, memory_mb=1, active_ai_tasks=0,
            requests_today=0, known_cost_today=1, queue_depth=1, content=b"fixture")["admitted"])
        first = ResourceGovernor().admit(priority=1, cpu_pct=1, memory_mb=1, active_ai_tasks=0,
            requests_today=0, known_cost_today=0, queue_depth=0, content=b"same")
        governor = ResourceGovernor(); governor.admit(priority=1, cpu_pct=1, memory_mb=1, active_ai_tasks=0,
            requests_today=0, known_cost_today=0, queue_depth=0, content=b"same")
        self.assertIn("CONTENT_DUPLICATE", governor.admit(priority=1, cpu_pct=1, memory_mb=1, active_ai_tasks=0,
            requests_today=0, known_cost_today=0, queue_depth=0, content=b"same")["reasons"])
        self.assertTrue(first["admitted"])

    def test_truth_states_and_sanitization(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(state_for(present=True, observed_at=(now - timedelta(hours=1)).isoformat(), now=now), "STALE")
        self.assertEqual(state_for(present=True, observed_at="malformed", now=now), "UNKNOWN")
        projection = build_living_wall_projection({"cases": {"observed_at": now.isoformat(), "complete": False,
            "data": {"password": "hidden", "nested": {"access_token": "hidden", "ok": True}}}})
        self.assertEqual(projection["sections"]["cases"]["state"], "INCOMPLETE")
        self.assertNotIn("password", projection["sections"]["cases"]["data"])
        self.assertNotIn("access_token", projection["sections"]["cases"]["data"]["nested"])

    def test_frontend_registry_fixture_label_dialog_and_keyboard_contract(self):
        text = (ROOT / "FRONT END/src/ExpansionWingFactory.tsx").read_text()
        self.assertEqual(text.count('title:"'), 14)
        for marker in ("FIXTURE / NON-LIVE", 'role="dialog"', 'event.key==="Escape"', "aria-label"):
            self.assertIn(marker, text)
        main = (ROOT / "FRONT END/src/main.tsx").read_text()
        self.assertIn("VITE_EXPANSION_WING_APP", main)
        self.assertIn("? <ExpansionWing />", main)
        provider = (ROOT / "FRONT END/src/ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertIn("VITE_EXPANSION_WING_FIXTURE", provider)
        self.assertEqual(provider.count("fetch("), 1)
        self.assertNotIn("fetch(", text)


if __name__ == "__main__":
    unittest.main()
