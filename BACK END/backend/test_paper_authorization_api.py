import unittest
from datetime import datetime, timezone

import paper_authorization_api
from paper_authorization_api import (
    assess_authorization_readiness,
)


def qualification():
    return {
        "qualified_buy_candidate":
            True,
    }


def thesis():
    return {
        "status":
            "ACTIVE_WITH_WATCHES",
        "thesis_invalidated":
            False,
        "breached_rules": [],
    }


def capital():
    return {
        "decision":
            "APPROVED",
        "current_price":
            800.0,
    }


def sizing():
    return {
        "decision":
            "SIZE_READY",
        "entry_price":
            800.0,
        "proposed_shares":
            3,
        "proposed_notional":
            2400.0,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,
    }


def watch():
    return {
        "stage":
            "READY_FOR_POSITION_SIZING",
        "current_price":
            800.0,
        "quote_timestamp":
            datetime.now(timezone.utc).isoformat(),
    }


class PaperAuthorizationApiTests(
    unittest.TestCase
):

    def test_good_state_is_ready(self):
        result = (
            assess_authorization_readiness(
                qualification=
                    qualification(),
                thesis=thesis(),
                capital=capital(),
                sizing=sizing(),
                entry_watch=watch(),
            )
        )

        self.assertTrue(
            result["ready"]
        )

    def test_wait_for_entry_is_not_ready(self):
        w = watch()
        w["stage"] = "WAIT_FOR_ENTRY"

        result = (
            assess_authorization_readiness(
                qualification=
                    qualification(),
                thesis=thesis(),
                capital=capital(),
                sizing=sizing(),
                entry_watch=w,
            )
        )

        self.assertFalse(
            result["ready"]
        )

        self.assertIn(
            "entry_watch_ready",
            result["failed_checks"],
        )

    def test_quote_change_blocks_authorization(self):
        w = watch()
        w["current_price"] = 801.0

        result = (
            assess_authorization_readiness(
                qualification=
                    qualification(),
                thesis=thesis(),
                capital=capital(),
                sizing=sizing(),
                entry_watch=w,
            )
        )

        self.assertFalse(
            result["ready"]
        )

        self.assertIn(
            "quote_binding_current",
            result["failed_checks"],
        )

    def test_invalidated_thesis_blocks_authorization(self):
        t = thesis()
        t["status"] = "INVALIDATED"
        t["thesis_invalidated"] = True

        result = (
            assess_authorization_readiness(
                qualification=
                    qualification(),
                thesis=t,
                capital=capital(),
                sizing=sizing(),
                entry_watch=watch(),
            )
        )

        self.assertFalse(
            result["ready"]
        )

    def test_api_contains_no_execution_route(self):
        paths = {
            route.path
            for route
            in paper_authorization_api
            .router.routes
        }

        self.assertIn(
            "/paper-authorization/{case_id}/status",
            paths,
        )

        self.assertIn(
            "/paper-authorization/{case_id}/prepare",
            paths,
        )

        self.assertFalse(
            any(
                "execute" in path.lower()
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
