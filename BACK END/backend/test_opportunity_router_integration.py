import unittest

import eight_agent_orchestrator
import opportunity_acquisition
import public_case_router


class OpportunityRouterIntegrationTests(unittest.TestCase):

    def test_public_factory_router_includes_research_routers(self):
        path_routes = [
            route
            for route in public_case_router.router.routes
            if hasattr(route, "path")
        ]
        paths = {route.path for route in path_routes}
        included = [
            route
            for route in public_case_router.router.routes
            if route.__class__.__name__ == "_IncludedRouter"
        ]
        self.assertIn("/factory/run-public", paths)
        self.assertGreaterEqual(len(included), 2)

        opportunity_paths = {route.path for route in opportunity_acquisition.router.routes}
        orchestration_paths = {route.path for route in eight_agent_orchestrator.router.routes}
        self.assertIn("/opportunities/scan", opportunity_paths)
        self.assertIn("/opportunities/queue", opportunity_paths)
        self.assertIn("/orchestration/plan", orchestration_paths)
        self.assertIn("/orchestration/{case_id}/run", orchestration_paths)

    def test_new_research_routes_do_not_expose_execution(self):
        research_paths = {
            route.path.lower()
            for child in (opportunity_acquisition.router, eight_agent_orchestrator.router)
            for route in child.routes
            if hasattr(route, "path")
        }
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
