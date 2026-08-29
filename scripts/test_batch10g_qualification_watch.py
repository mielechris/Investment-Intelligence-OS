from __future__ import annotations

import unittest

import iios_qualification_watch as watch


class Batch10GQualificationWatchTest(unittest.TestCase):
    def test_zero_sample_stays_collection_only(self) -> None:
        payload = watch.build_watch(
            qualification={
                "status": "INSUFFICIENT_PAPER_SAMPLE",
                "sample_ready": False,
                "gates": [
                    {"gate": "COMPLETE_VALIDATION_SESSIONS", "observed": 0, "required": ">= 20", "state": "FAIL"},
                    {"gate": "GOVERNED_PAPER_TRANSACTIONS", "observed": 0, "required": ">= 30", "state": "FAIL"},
                    {"gate": "MATURE_5D_OUTCOMES", "observed": 0, "required": ">= 30", "state": "FAIL"},
                    {"gate": "MAX_DRAWDOWN", "observed": 0, "required": "absolute drawdown <= 10.0%", "state": "PASS"},
                    {"gate": "CUMULATIVE_PAPER_RETURN", "observed": 0, "required": ">= 0.0% after sample gate", "state": "PASS"},
                ],
            },
            readiness={"status": "NOT_READY_FOR_LIVE_CAPITAL", "gates": [{"gate": "HUMAN_CAPITAL_APPROVAL", "state": "UNRESOLVED_MANUAL_GATE"}]},
        )
        self.assertEqual(payload["phase"], "GOVERNED_PAPER_EVIDENCE_COLLECTION")
        self.assertEqual(payload["qualification_progress_pct"], 0.0)
        self.assertEqual(payload["next_action"], "CONTINUE_GOVERNED_PAPER_COLLECTION")
        self.assertFalse(payload["safety"]["auto_generate_trades"])
        self.assertFalse(payload["safety"]["auto_enable_live"])
        self.assertFalse(payload["safety"]["capital_authority"])

    def test_progress_is_evidence_based_and_capped(self) -> None:
        payload = watch.build_watch(
            qualification={
                "status": "INSUFFICIENT_PAPER_SAMPLE",
                "sample_ready": False,
                "gates": [
                    {"gate": "COMPLETE_VALIDATION_SESSIONS", "observed": 10, "required": ">= 20", "state": "FAIL"},
                    {"gate": "GOVERNED_PAPER_TRANSACTIONS", "observed": 15, "required": ">= 30", "state": "FAIL"},
                    {"gate": "MATURE_5D_OUTCOMES", "observed": 60, "required": ">= 30", "state": "PASS"},
                ],
            },
            readiness={"status": "NOT_READY_FOR_LIVE_CAPITAL", "gates": []},
        )
        self.assertEqual(payload["qualification_progress_pct"], 66.7)
        mature = next(row for row in payload["progress"] if row["gate"] == "MATURE_5D_OUTCOMES")
        self.assertEqual(mature["progress_pct"], 100.0)
        self.assertEqual(mature["remaining"], 0.0)

    def test_paper_pass_only_advances_to_human_review(self) -> None:
        payload = watch.build_watch(
            qualification={"status": "PAPER_QUALIFIED_FOR_HUMAN_READINESS_REVIEW", "sample_ready": True, "gates": []},
            readiness={"status": "NOT_READY_FOR_LIVE_CAPITAL", "gates": [{"gate": "LEGAL_COMPLIANCE_REVIEW", "state": "UNRESOLVED_MANUAL_GATE"}]},
        )
        self.assertEqual(payload["phase"], "HUMAN_READINESS_REVIEW_ELIGIBLE")
        self.assertEqual(payload["next_action"], "HUMAN_READINESS_REVIEW")
        self.assertFalse(payload["safety"]["auto_connect_broker"])
        self.assertFalse(payload["safety"]["trade_execution_permission"])


if __name__ == "__main__":
    unittest.main()
