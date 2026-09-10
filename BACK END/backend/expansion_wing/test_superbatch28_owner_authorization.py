from __future__ import annotations
import json
from unittest.mock import patch
from datetime import datetime,timezone
from pathlib import Path
from .operational_market_executor import ExecutorStore,_digest
from .operational_market_executor_installer import AUTHORIZATION_NAME,SESSIONS_NAME,authorize_september_9_market_open_50,reselect_corrected_september_9_generation
from .test_superbatch28_canonical_recovery import CanonicalRecoveryTests

class OwnerAuthorizationTests(CanonicalRecoveryTests):
    def setUp(self):
        super().setUp(); self.supervisor=self.base/'supervisor'; self.supervisor.mkdir(); self.manifest_identity='f'*64
        (self.supervisor/'installation-manifest.json').write_text(json.dumps({'canonical_manifest_content_hash':self.manifest_identity})+'\n')
        self.validator=patch('expansion_wing.unattended_supervisor_installer.validate_installed_root',return_value='INSTALLED_VALID'); self.validator.start(); self.addCleanup(self.validator.stop)
    def _auth(self,**kwargs):
        return authorize_september_9_market_open_50(supervisor_root=self.supervisor,supervisor_manifest_identity=self.manifest_identity,
            service_probe=lambda:{'running':True,'supervisor_count':1,'lock_owned':True,'listeners':0,'children':0},**kwargs)
    def _ready_selected(self):
        self._closed_and_incident_selected(); ready=self._readiness(); self._reselect(self.root,readiness_root=ready)
        return ready,self.root/SESSIONS_NAME/'2026-09-09-canonical-v2'
    def test_authorizes_once_without_dispatch(self):
        ready,selected=self._ready_selected(); now=datetime(2026,9,9,4,tzinfo=timezone.utc)
        self.assertEqual(self._auth(root=self.root,readiness_root=ready,expected_commit='a'*40,now=now),'SEPTEMBER_9_MARKET_OPEN_50_AUTHORIZED')
        state=ExecutorStore(selected).read(); self.assertEqual((state['released_credits'],state['stage_a'],state['dispatched'],state['keychain_accesses']),(50,'RUNNING',0,0)); self.assertEqual((state['stage_b'],state['stage_c']),('LOCKED','LOCKED'))
        self.assertFalse(json.loads((selected/AUTHORIZATION_NAME).read_text())['direct_dispatch'])
        self.assertEqual(self._auth(root=self.root,readiness_root=ready,expected_commit='a'*40,now=now),'SEPTEMBER_9_MARKET_OPEN_50_ALREADY_AUTHORIZED')
    def test_clock_boundaries_fail_closed(self):
        for now in (datetime(2026,9,7,23,59,tzinfo=timezone.utc),datetime(2026,9,9,14,tzinfo=timezone.utc)):
            with self.subTest(now=now):
                self.base=Path(self.temp.name).resolve()/str(now.timestamp()); self.base.mkdir(); self.root=self.base/'executor'; self.rollback=self.base/'rollback'; ready,_=self._ready_selected()
                with self.assertRaisesRegex(ValueError,'MARKET_OPEN_AUTHORIZATION_WINDOW_CLOSED'): self._auth(root=self.root,readiness_root=ready,expected_commit='a'*40,now=now)
    def test_prior_activity_rejected_and_postcheck_rolls_back(self):
        ready,selected=self._ready_selected(); store=ExecutorStore(selected); state=store.read(); state['released_credits']=1; state['content_hash']=''; state['content_hash']=_digest(state); store.write(state)
        with self.assertRaisesRegex(ValueError,'AUTHORIZATION_PRISTINE_STATE_REQUIRED'): self._auth(root=self.root,readiness_root=ready,expected_commit='a'*40,now=datetime(2026,9,9,4,tzinfo=timezone.utc))
        state['released_credits']=0; state['content_hash']=''; state['content_hash']=_digest(state); store.write(state); before=store.state_path.read_bytes()
        with self.assertRaisesRegex(ValueError,'POST'): self._auth(root=self.root,readiness_root=ready,expected_commit='a'*40,now=datetime(2026,9,9,4,tzinfo=timezone.utc),post_authorization_validator=lambda _r:(_ for _ in ()).throw(ValueError('POST')))
        self.assertEqual(store.state_path.read_bytes(),before); self.assertFalse((selected/AUTHORIZATION_NAME).exists())

if __name__=='__main__': unittest.main()
