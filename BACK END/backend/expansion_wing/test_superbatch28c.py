from __future__ import annotations
import json, plistlib, tempfile, threading, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .provider_readiness import MAX_COST_EVIDENCE_AGE_SECONDS, PRICING_EXPIRES_AT, PRICING_OBSERVED_AT, REQUIRED_SESSION_COVERAGE_UTC, READINESS_INVENTORY, FixedCredentialBoundary, EndpointCost, cost_contract_document, installed_readiness_projection, revised_plan_identity, reviewed_cost_contracts
from .provider_readiness_service import install_cost_contract, probe_credential_once
from .unattended_tuesday_service import supervise

class Probe:
    def __init__(self,value): self.value=value; self.calls=0
    def exists(self,**kwargs): self.calls+=1; return self.value

class Superbatch28C(unittest.TestCase):
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

if __name__=="__main__": unittest.main()
