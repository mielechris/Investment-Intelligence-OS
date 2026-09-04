from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from expansion_wing.candidate_flow_acceptance import AcceptanceResult, ReviewQueueItem
from expansion_wing.post_close_candidate_pipeline import ClosingSessionEvidence, PrimarySourceAttestation
from expansion_wing.post_close_operations import PostCloseController, ProjectionStore


def close(*, complete=True):
    body = dict(session_date="2026-09-04", market_timezone="America/New_York",
                final_snapshot_at="2026-09-04T20:00:00Z", expected_snapshot_count=79,
                observed_snapshot_count=79 if complete else 78, provider_error_count=0,
                universe_count=519, complete=complete)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ClosingSessionEvidence(**body, evidence_hash=digest)


def accepted():
    item = ReviewQueueItem("candidate_0123456789abcdef", "MU", "a" * 64)
    return AcceptanceResult("COMPLETE", "batch_0123456789abcdef", (item,), 1, 1, 1, 0, 5, 6, None)


def proof():
    return PrimarySourceAttestation("candidate_0123456789abcdef", "MU", "SEC_FILING",
                                    "www.sec.gov", "2026-09-04", "b" * 64, True, True)


class PostCloseOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name) / "state"
        self.root.mkdir(mode=0o700); os.chmod(self.root, 0o700)
        self.store = ProjectionStore(self.root)

    def tearDown(self): self.temp.cleanup()

    def test_disabled_controller_does_not_touch_inputs_or_disk(self):
        acceptance = Mock()
        result = PostCloseController(acceptance, self.store).run(close(), {}, explicitly_authorized=True)
        self.assertEqual(result.state, "NOT_ACTIVATED"); acceptance.run.assert_not_called()
        self.assertFalse(self.store.path.exists())

    def test_incomplete_close_stops_before_candidates(self):
        acceptance = Mock()
        result = PostCloseController(acceptance, self.store, enabled=True).run(
            close(complete=False), {}, explicitly_authorized=True)
        self.assertEqual(result.state, "WAITING_FOR_CLOSE"); acceptance.run.assert_not_called()
        self.assertEqual(self.store.read()["failure_category"], "CLOSING_SESSION_INCOMPLETE")

    def test_completed_candidates_wait_for_primary_sources(self):
        acceptance = Mock(); acceptance.run.return_value = accepted()
        result = PostCloseController(acceptance, self.store, enabled=True).run(
            close(), {"sanitized": True}, explicitly_authorized=True)
        self.assertEqual(result.state, "AWAITING_PRIMARY_SOURCES")
        self.assertEqual((result.candidate_count, result.new_credits), (1, 1))

    def test_verified_candidate_reaches_case_draft_only(self):
        acceptance = Mock(); acceptance.run.return_value = accepted()
        result = PostCloseController(acceptance, self.store, enabled=True).run(
            close(), {}, (proof(),), explicitly_authorized=True)
        self.assertEqual(result.state, "READY_FOR_GOVERNED_CASE_DRAFT")
        saved = self.store.read()
        self.assertEqual(saved["governed_case_draft_count"], 1)
        self.assertFalse(saved["authority_granted"])
        self.assertTrue(all(value is False for value in saved["authority"].values()))

    def test_store_rejects_permissions_and_tampering(self):
        acceptance = Mock(); acceptance.run.return_value = accepted()
        PostCloseController(acceptance, self.store, enabled=True).run(close(), {}, explicitly_authorized=True)
        os.chmod(self.store.path, 0o644)
        with self.assertRaisesRegex(RuntimeError, "POST_CLOSE_STORE_UNAVAILABLE"):
            self.store.read()


if __name__ == "__main__": unittest.main()
