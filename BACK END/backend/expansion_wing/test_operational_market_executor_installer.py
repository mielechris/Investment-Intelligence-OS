from __future__ import annotations
import hashlib, json, os, tempfile, unittest
from pathlib import Path
from .operational_market_executor import (CANARY_PLAN, POST_0930_PLAN, ExecutorStore,
    _digest, canary_plan, plan_identity, post_0930_plan,
    september_9_plan)
from .operational_market_executor_installer import *
from .september_9_canonical_plan import obsolete_c40_plan

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/"source"; base=self.source/"BACK END/backend/expansion_wing"; base.mkdir(parents=True)
        for name in ARTIFACTS: (base/name).write_text(name+"\n")
        self.root=Path(self.temp.name)/"install"; self.rollback=Path(self.temp.name)/"rollback"
    def test_manifest_is_fixed_and_disabled(self):
        value=render_manifest(self.source,"a"*40); self.assertEqual(validate_manifest(value,self.source),value)
        self.assertFalse(value["network_enabled"]); self.assertEqual(value["plan"]["requests"],1)
        self.assertEqual(value["credential_selector"]["service"],"com.iios.expansion-wing.financial-datasets")
    def test_install_and_absence_rollback(self):
        self.assertEqual(install_disabled(self.source,"a"*40,self.root,self.rollback,observed_commit="a"*40),"EXECUTOR_INSTALLED_DISABLED")
        self.assertEqual(validate_installed(self.root)["plan"]["classification"],CANARY_PLAN)
        self.assertEqual(ExecutorStore(self.root/"state").read_plan(),canary_plan())
        projection=browser_projection(self.root); self.assertEqual((projection["phase"],projection["installed"],projection["released_credits"]),("CANARY_READY",True,0))
        self.assertNotIn("requests",projection); self.assertFalse(any(projection["authority"].values()))
        for path in self.root.rglob("*"):
            self.assertFalse(path.is_symlink()); self.assertEqual(path.stat().st_mode&0o777,0o700 if path.is_dir() else 0o600)
        self.assertEqual(rollback_install(self.root,self.rollback),"EXECUTOR_INSTALLATION_ABSENT_RESTORED"); self.assertFalse(self.root.exists())
    def test_tamper_and_unknown_inventory_fail_closed(self):
        install_disabled(self.source,"a"*40,self.root,self.rollback,observed_commit="a"*40); (self.root/"unknown").write_text("x")
        with self.assertRaisesRegex(ValueError,"INSTALL_INVENTORY_INVALID"): validate_installed(self.root)
        self.assertEqual(browser_projection(self.root)["phase"],"UNAVAILABLE")
    def test_absent_projection_is_not_installed(self):
        value=browser_projection(self.root); self.assertEqual((value["phase"],value["installed"]),("NOT_INSTALLED",False))
    def test_upgrade_preserves_state_and_is_rollback_backed(self):
        install_disabled(self.source,"a"*40,self.root,self.rollback,observed_commit="a"*40)
        before=(self.root/"state"/"executor-state.json").read_bytes(); upgrade_rollback=Path(self.temp.name)/"upgrade-rollback"
        base=self.source/"BACK END/backend/expansion_wing"; (base/ARTIFACTS[0]).write_text("changed\n")
        self.assertEqual(upgrade_disabled(self.source,"b"*40,self.root,upgrade_rollback,observed_commit="b"*40),"EXECUTOR_UPGRADED_DISABLED")
        self.assertEqual(validate_installed(self.root)["installed_source_commit"],"b"*40)
        self.assertEqual(before,(self.root/"state"/"executor-state.json").read_bytes()); self.assertTrue((upgrade_rollback/"installation-manifest.json").is_file())

    def closed_september_8(self):
        install_disabled(self.source,"a"*40,self.root,self.rollback,observed_commit="a"*40)
        store=ExecutorStore(self.root/"state"); rows=post_0930_plan(); store.write_plan(rows,POST_0930_PLAN)
        state=store.read(); state.update({"classification":POST_0930_PLAN,"plan_identity":plan_identity(rows),
            "planned":len(rows),"requests":{r["identity"]:{"lifecycle":"CONFIRMED","cost":1} for r in rows},
            "dispatched":len(rows),"completed":len(rows),"failed":0,"ambiguous":0,
            "confirmed_credits":len(rows),"ambiguous_credits":0,"released_credits":0,
            "stage_a":"LOCKED","stage_b":"LOCKED","stage_c":"LOCKED","phase":"SESSION_CLOSED","next_gate":"NONE"})
        state["content_hash"]=_digest(state)
        store.write(state); return store

    def test_transition_requires_complete_locked_zero_allowance_terminal_state(self):
        cases=(("phase","STAGE_A_RUNNING"),("released_credits",1),("stage_a","RUNNING"))
        for index,(key,value) in enumerate(cases):
            with self.subTest(key=key):
                root=Path(self.temp.name)/f"install-{index}"; rollback=Path(self.temp.name)/f"rollback-{index}"
                prior_root,prior_rollback=self.root,self.rollback; self.root,self.rollback=root,rollback
                store=self.closed_september_8(); state=store.read(); state[key]=value
                state["content_hash"]=_digest(state); store.write(state)
                with self.assertRaisesRegex(ValueError,"SEPTEMBER_8_NOT_TERMINAL"): prepare_september_9_generation(root)
                self.root,self.rollback=prior_root,prior_rollback
        root=Path(self.temp.name)/"install-incomplete"; rollback=Path(self.temp.name)/"rollback-incomplete"
        self.root,self.rollback=root,rollback; store=self.closed_september_8(); state=store.read(); identity=next(iter(state["requests"])); state["requests"][identity]["lifecycle"]="PLANNED"; state["completed"]-=1; state["dispatched"]-=1; state["confirmed_credits"]-=1
        state["content_hash"]=_digest(state); store.write(state)
        with self.assertRaisesRegex(ValueError,"SEPTEMBER_8_NOT_TERMINAL"): prepare_september_9_generation(root)

    def test_transition_archives_bytes_and_selects_new_locked_generation(self):
        store=self.closed_september_8(); source={str(p.relative_to(store.root)):p.read_bytes() for p in store.root.rglob('*') if p.is_file() and p.name!='executor.lock'}
        self.assertEqual(prepare_september_9_generation(self.root),"SEPTEMBER_9_GENERATION_SELECTED_LOCKED")
        selected=resolve_selected_state_root(self.root); self.assertEqual(selected,self.root/SESSIONS_NAME/"2026-09-09")
        new=ExecutorStore(selected); self.assertEqual(new.read_plan(),obsolete_c40_plan())
        state=new.read(); self.assertEqual((state['released_credits'],state['stage_a'],state['stage_b'],state['stage_c']),(0,'LOCKED','LOCKED','LOCKED'))
        archive=self.root/SESSIONS_NAME/"2026-09-08"
        for relative,payload in source.items(): self.assertEqual((archive/relative).read_bytes(),payload)
        self.assertEqual(source,{str(p.relative_to(store.root)):p.read_bytes() for p in store.root.rglob('*') if p.is_file() and p.name!='executor.lock'})

    def test_interrupted_archive_and_selection_recover_fail_closed(self):
        self.closed_september_8()
        with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_ARCHIVAL'): prepare_september_9_generation(self.root,interrupt_after='archive')
        self.assertEqual(recover_session_transition(self.root),'SEPTEMBER_8_REMAINS_SELECTED')
        self.assertEqual(resolve_selected_state_root(self.root),self.root/'state')
        with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_SELECTION'): prepare_september_9_generation(self.root,interrupt_after='selection')
        self.assertEqual(recover_session_transition(self.root),'SESSION_SELECTION_RECOVERED')

    def test_interrupted_selection_corrupt_pointer_archive_and_mixed_session_rejected(self):
        self.closed_september_8()
        with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_SELECTION'): prepare_september_9_generation(self.root,interrupt_after='selection')
        self.assertEqual(recover_session_transition(self.root),'SESSION_SELECTION_RECOVERED')
        selector=self.root/SELECTOR_NAME; original=selector.read_bytes(); selector.write_text('{}'); selector.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'SESSION_SELECTOR_INVALID'): resolve_selected_state_root(self.root)
        selector.write_bytes(original); selector.chmod(0o600)
        archive_file=next(p for p in (self.root/SESSIONS_NAME/'2026-09-08').rglob('*') if p.is_file() and p.name!='archive-manifest.json'); archive_file.write_bytes(archive_file.read_bytes()+b'x'); archive_file.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'SESSION_ARCHIVE_HASH_MISMATCH'): resolve_selected_state_root(self.root)

    def test_interrupted_generation_and_stale_pointer_fail_closed(self):
        self.closed_september_8()
        with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_GENERATION'): prepare_september_9_generation(self.root,interrupt_after='generation')
        self.assertEqual(recover_session_transition(self.root),'SEPTEMBER_8_REMAINS_SELECTED')
        self.assertEqual(prepare_september_9_generation(self.root),'SEPTEMBER_9_GENERATION_SELECTED_LOCKED')
        self.assertEqual(recover_session_transition(self.root),'SESSION_SELECTION_VALID')
        selector=self.root/SELECTOR_NAME; value=json.loads(selector.read_text()); value['selected_session']='2026-09-08'; value['content_hash']=''
        value['content_hash']=hashlib.sha256((json.dumps({k:v for k,v in value.items() if k!='content_hash'},sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
        selector.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n'); selector.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'SESSION_SELECTOR_INVALID'): resolve_selected_state_root(self.root)

    def test_mixed_selected_session_artifact_is_rejected(self):
        self.closed_september_8(); prepare_september_9_generation(self.root); selected=resolve_selected_state_root(self.root)
        bogus=selected/'receipts'/('market-evidence-'+'0'*64+'.json'); bogus.write_text('{}'); bogus.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'SUPERSESSION_SAFETY_GATE_FAILED'): resolve_selected_state_root(self.root)

if __name__=="__main__": unittest.main()
