import unittest

from capital_entry_watch import (
    classify_entry_state,
)


def capital(
    *,
    decision="WAIT_FOR_ENTRY",
    price=914.44,
    maximum_entry=819.504,
    reward_risk=0.5663,
):
    return {
        "decision":
            decision,
        "current_price":
            price,
        "maximum_qualifying_entry":
            maximum_entry,
        "reward_risk":
            reward_risk,
        "minimum_reward_risk":
            1.5,
    }


class CapitalEntryWatchTests(
    unittest.TestCase
):

    def test_wait_for_entry_remains_locked(self):
        result = classify_entry_state(
            capital=capital(),
        )

        self.assertEqual(
            result["stage"],
            "WAIT_FOR_ENTRY",
        )

        self.assertAlmostEqual(
            result["entry_gap"],
            94.936,
            places=3,
        )

        self.assertFalse(
            result[
                "position_sizing_ready"
            ]
        )

    def test_approved_entry_only_advances_to_sizing(self):
        result = classify_entry_state(
            capital=capital(
                decision="APPROVED",
                price=800.0,
                reward_risk=1.75,
            ),
        )

        self.assertEqual(
            result["stage"],
            "READY_FOR_POSITION_SIZING",
        )

        self.assertTrue(
            result[
                "position_sizing_ready"
            ]
        )

        self.assertFalse(
            result[
                "paper_authorization_ready"
            ]
        )

        self.assertFalse(
            result[
                "paper_order_permission"
            ]
        )

    def test_crossing_from_wait_is_detected(self):
        previous = {
            "stage":
                "WAIT_FOR_ENTRY",
        }

        result = classify_entry_state(
            capital=capital(
                decision="APPROVED",
                price=800.0,
                reward_risk=1.75,
            ),
            previous=previous,
        )

        self.assertTrue(
            result[
                "crossed_into_ready"
            ]
        )

    def test_rejected_capital_stays_blocked(self):
        result = classify_entry_state(
            capital=capital(
                decision="REJECTED",
            ),
        )

        self.assertEqual(
            result["stage"],
            "CAPITAL_REJECTED",
        )

        self.assertFalse(
            result[
                "position_sizing_ready"
            ]
        )

    def test_entry_watch_never_authorizes_or_executes(self):
        result = classify_entry_state(
            capital=capital(
                decision="APPROVED",
                price=800.0,
                reward_risk=1.75,
            ),
        )

        self.assertFalse(
            result[
                "paper_authorization_ready"
            ]
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


if __name__ == "__main__":
    unittest.main()
