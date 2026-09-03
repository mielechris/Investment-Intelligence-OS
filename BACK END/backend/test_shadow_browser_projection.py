from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import shadow_browser_projection as browser

NOW = datetime(2026, 9, 3, 22, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("shadow_producer", ROOT / "scripts" / "iios_shadow_counterfactual_lab.py")
assert SPEC and SPEC.loader
PRODUCER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRODUCER)


def rollup(count: int = 4, advice: bool = False) -> dict:
    sessions = [f"fixture-session-{index}" for index in range(count)]
    return {
        "schema_version": "batch9i-shadow-counterfactual-rollup-v1",
        "generated_at": NOW.isoformat(),
        "status": "ADVISORY_READY" if count >= 5 else "WARMUP_COLLECTING_COMPLETE_SESSIONS",
        "complete_session_count": count,
        "minimum_complete_sessions_for_advice": 5,
        "session_ids": sessions,
        "baseline": {"captured_tickers": ["SYNTHETIC"]},
        "scenario_rollup": [{"ticker": "SYNTHETIC"}],
        "advisory_frontier": [{"symbol": "SYNTHETIC"}],
        "recommendations": ([{"action": "HUMAN_REVIEW_ONLY", "url": "https://invalid.example"}] if advice else []),
        "safety": {"shadow_only": True, "ledger_mode": "READ_ONLY", "auto_apply_threshold_changes": False,
                   "trade_execution_permission": False, "live_execution": False},
    }


def private_payload(value: dict) -> dict:
    return {**value, "session_results": [{"ticker": "SYNTHETIC", "trade": "NEVER_EMIT"}],
            "source": {"path": "/private/fixture", "prompt": "NEVER_EMIT"}}


class BrowserProjectionTests(unittest.TestCase):
    def test_warmup_and_mature_no_advice(self):
        warm = self._project(rollup())
        self.assertEqual((warm["status"], warm["truth_state"]), ("WARMUP", "INCOMPLETE"))
        mature = self._project(rollup(5))
        self.assertEqual((mature["status"], mature["truth_state"]), ("NO_ADVICE", "CURRENT"))

    def test_mature_advice_is_boolean_only(self):
        result = self._project(rollup(5, True))
        self.assertEqual((result["status"], result["advice_issued"]), ("READY", True))
        self.assertNotIn("recommendations", result)

    def test_malformed_unsafe_and_session_mismatch_fail_closed(self):
        self.assertEqual(browser.project_or_unavailable({}, "bad", generated_at=NOW.isoformat())["reason"], "SANITIZATION_FAILED")
        value = self._source(rollup()); value["safety"]["live_execution"] = True
        self.assertEqual(browser.project_or_unavailable(value, "0" * 64, generated_at=NOW.isoformat())["truth_state"], "UNAVAILABLE")
        value = self._source(rollup()); value["latest_session_id"] = "different"
        self.assertEqual(browser.project_or_unavailable(value, "0" * 64, generated_at=NOW.isoformat())["reason"], "SESSION_MISMATCH")

    def test_stale_is_not_healthy(self):
        result = browser.project(self._source(rollup()), "0" * 64, now=NOW + timedelta(days=2))
        self.assertEqual((result["truth_state"], result["reason"]), ("STALE", "STALE_SOURCE"))

    def test_unknown_and_private_fields_are_rejected(self):
        for key in ("session_results", "path", "url", "prompt", "raw_error", "credential", "trades"):
            value = self._source(rollup()) | {key: "NEVER_EMIT"}
            result = browser.project_or_unavailable(value, "0" * 64, generated_at=NOW.isoformat())
            self.assertEqual(result["reason"], "SANITIZATION_FAILED")
            self.assertNotIn("NEVER_EMIT", browser.projection_bytes(result).decode())

    def test_atomic_modes_and_deterministic_hash(self):
        local = private_payload(rollup())
        expected_bytes = (json.dumps(local, indent=2, sort_keys=True, default=str) + "\n").encode()
        self.assertEqual(browser.private_artifact_bytes(local), expected_bytes)
        self.assertEqual(browser.private_artifact_hash(local), hashlib.sha256(expected_bytes).hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "browser" / "shadow_strategy.json"
            browser.publish(path, self._project(rollup()))
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_producer_emission_preserves_private_bytes_and_excludes_private_content(self):
        value = rollup()
        local = private_payload(value)
        expected = browser.private_artifact_bytes(local)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); private = root / "shadow_strategy" / "latest_shadow_counterfactual.json"
            PRODUCER._atomic_write(private, local)
            self.assertEqual(private.read_bytes(), expected)
            state = PRODUCER._emit_browser_projection(state_dir=root, browser_source=self._source(value),
                                                       source_artifact_hash=browser.private_artifact_hash(local))
            self.assertEqual(state, "INCOMPLETE")
            safe = (root / "browser" / "shadow_strategy.json").read_text()
            for prohibited in ("session_results", "SYNTHETIC", "NEVER_EMIT", "recommendations", "/private", "https://"):
                self.assertNotIn(prohibited, safe)

    def test_private_write_survives_projection_publication_failure(self):
        value = rollup(); local = private_payload(value)
        with tempfile.TemporaryDirectory() as folder:
            private = Path(folder) / "latest.json"
            PRODUCER._atomic_write(private, local)
            with patch.object(PRODUCER, "publish_browser_projection", side_effect=OSError):
                state = PRODUCER._emit_browser_projection(state_dir=Path(folder), browser_source=self._source(value),
                                                           source_artifact_hash=browser.private_artifact_hash(local))
            self.assertEqual(state, "UNAVAILABLE")
            self.assertEqual(private.read_bytes(), browser.private_artifact_bytes(local))

    @staticmethod
    def _source(value: dict) -> dict:
        return {
            "generated_at": value["generated_at"], "status": value["status"],
            "complete_session_count": value["complete_session_count"],
            "minimum_complete_sessions_for_advice": value["minimum_complete_sessions_for_advice"],
            "latest_session_id": value["session_ids"][-1], "session_ids": value["session_ids"],
            "advice_issued": bool(value["recommendations"]),
            "five_session_mature_count": max(0, value["complete_session_count"] - 4),
            "safety": {"ledger_mode": "READ_ONLY", "auto_apply_threshold_changes": False,
                       "automatic_agent_weight_changes": False, "auto_write_judgment_bank": False,
                       "trade_execution_permission": False, "broker_connected": False, "live_execution": False},
        }

    def _project(self, value: dict) -> dict:
        return browser.project(self._source(value), browser.private_artifact_hash(private_payload(value)), now=NOW)


if __name__ == "__main__":
    unittest.main()
