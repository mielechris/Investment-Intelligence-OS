import importlib
import os
import tempfile
import unittest
from pathlib import Path


class GovernedPaperExecutionBridgeTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()

        os.environ["IIOS_DB_PATH"] = str(
            Path(cls.tempdir.name)
            / "bridge_test.db"
        )

        import ledger
        import governed_paper_authorization
        import governed_paper_execution_bridge

        importlib.reload(ledger)
        ledger.init_ledger()

        importlib.reload(
            governed_paper_authorization
        )

        importlib.reload(
            governed_paper_execution_bridge
        )

        cls.ledger = ledger
        cls.auth = (
            governed_paper_authorization
        )
        cls.bridge = (
            governed_paper_execution_bridge
        )

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def qualification(self):
        return {
            "stage":
                "QUALIFIED_BUY_CANDIDATE",
            "qualified_buy_candidate":
                True,
            "unmet_requirements": [],
        }

    def thesis(self):
        return {
            "status":
                "ACTIVE_WITH_WATCHES",
            "thesis_invalidated":
                False,
            "breached_rules": [],
            "watching_rules": [
                "SUPPLY_DEMAND_REVERSAL",
            ],
            "governance": {
                "deterministic_mapper":
                    True,
                "llm_can_trigger_rule":
                    False,
            },
        }

    def capital(self):
        return {
            "decision": "APPROVED",
            "current_price": 800.0,
            "reward_risk": 1.75,
            "failed_hard_checks": [],
            "checks": {
                "reward_risk_passed":
                    True,
            },
        }

    def sizing(self):
        return {
            "decision": "SIZE_READY",
            "proposed_shares": 3,
            "proposed_notional": 2400.0,
            "invalidation_price": 660.24,
            "invalidation_basis":
                "Governed thesis invalidation level",
            "portfolio_nav": 100000.0,
            "combined_overlap_weight_pct":
                30.0,
            "paper_order_permission": False,
            "trade_execution_permission":
                False,
            "live_execution": False,
        }

    def create_auth(
        self,
        case_id,
        qualification=None,
        thesis=None,
        capital=None,
        sizing=None,
    ):
        return self.auth.create_paper_authorization(
            case_id=case_id,
            qualification=(
                qualification
                or self.qualification()
            ),
            thesis_status=(
                thesis
                or self.thesis()
            ),
            capital_gate=(
                capital
                or self.capital()
            ),
            sizing=(
                sizing
                or self.sizing()
            ),
        )

    def execute(
        self,
        case_id,
        authorization_id,
        qualification=None,
        thesis=None,
        capital=None,
        sizing=None,
    ):
        return (
            self.bridge
            .create_governed_paper_order(
                case_id=case_id,
                authorization_id=
                    authorization_id,
                qualification=(
                    qualification
                    or self.qualification()
                ),
                thesis_status=(
                    thesis
                    or self.thesis()
                ),
                capital_gate=(
                    capital
                    or self.capital()
                ),
                sizing=(
                    sizing
                    or self.sizing()
                ),
            )
        )

    def test_valid_authorization_creates_paper_order(self):
        case_id = "case_valid"

        auth = self.create_auth(
            case_id
        )

        result = self.execute(
            case_id,
            auth["paper_authorization_id"],
        )

        self.assertEqual(
            result["execution"],
            "PAPER_ORDER_CREATED",
        )

        self.assertEqual(
            result["shares"],
            3,
        )

        self.assertEqual(
            result["notional"],
            2400.0,
        )

        self.assertTrue(
            result[
                "authorization_consumed"
            ]
        )

        self.assertTrue(
            result[
                "paper_order_permission"
            ]
        )

        self.assertFalse(
            result["live_execution"]
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )

    def test_replayed_token_is_blocked(self):
        case_id = "case_replay"

        auth = self.create_auth(
            case_id
        )

        auth_id = auth[
            "paper_authorization_id"
        ]

        first = self.execute(
            case_id,
            auth_id,
        )

        self.assertEqual(
            first["execution"],
            "PAPER_ORDER_CREATED",
        )

        second = self.execute(
            case_id,
            auth_id,
        )

        self.assertEqual(
            second["status"],
            "BLOCKED",
        )

        self.assertEqual(
            second["reason"],
            "AUTHORIZATION_ALREADY_CONSUMED",
        )

    def test_changed_quote_outside_window_blocks_execution(self):
        case_id = "case_quote"

        auth = self.create_auth(
            case_id
        )

        capital = self.capital()
        capital["current_price"] = 805.0

        result = self.execute(
            case_id,
            auth["paper_authorization_id"],
            capital=capital,
        )

        self.assertEqual(
            result["reason"],
            "ORDER_PRICE_OUTSIDE_AUTHORIZED_WINDOW",
        )

    def test_changed_size_blocks_execution(self):
        case_id = "case_size"

        auth = self.create_auth(
            case_id
        )

        sizing = self.sizing()
        sizing["proposed_shares"] = 4
        sizing["proposed_notional"] = 3200.0

        result = self.execute(
            case_id,
            auth["paper_authorization_id"],
            sizing=sizing,
        )

        self.assertEqual(
            result["reason"],
            "AUTHORIZATION_BINDING_MISMATCH",
        )

    def test_invalidated_thesis_blocks_execution(self):
        case_id = "case_thesis"

        auth = self.create_auth(
            case_id
        )

        thesis = self.thesis()
        thesis["status"] = "INVALIDATED"
        thesis[
            "thesis_invalidated"
        ] = True
        thesis["breached_rules"] = [
            "MEMORY_PRICING_BREAK"
        ]

        result = self.execute(
            case_id,
            auth["paper_authorization_id"],
            thesis=thesis,
        )

        self.assertEqual(
            result["reason"],
            "AUTHORIZATION_BINDING_MISMATCH",
        )

    def test_wait_for_entry_cannot_create_auth_or_execute(self):
        case_id = "case_wait"

        capital = self.capital()
        capital["decision"] = (
            "WAIT_FOR_ENTRY"
        )

        auth = self.create_auth(
            case_id,
            capital=capital,
        )

        self.assertEqual(
            auth["decision"],
            "AUTHORIZATION_DENIED",
        )

        self.assertIsNone(
            auth["paper_authorization_id"]
        )

    def test_zero_notional_cannot_authorize(self):
        case_id = "case_zero"

        sizing = self.sizing()
        sizing["proposed_shares"] = 0
        sizing["proposed_notional"] = 0.0
        sizing["decision"] = "BLOCKED"

        auth = self.create_auth(
            case_id,
            sizing=sizing,
        )

        self.assertEqual(
            auth["decision"],
            "AUTHORIZATION_DENIED",
        )

    def test_wrong_case_blocks_execution(self):
        auth = self.create_auth(
            "case_original"
        )

        result = self.execute(
            "case_other",
            auth["paper_authorization_id"],
        )

        self.assertEqual(
            result["reason"],
            "CASE_BINDING_MISMATCH",
        )

    def test_paper_execution_never_becomes_live(self):
        case_id = "case_no_live"

        auth = self.create_auth(
            case_id
        )

        result = self.execute(
            case_id,
            auth["paper_authorization_id"],
        )

        self.assertFalse(
            result["live_execution"]
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )


if __name__ == "__main__":
    unittest.main()
