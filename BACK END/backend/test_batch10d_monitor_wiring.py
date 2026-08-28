import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import APIRouter

from open_evidence_watch import install_open_evidence_watch


class Batch10DMonitorWiringTests(unittest.TestCase):
    def test_monitor_chain_mounts_deep_watch_and_closed_loop_lineage(self):
        primary = Mock()
        primary._lane_status = lambda case_id, lane, records: {"facts": [], "note": ""}

        monitoring = SimpleNamespace(
            refresh_profile=lambda profile: {"profile": profile},
            router=APIRouter(),
        )

        install_open_evidence_watch(primary, monitoring)

        paths = {route.path.lower() for route in monitoring.router.routes}

        self.assertIn("/deep-watch/{case_id}/status", paths)
        self.assertIn("/deep-watch/{case_id}/run", paths)
        self.assertIn("/closed-loop/{case_id}/status", paths)
        self.assertIn("/closed-loop/overview", paths)

        self.assertNotIn("/portfolio-context/{case_id}/paper-fund", paths)
        self.assertNotIn("/options-shadow/plan", paths)

        self.assertFalse(
            any(
                token in path
                for path in paths
                for token in ("broker", "live-execution", "options-order")
            )
        )

    def test_closed_loop_surface_is_read_only(self):
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
            if "closed-loop" in path:
                self.assertEqual(methods, {"GET"})


if __name__ == "__main__":
    unittest.main()
