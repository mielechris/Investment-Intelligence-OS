from __future__ import annotations
import json, os, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from .provider_readiness import operational_cost_binding
from .provider_readiness_service import install_cost_contract, probe_credential_once
from .unattended_policy_reader import PROVENANCE_ABSENT, PROVENANCE_AUTHENTIC, PROVENANCE_SYNTHETIC, UnattendedPolicyReader, synthetic_absence_projection
from .unattended_tuesday import PolicyStore, make_policy

NOW=datetime(2026,9,8,2,0,tzinfo=timezone.utc); COMMIT="f"*40
class Probe:
    def exists(self,**_kwargs): return True

class Superbatch28F(unittest.TestCase):
    def setup(self,base:Path):
        manifest=base/"installation.json"; manifest.write_text(json.dumps({"schema":"iios-unattended-installation-v1","installed_commit":COMMIT})); manifest.chmod(0o600)
        ready=base/"ready"; install_cost_contract(root=ready); probe_credential_once(root=ready,runner=Probe(),clock=lambda:NOW)
        binding=operational_cost_binding(root=ready,now=NOW)
        policy=make_policy(owner_identity="OPAQUE_OWNER_28F",approval_timestamp=NOW.isoformat(),command_time=NOW,installed_commit=COMMIT,authorized_commit=COMMIT,cost_binding=binding)
        return manifest,policy
    def test_absent_installed_rollback_without_reader_restart(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); root=base/"policy"; manifest,policy=self.setup(base); reader=UnattendedPolicyReader(root,manifest)
            absent=reader.read(); self.assertEqual((absent["provenance"],absent["policy_installed"]),(PROVENANCE_ABSENT,False)); absent_identity=reader.cache_identity
            root.mkdir(mode=0o700); PolicyStore(root).install(policy); installed=reader.read()
            self.assertEqual((installed["provenance"],installed["policy_installed"],installed["phase"],installed["next_gate"],installed["released_credits"]),(PROVENANCE_AUTHENTIC,True,"TUESDAY_POLICY_INSTALLED_DISABLED","05:55 RECOVERY",0)); self.assertNotEqual(absent_identity,reader.cache_identity)
            saved=base/"saved"; root.rename(saved); rolled=reader.read(); self.assertEqual((rolled["provenance"],rolled["policy_installed"]),(PROVENANCE_ABSENT,False))
    def test_partial_tamper_and_same_mtime_change_fail_closed_then_recover(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); root=base/"policy"; manifest,policy=self.setup(base); root.mkdir(mode=0o700); PolicyStore(root).install(policy); reader=UnattendedPolicyReader(root,manifest)
            self.assertIsNotNone(reader.read()); path=root/"unattended-session.json"; before=path.stat(); original=path.read_bytes(); path.write_bytes(b"{}"); os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns)); self.assertIsNone(reader.read())
            path.write_bytes(original); path.chmod(0o600); self.assertEqual(reader.read()["provenance"],PROVENANCE_AUTHENTIC)
    def test_partial_installation_is_unavailable_and_fixture_is_explicit(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); root=base/"policy"; manifest,_policy=self.setup(base)
            root.mkdir(mode=0o700); (root/"unattended-policy.json").write_text("{}\n"); (root/"unattended-policy.json").chmod(0o600)
            self.assertIsNone(UnattendedPolicyReader(root,manifest).read())
            self.assertEqual(synthetic_absence_projection()["provenance"],PROVENANCE_SYNTHETIC)
    def test_readiness_maps_authenticated_policy_only(self):
        from .provider_readiness import installed_readiness_projection
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); ready=base/"ready"; install_cost_contract(root=ready); probe_credential_once(root=ready,runner=Probe(),clock=lambda:NOW)
            self.assertEqual(installed_readiness_projection(root=ready,now=NOW,policy_installed=False)["one_day_policy_state"],"NOT_AUTHORIZED")
            self.assertEqual(installed_readiness_projection(root=ready,now=NOW,policy_installed=True)["one_day_policy_state"],"AUTHORIZED_WAITING")
if __name__=="__main__": unittest.main()
