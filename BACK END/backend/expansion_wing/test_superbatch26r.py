from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .acceptance_server import Compositor
from .tuesday_controller_state import (
    BROWSER_SCHEMA, INSTALL_NAME, LOCKS, STATE_NAME, ControllerStateStore,
    ControllerStatusReader, disabled_state, installation_manifest,
    validate_installation, validate_state,
)

NOW = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)


class ControllerStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "controller"
        self.identity = "installation-fixture-0001"
        stamp = NOW.isoformat()
        self.install = installation_manifest(self.identity, installed=True, registered=True, running=False, generated_at=stamp)
        self.state = disabled_state(self.identity, installed=True, running=False, updated_at=stamp)
        self.store = ControllerStateStore(self.root)
        self.store.initialize(self.install, self.state)

    def tearDown(self): self.temp.cleanup()

    def test_owner_only_atomic_fixed_inventory(self):
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual({p.name for p in self.root.iterdir()}, {INSTALL_NAME, STATE_NAME})
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.root.iterdir()))
        self.assertFalse(any(p.name.startswith(".") for p in self.root.iterdir()))

    def test_strict_hash_schema_future_authority_and_budget_rejection(self):
        for mutate, category in (
            (lambda x: x.update(extra=True), "STATE_SCHEMA_INVALID"),
            (lambda x: x.update(content_hash="0" * 64), "STATE_HASH_INVALID"),
            (lambda x: x["authority"].update(provider=True), "STATE_AUTHORITY_INVALID"),
            (lambda x: x.update(requests_used=31), "BUDGET_STATE_INVALID"),
            (lambda x: x.update(updated_at=(NOW + timedelta(seconds=1)).isoformat()), "FUTURE_TIMESTAMP"),
        ):
            value=json.loads(json.dumps(self.state)); mutate(value)
            if category not in {"STATE_HASH_INVALID", "STATE_SCHEMA_INVALID"}:
                value["content_hash"] = __import__("expansion_wing.tuesday_controller_state", fromlist=["_hash"])._hash(value)
            with self.assertRaisesRegex(ValueError, category): validate_state(value, self.install, now=NOW)

    def test_permissions_symlink_unknown_and_ambiguous_install_fail_closed(self):
        (self.root / STATE_NAME).chmod(0o644)
        self.assertEqual(ControllerStatusReader(self.root).read()["state"], "FAILED_CLOSED")
        (self.root / STATE_NAME).chmod(0o600); (self.root / "unknown.json").write_text("{}")
        self.assertEqual(ControllerStatusReader(self.root).read()["state"], "FAILED_CLOSED")
        (self.root / "unknown.json").unlink(); (self.root / STATE_NAME).unlink(); (self.root / STATE_NAME).symlink_to(self.root / INSTALL_NAME)
        self.assertEqual(ControllerStatusReader(self.root).read()["state"], "FAILED_CLOSED")
        bad=installation_manifest(self.identity,installed=True,registered=True,running=False,generated_at=NOW.isoformat()); bad["launchd_registered"]=False
        bad["content_hash"]=__import__("expansion_wing.tuesday_controller_state",fromlist=["_hash"])._hash(bad)
        with self.assertRaisesRegex(ValueError,"INSTALLATION_STATE_AMBIGUOUS"): validate_installation(bad,now=NOW)

    def test_missing_is_truthful_not_installed(self):
        value=ControllerStatusReader(Path(self.temp.name)/"absent").read()
        self.assertEqual(value["state"],"NOT_INSTALLED"); self.assertFalse(value["installed"]); self.assertFalse(value["running"])

    def test_browser_projection_is_scalar_bounded_and_authority_locked(self):
        value=ControllerStatusReader(self.root).read()
        self.assertEqual(value["schema_version"],BROWSER_SCHEMA); self.assertTrue(value["installed"])
        self.assertFalse(value["activated"]); self.assertTrue(value["authority_locked"])
        self.assertTrue(all(not isinstance(v,(dict,list)) for v in value.values()))
        self.assertNotIn("installation_identity",value); self.assertNotIn("request_identities",value)

    def test_restart_preserves_budget_identity_phase_and_never_activates(self):
        prior=json.loads(json.dumps(self.state)); prior.update(requests_used=1,credits_used=1,request_identities=["request-fixture-0001"])
        prior["content_hash"]=__import__("expansion_wing.tuesday_controller_state",fromlist=["_hash"])._hash(prior)
        recovered=disabled_state(self.identity,installed=True,running=True,updated_at=NOW.isoformat(),prior=prior,transition="SUPERVISOR_STARTED")
        self.assertEqual(recovered["request_identities"],prior["request_identities"])
        self.assertEqual(recovered["requests_used"],1); self.assertEqual(recovered["phase"],"TUESDAY_PREMARKET_LOCKED")
        self.assertGreater(recovered["sequence"],prior["sequence"]); self.assertFalse(recovered["activated"])
        self.assertEqual(recovered["authority"],LOCKS)

    def test_abrupt_stale_running_state_is_not_reported_alive(self):
        install=installation_manifest(self.identity,installed=True,registered=True,running=True,generated_at=NOW.isoformat())
        state=disabled_state(self.identity,installed=True,running=True,updated_at=NOW.isoformat(),prior=self.state,transition="SUPERVISOR_STARTED")
        self.store.write_installation(install); self.store.write_state(state,install)
        value=ControllerStatusReader(self.root).read()
        self.assertTrue(value["installed"]); self.assertFalse(value["running"]); self.assertFalse(value["activated"])

    def test_rejected_write_retains_exact_last_valid_bytes(self):
        before=(self.root/STATE_NAME).read_bytes(); unsafe=json.loads(json.dumps(self.state)); unsafe["authority"]["provider"]=True
        with self.assertRaisesRegex(ValueError,"STATE_AUTHORITY_INVALID"): self.store.write_state(unsafe,self.install)
        self.assertEqual((self.root/STATE_NAME).read_bytes(),before)

    def test_duplicate_supervisor_lock(self):
        first=self.store.acquire()
        try:
            with self.assertRaisesRegex(ValueError,"DUPLICATE_SUPERVISOR"): self.store.acquire()
        finally: first.close()

    def test_real_supervisor_signal_shutdown_has_no_listener_or_busy_loop(self):
        env={"PATH":"/usr/bin:/bin","PYTHONPATH":str(Path(__file__).parents[1])}
        proc=subprocess.Popen([sys.executable,"-m","expansion_wing.tuesday_controller_service","--supervisor","--state-root",str(self.root)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for _ in range(30):
                if proc.poll() is not None: break
                if ControllerStatusReader(self.root).read().get("running") is True: break
                time.sleep(.05)
            self.assertIsNone(proc.poll()); self.assertTrue(ControllerStatusReader(self.root).read()["running"])
            proc.send_signal(signal.SIGTERM); self.assertEqual(proc.wait(timeout=3),0)
            value=ControllerStatusReader(self.root).read(); self.assertFalse(value["running"]); self.assertFalse(value["activated"])
            self.assertEqual(proc.stdout.read(),b""); self.assertEqual(proc.stderr.read(),b"")
        finally:
            if proc.poll() is None: proc.kill(); proc.wait(timeout=3)
            proc.stdout.close(); proc.stderr.close()

    def test_activate_browser_and_missing_mode_are_rejected(self):
        from .tuesday_controller_service import main
        self.assertEqual(main(["--activate"]),3); self.assertEqual(main([]),2)

    def test_compositor_accepts_only_browser_allowlist(self):
        base=lambda: ControllerStatusReader(self.root).read()
        missing=Path(self.temp.name)/"missing.json"
        compositor=Compositor(missing,missing,missing,missing,"http://127.0.0.1:1",controller_reader=base)
        compositor._reachability=lambda: "UNAVAILABLE"
        projected=compositor.snapshot()["sections"]["tuesday_controller_status"]
        self.assertEqual(projected["state"],"INSTALLED_BUT_DISABLED")
        self.assertNotIn("request_identities",projected["data"]); self.assertNotIn("installation_identity",projected["data"])
        unsafe=base() | {"private_path":"prohibited"}
        compositor.controller_reader=lambda: unsafe
        self.assertEqual(compositor.snapshot()["sections"]["tuesday_controller_status"],{"state":"UNAVAILABLE","data":None})

    def test_fixture_matrix_is_complete(self):
        fixture=json.loads((Path(__file__).parent/"fixtures/superbatch26r_controller_states.json").read_text())
        self.assertEqual(len(fixture["scenarios"]),12); self.assertEqual(fixture["fixture_identity"],"SYNTHETIC_FIXTURE_NON_LIVE")

    def test_fixture_preview_uses_an_explicit_controller_state_root(self):
        source=(Path(__file__).parents[3]/"scripts/iios_factory_browser_preview.py").read_text()
        self.assertIn('"--controller-state-root"',source)
        self.assertIn("ControllerStatusReader(controller_state_root).read",source)
        self.assertNotIn("None if fixture_isolated else ControllerStatusReader().read",source)


if __name__ == "__main__": unittest.main()
