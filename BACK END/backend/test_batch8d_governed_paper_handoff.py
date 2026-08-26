import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from unittest.mock import patch

import governed_paper_authorization as auth
import governed_paper_execution_bridge as bridge


QUALIFICATION = {
    "qualification_assessment_id":
        "qualification_test",

    "stage":
        "QUALIFIED_BUY_CANDIDATE",

    "qualified_buy_candidate":
        True,
}

THESIS = {
    "status":
        "ACTIVE_WITH_WATCHES",

    "thesis_invalidated":
        False,

    "breached_rules":
        [],

    "governance": {
        "deterministic_mapper":
            True,
    },
}

CAPITAL = {
    "decision":
        "APPROVED",

    "current_price":
        214.00,

    "reward_risk":
        1.503,

    "minimum_reward_risk":
        1.50,

    "maximum_qualifying_entry":
        214.0695,

    "upside_reference_value":
        300.2194,

    "downside_reference_value":
        156.6362,

    "failed_hard_checks":
        [],

    "_risk_authorization_id":
        "risk_test",
}

SIZING = {
    "decision":
        "SIZE_READY",

    "entry_price":
        214.00,

    "proposed_shares":
        2,

    "proposed_notional":
        428.00,

    "invalidation_price":
        190.00,

    "invalidation_basis":
        "Human-approved invalidation",

    "portfolio_nav":
        10000.00,

    "combined_overlap_weight_pct":
        0.0,

    "max_position_pct":
        0.05,

    "max_portfolio_risk_pct":
        0.005,

    "generic_sizing_profile_id":
        "generic_sizing_profile_test",

    "invalidation_mode":
        "MANUAL_APPROVED",

    "paper_order_permission":
        False,

    "trade_execution_permission":
        False,

    "live_execution":
        False,
}


class Batch8DAuthorizationTests(
    unittest.TestCase
):

    def _create_auth(self):
        with patch.object(
            auth,
            "record_object",
        ), patch.object(
            auth,
            "record_event",
        ):
            return (
                auth.create_paper_authorization(
                    case_id="case_test",
                    qualification=QUALIFICATION,
                    thesis_status=THESIS,
                    capital_gate=CAPITAL,
                    sizing=SIZING,
                )
            )

    def test_authorization_requires_size_ready(self):
        bad_size = {
            **SIZING,
            "decision": "BLOCKED",
            "proposed_shares": 0,
            "proposed_notional": 0.0,
        }

        with patch.object(
            auth,
            "record_object",
        ), patch.object(
            auth,
            "record_event",
        ):
            result = (
                auth.create_paper_authorization(
                    case_id="case_test",
                    qualification=
                        QUALIFICATION,
                    thesis_status=
                        THESIS,
                    capital_gate=
                        CAPITAL,
                    sizing=
                        bad_size,
                )
            )

        self.assertEqual(
            result["decision"],
            "AUTHORIZATION_DENIED",
        )

        self.assertFalse(
            result[
                "paper_order_permission"
            ]
        )

    def test_v2_authorization_has_exact_size_price_window_and_expiry(self):
        result = self._create_auth()

        self.assertEqual(
            result[
                "authorization_version"
            ],
            "GOVERNED_PAPER_AUTHORIZATION_V2",
        )

        self.assertEqual(
            result["authorized_shares"],
            2,
        )

        self.assertLess(
            result["minimum_order_price"],
            214.0,
        )

        self.assertLessEqual(
            result["maximum_order_price"],
            214.0695,
        )

        self.assertTrue(
            result["single_use"]
        )

        self.assertFalse(
            result[
                "paper_order_permission"
            ]
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )

        self.assertFalse(
            result["live_execution"]
        )

    def test_expired_authorization_is_rejected(self):
        authorization = (
            self._create_auth()
        )

        authorization["expires_at"] = (
            datetime.now(
                timezone.utc
            )
            - timedelta(minutes=1)
        ).isoformat()

        binding = (
            auth._canonical_binding(
                case_id="case_test",
                qualification=QUALIFICATION,
                thesis_status=THESIS,
                capital_gate=CAPITAL,
                sizing=SIZING,
            )
        )

        with patch.object(
            auth,
            "get_object",
            return_value=authorization,
        ), patch.object(
            auth,
            "paper_authorization_consumed",
            return_value=False,
        ):
            result = (
                auth.verify_paper_authorization(
                    authorization_id=
                        authorization[
                            "paper_authorization_id"
                        ],

                    current_binding=
                        binding,
                )
            )

        self.assertFalse(
            result["valid"]
        )

        self.assertEqual(
            result["reason"],
            "AUTHORIZATION_EXPIRED",
        )

    def test_binding_change_invalidates_token(self):
        authorization = (
            self._create_auth()
        )

        changed_size = {
            **SIZING,
            "proposed_shares": 1,
        }

        changed_binding = (
            auth._canonical_binding(
                case_id="case_test",
                qualification=QUALIFICATION,
                thesis_status=THESIS,
                capital_gate=CAPITAL,
                sizing=changed_size,
            )
        )

        with patch.object(
            auth,
            "get_object",
            return_value=authorization,
        ), patch.object(
            auth,
            "paper_authorization_consumed",
            return_value=False,
        ):
            result = (
                auth.verify_paper_authorization(
                    authorization_id=
                        authorization[
                            "paper_authorization_id"
                        ],

                    current_binding=
                        changed_binding,
                )
            )

        self.assertFalse(
            result["valid"]
        )

        self.assertEqual(
            result["reason"],
            "AUTHORIZATION_BINDING_MISMATCH",
        )

    def test_consumed_token_cannot_be_reused(self):
        authorization = (
            self._create_auth()
        )

        binding = (
            auth._canonical_binding(
                case_id="case_test",
                qualification=QUALIFICATION,
                thesis_status=THESIS,
                capital_gate=CAPITAL,
                sizing=SIZING,
            )
        )

        with patch.object(
            auth,
            "get_object",
            return_value=authorization,
        ), patch.object(
            auth,
            "paper_authorization_consumed",
            return_value=True,
        ):
            result = (
                auth.verify_paper_authorization(
                    authorization_id=
                        authorization[
                            "paper_authorization_id"
                        ],

                    current_binding=
                        binding,
                )
            )

        self.assertFalse(
            result["valid"]
        )

        self.assertEqual(
            result["reason"],
            "AUTHORIZATION_ALREADY_CONSUMED",
        )

    def test_price_above_window_blocks_before_consumption(self):
        authorization = (
            self._create_auth()
        )

        high_capital = {
            **CAPITAL,
            "current_price": 214.10,
            "reward_risk": 1.50,
        }

        high_sizing = {
            **SIZING,
            "entry_price": 214.10,
            "proposed_notional": 428.20,
        }

        with patch.object(
            bridge,
            "get_object",
            return_value=authorization,
        ), patch.object(
            bridge,
            "verify_paper_authorization",
            return_value={
                "valid": True,
            },
        ), patch.object(
            bridge,
            "consume_verified_paper_authorization",
        ) as consume_mock:

            result = (
                bridge.create_governed_paper_order(
                    case_id="case_test",
                    authorization_id=
                        authorization[
                            "paper_authorization_id"
                        ],
                    qualification=
                        QUALIFICATION,
                    thesis_status=
                        THESIS,
                    capital_gate=
                        high_capital,
                    sizing=
                        high_sizing,
                )
            )

        self.assertEqual(
            result["execution"],
            "NOT_SUBMITTED",
        )

        self.assertEqual(
            result["reason"],
            "ORDER_PRICE_OUTSIDE_AUTHORIZED_WINDOW",
        )

        consume_mock.assert_not_called()

    def test_valid_token_creates_paper_order_only(self):
        authorization = (
            self._create_auth()
        )

        with patch.object(
            bridge,
            "get_object",
            return_value=authorization,
        ), patch.object(
            bridge,
            "verify_paper_authorization",
            return_value={
                "valid": True,
            },
        ), patch.object(
            bridge,
            "consume_verified_paper_authorization",
            return_value={
                "valid": True,
                "consumed": True,
            },
        ), patch.object(
            bridge,
            "record_object",
        ), patch.object(
            bridge,
            "record_event",
        ):

            result = (
                bridge.create_governed_paper_order(
                    case_id="case_test",
                    authorization_id=
                        authorization[
                            "paper_authorization_id"
                        ],
                    qualification=
                        QUALIFICATION,
                    thesis_status=
                        THESIS,
                    capital_gate=
                        CAPITAL,
                    sizing=
                        SIZING,
                )
            )

        self.assertEqual(
            result["status"],
            "COMPLETE",
        )

        self.assertEqual(
            result["execution"],
            "PAPER_ORDER_CREATED",
        )

        self.assertEqual(
            result["shares"],
            2,
        )

        self.assertEqual(
            result["notional"],
            428.00,
        )

        self.assertTrue(
            result[
                "paper_order_permission"
            ]
        )

        self.assertFalse(
            result[
                "trade_execution_permission"
            ]
        )

        self.assertFalse(
            result["live_execution"]
        )


if __name__ == "__main__":
    unittest.main()
