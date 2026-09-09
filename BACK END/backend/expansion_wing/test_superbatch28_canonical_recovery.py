from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .operational_market_executor import (ExecutorStore, FinancialDatasetsOperationalBoundary,
    POST_0930_PLAN, _digest, plan_identity, post_0930_plan, september_9_plan)
from .operational_market_executor_installer import (ARTIFACTS, SELECTOR_NAME, SESSIONS_NAME,
    SUPERSESSION_NAME, CORRECTED_GENERATION_NAME, install_disabled, prepare_september_9_generation,
    reselect_corrected_september_9_generation, resolve_selected_state_root)
from .provider_readiness import (COST_CONTRACT_NAME, SEPTEMBER_9_COST_SCHEMA, _hash,
    installed_readiness_projection, september_9_cost_evidence_document, september_9_plan_identity)
from .provider_readiness_service import (install_cost_contract, probe_credential_once,
    refresh_september_9_cost_contract)
from .september_9_canonical_plan import (OBSOLETE_EXECUTOR_IDENTITY, OBSOLETE_READINESS_IDENTITY,
    PROVIDER, PROVIDER_CONTRACT, canonical_plan_identity, corrected_september_9_plan,
    mutated_identity, obsolete_c40_plan, validate_canonical_plan)


class Probe:
    def exists(self, **_kwargs): return True


class Credentials:
    class Adapter: service=b"com.iios.expansion-wing.financial-datasets"
    adapter=Adapter()
    def retrieve(self): return b"test-only"


class Transport:
    def __init__(self): self.kwargs=None
    def trust_readiness(self): return "READY"
    def operational_request(self, **kwargs): self.kwargs=kwargs; return 200,"application/json",b'{}',1.0


class CanonicalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.source=self.base/"source"
        artifacts=self.source/"BACK END/backend/expansion_wing"; artifacts.mkdir(parents=True)
        for name in ARTIFACTS: (artifacts/name).write_text(name+"\n")
        self.root=self.base/"executor"; self.rollback=self.base/"install-rollback"

    def _closed_and_incident_selected(self):
        install_disabled(self.source,"a"*40,self.root,self.rollback,observed_commit="a"*40)
        store=ExecutorStore(self.root/"state"); rows=post_0930_plan(); store.write_plan(rows,POST_0930_PLAN)
        state=store.read(); state.update({"classification":POST_0930_PLAN,"plan_identity":plan_identity(rows),
            "planned":20,"requests":{r["identity"]:{"lifecycle":"CONFIRMED","cost":1} for r in rows},
            "dispatched":20,"completed":20,"failed":0,"ambiguous":0,"confirmed_credits":20,
            "ambiguous_credits":0,"released_credits":0,"stage_a":"LOCKED","stage_b":"LOCKED",
            "stage_c":"LOCKED","phase":"SESSION_CLOSED","next_gate":"NONE"})
        state["content_hash"]=_digest(state); store.write(state)
        self.assertEqual(prepare_september_9_generation(self.root),"SEPTEMBER_9_GENERATION_SELECTED_LOCKED")
        return self.root/SESSIONS_NAME/"2026-09-09"

    def _readiness(self):
        root=self.base/"readiness"; install_cost_contract(root=root)
        probe_credential_once(root=root,runner=Probe(),clock=lambda:datetime(2026,9,9,12,tzinfo=timezone.utc))
        doc=september_9_cost_evidence_document(observed_at="2026-09-09T02:00:00+00:00",
            expires_at="2026-09-09T20:05:00+00:00",observation_identity="financial-datasets-pricing-2026-09-09-canonical-v2")
        refresh_september_9_cost_contract(document=doc,root=root,rollback=self.base/"pricing-rollback",
            now=datetime(2026,9,9,3,tzinfo=timezone.utc))
        return root

    def test_exact_plan_composition_windows_dates_and_provider_binding(self):
        rows=validate_canonical_plan(corrected_september_9_plan())
        self.assertEqual((len(rows),len({r['identity'] for r in rows}),sum(r['cost'] for r in rows)),(50,50,50))
        self.assertEqual({r['ticker'] for r in rows},{'MU','SPY','XLK','VNQ','TLT','GLD','UUP','IBIT','PFF','BIL'})
        self.assertTrue(all((r['provider'],r['provider_contract'],r['retry'])==(PROVIDER,PROVIDER_CONTRACT,False) for r in rows))
        point=[r for r in rows if r['observation_type']=='POINT_IN_TIME_OHLCV']
        prior=[r for r in rows if r['observation_type']=='PRIOR_SESSION_BASELINE']
        facts=[r for r in rows if r['observation_type']=='APPLICABLE_FACTS']
        self.assertEqual((len(point),len(prior),len(facts)),(10,9,1))
        self.assertTrue(all((r['earliest'],r['latest'],r['start_date'],r['end_date'])==('06:30','09:30','2026-09-08','2026-09-09') for r in point))
        self.assertTrue(all((r['earliest'],r['latest'],r['start_date'],r['end_date'])==('06:30','09:30','2026-09-08','2026-09-08') for r in prior))
        self.assertEqual((facts[0]['endpoint'],facts[0]['start_date'],facts[0]['end_date']),('COMPANY_FACTS',None,None))

    def test_shared_identity_and_every_material_mutation_changes_it(self):
        identity=canonical_plan_identity(); self.assertEqual(identity,september_9_plan_identity())
        self.assertEqual(identity,plan_identity(september_9_plan()))
        self.assertNotIn(identity,{OBSOLETE_EXECUTOR_IDENTITY,OBSOLETE_READINESS_IDENTITY})
        samples={'provider':'OTHER','provider_contract':'v2','endpoint':'COMPANY_FACTS','ticker':'ZZZ',
            'observation_type':'OTHER','variant':'OTHER','window':'OTHER','start_date':'2026-09-07',
            'end_date':'2026-09-10','session_date':'2026-09-10','cost':2,'retry':True}
        for field,value in samples.items():
            with self.subTest(field=field): self.assertNotEqual(mutated_identity(0,field,value),identity)
        legacy_bytes=json.dumps(obsolete_c40_plan(),sort_keys=True,separators=(',',':')).encode()
        self.assertEqual(hashlib.sha256(legacy_bytes).hexdigest(),OBSOLETE_EXECUTOR_IDENTITY)
        self.assertNotEqual(identity,OBSOLETE_READINESS_IDENTITY)

    def test_transport_receives_historical_dates_and_rejects_dates_for_facts(self):
        transport=Transport(); boundary=FinancialDatasetsOperationalBoundary(Credentials(),transport)
        row=next(r for r in september_9_plan() if r['observation_type']=='POINT_IN_TIME_OHLCV')
        boundary.request(row)
        self.assertEqual((transport.kwargs['start_date'],transport.kwargs['end_date']),('2026-09-08','2026-09-09'))
        facts=next(r for r in september_9_plan() if r['observation_type']=='APPLICABLE_FACTS'); boundary.request(facts)
        self.assertEqual((transport.kwargs['start_date'],transport.kwargs['end_date']),(None,None))

    def test_obsolete_d082_pricing_is_preserved_but_ineligible_then_backed_up(self):
        root=self.base/'old-pricing'; install_cost_contract(root=root)
        probe_credential_once(root=root,runner=Probe(),clock=lambda:datetime(2026,9,9,2,tzinfo=timezone.utc))
        corrected=september_9_cost_evidence_document(observed_at='2026-09-09T02:00:00+00:00',
            expires_at='2026-09-09T20:05:00+00:00',observation_identity='financial-datasets-pricing-2026-09-09-canonical-v2')
        obsolete=dict(corrected); obsolete['schema']=SEPTEMBER_9_COST_SCHEMA; obsolete['request_plan_identity']=OBSOLETE_READINESS_IDENTITY
        obsolete.pop('document_hash'); obsolete['document_hash']=_hash(obsolete)
        old_bytes=(json.dumps(obsolete,sort_keys=True,separators=(',',':'))+'\n').encode()
        (root/COST_CONTRACT_NAME).write_bytes(old_bytes); (root/COST_CONTRACT_NAME).chmod(0o600)
        self.assertEqual(installed_readiness_projection(root=root,now=datetime(2026,9,9,3,tzinfo=timezone.utc))['provider_state'],'FAILED_CLOSED')
        rollback=self.base/'old-pricing-backup'
        refresh_september_9_cost_contract(document=corrected,root=root,rollback=rollback,now=datetime(2026,9,9,3,tzinfo=timezone.utc))
        self.assertEqual((rollback/'prior-provider-cost-contract.json').read_bytes(),old_bytes)
        self.assertEqual(installed_readiness_projection(root=root,now=datetime(2026,9,9,3,tzinfo=timezone.utc))['request_plan_identity'],canonical_plan_identity())

    def test_quarantine_and_atomic_corrected_reselection_preserve_incident(self):
        obsolete=self._closed_and_incident_selected(); before={str(p.relative_to(obsolete)):p.read_bytes() for p in obsolete.rglob('*') if p.is_file()}
        archive=self.root/SESSIONS_NAME/'2026-09-08'; archive_before={str(p.relative_to(archive)):p.read_bytes() for p in archive.rglob('*') if p.is_file()}
        self.assertEqual(reselect_corrected_september_9_generation(self.root,readiness_root=self._readiness()),"SEPTEMBER_9_CORRECTED_GENERATION_SELECTED_LOCKED")
        self.assertEqual(before,{str(p.relative_to(obsolete)):p.read_bytes() for p in obsolete.rglob('*') if p.is_file()})
        self.assertEqual(archive_before,{str(p.relative_to(archive)):p.read_bytes() for p in archive.rglob('*') if p.is_file()})
        self.assertTrue((self.root/'incidents'/SUPERSESSION_NAME).is_file())
        selected=resolve_selected_state_root(self.root); self.assertEqual(selected,self.root/SESSIONS_NAME/CORRECTED_GENERATION_NAME)
        state=ExecutorStore(selected).read(); self.assertEqual((state['plan_identity'],state['released_credits'],state['dispatched']),(canonical_plan_identity(),0,0))
        self.assertEqual((state['stage_a'],state['stage_b'],state['stage_c']),('LOCKED','LOCKED','LOCKED'))
        selector=json.loads((self.root/SELECTOR_NAME).read_text()); self.assertEqual(selector['plan_identity'],canonical_plan_identity())
        self.assertEqual(selector['supersession_receipt_hash'],json.loads((self.root/'incidents'/SUPERSESSION_NAME).read_text())['content_hash'])

    def test_reselection_refuses_any_activity_or_unlocked_state(self):
        for key,value in [('released_credits',1),('stage_a','RUNNING'),('dispatched',1),('confirmed_credits',1),('keychain_accesses',1)]:
            with self.subTest(key=key):
                self.base=Path(self.temp.name)/key; self.base.mkdir()
                self.root=self.base/'executor'; self.rollback=self.base/'install-rollback'
                obsolete=self._closed_and_incident_selected(); store=ExecutorStore(obsolete); state=store.read(); state[key]=value
                identity=next(iter(state['requests']))
                if key=='dispatched': state['requests'][identity]['lifecycle']='DISPATCH_STARTED'
                if key=='confirmed_credits':
                    state['requests'][identity]['lifecycle']='CONFIRMED'; state['dispatched']=1; state['completed']=1
                state['content_hash']=_digest(state); store.write(state)
                with self.assertRaisesRegex(ValueError,'SUPERSESSION_SAFETY_GATE_FAILED'):
                    reselect_corrected_september_9_generation(self.root,readiness_root=self._readiness())

    def test_reselection_refuses_receipt_and_evidence(self):
        for directory in ('receipts','evidence'):
            with self.subTest(directory=directory):
                self.base=Path(self.temp.name)/directory; self.base.mkdir()
                self.root=self.base/'executor'; self.rollback=self.base/'install-rollback'
                obsolete=self._closed_and_incident_selected(); artifact=obsolete/directory/'unexpected.json'
                artifact.write_text('{}\n'); artifact.chmod(0o600)
                with self.assertRaisesRegex(ValueError,'SUPERSESSION_SAFETY_GATE_FAILED'):
                    reselect_corrected_september_9_generation(self.root,readiness_root=self._readiness())

    def test_interruption_before_selection_retains_obsolete_selection(self):
        obsolete=self._closed_and_incident_selected(); ready=self._readiness()
        for phase in ('quarantine','generation','selection'):
            if phase!='quarantine':
                # Earlier durable products are valid and reused without mutation.
                pass
            with self.assertRaises(RuntimeError):
                reselect_corrected_september_9_generation(self.root,readiness_root=ready,interrupt_after=phase)
            self.assertEqual(resolve_selected_state_root(self.root),obsolete)

    def test_post_selection_failure_restores_obsolete_selector(self):
        obsolete=self._closed_and_incident_selected(); original=(self.root/SELECTOR_NAME).read_bytes()
        with self.assertRaisesRegex(ValueError,'POST_SELECT'):
            reselect_corrected_september_9_generation(self.root,readiness_root=self._readiness(),
                post_select_validator=lambda _root:(_ for _ in ()).throw(ValueError('POST_SELECT')))
        self.assertEqual((self.root/SELECTOR_NAME).read_bytes(),original)
        self.assertEqual(resolve_selected_state_root(self.root),obsolete)

    def test_corrupt_supersession_receipt_fails_closed(self):
        self._closed_and_incident_selected(); ready=self._readiness()
        with self.assertRaises(RuntimeError):
            reselect_corrected_september_9_generation(self.root,readiness_root=ready,interrupt_after='quarantine')
        receipt=self.root/'incidents'/SUPERSESSION_NAME; receipt.write_text('{}\n'); receipt.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'SUPERSESSION_RECEIPT_INVALID'):
            reselect_corrected_september_9_generation(self.root,readiness_root=ready)


if __name__ == '__main__': unittest.main()
