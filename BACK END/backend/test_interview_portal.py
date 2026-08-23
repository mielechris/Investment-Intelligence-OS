import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


class InterviewPortalTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "interviews.db")
        for name in ("interview_portal", "ledger"):
            sys.modules.pop(name, None)
        import ledger

        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import interview_portal

        self.portal = importlib.reload(interview_portal)
        self.interview = self.portal.create_interview(
            {
                "subject_name": "Test Professional",
                "professional_role": "Industry specialist",
                "objective": "Capture reusable semiconductor purchasing judgment",
            }
        )
        self.interview_id = self.interview["interview_id"]

    def tearDown(self):
        self.tempdir.cleanup()

    def test_transcript_is_persisted(self):
        updated = self.portal.update_transcript(
            self.interview_id,
            {"transcript": "When information is incomplete, I shorten the commitment horizon.", "append": False},
        )
        self.assertEqual(updated["status"], "READY_FOR_EXTRACTION")
        stored = self.ledger.get_object(self.interview_id)
        self.assertIn("shorten the commitment horizon", stored["transcript"])

    def test_human_approval_only_publishes_low_risk_selected_insights(self):
        packet_id = "interview_packet_test"
        packet = {
            "interview_insight_packet_id": packet_id,
            "interview_id": self.interview_id,
            "subject_name": "Test Professional",
            "insights": [
                {
                    "insight_index": 0,
                    "claim": "Use shorter commitments when evidence is incomplete",
                    "category": "decision_rule",
                    "confidence": 0.9,
                    "source_excerpt": "shorten the commitment horizon",
                    "applicability": "uncertain sourcing decisions",
                    "restriction_risk": "LOW",
                    "restriction_reason": "",
                },
                {
                    "insight_index": 1,
                    "claim": "Unreleased customer order detail",
                    "category": "signal",
                    "confidence": 0.9,
                    "source_excerpt": "private customer detail",
                    "applicability": "company forecast",
                    "restriction_risk": "HIGH",
                    "restriction_reason": "Potential non-public customer information",
                },
            ],
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(packet_id, "interview_insight_packet", self.interview_id, packet, parent_id=self.interview_id, topic=self.interview["objective"])

        result = self.portal.approve_judgment(
            self.interview_id,
            {
                "approved_insight_indexes": [0, 1],
                "attest_no_mnpi": True,
                "attest_right_to_use": True,
                "approval_notes": "Reviewed for research use",
            },
        )
        self.assertEqual(result["judgment_bank_entries_added"], 1)
        self.assertEqual(len(result["restricted_insights"]), 1)
        entries = self.ledger.list_objects(self.interview_id, "professional_judgment")
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["trade_execution_permission"])

    def test_approval_requires_attestations(self):
        with self.assertRaises(Exception):
            self.portal.approve_judgment(
                self.interview_id,
                {"approved_insight_indexes": [0], "attest_no_mnpi": False, "attest_right_to_use": True},
            )


if __name__ == "__main__":
    unittest.main()
