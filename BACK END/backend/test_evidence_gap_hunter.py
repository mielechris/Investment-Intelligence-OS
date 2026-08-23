import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


class EvidenceGapHunterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "gap_hunter.db")
        for name in ("evidence_gap_hunter", "ledger"):
            sys.modules.pop(name, None)
        import ledger

        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import evidence_gap_hunter

        self.hunter = importlib.reload(evidence_gap_hunter)
        self.case_id = "case_gap_test"
        case = {
            "case_id": self.case_id,
            "topic": "AI infrastructure demand may support semiconductor memory pricing",
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(self.case_id, "case", self.case_id, case, topic=case["topic"])
        decision = {
            "decision_id": "decision_gap_test",
            "case_id": self.case_id,
            "topic": case["topic"],
            "evidence_packet_id": "packet_gap_prior",
            "required_evidence": ["Current Micron inventory and capex evidence", "Downside risk and valuation context"],
            "confidence": 0.86,
            "disposition": "WATCH",
            "evidence_summary": {"evidence_count": 25, "average_quality_score": 0.51, "critical_flags": []},
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(decision["decision_id"], "committee_decision", self.case_id, decision, parent_id=self.case_id, topic=case["topic"])
        profile = {
            "monitor_profile_id": "monitor_gap_test",
            "case_id": self.case_id,
            "ticker": "MU.US",
            "direction": "LONG",
            "enabled": True,
            "created_at": self.ledger.utc_now(),
        }
        self.ledger.record_object(profile["monitor_profile_id"], "monitor_profile", self.case_id, profile, parent_id=self.case_id, topic=case["topic"])

    def tearDown(self):
        self.tempdir.cleanup()

    def test_gap_plan_targets_requirements_and_relevant_desks(self):
        plan = self.hunter.build_gap_plan(self.case_id)
        self.assertEqual(len(plan["requirements"]), 2)
        sources = [item["source"] for item in plan["source_requests"]]
        self.assertIn("google_news_rss", sources)
        self.assertIn("official_web", sources)
        self.assertIn("fundamentals", plan["targeted_desks"])
        self.assertIn("skeptic", plan["targeted_desks"])
        self.assertEqual(plan["ticker"], "MU.US")

    def test_qualified_candidate_requires_every_gate(self):
        agents = {
            key: {"disposition": "WATCH"}
            for key in self.hunter.AGENT_ORDER
        }
        committee = {
            "disposition": "WATCH",
            "confidence": 0.86,
            "required_evidence": [],
            "evidence_summary": {
                "evidence_count": 25,
                "average_quality_score": 0.72,
                "critical_flags": [],
            },
            "agents": agents,
        }
        risk = {"decision": "WATCH_ONLY", "triggered_rules": []}
        result = self.hunter._qualification_assessment(committee, risk)
        self.assertTrue(result["qualified_buy_candidate"])
        self.assertEqual(result["stage"], "QUALIFIED_BUY_CANDIDATE")
        self.assertFalse(result["paper_buy_enabled"])

        committee["required_evidence"] = ["Need one more item"]
        result = self.hunter._qualification_assessment(committee, risk)
        self.assertFalse(result["qualified_buy_candidate"])
        self.assertIn("required_evidence_resolved", result["unmet_requirements"])


if __name__ == "__main__":
    unittest.main()
