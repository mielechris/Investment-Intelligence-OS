import unittest

import governed_paper_execution_api
from governed_paper_execution_api import (
    _authorization_id,
)


class GovernedPaperExecutionApiTests(
    unittest.TestCase
):

    def test_valid_governed_token_format(self):
        result = _authorization_id({
            "paper_authorization_id":
                "paper_auth_abc123"
        })

        self.assertEqual(
            result,
            "paper_auth_abc123",
        )

    def test_missing_authorization_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            _authorization_id({})

    def test_wrong_authorization_type_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            _authorization_id({
                "paper_authorization_id":
                    "risk_auth_123"
            })

    def test_submit_route_exists(self):
        paths = {
            route.path
            for route
            in governed_paper_execution_api
            .router.routes
        }

        self.assertIn(
            "/governed-paper-execution/{case_id}/status",
            paths,
        )

        self.assertIn(
            "/governed-paper-execution/{case_id}/submit",
            paths,
        )

    def test_no_live_execution_route_exists(self):
        paths = {
            route.path.lower()
            for route
            in governed_paper_execution_api
            .router.routes
        }

        self.assertFalse(
            any(
                "live" in path
                or "broker" in path
                or "real-money" in path
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
