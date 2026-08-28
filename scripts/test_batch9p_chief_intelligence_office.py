from __future__ import annotations

import unittest
from datetime import datetime, timezone

import iios_chief_intelligence_office as cio


class Batch9PChiefIntelligenceOfficeTest(unittest.TestCase):
    def test_builds_ranked_advisory_memo_from_persisted_measurements(self) -> None:
        payload = cio.build_office(
            scorecard={
                "generated_at": "2026-08-28T22:00:00+00:00",
                "metrics": {
                    "benchmark_opportunity_count": 36,
                    "eventual_detected_count": 17,
                    "eventual_detection_rate_pct": 47.2,
                    "eventual_opportunity_miss_rate_pct": 52.8,
                },
            },
            shadow={"complete_session_count": 0, "recommendations": []},
            learning={"outcome_count": 0, "mature_5d_count": 0},
            telemetry={"paper_fund": {"nav": 10000.0, "position_count": 0}},
            episode={"status": "FINAL_WITH_LEARNING_WARMUP"},
            generated_at=datetime(2026, 8, 28, 22, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(payload["status"], "CHIEF_INTELLIGENCE_OFFICE_ADVISORY_READY")
        self.assertEqual(payload["current_weaknesses"][0]["area"], "RADAR_QUALITY")
        memo = payload["improvement_memo"]["top_five_upgrades"]
        self.assertGreaterEqual(len(memo), 4)
        self.assertEqual(memo[0]["upgrade_id"], "RADAR_RECALL_REVIEW")
        self.assertEqual(memo[0]["suggested_implementation_batch"], "9Q")
        self.assertFalse(payload["analysis_coverage"]["model_performance_by_task"])
        safety = payload["safety"]
        self.assertTrue(safety["advisory_only"])
        self.assertTrue(safety["human_approval_required"])
        self.assertFalse(safety["auto_apply_thresholds"])
        self.assertFalse(safety["agent_weight_change_authority"])
        self.assertFalse(safety["committee_change_authority"])
        self.assertFalse(safety["risk_rule_change_authority"])
        self.assertFalse(safety["capital_authority"])
        self.assertFalse(safety["trade_execution_permission"])
        self.assertFalse(safety["live_execution"])

    def test_rejects_self_modifying_upgrades(self) -> None:
        payload = cio.build_office(
            scorecard={"metrics": {}}, shadow={}, learning={}, telemetry={}, episode={}
        )
        rejected = {row["upgrade"] for row in payload["rejected_upgrades"]}
        self.assertIn("AUTO_TUNE_THRESHOLDS", rejected)
        self.assertIn("AUTO_REWEIGHT_AGENTS", rejected)
        self.assertIn("LIVE_CAPITAL_ACCELERATION", rejected)


if __name__ == "__main__":
    unittest.main()
