from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from expansion_wing.candidate_flow_acceptance import AcceptanceResult, ReviewQueueItem
from expansion_wing.post_close_candidate_pipeline import (
    ClosingSessionEvidence,
    PrimarySourceAttestation,
    finalize_post_close,
)


def closing(**changes):
    values = dict(session_date="2026-09-04", market_timezone="America/New_York",
                  final_snapshot_at="2026-09-04T20:00:00Z", expected_snapshot_count=79,
                  observed_snapshot_count=79, provider_error_count=0, universe_count=519,
                  complete=True)
    values.update(changes)
    digest = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ClosingSessionEvidence(**values, evidence_hash=digest)


def acceptance():
    items = (ReviewQueueItem("candidate_0123456789abcdef", "MU", "a" * 64),)
    return AcceptanceResult("COMPLETE", "batch_0123456789abcdef", items, 1, 1, 1, 0, 5, 6, None)


def attestation(**changes):
    values = dict(candidate_id="candidate_0123456789abcdef", ticker="MU", source_class="SEC_FILING",
                  source_host="www.sec.gov", document_date="2026-09-04", content_hash="b" * 64,
                  rights_approved=True, human_approved=True)
    values.update(changes)
    return PrimarySourceAttestation(**values)


class PostCloseCandidatePipelineTests(unittest.TestCase):
    def test_committed_close_fixture_is_hash_valid(self):
        path = Path(__file__).with_name("fixtures") / "post_close_session_14cd.json"
        ClosingSessionEvidence(**json.loads(path.read_text())).validate()

    def test_requires_explicit_authorization(self):
        result = finalize_post_close(closing(), acceptance(), (attestation(),))
        self.assertEqual(result.state, "NOT_ACTIVATED")

    def test_rejects_incomplete_or_tampered_close(self):
        for value in (closing(complete=False), closing(observed_snapshot_count=78),
                      closing(provider_error_count=1)):
            result = finalize_post_close(value, acceptance(), (attestation(),), explicitly_authorized=True)
            self.assertEqual(result.failure_category, "CLOSING_SESSION_INCOMPLETE")

    def test_requires_completed_candidate_acceptance(self):
        rejected = AcceptanceResult("STOPPED_FAIL_CLOSED", None, (), 0, 0, 0, 0, 5, 5, "x")
        result = finalize_post_close(closing(), rejected, (), explicitly_authorized=True)
        self.assertEqual(result.failure_category, "CANDIDATE_ACCEPTANCE_REQUIRED")

    def test_requires_exact_primary_source_binding(self):
        for proof in (attestation(ticker="AMD"), attestation(source_host="bad..host"),
                      attestation(rights_approved=False)):
            result = finalize_post_close(closing(), acceptance(), (proof,), explicitly_authorized=True)
            self.assertEqual(result.failure_category, "PRIMARY_SOURCE_ATTESTATION_INVALID")

    def test_partial_review_does_not_create_cases(self):
        result = finalize_post_close(closing(), acceptance(), (), explicitly_authorized=True)
        self.assertEqual(result.state, "AWAITING_PRIMARY_SOURCES")
        self.assertEqual(result.governed_case_count, 0)

    def test_verified_candidates_reach_draft_only(self):
        result = finalize_post_close(closing(), acceptance(), (attestation(),), explicitly_authorized=True)
        self.assertEqual(result.state, "READY_FOR_GOVERNED_CASE_DRAFT")
        self.assertEqual(result.governed_case_count, 1)
        self.assertTrue(all(value is False for value in result.browser_safe()["authority"].values()))


if __name__ == "__main__":
    unittest.main()
