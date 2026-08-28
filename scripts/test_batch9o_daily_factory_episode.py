from __future__ import annotations

import unittest
from datetime import datetime, timezone

import iios_daily_factory_episode as episode


class Batch9ODailyFactoryEpisodeTest(unittest.TestCase):
    def test_episode_classifies_calls_saves_dumb_calls_misses_and_paper_performance(self) -> None:
        scorecard = {
            "session_id": "2026-08-28",
            "generated_at": "2026-08-28T20:25:00+00:00",
            "metrics": {
                "benchmark_opportunity_count": 4,
                "eventual_detected_count": 3,
                "eventual_promotion_count": 2,
                "eventual_detection_rate_pct": 75.0,
                "eventual_opportunity_miss_rate_pct": 25.0,
            },
            "opportunities": [
                {"opportunity_id": "opp1", "ticker": "NVDA", "move_pct": 6.0, "eventually_detected": True},
                {"opportunity_id": "opp2", "ticker": "LITE", "move_pct": 8.0, "eventually_detected": True},
                {"opportunity_id": "opp3", "ticker": "MISS", "move_pct": -11.0, "eventually_detected": False},
                {"opportunity_id": "opp4", "ticker": "SAVE", "move_pct": -7.0, "eventually_detected": True},
            ],
        }
        shadow = {
            "status": "ADVISORY_READY",
            "complete_session_count": 6,
            "recommendations": [
                {
                    "type": "REVIEW_SHADOW_SCENARIO",
                    "scenario_id": "score_68_cap_7",
                    "reason": "Captured one additional benchmark opportunity within governed shadow load.",
                    "action": "HUMAN_REVIEW_ONLY",
                }
            ],
        }
        learning = {
            "status": "ACTIVE",
            "latest_session_id": "2026-08-28",
            "complete_session_count": 6,
            "outcome_count": 4,
            "mature_5d_count": 4,
            "recent_outcomes": [
                {
                    "ticker": "NVDA",
                    "case_id": "case_nvda",
                    "session_id": "2026-08-28",
                    "decision_quality": "PAPER_ENTRY_FAVORABLE",
                    "market_outcome": "STRONG_UPSIDE",
                    "longest_available_horizon": "5d",
                    "forward_return_pct": 10.0,
                    "benchmark_return_pct": 2.0,
                    "relative_return_pct": 8.0,
                },
                {
                    "ticker": "SAVE",
                    "case_id": "case_save",
                    "session_id": "2026-08-28",
                    "decision_quality": "NO_TRADE_AVOIDED_DOWNSIDE",
                    "market_outcome": "DOWNSIDE",
                    "longest_available_horizon": "5d",
                    "forward_return_pct": -8.0,
                    "benchmark_return_pct": 1.0,
                    "relative_return_pct": -9.0,
                },
                {
                    "ticker": "LITE",
                    "case_id": "case_lite",
                    "session_id": "2026-08-28",
                    "decision_quality": "NO_TRADE_FOREGONE_UPSIDE",
                    "market_outcome": "UPSIDE",
                    "longest_available_horizon": "5d",
                    "forward_return_pct": 7.5,
                    "benchmark_return_pct": 1.5,
                    "relative_return_pct": 6.0,
                },
                {
                    "ticker": "MISS",
                    "case_id": None,
                    "session_id": "2026-08-28",
                    "decision_quality": "FACTORY_MISS_WITH_UPSIDE",
                    "market_outcome": "UPSIDE",
                    "longest_available_horizon": "5d",
                    "forward_return_pct": 9.0,
                },
            ],
        }
        telemetry = {
            "generated_at": "2026-08-28T20:30:00+00:00",
            "paper_fund": {
                "snapshot_id": "paper_1",
                "starting_cash": 10000.0,
                "nav": 10125.0,
                "cash": 9000.0,
                "total_pnl": 125.0,
                "position_count": 1,
                "transaction_count": 1,
                "cumulative_return_pct": 1.25,
                "max_drawdown_pct": -0.4,
                "data_source": "PERSISTED_GOVERNED_PAPER_SNAPSHOTS_ONLY",
            },
            "providers": {"provider_error_count": 0},
        }

        payload = episode.build_daily_episode(
            scorecard=scorecard,
            shadow=shadow,
            learning=learning,
            telemetry=telemetry,
            generated_at=datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc),
            final_requested=True,
        )

        self.assertEqual(payload["status"], "FINAL")
        self.assertEqual(payload["episode_session_id"], "2026-08-28")
        self.assertEqual(payload["best_calls"][0]["ticker"], "NVDA")
        self.assertEqual(payload["saves"][0]["ticker"], "SAVE")
        self.assertEqual(payload["dumb_calls"][0]["ticker"], "LITE")
        self.assertEqual(payload["misses"][0]["ticker"], "MISS")
        self.assertEqual(payload["learning_misses"][0]["ticker"], "MISS")
        self.assertEqual(payload["scoreboard"]["paper"]["nav"], 10125.0)
        self.assertEqual(payload["scoreboard"]["paper"]["total_pnl"], 125.0)
        self.assertEqual(payload["scoreboard"]["validation_miss_count"], 1)
        self.assertEqual(payload["scoreboard"]["validation_miss_detail_count"], 1)
        self.assertEqual(payload["tomorrow_focus"][0]["priority"], "RADAR_MISS_REVIEW")
        self.assertEqual(payload["tomorrow_focus"][1]["authority"], "ADVISORY_ONLY")
        self.assertFalse(payload["safety"]["trade_execution_permission"])
        self.assertFalse(payload["safety"]["live_execution"])

    def test_aggregate_misses_survive_when_detail_rows_are_absent(self) -> None:
        payload = episode.build_daily_episode(
            scorecard={
                "session_id": "2026-08-28",
                "metrics": {
                    "benchmark_opportunity_count": 36,
                    "eventual_detected_count": 17,
                    "eventual_detection_rate_pct": 47.2,
                    "eventual_opportunity_miss_rate_pct": 52.8,
                },
                "opportunities": [],
            },
            shadow={},
            learning={"latest_session_id": "2026-08-28", "recent_outcomes": []},
            telemetry={"paper_fund": {"nav": 10000.0, "total_pnl": 0.0}},
            generated_at=datetime(2026, 8, 28, 22, 0, tzinfo=timezone.utc),
            final_requested=True,
        )
        self.assertEqual(payload["scoreboard"]["validation_miss_count"], 19)
        self.assertEqual(payload["scoreboard"]["validation_miss_detail_count"], 0)
        self.assertEqual(payload["misses"], [])
        self.assertIn("19 missed by the aggregate 9H metric", payload["story"][0]["line"])
        self.assertIn("0 detailed miss row(s)", payload["tomorrow_focus"][0]["why"])

    def test_final_with_learning_warmup_when_current_session_outcomes_are_missing(self) -> None:
        payload = episode.build_daily_episode(
            scorecard={"session_id": "2026-08-28", "metrics": {}, "opportunities": []},
            shadow={"status": "WARMUP_COLLECTING_COMPLETE_SESSIONS", "recommendations": []},
            learning={
                "status": "WARM-UP",
                "latest_session_id": "2026-08-27",
                "recent_outcomes": [
                    {"ticker": "OLD", "session_id": "2026-08-27", "decision_quality": "PAPER_ENTRY_FAVORABLE"}
                ],
            },
            telemetry={"paper_fund": {"nav": 10000.0}},
            generated_at=datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc),
            final_requested=True,
        )
        self.assertEqual(payload["status"], "FINAL_WITH_LEARNING_WARMUP")
        self.assertEqual(payload["best_calls"], [])
        self.assertFalse(payload["source_freshness"]["learning_session_match"])

    def test_story_is_grounded_in_persisted_sections_and_never_grants_authority(self) -> None:
        payload = episode.build_daily_episode(
            scorecard={"session_id": "2026-08-28", "metrics": {}, "opportunities": []},
            shadow={},
            learning={"latest_session_id": "2026-08-28", "recent_outcomes": []},
            telemetry={"paper_fund": {"nav": 10000.0, "total_pnl": 0.0}},
            generated_at=datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc),
            final_requested=False,
        )
        self.assertEqual(payload["status"], "LIVE_DRAFT")
        self.assertTrue(payload["safety"]["report_only"])
        self.assertFalse(payload["safety"]["auto_apply_threshold_changes"])
        self.assertFalse(payload["safety"]["agent_weight_change_authority"])
        self.assertFalse(payload["safety"]["capital_authority"])
        self.assertGreaterEqual(len(payload["story"]), 2)
        self.assertTrue(all(line.get("basis") for line in payload["story"]))


if __name__ == "__main__":
    unittest.main()
