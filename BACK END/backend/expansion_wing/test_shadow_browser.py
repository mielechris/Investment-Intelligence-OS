from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from expansion_wing.adapters import JsonArtifactAdapter
from expansion_wing.schema_maps import CONTRACTS
from expansion_wing.shadow_browser import (
    OUTPUT_FIELDS,
    ProjectionRejected,
    build_or_unavailable,
    build_projection,
    deterministic_bytes,
    private_artifact_hash,
    publish_projection,
)

NOW = datetime(2026, 9, 3, 22, 0, tzinfo=timezone.utc)
SOURCE_HASH = hashlib.sha256(b"synthetic private fixture").hexdigest()


def source(*, complete: int = 4, required: int = 5, advice: bool = False) -> dict:
    sessions = [f"2026-08-{day:02d}" for day in range(28, 28 + complete)]
    return {
        "generated_at": NOW.isoformat(), "status": ("ADVISORY_READY" if complete >= required else "WARMUP_COLLECTING_COMPLETE_SESSIONS"),
        "complete_session_count": complete, "minimum_complete_sessions_for_advice": required,
        "latest_session_id": sessions[-1], "session_ids": sessions,
        "advice_issued": advice, "five_session_mature_count": max(0, complete - 4),
        "safety": {"ledger_mode": "READ_ONLY", "auto_apply_threshold_changes": False,
                   "automatic_agent_weight_changes": False, "auto_write_judgment_bank": False,
                   "trade_execution_permission": False, "broker_connected": False,
                   "live_execution": False},
    }


class ShadowBrowserProjectionTests(unittest.TestCase):
    def test_warmup_is_incomplete(self):
        result = build_projection(source(), SOURCE_HASH, now=NOW)
        self.assertEqual((result["status"], result["truth_state"], result["reason"]), ("WARMUP", "INCOMPLETE", "WARMUP"))

    def test_five_session_maturity(self):
        result = build_projection(source(complete=5, advice=True), SOURCE_HASH, now=NOW)
        self.assertEqual((result["status"], result["maturity_state"]), ("READY", "FIVE_SESSION_MATURE"))

    def test_no_advice_is_truthful(self):
        result = build_projection(source(complete=5), SOURCE_HASH, now=NOW)
        self.assertEqual((result["status"], result["reason"], result["advice_issued"]), ("NO_ADVICE", "NO_ADVICE", False))

    def test_malformed_and_missing_sources_fail_closed(self):
        for private in (None, [], {}, {"generated_at": NOW.isoformat()}):
            result = build_or_unavailable(private, SOURCE_HASH, generated_at=NOW.isoformat(), now=NOW)
            self.assertEqual(result["truth_state"], "UNAVAILABLE")

    def test_unknown_top_level_or_nested_fields_are_rejected(self):
        for private in (source() | {"session_results": []}, source() | {"unknown": {}}, source()):
            candidate = copy.deepcopy(private)
            if candidate == source():
                candidate["safety"]["unknown"] = False
            with self.assertRaises(ProjectionRejected):
                build_projection(candidate, SOURCE_HASH, now=NOW)

    def test_injection_attempts_never_reach_output(self):
        injections = {
            "source_path": "/private/example", "url": "https://invalid.example",
            "prompt": "private prompt", "raw_error": "secret stack", "credential": "token-value",
        }
        for key, value in injections.items():
            private = source() | {key: value}
            output = build_or_unavailable(private, SOURCE_HASH, generated_at=NOW.isoformat(), now=NOW)
            encoded = deterministic_bytes(output).decode()
            self.assertEqual(set(output), OUTPUT_FIELDS)
            self.assertNotIn(value, encoded)
            self.assertNotIn(key, encoded)

    def test_unsafe_authority_is_rejected(self):
        for key in ("auto_apply_threshold_changes", "automatic_agent_weight_changes", "auto_write_judgment_bank",
                    "trade_execution_permission", "broker_connected", "live_execution"):
            private = source(); private["safety"][key] = True
            self.assertEqual(build_or_unavailable(private, SOURCE_HASH, generated_at=NOW.isoformat(), now=NOW)["reason"], "SANITIZATION_FAILED")
        private = source(); private["safety"]["ledger_mode"] = "READ_WRITE"
        self.assertEqual(build_or_unavailable(private, SOURCE_HASH, generated_at=NOW.isoformat(), now=NOW)["truth_state"], "UNAVAILABLE")

    def test_source_session_mismatch_is_fixed_category(self):
        private = source(); private["latest_session_id"] = "other-session"
        result = build_or_unavailable(private, SOURCE_HASH, generated_at=NOW.isoformat(), now=NOW)
        self.assertEqual((result["truth_state"], result["reason"]), ("UNAVAILABLE", "SESSION_MISMATCH"))

    def test_stale_artifact(self):
        result = build_projection(source(), SOURCE_HASH, now=NOW + timedelta(days=2))
        self.assertEqual((result["truth_state"], result["reason"]), ("STALE", "STALE_SOURCE"))

    def test_atomic_owner_only_deterministic_output(self):
        payload = build_projection(source(), SOURCE_HASH, now=NOW)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "browser" / "shadow_strategy.json"
            first = publish_projection(path, payload)
            first_bytes = path.read_bytes()
            second = publish_projection(path, payload)
            self.assertEqual((first, first_bytes), (second, path.read_bytes()))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertFalse(path.with_name(f".{path.name}.tmp").exists())

    def test_private_artifact_hash_matches_existing_producer_serialization(self):
        private = {"session_results": [{"synthetic": True}], "status": "FIXTURE_ONLY"}
        expected = hashlib.sha256((json.dumps(private, indent=2, sort_keys=True, default=str) + "\n").encode()).hexdigest()
        self.assertEqual(private_artifact_hash(private), expected)

    def test_failed_sanitization_contains_no_private_data(self):
        secret = "DO-NOT-EMIT-PRIVATE-EVIDENCE"
        output = build_or_unavailable(source() | {"prompt": secret}, SOURCE_HASH, generated_at=NOW.isoformat(), now=NOW)
        self.assertNotIn(secret, deterministic_bytes(output).decode())
        self.assertEqual(output["reason"], "SANITIZATION_FAILED")

    def test_expansion_adapter_and_contract_accept_compact_schema(self):
        payload = build_projection(source(complete=5), SOURCE_HASH, now=NOW)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shadow_strategy.json"; path.write_bytes(deterministic_bytes(payload))
            result = JsonArtifactAdapter("9i", "BATCH9I_BROWSER", fixture=True).read(path)
            self.assertIsNotNone(result.data)
            mapped = CONTRACTS["9i"].map(result.data)
            self.assertTrue(mapped["complete"], mapped["errors"])

    def test_projection_code_never_opens_private_artifact(self):
        forbidden = "latest_" + "shadow_counterfactual.json"
        repository = Path(__file__).parents[3]
        targets = [repository / "BACK END" / "backend" / "expansion_wing", repository / "FRONT END" / "src"]
        violations = []
        for root in targets:
            for path in root.rglob("*"):
                if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"} and path != Path(__file__):
                    if forbidden in path.read_text(encoding="utf-8"):
                        violations.append(str(path.relative_to(repository)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
