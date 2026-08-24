import unittest

import public_case_router


class OpportunityRouterIntegrationTests(unittest.TestCase):

    def test_public_factory_router_exposes_new_research_routes(self):
        paths = {route.path for route in public_case_router.router.routes}
        self.assertIn("/factory/run-public", paths)
        self.assertIn("/opportunities/scan", paths)
        self.assertIn("/opportunities/queue", paths)
        self.assertIn("/orchestration/plan", paths)
        self.assertIn("/orchestration/{case_id}/run", paths)

    def test_new_research_routes_do_not_expose_execution(self):
        paths = {route.path.lower() for route in public_case_router.router.routes}
        research_paths = [
            path for path in paths
            if path.startswith("/opportunities") or path.startswith("/orchestration")
        ]
        self.assertTrue(research_paths)
        self.assertFalse(
            any(
                "paper-authorization" in path
                or "governed-paper-execution" in path
                or "broker" in path
                or "live" in path
                for path in research_paths
            )
        )


if __name__ == "__main__":
    unittest.main()
