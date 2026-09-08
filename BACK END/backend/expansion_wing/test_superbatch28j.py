from __future__ import annotations
import json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from .test_superbatch28h import Superbatch28H,COMMIT,NOW
from .unattended_supervisor_installer import MANIFEST_NAME,museum_identity_document,supervisor_browser_projection

class Superbatch28J(unittest.TestCase):
    def test_match_mismatch_tamper_absent_and_coherent_recovery(self):
        helper=Superbatch28H()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); candidate=helper.candidate(raw); installed=root/"installed"; installed.mkdir(mode=0o700)
            artifacts=installed/"installed-artifacts"; artifacts.mkdir(mode=0o700)
            for item in candidate.iterdir():
                if item.name==MANIFEST_NAME: continue
                target=artifacts/item.name
                if item.is_dir():
                    import shutil; shutil.copytree(item,target); [p.chmod(0o600) for p in target.iterdir()]
                else: target.write_bytes(item.read_bytes()); target.chmod(0o600)
            (installed/MANIFEST_NAME).write_bytes((candidate/MANIFEST_NAME).read_bytes()); (installed/MANIFEST_NAME).chmod(0o600)
            museum_root=root/"museum"; museum_root.mkdir(mode=0o700)
            museum=museum_root/"installation-manifest.json"; museum.write_text(json.dumps(museum_identity_document(COMMIT,"b"*64),sort_keys=True,separators=(",",":"))+"\n"); museum.chmod(0o600)
            service=lambda:{"running":True,"supervisor_count":1,"lock_owned":True,"listeners":0,"children":0}
            value=supervisor_browser_projection(supervisor_root=installed,museum_manifest=museum,service_probe=service,clock=lambda:NOW)
            self.assertEqual((value["commit_binding"],value["manifest_status"],value["inventory_status"]),("MATCH","VALID","VALID"))
            museum.write_text(json.dumps(museum_identity_document("c"*40,"b"*64),sort_keys=True,separators=(",",":"))+"\n")
            self.assertEqual(supervisor_browser_projection(supervisor_root=installed,museum_manifest=museum,service_probe=service)["commit_binding"],"MISMATCH")
            (artifacts/"expansion_wing/unattended_tuesday.py").write_text("tamper")
            self.assertEqual(supervisor_browser_projection(supervisor_root=installed,museum_manifest=museum,service_probe=service)["manifest_status"],"UNAVAILABLE")
        with tempfile.TemporaryDirectory() as raw:
            missing=supervisor_browser_projection(supervisor_root=Path(raw)/"missing",museum_manifest=Path(raw)/"museum")
            self.assertEqual((missing["provenance"],missing["commit_binding"]),("SUPERVISOR_NOT_INSTALLED","UNAVAILABLE"))

    def test_partial_wrong_mode_and_service_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); partial=root/"partial"; partial.mkdir(mode=0o700)
            museum_root=root/"museum"; museum_root.mkdir(mode=0o700)
            museum=museum_root/"installation-manifest.json"
            museum.write_text(json.dumps(museum_identity_document(COMMIT,"b"*64))+"\n"); museum.chmod(0o600)
            value=supervisor_browser_projection(supervisor_root=partial,museum_manifest=museum)
            self.assertEqual(value["provenance"],"UNAVAILABLE")
            partial.chmod(0o755)
            self.assertEqual(supervisor_browser_projection(supervisor_root=partial,museum_manifest=museum)["manifest_status"],"UNAVAILABLE")

    def test_frontend_has_browser_safe_manifest_status(self):
        source=(Path(__file__).parents[3]/"FRONT END/src/MobExpansionWing.tsx").read_text()
        for phrase in ("Unattended supervisor installation","Commit binding","Service ownership","Lock ownership"):
            self.assertIn(phrase,source)
        provider=(Path(__file__).parents[3]/"FRONT END/src/ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertIn("supervisorGeneration",provider)
        self.assertIn("supervisorReadAt < priorSupervisor.readAt",provider)

if __name__=="__main__": unittest.main()
