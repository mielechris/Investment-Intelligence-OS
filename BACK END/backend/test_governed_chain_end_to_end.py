import importlib
import os
import tempfile
import unittest
from pathlib import Path


class GovernedChainEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(cls.tempdir.name) / "governed_chain_e2e.db")

        import ledger
        import automatic_paper_sizing
        import capital_entry_watch
        import governed_paper_authorization
        import governed_paper_execution_bridge
        import paper_authorization_api

        importlib.reload(ledger)
        ledger.init_ledger()
        importlib.reload(automatic_paper_sizing)
        importlib.reload(capital_entry_watch)
        importlib.reload(governed_paper_authorization)
        importlib.reload(governed_paper_execution_bridge)
        importlib.reload(paper_authorization_api)

        cls.ledger = ledger
        cls.sizer = automatic_paper_sizing
        cls.entry = capital_entry_watch
        cls.auth = governed_paper_authorization
        cls.bridge = governed_paper_execution_bridge
        cls.auth_api = paper_authorization_api

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def qualification(self):
        return {
            "stage": "QUALIFIED_BUY_CANDIDATE",
            "qualified_buy_candidate": True,
            "unmet_requirements": [],
        }

    def thesis(self):
        return {
            "status": "ACTIVE_WITH_WATCHES",
            "thesis_invalidated": False,
            "breached_rules": [],
            "watching_rules": ["SUPPLY_DEMAND_REVERSAL"],
            "governance": {
                "deterministic_mapper": True,
                "llm_can_trigger_rule": False,
            },
        }

    def capital(self):
        return {
            "decision": "APPROVED",
            "current_price": 800.0,
            "reward_risk": 1.75,
            "minimum_reward_risk": 1.50,
            "maximum_qualifying_entry": 819.504,
            "failed_hard_checks": [],
            "checks": {"reward_risk_passed": True},
        }

    def seed_sizing_inputs(self, case_id):
        profile_id = f"paper_sizing_profile_{case_id}"
        self.ledger.record_object(
            profile_id,
            "paper_sizing_profile",
            case_id,
            {
                "paper_sizing_profile_id": profile_id,
                "case_id": case_id,
                "enabled": True,
                "inputs_complete": True,
                "portfolio_nav": 100000.0,
                "invalidation_price": 660.24,
                "invalidation_basis": "Explicit governed thesis risk boundary for E2E test.",
                "paper_mode": True,
                "trade_execution_permission": False,
            },
        )

        snapshot_id = f"portfolio_snapshot_{case_id}"
        self.ledger.record_object(
            snapshot_id,
            "portfolio_snapshot",
            case_id,
            {
                "portfolio_snapshot_id": snapshot_id,
                "case_id": case_id,
                "overlap": {
                    "combined_overlap_weight_pct": 30.0,
                    "concentration_level": "MODERATE",
                },
                "paper_mode": True,
                "live_execution": False,
            },
        )

    def build_good_chain(self, case_id):
        qualification = self.qualification()
        thesis = self.thesis()
        capital = self.capital()
        entry_watch = self.entry.classify_entry_state(
            capital=capital,
            previous={"stage": "WAIT_FOR_ENTRY"},
        )

        # Authorization now requires a governed quote no older than 30 minutes.
        # The E2E fixture represents a quote captured at test time; production
        # freshness enforcement remains unchanged and fail-closed.
        entry_watch["quote_timestamp"] = self.ledger.utc_now()

        self.assertEqual(entry_watch["stage"], "READY_FOR_POSITION_SIZING")
        self.assertTrue(entry_watch["crossed_into_ready"])
        self.assertFalse(entry_watch["paper_authorization_ready"])

        self.seed_sizing_inputs(case_id)
        sizing = self.sizer.calculate_automatic_paper_sizing(
            case_id=case_id,
            capital_gate=capital,
        )
        self.assertEqual(sizing["decision"], "SIZE_READY")
        self.assertEqual(sizing["proposed_shares"], 3)
        self.assertEqual(sizing["proposed_notional"], 2400.0)

        readiness = self.auth_api.assess_authorization_readiness(
            qualification=qualification,
            thesis=thesis,
            capital=capital,
            sizing=sizing,
            entry_watch=entry_watch,
        )
        self.assertTrue(readiness["ready"], readiness)

        authorization = self.auth.create_paper_authorization(
            case_id=case_id,
            qualification=qualification,
            thesis_status=thesis,
            capital_gate=capital,
            sizing=sizing,
        )
        self.assertEqual(authorization["decision"], "AUTHORIZED_FOR_PAPER_HANDOFF")
        self.assertTrue(authorization["paper_authorization_id"].startswith("paper_auth_"))
        self.assertFalse(authorization["paper_order_permission"])

        return {
            "qualification": qualification,
            "thesis": thesis,
            "capital": capital,
            "entry_watch": entry_watch,
            "sizing": sizing,
            "authorization": authorization,
        }

    def execute(
        self,
        case_id,
        chain,
        *,
        qualification=None,
        thesis=None,
        capital=None,
        sizing=None,
    ):
        return self.bridge.create_governed_paper_order(
            case_id=case_id,
            authorization_id=chain["authorization"]["paper_authorization_id"],
            qualification=qualification or chain["qualification"],
            thesis_status=thesis or chain["thesis"],
            capital_gate=capital or chain["capital"],
            sizing=sizing or chain["sizing"],
        )

    def test_01_good_trade_reaches_one_paper_order(self):
        case_id = "case_e2e_good_trade"
        chain = self.build_good_chain(case_id)
        result = self.execute(case_id, chain)
        self.assertEqual(result["execution"], "PAPER_ORDER_CREATED")
        self.assertEqual(result["shares"], 3)
        self.assertEqual(result["notional"], 2400.0)
        self.assertTrue(result["authorization_consumed"])
        self.assertTrue(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])
        persisted = self.ledger.latest_object("governed_paper_execution", case_id=case_id) or {}
        self.assertEqual(persisted.get("execution_id"), result["execution_id"])

    def test_02_replay_is_rejected_and_does_not_duplicate_order(self):
        case_id = "case_e2e_replay"
        chain = self.build_good_chain(case_id)
        first = self.execute(case_id, chain)
        self.assertEqual(first["execution"], "PAPER_ORDER_CREATED")
        second = self.execute(case_id, chain)
        self.assertEqual(second["status"], "BLOCKED")
        self.assertEqual(second["reason"], "AUTHORIZATION_ALREADY_CONSUMED")
        executions = self.ledger.list_objects(case_id, "governed_paper_execution")
        self.assertEqual(len(executions), 1)

    def test_03_changed_quote_outside_window_is_rejected(self):
        case_id = "case_e2e_quote_attack"
        chain = self.build_good_chain(case_id)
        changed = {**chain["capital"], "current_price": 805.0}
        result = self.execute(case_id, chain, capital=changed)
        self.assertEqual(result["reason"], "ORDER_PRICE_OUTSIDE_AUTHORIZED_WINDOW")

    def test_04_changed_size_is_rejected(self):
        case_id = "case_e2e_size_attack"
        chain = self.build_good_chain(case_id)
        changed = {
            **chain["sizing"],
            "proposed_shares": 4,
            "proposed_notional": 3200.0,
        }
        result = self.execute(case_id, chain, sizing=changed)
        self.assertEqual(result["reason"], "AUTHORIZATION_BINDING_MISMATCH")

    def test_05_invalidated_thesis_is_rejected(self):
        case_id = "case_e2e_thesis_attack"
        chain = self.build_good_chain(case_id)
        changed = {
            **chain["thesis"],
            "status": "INVALIDATED",
            "thesis_invalidated": True,
            "breached_rules": ["MEMORY_PRICING_BREAK"],
        }
        result = self.execute(case_id, chain, thesis=changed)
        self.assertEqual(result["reason"], "AUTHORIZATION_BINDING_MISMATCH")

    def test_06_wrong_case_is_rejected(self):
        source_case = "case_e2e_original"
        chain = self.build_good_chain(source_case)
        result = self.execute("case_e2e_wrong_case", chain)
        self.assertEqual(result["reason"], "CASE_BINDING_MISMATCH")

    def test_07_stale_governed_state_is_rejected(self):
        case_id = "case_e2e_stale_state"
        chain = self.build_good_chain(case_id)
        changed = {**chain["capital"], "maximum_qualifying_entry": 818.0}
        result = self.execute(case_id, chain, capital=changed)
        self.assertEqual(result["reason"], "AUTHORIZATION_BINDING_MISMATCH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
