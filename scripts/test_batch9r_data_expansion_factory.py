from __future__ import annotations

import unittest
from datetime import datetime, timezone

import iios_data_expansion_factory as factory


class Batch9RDataExpansionFactoryTest(unittest.TestCase):
    def _payload(self):
        return factory.build_data_expansion_factory(
            office={
                "status": "CHIEF_INTELLIGENCE_OFFICE_ADVISORY_READY",
                "analysis_coverage": {
                    "model_performance_by_task": False,
                    "unused_new_data_sources": False,
                },
            },
            lab={
                "status": "EXPERIMENT_AB_LAB_ADVISORY_READY",
                "summary": {"need_more_data_count": 5},
            },
            scorecard={
                "generated_at": "2026-08-28T20:00:00+00:00",
                "metrics": {
                    "benchmark_opportunity_count": 36,
                    "eventual_detected_count": 17,
                    "eventual_detection_rate_pct": 47.2,
                    "eventual_opportunity_miss_rate_pct": 52.8,
                },
            },
            telemetry={
                "generated_at": "2026-08-28T20:05:00+00:00",
                "providers": {"provider_error_count": 0},
            },
            generated_at=datetime(2026, 8, 28, 22, 0, tzinfo=timezone.utc),
        )

    def test_gap_driven_candidates_are_ranked_without_connecting_anything(self) -> None:
        payload = self._payload()
        self.assertEqual(payload["status"], "DATA_EXPANSION_FACTORY_ADVISORY_READY")
        gaps = {row["gap_id"]: row for row in payload["data_gaps"]}
        self.assertEqual(gaps["RADAR_EVENT_COVERAGE"]["severity"], "HIGH")
        self.assertIn("52.8%", gaps["RADAR_EVENT_COVERAGE"]["evidence"])
        self.assertIn("MODEL_PERFORMANCE_BY_TASK", gaps)
        self.assertGreaterEqual(payload["summary"]["candidate_source_count"], 10)
        self.assertEqual(payload["summary"]["shadow_connected_count"], 0)
        self.assertEqual(payload["summary"]["production_sources_added"], 0)

        top = payload["candidate_sources"]
        self.assertTrue(top)
        self.assertGreaterEqual(top[0]["priority_score"], top[-1]["priority_score"])
        self.assertTrue(any("RADAR_EVENT_COVERAGE" in row["closes_gaps"] for row in top))
        self.assertTrue(any(row["source_id"] == "MODEL_TASK_TELEMETRY" for row in top))

    def test_unknown_provider_attributes_are_not_fabricated(self) -> None:
        payload = self._payload()
        for row in payload["candidate_sources"]:
            self.assertEqual(row["quality_measurement_state"], "NOT_MEASURED_IN_9R")
            self.assertEqual(row["latency_measurement_state"], "NOT_MEASURED_IN_9R")
            self.assertEqual(row["coverage_measurement_state"], "NOT_MEASURED_IN_9R")
            self.assertEqual(row["data_provider_cost"], "NO_PERSISTED_COST_EVIDENCE")
            self.assertEqual(row["licensing_state"], "REVIEW_REQUIRED")
            self.assertFalse(row["shadow_feed_connected"])
            self.assertFalse(row["production_feed_enabled"])

    def test_existing_inventory_is_implementation_evidence_not_production_claim(self) -> None:
        payload = self._payload()
        inventory = {row["source_id"]: row for row in payload["current_source_inventory"]}
        self.assertIn("SEC_COMPANYFACTS", inventory)
        self.assertIn("YAHOO_CHART", inventory)
        self.assertEqual(inventory["SEC_COMPANYFACTS"]["inventory_state"], "IMPLEMENTATION_PRESENT")
        self.assertIn("implementation_evidence", inventory["YAHOO_CHART"])

    def test_safety_contract_blocks_provider_and_production_authority(self) -> None:
        safety = self._payload()["safety"]
        self.assertTrue(safety["advisory_only"])
        self.assertTrue(safety["research_only_until_human_approval"])
        self.assertTrue(safety["human_approval_required"])
        for key in (
            "auto_connect_provider",
            "auto_request_credentials",
            "credential_use_authority",
            "purchase_authority",
            "license_acceptance_authority",
            "production_feed_change_authority",
            "auto_apply_thresholds",
            "agent_weight_change_authority",
            "committee_change_authority",
            "risk_rule_change_authority",
            "capital_authority",
            "trade_execution_permission",
            "live_execution",
        ):
            self.assertFalse(safety[key], key)


if __name__ == "__main__":
    unittest.main()
