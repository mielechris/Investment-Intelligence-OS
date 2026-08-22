import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "test_ledger.db")
        sys.modules.pop("ledger", None)
        import ledger
        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_record_and_retrieve_case(self):
        case = {
            "case_id": "case_test",
            "topic": "test thesis",
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(
            "case_test",
            "case",
            "case_test",
            case,
            topic=case["topic"],
        )
        loaded = self.ledger.get_object("case_test")
        self.assertEqual(loaded["topic"], "test thesis")

    def test_authorization_is_one_time_consumable(self):
        authorization = {
            "risk_authorization_id": "risk_test",
            "case_id": "case_test",
            "decision_id": "decision_test",
            "topic": "test thesis",
            "created_at": self.ledger.utc_now(),
            "decision": "WATCH_ONLY",
            "allowed_notional": 0,
        }
        self.ledger.record_object(
            "risk_test",
            "risk_authorization",
            "case_test",
            authorization,
            parent_id="decision_test",
            topic=authorization["topic"],
        )
        self.assertTrue(self.ledger.consume_authorization("risk_test"))
        self.assertFalse(self.ledger.consume_authorization("risk_test"))
        self.assertTrue(self.ledger.authorization_consumed("risk_test"))

    def test_audit_returns_objects_and_events(self):
        case = {
            "case_id": "case_audit",
            "topic": "audit thesis",
            "created_at": self.ledger.utc_now(),
        }
        self.ledger.record_object(
            "case_audit",
            "case",
            "case_audit",
            case,
            topic=case["topic"],
        )
        self.ledger.record_event(
            "case_audit",
            "CASE_CREATED",
            entity_id="case_audit",
            payload={"topic": case["topic"]},
        )
        audit = self.ledger.get_audit("case_audit")
        self.assertEqual(len(audit["objects"]), 1)
        self.assertEqual(len(audit["events"]), 1)
        self.assertEqual(audit["events"][0]["event_type"], "CASE_CREATED")


if __name__ == "__main__":
    unittest.main()
