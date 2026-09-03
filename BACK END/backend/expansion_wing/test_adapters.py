from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from expansion_wing.adapters import CallbackAdapter, JsonArtifactAdapter, adapter_registry


def stamp(seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class AdapterContractTests(unittest.TestCase):
    def test_registry_has_every_required_read_adapter(self):
        self.assertEqual(set(adapter_registry()), {"9a", "9b", "9e", "9h", "9i", "9j", "paper_fund",
            "equity_etf", "treasury_bond", "ipo_listing", "commodity_future",
            "investor_intelligence", "interview_upload"})

    def test_missing_and_malformed_artifacts_are_unavailable(self):
        adapter = JsonArtifactAdapter("9h", "IIOS_9H_SANITIZED_ARTIFACT", fixture=True)
        self.assertEqual(adapter.read(None).state, "UNAVAILABLE")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.json"
            path.write_text("not json")
            result = adapter.read(path)
            self.assertEqual(result.state, "UNAVAILABLE")
            self.assertEqual(result.error, "JSONDecodeError")
            self.assertNotIn(str(path), str(result.to_source()))

    def test_fresh_stale_incomplete_and_unknown_states(self):
        adapter = CallbackAdapter("equity", "FIXTURE", stale_after_seconds=60, fixture=True)
        self.assertEqual(adapter.read(lambda: {"observed_at": stamp()}).state, "CURRENT")
        self.assertEqual(adapter.read(lambda: {"observed_at": stamp(-120)}).state, "STALE")
        self.assertEqual(adapter.read(lambda: {"observed_at": stamp(), "complete": False}).state, "INCOMPLETE")
        self.assertEqual(adapter.read(lambda: {"value": 1}).state, "UNKNOWN")

    def test_hash_deduplication(self):
        adapter = CallbackAdapter("equity", "FIXTURE", fixture=True)
        payload = {"observed_at": "2026-09-03T12:00:00+00:00", "value": 1}
        self.assertFalse(adapter.read(lambda: payload).duplicate)
        self.assertTrue(adapter.read(lambda: payload).duplicate)

    def test_timeout_and_errors_are_sanitized(self):
        slow = CallbackAdapter("public", "FIXTURE", timeout_seconds=.01, fixture=True)
        self.assertEqual(slow.read(lambda: (time.sleep(.05), {})[1]).error, "TimeoutError")
        failed = slow.read(lambda: (_ for _ in ()).throw(RuntimeError("credential=do-not-leak")))
        self.assertEqual(failed.error, "RuntimeError")
        self.assertNotIn("do-not-leak", str(failed.to_source()))

    def test_fixture_provenance_and_no_credentials(self):
        result = CallbackAdapter("interview_upload", "USER_UPLOADED_MEDIA_METADATA", fixture=True).read(
            lambda: {"observed_at": stamp(), "media_type": "AUDIO"})
        self.assertTrue(result.fixture)
        self.assertEqual(result.provenance["source"], "FIXTURE_CALLBACK")
        self.assertNotIn("credential", result.provenance)


if __name__ == "__main__":
    unittest.main()
