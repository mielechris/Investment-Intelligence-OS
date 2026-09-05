from __future__ import annotations

import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts" / "iios_factory_browser_preview.py"
FRONTEND = ROOT / "FRONT END" / "src"


def load_preview_module():
    spec = importlib.util.spec_from_file_location("iios_superbatch19_preview", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("PREVIEW_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FixedCache:
    def get(self, _identity, _builder):
        return {"schema_version": "batch9l-living-factory-v1", "safety": {"live_execution": False}}


class FakeCompositor:
    def snapshot(self):
        return {
            "schema_version": "expansion-wing-truth-v1",
            "mode": "READ_ONLY",
            "sections": {},
            "authority": {"provider": False, "broker": False, "ledger_write": False, "live_execution": False},
        }


class RuntimeParityServerTests(unittest.TestCase):
    def setUp(self):
        self.module = load_preview_module()
        self.module._living_overview_cache = FixedCache()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "index.html").write_text("<main>UNIFIED FACTORY</main>", encoding="utf-8")
        self.servers = []

    def tearDown(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.temporary.cleanup()

    def start(self, enabled: bool):
        server = self.module.PreviewServer(
            ("127.0.0.1", 0), self.root, self.root, self.root, self.root / "paper.db",
            expansion_enabled=enabled, expansion_compositor=FakeCompositor(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return server

    @staticmethod
    def request(server, path: str):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_disabled_server_projects_false_and_route_is_closed(self):
        server = self.start(False)
        _, health = self.request(server, "/health")
        _, overview = self.request(server, "/living/overview")
        status, disabled = self.request(server, "/expansion-wing/snapshot")
        self.assertFalse(health["runtime_capabilities"]["expansion_wing_enabled"])
        self.assertFalse(overview["runtime_capabilities"]["expansion_wing_enabled"])
        self.assertEqual((status, disabled["status"]), (503, "EXPANSION_WING_NOT_ACTIVATED"))

    def test_enabled_server_projects_authenticated_read_only_capability(self):
        server = self.start(True)
        for path in ("/health", "/living/overview"):
            status, payload = self.request(server, path)
            capability = payload["runtime_capabilities"]
            self.assertEqual(status, 200)
            self.assertEqual(capability["schema_version"], "iios-runtime-capabilities-v1")
            self.assertTrue(capability["configuration_authenticated"])
            self.assertTrue(capability["expansion_wing_enabled"])
            self.assertTrue(capability["read_only"])
            self.assertFalse(capability["publisher_control"])
        status, snapshot = self.request(server, "/expansion-wing/snapshot")
        self.assertEqual((status, snapshot["mode"]), (200, "READ_ONLY"))

    def test_cached_evidence_cannot_suppress_runtime_capability(self):
        server = self.start(False)
        _, before = self.request(server, "/living/overview")
        server.expansion_enabled = True
        _, after = self.request(server, "/living/overview")
        self.assertFalse(before["runtime_capabilities"]["expansion_wing_enabled"])
        self.assertTrue(after["runtime_capabilities"]["expansion_wing_enabled"])


class RuntimeParityFrontendTests(unittest.TestCase):
    def test_navigation_is_runtime_gated_not_fixture_gated(self):
        browser = (FRONTEND / "LiveFactoryBrowser.tsx").read_text(encoding="utf-8")
        self.assertIn("runtimeCapabilities.expansionWingEnabled", browser)
        self.assertIn("expansionEnabled ? <button", browser)
        self.assertNotIn("VITE_EXPANSION_WING_FIXTURE", browser)
        self.assertIn("#expansion-wing", browser)
        self.assertIn('view === "expansion" && !expansionEnabled ? "floor" : view', browser)

    def test_single_expansion_polling_owner_is_same_origin_and_has_no_control_route(self):
        provider = (FRONTEND / "ExpansionWingSnapshotProvider.tsx").read_text(encoding="utf-8")
        sources = "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND.glob("*.tsx"))
        self.assertEqual(sources.count('"/expansion-wing/snapshot"'), 1)
        self.assertEqual(provider.count("fetch("), 1)
        self.assertIn('const CAPABILITIES_ENDPOINT = "/living/overview"', provider)
        self.assertIn("UNIFIED_FACTORY", provider)
        for prohibited in ("/publish", "projection_publisher", "broker/connect", "ledger/write"):
            self.assertNotIn(prohibited, provider)

    def test_terminal_fetch_failures_do_not_claim_warm_up_or_models(self):
        operating = (FRONTEND / "OperatingSuperbatch.tsx").read_text(encoding="utf-8")
        readiness = (FRONTEND / "ReadinessSuperbatch.tsx").read_text(encoding="utf-8")
        floor = (FRONTEND / "LivingFactorySpatialFloor.tsx").read_text(encoding="utf-8")
        for source in (operating, readiness, floor):
            self.assertNotIn("SIDECAR WARM-UP", source)
        self.assertIn("OPERATING VIEW UNAVAILABLE", operating)
        self.assertIn("OPTIONAL_OPERATING_SOURCE_UNAVAILABLE", operating)
        self.assertIn("READINESS UNAVAILABLE", readiness)
        self.assertIn("OPTIONAL_READINESS_SOURCE_UNAVAILABLE", readiness)
        self.assertIn("FACTORY SOURCE UNAVAILABLE", floor)
        self.assertNotIn("model is warming", (operating + readiness + floor).lower())
        visible_sources = "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND.glob("*.tsx"))
        self.assertNotIn("WARM-UP", visible_sources)

    def test_initial_loading_remains_distinct_from_completed_failure(self):
        operating = (FRONTEND / "OperatingSuperbatch.tsx").read_text(encoding="utf-8")
        readiness = (FRONTEND / "ReadinessSuperbatch.tsx").read_text(encoding="utf-8")
        self.assertIn('error?"OPERATING VIEW UNAVAILABLE":"ASSEMBLING THE FIRM VIEW"', operating)
        self.assertIn('error?"READINESS UNAVAILABLE":"ASSEMBLING THE CAPITAL DOSSIER"', readiness)

    def test_authority_and_unknown_value_contracts_remain_fail_closed(self):
        expansion = (FRONTEND / "MobExpansionWing.tsx").read_text(encoding="utf-8")
        provider = (FRONTEND / "ExpansionWingSnapshotProvider.tsx").read_text(encoding="utf-8")
        self.assertIn("UNKNOWN IS NOT ZERO", expansion)
        self.assertIn('publisherControl: false', provider)
        self.assertIn('state: "FAILED_CLOSED"', provider)
        self.assertIn('state: "UNAVAILABLE"', provider)
        self.assertIn('state: "STALE"', provider)


if __name__ == "__main__":
    unittest.main()
