import unittest

import monitoring_engine
import portfolio_context


def _route_rows(router):
    """Flatten FastAPI/APIRouter routes across deferred included routers."""
    rows = []
    stack = list(getattr(router, "routes", []) or [])
    seen = set()

    while stack:
        route = stack.pop()
        marker = id(route)
        if marker in seen:
            continue
        seen.add(marker)

        path = getattr(route, "path", None)
        if path:
            rows.append(
                (
                    str(path).lower(),
                    {str(method).upper() for method in (getattr(route, "methods", None) or set())},
                )
            )

        nested_router = getattr(route, "router", None)
        if nested_router is not None:
            stack.extend(list(getattr(nested_router, "routes", []) or []))

        nested_routes = getattr(route, "routes", None)
        if nested_routes:
            stack.extend(list(nested_routes))

    return rows


class Batch10DPortfolioOptionsIntegrationTests(unittest.TestCase):
    def test_portfolio_router_mounts_paper_fund_and_options_shadow_surfaces(self):
        paths = {path for path, _ in _route_rows(portfolio_context.router)}
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
        paths = {path for path, _ in _route_rows(portfolio_context.router)}
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
