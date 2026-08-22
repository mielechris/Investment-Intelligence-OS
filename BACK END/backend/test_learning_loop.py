import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


AGENT_KEYS = [
    "policy",
    "macro",
    "fundamentals",
    "market_structure",
    "commodities",
    "geo_weather",
    "skeptic",
    "portfolio",
]


class LearningLoopTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "learning_test.db")
        sys.modules.pop("learning_loop", None)
        sys.modules.pop("ledger", None)
        import ledger
        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import learning_loop
        self.loop = importlib.reload(learning_loop)
        self.case_id = "case_learning"
        self._seed_case()

    def tearDown(self):
        self.tempdir.cleanup()

    def _seed_case(self):
        case = {
            "case_id": self.case_id,
            "topic": "Semiconductor paper thesis",
            "paper_mode": True,
            "created_at": self.ledger.utc_now(),
        }
        self.ledger.record_object(self.case_id, "case", self.case_id, case, topic=case["topic"])
        decision = {
            "decision_id": "decision_learning",
            "case_id": self.case_id,
            "topic": case["topic"],
            "disposition": "WATCH",
            "confidence": 0.70,
            "paper_mode": True,
            "created_at": self.ledger.utc_now(),
        }
        self.ledger.record_object(
            decision["decision_id"],
            "committee_decision",
            self.case_id,
            decision,
            parent_id=self.case_id,
            topic=case["topic"],
        )
        for index, key in enumerate(AGENT_KEYS):
            disposition = "WATCH" if index < 4 else "NO_TRADE"
            agent = {
                "agent_result_id": f"agent_{key}",
                "case_id": self.case_id,
                "agent_key": key,
                "agent": key.replace("_", " ").title(),
                "disposition": disposition,
                "confidence": 0.75 if disposition == "WATCH" else 0.80,
                "falsifier": f"{key} falsifier",
                "missing_evidence": [],
                "created_at": self.ledger.utc_now(),
            }
            self.ledger.record_object(
                agent["agent_result_id"],
                "agent_result",
                self.case_id,
                agent,
                parent_id=decision["decision_id"],
                topic=case["topic"],
            )

    def test_shadow_position_and_broken_thesis_exit(self):
        position = self.loop.record_position_monitor({
            "case_id": self.case_id,
            "direction": "LONG",
            "reference_price": 100,
            "current_price": 94,
        })
        self.assertEqual(position["mode"], "SHADOW_CASE")
        self.assertEqual(position["return_pct"], -6.0)
        self.assertIn("NO_PAPER_ORDER_EXISTS", position["flags"])

        thesis = self.loop.record_thesis_monitor({
            "case_id": self.case_id,
            "falsifiers_triggered": ["fundamentals"],
            "catalyst_status": "MISSED",
        })
        self.assertEqual(thesis["thesis_status"], "THESIS_BROKEN")
        self.assertIn("FALSIFIER_TRIGGERED", thesis["flags"])

        reunderwrite = self.loop.record_reunderwrite({"case_id": self.case_id})
        self.assertEqual(reunderwrite["action"], "EXIT_SHADOW_CASE")
        self.assertFalse(reunderwrite["live_execution"])

    def test_postmortem_updates_judgment_bank_and_scorecards(self):
        result = self.loop.record_postmortem({
            "case_id": self.case_id,
            "outcome": "INVALIDATED",
            "realized_return_pct": -8.5,
            "horizon_days": 30,
        })
        self.assertEqual(result["postmortem"]["agent_count"], 8)
        self.assertEqual(len(result["judgment_entries"]), 8)

        watch_entries = [entry for entry in result["judgment_entries"] if entry["original_disposition"] == "WATCH"]
        no_trade_entries = [entry for entry in result["judgment_entries"] if entry["original_disposition"] == "NO_TRADE"]
        self.assertTrue(all(entry["correct"] is False for entry in watch_entries))
        self.assertTrue(all(entry["correct"] is True for entry in no_trade_entries))

        scorecards = self.loop.build_agent_scorecards()
        self.assertEqual(len(scorecards), 8)
        by_key = {item["agent_key"]: item for item in scorecards}
        self.assertEqual(by_key["skeptic"]["accuracy"], 1.0)
        self.assertEqual(by_key["policy"]["accuracy"], 0.0)

    def test_learning_events_are_persisted(self):
        self.loop.record_position_monitor({"case_id": self.case_id})
        self.loop.record_thesis_monitor({"case_id": self.case_id})
        self.loop.record_reunderwrite({"case_id": self.case_id})
        self.loop.record_postmortem({"case_id": self.case_id, "outcome": "INCONCLUSIVE"})
        audit = self.ledger.get_audit(self.case_id)
        event_types = [event["event_type"] for event in audit["events"]]
        self.assertIn("POSITION_MONITORED", event_types)
        self.assertIn("THESIS_MONITORED", event_types)
        self.assertIn("REUNDERWRITE_COMPLETE", event_types)
        self.assertIn("POST_MORTEM_COMPLETE", event_types)
        self.assertIn("JUDGMENT_BANK_UPDATED", event_types)


if __name__ == "__main__":
    unittest.main()
