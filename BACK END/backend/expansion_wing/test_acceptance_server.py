from __future__ import annotations

import json
import os
import subprocess
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

    def test_cors_origin_is_exact_loopback_only(self):
        self.assertTrue(server._valid_origin("http://127.0.0.1:49452"))
        for value in ("http://localhost:49452", "https://127.0.0.1:49452", "http://127.0.0.1:49452/path", "*"):
            self.assertFalse(server._valid_origin(value))

    def test_browser_outcome_contract_is_read_only_and_current(self):
        outcome = {"schema_version": server.OUTCOME_SCHEMA, "generated_at": "2026-09-03T22:50:00+00:00",
            "status": "CURRENT", "safety": {"read_only_browser_payload": True,
                "auto_write_judgment_bank": False, "trade_execution_permission": False, "live_execution": False}}
        snapshot = self.compositor(telemetry(), outcome=outcome).snapshot()
        self.assertEqual(snapshot["sections"]["outcomes_9j"]["state"], "CURRENT")
        outcome["safety"]["auto_write_judgment_bank"] = True
        self.assertEqual(self.compositor(telemetry(), outcome=outcome).snapshot()["sections"]["outcomes_9j"]["state"], "UNAVAILABLE")


class FrontendPollingContractTests(unittest.TestCase):
    def test_one_timer_one_fetch_and_cleanup(self):
        root = Path(__file__).parents[3] / "FRONT END" / "src"
        provider = (root / "ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertEqual(provider.count("setTimeout("), 1); self.assertEqual(provider.count("fetch("), 1)
        self.assertIn("15_000", provider); self.assertIn("60_000", provider); self.assertIn("clearTimeout", provider)
        self.assertIn("controller?.abort()", provider); self.assertIn("immutableSnapshot", provider)
        self.assertIn('"STALE"', provider); self.assertIn("snapshotAgeSeconds", provider)
        for path in root.glob("ExpansionWing*.tsx"):
            if path.name != "ExpansionWingSnapshotProvider.tsx":
                text = path.read_text(); self.assertNotIn("fetch(", text); self.assertNotIn("setInterval(", text)

    def test_room_presentation_and_dialog_focus_contracts(self):
        root = Path(__file__).parents[3] / "FRONT END" / "src"
        context = (root / "ExpansionWingSnapshotContext.ts").read_text()
        room = (root / "ExpansionWing.tsx").read_text()
        self.assertIn('"NOT_ACTIVATED"', context); self.assertIn('"AVAILABLE_EMPTY"', context)
        for token in ("dialogRef", "openerRef", "requestAnimationFrame", 'event.key === "Escape"',
                      'event.key !== "Tab"', "aria-modal=\"true\""):
            self.assertIn(token, room)

    def test_compact_labels_preserve_semantic_distinctions(self):
        room = (Path(__file__).parents[3] / "FRONT END" / "src" / "ExpansionWing.tsx").read_text()
        self.assertIn('AVAILABLE_FOR_REVIEWED_UPLOAD: "UPLOAD READY"', room)
        self.assertIn('aria-label={`Open ${room.title}, ${state}`}', room)
        self.assertIn('aria-hidden="true">{compactStatus[state]??state}', room)
        self.assertIn('shadow_9i:"9I shadow"', room)
        self.assertIn('title: "Strictness Observatory"', room)
        self.assertNotIn('shadow_9i:"9I strictness"', room)

    def test_build_identity_matrix(self):
        frontend = Path(__file__).parents[3] / "FRONT END"
        base = {key: value for key, value in os.environ.items() if not key.startswith("VITE_EXPANSION_WING_") and key != "VITE_BACKEND_RECOVERY_GREEN"}
        valid = (
            ({"VITE_EXPANSION_WING_APP": "1", "VITE_EXPANSION_WING_FIXTURE": "1"}, True),
            ({"VITE_EXPANSION_WING_APP": "1", "VITE_EXPANSION_WING_LIVE_READONLY": "1", "VITE_BACKEND_RECOVERY_GREEN": "1",
              "VITE_EXPANSION_WING_READONLY_ENDPOINT": "http://127.0.0.1:49451/snapshot"}, True),
            ({}, False),
        )
        for flags, expansion in valid:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as output:
                result = subprocess.run(["npx", "vite", "build", "--outDir", output, "--emptyOutDir"], cwd=frontend,
                    env={**base, **flags}, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                bundle = "".join(path.read_text(errors="replace") for path in Path(output, "assets").glob("*.js"))
                if expansion:
                    self.assertIn("Interview Studio", bundle); self.assertNotIn("THE INTELLIGENCE FACTORY", bundle)
                else:
                    self.assertIn("THE INTELLIGENCE FACTORY", bundle)
        invalid = (
            {"VITE_EXPANSION_WING_APP": "1"},
            {"VITE_EXPANSION_WING_FIXTURE": "1"},
            {"VITE_EXPANSION_WING_APP": "1", "VITE_EXPANSION_WING_LIVE_READONLY": "1"},
            {"VITE_EXPANSION_WING_APP": "1", "VITE_EXPANSION_WING_FIXTURE": "1",
             "VITE_EXPANSION_WING_LIVE_READONLY": "1", "VITE_BACKEND_RECOVERY_GREEN": "1",
             "VITE_EXPANSION_WING_READONLY_ENDPOINT": "http://127.0.0.1:49451/snapshot"},
        )
        for flags in invalid:
            with self.subTest(invalid=flags), tempfile.TemporaryDirectory() as output:
                result = subprocess.run(["npx", "vite", "build", "--outDir", output, "--emptyOutDir"], cwd=frontend,
                    env={**base, **flags}, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)


class RoomProjectionTests(unittest.TestCase):
    def test_truthful_empty_and_not_activated_rooms(self):
        fixture = AcceptanceServerTests(); fixture.setUp()
        try:
            snapshot = fixture.compositor(telemetry()).snapshot(); rooms = snapshot["room_states"]
            self.assertEqual(rooms["Interview Studio"]["presentation_status"], "AVAILABLE_FOR_REVIEWED_UPLOAD")
            self.assertFalse(rooms["Interview Studio"]["data"]["active_interviews_claimed"])
            self.assertEqual(rooms["Investor Archive"]["presentation_status"], "NOT_ACTIVATED")
            self.assertEqual(rooms["Pattern Laboratory"]["presentation_status"], "AVAILABLE_EMPTY")
            self.assertEqual(rooms["Strategy Incubator"]["presentation_status"], "AVAILABLE_EMPTY")
            self.assertEqual(rooms["Learning Theater"]["presentation_status"], "AVAILABLE_EMPTY")
        finally: fixture.tearDown()

    def test_strictness_does_not_score_incomplete_validation(self):
        fixture = AcceptanceServerTests(); fixture.setUp()
        try:
            validation = {"schema_version": server.VALIDATION_SCHEMA, "generated_at": "2026-09-03T22:50:00+00:00",
                          "benchmark_complete": False, "metrics": {}, "status": "VALIDATION_INCOMPLETE"}
            room = fixture.compositor(telemetry(), validation=validation).snapshot()["room_states"]["Strictness Observatory"]
            self.assertEqual(room["state"], "INCOMPLETE"); self.assertFalse(room["data"]["performance_calculated"])
            self.assertTrue(room["data"]["simulation_only"])
        finally: fixture.tearDown()

    def test_opportunity_passport_is_compact_and_non_executing(self):
        fixture = AcceptanceServerTests(); fixture.setUp()
        try:
            value = telemetry(recent_promotions=[{"source_candidate_id": "private-id", "ticker": "FIX",
                "promoted_at": "2026-09-03T22:50:00+00:00", "committee": {"confidence": .9, "disposition": "APPROVED"},
                "risk": {"decision": "APPROVED"}, "qualification": {"qualified_buy_candidate": True},
                "prompt": "NEVER_EMIT", "opportunity_score": 99.9}])
            passport = fixture.compositor(value).snapshot()["sections"]["radar"]["data"]["opportunity_passports"][0]
            self.assertEqual(passport["classification"], "OBSERVATION_ONLY")
            self.assertEqual(passport["confidence_category"], "HIGH")
            self.assertFalse(any(passport["authority"].values()))
            encoded = json.dumps(passport)
            for prohibited in ("private-id", "NEVER_EMIT", "prompt", "opportunity_score"):
                self.assertNotIn(prohibited, encoded)
        finally: fixture.tearDown()


if __name__ == "__main__": unittest.main()
