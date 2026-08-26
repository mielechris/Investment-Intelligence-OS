import os
import tempfile
import unittest
from pathlib import Path


class GovernedPaperAuthorizationTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()

        os.environ["IIOS_DB_PATH"] = str(
            Path(cls.tempdir.name)
            / "auth_test.db"
        )

        import importlib
        import ledger

        importlib.reload(ledger)
        ledger.init_ledger()

        cls.ledger = ledger

        import governed_paper_authorization

        importlib.reload(
            governed_paper_authorization
        )

        cls.auth = (
            governed_paper_authorization
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
                "Governed thesis risk level",
            "portfolio_nav": 100000.0,
            "combined_overlap_weight_pct":
                30.0,
            "paper_order_permission": False,
            "trade_execution_permission":
                False,
            "live_execution": False,
        }

    def binding(self):
        return self.auth._canonical_binding(
            case_id="case_test",
            qualification=self.qualification(),
            thesis_status=self.thesis(),
            capital_gate=self.capital(),
            sizing=self.sizing(),
        )

    def test_approved_chain_can_create_authorization(self):
        result = (
            self.auth
            .create_paper_authorization(
                case_id="case_test",
                qualification=self.qualification(),
                thesis_status=self.thesis(),
                capital_gate=self.capital(),
                sizing=self.sizing(),
            )
        )

        self.assertEqual(
            result["decision"],
            "AUTHORIZED_FOR_PAPER_HANDOFF",
        )

        self.assertTrue(
            result["paper_authorization_id"]
            .startswith("paper_auth_")
        )

        self.assertFalse(
            result[
                "paper_execution_ready"
            ]
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )

    def test_wait_for_entry_denies_authorization(self):
        capital = self.capital()
        capital["decision"] = (
            "WAIT_FOR_ENTRY"
        )

        result = (
            self.auth
            .create_paper_authorization(
                case_id="case_test",
                qualification=self.qualification(),
                thesis_status=self.thesis(),
                capital_gate=capital,
                sizing=self.sizing(),
            )
        )

        self.assertEqual(
            result["decision"],
            "AUTHORIZATION_DENIED",
        )

    def test_invalidated_thesis_denies_authorization(self):
        thesis = self.thesis()
        thesis["status"] = "INVALIDATED"
        thesis[
            "thesis_invalidated"
        ] = True
        thesis["breached_rules"] = [
            "MEMORY_PRICING_BREAK"
        ]

        result = (
            self.auth
            .create_paper_authorization(
                case_id="case_test",
                qualification=self.qualification(),
                thesis_status=thesis,
                capital_gate=self.capital(),
                sizing=self.sizing(),
            )
        )

        self.assertEqual(
            result["decision"],
            "AUTHORIZATION_DENIED",
        )

    def test_binding_change_invalidates_token(self):
        result = (
            self.auth
            .create_paper_authorization(
                case_id="case_binding",
                qualification=self.qualification(),
                thesis_status=self.thesis(),
                capital_gate=self.capital(),
                sizing=self.sizing(),
            )
        )

        current = self.auth._canonical_binding(
            case_id="case_binding",
            qualification=self.qualification(),
            thesis_status=self.thesis(),
            capital_gate=self.capital(),
            sizing=self.sizing(),
        )

        # Inject a foreign field to prove the fingerprint rejects
        # any mutation to the canonical authorization payload.
        current["capital_entry_price"] = 801.0

        verified = (
            self.auth
            .verify_paper_authorization(
                authorization_id=result[
                    "paper_authorization_id"
                ],
                current_binding=current,
            )
        )

        self.assertFalse(
            verified["valid"]
        )

        self.assertEqual(
            verified["reason"],
            "AUTHORIZATION_BINDING_MISMATCH",
        )

    def test_authorization_is_single_use(self):
        result = (
            self.auth
            .create_paper_authorization(
                case_id="case_single_use",
                qualification=self.qualification(),
                thesis_status=self.thesis(),
                capital_gate=self.capital(),
                sizing=self.sizing(),
            )
        )

        binding = self.auth._canonical_binding(
            case_id="case_single_use",
            qualification=self.qualification(),
            thesis_status=self.thesis(),
            capital_gate=self.capital(),
            sizing=self.sizing(),
        )

        first = (
            self.auth
            .consume_verified_paper_authorization(
                authorization_id=result[
                    "paper_authorization_id"
                ],
                current_binding=binding,
            )
        )

        self.assertTrue(
            first["consumed"]
        )

        second = (
            self.auth
            .consume_verified_paper_authorization(
                authorization_id=result[
                    "paper_authorization_id"
                ],
                current_binding=binding,
            )
        )

        self.assertFalse(
            second["consumed"]
        )

        self.assertEqual(
            second["reason"],
            "AUTHORIZATION_ALREADY_CONSUMED",
        )

    def test_consumption_still_does_not_execute(self):
        result = (
            self.auth
            .create_paper_authorization(
                case_id="case_no_execute",
                qualification=self.qualification(),
                thesis_status=self.thesis(),
                capital_gate=self.capital(),
                sizing=self.sizing(),
            )
        )

        binding = self.auth._canonical_binding(
            case_id="case_no_execute",
            qualification=self.qualification(),
            thesis_status=self.thesis(),
            capital_gate=self.capital(),
            sizing=self.sizing(),
        )

        consumed = (
            self.auth
            .consume_verified_paper_authorization(
                authorization_id=result[
                    "paper_authorization_id"
                ],
                current_binding=binding,
            )
        )

        self.assertTrue(
            consumed["consumed"]
        )

        self.assertFalse(
            consumed[
                "paper_execution_ready"
            ]
        )

        self.assertFalse(
            consumed[
                "trade_execution_permission"
            ]
        )


if __name__ == "__main__":
    unittest.main()
