"""Bounded historical mode; no installation, service or provider activity."""
from datetime import datetime, timedelta, timezone
import unittest
import copy
import hashlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from truth_spine_contract import digest, seal
from truth_spine_session import (HistoricalSession, Lifecycle, Phase, exchange_session,
    parse_session, session_authority, validate_session_authority)


class HistoricalContractTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 9, 10, 23, 0, tzinfo=timezone.utc)
        self.s = HistoricalSession(self.at, 600)
        self.owners = {'scheduler': 'historical-scheduler', 'publisher': 'historical-publisher'}

    def test_roundtrip_deterministic_and_not_exchange_identity(self):
        self.assertEqual(parse_session(self.s.record()), self.s)
        self.assertEqual(HistoricalSession(self.at, 600).identity, self.s.identity)
        self.assertNotEqual(exchange_session('2026-09-10').identity, self.s.identity)
        self.assertFalse(self.s.record()['market_calendar_authority'])

    def test_duration_and_timezone_are_strict(self):
        for duration in (True, 0, 299, 3601, 600.0):
            with self.assertRaises(ValueError): HistoricalSession(self.at, duration)
        with self.assertRaises(ValueError): HistoricalSession(self.at.replace(tzinfo=None), 600)
        with self.assertRaises(ValueError): HistoricalSession(self.at, 600, 'NORMAL')

    def test_resealed_scope_and_expiration_cannot_change(self):
        for key, value in [('scope', 'FULL_MARKET_DAY'), ('market_calendar_authority', True),
                           ('shutdown_end', (self.at+timedelta(days=1)).isoformat())]:
            bad = self.s.record(); bad[key] = value
            with self.assertRaises(ValueError): parse_session(seal(bad))

    def test_authority_current_wall_clock_and_no_expansion(self):
        a = session_authority(self.s, 'historical-release', self.owners, self.at)
        validate_session_authority(a, self.s, 'historical-release', self.owners, digest(a), self.at)
        self.assertTrue(all(v is False for v in a['capabilities'].values()))
        for at in (self.at-timedelta(seconds=1), self.s.shutdown_end):
            with self.assertRaises(PermissionError):
                validate_session_authority(a, self.s, 'historical-release', self.owners, digest(a), at)
        bad = dict(a); bad['capabilities'] = {**a['capabilities'], 'provider_requests': True}; bad = seal(bad)
        with self.assertRaises(PermissionError):
            validate_session_authority(bad, self.s, 'historical-release', self.owners, digest(bad), self.at)

    def test_no_opening_intraday_or_market_closing_fabricated(self):
        life = Lifecycle(self.s)
        life.tick(self.at, authority_current=True)
        self.assertEqual(life.state['phase'], Phase.POST_CLOSE_RECONCILIATION)
        self.assertEqual(life.state['missed_phases'], [])
        self.assertEqual(life.state['incidents'], ['HISTORICAL_REPLAY_NOT_FULL_MARKET_DAY'])
        life.captured(self.at, 'historical-generation')
        life.reconciled()
        life.tick(self.s.reconcile_end, authority_current=True)
        self.assertEqual(life.state['phase'], Phase.SESSION_COMPLETE)
        life.shutdown(unresolved=False, listener_clear=True)
        self.assertEqual(life.state['session_result'], 'COMPLETE')

    def test_restart_preserves_disabled_historical_identity(self):
        life = Lifecycle(self.s); life.tick(self.at, authority_current=True)
        life.reserve_restart('publisher', self.at, authority_current=True)
        recovered = Lifecycle(parse_session(self.s.record()), life.state)
        self.assertEqual(recovered.state, life.state)
        recovered.reserve_restart('publisher', self.at+timedelta(seconds=60), authority_current=True)
        self.assertEqual(recovered.state['phase'], Phase.FAILED_CLOSED)
        self.assertIn('RESTART_BUDGET_EXHAUSTED', recovered.state['incidents'])

    def test_original_market_calendar_and_24_hour_boundary_unchanged(self):
        s = exchange_session('2026-09-11')
        self.assertEqual(parse_session(s.record()), s)
        self.assertEqual(s.phase_at(s.open_at), Phase.OPENING_OBSERVATION)
        with self.assertRaises(ValueError):
            session_authority(s, 'r', self.owners, s.shutdown_end-timedelta(hours=24, seconds=1))


class HistoricalPackageTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
        self.addCleanup(sys.path.pop,0)
        import truth_spine_historical_package as p
        self.p=p
        self.files={'release/backend/'+n:(b'# offline test\n',0o400) for n in p.BACKEND_FILES}
        self.files['runtime/bin/python']=(b'unit-only-not-executable',0o500)
        self.c={'source_commit':'a'*40,'inputs':[],'dependency_lock_sha256':'b'*64,
                'files':[{'path':n,'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest(),'mode':f'{m:04o}'}
                         for n,(d,m) in sorted(self.files.items())]}
        self.reseal()

    def reseal(self):
        self.c['identity']=digest({'source':self.c['source_commit'],'files':self.c['files'],
                                 'inputs':self.c['inputs'],'lock':self.c['dependency_lock_sha256']})
        self.c['release']='northstar-historical-'+self.c['identity'][:16]

    def test_exact_candidate_and_deterministic_identity(self):
        before=copy.deepcopy(self.c);self.p.validate_payload(self.c,self.files)
        self.reseal();self.assertEqual(self.c,before)

    def test_changed_byte_missing_extra_and_bad_mode_rejected(self):
        first=next(iter(self.files))
        for action in ('byte','missing','extra','mode'):
            files=copy.deepcopy(self.files)
            if action=='byte':files[first]=(b'changed',0o400)
            elif action=='missing':files.pop(first)
            elif action=='extra':files['release/backend/extra.py']=(b'extra',0o400)
            else:files[first]=(files[first][0],0o600)
            with self.assertRaises(ValueError):self.p.validate_payload(self.c,files)

    def test_path_escape_cache_and_unknown_backend_rejected_even_resealed(self):
        for name in ('../escape','/absolute','release/backend/../escape','runtime/__pycache__/x.pyc','release/backend/extra.py'):
            files=copy.deepcopy(self.files);files[name]=(b'bad',0o400)
            old=copy.deepcopy(self.c)
            self.c['files'].append({'path':name,'bytes':3,'sha256':hashlib.sha256(b'bad').hexdigest(),'mode':'0400'});self.reseal()
            with self.assertRaises(ValueError):self.p.validate_payload(self.c,files)
            self.c=old

    def test_invalid_duration_and_identity_before_any_creation(self):
        root=Path('/private/tmp')/self.p.ROOT_NAME
        with patch.object(Path,'mkdir',side_effect=AssertionError('MUTATION')):
            with self.assertRaisesRegex(ValueError,'HISTORICAL_DURATION_INVALID'):
                self.p.install(root,self.c,self.files,{},duration=3601)
            self.c['identity']='c'*64
            with self.assertRaisesRegex(ValueError,'CANDIDATE_IDENTITY_MISMATCH'):
                self.p.install(root,self.c,self.files,{},duration=600)

    def test_authorized_build_roots_only_before_source_read_or_creation(self):
        from truth_spine_frontend_provenance import build
        import truth_spine_frontend_provenance as p
        with patch.object(p,'inputs',side_effect=ValueError('PRECREATION_SOURCE_CHECK')):
            # Retained E.2 roots are evidence and must not be removed merely to
            # exercise this precreation guard. Use a fresh authorized-prefix
            # root for the same validation contract.
            root = Path('/private/tmp') / f'iios-frontend-build-precreation-{os.getpid()}'
            with self.assertRaisesRegex(ValueError,'PRECREATION_SOURCE_CHECK'):
                build(Path('/unit/source'), root, 'a'*40, northstar=True)
            with self.assertRaisesRegex(ValueError,'NEW_ISOLATED_BUILD_ROOT_REQUIRED'):
                build(Path('/unit/source'),Path('/private/tmp/iios-northstar-sb37-build-c'),'a'*40,northstar=True)


class HistoricalOwnershipTests(unittest.TestCase):
    def test_receipt_requires_lease_then_bind_and_cleanup_is_independent(self):
        import truth_spine_full_day_service as service
        root=Path('/private/tmp/unit-historical-process')
        args=SimpleNamespace(config=root/'topology.json',role='backend',port=5291,
                             instance_id='unit',runner_id='owner',created_at='2026-09-10T23:00:00+00:00')
        for fails in (False,True):
            events=[]
            class Lease:
                def __init__(self,*_):events.append('LEASE')
                def close(self):events.append('CLOSED')
            def server(_path,_port,on_bound):
                if fails:raise OSError('unit bind failure')
                events.append('BOUND');on_bound()
            with patch.object(service.argparse.ArgumentParser,'parse_args',return_value=args), \
                 patch.object(service,'load_config',return_value=({},None,{},None,{})), \
                 patch.object(service,'__file__',str(root/'release/backend/service.py')), \
                 patch.object(service.sys,'executable',str(root/'runtime/bin/python')), \
                 patch.object(service,'Lease',Lease),patch.object(service,'serve',server), \
                 patch.object(service,'deny_external_io',side_effect=lambda:events.append('DENY')), \
                 patch('truth_spine_process_identity.write_startup',side_effect=lambda *_:events.append('RECEIPT')):
                if fails:
                    with self.assertRaises(OSError):service.main()
                    self.assertEqual(events,['LEASE','CLOSED'])
                else:
                    service.main();self.assertEqual(events,['LEASE','BOUND','RECEIPT','DENY','CLOSED'])


if __name__ == '__main__': unittest.main()
