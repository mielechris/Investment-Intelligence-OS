from __future__ import annotations
import unittest
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .operational_market_executor import ExecutorStore,session_time_state
from .operational_market_executor_installer import RECOVERY_GENERATION_NAME,SELECTOR_NAME,SESSIONS_NAME,recover_time_failed_september_9_generation,resolve_selected_state_root
from .test_superbatch28_owner_authorization import OwnerAuthorizationTests

class Superbatch30TimeTests(unittest.TestCase):
    def test_bounded_wait_and_active_boundaries(self):
        auth='2026-09-09T06:16:48+00:00'; z=ZoneInfo('America/Los_Angeles')
        cases={
            datetime(2026,9,8,23,16,47,tzinfo=z):'INVALID_SESSION_TIME',
            datetime(2026,9,8,23,16,48,tzinfo=z):'PRE_SESSION_BOUNDED_WAIT',
            datetime(2026,9,8,23,59,59,tzinfo=z):'PRE_SESSION_BOUNDED_WAIT',
            datetime(2026,9,9,0,0,0,tzinfo=z):'PRE_SESSION_BOUNDED_WAIT',
            datetime(2026,9,9,6,29,59,tzinfo=z):'PRE_SESSION_BOUNDED_WAIT',
            datetime(2026,9,9,6,30,0,tzinfo=z):'ACTIVE_SESSION_DATE',
            datetime(2026,9,9,13,4,59,tzinfo=z):'ACTIVE_SESSION_DATE',
            datetime(2026,9,9,13,5,0,tzinfo=z):'POST_SESSION_EXPIRED',
            datetime(2026,9,9,13,5,1,tzinfo=z):'POST_SESSION_EXPIRED'}
        for moment,expected in cases.items(): self.assertEqual(session_time_state('2026-09-09',auth,moment),expected)
    def test_wrong_prior_date_and_naive_fail(self):
        self.assertEqual(session_time_state('2026-09-09','2026-09-07T06:00:00+00:00',datetime.now(timezone.utc)),'INVALID_SESSION_TIME')
        self.assertEqual(session_time_state('2026-09-09','2026-09-09T06:00:00+00:00',datetime(2026,9,9)),'INVALID_SESSION_TIME')
    def test_dst_uses_los_angeles_civil_time(self):
        z=ZoneInfo('America/Los_Angeles')
        self.assertEqual(session_time_state('2026-11-02','2026-11-02T05:30:00+00:00',datetime(2026,11,2,6,29,59,tzinfo=z)),'PRE_SESSION_BOUNDED_WAIT')

class Superbatch30RecoveryTests(OwnerAuthorizationTests):
    @staticmethod
    def _coordinator(selected:Path):
        from .operational_market_executor import OperationalMarketEvidenceCoordinator
        from .test_operational_market_executor import Boundary
        store=ExecutorStore(selected)
        return OperationalMarketEvidenceCoordinator(store,store.read_plan(),Boundary())
    def _failed_generation(self):
        ready,selected=self._ready_selected(); now=datetime(2026,9,9,4,tzinfo=timezone.utc)
        self._auth(root=self.root,readiness_root=ready,expected_commit='a'*40,now=now)
        # Reconstruct the persisted result produced by the pre-repair scheduler.
        self._coordinator(selected).close('SESSION_TIME_INVALID')
        return selected
    def test_preserves_failed_generation_and_selects_locked_successor(self):
        failed=self._failed_generation(); before={str(p.relative_to(failed)):p.read_bytes() for p in failed.rglob('*') if p.is_file()}
        self.assertEqual(recover_time_failed_september_9_generation(self.root),'SEPTEMBER_9_TIME_FAILURE_RECOVERED_LOCKED')
        self.assertEqual(before,{str(p.relative_to(failed)):p.read_bytes() for p in failed.rglob('*') if p.is_file()})
        successor=self.root/SESSIONS_NAME/RECOVERY_GENERATION_NAME
        self.assertEqual(resolve_selected_state_root(self.root),successor)
        state=ExecutorStore(successor).read()
        self.assertEqual((state['released_credits'],state['dispatched'],state['keychain_accesses']),(0,0,0))
        self.assertEqual((state['stage_a'],state['stage_b'],state['stage_c']),('LOCKED','LOCKED','LOCKED'))
    def test_post_selection_failure_restores_failed_selector(self):
        failed=self._failed_generation(); selector=self.root/SELECTOR_NAME; original=selector.read_bytes()
        with self.assertRaisesRegex(ValueError,'POST_SELECTION'):
            recover_time_failed_september_9_generation(self.root,post_select_validator=lambda _root:(_ for _ in ()).throw(ValueError('POST_SELECTION')))
        self.assertEqual(selector.read_bytes(),original)
        self.assertEqual(resolve_selected_state_root(self.root),failed)
    def test_interrupted_selection_is_restart_safe(self):
        failed=self._failed_generation(); selector=self.root/SELECTOR_NAME; original=selector.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_BEFORE'):
            recover_time_failed_september_9_generation(self.root,interrupt_after='before_selection')
        self.assertEqual(selector.read_bytes(),original)
        with self.assertRaisesRegex(SystemExit,'INTERRUPTED_AFTER'):
            recover_time_failed_september_9_generation(self.root,interrupt_after='after_selection')
        self.assertEqual(recover_time_failed_september_9_generation(self.root),'SEPTEMBER_9_TIME_FAILURE_ALREADY_RECOVERED_LOCKED')

if __name__=='__main__': unittest.main()
