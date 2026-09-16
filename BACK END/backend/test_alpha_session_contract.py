"""Offline admission regressions. All calendar and universe inputs are fixtures."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest

from alpha_session_contract import CALENDAR_SCHEMA, SCHEMA, validate_session
from provider_gateway_contract import content_hash, locked_authority


class SessionContractTests(unittest.TestCase):
    def setUp(self):
        self.universe = [f'S{i:03}' for i in range(517)]
        self.calendar = dict(schema=CALENDAR_SCHEMA, exchange='XNYS', timezone='America/New_York',
                             session='2026-09-16', open='2026-09-16T13:30:00+00:00',
                             close='2026-09-16T20:00:00+00:00', review_parent='b'*64)
        self.contract = dict(schema=SCHEMA, source_commit='a'*40, session='2026-09-16',
                             calendar_parent=content_hash(self.calendar), universe_parent=content_hash(self.universe),
                             valid_from='2026-09-16T13:00:00+00:00', expires_at='2026-09-16T20:15:00+00:00',
                             authority=locked_authority())
        self.now = datetime(2026, 9, 16, 13, 10, tzinfo=timezone.utc)
        self.repin()

    def repin(self):
        self.contract['calendar_parent'] = content_hash(self.calendar)
        self.contract['universe_parent'] = content_hash(self.universe)
        self.expected = dict(session=content_hash(self.contract), calendar=content_hash(self.calendar),
                             universe=content_hash(self.universe))

    def check(self):
        return validate_session(self.contract, self.calendar, self.universe, expected=self.expected, now=self.now)

    def test_valid_contract_never_grants_execution(self):
        result = self.check()
        self.assertEqual(result['status'], 'CONTRACT_VALID_ONLY')
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['production_qualified'])
        self.assertTrue(all(v is False for v in result['authority'].values()))

    def test_independent_pin_required_for_each_document(self):
        for name in self.expected:
            with self.subTest(name=name):
                original = self.expected[name]
                self.expected[name] = '0'*64
                with self.assertRaises(ValueError): self.check()
                self.expected[name] = original

    def test_universe_order_is_bound(self):
        self.universe.reverse()
        with self.assertRaises(ValueError): self.check()

    def test_calendar_parent_cannot_be_substituted(self):
        self.contract['calendar_parent'] = 'c'*64
        self.expected['session'] = content_hash(self.contract)
        with self.assertRaisesRegex(ValueError, 'SESSION_PARENTS'): self.check()

    def test_authority_rejects_integer_false_and_true(self):
        for value in (0, True):
            self.contract['authority']['live_execution'] = value
            self.repin()
            with self.assertRaisesRegex(ValueError, 'SESSION_AUTHORITY'): self.check()

    def test_expiry_boundary_and_naive_clock(self):
        for now in (datetime(2026, 9, 16, 20, 15, tzinfo=timezone.utc),
                    datetime(2026, 9, 16, 12, 59, tzinfo=timezone.utc), datetime(2026, 9, 16, 14)):
            self.now = now
            with self.assertRaises(ValueError): self.check()

    def test_unknown_fields_rejected_even_when_pinned(self):
        self.contract['live_mode'] = True
        self.repin()
        with self.assertRaisesRegex(ValueError, 'SESSION_SCHEMA'): self.check()

    def test_session_mismatch(self):
        self.calendar['session'] = '2026-09-14'
        self.repin()
        with self.assertRaisesRegex(ValueError, 'SESSION_DATE'): self.check()

    def test_short_session_supported_without_six_batch_assumption(self):
        self.calendar['close'] = '2026-09-16T17:00:00+00:00'
        self.repin()
        self.assertEqual(self.check()['status'], 'CONTRACT_VALID_ONLY')

    def test_winter_utc_offset_supported(self):
        self.calendar.update(session='2026-12-01', open='2026-12-01T14:30:00+00:00', close='2026-12-01T21:00:00+00:00')
        self.contract.update(session='2026-12-01', valid_from='2026-12-01T14:00:00+00:00', expires_at='2026-12-01T21:15:00+00:00')
        self.now = datetime(2026, 12, 1, 14, 10, tzinfo=timezone.utc)
        self.repin()
        self.assertEqual(self.check()['session'], '2026-12-01')

    def test_invalid_window_and_missing_review(self):
        original = deepcopy(self.calendar)
        for patch in ({'close': self.calendar['open']}, {'review_parent': ''},
                      {'open': '2026-09-16T13:30:00'}, {'close': '2026-09-17T00:01:00+00:00'}):
            self.calendar = original | patch
            self.repin()
            with self.assertRaises(ValueError): self.check()

    def test_duplicate_and_wrong_universe_size(self):
        for items in ([self.universe[0]]*517, self.universe[:-1]):
            self.universe = items
            self.repin()
            with self.assertRaises(ValueError): self.check()


if __name__ == '__main__':
    unittest.main()
