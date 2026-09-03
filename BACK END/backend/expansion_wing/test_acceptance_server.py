from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expansion_wing import acceptance_server as server


def telemetry(**overrides):
    value = {
        "schema_version": server.TELEMETRY_SCHEMA, "generated_at": "2026-09-03T22:50:00+00:00",
        "cadence": {"observation": {"availability": "AVAILABLE"}, "paper_trading": {"availability": "AVAILABLE"}},
        "radar": {"last_cycle_completed_at": "2026-09-03T22:50:00+00:00"},
        "paper_fund": {"snapshot_as_of": "2026-09-03T22:50:00+00:00", "nav": 10000, "cash": 10000},
        "recent_paper_orders": [], "recent_paper_fills": [],
        "safety": {"telemetry_read_only": True, "broker_connected": False,
                   "trade_execution_permission": False, "live_execution": False},
    }
    value.update(overrides); return value


class AcceptanceServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def write(self, name, value):
        path = self.root / name; path.write_text(json.dumps(value)); return path

    def compositor(self, telemetry_value=None, validation=None, shadow=None, outcome=None):
        paths = []
        for index, value in enumerate((telemetry_value, validation, shadow, outcome)):
            paths.append(self.write(f"{index}.json", value) if value is not None else self.root / f"missing-{index}.json")
        result = server.Compositor(*paths, "http://127.0.0.1:8002/system/status")
        result._reachability = lambda: "CURRENT"
        return result

    def test_accepted_schema_versions(self):
        for schema in (server.TELEMETRY_SCHEMA, server.VALIDATION_SCHEMA, server.SHADOW_SCHEMA, server.OUTCOME_SCHEMA):
            self.assertIsNotNone(server._read(self.write(schema, {"schema_version": schema}), schema))

    def test_unknown_schema_and_two_mb_sources_are_rejected(self):
        self.assertIsNone(server._read(self.write("unknown", {"schema_version": "unknown"}), server.TELEMETRY_SCHEMA))
        large = self.root / "large.json"; large.write_bytes(b" " * 2_000_001)
        self.assertIsNone(server._read(large, server.TELEMETRY_SCHEMA))

    def test_missing_9i_is_unavailable_without_private_fallback(self):
        snapshot = self.compositor(telemetry()).snapshot()
        self.assertEqual(snapshot["sections"]["shadow_9i"], {"state": "UNAVAILABLE", "data": {
            "truth_state": "UNAVAILABLE", "reason": "BROWSER_SUMMARY_NOT_AVAILABLE"}})
        self.assertNotIn("latest_" + "shadow_counterfactual.json", Path(server.__file__).read_text())

    def test_unsafe_authority_rejects_telemetry(self):
        value = telemetry(); value["safety"]["live_execution"] = True
        snapshot = self.compositor(value).snapshot()
        self.assertEqual(snapshot["sections"]["books"]["state"], "UNAVAILABLE")

    def test_paper_projection_is_scalar_only(self):
        value = telemetry(); value["paper_fund"].update({"positions": [{"ticker": "PRIVATE"}],
            "position_count": 1, "transaction_count": 2}); value["recent_paper_orders"] = [{"ticker": "PRIVATE"}]
        books = self.compositor(value).snapshot()["sections"]["books"]["data"]
        self.assertEqual((books["positions"], books["transactions"], books["orders"]), (1, 2, 1))
        self.assertNotIn("PRIVATE", json.dumps(books))

    def test_missing_counts_are_not_inferred(self):
        books = self.compositor(telemetry()).snapshot()["sections"]["books"]["data"]
        self.assertIsNone(books["positions"]); self.assertIsNone(books["transactions"])
        value = telemetry(); value.pop("recent_paper_orders"); value.pop("recent_paper_fills")
        books = self.compositor(value).snapshot()["sections"]["books"]["data"]
        self.assertIsNone(books["orders"]); self.assertIsNone(books["fills"])

    def test_one_backend_get_per_snapshot(self):
        compositor = server.Compositor(*(self.root / f"missing-{i}" for i in range(4)),
                                       "http://127.0.0.1:8002/system/status")
        with patch.object(compositor, "_reachability", wraps=compositor._reachability) as reach:
            with patch.object(server, "urlopen", side_effect=OSError):
                compositor.snapshot(); compositor.snapshot()
        self.assertEqual(reach.call_count, 2); self.assertEqual(compositor.backend_requests, 2)
        self.assertEqual(compositor.backend_errors, {"OSError": 2})

    def test_projection_contains_fixed_safety_authority(self):
        snapshot = self.compositor(telemetry()).snapshot()
        self.assertFalse(snapshot["fabricated_activity"])
        self.assertEqual(snapshot["authority"], {"paper_mode": True, "credential_access": False,
            "ledger_write_authority": False, "broker_connectivity": False, "live_execution_authority": False})


class FrontendPollingContractTests(unittest.TestCase):
    def test_one_timer_one_fetch_and_cleanup(self):
        root = Path(__file__).parents[3] / "FRONT END" / "src"
        provider = (root / "ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertEqual(provider.count("setInterval("), 1); self.assertEqual(provider.count("fetch("), 1)
        self.assertIn("15_000", provider); self.assertIn("clearInterval", provider); self.assertIn("controller.abort()", provider)
        for path in root.glob("ExpansionWing*.tsx"):
            if path.name != "ExpansionWingSnapshotProvider.tsx":
                text = path.read_text(); self.assertNotIn("fetch(", text); self.assertNotIn("setInterval(", text)


if __name__ == "__main__": unittest.main()
