import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


class DecisionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "history.db")
        for name in ("decision_history", "ledger"):
            sys.modules.pop(name, None)
        import ledger
        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import decision_history
        self.history = importlib.reload(decision_history)
        self.case_id = "case_history_test"
        case = {
            "case_id": self.case_id,
            "topic": "Micron memory thesis",
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(self.case_id, "case", self.case_id, case, topic=case["topic"])

    def tearDown(self):
        self.tempdir.cleanup()

    def _decision(self, number, disposition, confidence, quality, fundamentals_disposition):
        decision_id = f"decision_history_{number}"
        packet_id = f"packet_history_{number}"
        agents = {}
        for key in self.history.AGENT_ORDER:
            agent_disposition = fundamentals_disposition if key == "fundamentals" else disposition
            agents[key] = {
                "agent_key": key,
                "agent": key,
                "room": key,
                "disposition": agent_disposition,
                "confidence": confidence,
                "headline": f"{key} round {number}",
                "falsifier": f"{key} falsifier",
                "missing_evidence": [],
            }
        decision = {
            "decision_id": decision_id,
            "case_id": self.case_id,
            "evidence_packet_id": packet_id,
            "evidence_summary": {
                "evidence_count": number * 5,
                "average_quality_score": quality,
                "critical_flags": [],
            },
            "topic": "Micron memory thesis",
            "headline": f"Round {number}",
            "summary": "summary",
            "agreement": "agreement",
            "dissent": "dissent",
            "bull_case": "bull",
            "bear_case": "bear",
            "required_evidence": ["more evidence"] if number < 3 else [],
            "confidence": confidence,
            "disposition": disposition,
            "agents": agents,
            "created_at": f"2026-08-2{number}T10:00:00+00:00",
            "paper_mode": True,
        }
        self.ledger.record_object(decision_id, "committee_decision", self.case_id, decision, parent_id=packet_id, topic=decision["topic"])
        risk = {
            "risk_authorization_id": f"risk_history_{number}",
            "decision_id": decision_id,
            "case_id": self.case_id,
            "decision": "VETOED",
            "allowed_notional": 0.0,
            "triggered_rules": ["EVIDENCE_QUALITY_BELOW_THRESHOLD"] if quality < 0.55 else ["OPEN_EVIDENCE_REQUIREMENTS"] if number < 3 else [],
            "created_at": decision["created_at"],
        }
        self.ledger.record_object(risk["risk_authorization_id"], "risk_authorization", self.case_id, risk, parent_id=decision_id, topic=decision["topic"])
        execution = {
            "execution_id": f"paper_history_{number}",
            "decision_id": decision_id,
            "case_id": self.case_id,
            "execution": "NOT_SUBMITTED",
            "reason": "RISK_NOT_APPROVED",
            "created_at": decision["created_at"],
        }
        self.ledger.record_object(execution["execution_id"], "execution", self.case_id, execution, parent_id=risk["risk_authorization_id"], topic=decision["topic"])
        if number > 1:
            full = {
                "full_reunderwrite_id": f"full_history_{number}",
                "case_id": self.case_id,
                "committee": {"decision_id": decision_id},
                "created_at": decision["created_at"],
            }
            self.ledger.record_object(full["full_reunderwrite_id"], "full_reunderwrite", self.case_id, full, parent_id=decision_id, topic=decision["topic"])

    def test_history_orders_rounds_and_detects_agent_shift(self):
        self._decision(1, "NO_TRADE", 0.12, 0.0, "NO_TRADE")
        self._decision(2, "WATCH", 0.80, 0.51, "WATCH")
        self._decision(3, "WATCH", 0.86, 0.60, "WATCH")
        result = self.history.build_case_history(self.case_id)
        self.assertEqual(result["round_count"], 3)
        self.assertEqual(result["rounds"][0]["round_type"], "INITIAL")
        self.assertEqual(result["rounds"][1]["round_type"], "REUNDERWRITE")
        self.assertEqual(result["rounds"][2]["committee"]["confidence"], 0.86)
        changed_keys = {item["agent_key"] for item in result["rounds"][1]["agent_changes"]}
        self.assertIn("fundamentals", changed_keys)
        self.assertEqual(result["signal_ladder"]["current_stage"], "WATCH")
        self.assertFalse(result["signal_ladder"]["qualified_buy_candidate_enabled"])
        self.assertFalse(result["signal_ladder"]["paper_buy_enabled"])


if __name__ == "__main__":
    unittest.main()
