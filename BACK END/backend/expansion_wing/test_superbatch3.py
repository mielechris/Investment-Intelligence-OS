from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from expansion_wing.compositor import compose_snapshot
from expansion_wing.models import Book
from expansion_wing.portfolio import DualBookPortfolio, FillModel
from expansion_wing.schema_maps import CONTRACTS

FIXTURES = Path(__file__).with_name("fixtures")
NOW = datetime(2026, 9, 3, 20, 5, tzinfo=timezone.utc)


def paths() -> dict[str, Path]:
    return {name: FIXTURES / f"{name}.json" for name in CONTRACTS}


class SchemaMappingTests(unittest.TestCase):
    def test_all_source_controlled_contract_fixtures_map(self):
        for name, contract in CONTRACTS.items():
            payload = json.loads((FIXTURES / f"{name}.json").read_text())
            mapped = contract.map(payload)
            self.assertTrue(mapped["complete"], (name, mapped["errors"]))
            self.assertTrue(mapped["observed_at"])

    def test_legacy_schema_is_explicitly_incomplete(self):
        mapped = CONTRACTS["9h"].map({"schema_version": "legacy-v0", "session_id": "x", "observed_at": NOW.isoformat()})
        self.assertFalse(mapped["complete"])
        self.assertIn("LEGACY_OR_UNKNOWN_SCHEMA", mapped["errors"])

    def test_malformed_root_is_incomplete(self):
        mapped = CONTRACTS["9j"].map(["not", "an", "object"])
        self.assertFalse(mapped["complete"])
        self.assertIn("MALFORMED_ROOT", mapped["errors"])


class SnapshotCompositorTests(unittest.TestCase):
    def test_healthy_fixture_composes_bounded_snapshot(self):
        snapshot = compose_snapshot(paths(), fixture=True, now=NOW)
        self.assertEqual(snapshot["mode"], "FIXTURE_NON_LIVE")
        self.assertEqual(snapshot["bounded_source_count"], 7)
        self.assertEqual(snapshot["sections"]["radar"]["state"], "CURRENT")
        self.assertEqual(snapshot["sections"]["books"]["data"]["starting_cash"], 10000)

    def test_stale_condition_is_truthful(self):
        snapshot = compose_snapshot(paths(), fixture=True, now=NOW + timedelta(hours=2))
        self.assertEqual(snapshot["sections"]["radar"]["state"], "STALE")

    def test_missing_source_is_unavailable(self):
        source_paths = paths(); source_paths["9j"] = None
        snapshot = compose_snapshot(source_paths, fixture=True, now=NOW)
        self.assertEqual(snapshot["sections"]["outcomes_9j"]["state"], "UNAVAILABLE")

    def test_malformed_source_is_unavailable_and_error_is_sanitized(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "bad.json"; bad.write_text("bad")
            source_paths = paths(); source_paths["9a"] = bad
            snapshot = compose_snapshot(source_paths, fixture=True, now=NOW)
            receipt = next(row for row in snapshot["source_receipts"] if row["source"] == "9a")
            self.assertEqual(receipt["error"], "JSONDecodeError")
            self.assertNotIn(str(bad), str(receipt))

    def test_cross_session_mismatch_is_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            altered = json.loads((FIXTURES / "9i.json").read_text()); altered["session_ids"] = ["different-session"]
            file = Path(folder) / "9i.json"; file.write_text(json.dumps(altered))
            source_paths = paths(); source_paths["9i"] = file
            snapshot = compose_snapshot(source_paths, fixture=True, now=NOW)
            self.assertEqual(snapshot["sections"]["shadow_9i"]["state"], "INCOMPLETE")
            self.assertIn("CROSS_SESSION_MISMATCH", snapshot["sections"]["shadow_9i"]["data"]["mapping_errors"])

    def test_duplicate_cross_source_payload_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            duplicate = Path(folder) / "same.json"; duplicate.write_text(json.dumps({"observed_at": NOW.isoformat()}))
            source_paths = paths(); source_paths["9a"] = duplicate; source_paths["9b"] = duplicate
            snapshot = compose_snapshot(source_paths, fixture=True, now=NOW)
            receipt = next(row for row in snapshot["source_receipts"] if row["source"] == "9b")
            self.assertTrue(receipt["duplicate"])

    def test_source_limit_fails_closed(self):
        source_paths = paths() | {"extra": None}
        with self.assertRaises(ValueError): compose_snapshot(source_paths, fixture=True, now=NOW)


class StrategicBookLifecycleTests(unittest.TestCase):
    def test_valuation_required(self):
        result = DualBookPortfolio().open_position(book=Book.STRATEGIC, instrument="FIX", quantity=2,
            reference_price=100, thesis="fixture thesis", invalidation="fixture invalidation")
        self.assertIn("STRATEGIC_VALUATION_REQUIRED", result["reasons"])

    def test_partial_and_full_exit_pnl_and_reconciliation(self):
        portfolio = DualBookPortfolio()
        opened = portfolio.open_position(book=Book.STRATEGIC, instrument="FIX", quantity=10, reference_price=100,
            thesis="fixture thesis", invalidation="fixture invalidation", valuation={"method": "DCF", "fair_value": 120},
            fill_model=FillModel(0, 0, 1))
        self.assertEqual(opened["status"], "PAPER_FILLED")
        partial = portfolio.exit_position(book=Book.STRATEGIC, instrument="FIX", quantity=4, reference_price=110,
                                          reason="fixture trim", fill_model=FillModel(0, 0, 1))
        self.assertEqual(partial["status"], "PAPER_PARTIAL_EXIT")
        self.assertEqual(partial["realized_pnl"], 40)
        full = portfolio.exit_position(book=Book.STRATEGIC, instrument="FIX", quantity=6, reference_price=90,
                                       reason="fixture invalidation", fill_model=FillModel(0, 0, 1))
        self.assertEqual(full["status"], "PAPER_FULL_EXIT")
        self.assertEqual(full["realized_pnl"], -60)
        self.assertEqual(portfolio.strategic.realized_pnl, -20)
        self.assertEqual(portfolio.reconcile()["status"], "RECONCILED")
        self.assertEqual(portfolio.snapshot()["total_nav"], 9980)

    def test_exit_cannot_cross_position_or_book(self):
        portfolio = DualBookPortfolio()
        portfolio.open_position(book=Book.STRATEGIC, instrument="FIX", quantity=2, reference_price=100,
            thesis="fixture", invalidation="fixture", valuation={"fair_value": 120}, fill_model=FillModel(0, 0, 1))
        self.assertEqual(portfolio.exit_position(book=Book.STRATEGIC, instrument="FIX", quantity=3,
            reference_price=100, reason="fixture")["status"], "REJECTED")
        self.assertEqual(portfolio.exit_position(book=Book.TACTICAL, instrument="FIX", quantity=1,
            reference_price=100, reason="fixture")["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
