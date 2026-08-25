import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


class HardDataTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "hard_data.db")
        for name in ("hard_data", "ledger"):
            sys.modules.pop(name, None)
        import ledger

        self.ledger = importlib.reload(ledger)
        self.ledger.init_ledger()
        import hard_data

        self.hard = importlib.reload(hard_data)
        self.case_id = "case_hard_data_test"
        case = {
            "case_id": self.case_id,
            "topic": "AI infrastructure demand may support semiconductor memory pricing",
            "created_at": self.ledger.utc_now(),
            "paper_mode": True,
        }
        self.ledger.record_object(self.case_id, "case", self.case_id, case, topic=case["topic"])
        decision = {
            "decision_id": "decision_hard_data_test",
            "case_id": self.case_id,
            "topic": case["topic"],
            "required_evidence": [
                "Micron's latest filing-based revenue mix, HBM volumes and margins, inventory, free cash flow, debt, cash, capex commitments, and sensitivity to memory ASPs",
                "Current independent DRAM, HBM, and NAND spot and contract pricing by product and quarter",
                "Current MU price, valuation multiples, consensus estimates, volume and trend data, options positioning, and portfolio exposure overlap",
            ],
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

    def tearDown(self):
        self.tempdir.cleanup()

    def _request(self, **overrides):
        base = dict(
            lane="memory_pricing",
            metric="HBM3E contract price index",
            value_text="112.4",
            unit="index",
            period="2026-Q3",
            observed_at="2026-08-23T10:00:00-07:00",
            source_name="Licensed memory pricing feed",
            source_url="https://example.com/memory-pricing",
            source_kind="licensed_data",
            notes="Verified source snapshot",
            verified_against_source=True,
            permitted_use=True,
        )
        base.update(overrides)
        return self.hard.HardDataCreateRequest(**base)

    def test_verified_hard_data_becomes_case_evidence_and_maps_gap(self):
        record = self.hard.create_hard_data(self.case_id, self._request())
        self.assertEqual(record["admission_status"], "ADMITTED")
        self.assertIn("DRAM", record["gap_requirement"])
        evidence = self.hard.hard_data_evidence(self.case_id)
        self.assertEqual(len(evidence), 1)
        self.assertTrue(evidence[0]["hard_data_verified"])
        self.assertEqual(evidence[0]["source_type"], "market_data")
        self.assertEqual(evidence[0]["gap_requirement"], record["gap_requirement"])

    def test_valuation_lane_uses_best_requirement_not_first_volume_match(self):
        record = self.hard.create_hard_data(
            self.case_id,
            self._request(
                lane="valuation_positioning",
                metric="MU.US market price",
                value_text="966.78",
                unit="USD/share",
                source_name="Yahoo Finance",
                source_url="https://finance.yahoo.com/quote/MU/",
                source_kind="market_data",
            ),
        )
        self.assertIn("Current MU price", record["gap_requirement"])
        self.assertNotIn("filing-based revenue mix", record["gap_requirement"])
        self.assertEqual(record["gap_mapping_mode"], "AUTO")

    def test_existing_auto_mapping_is_repaired(self):
        wrong = self.hard.create_hard_data(
            self.case_id,
            self._request(
                lane="valuation_positioning",
                metric="MU.US market price",
                value_text="966.78",
                unit="USD/share",
                source_name="Yahoo Finance",
                source_url="https://finance.yahoo.com/quote/MU/",
                source_kind="market_data",
                gap_requirement="Micron's latest filing-based revenue mix, HBM volumes and margins, inventory, free cash flow, debt, cash, capex commitments, and sensitivity to memory ASPs",
            ),
        )
        # Simulate a pre-v0.10.1 auto-mapped record: remove the explicit marker while
        # leaving the wrong stored requirement in place.
        legacy = {**wrong, "gap_mapping_mode": None}
        self.ledger.record_object(
            legacy["hard_data_id"],
            "hard_data_record",
            self.case_id,
            legacy,
            topic=legacy["topic"],
        )
        status = self.hard.hard_data_status(self.case_id)
        repaired = status["records"][0]
        self.assertIn("Current MU price", repaired["gap_requirement"])
        self.assertEqual(repaired["gap_mapping_mode"], "AUTO")

    def test_unverified_record_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self.hard.create_hard_data(
                self.case_id,
                self._request(verified_against_source=False),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self.hard.hard_data_evidence(self.case_id), [])

    def test_manual_observation_is_context_only(self):
        record = self.hard.create_hard_data(
            self.case_id,
            self._request(
                source_kind="manual_observation",
                source_name="Analyst observation",
                source_url="https://example.com/notes",
            ),
        )
        self.assertEqual(record["admission_status"], "CONTEXT_ONLY")
        self.assertEqual(self.hard.hard_data_evidence(self.case_id), [])

    def test_lane_status_reports_admitted_counts(self):
        self.hard.create_hard_data(self.case_id, self._request())
        status = self.hard.hard_data_status(self.case_id)
        self.assertEqual(status["lanes"]["memory_pricing"]["admitted_records"], 1)
        self.assertEqual(status["admitted_evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
