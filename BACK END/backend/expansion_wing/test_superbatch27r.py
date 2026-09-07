from __future__ import annotations

import copy
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from .acceptance_server import (
    CONTROLLER_PROVENANCE_AUTHENTIC, CONTROLLER_PROVENANCE_SYNTHETIC,
    CONTROLLER_PROVENANCE_UNAVAILABLE, Compositor,
)
from .tuesday_controller_state import (
    ControllerStateStore, ControllerStatusReader, DisabledSupervisor, _canonical, _hash,
    disabled_state, installation_manifest, validate_state,
)
from .tuesday_controller_v2 import (
    LAST_KNOWN_VALID_NAME, STATE_SCHEMA_V2, V1_ROLLBACK_NAME, V2_FIELDS, browser_projection_v2,
    migrate_store_atomic, migrate_v1_to_v2, validate_state_v2,
)

STAMP = "2026-09-07T00:00:00+00:00"
IDENTITY = "controller-install-27r"


class OperationalV2ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "state"
        self.install = installation_manifest(IDENTITY, installed=True, registered=True, running=False, generated_at=STAMP)
        self.v1 = disabled_state(IDENTITY, installed=True, running=False, updated_at=STAMP)

    def tearDown(self): self.temp.cleanup()

    def v2(self): return migrate_v1_to_v2(self.v1, self.install, timestamp="2026-09-07T00:01:00+00:00")

    def test_valid_v1_and_v2_loading_and_exact_contract(self):
        self.assertEqual(validate_state(self.v1, self.install)["schema_version"], "iios-tuesday-controller-state-v1")
        value = validate_state(self.v2(), self.install)
        self.assertEqual(set(value), V2_FIELDS); self.assertEqual(value["schema_version"], STATE_SCHEMA_V2)
        self.assertEqual(value["daily_hard_ceiling"], 200); self.assertEqual(value["released_credit_total"], 0)
        self.assertEqual({k: v["maximum"] for k, v in value["stages"].items()}, {"A": 100, "B": 50, "C": 50})
        self.assertEqual(len(value["stages"]["A"]["draft_request_identities"]), 50)
        self.assertTrue(all(v["locked"] and v["released"] == 0 for v in value["stages"].values()))

    def test_migration_preserves_monotonic_state_and_accounting(self):
        old = copy.deepcopy(self.v1)
        old.update({"sequence": 7, "phase_history": ["TUESDAY_PREMARKET_LOCKED"] * 2,
                    "requests_used": 2, "credits_used": 1,
                    "request_identities": ["legacy-request-0001", "legacy-request-0002"]})
        old["content_hash"] = _hash(old)
        value = migrate_v1_to_v2(old, self.install, timestamp="2026-09-07T00:02:00+00:00")
        self.assertEqual(value["sequence"], 8); self.assertEqual(value["phase_history"], old["phase_history"])
        self.assertEqual(value["request_identities"], old["request_identities"])
        self.assertEqual((value["confirmed_credits"], value["ambiguous_credits"]), (1, 1))
        self.assertEqual(value["rehearsal_receipts"][0]["classification"], old["monday_rehearsal_status"])
        self.assertTrue(value["authority_locked"]); self.assertFalse(any(value["authority"].values()))

    def test_unknown_duplicate_hash_future_and_authority_fail_closed(self):
        mutations = []
        bad = self.v2(); bad["unknown"] = True; mutations.append((bad, "STATE_V2_SCHEMA_INVALID"))
        bad = self.v2(); bad["request_identities"] = ["duplicate-id", "duplicate-id"]; bad["requests_used"] = 2; bad["content_hash"] = _hash(bad); mutations.append((bad, "DUPLICATE_REQUEST_IDENTITY"))
        bad = self.v2(); bad["content_hash"] = "0" * 64; mutations.append((bad, "STATE_V2_HASH_OR_FAILURE_INVALID"))
        bad = self.v2(); bad["updated_at"] = "2999-01-01T00:00:00+00:00"; bad["content_hash"] = _hash(bad); mutations.append((bad, "FUTURE_TIMESTAMP"))
        bad = self.v2(); bad["authority"]["provider"] = True; bad["content_hash"] = _hash(bad); mutations.append((bad, "AUTHORITY_INVALID"))
        for value, reason in mutations:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason): validate_state_v2(value, self.install)

    def test_missing_receipt_stage_and_accounting_limits_fail(self):
        mutations = []
        bad = self.v2(); bad["rehearsal_receipts"] = []; bad["content_hash"] = _hash(bad); mutations.append((bad, "REHEARSAL_RECEIPTS_MISSING"))
        bad = self.v2(); bad["stages"]["A"]["released"] = 1; bad["released_credit_total"] = 1; bad["content_hash"] = _hash(bad); mutations.append((bad, "BUDGET_CONTRACT_INVALID|STAGE_RELEASE_INVALID"))
        bad = self.v2(); bad["per_instrument_accounting"] = {"MU": 11}; bad["content_hash"] = _hash(bad); mutations.append((bad, "ACCOUNTING_LIMIT_EXCEEDED"))
        bad = self.v2(); bad["per_endpoint_accounting"] = {"MARKET": 101}; bad["content_hash"] = _hash(bad); mutations.append((bad, "ACCOUNTING_LIMIT_EXCEEDED"))
        for value, reason in mutations:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason): validate_state_v2(value, self.install)

    def test_atomic_migration_repeat_rejection_and_last_known_valid(self):
        store = ControllerStateStore(self.root); store.initialize(self.install, self.v1)
        before = (self.root / "controller-state.json").read_bytes()
        value = migrate_store_atomic(store, timestamp="2026-09-07T00:03:00+00:00")
        self.assertEqual(value["schema_version"], STATE_SCHEMA_V2)
        self.assertEqual((self.root / V1_ROLLBACK_NAME).read_bytes(), before)
        self.assertEqual(json.loads((self.root / LAST_KNOWN_VALID_NAME).read_text())["schema_version"], STATE_SCHEMA_V2)
        self.assertEqual((self.root / "controller-state.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "ALREADY_MIGRATED"): migrate_store_atomic(store, timestamp="2026-09-07T00:04:00+00:00")

    def test_partial_current_recovers_lkv_but_ordinary_read_fails(self):
        store = ControllerStateStore(self.root); store.initialize(self.install, self.v1)
        migrate_store_atomic(store, timestamp="2026-09-07T00:03:00+00:00")
        current = (self.root / "controller-state.json").read_bytes()
        (self.root / LAST_KNOWN_VALID_NAME).write_bytes(current); os.chmod(self.root / LAST_KNOWN_VALID_NAME, 0o600)
        (self.root / "controller-state.json").write_bytes(b'{"partial":'); os.chmod(self.root / "controller-state.json", 0o600)
        with self.assertRaisesRegex(ValueError, "STATE_JSON_INVALID"): store.read(recover=False)
        self.assertEqual(store.read(recover=True)[1]["schema_version"], STATE_SCHEMA_V2)

    def test_permissions_symlink_inventory_and_malformed_rejected(self):
        store = ControllerStateStore(self.root); store.initialize(self.install, self.v1)
        os.chmod(self.root / "controller-state.json", 0o644)
        with self.assertRaisesRegex(ValueError, "FILE_MODE_INVALID"): store.read()
        os.chmod(self.root / "controller-state.json", 0o600); (self.root / "unknown").write_text("x")
        with self.assertRaisesRegex(ValueError, "STATE_INVENTORY_INVALID"): store.read()
        (self.root / "unknown").unlink(); target = self.root / "target"; target.write_text("x")
        (self.root / "controller-state.json").unlink(); (self.root / "controller-state.json").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "STATE_INVENTORY_INVALID|UNSAFE_FILE_TYPE"): store.read()

    def test_browser_projection_is_strict_scalar_summary(self):
        value = browser_projection_v2(self.v2(), running=False)
        self.assertEqual(value["daily_hard_ceiling"], 200); self.assertEqual(value["released_now"], 0)
        encoded = json.dumps(value)
        for prohibited in ("request_identities", "installation_identity", "content_hash", "provider_response", "state-root"):
            self.assertNotIn(prohibited, encoded)

    def test_compositor_accepts_v2_allowlist_and_rejects_extra_field(self):
        value = browser_projection_v2(self.v2(), running=False)
        missing = Path(self.temp.name) / "missing"
        compositor = Compositor(missing, missing, missing, missing, "http://127.0.0.1:1", controller_reader=lambda: value,
                                controller_status_provenance="AUTHENTIC_OPERATIONAL_STATE")
        compositor._reachability = lambda: "UNAVAILABLE"
        self.assertEqual(compositor.snapshot()["sections"]["tuesday_controller_status"]["state"], "INSTALLED_BUT_DISABLED")
        compositor.controller_reader = lambda: value | {"request_identities": []}
        self.assertEqual(compositor.snapshot()["sections"]["tuesday_controller_status"], {"state": "UNAVAILABLE", "data": None})

    def test_controller_provenance_is_explicit_strict_and_schema_independent(self):
        missing = Path(self.temp.name) / "missing"
        v2 = browser_projection_v2(self.v2(), running=False)
        v1_root = Path(self.temp.name) / "v1"
        ControllerStateStore(v1_root).initialize(self.install, self.v1)
        v1 = ControllerStatusReader(v1_root).read()

        def projected(value, provenance=CONTROLLER_PROVENANCE_UNAVAILABLE):
            compositor = Compositor(
                missing, missing, missing, missing, "http://127.0.0.1:1",
                controller_reader=lambda: value,
                controller_status_provenance=provenance,
            )
            compositor._reachability = lambda: "UNAVAILABLE"
            return compositor.snapshot()["sections"]["tuesday_controller_status"]

        for value in (v1, v2):
            for provenance in (CONTROLLER_PROVENANCE_AUTHENTIC, CONTROLLER_PROVENANCE_SYNTHETIC):
                with self.subTest(schema=value["schema_version"], provenance=provenance):
                    result = projected(value, provenance)
                    self.assertEqual(result["data"]["controller_status_provenance"], provenance)
                    self.assertNotIn("installation_identity", json.dumps(result))
                    self.assertNotIn("request_identities", json.dumps(result))
        for provenance in (CONTROLLER_PROVENANCE_UNAVAILABLE, "UNKNOWN", ""):
            with self.subTest(provenance=provenance):
                self.assertEqual(projected(v2, provenance), {"state": "UNAVAILABLE", "data": None})

        contradictory = v2 | {"migration_status": "NOT_MIGRATED"}
        self.assertEqual(
            projected(contradictory, CONTROLLER_PROVENANCE_AUTHENTIC),
            {"state": "UNAVAILABLE", "data": None},
        )

    def test_isolated_lifecycle_restart_and_byte_exact_rollback(self):
        store = ControllerStateStore(self.root); store.initialize(self.install, self.v1)
        original_install = (self.root / "installation.json").read_bytes(); original_state = (self.root / "controller-state.json").read_bytes()
        migrate_store_atomic(store, timestamp="2026-09-07T00:03:00+00:00")
        env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parents[1])}
        for _ in range(2):
            proc = subprocess.Popen([sys.executable, "-m", "expansion_wing.tuesday_controller_service", "--supervisor", "--state-root", str(self.root)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(50):
                if proc.poll() is not None or ControllerStatusReader(self.root).read().get("running"): break
                time.sleep(.03)
            self.assertIsNone(proc.poll()); self.assertEqual(ControllerStatusReader(self.root).read()["controller_schema"], STATE_SCHEMA_V2)
            proc.send_signal(signal.SIGTERM); stdout, stderr = proc.communicate(timeout=3)
            self.assertEqual(proc.returncode, 0); self.assertEqual(stdout, b""); self.assertEqual(stderr, b"")
        for path in self.root.iterdir(): path.unlink()
        (self.root / "installation.json").write_bytes(original_install); os.chmod(self.root / "installation.json", 0o600)
        (self.root / "controller-state.json").write_bytes(original_state); os.chmod(self.root / "controller-state.json", 0o600)
        install, state = store.read(); self.assertEqual(_canonical(install), original_install); self.assertEqual(_canonical(state), original_state)

    def test_duplicate_supervisor_and_no_listener_contract(self):
        store = ControllerStateStore(self.root); store.initialize(self.install, self.v1)
        first = store.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "DUPLICATE_SUPERVISOR"): store.acquire()
        finally: first.close()
        source = Path(__file__).with_name("tuesday_controller_service.py").read_text()
        self.assertNotIn("socket", source); self.assertNotIn("HTTPServer", source); self.assertNotIn("provider", source.lower())

    def test_activation_and_browser_invocation_rejected(self):
        from .tuesday_controller_service import main
        self.assertEqual(main(["--activate"]), 3)
        self.assertEqual(main(["--browser"]), 3)


if __name__ == "__main__": unittest.main()
