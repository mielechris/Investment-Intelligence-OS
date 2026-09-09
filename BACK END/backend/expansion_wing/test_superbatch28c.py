from __future__ import annotations
import json, plistlib, tempfile, threading, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .provider_readiness import (ENDPOINT_PATHS, MAX_COST_EVIDENCE_AGE_SECONDS, PRICING_EXPIRES_AT,
    PRICING_OBSERVED_AT, REQUIRED_SESSION_COVERAGE_UTC, READINESS_INVENTORY, FixedCredentialBoundary,
    EndpointCost, cost_contract_document, installed_readiness_projection, revised_plan_identity,
    reviewed_cost_contracts, september_9_cost_evidence_document, september_9_plan_identity,
    validate_september_9_cost_evidence)
from .provider_readiness_service import (install_cost_contract, probe_credential_once,
    refresh_september_9_cost_contract, restore_prior_pricing, _backup_value, main)
from .unattended_tuesday_service import SupervisorHeartbeatStore, SupervisorIncidentStore, supervise

class Probe:
    def __init__(self,value): self.value=value; self.calls=0
    def exists(self,**kwargs): self.calls+=1; return self.value

class Superbatch28C(unittest.TestCase):
    def readiness_root(self,raw):
        root=Path(raw)/"ready"; install_cost_contract(root=root)
        probe_credential_once(root=root,runner=Probe(True),clock=lambda:datetime(2026,9,9,12,tzinfo=timezone.utc))
        return root

    def september_9_document(self):
        return september_9_cost_evidence_document(observed_at="2026-09-09T12:00:00+00:00",
            expires_at="2026-09-09T20:05:00+00:00",
            observation_identity="financial-datasets-pricing-2026-09-09-public-review-v1")
    def test_cost_window_is_bounded_and_covers_close(self):
        observed=datetime.fromisoformat(PRICING_OBSERVED_AT); expires=datetime.fromisoformat(PRICING_EXPIRES_AT)
        self.assertEqual((expires-observed).total_seconds(),MAX_COST_EVIDENCE_AGE_SECONDS)
        self.assertGreaterEqual(expires,datetime.fromisoformat(REQUIRED_SESSION_COVERAGE_UTC))
        self.assertTrue(all(c.validate(observed)=="VALID" for c in reviewed_cost_contracts().values()))
        sample=next(iter(reviewed_cost_contracts().values()))
        too_long=EndpointCost(sample.evidence_category,sample.endpoint_identity,1,sample.source_url,sample.observed_at,(expires+timedelta(seconds=1)).isoformat())
        self.assertEqual(too_long.validate(observed),"COST_CONTRACT_EXPIRED")

    def test_plan_and_contract_are_exact(self):
        doc=cost_contract_document()
        self.assertEqual(revised_plan_identity(),"48e931a03c69586f77a0804b9e73f89e39e0fff059808de4344dec0bbe7d7c60")
        self.assertEqual((doc["planned_request_count"],doc["worst_case_credits"],doc["stage_a_maximum"],doc["daily_hard_ceiling"]),(50,50,100,200))
        self.assertEqual({x["endpoint_identity"] for x in doc["contracts"]},{"MARKET_SNAPSHOT","HISTORICAL_OHLCV","COMPANY_FACTS"})

    def test_install_and_one_presence_probe_only(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)/"ready"; self.assertEqual(install_cost_contract(root=root),"COST_CONTRACT_INSTALLED")
            probe=Probe(True); self.assertEqual(probe_credential_once(root=root,runner=probe,clock=lambda:datetime(2026,9,8,2,tzinfo=timezone.utc)),"AVAILABLE")
            self.assertEqual(probe.calls,1); self.assertEqual({p.name for p in root.iterdir()},READINESS_INVENTORY)
            result=installed_readiness_projection(root=root,now=datetime(2026,9,8,2,tzinfo=timezone.utc))
            self.assertEqual(result["commissioning_state"],"READY_FOR_OWNER_POLICY_AUTHORIZATION")
            self.assertEqual((result["stage_a_released_credits"],result["network_enabled"]),(0,False))
            with self.assertRaisesRegex(ValueError,"CREDENTIAL_PRESENCE_ALREADY_CHECKED"): probe_credential_once(root=root,runner=probe)
            self.assertEqual(probe.calls,1)

    def test_supervisor_idles_without_policy_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)/"policy"; self.assertEqual(supervise(root=root,iterations=1),0)
            gate=threading.Event(); release=threading.Event()
            def sleeper(_): gate.set(); release.wait(2)
            thread=threading.Thread(target=lambda:supervise(root=root,iterations=2,sleep=sleeper)); thread.start(); self.assertTrue(gate.wait(1))
            self.assertEqual(supervise(root=root,iterations=1),4); release.set(); thread.join()
            self.assertFalse((root/"unattended-policy.json").exists())

    def test_reviewed_plist_is_fixed_and_disabled(self):
        path=Path(__file__).parents[3]/"config/com.iios.expansion-wing-unattended-tuesday.plist.template"
        value=plistlib.loads(path.read_bytes().replace(b"__FIXED_PYTHON__",b"/usr/bin/python3").replace(b"__FIXED_WORKTREE__",b"/tmp/work").replace(b"__OWNER_ONLY_LOG__",b"/tmp/log"))
        self.assertEqual(value["Label"],"com.iios.expansion-wing-unattended-tuesday")
        self.assertEqual(value["ProgramArguments"][-1],"--operational-supervisor")
        forbidden=" ".join(value["ProgramArguments"])
        for word in ("activate","provider","credential","policy","browser","ledger","broker"): self.assertNotIn(word,forbidden.lower())
        self.assertTrue(value["RunAtLoad"]); self.assertEqual(value["KeepAlive"],{"SuccessfulExit":False})

    def test_supervisor_schedules_selected_september_9_generation_only(self):
        class Coordinator:
            def __init__(self): self.ticks=[]
            def recover(self): return {"classification":"SEPTEMBER_9_MARKET_OPEN_50","phase":"STAGE_A_RUNNING"}
            def scheduled_tick(self,now): self.ticks.append(now); return "BOUNDED_WAIT"
        selected=Coordinator(); factories=[]
        def factory(): factories.append(True); return selected
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)/"policy"
            self.assertEqual(supervise(root=root,iterations=1,clock=lambda:datetime(2026,9,9,8,tzinfo=timezone.utc),coordinator_factory=factory),0)
        self.assertEqual((len(factories),len(selected.ticks)),(1,1))
        self.assertEqual(selected.ticks[0].date().isoformat(),"2026-09-09")

    def test_supervisor_persists_sanitized_incident_instead_of_silent_exit(self):
        def broken():
            raise ValueError("SELECTED_GENERATION_INVALID")
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); root=base/"policy"; incidents=SupervisorIncidentStore(base/"incidents")
            result=supervise(root=root,iterations=1,coordinator_factory=broken,incident_store=incidents,
                clock=lambda:datetime(2026,9,9,8,tzinfo=timezone.utc))
            record=json.loads((base/"incidents"/"latest-incident.json").read_text())
            incident_mode=(base/"incidents").stat().st_mode&0o777
        self.assertEqual(result,4); self.assertEqual(record["failure_category"],"SELECTED_GENERATION_INVALID")
        self.assertEqual(record["phase"],"OPERATIONAL_COORDINATOR")
        self.assertEqual(incident_mode,0o700)
        self.assertNotIn("private",json.dumps(record).lower())

    def test_supervisor_persists_hash_bound_runtime_heartbeat(self):
        digest="a"*64; commit="b"*40; generation="2026-09-09-shadow"
        evidence={"release_commit":commit,"supervisor_manifest_hash":digest,"executor_manifest_hash":digest,
            "selected_generation":generation,"plan_identity":digest,"executor_state_hash":digest,
            "projection_hash":digest,"projection_generation":generation,"ledger_identity":digest}
        observed=datetime(2026,9,9,17,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); root=base/"policy"; heartbeat=SupervisorHeartbeatStore(base/"heartbeat")
            (base/"heartbeat").mkdir(mode=0o700)
            self.assertEqual(supervise(root=root,iterations=1,clock=lambda:observed,
                heartbeat_store=heartbeat,heartbeat_evidence_factory=lambda:evidence),0)
            value=json.loads((base/"heartbeat"/"supervisor-heartbeat.json").read_text())
            mode=(base/"heartbeat"/"supervisor-heartbeat.json").stat().st_mode&0o777
        self.assertEqual(value["schema"],"iios-unattended-supervisor-heartbeat-v1")
        self.assertEqual(value["selected_generation"],generation); self.assertEqual(mode,0o600)
        supplied=value.pop("content_hash"); self.assertEqual(supplied,__import__("hashlib").sha256(
            (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest())

    def test_september_9_refresh_backup_reader_and_exact_restore(self):
        with tempfile.TemporaryDirectory() as raw:
            root=self.readiness_root(raw); rollback=Path(raw)/"rollback"; old=(root/"provider-cost-contract.json").read_bytes(); doc=self.september_9_document()
            self.assertEqual(refresh_september_9_cost_contract(document=doc,root=root,rollback=rollback,
                now=datetime(2026,9,9,13,tzinfo=timezone.utc)),"SEPTEMBER_9_COST_CONTRACT_INSTALLED")
            receipt=_backup_value(rollback)
            self.assertEqual(receipt["target_document_hash"],doc["document_hash"])
            self.assertEqual((rollback/"prior-provider-cost-contract.json").read_bytes(),old)
            projected=installed_readiness_projection(root=root,now=datetime(2026,9,9,13,tzinfo=timezone.utc))
            self.assertEqual((projected["provider_state"],projected["request_plan_identity"],projected["planned_identity_count"]),
                ("READY",september_9_plan_identity(),50))
            self.assertEqual(refresh_september_9_cost_contract(document=doc,root=root,rollback=rollback,
                now=datetime(2026,9,9,13,tzinfo=timezone.utc)),"SEPTEMBER_9_COST_CONTRACT_ALREADY_INSTALLED")
            self.assertEqual(restore_prior_pricing(root=root,rollback=rollback),"PRIOR_PRICING_RESTORED")
            self.assertEqual((root/"provider-cost-contract.json").read_bytes(),old)

    def test_september_9_refresh_rejects_time_and_contract_tampering(self):
        valid=self.september_9_document(); now=datetime(2026,9,9,13,tzinfo=timezone.utc)
        for changed in ({"request_plan_identity":"c40b4c241d114df4d95069e55e7c68a4fbc8e1c899c5faa6aa8e3767b97a626a"},
                        {"planned_request_count":49},{"unique_request_identity_count":49},
                        {"exact_planned_cost_credits":49},{"worst_case_cost_credits":51},
                        {"automatic_retry_count":1},{"source_url_identity":"https://example.invalid"},
                        {"reviewed_endpoint_identities":["MARKET_SNAPSHOT"]}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                validate_september_9_cost_evidence(valid|changed,now=now)
        with self.assertRaises(ValueError): validate_september_9_cost_evidence(valid,now=datetime(2026,9,9,21,tzinfo=timezone.utc))
        future=september_9_cost_evidence_document(observed_at="2026-09-09T14:00:00+00:00",expires_at="2026-09-09T20:05:00+00:00",observation_identity="financial-datasets-pricing-2026-09-09-future-v1")
        with self.assertRaises(ValueError): validate_september_9_cost_evidence(future,now=now)
        for observed,expires in (("2026-09-08T12:00:00+00:00","2026-09-09T20:05:01+00:00"),
                                 ("2026-09-09T12:00:00+00:00","2026-09-09T20:04:59+00:00")):
            with self.assertRaises(ValueError): september_9_cost_evidence_document(observed_at=observed,expires_at=expires,observation_identity="financial-datasets-pricing-2026-09-09-invalid-v1")

    def test_invalid_old_record_and_refresh_interruptions_fail_closed(self):
        now=datetime(2026,9,9,13,tzinfo=timezone.utc); doc=self.september_9_document()
        with tempfile.TemporaryDirectory() as raw:
            root=self.readiness_root(raw); rollback=Path(raw)/"rollback"
            (root/"provider-cost-contract.json").write_text("{}\n")
            with self.assertRaises(ValueError): refresh_september_9_cost_contract(document=doc,root=root,rollback=rollback,now=now)
            self.assertFalse(rollback.exists())
        for phase in ("before_backup","backup","staging","selection","after_selection"):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as raw:
                root=self.readiness_root(raw); rollback=Path(raw)/"rollback"; old=(root/"provider-cost-contract.json").read_bytes()
                with self.assertRaises(RuntimeError): refresh_september_9_cost_contract(document=doc,root=root,rollback=rollback,now=now,interrupt_at=phase)
                if phase=="after_selection": self.assertEqual((root/"provider-cost-contract.json").read_bytes(),old)
                self.assertEqual(refresh_september_9_cost_contract(document=doc,root=root,rollback=rollback,now=now),"SEPTEMBER_9_COST_CONTRACT_INSTALLED")

    def test_post_selection_failure_rolls_back_and_has_no_operational_surface(self):
        with tempfile.TemporaryDirectory() as raw:
            root=self.readiness_root(raw); rollback=Path(raw)/"rollback"; old=(root/"provider-cost-contract.json").read_bytes()
            with self.assertRaisesRegex(ValueError,"POST_SELECTION_REJECTED"):
                refresh_september_9_cost_contract(document=self.september_9_document(),root=root,rollback=rollback,
                    now=datetime(2026,9,9,13,tzinfo=timezone.utc),
                    post_select_validator=lambda _:(_ for _ in ()).throw(ValueError("POST_SELECTION_REJECTED")))
            self.assertEqual((root/"provider-cost-contract.json").read_bytes(),old)
        source=Path(__file__).with_name("provider_readiness_service.py").read_text().lower()
        for forbidden in ("urlopen(","requests.get(","select_generation(","released_credits = 50","broker_authority = true"):
            self.assertNotIn(forbidden,source)
        self.assertEqual(main(["--refresh-september-9-cost-contract","--browser",
            "--observed-at","2026-09-09T12:00:00+00:00","--expires-at","2026-09-09T20:05:00+00:00",
            "--observation-identity","financial-datasets-pricing-2026-09-09-public-review-v1"]),5)

if __name__=="__main__": unittest.main()
