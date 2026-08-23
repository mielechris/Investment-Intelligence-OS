import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SemiconductorIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "semiconductor.db")
        for name in (
            "semiconductor_intelligence",
            "monitoring_engine",
            "learning_loop",
            "ledger",
        ):
            sys.modules.pop(name, None)

        import ledger

        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import semiconductor_intelligence

        self.intel = importlib.reload(semiconductor_intelligence)
        self.case_id = "case_memory_test"
        case = {
            "case_id": self.case_id,
            "topic": "AI infrastructure demand may support semiconductor memory pricing",
            "evidence_summary": {"average_quality_score": 0.0},
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(
            self.case_id, "case", self.case_id, case, topic=case["topic"]
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_memory_profile_contains_official_and_market_context_sources(self):
        requests = self.intel.build_memory_source_requests("Micron memory thesis")
        self.assertEqual(len(requests), 9)
        sec_requests = [item for item in requests if item["source"] == "sec_companyfacts"]
        gdelt_requests = [item for item in requests if item["source"] == "gdelt_news"]
        fred_requests = [item for item in requests if item["source"] == "fred_series"]
        self.assertEqual(len(sec_requests), 5)
        self.assertEqual(len(gdelt_requests), 3)
        self.assertEqual(len(fred_requests), 1)
        ciks = {item["params"]["cik"] for item in sec_requests}
        self.assertIn(self.intel.MICRON_CIK, ciks)
        self.assertTrue(set(self.intel.HYPERSCALER_CIKS.values()).issubset(ciks))

    def test_apply_profile_keeps_same_case_and_arms_monitoring(self):
        profile = self.intel.apply_memory_profile(self.case_id)
        self.assertEqual(profile["case_id"], self.case_id)
        self.assertTrue(profile["enabled"])
        self.assertEqual(profile["ticker"], "MU.US")
        self.assertEqual(profile["analysis_mode"], "llm")
        self.assertEqual(len(profile["source_requests"]), 9)

    def test_full_reunderwrite_uses_same_case_and_stays_paper_only(self):
        packet = {
            "packet_version": "0.4.0",
            "generated_at": self.ledger.utc_now(),
            "items": [
                {
                    "evidence_id": "evidence_memory",
                    "claim": "Fresh memory evidence",
                    "quality_score": 0.9,
                    "stale": False,
                    "missing_fields": [],
                }
            ],
            "summary": {
                "evidence_count": 1,
                "stale_count": 0,
                "incomplete_count": 0,
                "conflict_count": 0,
                "average_quality_score": 0.9,
                "critical_flags": [],
            },
            "conflicts": [],
        }
        fake_refresh = {
            "profile": {"case_id": self.case_id},
            "snapshot": {
                "monitor_snapshot_id": "snapshot_memory",
                "evidence_packet": packet,
                "ingestion": {"source_results": []},
                "quote": {"status": "ok", "current_price": 100.0},
            },
            "position": {"case_id": self.case_id},
            "thesis": {"case_id": self.case_id, "thesis_status": "INTACT"},
            "surveillance": {"falsifiers_triggered": []},
        }
        committee = {
            "decision_id": "decision_memory",
            "case_id": self.case_id,
            "topic": "memory",
            "disposition": "WATCH",
            "confidence": 0.7,
            "paper_mode": True,
        }
        risk = {
            "risk_authorization_id": "risk_memory",
            "case_id": self.case_id,
            "decision_id": "decision_memory",
            "decision": "WATCH_ONLY",
            "allowed_notional": 0.0,
            "paper_mode": True,
        }
        execution = {
            "case_id": self.case_id,
            "decision_id": "decision_memory",
            "risk_authorization_id": "risk_memory",
            "execution": "NOT_SUBMITTED",
            "paper_mode": True,
            "live_execution": False,
        }

        import main

        with patch.object(self.intel, "refresh_profile", return_value=fake_refresh), \
             patch.object(main, "build_committee", return_value=committee) as build_committee, \
             patch.object(main, "evaluate_decision", return_value=risk), \
             patch.object(main, "submit_paper_order", return_value=execution):
            result = self.intel.run_full_memory_reunderwrite(self.case_id)

        review_case = build_committee.call_args.args[0]
        self.assertEqual(review_case["case_id"], self.case_id)
        self.assertEqual(review_case["evidence_summary"]["average_quality_score"], 0.9)
        self.assertEqual(result["case_id"], self.case_id)
        self.assertTrue(result["paper_mode"])
        self.assertFalse(result["live_execution"])
        self.assertEqual(result["execution"]["execution"], "NOT_SUBMITTED")


if __name__ == "__main__":
    unittest.main()
