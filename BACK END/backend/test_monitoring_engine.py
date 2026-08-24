import importlib
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


class MonitoringEngineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "monitoring.db")
        for name in ("monitoring_engine", "learning_loop", "ledger"):
            sys.modules.pop(name, None)
        import ledger
        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import learning_loop
        import monitoring_engine
        self.learning_loop = importlib.reload(learning_loop)
        self.monitoring = importlib.reload(monitoring_engine)

        self.case = {
            "case_id": "case_monitor_test",
            "topic": "Semiconductor memory demand remains constructive",
            "evidence_summary": {"average_quality_score": 0.8},
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(
            self.case["case_id"], "case", self.case["case_id"], self.case, topic=self.case["topic"]
        )
        self.decision = {
            "decision_id": "decision_monitor_test",
            "case_id": self.case["case_id"],
            "topic": self.case["topic"],
            "disposition": "WATCH",
            "confidence": 0.72,
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(
            self.decision["decision_id"],
            "committee_decision",
            self.case["case_id"],
            self.decision,
            parent_id=self.case["case_id"],
            topic=self.case["topic"],
        )
        for index, key in enumerate((
            "policy", "macro", "fundamentals", "market_structure",
            "commodities", "geo_weather", "skeptic", "portfolio",
        )):
            agent = {
                "agent_result_id": f"agent_monitor_{index}",
                "case_id": self.case["case_id"],
                "agent_key": key,
                "agent": key,
                "disposition": "WATCH",
                "confidence": 0.6,
                "falsifier": f"{key} falsifier",
                "missing_evidence": [],
                "created_at": self.ledger.utc_now(),
            }
            self.ledger.record_object(
                agent["agent_result_id"], "agent_result", self.case["case_id"], agent,
                parent_id=self.case["case_id"], topic=self.case["topic"],
            )

    def tearDown(self):
        self.monitoring.stop_scheduler()
        self.tempdir.cleanup()

    def test_configure_profile_uses_safe_default_interval(self):
        profile = self.monitoring.configure_profile({
            "case_id": self.case["case_id"],
            "interval_minutes": 5,
            "ticker": "MU.US",
            "direction": "LONG",
            "reference_price": 100,
            "analysis_mode": "deterministic",
        })
        self.assertEqual(profile["interval_minutes"], 60)
        self.assertTrue(profile["enabled"])
        self.assertEqual(profile["ticker"], "MU.US")
        self.assertEqual(len(profile["source_requests"]), 2)

    def test_due_logic(self):
        now = datetime.now(timezone.utc)
        profile = {"enabled": True, "interval_minutes": 60, "last_refresh_at": None}
        self.assertTrue(self.monitoring._is_due(profile, now))
        profile["last_refresh_at"] = (now - timedelta(minutes=30)).isoformat()
        self.assertFalse(self.monitoring._is_due(profile, now))
        profile["last_refresh_at"] = (now - timedelta(minutes=61)).isoformat()
        self.assertTrue(self.monitoring._is_due(profile, now))

    def test_refresh_persists_snapshot_position_and_thesis(self):
        profile = self.monitoring.configure_profile({
            "case_id": self.case["case_id"],
            "interval_minutes": 60,
            "ticker": "MU.US",
            "direction": "LONG",
            "reference_price": 100,
            "analysis_mode": "deterministic",
            "source_requests": [],
        })
        evidence = [{
            "source": "test",
            "source_type": "official",
            "evidence_type": "market_data",
            "claim": "Fresh monitoring evidence",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reliability_score": 0.9,
        }]
        fake_ingestion = {
            "fetched_at": self.ledger.utc_now(),
            "requested_sources": 0,
            "successful_sources": 0,
            "failed_sources": 0,
            "evidence_items": evidence,
            "source_results": [],
        }
        fake_quote = {
            "status": "ok",
            "items": [],
            "current_price": 95.0,
            "error": None,
        }
        surveillance = {
            "falsifiers_triggered": [],
            "catalyst_status": "ON_TRACK",
            "summary": "No stored falsifier triggered.",
        }
        safe_capital_watch = {
            "case_id": self.case["case_id"],
            "stage": "RESEARCH_NOT_QUALIFIED",
            "position_sizing_ready": False,
            "paper_authorization_ready": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        with patch.object(self.monitoring, "ingest_sources", return_value=fake_ingestion), \
             patch.object(self.monitoring, "_fetch_stooq_quote", return_value=fake_quote), \
             patch.object(self.monitoring, "_falsifier_review", return_value=surveillance), \
             patch.object(self.monitoring, "refresh_capital_entry_watch", return_value=safe_capital_watch):
            result = self.monitoring.refresh_profile(profile)

        self.assertEqual(result["position"]["return_pct"], -5.0)
        self.assertEqual(result["thesis"]["thesis_status"], "REUNDERWRITE_REQUIRED")
        self.assertEqual(result["capital_entry_watch"]["stage"], "RESEARCH_NOT_QUALIFIED")
        self.assertEqual(len(self.ledger.list_objects(self.case["case_id"], "monitor_snapshot")), 1)
        self.assertEqual(len(self.ledger.list_objects(self.case["case_id"], "position_monitor")), 1)
        self.assertEqual(len(self.ledger.list_objects(self.case["case_id"], "thesis_monitor")), 1)
        event_types = [item["event_type"] for item in self.ledger.get_audit(self.case["case_id"])["events"]]
        self.assertIn("AUTOMATIC_EVIDENCE_REFRESH", event_types)
        self.assertIn("AUTO_MONITOR_COMPLETE", event_types)

    def test_dashboard_reports_case_health(self):
        self.monitoring.configure_profile({
            "case_id": self.case["case_id"],
            "analysis_mode": "deterministic",
        })
        dashboard = self.monitoring.build_dashboard()
        self.assertEqual(dashboard["count"], 1)
        self.assertEqual(dashboard["cases"][0]["health"], "AUTO_WATCH")
        self.assertTrue(dashboard["cases"][0]["monitoring_enabled"])


if __name__ == "__main__":
    unittest.main()
