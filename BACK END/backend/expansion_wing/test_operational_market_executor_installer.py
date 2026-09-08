from __future__ import annotations
import json, os, tempfile, unittest
from pathlib import Path
from .operational_market_executor import CANARY_PLAN, ExecutorStore, canary_plan
from .operational_market_executor_installer import *

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

if __name__=="__main__": unittest.main()
