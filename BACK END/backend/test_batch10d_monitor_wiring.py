import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import APIRouter

from open_evidence_watch import install_open_evidence_watch


class Batch10DMonitorWiringTests(unittest.TestCase):
    def test_monitor_chain_mounts_portfolio_deep_watch_options_and_lineage(self):
        primary = Mock()
        primary._lane_status = lambda case_id, lane, records: {"facts": [], "note": ""}

        monitoring = SimpleNamespace(
            refresh_profile=lambda profile: {"profile": profile},
            router=APIRouter(),
        )

        install_open_evidence_watch(primary, monitoring)

        paths = {route.path.lower() for route in monitoring.router.routes}

        self.assertIn("/portfolio-context/{case_id}/paper-fund", paths)
        self.assertIn("/portfolio-context/{case_id}/sync-paper-fund", paths)
        self.assertIn("/deep-watch/{case_id}/status", paths)
        self.assertIn("/deep-watch/{case_id}/run", paths)
        self.assertIn("/options-shadow/plan", paths)
        self.assertIn("/options-shadow/{case_id}/status", paths)
        self.assertIn("/closed-loop/{case_id}/status", paths)
        self.assertIn("/closed-loop/overview", paths)

        self.assertTrue(getattr(monitoring, "_paper_fund_portfolio_context_installed", False))
        self.assertFalse(
            any(
                token in path
                for path in paths
                for token in ("broker", "live-execution", "options-order")
            )
        )

    def test_read_only_10d_surfaces_have_no_execution_methods(self):
        primary = Mock()
        primary._lane_status = lambda case_id, lane, records: {"facts": [], "note": ""}

        monitoring = SimpleNamespace(
            refresh_profile=lambda profile: {"profile": profile},
            router=APIRouter(),
        )

        install_open_evidence_watch(primary, monitoring)
        self.assertTrue(callable(monitoring.refresh_profile))

        for route in monitoring.router.routes:
            path = route.path.lower()
            methods = {method.upper() for method in (route.methods or set())}
            if "options-shadow" in path or "closed-loop" in path:
                self.assertEqual(methods, {"GET"})


if __name__ == "__main__":
    unittest.main()
