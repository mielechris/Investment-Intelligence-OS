from __future__ import annotations

import unittest
import json
from pathlib import Path
from datetime import datetime, timezone

from .tuesday_market_evidence import (AUTHORITY, FORWARD_MODE, METHOD_ADJUSTMENT_REQUIREMENTS,
    PILOT_INSTRUMENTS, adjustment_contract, composite_evidence, controller_plan, derive_liquidity,
    forward_eligibility, method_adjustment_decision, mu_tuesday_template, paper_cost_assumption,
    monday_rehearsal, post_close_report, product_board, prospective_mark, synthetic_forward_receipt,
    synthetic_observation, TuesdayController)


class Superbatch24Tests(unittest.TestCase):
    def setUp(self):
        self.instrument = {"ticker": "MU", "instrument_id": "NASDAQ:MU", "product_id": "us_large_cap_equities", "security_type": "COMMON_STOCK"}
        self.rows = [{"time": f"2026-09-{day:02d}T20:00:00Z", "close": 100 + day, "volume": 1_000_000 + day} for day in range(1, 6)]

    def test_registry_has_ten_governed_unique_representatives(self):
        self.assertEqual(len(PILOT_INSTRUMENTS), 10); self.assertEqual(len({x[0] for x in PILOT_INSTRUMENTS}), 10)

    def test_derived_values_are_labeled_and_reproducible(self):
        values = derive_liquidity(self.rows)
        self.assertEqual(values["median_daily_volume"].units, "SHARES")
        self.assertEqual(values["median_daily_volume"].formula_version, "iios-market-derivations-v1")
        self.assertEqual(values["close_to_close_volatility"].units, "DECIMAL_RETURN")
        self.assertEqual(values, derive_liquidity(self.rows))

    def test_missing_volume_is_unavailable_not_zero(self):
        value = derive_liquidity([])["median_daily_volume"]
        self.assertIsNone(value.value); self.assertEqual(value.name, "UNAVAILABLE")

    def test_adjustment_unspecified_blocks_adjusted_history(self):
        value = adjustment_contract(None)
        self.assertEqual(value["adjustment_state"], "UNSPECIFIED"); self.assertFalse(value["adjusted_history_method_eligible"])

    def test_method_specific_adjustment_matrix(self):
        for method, requirement in METHOD_ADJUSTMENT_REQUIREMENTS.items():
            result = method_adjustment_decision(method, adjustment_state="UNSPECIFIED",
                independent_corroboration=method == "PROFESSIONAL_METHOD")
            if requirement == "ADJUSTED_HISTORY_REQUIRED":
                self.assertEqual(result, {"eligible": False, "reason": "ADJUSTMENT_BASIS_UNSPECIFIED"})
            else:
                self.assertTrue(result["eligible"]); self.assertEqual(result["mode"], FORWARD_MODE)

    def test_cost_is_assumption_never_observed_quote(self):
        cost = paper_cost_assumption("us_large_cap_equities")
        self.assertIsNone(cost.observed_spread_bps); self.assertFalse(cost.actual_bid_ask_available)
        self.assertIn("NOT_MARKET_QUOTE", cost.classification)

    def test_composite_separates_observed_derived_and_blocks_paper(self):
        value = composite_evidence(instrument=self.instrument, snapshot={"price_available": True}, history=self.rows,
            adjustment_basis=None, observed_at="2026-09-05T20:00:00Z", retrieved_at="2026-09-05T20:01:00Z", credits=2)
        self.assertEqual(value["observed"]["adjustment_state"], "UNSPECIFIED")
        self.assertIn("formula_version", value["derived"]["median_daily_volume"])
        self.assertFalse(value["adjusted_history_method_eligible"]); self.assertFalse(value["paper_research_eligible"])
        self.assertEqual(value["authority"], AUTHORITY)

    def test_point_in_time_and_registry_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "ACCOUNTING_OR_POINT_IN_TIME_INVALID"):
            composite_evidence(instrument=self.instrument, snapshot={}, history=[], adjustment_basis=None,
                observed_at="2026-09-06T00:00:00Z", retrieved_at="2026-09-05T00:00:00Z", credits=1)

    def test_controller_disabled_and_budgeted(self):
        plan = controller_plan(instruments=10, observations_per_instrument=3, credits_remaining=996, market_day=True)
        self.assertFalse(plan["enabled"]); self.assertTrue(plan["budget_valid"]); self.assertEqual(plan["expected_credits"], 30)
        self.assertFalse(controller_plan(instruments=10, observations_per_instrument=4, credits_remaining=996, market_day=True)["budget_valid"])
        self.assertEqual(plan["cadence"], ("OPENING_CURRENT_EVIDENCE", "BOUNDED_INTRADAY_MARK", "CLOSING_POST_MARKET_MARK"))

    def test_holiday_controller_makes_no_market_cadence_eligible(self):
        plan = controller_plan(instruments=10, observations_per_instrument=0, credits_remaining=996, market_day=False)
        self.assertEqual(plan["market_state"], "CLOSED_HOLIDAY"); self.assertFalse(plan["budget_valid"])

    def test_synthetic_separation(self):
        value = synthetic_observation({"research_eligible": True, "paper_research_eligible": True, "missing_fields": []}, candidate_id="opaque")
        self.assertEqual(value["state"], "SYNTHETIC_OBSERVATION_ELIGIBLE")
        self.assertFalse(value["operational_position"]); self.assertFalse(value["ledger_write"])

    def test_synthetic_requires_candidate_and_complete_evidence(self):
        self.assertEqual(synthetic_observation({"research_eligible": True, "paper_research_eligible": True, "missing_fields": []}, candidate_id=None)["state"], "BLOCKED")

    def test_product_board_keeps_all_24_rooms_and_nulls_unknown_credits(self):
        board = product_board([], next_observation=None)
        self.assertEqual(len(board), 24); self.assertTrue(all(x["classification"] == "UNAVAILABLE" for x in board))
        self.assertTrue(all(x["credits_used"] is None for x in board)); self.assertTrue(all(x["authority"] == AUTHORITY for x in board))

    def test_mu_template_has_no_trade_parameters(self):
        template = mu_tuesday_template()
        self.assertEqual(template["candidate_state"], "WAITING_FOR_CURRENT_TUESDAY_EVIDENCE")
        self.assertEqual(template["mode"], FORWARD_MODE); self.assertEqual(template["starting_synthetic_sleeve"], 10_000)
        for key in ("entry_price", "share_count", "stop", "target", "size", "position", "return", "recommendation"):
            self.assertIsNone(template[key])

    def test_forward_only_requires_every_nonhistorical_gate(self):
        evidence = composite_evidence(instrument=self.instrument, snapshot={"price_available": True}, history=self.rows,
            adjustment_basis=None, observed_at="2026-09-05T20:00:00Z", retrieved_at="2026-09-05T20:01:00Z", credits=2)
        accepted = forward_eligibility(evidence, thesis_evidence=True, invalidation=True, candidate_id="immutable",
            committee_approved=True, risk_approved=True)
        self.assertTrue(accepted["synthetic_paper_eligible"]); self.assertFalse(accepted["operational_paper_eligible"])
        self.assertFalse(accepted["historical_return_claim"]); self.assertFalse(accepted["total_return_claim"])
        rejected = forward_eligibility(evidence, thesis_evidence=True, invalidation=True, candidate_id=None,
            committee_approved=True, risk_approved=True)
        self.assertIn("IMMUTABLE_CANDIDATE", rejected["failed_requirements"])

    def test_forward_marks_suspend_across_corporate_action_without_rewrite(self):
        initial = prospective_mark({"marks": ()}, timestamp="2026-09-08T13:30:00Z", source_hash="a" * 64)
        marked = prospective_mark(initial, timestamp="2026-09-08T17:00:00Z", source_hash="b" * 64)
        suspended = prospective_mark(marked, timestamp="2026-09-08T20:00:00Z", source_hash="c" * 64,
            corporate_action="SPLIT")
        self.assertEqual(suspended["outcome"], "INCOMPLETE_CORPORATE_ACTION")
        self.assertEqual(suspended["marks"], marked["marks"]); self.assertFalse(suspended["retroactive_rewrite"])

    def test_forward_gate_rejects_stale_snapshot_committee_risk_and_corporate_action(self):
        evidence = composite_evidence(instrument=self.instrument, snapshot={"price_available": True}, history=self.rows,
            adjustment_basis=None, observed_at="2026-09-04T20:00:00Z", retrieved_at="2026-09-05T20:01:00Z", credits=2)
        result = forward_eligibility(evidence, thesis_evidence=True, invalidation=True, candidate_id="immutable",
            committee_approved=False, risk_approved=False, corporate_action_state="UNRECONCILED")
        self.assertTrue({"CURRENT_SNAPSHOT", "COMMITTEE", "RISK", "CORPORATE_ACTION"} <= set(result["failed_requirements"]))

    def test_monday_holiday_rehearsal_is_zero_mutation(self):
        value = monday_rehearsal()
        self.assertEqual(value["market_state"], "CLOSED_HOLIDAY")
        for key in ("provider_requests", "credits_consumed", "candidates_created", "synthetic_positions",
                    "operational_positions", "orders", "fills", "transactions", "ledger_entries"):
            self.assertEqual(value[key], 0)
        self.assertFalse(value["keychain_access"]); self.assertFalse(value["projection_sequence_mutation"])

    def test_controller_is_disabled_and_credential_gate_precedes_reservation(self):
        controller = TuesdayController()
        self.assertFalse(controller.readiness()["enabled"])
        self.assertEqual(controller.reserve("MU", "obs-1", owner_authorized=True, entitlement=True,
            session_open=True), "CREDENTIAL_ACCESS_PROHIBITED")
        self.assertEqual(controller.consumed_by_instrument, {})

    def test_controller_enforces_identity_duplicate_per_instrument_and_global_budget(self):
        controller = TuesdayController(enabled=True)
        for index in range(3): self.assertEqual(controller.reserve("MU", f"mu-{index}", owner_authorized=True,
            entitlement=True, session_open=True), "RESERVED")
        self.assertEqual(controller.reserve("MU", "mu-3", owner_authorized=True, entitlement=True,
            session_open=True), "BUDGET_IDENTITY_OR_DUPLICATE_REJECTED")
        other = TuesdayController(enabled=True)
        self.assertEqual(other.reserve("MU", "same", owner_authorized=True, entitlement=True, session_open=True), "RESERVED")
        self.assertEqual(other.reserve("SPY", "same", owner_authorized=True, entitlement=True, session_open=True), "BUDGET_IDENTITY_OR_DUPLICATE_REJECTED")

    def test_phase_machine_requires_human_review_and_fails_closed(self):
        controller = TuesdayController(enabled=True)
        self.assertEqual(controller.transition("OPENING_EVIDENCE_COLLECTION"), "OPENING_EVIDENCE_COLLECTION")
        self.assertEqual(controller.transition("HUMAN_CANDIDATE_REVIEW"), "HUMAN_CANDIDATE_REVIEW")
        self.assertEqual(controller.transition("FORWARD_OBSERVATION_ACTIVE"), "FAILED_CLOSED")
        accepted = TuesdayController(enabled=True); accepted.transition("OPENING_EVIDENCE_COLLECTION")
        accepted.transition("HUMAN_CANDIDATE_REVIEW")
        self.assertEqual(accepted.transition("FORWARD_OBSERVATION_ACTIVE", human_candidate_review=True), "FORWARD_OBSERVATION_ACTIVE")

    def test_synthetic_receipt_is_explicit_and_operationally_inert(self):
        value = synthetic_forward_receipt(observation_id="immutable-observation", instrument_id="NASDAQ:MU",
            product_id="us_large_cap_equities", thesis_id="reviewed-thesis", benchmark="SP500",
            timestamp="2026-09-08T14:00:00Z", modeled_cost_bps=26, synthetic_quantity=10,
            invalidation="reviewed-invalidation", committee_receipt="committee-receipt",
            risk_receipt="risk-receipt", corporate_action_state="CLEAR", evidence_lineage=("source-hash",))
        self.assertEqual(value["classification"], "SYNTHETIC_PAPER_RESEARCH")
        for key in ("operational_position", "order", "fill", "transaction", "ledger_write", "recommendation"):
            self.assertFalse(value[key])

    def test_post_close_report_is_null_safe_and_does_not_rank_one_day(self):
        value = post_close_report(instrument_accounting={"MU": {"requests": 0, "credits": 0}})
        self.assertEqual(value["sample_state"], "INSUFFICIENT_SAMPLE")
        self.assertIsNone(value["drawdown"]); self.assertIsNone(value["calibration"]); self.assertFalse(value["profitability_claim"])

    def test_sanitized_live_acceptance_is_bounded_and_non_authoritative(self):
        value = json.loads((Path(__file__).parent / "fixtures/superbatch24_live_acceptance_metadata.json").read_text())
        self.assertEqual((value["attempted_requests"], value["confirmed_requests"], value["ambiguous_requests"]), (20, 20, 0))
        self.assertEqual(value["new_confirmed_credits"], 20); self.assertEqual(value["maximum_remaining"], 976)
        self.assertEqual(len(value["products"]), 10); self.assertTrue(all(row["observations"] == 20 for row in value["products"]))
        self.assertEqual(value["adjustment_state"], "UNSPECIFIED"); self.assertEqual(value["authority"], AUTHORITY)
        encoded = json.dumps(value).lower()
        for prohibited in ("x-api-key", "credential_value", "response_body", "entry_price", "recommendation"):
            self.assertNotIn(prohibited, encoded)


if __name__ == "__main__": unittest.main()
