from __future__ import annotations

import unittest
from datetime import datetime, timezone

import iios_agent_performance_league as league


class Batch9SAgentPerformanceLeagueTest(unittest.TestCase):
    def test_mature_agent_can_rank_but_weighting_never_changes(self) -> None:
        learning = {
            "status": "OUTCOME_LEARNING_MEMORY_AVAILABLE",
            "outcome_count": 30,
            "mature_5d_count": 25,
            "complete_session_count": 6,
            "agent_scorecards": [
                {
                    "agent_key": "skeptic",
                    "agent": "Skeptic / Red Team",
                    "observations": 24,
                    "decisive_outcomes": 22,
                    "aligned_outcomes": 17,
                    "alignment_rate_pct": 77.27,
                    "average_confidence": 0.61,
                },
                {
                    "agent_key": "policy",
                    "agent": "Policy Analyst",
                    "observations": 10,
                    "decisive_outcomes": 8,
                    "aligned_outcomes": 5,
                    "alignment_rate_pct": 62.5,
                    "average_confidence": 0.55,
                },
            ],
            "recent_outcomes": [
                {
                    "case_id": "case_save",
                    "detected": True,
                    "decision_quality": "NO_TRADE_AVOIDED_DOWNSIDE",
                    "agents": [
                        {"agent_key": "skeptic", "alignment": "ALIGNED"},
                        {"agent_key": "policy", "alignment": "ALIGNED"},
                    ],
                }
            ],
        }
        telemetry = {
            "generated_at": "2026-08-28T22:00:00+00:00",
            "recent_promotions": [
                {"agents": {"agent_keys": ["skeptic", "policy"]}},
                {"agents": {"agent_keys": ["skeptic"]}},
            ],
        }
        payload = league.build_league(
            learning=learning,
            telemetry=telemetry,
            generated_at=datetime(2026, 8, 28, 22, 30, tzinfo=timezone.utc),
        )
        skeptic = next(row for row in payload["agent_standings"] if row["agent_key"] == "skeptic")
        policy = next(row for row in payload["agent_standings"] if row["agent_key"] == "policy")
        self.assertEqual(skeptic["status"], "OFFICIAL")
        self.assertTrue(skeptic["official_ranking_eligible"])
        self.assertEqual(skeptic["recent_case_participation"], 2)
        self.assertEqual(skeptic["outcome_attribution"]["downside_avoidance_alignment"], 1)
        self.assertEqual(policy["status"], "PROVISIONAL")
        self.assertFalse(payload["safety"]["agent_weight_change_authority"])
        self.assertFalse(payload["safety"]["model_routing_change_authority"])
        self.assertEqual(payload["summary"]["automatic_weight_changes"], 0)
        self.assertEqual(payload["summary"]["automatic_model_routing_changes"], 0)

    def test_factory_miss_without_case_is_not_blamed_on_agents(self) -> None:
        payload = league.build_league(
            learning={
                "status": "OUTCOME_LEARNING_MEMORY_AVAILABLE",
                "outcome_count": 1,
                "agent_scorecards": [],
                "recent_outcomes": [
                    {
                        "case_id": None,
                        "detected": False,
                        "decision_quality": "FACTORY_MISS_WITH_UPSIDE",
                        "agents": [],
                    }
                ],
            },
            telemetry={},
        )
        self.assertEqual(payload["summary"]["unattributed_factory_miss_count"], 1)
        self.assertTrue(all(row["status"] == "WARM_UP" for row in payload["agent_standings"]))
        self.assertIn("UNATTRIBUTED_TO_AGENTS", payload["measurement_contract"]["miss_attribution_rule"])

    def test_model_league_refuses_fake_performance_scores(self) -> None:
        payload = league.build_league(learning={}, telemetry={})
        self.assertEqual(len(payload["model_league"]), 4)
        self.assertEqual(payload["summary"]["ranked_model_count"], 0)
        for row in payload["model_league"]:
            self.assertEqual(row["status"], "UNRANKED_MEASUREMENT_GAP")
            self.assertIsNone(row["task_accuracy"])
            self.assertIsNone(row["latency"])
            self.assertIsNone(row["cost_per_useful_result"])


if __name__ == "__main__":
    unittest.main()
