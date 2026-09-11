"""Explicit-date migration: synthetic accounts, clocks and credential adapters only."""
import inspect
import unittest
from dataclasses import FrozenInstanceError
from datetime import timedelta
from unittest.mock import Mock, patch

from .collection_plan import (CREDENTIAL_BINDING, KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE,
    EARLY_CLOSES, HOLIDAYS, SessionPlan, digest, instant, request_plan,
    validate_account, validate_authority, validate_row)
from .collection_service import CollectionCredentials, main
from .collection_session import CollectionSession, Journal
from .collection_transport import CollectionBoundary
from .test_collection_session import account_document, grant_document, response, test_root


class CalendarMigrationTests(unittest.TestCase):
    def setUp(self):
        self.plan = SessionPlan("2026-09-14")
        self.now = self.plan.opening - timedelta(minutes=10)
        self.account = account_document() | {"session": self.plan.session,
            "spec_sha256": self.plan.spec_sha256, "previous_session": "2026-09-11",
            "observed_at": "2026-09-14T12:00:00Z", "valid_until": self.plan.expiry.isoformat()}
        self.grant = grant_document(digest(self.account)) | {"session": self.plan.session,
            "spec_sha256": self.plan.spec_sha256, "plan_sha256": digest(request_plan(plan=self.plan)),
            "approved_at": "2026-09-14T13:15:00Z", "arm_before": self.plan.opening.isoformat(),
            "expires_at": self.plan.expiry.isoformat()}

    def make_session(self):
        root = test_root()
        for name in ("state", "receipts", "raw", "inputs"):
            (root / name).mkdir(mode=0o700)
        self.boundary = Mock()
        def synthetic(row, deadline):
            if row["path"] == "/prices":
                from .collection_plan import canonical
                return 200, "application/json", canonical({"ticker": row["ticker"], "prices": [
                    {"time": self.plan.previous_session, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]})
            return response(row, self.now)
        self.boundary.request.side_effect = synthetic
        self.journal = Journal(root, "a" * 64, plan=self.plan)
        return CollectionSession(self.journal, self.account, digest(self.account), self.grant,
            digest(self.grant), clock=lambda: self.now, boundary=self.boundary, verify_runtime=Mock())

    def test_monday_exact_schedule(self):
        rows = request_plan(plan=self.plan)
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({r["proposal_row_sha256"] for r in rows}), 50)
        self.assertEqual(self.plan.previous_session, "2026-09-11")
        self.assertEqual(self.plan.opening, instant("2026-09-14T13:30:00Z"))
        self.assertEqual(self.plan.expiry, instant("2026-09-14T20:05:00Z"))
        self.assertEqual([r["target_pdt"][11:16] for r in rows[::10]], ["06:30", "06:32", "06:34", "09:30", "13:00"])
        self.assertEqual([sum(r["path"] == p for r in rows) for p in ("/prices/snapshot", "/prices", "/company/facts")], [30, 19, 1])
        self.assertTrue(all(r["retries"] == 0 and r["public_standard_request_units"] == 1 for r in rows))

    def test_calendar_holidays_weekends_invalid_range_and_early_close_fail_closed(self):
        for value in sorted(HOLIDAYS | EARLY_CLOSES) + ["2026-09-12", "2026-09-13", "2026-02-30",
                "2027-09-14", "2026-9-14", "2026-09-14T00:00:00", "2026-01-02", "", None]:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                SessionPlan(value)

    def test_previous_session_skips_exchange_holiday(self):
        self.assertEqual(SessionPlan("2026-09-08").previous_session, "2026-09-04")

    def test_daylight_saving_uses_zone_offsets(self):
        self.assertEqual(SessionPlan("2026-11-02").opening, instant("2026-11-02T14:30:00Z"))
        self.assertTrue(request_plan(plan=SessionPlan("2026-11-02"))[0]["dispatch_deadline_pdt"].endswith("-08:00"))

    def test_no_implicit_session_input(self):
        for function in (request_plan, validate_row, validate_account, validate_authority, CollectionBoundary, Journal):
            self.assertIs(inspect.signature(function).parameters["plan"].default, inspect.Parameter.empty)
        with self.assertRaises(TypeError):
            request_plan()
        with self.assertRaises(ValueError):
            request_plan(plan=None)
        with self.assertRaises(FrozenInstanceError):
            self.plan.session = "2026-09-11"

    def test_missing_cli_date_fails_before_root_or_credential_access(self):
        with patch("expansion_wing.collection_service.validate_installed") as validate, self.assertRaises(SystemExit):
            main(["validate", "--root", "/nonexistent-synthetic-root", "--release-sha256", "a" * 64, "--source-commit", "1" * 40])
        validate.assert_not_called()

    def test_wrong_session_row_rejected_by_transport_before_secret(self):
        credentials = Mock()
        boundary = CollectionBoundary(credentials, Mock(), plan=self.plan, stopped=lambda: False, clock=lambda: self.now)
        with self.assertRaises(ValueError):
            boundary.request(request_plan(plan=SessionPlan("2026-09-11"))[0], self.plan.expiry)
        credentials.retrieve.assert_not_called()

    def test_old_account_selector_wrong_dates_and_spec_fail_closed(self):
        for change in [{"credential_binding": "com.iios.expansion-wing.financial-datasets/financial-datasets-api-key"},
                {"session": "2026-09-11"}, {"previous_session": "2026-09-10"},
                {"spec_sha256": SessionPlan("2026-09-11").spec_sha256}, {"valid_until": "2026-09-11T20:05:00Z"}]:
            account = self.account | change
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_account(account, digest(account), self.now, plan=self.plan)
        validate_account(self.account, digest(self.account), self.now, plan=self.plan)

    def test_friday_authority_not_relabelled_as_monday(self):
        for change in [{"approved_at": "2026-09-11T13:15:00Z"}, {"session": "2026-09-11"},
                {"plan_sha256": digest(request_plan(plan=SessionPlan("2026-09-11")))}]:
            grant = self.grant | change
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_authority(grant, digest(grant), digest(self.account), "a" * 64, self.now, plan=self.plan)

    def test_exact_new_selector_only_mocked_secure_adapter(self):
        adapter = Mock(service=KEYCHAIN_SERVICE.encode("ascii"))
        adapter.retrieve_opaque.return_value = b"SYNTHETIC_ONLY_NOT_A_REAL_KEY"
        provider = CollectionCredentials(adapter)
        adapter.retrieve_opaque.assert_not_called()
        self.assertEqual(provider.retrieve(), b"SYNTHETIC_ONLY_NOT_A_REAL_KEY")
        self.assertEqual(adapter.retrieve_opaque.call_args.args, (KEYCHAIN_ACCOUNT,))
        self.assertEqual(CREDENTIAL_BINDING, "IIOS_FINANCIAL_DATASETS_API_KEY/iios-provider")
        for value in (b"com.iios.expansion-wing.financial-datasets", b"other"):
            rejected = Mock(service=value)
            with self.assertRaises(ValueError):
                CollectionCredentials(rejected)
            rejected.retrieve_opaque.assert_not_called()

    def test_secret_failure_redacted_no_fallback_or_retry(self):
        adapter = Mock(service=KEYCHAIN_SERVICE.encode("ascii"))
        adapter.retrieve_opaque.side_effect = RuntimeError("SYNTHETIC_SECRET_SENTINEL")
        with self.assertRaisesRegex(RuntimeError, "^KEYCHAIN_UNAVAILABLE$"):
            CollectionCredentials(adapter).retrieve()
        adapter.retrieve_opaque.assert_called_once()

    def test_monday_complete_50_no_51st_reservation(self):
        session = self.make_session()
        session.arm()
        for row in request_plan(plan=self.plan):
            self.now = instant(row["target_utc"])
            self.assertEqual(session.tick(), "OBSERVED")
        self.assertEqual(session.tick(), "WAIT")
        self.assertEqual(self.boundary.request.call_count, 50)
        self.assertEqual(sum(e["kind"] == "RESERVED" for e in self.journal.events()), 50)
        self.now = self.plan.expiry
        self.assertEqual(session.tick(), "CLOSED")
        self.assertEqual(self.journal.events()[-1]["coverage"]["classification"], "COMPLETE_SCHEDULED_COLLECTION")

    def test_monday_missed_opening_no_backfill(self):
        session = self.make_session()
        session.arm()
        self.now = self.plan.opening + timedelta(minutes=30)
        self.assertEqual(session.tick(), "OBSERVED")
        self.assertNotEqual(self.boundary.request.call_args.args[0]["type"], "OPENING")
        self.assertEqual(sum(e["kind"] == "MISSED" for e in self.journal.events()), 10)
        self.assertEqual(session.coverage(self.journal.events(), self.now)["classification"], "PARTIAL_SESSION")

    def test_monday_late_arm_stays_closed(self):
        session = self.make_session()
        self.now = self.plan.opening
        with self.assertRaises(ValueError):
            session.arm()
        self.boundary.request.assert_not_called()

    def test_monday_interrupted_request_never_retries(self):
        session = self.make_session()
        session.arm()
        self.now = self.plan.opening
        self.boundary.request.side_effect = TimeoutError("SYNTHETIC_TIMEOUT")
        self.assertEqual(session.tick(), "FAILED_CLOSED")
        self.assertEqual(session.tick(), "CLOSED")
        self.boundary.request.assert_called_once()

    def test_monday_cooperative_shutdown(self):
        from .collection_service import supervise
        session = self.make_session()
        session.arm()
        self.assertEqual(supervise(session, stop_requested=lambda: True), "STOPPED")
        self.assertTrue(self.journal.disarmed())
        self.boundary.request.assert_not_called()
