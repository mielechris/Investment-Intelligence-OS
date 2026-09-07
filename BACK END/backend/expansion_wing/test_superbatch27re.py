import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from expansion_wing.operational_rehearsal import ClockObservation, record_authentic_rehearsal
from expansion_wing.preview_server import PreviewApplication
from expansion_wing.tuesday_controller_state import (
    ControllerStateStore, ControllerStatusReader, _atomic, _hash, disabled_state,
    installation_manifest,
)
from expansion_wing.tuesday_controller_v2 import (
    AUTHENTIC_RECEIPT_TYPE, LAST_KNOWN_VALID_NAME, migrate_store_atomic,
)

STAMP = "2026-09-07T00:00:00+00:00"
APPROVAL = "2026-09-07T16:00:00+00:00"
NOW = datetime(2026, 9, 7, 16, 1, tzinfo=timezone.utc)


class ControllerCoherenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "state"
        self.install = installation_manifest("controller-27re", installed=True, registered=True, running=False, generated_at=STAMP)
        self.v1 = disabled_state("controller-27re", installed=True, running=False, updated_at=STAMP)
        self.store = ControllerStateStore(self.root)
        self.store.initialize(self.install, self.v1)
        self.pre = migrate_store_atomic(self.store, timestamp="2026-09-07T00:01:00+00:00")

    def tearDown(self): self.temp.cleanup()

    def clock(self):
        return ClockObservation(NOW.astimezone(__import__("zoneinfo").ZoneInfo("America/Los_Angeles")), NOW, "UNAVAILABLE")

    def test_no_receipt_then_add_then_byte_exact_rollback(self):
        before_bytes = (self.root / "controller-state.json").read_bytes()
        before = ControllerStatusReader(self.root).read()
        self.assertEqual(before["authentic_rehearsal_status"], "NOT_YET_RECORDED")
        record_authentic_rehearsal(self.store, approval_identity="owner-approval-27re", approval_timestamp=APPROVAL, clock=self.clock)
        present = ControllerStatusReader(self.root).read()
        self.assertEqual(present["authentic_rehearsal_status"], "PASSED_CLOSED_HOLIDAY")
        self.assertNotEqual(before["controller_generation_sequence"], present["controller_generation_sequence"])
        (self.root / "controller-state.json").write_bytes(before_bytes); os.chmod(self.root / "controller-state.json", 0o600)
        _atomic(self.root, LAST_KNOWN_VALID_NAME, self.pre)
        rolled = ControllerStatusReader(self.root).read()
        self.assertEqual(rolled["authentic_rehearsal_status"], "NOT_YET_RECORDED")

    def test_same_mtime_different_bytes_changes_private_identity(self):
        reader = ControllerStatusReader(self.root)
        first = reader.cache_identity(); path = self.root / "controller-state.json"; times = (path.stat().st_atime_ns, path.stat().st_mtime_ns)
        state = json.loads(path.read_text()); state["sequence"] += 1; state["last_known_valid"] = {"schema_version": self.pre["schema_version"], "sequence": self.pre["sequence"], "content_hash": self.pre["content_hash"]}; state["content_hash"] = _hash(state)
        path.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"); os.chmod(path, 0o600); os.utime(path, ns=times)
        self.assertNotEqual(first, reader.cache_identity())

    def test_state_change_during_read_retries_then_succeeds(self):
        reader = ControllerStatusReader(self.root); original = reader._state_bytes; calls = 0
        def changing():
            nonlocal calls
            calls += 1
            return original() + (b"x" if calls == 2 else b"")
        with patch.object(reader, "_state_bytes", side_effect=changing):
            self.assertEqual(reader.read()["authentic_rehearsal_status"], "NOT_YET_RECORDED")
        self.assertGreaterEqual(calls, 4)

    def test_retry_exhaustion_and_lkv_mismatch_fail_closed_then_recover(self):
        reader = ControllerStatusReader(self.root)
        with patch.object(reader, "_state_bytes", side_effect=[b"a", b"b"] * 3):
            self.assertEqual(reader.read()["error_category"], "CONTROLLER_STATUS_FAILED_CLOSED")
        self.assertEqual(reader.read()["authentic_rehearsal_status"], "NOT_YET_RECORDED")
        lkv = json.loads((self.root / LAST_KNOWN_VALID_NAME).read_text()); lkv["sequence"] += 1; lkv["content_hash"] = _hash(lkv); _atomic(self.root, LAST_KNOWN_VALID_NAME, lkv)
        self.assertEqual(reader.read()["error_category"], "CONTROLLER_STATUS_FAILED_CLOSED")

    def test_browser_projection_has_only_sanitized_generation_metadata(self):
        value = ControllerStatusReader(self.root).read(); encoded = json.dumps(value)
        self.assertIsInstance(value["controller_generation_sequence"], int)
        self.assertIsInstance(value["controller_read_timestamp"], str)
        for prohibited in ("content_hash", "installation_identity", str(self.root)):
            self.assertNotIn(prohibited, encoded)

    def test_no_mutation_interfaces_are_present(self):
        source = Path(__file__).with_name("tuesday_controller_state.py").read_text()
        self.assertIn("MAX_COHERENT_READ_ATTEMPTS = 3", source)
        self.assertNotIn("urlopen", source)
        self.assertNotIn("Keychain", source)

    def test_cache_invalidates_on_generation_and_does_not_retain_failure(self):
        static = Path(self.temp.name) / "www"; static.mkdir(); (static / "index.html").write_text("ok")
        snapshots = [
            {"sections": {"tuesday_controller_status": {"state": "INSTALLED_BUT_DISABLED", "data": {"authentic_rehearsal_status": "NOT_YET_RECORDED"}}}},
            {"sections": {"tuesday_controller_status": {"state": "INSTALLED_BUT_DISABLED", "data": {"authentic_rehearsal_status": "PASSED_CLOSED_HOLIDAY"}}}},
            {"sections": {"tuesday_controller_status": {"state": "FAILED_CLOSED", "data": None}}},
            {"sections": {"tuesday_controller_status": {"state": "INSTALLED_BUT_DISABLED", "data": {"authentic_rehearsal_status": "NOT_YET_RECORDED"}}}},
        ]
        class Fake:
            def snapshot(self): return snapshots.pop(0)
        generations = iter([("v2", 1), ("v2", 2), None, ("v2", 1)])
        app = PreviewApplication(static, Fake(), cache_seconds=60, controller_generation_reader=lambda: next(generations))
        self.assertEqual(app.snapshot(now=0)["sections"]["tuesday_controller_status"]["data"]["authentic_rehearsal_status"], "NOT_YET_RECORDED")
        self.assertEqual(app.snapshot(now=1)["sections"]["tuesday_controller_status"]["data"]["authentic_rehearsal_status"], "PASSED_CLOSED_HOLIDAY")
        self.assertEqual(app.snapshot(now=2)["sections"]["tuesday_controller_status"]["state"], "FAILED_CLOSED")
        self.assertEqual(app.snapshot(now=3)["sections"]["tuesday_controller_status"]["data"]["authentic_rehearsal_status"], "NOT_YET_RECORDED")

    def test_private_cache_identity_binds_receipt_set(self):
        reader = ControllerStatusReader(self.root); before = reader.cache_identity()
        record_authentic_rehearsal(self.store, approval_identity="owner-approval-27re", approval_timestamp=APPROVAL, clock=self.clock)
        after = reader.cache_identity()
        self.assertNotEqual(before, after)
        self.assertEqual(len(before), 5); self.assertEqual(len(after), 5)


if __name__ == "__main__": unittest.main()
