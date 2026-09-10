"""Offline compatibility is explicit; historical clocks never grant authority."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import truth_spine_authority as authority
from . import test_superbatch28_canonical_recovery as fixtures
from . import operational_market_executor_installer as installer
from .operational_market_executor import FixedClock
from .provider_readiness import operational_cost_binding, SystemCostClock
from .test_authority_fixtures import offline_boundary


def inventory(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class OfflineAuthorityTests(unittest.TestCase):
    def test_scoped_fixture_restores_production_deny(self):
        @offline_boundary('provider_requests')
        def test_mocked_boundary():
            authority.require_capability('provider_requests')
            with self.assertRaisesRegex(PermissionError, 'AUTHORITY_MISSING'):
                authority.require_capability('credential_access')
            with self.assertRaisesRegex(ValueError, 'CONTENT_HASH_INVALID'):
                authority.require_capability('provider_requests', document={})
        original = authority.require_capability
        test_mocked_boundary()
        self.assertIs(authority.require_capability, original)
        with self.assertRaisesRegex(PermissionError, 'AUTHORITY_MISSING'):
            authority.require_capability('provider_requests')

    def test_non_test_and_trading_permissions_rejected(self):
        for capability in ('paper_order', 'broker', 'promotion', 'live_execution',
                           'operational_ledger_write', 'paid_model_requests'):
            with self.subTest(capability=capability), self.assertRaises(ValueError):
                offline_boundary(capability)
        with self.assertRaisesRegex(ValueError, 'TEST_FUNCTION_REQUIRED'):
            offline_boundary('credential_access')(lambda: None)

    @offline_boundary('provider_requests', 'credential_access')
    def test_explicit_fixture_cannot_reach_real_boundary(self):
        with socket.socket() as connection, self.assertRaises(PermissionError):
            connection.connect(('203.0.113.1', 443))
        with self.assertRaises(PermissionError):
            Path('/nonexistent/Keychains/login.keychain-db').read_bytes()
        with self.assertRaises(PermissionError):
            Path('/nonexistent/permanent-test-write').write_text('forbidden')

    def test_environment_cannot_grant_authority(self):
        with patch.dict(os.environ, {'ALLOW_PROVIDER_REQUESTS': '1', 'ALLOW_PAPER_EXECUTION': '1'}):
            for capability in authority.CAPABILITIES:
                with self.subTest(capability=capability), self.assertRaises(PermissionError):
                    authority.require_capability(capability)


class CostClockTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CanonicalRecoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ready = self.fixture._readiness()
        self.expiry = datetime(2026, 9, 9, 20, 5, tzinfo=timezone.utc)

    def test_before_at_after_original_expiration(self):
        original = inventory(self.ready)
        for offset in (-1, 0, 1):
            with self.subTest(offset=offset):
                clock = FixedClock(self.expiry + timedelta(seconds=offset))
                if offset > 0:
                    with self.assertRaisesRegex(ValueError, 'OPERATIONAL_COST_BINDING_UNAVAILABLE'):
                        operational_cost_binding(root=self.ready, clock=clock, evaluation_classification='REPLAY')
                else:
                    result = operational_cost_binding(root=self.ready, clock=clock, evaluation_classification='REPLAY')
                    self.assertEqual(result['evaluated_at'], clock.now_utc().isoformat())
                    self.assertEqual(result['evaluation_classification'], 'REPLAY')
        self.assertEqual(inventory(self.ready), original)

    def test_future_observation_and_naive_time_fail_closed(self):
        for value in (datetime(2026, 9, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 9, 3)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                operational_cost_binding(root=self.ready, clock=FixedClock(value), evaluation_classification='HISTORICAL')

    def test_operational_path_rejects_injected_clock_before_state_access(self):
        with self.assertRaisesRegex(ValueError, 'PRODUCTION_SYSTEM_CLOCK_REQUIRED'):
            installer.reselect_corrected_september_9_generation(
                Path('/nonexistent'), clock=FixedClock(self.expiry))
        with self.assertRaisesRegex(ValueError, 'PRODUCTION_SYSTEM_CLOCK_REQUIRED'):
            operational_cost_binding(root=self.ready, clock=FixedClock(self.expiry))

    def test_replay_cannot_use_operational_root(self):
        with self.assertRaisesRegex(ValueError, 'ISOLATED_REPLAY_ROOT_REQUIRED'):
            installer.reselect_corrected_september_9_generation(
                installer.INSTALL_ROOT, clock=FixedClock(self.expiry), evaluation_classification='REPLAY')

    def test_system_clock_ignores_environment_and_expiry_is_real(self):
        before = datetime.now(timezone.utc)
        with patch.dict(os.environ, {'IIOS_NOW': '2026-09-09T03:00:00Z', 'FIXTURE_CLOCK': '2026-09-09T03:00:00Z'}):
            current = SystemCostClock().now_utc()
            self.assertLessEqual(before, current)
            self.assertLessEqual(current, datetime.now(timezone.utc))
            # Conditional only on whether this immutable historical fixture has expired.
            if current > self.expiry:
                original = inventory(self.ready)
                with self.assertRaisesRegex(ValueError, 'OPERATIONAL_COST_BINDING_UNAVAILABLE'):
                    operational_cost_binding(root=self.ready)
                self.assertEqual(inventory(self.ready), original)

    def test_receipt_binds_single_evaluation_and_restart_retains_bytes(self):
        obsolete = self.fixture._closed_and_incident_selected()
        class CountingClock:
            calls = 0
            def now_utc(self):
                self.calls += 1
                return datetime(2026, 9, 9, 3, tzinfo=timezone.utc)
        clock = CountingClock()
        with self.assertRaisesRegex(RuntimeError, 'INTERRUPTED_QUARANTINE'):
            installer.reselect_corrected_september_9_generation(
                self.fixture.root, readiness_root=self.ready, clock=clock,
                evaluation_classification='REPLAY', interrupt_after='quarantine')
        self.assertEqual(clock.calls, 1)
        path = self.fixture.root/'incidents'/installer.SUPERSESSION_NAME
        original = path.read_bytes()
        receipt = installer._validate_supersession(path, obsolete)
        self.assertEqual(receipt['cost_evaluation']['evaluated_at'], '2026-09-09T03:00:00+00:00')
        self.assertEqual(receipt['cost_evaluation']['evaluation_classification'], 'REPLAY')
        installer.reselect_corrected_september_9_generation(
            self.fixture.root, readiness_root=self.ready,
            clock=FixedClock(datetime(2026, 9, 9, 4, tzinfo=timezone.utc)), evaluation_classification='REPLAY')
        self.assertEqual(path.read_bytes(), original)

    def test_receipt_tamper_rejected_and_legacy_bytes_preserved(self):
        obsolete = self.fixture._closed_and_incident_selected()
        path = self.fixture.base/'legacy-receipt.json'
        installer._write(path, installer._supersession_document(obsolete))
        original = path.read_bytes()
        installer._validate_supersession(path, obsolete)
        self.assertEqual(path.read_bytes(), original)
        receipt = json.loads(original)
        receipt['provider_activity'] = True
        installer._write(path, receipt)
        with self.assertRaises(ValueError):
            installer._validate_supersession(path, obsolete)

    def test_ambiguous_clock_rejected(self):
        with self.assertRaisesRegex(ValueError, 'COST_CLOCK_AMBIGUOUS'):
            operational_cost_binding(root=self.ready, now=self.expiry, clock=FixedClock(self.expiry))
