import unittest

import paper_capital_api


class PaperCapitalApiTests(
    unittest.TestCase
):

    def test_router_has_status_route_only(self):
        paths = {
            route.path
            for route
            in paper_capital_api.router.routes
        }

        self.assertIn(
            "/paper-capital/{case_id}/status",
            paths,
        )

    def test_no_execution_route_exists(self):
        paths = {
            route.path
            for route
            in paper_capital_api.router.routes
        }

        self.assertFalse(
            any(
                "execute" in path.lower()
                for path in paths
            )
        )

        self.assertFalse(
            any(
                "authorize" in path.lower()
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
