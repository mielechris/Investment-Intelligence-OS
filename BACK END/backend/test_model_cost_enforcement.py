import json
import multiprocessing
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import model_cost_enforcement as cost


def _process_admission(directory, query, policy, queue):
    import model_cost_enforcement as process_cost

    process_cost.DEFAULT_COST_DIR = Path(directory)
    process_cost.POLICY.update(policy)
    queue.put(process_cost.preflight_xai_request(query=query, model="grok-4.6", estimated_input_tokens=1)["allow"])


class ModelCostEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(cost, "DEFAULT_COST_DIR", Path(self.temporary_directory.name))
        self.root_patch.start()
        self.policy = dict(cost.POLICY)
        cost.POLICY.update({"pricing_verified": True, "pricing_source_name": "TEST", "pricing_source_reference": "test://pricing", "pricing_verified_date": "2026-08-01", "pricing_verifier_id": "TEST-REVIEW", "pricing_expires_date": "2026-12-31"})

    def tearDown(self):
        cost.POLICY.clear()
        cost.POLICY.update(self.policy)
        self.root_patch.stop()
        self.temporary_directory.cleanup()

    def test_reservations_block_concurrent_admissions_before_hard_limit(self):
        outcomes = []
        barrier = threading.Barrier(2)

        def admit(index):
            barrier.wait()
            outcomes.append(cost.preflight_xai_request(query=f"query {index}", model="grok-4.6", estimated_input_tokens=1))

        with patch.dict(cost.POLICY, {"daily_hard_limit_ticks": 3, "rolling_7d_hard_limit_ticks": 3, "max_estimated_input_tokens_per_request": 1, "max_output_tokens_per_request": 1, "max_x_search_tool_calls_per_request": 1, "input_ticks_per_million_tokens": 1, "output_ticks_per_million_tokens": 1, "x_search_ticks_per_call": 2, "reservation_safety_margin_numerator": 1, "reservation_safety_margin_denominator": 1}):
            threads = [threading.Thread(target=admit, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(sum(result["allow"] for result in outcomes), 1)
        self.assertEqual(sum(result["decision"] == "BLOCK_HARD_BUDGET" for result in outcomes), 1)

    def test_reservation_uses_named_pricing_formula(self):
        with patch.dict(cost.POLICY, {
            "max_estimated_input_tokens_per_request": 100,
            "max_output_tokens_per_request": 10,
            "max_x_search_tool_calls_per_request": 2,
            "input_ticks_per_million_tokens": 1_000_000_000,
            "output_ticks_per_million_tokens": 2_000_000_000,
            "x_search_ticks_per_call": 30_000_000_000,
            "reservation_safety_margin_numerator": 3,
            "reservation_safety_margin_denominator": 2,
        }):
            self.assertEqual(cost.maximum_request_reservation_ticks(model="grok-4.6"), 90_000_180_000)

    def test_stale_or_invalid_pricing_fails_closed(self):
        with patch.dict(cost.POLICY, {"pricing_verified_date": "2000-01-01"}):
            with self.assertRaisesRegex(RuntimeError, "pricing policy is stale"):
                cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)

    def test_unverified_pricing_creates_no_reservation(self):
        with patch.dict(cost.POLICY, {"pricing_verified": False}):
            with self.assertRaisesRegex(RuntimeError, "pricing is unverified"):
                cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        self.assertFalse(Path(self.temporary_directory.name, cost.RESERVATION_NAME).exists())
        with patch.dict(cost.POLICY, {"x_search_ticks_per_call": 0}):
            with self.assertRaisesRegex(RuntimeError, "pricing policy is invalid"):
                cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)

    def test_multiprocess_admission_blocks_daily_and_weekly_hard_limits(self):
        policy = {"pricing_verified": True, "pricing_source_name": "TEST", "pricing_source_reference": "test://pricing", "pricing_verified_date": "2026-08-01", "pricing_verifier_id": "TEST-REVIEW", "pricing_expires_date": "2026-12-31", "daily_hard_limit_ticks": 3, "rolling_7d_hard_limit_ticks": 3, "max_estimated_input_tokens_per_request": 1, "max_output_tokens_per_request": 1, "max_x_search_tool_calls_per_request": 1, "input_ticks_per_million_tokens": 1, "output_ticks_per_million_tokens": 1, "x_search_ticks_per_call": 2, "reservation_safety_margin_numerator": 1, "reservation_safety_margin_denominator": 1}
        queue = multiprocessing.Queue()
        processes = [multiprocessing.Process(target=_process_admission, args=(self.temporary_directory.name, f"query-{index}", policy, queue)) for index in range(2)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(5)
        self.assertTrue(all(process.exitcode == 0 for process in processes))
        self.assertEqual([queue.get(timeout=1) for _ in processes].count(True), 1)

    def test_unpriced_response_settles_reservation_as_conservative_estimate(self):
        admission = cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        row = cost.record_xai_response({}, model="grok-4.6", query="query", case_id="case", latency_ms=1, reservation_id=admission["reservation_id"])

        self.assertEqual(row["cost_ticks"], admission["reserved_cost_ticks"])
        self.assertEqual(row["cost_source"], "RESERVATION_CONSERVATIVE_ESTIMATE")
        reservations = json.loads((Path(self.temporary_directory.name) / cost.RESERVATION_NAME).read_text())
        self.assertEqual(reservations["reservations"], [])

    def test_exact_provider_cost_settles_reservation_with_reported_ticks(self):
        admission = cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        row = cost.record_xai_response(
            {"usage": {"cost_in_usd_ticks": 2500000000}},
            model="grok", query="query", case_id="case", latency_ms=1, reservation_id=admission["reservation_id"],
        )

        self.assertEqual(row["cost_ticks"], 2500000000)
        self.assertEqual(row["cost_source"], "XAI_COST_IN_USD_TICKS")

    def test_failure_settles_and_redacts_persisted_error(self):
        admission = cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        secret = "Bearer xai-secret-token-value"
        row = cost.record_xai_failure(model="grok", query="query", case_id=None, latency_ms=1, error_type=secret, reservation_id=admission["reservation_id"])

        persisted = (Path(self.temporary_directory.name) / cost.LEDGER_NAME).read_text()
        self.assertNotIn("xai-secret-token-value", row["error_type"])
        self.assertNotIn("xai-secret-token-value", persisted)
        self.assertEqual(row["cost_source"], "RESERVATION_CONSERVATIVE_ESTIMATE")

    def test_pre_provider_cancellation_is_idempotent_and_provider_start_rejects_it(self):
        admission = cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        first = cost.cancel_xai_reservation(reservation_id=admission["reservation_id"], reason="MISSING_CREDENTIALS")
        second = cost.cancel_xai_reservation(reservation_id=admission["reservation_id"], reason="MISSING_CREDENTIALS")
        self.assertFalse(first["already_cancelled"])
        self.assertTrue(second["already_cancelled"])
        self.assertEqual(cost._read_reservations(Path(self.temporary_directory.name)), [])

        started = cost.preflight_xai_request(query="different", model="grok-4.6", estimated_input_tokens=1)
        cost.mark_xai_provider_invocation_started(reservation_id=started["reservation_id"])
        with self.assertRaisesRegex(RuntimeError, "invocation has started"):
            cost.cancel_xai_reservation(reservation_id=started["reservation_id"], reason="TOO_LATE")

    def test_charge_write_failure_retains_reservation_and_removal_failure_is_idempotent(self):
        admission = cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        with patch.object(cost, "_append_jsonl", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cost.record_xai_response({}, model="grok-4.6", query="query", case_id=None, latency_ms=1, reservation_id=admission["reservation_id"])
        self.assertEqual(len(cost._read_reservations(Path(self.temporary_directory.name))), 1)
        with patch.object(cost, "_remove_settled_reservation", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                cost.record_xai_response({}, model="grok-4.6", query="query", case_id=None, latency_ms=1, reservation_id=admission["reservation_id"])
        row = cost.record_xai_response({}, model="grok-4.6", query="query", case_id=None, latency_ms=1, reservation_id=admission["reservation_id"])
        self.assertEqual(row["reservation_id"], admission["reservation_id"])
        self.assertEqual(len(cost._read_events(Path(self.temporary_directory.name))), 1)

    def test_exact_cost_breach_blocks_future_admission(self):
        admission = cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        cost.record_xai_response({"usage": {"cost_in_usd_ticks": admission["reserved_cost_ticks"] + 1}}, model="grok-4.6", query="query", case_id=None, latency_ms=1, reservation_id=admission["reservation_id"])
        blocked = cost.preflight_xai_request(query="different", model="grok-4.6", estimated_input_tokens=1)
        self.assertEqual(blocked["decision"], "BLOCK_BUDGET_INTEGRITY")

    def test_malformed_ledger_and_unsafe_path_fail_closed(self):
        Path(self.temporary_directory.name, cost.LEDGER_NAME).write_text("not-json\n")
        with self.assertRaisesRegex(RuntimeError, "ledger is malformed"):
            cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        with patch.object(cost, "DEFAULT_COST_DIR", Path("relative-ledger")):
            with self.assertRaisesRegex(RuntimeError, "path is unsafe"):
                cost.preflight_xai_request(query="other", model="grok-4.6", estimated_input_tokens=1)

    def test_malformed_reservation_schema_and_lock_timeout_fail_closed(self):
        Path(self.temporary_directory.name, cost.RESERVATION_NAME).write_text('{"reservations":[{"reservation_id":"bad","amount_usd":"0"}]}')
        with self.assertRaisesRegex(RuntimeError, "reservations are malformed"):
            cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        Path(self.temporary_directory.name, cost.RESERVATION_NAME).unlink()
        with patch.object(cost.fcntl, "flock", side_effect=BlockingIOError), patch.object(cost, "LOCK_TIMEOUT_SECONDS", 0):
            with self.assertRaisesRegex(RuntimeError, "lock unavailable"):
                cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)

    def test_symlinked_ledger_and_encoded_secrets_fail_safely(self):
        target = Path(self.temporary_directory.name, "target.jsonl")
        target.write_text("")
        Path(self.temporary_directory.name, cost.LEDGER_NAME).symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "ledger is unsafe"):
            cost.preflight_xai_request(query="query", model="grok-4.6", estimated_input_tokens=1)
        sanitized = cost.sanitize_error("AUTHORIZATION: bearer xai-abcdefghijkl https://example.test/?%61pi_key=sk-abcdefghijkl&token=xai-secret")
        self.assertNotIn("sk-abcdefghijkl", sanitized)
        self.assertNotIn("xai-secret", sanitized)

    def test_sanitize_error_removes_headers_urls_and_provider_tokens(self):
        message = "Authorization: Bearer xai-secret-token-value https://user:pass@example.test/?api_key=sk-secret-value"
        sanitized = cost.sanitize_error(message)
        for secret in ("xai-secret-token-value", "sk-secret-value", "user:pass"):
            self.assertNotIn(secret, sanitized)


if __name__ == "__main__":
    unittest.main()