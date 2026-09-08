from __future__ import annotations
import json, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from .provider_readiness import operational_cost_binding, revised_plan_identity
from .provider_readiness_service import install_cost_contract, probe_credential_once
from .unattended_tuesday import POLICY_SCHEMA, POLICY_SCHEMA_V1, OfflineSession, initial_state, make_policy, operational_request_plan, transition, validate_policy
from .unattended_tuesday_service import install

NOW=datetime(2026,9,8,2,0,tzinfo=timezone.utc); COMMIT="e"*40; OWNER="OPAQUE_OWNER_APPROVAL_28E"
class Probe:
    def exists(self,**_kwargs): return True
def readiness(root:Path):
    install_cost_contract(root=root); probe_credential_once(root=root,runner=Probe(),clock=lambda:NOW)
    return operational_cost_binding(root=root,now=NOW)
def manifest(path:Path,commit:str=COMMIT):
    path.write_text(json.dumps({"schema":"iios-unattended-installation-v1","installed_commit":commit})); path.chmod(0o600)

class Superbatch28E(unittest.TestCase):
    def policy(self,root:Path):
        return make_policy(owner_identity=OWNER,approval_timestamp=NOW.isoformat(),command_time=NOW,
            installed_commit=COMMIT,authorized_commit=COMMIT,cost_binding=readiness(root))
    def test_exact_v2_binding_and_allowance(self):
        with tempfile.TemporaryDirectory() as raw:
            p=self.policy(Path(raw)/"ready")
            self.assertEqual((p["schema_version"],p["approved_commit"],p["request_plan_identity"]),(POLICY_SCHEMA,COMMIT,revised_plan_identity()))
            self.assertEqual((p["stage_a_authorized_allowance_credits"],p["stage_a_maximum"],initial_state(p)["released_credits"]),(50,100,0))
    def test_binding_mismatch_and_v1_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            binding=readiness(Path(raw)/"ready")
            with self.assertRaisesRegex(ValueError,"POLICY_BINDING_INVALID"):
                make_policy(owner_identity=OWNER,approval_timestamp=NOW.isoformat(),command_time=NOW,installed_commit=COMMIT,authorized_commit="a"*40,cost_binding=binding)
        with self.assertRaisesRegex(ValueError,"POLICY_SCHEMA_INVALID"): validate_policy({"schema_version":POLICY_SCHEMA_V1})
    def test_fixed_manifest_and_readiness_required(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); ready=base/"ready"; state=base/"state"; state.mkdir(mode=0o700); mf=base/"manifest.json"; manifest(mf); readiness(ready)
            self.assertEqual(install(OWNER,NOW.isoformat(),COMMIT,command_time=NOW,root=state,manifest=mf,readiness_root=ready),"ONE_DAY_POLICY_INSTALLED_DISABLED")
            self.assertEqual(json.loads((state/"unattended-policy.json").read_text())["stage_a_authorized_allowance_credits"],50)
    def test_release_exactly_fifty_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            p=self.policy(Path(raw)/"ready"); s=transition(transition(initial_state(p),p,"TUESDAY_WAITING_FOR_PREFLIGHT"),p,"TUESDAY_PREFLIGHT_RUNNING")
            gates={k:True for k in {"code_identity","controller_integrity","monday_receipt","single_supervisor","protected_services","projection_integrity","paper_unchanged","authorities_locked","stage_bc_locked","plan_valid","calendar_clock","network_bounds","no_conflicting_policy","no_browser_authorization"}}
            x=OfflineSession(p,s); costs={row["endpoint"]:1 for row in operational_request_plan()}
            self.assertEqual(x.release_stage_a(gates,costs),"STAGE_A_RUNNING"); self.assertEqual(x.state["released_credits"],50)
            with self.assertRaisesRegex(ValueError,"STAGE_A_ALLOWANCE_CONTRACT_UNSUPPORTED"): OfflineSession(p,json.loads(json.dumps(x.state))).release_stage_a(gates,costs)
if __name__=="__main__": unittest.main()
