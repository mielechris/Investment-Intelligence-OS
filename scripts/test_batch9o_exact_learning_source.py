from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import iios_daily_factory_episode_exact as exact


class Batch9OExactLearningSourceTest(unittest.TestCase):
    def _write(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_full_9j_memory_wins_over_compact_browser_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "market-validation"
            telemetry = root / "telemetry"
            self._write(
                state / "latest_market_validation.json",
                {
                    "session_id": "2026-08-28",
                    "metrics": {},
                    "opportunities": [],
                },
            )
            self._write(
                state / "latest_outcome_learning.json",
                {
                    "latest_session_id": "2026-08-28",
                    "status": "ACTIVE",
                    "recent_outcomes": [
                        {
                            "ticker": "NVDA",
                            "case_id": "case_nvda_exact",
                            "candidate_id": "candidate_nvda_exact",
                            "opportunity_id": "opportunity_nvda_exact",
                            "session_id": "2026-08-28",
                            "decision_quality": "WATCH_VALIDATED_BY_UPSIDE",
                            "market_outcome": "UPSIDE",
                            "forward_return_pct": 4.5,
                        }
                    ],
                },
            )
            self._write(
                state / "browser" / "outcome_learning.json",
                {
                    "latest_session_id": "2026-08-28",
                    "status": "COMPACT_SHOULD_NOT_WIN",
                    "recent_outcomes": [
                        {
                            "ticker": "NVDA",
                            "session_id": "2026-08-28",
                            "decision_quality": "NO_TRADE_FOREGONE_UPSIDE",
                        }
                    ],
                },
            )
            self._write(
                telemetry / "latest.json",
                {"paper_fund": {"nav": 10000.0, "total_pnl": 0.0}},
            )

            payload = exact.build_from_state(
                state_dir=state,
                telemetry_dir=telemetry,
                generated_at=datetime(2026, 8, 28, 22, 0, tzinfo=timezone.utc),
                final_requested=True,
            )

            self.assertEqual(payload["status"], "FINAL")
            self.assertEqual(
                payload["source_freshness"]["learning_lineage_mode"],
                "CASE_AND_CANDIDATE_LINKED",
            )
            self.assertEqual(
                payload["source_freshness"]["learning_source_filename"],
                "latest_outcome_learning.json",
            )
            self.assertEqual(payload["best_calls"][0]["case_id"], "case_nvda_exact")
            self.assertEqual(
                payload["safety"]["source_mode"],
                "PERSISTED_9G_9H_9I_9J_EXACT_LINKED_READ_ONLY",
            )
            self.assertFalse(payload["safety"]["trade_execution_permission"])
            self.assertFalse(payload["safety"]["live_execution"])

    def test_compact_fallback_is_truthfully_marked_learning_warmup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "market-validation"
            telemetry = root / "telemetry"
            self._write(
                state / "latest_market_validation.json",
                {"session_id": "2026-08-28", "metrics": {}, "opportunities": []},
            )
            self._write(
                state / "browser" / "outcome_learning.json",
                {
                    "latest_session_id": "2026-08-28",
                    "recent_outcomes": [
                        {
                            "ticker": "NVDA",
                            "session_id": "2026-08-28",
                            "decision_quality": "WATCH_VALIDATED_BY_UPSIDE",
                        }
                    ],
                },
            )
            self._write(telemetry / "latest.json", {"paper_fund": {"nav": 10000.0}})

            payload = exact.build_from_state(
                state_dir=state,
                telemetry_dir=telemetry,
                generated_at=datetime(2026, 8, 28, 22, 0, tzinfo=timezone.utc),
                final_requested=True,
            )

            self.assertEqual(payload["status"], "FINAL_WITH_LEARNING_WARMUP")
            self.assertEqual(
                payload["source_freshness"]["learning_lineage_mode"],
                "COMPACT_BROWSER_FALLBACK",
            )
            self.assertEqual(
                payload["safety"]["source_mode"],
                "PERSISTED_9G_9H_9I_9J_COMPACT_FALLBACK_READ_ONLY",
            )


if __name__ == "__main__":
    unittest.main()
