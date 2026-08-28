import unittest

import monitoring_engine
import portfolio_context


class Batch10DPortfolioOptionsIntegrationTests(unittest.TestCase):
    def test_portfolio_router_mounts_paper_fund_and_options_shadow_surfaces(self):
        paths = {route.path.lower() for route in portfolio_context.router.routes}
        self.assertIn("/portfolio-context/{case_id}/paper-fund", paths)
        self.assertIn("/portfolio-context/{case_id}/sync-paper-fund", paths)
        self.assertIn("/options-shadow/plan", paths)
        self.assertIn("/options-shadow/{case_id}/status", paths)

    def test_paper_fund_bridge_is_installed_on_monitoring_engine(self):
        self.assertTrue(
            getattr(
                monitoring_engine,
                "_paper_fund_portfolio_context_installed",
                False,
            )
        )
        self.assertTrue(callable(monitoring_engine.refresh_profile))

    def test_new_surfaces_do_not_expose_execution_routes(self):
        paths = {route.path.lower() for route in portfolio_context.router.routes}
        self.assertFalse(
            any(
                "broker" in path
                or "live-execute" in path
                or "option-order" in path
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
