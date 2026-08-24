import unittest

from fastapi import FastAPI

import eight_agent_orchestrator
import opportunity_acquisition
import opportunity_dispatch
import opportunity_scheduler
import orchestration_worker_pool
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
        self.assertGreaterEqual(len(included), 5)

        opportunity_paths = {route.path for route in opportunity_acquisition.router.routes}
        dispatch_paths = {route.path for route in opportunity_dispatch.router.routes}
        scheduler_paths = {
            route.path
            for route in opportunity_scheduler.router.routes
            if hasattr(route, "path")
        }
        orchestration_paths = {route.path for route in eight_agent_orchestrator.router.routes}
        batch_paths = {route.path for route in orchestration_worker_pool.router.routes}
        self.assertIn("/opportunities/scan", opportunity_paths)
        self.assertIn("/opportunities/queue", opportunity_paths)
        self.assertIn("/opportunities/dispatch-queue", dispatch_paths)
        self.assertIn("/opportunities/automation", scheduler_paths)
        self.assertIn("/orchestration/plan", orchestration_paths)
        self.assertIn("/orchestration/{case_id}/run", orchestration_paths)
        self.assertIn("/orchestration/batch/run", batch_paths)

    def test_batch_static_route_precedes_dynamic_case_route(self):
        app = FastAPI()
        app.include_router(public_case_router.router)
        paths = [
            route.path
            for route in app.routes
            if hasattr(route, "path")
        ]
        self.assertLess(
            paths.index("/orchestration/batch/run"),
            paths.index("/orchestration/{case_id}/run"),
        )

    def test_new_research_routes_do_not_expose_execution(self):
        research_paths = {
            route.path.lower()
            for child in (
                opportunity_acquisition.router,
                opportunity_dispatch.router,
                opportunity_scheduler.router,
                orchestration_worker_pool.router,
                eight_agent_orchestrator.router,
            )
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
