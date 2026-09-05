from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).parents[3]
SCRIPT = REPOSITORY / "scripts" / "iios_factory_browser_preview.py"
FRONTEND = REPOSITORY / "FRONT END" / "src"
CANONICAL_COMMIT = "5ad6a68182f92dd4d6f8910b440f63914490c572"


def load_preview_module():
    spec = importlib.util.spec_from_file_location("iios_unified_preview_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("PREVIEW_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCompositor:
    def __init__(self) -> None:
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {
            "schema_version": "expansion-wing-sanitized-snapshot-v1",
            "mode": "LIVE_READ_ONLY",
            "sections": {},
            "authority": {"broker": False, "ledger_write": False, "live_execution": False},
        }


class UnifiedPreviewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_preview_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "index.html").write_text("<main>INTELLIGENCE IIOS FACTORY</main>", encoding="utf-8")
        self.compositor = FakeCompositor()
        self.server = self.module.PreviewServer(
            ("127.0.0.1", 0), self.root, self.root, self.root, self.root / "paper.db",
            expansion_enabled=True, expansion_compositor=self.compositor,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(self, method: str, path: str):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read()
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, body

    def test_same_origin_snapshot_is_cached_and_browser_safe(self):
        first = self.request("GET", "/expansion-wing/snapshot")
        second = self.request("GET", "/expansion-wing/snapshot")
        self.assertEqual((first[0], second[0], self.compositor.calls), (200, 200, 1))
        payload = json.loads(first[2])
        self.assertEqual(payload["mode"], "LIVE_READ_ONLY")
        self.assertNotIn("Access-Control-Allow-Origin", first[1])
        self.assertFalse(any(key in first[2].decode().lower() for key in ("credential_value", "session_results", "source_path")))

    def test_head_and_mutation_boundary(self):
        status, _, body = self.request("HEAD", "/expansion-wing/snapshot")
        self.assertEqual((status, body), (200, b""))
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _, body = self.request(method, "/expansion-wing/snapshot")
            self.assertEqual(status, 405)
            self.assertEqual(json.loads(body)["status"], "METHOD_NOT_ALLOWED")

    def test_disabled_projection_route_fails_closed(self):
        self.server.expansion_enabled = False
        status, _, body = self.request("GET", "/expansion-wing/snapshot")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {"status": "EXPANSION_WING_NOT_ACTIVATED"})


class UnifiedFrontendContractTests(unittest.TestCase):
    def test_canonical_asset_provenance(self):
        expected = {
            "assets/v752/max-cinematic.webp": "8c5fa737a6a91402f89f3ea4814df3e3d2ce841672882bd2225985e433bfd543",
            "assets/v752/policy-move.webp": "3fd62024e100cd9aa54b40783fbeb5ad68f9744794eab31f56a6c0367fd7e7ab",
            "assets/v752/macro-move.webp": "b57a5c8cd60114d5e27d40af06ca182563ac2136c0a4fb13adb690a4935d50ce",
            "assets/v752/fundamentals-move.webp": "400d5aa49971338e126363132b81189fdf0536a107cdeef87c59ee43af2267ce",
            "assets/v752/skeptic-move.webp": "6b8a5142dda59fd02459c334515f88830bd75ec5cd8c08c7b76fc7f0260aebba",
            "assets/v752/portfolio-move.webp": "115e1384137930b1cdfe65a559299ff1bfaee1ac6b07891756d040996e54b2ce",
            "CinematicFactoryThemeV6.css": "42bb6743bdb597424434bc2113a8cf97482d82329fac633e47670d2b9b8046ae",
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((FRONTEND / name).read_bytes()).hexdigest(), digest)

    def test_room_registry_lanes_and_character_contracts(self):
        source = (FRONTEND / "MobExpansionWing.tsx").read_text(encoding="utf-8")
        for room in ("Main Factory Floor", "Expansion Wing", "Multi-Asset Trading Floor", "Candidate Conveyor",
                     "Professional Strategy Observatory", "Research Laboratory", "Committee Room", "Risk Inspection",
                     "Paper Portfolio Office", "Outcome Learning Theater", "Evidence Warehouse", "Control Room"):
            target = source if room != "Main Factory Floor" else (FRONTEND / "LiveFactoryBrowser.tsx").read_text()
            self.assertIn(room.upper(), target.upper())
        for lane in ("U.S. Equities", "Equity ETFs", "Treasury Rates", "Bond Proxies", "Commodity Proxies",
                     "FX Proxies", "Crypto Reference", "Listed Options", "Intraday", "Relative Value"):
            self.assertIn(lane, source)
        for character in ("MAX", "Policy Analyst", "Macro Analyst", "Sector / Market Analyst", "Historical Analyst",
                          "Professional Research Liaison", "Skeptic / Red Team", "Risk Keeper", "Portfolio Office"):
            self.assertIn(character, source)
        self.assertIn("slice(0, 5)", source)
        self.assertIn("Aggregate counts cannot grow nameplates", source)

    def test_one_projection_polling_owner_and_no_publisher_route(self):
        provider = (FRONTEND / "ExpansionWingSnapshotProvider.tsx").read_text(encoding="utf-8")
        browser_sources = "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND.glob("*.tsx"))
        self.assertEqual(browser_sources.count("/expansion-wing/snapshot"), 1)
        self.assertIn("const POLL_MS = 15_000", provider)
        self.assertNotIn("/publish", browser_sources)
        self.assertNotIn("projection_publisher", browser_sources)

    def test_truth_accessibility_and_responsive_contracts(self):
        source = (FRONTEND / "MobExpansionWing.tsx").read_text(encoding="utf-8")
        styles = (FRONTEND / "MobExpansionWing.css").read_text(encoding="utf-8")
        for phrase in ("current projection artifact does not make stale market evidence current",
                       "UNKNOWN IS NOT ZERO", "Publisher health remains unavailable", "aria-pressed", "Technical details"):
            self.assertIn(phrase.lower(), source.lower())
        self.assertIn("repeat(4,minmax(0,1fr))", styles)
        self.assertIn("repeat(2,minmax(0,1fr))", styles)
        self.assertIn("grid-template-columns:minmax(0,1fr)", styles)
        self.assertIn("min-width:0", styles)
        self.assertIn("overflow-x:clip", styles)
        self.assertIn("prefers-reduced-motion:reduce", styles)

    def test_feed_identity_excludes_sequence_and_timestamp_churn(self):
        source = (FRONTEND / "MobExpansionWing.tsx").read_text(encoding="utf-8")
        feed = source[source.index("function Feed"):source.index("function ControlRoom")]
        self.assertNotIn("activation.sequence", feed)
        self.assertNotIn("generated_at", feed)
        self.assertIn("new Map", feed)


if __name__ == "__main__":
    unittest.main()
