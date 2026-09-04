from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from expansion_wing.acquisition_queue import OfficialSourceQueue, QueuedSource
from expansion_wing.archive_backup import authorize_deletion, backup_manifest, retention_expired, verify_restore
from expansion_wing.encrypted_archive import (EphemeralTestKeyProvider, FixtureAuthenticatedCipher,
    MacOSKeychainAdapter, atomic_write, open_envelope, rotate, seal)
from expansion_wing.knowledge_pipeline import room_projection
from expansion_wing.quarantine import InactiveScanner, stage
from expansion_wing.review_console import ACTIONS, ReviewCase
from expansion_wing.sec_compliance import MockableSECThrottle, SECContactConfig
from expansion_wing.transcription_bakeoff import CandidatePolicy, evaluate_fixture, recommendation_packet


class CleanScanner:
    def scan(self, _payload): return "CLEAN"


class EncryptionTests(unittest.TestCase):
    def setUp(self):
        self.cipher = FixtureAuthenticatedCipher()
        self.keys = EphemeralTestKeyProvider({"k1": b"1" * 32, "k2": b"2" * 32})

    def test_round_trip_wrong_key_and_ciphertext_tamper(self):
        encoded = seal(b"synthetic private fixture", "k1", self.keys, self.cipher)
        self.assertEqual(open_envelope(encoded, self.keys, self.cipher), b"synthetic private fixture")
        wrong = EphemeralTestKeyProvider({"k1": b"9" * 32})
        with self.assertRaises(RuntimeError): open_envelope(encoded, wrong, self.cipher)
        value = json.loads(encoded); raw = bytearray(__import__("base64").b64decode(value["ciphertext"])); raw[0] ^= 1
        value["ciphertext"] = __import__("base64").b64encode(raw).decode()
        with self.assertRaises(RuntimeError): open_envelope(json.dumps(value).encode(), self.keys, self.cipher)

    def test_interrupted_atomic_write_recovery_and_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "archive" / "value.enc"; atomic_write(target, b"old")
            with self.assertRaises(RuntimeError):
                atomic_write(target, b"new", before_replace=lambda: (_ for _ in ()).throw(RuntimeError("fixture")))
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            self.assertFalse(any(path.name.startswith(".encrypted-") for path in target.parent.iterdir()))

    def test_rotation_and_keychain_failure_are_fail_closed(self):
        encoded = seal(b"fixture", "k1", self.keys, self.cipher)
        rotated = rotate(encoded, self.keys, "k2", self.keys, self.cipher)
        self.assertEqual(open_envelope(rotated, self.keys, self.cipher), b"fixture")
        with self.assertRaises(RuntimeError): rotate(encoded, self.keys, "missing", self.keys, self.cipher)
        with self.assertRaises(RuntimeError): MacOSKeychainAdapter().key("anything")
        self.assertFalse(self.cipher.operationally_approved)


class QuarantineTests(unittest.TestCase):
    def test_owner_only_fixture_staging_and_mime(self):
        with tempfile.TemporaryDirectory() as temp:
            wav = b"RIFF" + (4).to_bytes(4, "little") + b"WAVEfixture"
            result = stage(Path(temp) / "q", "fixture.wav", wav, duration_seconds=1, scanner=CleanScanner())
            self.assertEqual(result["status"], "QUARANTINED"); self.assertFalse(result["executed"])
            stored = next((Path(temp) / "q").iterdir())
            self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(stored.parent.stat().st_mode), 0o700)

    def test_traversal_executable_archive_polyglot_mime_and_scanner_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "q"
            cases = (("../x.txt", b"text", "TRAVERSAL_NAME_REJECTED"), ("x.txt", b"MZbad", "EXECUTABLE_OR_ARCHIVE_REJECTED"),
                ("x.txt", b"PK\x03\x04bad", "EXECUTABLE_OR_ARCHIVE_REJECTED"),
                ("x.txt", b"safe MZbad", "POLYGLOT_REJECTED"), ("x.wav", b"not wave", "MIME_MISMATCH"))
            for name, payload, reason in cases:
                with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                    stage(root, name, payload, duration_seconds=1, scanner=CleanScanner())
            self.assertEqual(stage(root, "x.txt", b"safe text", duration_seconds=1,
                scanner=InactiveScanner())["reason"], "SCANNER_NOT_CONFIGURED")

    def test_existing_content_address_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "q"; root.mkdir(); payload = b"safe text"
            target = root / f"{hashlib.sha256(payload).hexdigest()}.txt"; target.symlink_to(Path(temp) / "elsewhere")
            with self.assertRaisesRegex(ValueError, "SYMLINK_REJECTED"):
                stage(root, "safe.txt", payload, duration_seconds=1, scanner=CleanScanner())


class GovernanceTests(unittest.TestCase):
    def test_all_review_actions_require_identity_audit_and_no_automation(self):
        for action in ACTIONS:
            case = ReviewCase(action, action)
            with self.assertRaises(ValueError): case.decide("APPROVED", reviewer="", timestamp="t", reason="r", previous_hash="0" * 64)
            event = case.decide("APPROVED", reviewer="fixture-reviewer", timestamp="2026-09-03T00:00:00Z",
                reason="fixture evidence reviewed", previous_hash="0" * 64)
            self.assertEqual(len(event["event_hash"]), 64); self.assertFalse(event["automatic"])
            self.assertFalse(case.handoff()["automatic_mutation"])

    def test_sec_contact_mocked_serialization_backoff_and_403_respect(self):
        with self.assertRaises(RuntimeError): SECContactConfig("IIOS", "", False).user_agent()
        times = iter((0.0, 0.0, 0.2, 1.0, 1.0, 1.0)); sleeps = []; calls = []
        gate = MockableSECThrottle(SECContactConfig("IIOS Research", "review@example.invalid", True),
            clock=lambda: next(times), sleeper=sleeps.append)
        self.assertEqual(gate.request(lambda ua: calls.append(ua) or 200), "SUCCESS")
        self.assertEqual(gate.request(lambda ua: calls.append(ua) or 403), "ACCESS_POLICY_REJECTED")
        self.assertEqual(len(calls), 2); self.assertTrue(sleeps); self.assertIn("contact:", calls[0])
        with self.assertRaises(ValueError): MockableSECThrottle(SECContactConfig("x", "x@y.z", True), requests_per_second=2)

    def test_queue_domain_rights_dedup_backpressure_and_terminal_failure(self):
        queue = OfficialSourceQueue({"www.sec.gov"}, max_depth=1)
        item = QueuedSource("s1", "www.sec.gov", 1, "SEC_FILING", "APPROVED", "2026-09-04", 1)
        self.assertEqual(queue.admit(item), "QUEUED"); self.assertEqual(queue.admit(item), "DUPLICATE")
        self.assertEqual(queue.admit(QueuedSource("s2", "www.sec.gov", 1, "SEC_FILING", "APPROVED", "t")), "BACKPRESSURE")
        self.assertEqual(queue.record_attempt("s1", successful=False), "TERMINAL_FAILURE")
        self.assertFalse(queue.view()["scheduled"] or queue.view()["network_execution"])
        self.assertEqual(OfficialSourceQueue(set()).admit(item), "REJECTED_DOMAIN")

    def test_backup_restore_retention_and_deletion_authorization(self):
        records = {"notes/a.enc": b"encrypted-a", "claims/b.enc": b"encrypted-b"}; manifest = backup_manifest(records, key_id="k1")
        encrypted_manifest = seal(json.dumps(manifest, sort_keys=True).encode(), "k1",
            EphemeralTestKeyProvider({"k1": b"1" * 32}), FixtureAuthenticatedCipher())
        self.assertNotIn(b"notes/a.enc", encrypted_manifest)
        self.assertEqual(verify_restore(manifest, records), "VERIFIED")
        self.assertEqual(verify_restore(manifest, {"notes/a.enc": b"encrypted-a"}), "PARTIAL_RESTORE")
        self.assertEqual(verify_restore(manifest, {**records, "claims/b.enc": b"bad"}), "HASH_MISMATCH")
        with self.assertRaises(PermissionError): authorize_deletion("a" * 64, reviewer="r", timestamp="t", reason="x", human_authorized=False)
        tombstone = authorize_deletion("a" * 64, reviewer="r", timestamp="t", reason="expired", human_authorized=True)
        self.assertTrue(tombstone["tombstone"]); self.assertFalse(tombstone["private_content_retained"])
        self.assertTrue(retention_expired("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", 30))

    def test_truthful_room_operations_and_key_status(self):
        view = room_projection({"quarantine_count": 1, "rights_review_queue_count": 2,
            "transcript_correction_count": 1, "speaker_attribution_count": 1, "professional_approval_count": 1,
            "contradiction_case_count": 2, "judgment_handoff_ready_count": 0, "pattern_handoff_ready_count": 0,
            "encryption_key_status": "NOT_CONFIGURED"})
        self.assertEqual(view["Investor Archive"]["data"]["encryption_key_status"], "NOT_CONFIGURED")
        self.assertEqual(view["Interview Studio"]["data"]["quarantine_count"], 1)
        with self.assertRaises(ValueError): room_projection({"encryption_key_status": "KEY_BYTES"})

    def test_transcription_recommendation_packet_remains_zero_cost_and_inactive(self):
        class Adapter:
            name = "offline-fixture"; provider_activated = False
            def transcribe(self, _audio): return {"text": "synthetic words", "speakers": ("A",), "timestamps": (0,), "latency_ms": 2}
        result = evaluate_fixture(Adapter(), CandidatePolicy(True, True, True, 0.0, True), audio=b"fixture",
            reference="synthetic words", expected_speakers=("A",))
        packet = recommendation_packet([result])
        self.assertEqual(packet["recommended_candidate"], "offline-fixture")
        self.assertFalse(packet["provider_activation"]); self.assertTrue(packet["human_approval_required"])


if __name__ == "__main__": unittest.main()
