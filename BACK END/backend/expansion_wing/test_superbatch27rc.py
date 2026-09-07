from __future__ import annotations

import copy, io, json, os, tempfile, unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from .operational_rehearsal import ClockObservation, _receipt, record_authentic_rehearsal, system_clock
from .tuesday_controller_state import ControllerStateStore, _hash, disabled_state, installation_manifest
from .tuesday_controller_v2 import AUTHENTIC_RECEIPT_TYPE, LAST_KNOWN_VALID_NAME, browser_projection_v2, migrate_v1_to_v2, validate_state_v2

STAMP = "2026-09-07T18:00:00+00:00"
APPROVAL = "2026-09-07T17:59:00+00:00"
IDENTITY = "opaque-owner-approval-27rc"


class AuthenticOperationalRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name) / "state"
        self.install = installation_manifest("controller-install-27rc", installed=True, registered=True, running=False, generated_at=STAMP)
        old = disabled_state("controller-install-27rc", installed=True, running=False, updated_at=STAMP)
        self.v2 = migrate_v1_to_v2(old, self.install, timestamp=STAMP)
        self.store = ControllerStateStore(self.root); self.store.initialize(self.install, self.v2)
        local = datetime(2026, 9, 7, 11, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        self.clock = lambda: ClockObservation(local, local.astimezone(timezone.utc), "UNAVAILABLE")

    def tearDown(self): self.temp.cleanup()
    def record(self): return record_authentic_rehearsal(self.store, approval_identity=IDENTITY, approval_timestamp=APPROVAL, clock=self.clock)

    def test_compatibility_receipt_is_preserved_and_not_operational_proof(self):
        before = copy.deepcopy(self.v2["rehearsal_receipts"][0]); projection = browser_projection_v2(self.v2, running=False)
        self.assertEqual(projection["authentic_rehearsal_status"], "NOT_YET_RECORDED")
        self.assertEqual(projection["compatibility_rehearsal_status"], "MIGRATED_COMPATIBILITY_RECEIPT_NOT_OPERATIONAL_PROOF")
        self.assertEqual(self.record()["rehearsal_receipts"][0], before)

    def test_authentic_receipt_is_strict_immutable_and_zero_activity(self):
        before = copy.deepcopy(self.v2); result = self.record(); receipt = result["rehearsal_receipts"][-1]
        self.assertEqual(receipt["receipt_type"], AUTHENTIC_RECEIPT_TYPE); self.assertEqual(receipt["classification"], "PASSED_CLOSED_HOLIDAY")
        self.assertEqual((receipt["observed_local_date"], receipt["observed_weekday"], receipt["session"]), ("2026-09-07", "MONDAY", "CLOSED_HOLIDAY"))
        self.assertEqual(receipt["network_time_verification"], "UNAVAILABLE"); self.assertEqual(result["sequence"], before["sequence"] + 1)
        for key in ("phase", "phase_history", "confirmed_credits", "ambiguous_credits", "requests_used", "request_identities", "stages", "authority", "authority_locked", "activated", "released_credit_total"):
            self.assertEqual(result[key], before[key])
        self.assertEqual(browser_projection_v2(result, running=False)["authentic_rehearsal_status"], "PASSED_CLOSED_HOLIDAY")

    def test_duplicate_and_ambiguous_receipts_fail_closed_without_rewrite(self):
        result = self.record(); saved = (self.root / "controller-state.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_REHEARSAL_RECEIPT"): self.record()
        self.assertEqual((self.root / "controller-state.json").read_bytes(), saved)
        bad = copy.deepcopy(result); duplicate = copy.deepcopy(bad["rehearsal_receipts"][-1]); duplicate["immutable_receipt_id"] = "rehearsal-" + "1" * 64
        from .tuesday_controller_v2 import _receipt_hash
        duplicate["canonical_content_hash"] = _receipt_hash(duplicate); bad["rehearsal_receipts"].append(duplicate); bad["content_hash"] = _hash(bad)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_REHEARSAL_RECEIPT"): validate_state_v2(bad, self.install)

    def test_clock_calendar_session_and_approval_fail_closed(self):
        for local in (datetime(2026, 9, 6, 11, tzinfo=ZoneInfo("America/Los_Angeles")), datetime(2026, 9, 7, 11, tzinfo=timezone.utc)):
            with self.subTest(local=local), self.assertRaisesRegex(ValueError, "SYSTEM_CLOCK_CONTRACT_INVALID"):
                _receipt(self.v2, approval_identity=IDENTITY, approval_timestamp=APPROVAL, observation=ClockObservation(local, local.astimezone(timezone.utc), "UNAVAILABLE"))
        with patch("expansion_wing.operational_rehearsal.market_session", return_value={"state": "OPEN"}):
            with self.assertRaisesRegex(ValueError, "CALENDAR_SESSION_INVALID"): self.record()
        with self.assertRaisesRegex(ValueError, "APPROVAL_TIMESTAMP_INVALID"):
            record_authentic_rehearsal(self.store, approval_identity=IDENTITY, approval_timestamp="2026-09-08T00:00:00Z", clock=self.clock)

    def test_invalid_network_category_tamper_lock_and_state_fail_closed(self):
        local = datetime(2026, 9, 7, 11, tzinfo=ZoneInfo("America/Los_Angeles"))
        with self.assertRaisesRegex(ValueError, "AUTHENTIC_REHEARSAL_CLOCK_INVALID"):
            record_authentic_rehearsal(self.store, approval_identity=IDENTITY, approval_timestamp=APPROVAL, clock=lambda: ClockObservation(local, local.astimezone(timezone.utc), "ASSUMED"))
        lock = self.store.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "DUPLICATE_SUPERVISOR"): self.record()
        finally: lock.close()
        result = self.record(); bad = copy.deepcopy(result); bad["rehearsal_receipts"][-1]["classification"] = "PASSED"; bad["content_hash"] = _hash(bad)
        with self.assertRaisesRegex(ValueError, "AUTHENTIC_REHEARSAL_CLASSIFICATION_INVALID"): validate_state_v2(bad, self.install)

    def test_atomic_modes_lkv_and_restart_validation(self):
        result = self.record()
        for name in ("controller-state.json", LAST_KNOWN_VALID_NAME):
            path = self.root / name; self.assertTrue(path.is_file() and not path.is_symlink()); self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        installation, recovered = self.store.read(recover=False)
        self.assertEqual(validate_state_v2(recovered, installation)["content_hash"], result["content_hash"])

    def test_explicit_command_lifecycle_duplicate_and_byte_exact_rollback(self):
        from .tuesday_controller_service import main
        before_install = (self.root / "installation.json").read_bytes(); before_state = (self.root / "controller-state.json").read_bytes()
        args = ["--rehearse-closed-holiday", "--state-root", str(self.root), "--approval-identity", IDENTITY, "--approval-timestamp", APPROVAL]
        output = io.StringIO()
        with redirect_stdout(output): self.assertEqual(main(args, rehearsal_clock=self.clock), 0)
        self.assertEqual(json.loads(output.getvalue()), {"status": "AUTHENTIC_REHEARSAL_RECORDED"})
        sequence = self.store.read()[1]["sequence"]; output = io.StringIO()
        with redirect_stdout(output): self.assertEqual(main(args, rehearsal_clock=self.clock), 6)
        self.assertEqual(self.store.read()[1]["sequence"], sequence)
        for path in self.root.iterdir(): path.unlink()
        (self.root / "installation.json").write_bytes(before_install); os.chmod(self.root / "installation.json", 0o600)
        (self.root / "controller-state.json").write_bytes(before_state); os.chmod(self.root / "controller-state.json", 0o600)
        self.assertEqual((self.root / "installation.json").read_bytes(), before_install); self.assertEqual((self.root / "controller-state.json").read_bytes(), before_state)

    def test_environment_cannot_override_clock_or_calendar(self):
        source = Path(__file__).with_name("operational_rehearsal.py").read_text(); self.assertNotIn("os.environ", source); self.assertNotIn("getenv", source)
        with patch.dict(os.environ, {"IIOS_DATE": "2026-09-07", "IIOS_SESSION": "CLOSED_HOLIDAY"}):
            local = datetime(2026, 9, 8, 11, tzinfo=ZoneInfo("America/Los_Angeles"))
            with self.assertRaisesRegex(ValueError, "SYSTEM_CLOCK_CONTRACT_INVALID"):
                record_authentic_rehearsal(self.store, approval_identity=IDENTITY, approval_timestamp=APPROVAL, clock=lambda: ClockObservation(local, local.astimezone(timezone.utc), "VERIFIED"))

    def test_system_clock_and_no_browser_automatic_surface(self):
        class Result: returncode = 1; stdout = b"private"; stderr = b"private"
        with patch("expansion_wing.operational_rehearsal.subprocess.run", return_value=Result()) as run: observation = system_clock()
        self.assertEqual(observation.network_time_verification, "UNAVAILABLE"); self.assertEqual(run.call_args.args[0], ["/usr/sbin/systemsetup", "-getusingnetworktime"]); self.assertFalse(run.call_args.kwargs["shell"])
        writer = Path(__file__).with_name("operational_rehearsal.py").read_text(); self.assertNotIn("HTTPServer", writer); self.assertNotIn("provider", writer.lower()); self.assertNotIn("keychain", writer.lower())


if __name__ == "__main__": unittest.main()
