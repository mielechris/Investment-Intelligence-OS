from __future__ import annotations

import importlib.util
import inspect
import json
import os
import ssl
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch


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
    @staticmethod
    def _context(ca_count: int) -> Mock:
        context = Mock()
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.get_ca_certs.return_value = [{}] * ca_count
        return context

    def test_system_ca_is_preferred_when_valid(self):
        context = self._context(1)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(resilient.ssl, "create_default_context", return_value=context) as create:
                selected, source = resilient._ssl_context()
        self.assertIs(selected, context)
        self.assertEqual(source, "SYSTEM_CA")
        create.assert_called_once_with(cafile=None)

    def test_missing_system_ca_uses_existing_certifi_bundle(self):
        empty = self._context(0)
        trusted = self._context(1)
        certifi_path = Path(__file__)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(resilient.ssl, "create_default_context", side_effect=[empty, trusted]) as create:
                with patch.object(resilient, "_usable_file", side_effect=[None, certifi_path]):
                    selected, source = resilient._ssl_context()
        self.assertIs(selected, trusted)
        self.assertEqual(source, "CERTIFI_CA")
        self.assertEqual(create.call_args_list[-1].kwargs["cafile"], str(certifi_path))

    def test_missing_or_unreadable_ca_bundles_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(resilient.ssl, "create_default_context", return_value=self._context(0)):
                with patch.object(resilient, "_usable_file", return_value=None):
                    with self.assertRaises(resilient.SecureTrustUnavailable):
                        resilient._ssl_context()

    def test_tls_and_hostname_validation_failures_are_sanitized(self):
        certificate_error = ssl.SSLCertVerificationError(1, "hostname mismatch https://secret.invalid")
        wrapped = OSError("outer")
        wrapped.__cause__ = certificate_error
        self.assertEqual(resilient._failure_category(certificate_error), "TLS_VALIDATION_FAILED")
        self.assertEqual(resilient._failure_category(wrapped), "TLS_VALIDATION_FAILED")

    def test_no_unverified_tls_or_warning_suppression_constructs(self):
        source = inspect.getsource(resilient)
        forbidden = ("verify=False", "CERT_NONE", "_create_unverified_context", "disable_warnings", "check_hostname = False")
        for token in forbidden:
            self.assertNotIn(token, source)

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

    def test_provider_attempt_diagnostics_are_strictly_allowlisted(self):
        value = capture(ndx_count=5)
        value["indexes"]["NASDAQ100"].update(
            {
                "source_attempts": [
                    {
                        "provider": "https://secret.invalid/path",
                        "role": "uncontrolled role",
                        "result_category": "uncontrolled exception text",
                        "trust_source": "/private/ca.pem",
                    }
                ],
                "error": "SOURCE_UNAVAILABLE",
            }
        )
        attempt = collector._refresh_diagnostics(value)["sources"][1][
            "provider_attempts"
        ][0]
        self.assertEqual(
            attempt,
            {
                "provider": "UNKNOWN",
                "role": "SOURCE",
                "result_category": "SOURCE_UNAVAILABLE",
                "trust_source": None,
            },
        )

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
        direct_attempt = resilient._attempt("NASDAQ", "OFFICIAL_PRIMARY", "TIMEOUT")
        with patch.object(resilient, "_read_nasdaq100_direct", return_value=(None, [direct_attempt])):
            with patch.object(resilient, "_fetch", return_value=(raw, "text/csv", "CERTIFI_CA")):
                result = resilient._read_nasdaq100()
        self.assertTrue(result["verified_complete"])
        self.assertEqual(result["source_mode"], "GOVERNED_INDEX_TRACKER_MIRROR")
        self.assertEqual(result["source_publisher"], "BLACKROCK_ISHARES")
        self.assertEqual(result["benchmark"], "Nasdaq 100 Index")
        self.assertEqual(
            [(row["role"], row["result_category"]) for row in result["source_attempts"]],
            [("OFFICIAL_PRIMARY", "TIMEOUT"), ("GOVERNED_FALLBACK", "SUCCESS")],
        )
        self.assertEqual(result["trust_source"], "CERTIFI_CA")

    def test_both_nasdaq_paths_fail_with_separate_sanitized_attempts(self):
        direct_attempt = resilient._attempt("NASDAQ", "OFFICIAL_PRIMARY", "TLS_VALIDATION_FAILED")
        with patch.object(resilient, "_read_nasdaq100_direct", return_value=(None, [direct_attempt])):
            with patch.object(resilient, "_fetch", side_effect=ssl.SSLCertVerificationError(1, "secret URL")):
                result = resilient._read_nasdaq100()
        self.assertFalse(result["verified_complete"])
        self.assertEqual(result["error"], "TLS_VALIDATION_FAILED")
        self.assertEqual(len(result["source_attempts"]), 2)
        self.assertNotIn("secret", json.dumps(result))

    def test_thresholds_and_fail_closed_authority_are_unchanged(self):
        self.assertEqual(collector.production_index_universe.EXPECTED_COUNTS["SP500"], (490, 520))
        self.assertEqual(collector.production_index_universe.EXPECTED_COUNTS["NASDAQ100"], (95, 110))
        diagnostics = collector._refresh_diagnostics({})
        self.assertFalse(diagnostics["ledger_read"])
        self.assertFalse(diagnostics["ledger_write"])
        self.assertFalse(diagnostics["trade_execution_permission"])
        self.assertFalse(diagnostics["broker_connected"])
        self.assertFalse(diagnostics["live_execution"])


if __name__ == "__main__":
    unittest.main()
