from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from expansion_wing.interview_intake import stage_reviewed_upload
from expansion_wing.knowledge_pipeline import room_projection
from expansion_wing.official_acquisition import AcquisitionPolicy, OfficialSourceAcquirer, TransportResponse
from expansion_wing.secure_archive import RetentionPolicy, SecureArchive
from expansion_wing.source_review import SourceReviewItem
from expansion_wing.transcription_bakeoff import CandidatePolicy, evaluate_fixture, word_error_rate


def policy(**changes):
    values = dict(allowed_domains=frozenset({"www.sec.gov", "berkshirehathaway.com"}), max_redirects=1,
        timeout_seconds=2, max_response_bytes=100, minimum_interval_seconds=0, max_retries=1,
        rights_approved=True, access_policy_approved=True)
    values.update(changes); return AcquisitionPolicy(**values)


def response(**changes):
    values = dict(status=200, final_url="https://www.sec.gov/Archives/fixture.txt", redirect_urls=(),
        headers={"Content-Length": "7"}, body=b"fixture")
    values.update(changes); return TransportResponse(**values)


class AcquisitionContractTests(unittest.TestCase):
    def test_domain_https_user_agent_timeout_retry_and_hash(self):
        calls = []
        def transport(url, headers, timeout, retries):
            calls.append((url, headers, timeout, retries)); return response()
        result = OfficialSourceAcquirer(policy()).acquire("https://www.sec.gov/Archives/fixture.txt", transport)
        self.assertEqual(result["retrieved_bytes"], 7); self.assertEqual(len(result["content_hash"]), 64)
        self.assertIn("contact", calls[0][1]["User-Agent"]); self.assertEqual(calls[0][2:], (2, 1))
        with self.assertRaises(ValueError): OfficialSourceAcquirer(policy()).acquire("http://www.sec.gov/a", transport)
        with self.assertRaises(PermissionError): OfficialSourceAcquirer(policy()).acquire("https://example.com/a", transport)

    def test_redirect_size_tls_and_access_policy_fail_closed(self):
        with self.assertRaises(RuntimeError): OfficialSourceAcquirer(policy()).acquire(
            "https://www.sec.gov/a", lambda *_: response(redirect_urls=("https://www.sec.gov/1", "https://www.sec.gov/2")))
        with self.assertRaises(PermissionError): OfficialSourceAcquirer(policy()).acquire(
            "https://www.sec.gov/a", lambda *_: response(final_url="https://evil.example/a"))
        with self.assertRaises(RuntimeError): OfficialSourceAcquirer(policy()).acquire(
            "https://www.sec.gov/a", lambda *_: response(headers={"Content-Length": "101"}, body=b"x"))
        for change in ({"rights_approved": False}, {"access_policy_approved": False}):
            with self.assertRaises(PermissionError): OfficialSourceAcquirer(policy(**change))

    def test_rate_limit_response_body_and_bound_validation(self):
        clock = iter((10.0, 10.5)).__next__; client = OfficialSourceAcquirer(policy(minimum_interval_seconds=1), clock=clock)
        client.acquire("https://www.sec.gov/a", lambda *_: response())
        with self.assertRaises(RuntimeError): client.acquire("https://www.sec.gov/a", lambda *_: response())
        with self.assertRaises(RuntimeError): OfficialSourceAcquirer(policy(max_response_bytes=3)).acquire(
            "https://www.sec.gov/a", lambda *_: response(headers={}, body=b"four"))
        with self.assertRaises(ValueError): policy(max_retries=3).validate()
        with self.assertRaises(ValueError): policy(max_response_bytes=10_000_001).validate()


class ArchiveTests(unittest.TestCase):
    def test_content_addressing_permissions_atomicity_and_dedup(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = SecureArchive(Path(temp) / "archive", RetentionPolicy(30))
            first = archive.store("notes", b"synthetic note")
            second = archive.store("notes", b"synthetic note")
            self.assertEqual(first["content_hash"], second["content_hash"])
            root = Path(temp) / "archive"; stored = root / "notes" / f'{first["content_hash"]}.bin'
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)
            self.assertFalse(any(path.name.startswith(".pending-") for path in stored.parent.iterdir()))
            with self.assertRaises(ValueError): archive.store("notes", b"x", expected_hash="0" * 64)

    def test_layer_separation_browser_allowlist_retention_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = SecureArchive(Path(temp) / "archive", RetentionPolicy(7))
            for layer in ("original", "notes", "claims"): archive.store(layer, f"synthetic-{layer}".encode())
            safe = {"schema_version": "investor-archive-browser-v1", "generated_at": "2026-09-03T00:00:00Z",
                "truth_state": "CURRENT", "real_source_count": 0, "fixture_source_count": 3,
                "rights_review_count": 0, "approved_source_count": 0, "claims_pending_review_count": 0}
            archive.publish_browser(safe)
            with self.assertRaises(ValueError): archive.publish_browser({**safe, "local_path": "/private/example"})
            with self.assertRaises(ValueError): archive.publish_browser({**safe, "reason": "https://private.example"})
            with self.assertRaises(ValueError): archive.publish_browser({**safe, "real_source_count": -1})
            with self.assertRaises(ValueError): RetentionPolicy(0).validate()
            event = archive.manifest_entry(action="DELETION_APPROVED", content_hash="a" * 64,
                actor="human-reviewer", occurred_at="2026-09-03T00:00:00Z")
            self.assertTrue(event["human_approval_required"])


class ReviewInterviewTests(unittest.TestCase):
    def test_exact_source_lifecycle_and_no_automatic_judgment(self):
        item = SourceReviewItem("s1")
        with self.assertRaises(PermissionError): item.transition("RIGHTS_REVIEW", human_approved=False)
        item.transition("RIGHTS_REVIEW", human_approved=True)
        with self.assertRaises(PermissionError): item.transition("APPROVED", human_approved=True)
        item.rights_classification = "PERMITTED"; item.attribution_verified = True; item.source_approved = True
        for target in ("APPROVED", "NORMALIZED", "CLAIMS_PENDING_REVIEW"):
            self.assertEqual(item.transition(target, human_approved=True), target)
        self.assertTrue(item.claim_extraction_allowed()); self.assertFalse(item.judgment_handoff()["judgment_bank_write"])
        rejected = SourceReviewItem("s2"); rejected.transition("RIGHTS_REVIEW", human_approved=True)
        self.assertEqual(rejected.transition("REJECTED", human_approved=True), "REJECTED")

    def test_synthetic_upload_limits_consent_and_approval_queues(self):
        base = dict(media_type="AUDIO", extension="wav", payload=b"synthetic audio", duration_seconds=10,
            consent=True, permitted_use=True, confidential_exclusion=True, jesse_identity_confirmed=True,
            jesse_approval_required=True)
        accepted = stage_reviewed_upload(**base)
        self.assertEqual(accepted["status"], "STAGED"); self.assertFalse(accepted["real_file_inspected"])
        self.assertEqual(accepted["correction_status"], "PENDING")
        for key in ("consent", "permitted_use", "confidential_exclusion", "jesse_identity_confirmed"):
            with self.subTest(key=key): self.assertEqual(stage_reviewed_upload(**{**base, key: False})["status"], "REJECTED")
        self.assertEqual(stage_reviewed_upload(**{**base, "extension": "exe"})["status"], "REJECTED")


class BakeoffProjectionTests(unittest.TestCase):
    def test_provider_neutral_zero_cost_bakeoff_and_local_candidate(self):
        class FixtureAdapter:
            name = "local-offline-fixture"; provider_activated = False
            def transcribe(self, _audio):
                return {"text": "fixture words", "speakers": ("A",), "timestamps": (0.0,), "latency_ms": 4}
        approved = CandidatePolicy(True, True, True, 0.0, local_offline=True)
        result = evaluate_fixture(FixtureAdapter(), approved, audio=b"synthetic", reference="fixture words",
            expected_speakers=("A",))
        self.assertEqual(result["word_error_rate"], 0); self.assertFalse(result["provider_called"])
        self.assertEqual(evaluate_fixture(FixtureAdapter(), CandidatePolicy(True, True, True, None),
            audio=b"x", reference="x", expected_speakers=())["reason"], "COST_UNKNOWN")
        self.assertEqual(evaluate_fixture(FixtureAdapter(), CandidatePolicy(True, True, True, 0.01),
            audio=b"x", reference="x", expected_speakers=())["reason"], "COST_CEILING")
        self.assertGreater(word_error_rate("one two", "one three"), 0)

    def test_real_and_fixture_counts_are_distinct_and_no_fabricated_results(self):
        projection = room_projection({"source_count": 3, "real_source_count": 1, "fixture_source_count": 2,
            "approved_source_count": 1, "rights_review_queue_count": 1, "claims_pending_review_count": 1})
        archive = projection["Investor Archive"]["data"]
        self.assertEqual(archive["real_source_count"], 1); self.assertEqual(archive["fixture_source_count"], 2)
        encoded = json.dumps(projection)
        for prohibited in ("recommendation", "profitability", "interview_completed"):
            self.assertNotIn(prohibited, encoded)


if __name__ == "__main__": unittest.main()
