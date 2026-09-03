from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
sys.path.insert(0, str(BACKEND))

SPEC = importlib.util.spec_from_file_location(
    "iios_market_benchmark_collector",
    ROOT / "scripts" / "iios_market_benchmark_collector.py",
)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)

import production_index_universe_resilient as resilient  # noqa: E402


def capture(sp_count: int = 500, ndx_count: int = 100) -> dict:
    indexes = {}
    merged = []
    for key, count in (("SP500", sp_count), ("NASDAQ100", ndx_count)):
        symbols = [f"{key[0]}{number}" for number in range(count)]
        merged.extend(symbols)
        indexes[key] = {
            "verified_complete": collector.production_index_universe.validate_index_count(
                key, symbols
            )[0],
            "symbol_count": count,
            "symbols": symbols,
            "source_mode": "OFFICIAL_WEB_SOURCE",
            "error": None,
        }
    complete = all(row["verified_complete"] for row in indexes.values())
    return {
        "verified_complete": complete,
        "strict_membership": complete,
        "symbols": merged if complete else [],
        "symbol_count": len(merged) if complete else 0,
        "indexes": indexes,
        "source_lineage": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


class BenchmarkUniverseRefreshTests(unittest.TestCase):
    def test_complete_official_universe_is_cached_without_authority(self):
        now = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark_universe.json"
            with patch.object(
                collector.production_index_universe_resilient,
                "refresh_official_index_universe",
                return_value=capture(),
            ):
                result = collector._refresh_official_universe(path, now)
            self.assertEqual(result["symbol_count"], 600)
            self.assertFalse(result["ledger_read"])
            self.assertFalse(result["ledger_write"])
            self.assertFalse(result["live_execution"])
            self.assertEqual(json.loads(path.read_text())["symbol_count"], 600)

    def test_incomplete_universe_reproduces_fail_closed_path(self):
        incomplete = capture(ndx_count=5)
        incomplete["indexes"]["NASDAQ100"]["error"] = (
            "NASDAQ100 parsed 5 symbols; governed range is 95-110"
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                collector.production_index_universe_resilient,
                "refresh_official_index_universe",
                return_value=incomplete,
            ):
                with self.assertRaises(collector.UniverseRefreshIncomplete) as raised:
                    collector._refresh_official_universe(
                        Path(directory) / "benchmark_universe.json",
                        datetime.now(timezone.utc),
                    )
        diagnostics = raised.exception.diagnostics
        ndx = diagnostics["sources"][1]
        self.assertEqual(ndx["received"], 5)
        self.assertEqual(ndx["failure_category"], "COUNT_OUT_OF_RANGE")
        self.assertFalse(diagnostics["ledger_write"])
        self.assertFalse(diagnostics["trade_execution_permission"])

    def test_duplicate_and_malformed_counts_are_sanitized(self):
        value = capture(ndx_count=5)
        value["indexes"]["NASDAQ100"].update(
            {
                "received_count": 9,
                "valid_count": 5,
                "rejected_count": 4,
                "duplicate_count": 2,
                "error": "malformed invalid symbol rows",
            }
        )
        row = collector._refresh_diagnostics(value)["sources"][1]
        self.assertEqual(row["received"], 9)
        self.assertEqual(row["valid"], 5)
        self.assertEqual(row["rejected"], 4)
        self.assertEqual(row["duplicate_count"], 2)
        self.assertEqual(row["failure_category"], "MALFORMED_ROWS")

    def test_pagination_failure_has_fixed_category(self):
        self.assertEqual(
            collector._failure_category("pagination next page missing"),
            "PAGINATION_INCOMPLETE",
        )

    def test_stale_response_and_wrong_session_date_are_fixed_categories(self):
        self.assertEqual(collector._failure_category("stale response"), "STALE_RESPONSE")
        self.assertEqual(
            collector._failure_category("wrong session date"),
            "WRONG_SESSION_DATE",
        )

    def test_timeout_and_rate_limit_are_fixed_categories(self):
        self.assertEqual(collector._failure_category("request timed out"), "TIMEOUT")
        self.assertEqual(collector._failure_category("HTTP 429"), "RATE_LIMITED")

    def test_cache_reuse_boundary_is_inclusive_and_then_expires(self):
        now = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)
        payload = {
            "verified_complete": True,
            "strict_membership": True,
            "symbols": ["AAPL"],
            "cached_at": (now - timedelta(hours=24)).isoformat(),
        }
        self.assertTrue(collector._cache_fresh(payload, now))
        payload["cached_at"] = (now - timedelta(hours=24, seconds=1)).isoformat()
        self.assertFalse(collector._cache_fresh(payload, now))

    def test_nasdaq_direct_failure_uses_labeled_governed_mirror(self):
        header = "Ticker,Name,Sector,Asset Class,Market Value"
        rows = [f"N{i},Company {i},Technology,Equity,1" for i in range(100)]
        raw = ("metadata\n" + header + "\n" + "\n".join(rows)).encode()
        with patch.object(resilient, "_read_nasdaq100_direct", return_value=(None, ["timeout"])):
            with patch.object(resilient, "_fetch", return_value=(raw, "text/csv")):
                result = resilient._read_nasdaq100()
        self.assertTrue(result["verified_complete"])
        self.assertEqual(result["source_mode"], "GOVERNED_INDEX_TRACKER_MIRROR")
        self.assertEqual(result["source_publisher"], "BLACKROCK_ISHARES")
        self.assertEqual(result["benchmark"], "Nasdaq 100 Index")


if __name__ == "__main__":
    unittest.main()
