from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "activate_batch9h_9j_learning_superbatch.py"
SPEC = importlib.util.spec_from_file_location("learning_superbatch", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def complete_report(state_dir: Path, session_id: str) -> None:
    report = state_dir / "reports" / session_id
    write_json(report / "benchmark.json", {"benchmark_complete": True, "session_id": session_id})
    write_json(report / "scorecard.json", {"metrics": {"detection_rate_pct": 50.0}})


class LearningSuperbatchTests(unittest.TestCase):
    def test_no_complete_sessions_fails_closed_without_synthetic_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            snapshot = module.build_status_snapshot(
                state_dir=state_dir,
                now=datetime(2026, 8, 30, 12, 0, tzinfo=module.NEW_YORK),
            )
            self.assertEqual(
                snapshot["chain_state"],
                "ARMED_WAITING_FOR_COMPLETE_9H_SESSION",
            )
            self.assertEqual(snapshot["9H"]["complete_session_count"], 0)
            self.assertFalse(snapshot["safety"]["live_execution"])
            self.assertFalse(snapshot["safety"]["trade_execution_permission"])
            self.assertFalse(snapshot["safety"]["auto_apply_threshold_changes"])

    def test_complete_real_9h_session_routes_to_shadow_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            complete_report(state_dir, "2026-08-28")
            write_json(
                state_dir / "latest_market_validation.json",
                {
                    "generated_at": "2026-08-28T20:10:00+00:00",
                    "session_id": "2026-08-28",
                    "benchmark_complete": True,
                    "status": "LEARNING_REPORT_COMPLETE",
                },
            )
            snapshot = module.build_status_snapshot(
                state_dir=state_dir,
                now=datetime(2026, 8, 30, 12, 0, tzinfo=module.NEW_YORK),
            )
            self.assertEqual(snapshot["9H"]["complete_session_count"], 1)
            self.assertEqual(snapshot["9H"]["latest_complete_session_id"], "2026-08-28")
            self.assertEqual(snapshot["chain_state"], "READY_FOR_9I_SHADOW_REFRESH")
            self.assertEqual(snapshot["9H"]["age_interpretation"], "EXPECTED_OFF_HOURS_AGE")

    def test_shadow_warmup_and_outcome_refresh_is_active_learning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            complete_report(state_dir, "2026-08-28")
            write_json(
                state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json",
                {
                    "generated_at": "2026-08-30T18:00:00+00:00",
                    "status": "WARMUP_COLLECTING_COMPLETE_SESSIONS",
                    "complete_session_count": 1,
                    "minimum_complete_sessions_for_advice": 5,
                    "recommendations": [],
                },
            )
            write_json(
                state_dir / "latest_outcome_learning.json",
                {
                    "generated_at": "2026-08-30T18:01:00+00:00",
                    "status": "LEARNING_WARMUP",
                    "complete_session_count": 1,
                    "outcome_count": 4,
                    "mature_5d_count": 0,
                    "pending_5d_count": 4,
                },
            )
            snapshot = module.build_status_snapshot(state_dir=state_dir)
            self.assertEqual(snapshot["chain_state"], "ACTIVE_LEARNING_WARMUP")
            self.assertEqual(snapshot["9I"]["complete_session_count"], 1)
            self.assertEqual(snapshot["9J"]["outcome_count"], 4)

    def test_five_complete_sessions_can_be_advisory_ready_without_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            for day in range(24, 29):
                complete_report(state_dir, f"2026-08-{day:02d}")
            write_json(
                state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json",
                {
                    "generated_at": "2026-08-30T18:00:00+00:00",
                    "status": "ADVISORY_READY",
                    "complete_session_count": 5,
                    "minimum_complete_sessions_for_advice": 5,
                    "recommendations": [{"action": "HUMAN_REVIEW_ONLY"}],
                },
            )
            write_json(
                state_dir / "latest_outcome_learning.json",
                {
                    "generated_at": "2026-08-30T18:01:00+00:00",
                    "status": "OUTCOME_MEMORY_ACTIVE",
                    "complete_session_count": 5,
                    "outcome_count": 10,
                },
            )
            snapshot = module.build_status_snapshot(state_dir=state_dir)
            self.assertEqual(snapshot["chain_state"], "ACTIVE_ADVISORY_READY")
            self.assertEqual(snapshot["9I"]["recommendation_count"], 1)
            self.assertFalse(snapshot["safety"]["automatic_judgment_bank_writes"])
            self.assertFalse(snapshot["safety"]["automatic_agent_weight_changes"])
            self.assertFalse(snapshot["safety"]["capital_authority"])

    def test_weekend_context_is_non_market_day(self) -> None:
        context = module._market_context(
            datetime(2026, 8, 30, 11, 0, tzinfo=module.NEW_YORK)
        )
        self.assertEqual(context, "NON_MARKET_DAY")


if __name__ == "__main__":
    unittest.main()
