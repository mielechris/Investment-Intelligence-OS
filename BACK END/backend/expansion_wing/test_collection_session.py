"""Synthetic collection tests. No provider, credentials, services or ledger access."""
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

from functools import partial
from .collection_plan import (SessionPlan, CREDENTIAL_BINDING, FORBIDDEN, PATHS, TICKERS,
    canonical, digest, instant, request_plan, validate_account, validate_authority, validate_row)
from .collection_session import CollectionSession, Journal, exclusive, observation
from .collection_service import DeferredBoundary, supervise

# Explicit historical regression fixture, never a production default.
PLAN = SessionPlan("2026-09-11")
SESSION, OPEN, EXPIRY, SPEC_SHA256 = PLAN.session, PLAN.opening, PLAN.expiry, PLAN.spec_sha256
request_plan = partial(request_plan, plan=PLAN)
validate_row = partial(validate_row, plan=PLAN)
validate_account = partial(validate_account, plan=PLAN)
validate_authority = partial(validate_authority, plan=PLAN)
Journal = partial(Journal, plan=PLAN)


def test_root():
    parent = Path(os.environ['IIOS_COLLECTION_TEST_ROOT']).resolve(strict=True)
    return Path(tempfile.mkdtemp(prefix='case-', dir=parent))


def account_document():
    return {'session': SESSION, 'spec_sha256': SPEC_SHA256, 'entitled': True,
        'tickers': list(TICKERS), 'paths': list(PATHS), 'unit_costs': dict.fromkeys(PATHS, 1),
        'reserved_credits': 50, 'available_credits': 50, 'requests_per_minute': 10,
        'overage_or_topup': False, 'internal_use_permitted': True, 'calendar_open': True,
        'previous_session': '2026-09-10', 'ambiguous_billing': 'RESERVE_FULL_COST_NO_RETRY',
        'account_reference': 'SYNTHETIC_ACCOUNT', 'reservation_reference': 'SYNTHETIC_RESERVATION',
        'credential_binding': CREDENTIAL_BINDING,
        'observed_at': '2026-09-11T12:00:00Z', 'valid_until': EXPIRY.isoformat(),
        'entitlement_source_sha256': 'e'*64, 'cost_balance_source_sha256': 'c'*64,
        'calendar_source_sha256': 'd'*64}


def grant_document(account_hash, release='a'*64):
    return {'session': SESSION, 'spec_sha256': SPEC_SHA256, 'plan_sha256': digest(request_plan()),
        'account_sha256': account_hash, 'release_sha256': release, 'owner_approved': True,
        'authority': dict.fromkeys(FORBIDDEN, False), 'maximum_credits': 50, 'maximum_requests': 50,
        'approved_at': '2026-09-11T13:15:00Z', 'arm_before': OPEN.isoformat(),
        'expires_at': EXPIRY.isoformat(), 'owner_receipt_sha256': 'f'*64}


def response(row, now):
    if row['path'] == '/prices/snapshot':
        value = {'snapshot': {'ticker': row['ticker'], 'time': now.isoformat(), 'price': 10}}
    elif row['path'] == '/company/facts':
        value = {'company_facts': {'ticker': 'MU', 'name': 'Synthetic'}}
    else:
        value = {'ticker': row['ticker'], 'prices': [{'time': '2026-09-10',
            'open': 1, 'high': 2, 'low': 1, 'close': 2, 'volume': 10}]}
    return 200, 'application/json', canonical(value)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.root = test_root()
        for name in ('state', 'receipts', 'raw', 'inputs'):
            (self.root/name).mkdir(mode=0o700)
        self.now = instant('2026-09-11T13:20:00Z')
        self.account = account_document()
        self.grant = grant_document(digest(self.account))
        self.boundary = Mock()
        self.boundary.request.side_effect = lambda row, deadline: response(row, self.now)
        self.verify = Mock()
        self.journal = Journal(self.root, 'a'*64)
        self.session = self.make_session()

    def make_session(self):
        return CollectionSession(self.journal, self.account, digest(self.account), self.grant,
            digest(self.grant), clock=lambda:self.now, boundary=self.boundary, verify_runtime=self.verify)

    def arm(self):
        self.session.arm()

    def test_exact_preserved_50_rows(self):
        expected = json.loads(Path(os.environ['IIOS_COLLECTION_PRIOR_ROWS']).read_text())
        self.assertEqual(request_plan(), expected)
        self.assertEqual(len({r['proposal_row_sha256'] for r in request_plan()}), 50)
        self.assertEqual(sum(r['public_standard_request_units'] for r in request_plan()), 50)

    def test_schedule_tampering_rejected(self):
        for field, value in [('target_utc',OPEN.isoformat()), ('host','other.example'), ('retries',1), ('ticker','AAPL')]:
            row = request_plan()[49]; row[field] = value
            with self.assertRaises(ValueError): validate_row(row)

    def test_same_day_fresh_arm_no_provider_or_credential_access(self):
        self.arm(); self.assertEqual(self.journal.events()[0]['kind'], 'ARMED')
        self.boundary.request.assert_not_called()

    def test_prior_day_naive_future_wrong_date_authority_rejected(self):
        for value in ['2026-09-10T13:15:00Z','2026-09-11T13:15:00','2026-09-11T13:25:00Z','2026-09-12T13:15:00Z']:
            grant = self.grant | {'approved_at': value}
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_authority(grant,digest(grant),digest(self.account),'a'*64,self.now,arming=True)

    def test_stale_approval_rejected(self):
        grant=self.grant | {'approved_at':'2026-09-11T12:00:00Z'}
        with self.assertRaises(ValueError): validate_authority(grant,digest(grant),digest(self.account),'a'*64,self.now,arming=True)

    def test_wrong_expiry_or_parent_or_extra_authority_rejected(self):
        for change in [{'expires_at':'2026-09-11T20:04:00Z'}, {'account_sha256':'b'*64},
                       {'release_sha256':'b'*64}, {'authority':dict.fromkeys(FORBIDDEN,True)}]:
            grant=self.grant | change
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_authority(grant,digest(grant),digest(self.account),'a'*64,self.now)

    def test_missing_independent_pin_rejected(self):
        with self.assertRaises(ValueError): validate_account(self.account,None,self.now)
        with self.assertRaises(ValueError): validate_account(self.account,'b'*64,self.now)

    def test_account_gates_fail_closed(self):
        changes=[{'entitled':False},{'available_credits':49},{'reserved_credits':0},
                 {'paths':['/prices']},{'tickers':['MU']},{'unit_costs':dict.fromkeys(PATHS,2)},
                 {'requests_per_minute':9},{'overage_or_topup':True},{'calendar_open':False},
                 {'valid_until':'2026-09-11T20:04:00Z'},{'previous_session':'2026-09-09'}]
        for change in changes:
            account=self.account|change
            with self.subTest(change=change),self.assertRaises(ValueError):validate_account(account,digest(account),self.now)

    def test_late_arm_rejected(self):
        self.now=OPEN
        with self.assertRaises(ValueError):self.arm()
        self.boundary.request.assert_not_called()

    def test_disabled_does_not_construct_boundary(self):
        self.assertEqual(self.session.tick(),'DISABLED')
        self.boundary.request.assert_not_called()

    def test_preopen_wait_no_access(self):
        self.arm();self.assertEqual(self.session.tick(),'WAIT');self.boundary.request.assert_not_called()

    def test_all_50_exact_times_and_restart_no_duplicates(self):
        self.arm()
        for row in request_plan():
            self.now=instant(row['target_utc'])
            self.assertEqual(self.make_session().tick(),'OBSERVED')
            self.assertIn(self.make_session().tick(),('WAIT','RATE_WAIT'))
        self.assertEqual(self.boundary.request.call_count,50)
        self.now=EXPIRY
        self.assertEqual(self.session.tick(),'CLOSED')
        coverage=self.journal.events()[-1]['coverage']
        self.assertEqual(coverage['classification'],'COMPLETE_SCHEDULED_COLLECTION')
        self.assertFalse(coverage['official_close_proven'])

    def test_missed_opening_never_backfilled_or_full_day(self):
        self.arm();self.now=instant('2026-09-11T14:00:00Z')
        self.assertEqual(self.session.tick(),'OBSERVED')
        self.assertNotEqual(self.boundary.request.call_args.args[0]['type'],'OPENING')
        report=self.session.coverage(self.journal.events(),self.now)
        self.assertEqual(report['classification'],'PARTIAL_SESSION')
        self.assertEqual(report['missing_opening_tickers'],list(TICKERS))

    def test_nominal_time_never_early(self):
        self.arm();self.now=OPEN-timedelta(microseconds=1)
        self.assertEqual(self.session.tick(),'WAIT');self.boundary.request.assert_not_called()

    def test_rolling_rate_is_persisted(self):
        self.arm();self.now=instant('2026-09-11T13:40:00Z')
        for _ in range(10):self.assertEqual(self.make_session().tick(),'OBSERVED')
        self.assertEqual(self.make_session().tick(),'RATE_WAIT')
        self.now+=timedelta(seconds=60)
        self.assertEqual(self.make_session().tick(),'OBSERVED')

    def test_crash_reservation_never_retried(self):
        self.arm();self.now=OPEN
        with self.journal.lock():self.journal.append('RESERVED',self.now,row=request_plan()[0]['proposal_row_sha256'],cost=1)
        self.assertEqual(self.make_session().tick(),'FAILED_CLOSED')
        self.boundary.request.assert_not_called()

    def test_provider_failure_preserved_sanitized_and_terminal(self):
        self.arm();self.now=OPEN;self.boundary.request.side_effect=RuntimeError('SECRET_SENTINEL')
        self.assertEqual(self.session.tick(),'FAILED_CLOSED')
        self.assertEqual(self.make_session().tick(),'CLOSED')
        self.assertEqual(self.boundary.request.call_count,1)
        self.assertNotIn('SECRET_SENTINEL',json.dumps(self.journal.events()))

    def test_response_after_expiry_fails(self):
        self.arm();self.now=instant('2026-09-11T20:00:00Z')
        def late(row, deadline):
            self.now=EXPIRY
            return response(row,self.now)
        self.boundary.request.side_effect=late
        self.assertEqual(self.session.tick(),'FAILED_CLOSED')

    def test_runtime_failure_before_dispatch(self):
        self.arm();self.now=OPEN;self.verify.side_effect=ValueError('mismatch')
        self.assertEqual(self.session.tick(),'FAILED_CLOSED');self.boundary.request.assert_not_called()

    def test_clock_rollback_fails_closed(self):
        self.arm();self.now-=timedelta(seconds=1)
        with self.assertRaises(ValueError):self.session.tick()
        self.boundary.request.assert_not_called()

    def test_journal_wrong_parent_rejected(self):
        self.arm();path=self.root/'receipts/000000.json'
        event=json.loads(path.read_text());event.pop('sha256');event['parent']='b'*64;event['sha256']=digest(event)
        path.write_bytes(canonical(event))  # Adversarial synthetic tampering only.
        with self.assertRaises(ValueError):self.session.tick()

    def test_disarm_and_expiry_no_more_requests(self):
        self.arm();self.journal.disarm(self.now);self.now=OPEN
        self.assertEqual(self.session.tick(),'CLOSED');self.boundary.request.assert_not_called()

    def test_exclusive_evidence_never_overwritten(self):
        p=self.root/'raw/test.json';exclusive(p,b'first')
        with self.assertRaises(FileExistsError):exclusive(p,b'second')
        self.assertEqual(p.read_bytes(),b'first')

    def test_symlink_and_hardlink_lock_rejected(self):
        p=self.root/'state/session.lock';target=self.root/'raw/other';target.write_bytes(b'')
        os.chmod(target,0o600);os.link(target,p)
        with self.assertRaises(ValueError):
            with self.journal.lock():pass

    def test_raw_evidence_substitution_rejected(self):
        self.arm();self.now=OPEN;self.session.tick()
        path=next((self.root/'raw').iterdir());path.write_bytes(b'tampered synthetic evidence')
        with self.assertRaises(ValueError):self.session.tick()
        self.assertEqual(self.boundary.request.call_count,1)

    def test_pre_request_runtime_and_disarm_gate(self):
        self.arm();self.now=OPEN
        calls=[0]
        def revoke():
            calls[0]+=1
            if calls[0]==2:self.journal.disarm(self.now)
        self.verify.side_effect=revoke
        self.assertEqual(self.session.tick(),'FAILED_CLOSED')
        self.boundary.request.assert_not_called()

    def test_account_credential_substitution_rejected(self):
        account=self.account|{'credential_binding':'other credential'}
        with self.assertRaises(ValueError):validate_account(account,digest(account),self.now)

    def test_snapshot_stale_cannot_prove_complete(self):
        row=request_plan()[0];r=response(row,OPEN-timedelta(hours=1))
        self.assertEqual(observation(row,r,OPEN)['classification'],'STALE')

    def test_conflicting_history_envelope_and_non_utc_snapshot_rejected(self):
        row=request_plan()[10];payload=json.loads(response(row,OPEN)[2]);payload['ticker']='SPY'
        payload['prices'][0]['ticker']='MU'
        with self.assertRaises(ValueError):observation(row,(200,'application/json',canonical(payload)),OPEN)
        row=request_plan()[0];payload=json.loads(response(row,OPEN)[2]);payload['snapshot']['time']='2026-09-11T06:30:00-07:00'
        with self.assertRaises(ValueError):observation(row,(200,'application/json',canonical(payload)),OPEN)

    def test_history_remains_historical(self):
        row=request_plan()[10];details=observation(row,response(row,OPEN),OPEN)
        self.assertEqual(details['provider_timestamp'],'2026-09-10')
        self.assertEqual(details['classification'],'HISTORICAL_EOD_NOT_CURRENT_SNAPSHOT')

    def test_error_wrong_ticker_nan_pagination_rejected(self):
        row=request_plan()[0]
        for value in [{'error':'SECRET'}, {'snapshot':{'ticker':'BAD','time':OPEN.isoformat(),'price':1}},
                      {'snapshot':{'ticker':'MU','time':OPEN.isoformat(),'price':float('nan')}},
                      {'next_page_url':'https://other.example'}]:
            with self.subTest(value=value),self.assertRaises((ValueError,KeyError)):
                observation(row,(200,'application/json',json.dumps(value).encode()),OPEN)

    def test_supervisor_stops_without_external_service_actions(self):
        self.arm();result=supervise(self.session,stop_requested=lambda:True,sleep=Mock())
        self.assertEqual(result,'STOPPED');self.assertTrue(self.journal.disarmed())

    def test_deferred_boundary_not_constructed_until_request(self):
        factory=Mock();boundary=DeferredBoundary(factory);factory.assert_not_called()
        boundary.request(request_plan()[0],OPEN);factory.assert_called_once()
