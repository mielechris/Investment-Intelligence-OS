import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import APIRouter, FastAPI

from open_evidence_watch import install_open_evidence_watch


_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE"}


def _route_rows(router):
    """Read the public mounted-route contract through FastAPI OpenAPI."""
    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    rows = []
    for path, operations in (schema.get("paths") or {}).items():
        methods = {
            str(method).upper()
            for method in operations.keys()
            if str(method).upper() in _HTTP_METHODS
        }
        rows.append((str(path).lower(), methods))
    return rows


class Batch10DMonitorWiringTests(unittest.TestCase):
    def test_monitor_chain_mounts_deep_watch_and_closed_loop_lineage(self):
        primary = Mock()
        primary._lane_status = lambda case_id, lane, records: {"facts": [], "note": ""}

        monitoring = SimpleNamespace(
            refresh_profile=lambda profile: {"profile": profile},
            router=APIRouter(),
        )

        install_open_evidence_watch(primary, monitoring)

        paths = {path for path, _ in _route_rows(monitoring.router)}

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

        for path, methods in _route_rows(monitoring.router):
            if "closed-loop" in path:
                self.assertEqual(methods, {"GET"})


if __name__ == "__main__":
    unittest.main()
