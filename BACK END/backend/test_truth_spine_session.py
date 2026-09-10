"""SB3.6 deterministic, offline lifecycle/capture/cleanup contracts only."""
from __future__ import annotations

import copy
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from truth_spine_contract import canonical, digest, seal, utc
from truth_spine_generations import GenerationStore, immutable_file, registry_record
from truth_spine_session import (CADENCE, Lifecycle, Phase, RestartPolicy, exchange_session,
                                parse_session, session_authority, validate_session_authority)
from truth_spine_session_supervisor import (REQUIRED_PROBES, SessionSupervisor, browser_contract, health)

OWNERS = {"scheduler": "unit-scheduler", "publisher": "unit-publisher"}


class Clock:
    def __init__(self, at): self.at = at
    def __call__(self): return self.at
    def advance(self, seconds): self.at += timedelta(seconds=seconds)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.session = exchange_session("2026-09-10")
        self.authority = session_authority(self.session, "unit-release", OWNERS, self.session.start)
        self.life = Lifecycle(self.session)

    def test_normal_calendar_and_pacific_clock(self):
        from zoneinfo import ZoneInfo
        self.assertEqual(self.session.open_at.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%H:%M"), "06:30")
        self.assertEqual(self.session.close_at.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%H:%M"), "13:00")
        self.assertEqual(parse_session(self.session.record()), self.session)

    def test_holiday_weekend_and_unknown_year(self):
        for day in ("2026-09-07", "2026-09-12", "2026-12-25"):
            s = exchange_session(day)
            self.assertEqual(s.phase_at(s.start), Phase.FAILED_CLOSED)
            with self.assertRaises(ValueError): session_authority(s, "unit-release", OWNERS, s.start)
        with self.assertRaises(ValueError): exchange_session("2027-01-04")

    def test_shortened_session(self):
        for day in ("2026-11-27", "2026-12-24"):
            s = exchange_session(day)
            self.assertEqual(s.status, "SHORTENED")
            self.assertEqual((s.close_at-s.open_at).total_seconds(), 12600)
            self.assertEqual(s.phase_at(s.close_at), Phase.POST_CLOSE_RECONCILIATION)

    def test_dst_uses_exchange_zone_not_host_zone(self):
        for day, hour in (("2026-03-06", 14), ("2026-03-09", 13), ("2026-10-30", 13), ("2026-11-02", 14)):
            self.assertEqual(exchange_session(day).open_at.hour, hour)
        with patch.dict("os.environ", {"TZ": "Pacific/Auckland"}):
            self.assertEqual(exchange_session("2026-09-10").identity, self.session.identity)

    def test_calendar_mutation_rejected(self):
        r = self.session.record(); r["close"] = self.session.open_at.isoformat()
        with self.assertRaises(ValueError): parse_session(seal(r))

    def test_max_24_hour_authority_and_exact_expiry(self):
        with self.assertRaises(ValueError): session_authority(self.session, "unit-release", OWNERS, self.session.shutdown_end-timedelta(hours=24, seconds=1))
        a = session_authority(self.session, "unit-release", OWNERS, self.session.shutdown_end-timedelta(hours=24))
        validate_session_authority(a, self.session, "unit-release", OWNERS, digest(a), self.session.start)
        with self.assertRaises(PermissionError): validate_session_authority(a, self.session, "unit-release", OWNERS, digest(a), self.session.shutdown_end)

    def test_resealed_authority_cannot_extend_independent_owner_pin(self):
        a = copy.deepcopy(self.authority)
        a["expires_at"] = (self.session.shutdown_end+timedelta(minutes=1)).isoformat()
        a = seal(a)
        with self.assertRaises(PermissionError): validate_session_authority(a, self.session, "unit-release", OWNERS, digest(self.authority), self.session.start)
        with self.assertRaises(PermissionError): validate_session_authority(a, self.session, "unit-release", OWNERS, digest(a), self.session.start)

    def test_all_capabilities_false_and_ungrantable(self):
        for name in self.authority["capabilities"]:
            a = copy.deepcopy(self.authority); a["capabilities"][name] = True; a = seal(a)
            with self.assertRaises(PermissionError): validate_session_authority(a, self.session, "unit-release", OWNERS, digest(a), self.session.start)

    def test_late_start_discloses_partial_and_missed_phases(self):
        self.life.tick(self.session.open_at+timedelta(hours=2), authority_current=True)
        self.assertIn("PARTIAL_OBSERVATION_LATE_START", self.life.state["incidents"])
        self.assertIn(Phase.OPENING_OBSERVATION, self.life.state["missed_phases"])
        self.assertEqual(self.life.state["capture_status"], "STALE")

    def test_clock_jump_no_backfill_and_backward_fail_closed(self):
        self.life.tick(self.session.start, authority_current=True)
        self.life.captured(self.session.start, "capture")
        self.life.tick(self.session.open_at+timedelta(hours=4), authority_current=True)
        self.assertIn("MISSED_REFRESH_NO_BACKFILL", self.life.state["incidents"])
        self.assertEqual(self.life.state["capture_status"], "STALE")
        self.life.tick(self.session.start, authority_current=True)
        self.assertEqual(self.life.state["phase"], Phase.FAILED_CLOSED)

    def test_failed_refresh_never_claims_older_capture_current(self):
        self.life.tick(self.session.start, authority_current=True)
        self.life.captured(self.session.start, "old")
        self.life.captured(self.session.start+timedelta(minutes=15), None)
        self.assertEqual(self.life.state["last_capture"], "old")
        self.assertEqual(self.life.state["capture_status"], "STALE")

    def test_expiry_stops_work_but_not_cleanup(self):
        self.life.tick(self.session.start, authority_current=False)
        with self.assertRaises(PermissionError): self.life.captured(self.session.start, "capture")
        self.life.shutdown(unresolved=False, listener_clear=True)
        self.assertEqual(self.life.state["phase"], Phase.SHUTDOWN_COMPLETE)
        self.assertEqual(self.life.state["session_result"], "FAILED_CLOSED")

    def test_restart_budget_persists_and_cooldown(self):
        self.life.tick(self.session.start, authority_current=True)
        self.life.reserve_restart("scheduler", self.session.start, authority_current=True)
        restored = Lifecycle(self.session, json.loads(canonical(self.life.state)))
        self.assertEqual(utc(restored.state["restart_after"]["scheduler"]), self.session.start+timedelta(seconds=60))
        restored.reserve_restart("scheduler", self.session.start, authority_current=True)
        self.assertIn("RESTART_BUDGET_EXHAUSTED", restored.state["incidents"])
        with self.assertRaises(ValueError): RestartPolicy(total=999).validate()

    def test_shutdown_interruption_and_no_false_session_success(self):
        self.life.shutdown(unresolved=True, listener_clear=False)
        self.assertEqual(self.life.state["phase"], Phase.FAILED_CLOSED)
        self.life.shutdown(unresolved=False, listener_clear=True)
        self.assertEqual(self.life.state["session_result"], "FAILED_CLOSED")

    def test_missing_post_close_reconciliation_fails(self):
        self.life.tick(self.session.reconcile_end, authority_current=True)
        self.assertEqual(self.life.state["phase"], Phase.FAILED_CLOSED)

    def test_complete_full_day_reducer_and_early_close(self):
        for day in ("2026-09-10", "2026-11-27"):
            s = exchange_session(day); life = Lifecycle(s); now = s.start; phases = set()
            while now <= s.reconcile_end:
                life.tick(now, authority_current=True); phases.add(life.state["phase"])
                if life.capture_due(now): life.captured(now, "unit-capture")
                if life.state["phase"] == Phase.POST_CLOSE_RECONCILIATION: life.reconciled()
                now += timedelta(minutes=5)
            self.assertTrue(set(CADENCE).issubset(phases))
            self.assertEqual(life.state["phase"], Phase.SESSION_COMPLETE)
            life.shutdown(unresolved=False, listener_clear=True)
            self.assertEqual(life.state["session_result"], "COMPLETE")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iios-sb36-unit-"); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base/"shadow"; self.root.mkdir(mode=0o700)
        self.inputs = []
        for kind in ("operational", "historical"):
            p = self.base/(kind+".db")
            with closing(sqlite3.connect(p)) as db, db:
                db.execute("CREATE TABLE ledger_objects (object_id TEXT,object_type TEXT,payload_json TEXT,created_at TEXT)")
                db.execute("INSERT INTO ledger_objects VALUES (?,?,?,?)", ("one", "case", '{"classification":"HISTORICAL"}', "2026-09-10T12:00:00Z"))
            p.chmod(0o600)
            self.inputs.append({"store": "unit:"+kind, "kind": kind, "path": str(p)})
        self.registry = registry_record(self.inputs)
        self.session = exchange_session("2026-09-10")
        self.clock = Clock(self.session.start)
        self.store = GenerationStore(self.root, self.session.identity, self.registry, self.registry["content_hash"])

    def capture(self): return self.store.capture(clock=self.clock)

    def test_consistent_immutable_captures_readonly_and_unique_ids(self):
        original = [Path(s["path"]).read_bytes() for s in self.inputs]
        a = self.capture(); self.clock.advance(900); b = self.capture()
        self.assertNotEqual(a["identity"], b["identity"])
        self.assertFalse(a["globally_simultaneous"])
        self.assertEqual(original, [Path(s["path"]).read_bytes() for s in self.inputs])
        self.assertEqual(self.store.watermark()["count"], 2)
        self.assertTrue(self.store.validate())
        for p in self.root.rglob("*"):
            self.assertEqual(p.stat().st_mode & 0o777, 0o700 if p.is_dir() else 0o600)

    def test_new_rows_only_across_restart(self):
        self.capture(); before = self.store.watermark()
        with closing(sqlite3.connect(self.inputs[0]["path"])) as db, db:
            db.execute("INSERT INTO ledger_objects VALUES ('two','case','{}','2026-09-10T12:15:00Z')")
        self.clock.advance(900); self.capture()
        restored = GenerationStore(self.root, self.session.identity, self.registry, self.registry["content_hash"])
        self.assertEqual(restored.watermark()["count"], before["count"]+1)
        restored.capture(clock=self.clock)
        self.assertEqual(restored.watermark()["count"], 3)

    def test_changed_same_identity_rejected_atomically(self):
        old = self.capture(); watermark = self.store.watermark()
        with closing(sqlite3.connect(self.inputs[0]["path"])) as db, db:
            db.execute("UPDATE ledger_objects SET payload_json='{}'")
        with self.assertRaisesRegex(ValueError, "SOURCE_IDENTITY_MUTATION"): self.capture()
        self.assertEqual(self.store.selected(), old)
        self.assertEqual(self.store.watermark(), watermark)
        self.assertTrue(self.store.validate())

    def test_interrupted_backup_preserves_prior_and_no_reuse(self):
        selected = self.capture()
        with patch.object(self.store, "_adapt", side_effect=OSError("unit")):
            with self.assertRaises(OSError): self.capture()
        self.assertEqual(self.store.selected(), selected)
        self.assertEqual(len(list(self.store.captures.iterdir())), 2)
        self.capture(); self.assertEqual(len(list(self.store.captures.iterdir())), 3)

    def test_interruption_before_atomic_selection_retains_complete_capture(self):
        old = self.capture()
        real = self.store.connect
        def fail_selection(*, readonly=False):
            if not readonly: raise OSError("unit interruption")
            return real(readonly=True)
        with patch.object(self.store, "connect", side_effect=fail_selection):
            with self.assertRaises(OSError): self.capture()
        self.assertEqual(self.store.selected(), old)
        self.assertTrue(self.store.validate())

    def test_hash_tamper_detected(self):
        a = self.capture()
        p = self.store.captures/a["identity"] / "0.db"
        with p.open("ab") as f: f.write(b"tamper")
        with self.assertRaises(ValueError): self.store.validate()

    def test_cached_hash_rechecks_same_size_and_restored_mtime(self):
        a = self.capture(); self.store.validate()
        path = self.store.captures/a["identity"]/"0.db"; before = path.stat()
        data = path.read_bytes(); path.write_bytes(b"X"+data[1:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(ValueError): self.store.validate()

    def test_resealed_capture_schema_cannot_replace_snapshot_proof(self):
        from truth_spine_integration import atomic
        a = self.capture(); self.store.validate()
        a["files"][0]["schema"] = "0"*64; a = seal(a)
        atomic(self.store.captures/a["identity"]/"manifest.json", a)
        with closing(self.store.connect()) as db, db:
            db.execute("DROP TRIGGER capture_no_update")
            db.execute("UPDATE captures SET payload=?", (canonical(a).decode(),))
        with self.assertRaisesRegex(ValueError, "CAPTURE_SCHEMA_OR_INTERVAL_INVALID"): self.store.validate()

    def test_symlink_and_wrong_mode_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError): GenerationStore(self.root, self.session.identity, self.registry, self.registry["content_hash"])
        self.root.chmod(0o700)
        p = Path(self.inputs[0]["path"]); alias = self.base/"alias.db"; alias.symlink_to(p)
        inputs = copy.deepcopy(self.inputs); inputs[0]["path"] = str(alias)
        with self.assertRaises(ValueError): registry_record(inputs)

    def test_cross_session_and_registry_rejected(self):
        with self.assertRaises(ValueError): GenerationStore(self.root, "other", self.registry, self.registry["content_hash"])
        with self.assertRaises(ValueError): GenerationStore(self.root, self.session.identity, self.registry, "wrong")

    def test_checkpoint_hash_chain_and_rollback_copy(self):
        self.capture()
        self.store.record("CHECKPOINT", {"unit": "one"}, self.clock())
        self.store.record("CHECKPOINT", {"unit": "two"}, self.clock())
        entries = self.store.entries()
        self.assertEqual(entries[1]["parent"], entries[0]["content_hash"])
        original = self.store.path.read_bytes()
        restored = self.base/"isolated-rollback.db"; immutable_file(restored, original)
        self.assertEqual(hashlib.sha256(original).hexdigest(), hashlib.sha256(restored.read_bytes()).hexdigest())


@dataclass
class FakeFingerprint:
    role: str
    startup_receipt_hash: str = "unit-startup-receipt"


class FakeChild:
    def __init__(self): self.exited = False
    def poll(self): return 1 if self.exited else None


class FakeChildren:
    def __init__(self): self.active = {}; self.starts = []; self.stops = []
    def start(self, role):
        if role in self.active: raise ValueError("DUPLICATE_OWNER")
        self.active[role] = {"role": role, "child": FakeChild(), "fingerprint": FakeFingerprint(role)}
        self.starts.append(role)
    def verify(self, entry): return entry["fingerprint"]
    def stop(self, role): self.stops.append(role); del self.active[role]; return True
    def cleanup(self, report):
        for role in reversed(list(self.active)): self.stop(role)
        report.update(port_clear=True, cleanup_errors=[])


class SupervisorTests(StoreTests):
    def setUp(self):
        super().setUp()
        self.children = FakeChildren()
        self.authority = session_authority(self.session, "unit-release", OWNERS, self.session.start)
        self.probe_modifier = lambda p: p
        self.supervisor = SessionSupervisor(session=self.session, store=self.store, children=self.children,
            authority=self.authority, approved_authority_hash=digest(self.authority), release="unit-release",
            owners=OWNERS, topology_hash="a"*64, start_child=self.children.start, probe_runtime=self.probes, clock=self.clock)

    def probes(self, now, generation, watermark):
        # Simulation only. These are NOT runtime evidence or an installed acceptance.
        probes = {k: seal({"schema": "iios-shadow-runtime-probe-v1", "kind": k,
                          "session": self.session.identity, "release": "unit-release",
                          "generation": generation["content_hash"], "watermark": watermark,
                          "observed_at": now.isoformat(), "expires_at": (now+timedelta(seconds=30)).isoformat(),
                          "evidence_hash": "0"*64}) for k in REQUIRED_PROBES}
        return self.probe_modifier(probes)

    def ready(self, kind="ready", probes=None):
        return health(kind, lifecycle=self.supervisor.lifecycle.state, session=self.session,
                      authority=self.authority, authority_hash=digest(self.authority), release="unit-release",
                      owners=OWNERS, generation=self.store.selected(), watermark=self.store.watermark(),
                      probes=probes if probes is not None else self.probes(self.clock(), self.store.selected(), self.store.watermark()), now=self.clock())

    def test_simulated_full_session_capture_and_checkpoint_lifecycle(self):
        while self.clock() <= self.session.reconcile_end:
            self.supervisor.cycle()
            self.clock.advance(300)
        self.assertEqual(self.supervisor.lifecycle.state["phase"], Phase.SHUTDOWN_COMPLETE)
        self.assertEqual(self.supervisor.lifecycle.state["session_result"], "COMPLETE")
        self.assertEqual(self.store.watermark()["count"], 2)
        checkpoints = [r["value"]["name"] for r in self.store.entries() if r["kind"] == "CHECKPOINT"]
        for name in ("startup", "pre-market ready", "market open", "before close", "market close", "post-close reconciliation", "final shutdown"):
            self.assertIn(name, checkpoints)
        self.assertEqual(self.children.stops[-3:], ["backend", "publisher", "scheduler"])

    def test_dead_children_restart_once_cooldown_then_exhaustion(self):
        for role in ("scheduler", "publisher", "backend"):
            with self.subTest(role=role):
                # Each role is independent within the shared three-restart budget.
                if not self.supervisor.started: self.supervisor.cycle()
                self.children.active[role]["child"].exited = True
                self.supervisor.cycle()
                self.assertNotIn(role, self.children.active)
                self.clock.advance(59); self.supervisor.cycle()
                self.assertNotIn(role, self.children.active)
                self.clock.advance(1); self.supervisor.cycle()
                self.assertIn(role, self.children.active)
        self.children.active["scheduler"]["child"].exited = True
        self.supervisor.cycle()
        self.assertEqual(self.supervisor.lifecycle.state["session_result"], "FAILED_CLOSED")

    def test_every_missing_or_stale_probe_fails_readiness(self):
        self.supervisor.cycle()
        self.assertEqual(self.ready()[0], 200)
        self.assertEqual(self.ready("market-readiness")[0], 503)
        self.assertEqual(self.ready("research-readiness")[1]["status"], "SHADOW_OBSERVATION_READY")
        for name in REQUIRED_PROBES:
            p = self.probes(self.clock(), self.store.selected(), self.store.watermark())
            del p[name]
            self.assertEqual(self.ready(probes=p)[0], 503)
            p = self.probes(self.clock(), self.store.selected(), self.store.watermark())
            p[name]["observed_at"] = (self.clock()-timedelta(seconds=120)).isoformat()
            p[name] = seal(p[name])
            self.assertEqual(self.ready(probes=p)[0], 503)

    def test_wrong_generation_and_fresh_wrapper_stale_source(self):
        self.supervisor.cycle()
        p = self.probes(self.clock(), self.store.selected(), self.store.watermark())
        p["projection"]["generation"] = "wrong"; p["projection"] = seal(p["projection"])
        self.assertEqual(self.ready(probes=p)[0], 503)
        self.clock.advance(1200)
        self.assertEqual(self.ready()[0], 503)

    def test_authority_expiry_cleans_all_no_restart(self):
        self.supervisor.cycle(); starts = list(self.children.starts)
        self.clock.at = self.session.shutdown_end
        self.supervisor.cycle()
        self.assertFalse(self.children.active)
        self.assertEqual(starts, self.children.starts)

    def test_post_close_failure_is_not_success(self):
        self.supervisor.cycle()
        self.clock.at = self.session.close_at
        self.probe_modifier = lambda p: {}
        self.assertEqual(self.supervisor.cycle()["ready"], 503)
        self.assertFalse(self.supervisor.lifecycle.state["post_close_reconciled"])
        self.clock.at = self.session.reconcile_end
        self.supervisor.cycle()
        self.assertEqual(self.supervisor.lifecycle.state["session_result"], "FAILED_CLOSED")
        self.assertFalse(self.children.active)

    def test_persistence_failure_still_cleans_children(self):
        self.supervisor.cycle()
        with patch.object(self.store, "record", side_effect=OSError("unit full disk")):
            with self.assertRaises(OSError): self.supervisor.cycle()
        self.assertFalse(self.children.active)

    def test_restart_reservation_survives_parent_reconstruction(self):
        self.supervisor.cycle(); self.children.active["scheduler"]["child"].exited = True
        self.supervisor.cycle(); self.clock.advance(60)
        restored = SessionSupervisor(session=self.session, store=self.store, children=self.children,
            authority=self.authority, approved_authority_hash=digest(self.authority), release="unit-release",
            owners=OWNERS, topology_hash="a"*64, start_child=self.children.start, probe_runtime=self.probes, clock=self.clock)
        restored.cycle()
        self.assertEqual(restored.lifecycle.state["restart_counts"]["scheduler"], 1)
        self.assertEqual(self.children.starts.count("scheduler"), 2)
        self.assertEqual(self.store.watermark()["count"], 2)

    def test_browser_contains_only_qualified_metadata(self):
        self.supervisor.cycle()
        b = browser_contract(self.supervisor.lifecycle.state, self.store.selected(), self.store.watermark(), 200, {})
        self.assertEqual(b["narrative_classification"], "NARRATIVE")
        self.assertTrue(all(v is False for v in b["capabilities"].values()))
        self.assertNotIn("payload", canonical(b).decode())


class ProductionPathTests(unittest.TestCase):
    """Real filesystem/publisher/reader code; only OS children and time are fake.

    The tiny package is explicitly a unit fixture, not an accepted installed
    Python runtime or a full-day rehearsal. No network/child is started here.
    """
    def setUp(self):
        StoreTests.setUp(self)
        self.root = self.base/"full-session"; self.root.mkdir(mode=0o700)
        self.cycle_path = self.base/"cycle.json"
        self.write_cycle()
        self.inputs.append({"store": "unit:cycle", "kind": "source_cycle", "path": str(self.cycle_path)})
        self.registry = registry_record(self.inputs)
        self.store = GenerationStore(self.root, self.session.identity, self.registry, self.registry["content_hash"])
        for directory in ("release", "release/backend", "release/frontend", "runtime", "runtime/bin", "projections"):
            (self.root/directory).mkdir(mode=0o700)
        files = []
        def artifact(name, raw, mode=0o400):
            path = self.root/name; immutable_file(path, raw); path.chmod(mode)
            row = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "mode": f"{mode:04o}"}
            files.append(row); return row
        from truth_spine_session_package import BACKEND_FILES
        for name in BACKEND_FILES:
            artifact("release/backend/"+name, b"# UNIT FIXTURE ONLY\n")
        for directory in ("release/frontend/assets", "release/frontend/fixtures"):
            (self.root/directory).mkdir(mode=0o700)
        frontend = {
            "assets/truth-integration-unit.js": "/* UNIT FIXTURE ONLY */",
            "assets/truth-integration-unit.css": "main{display:block}",
            "truth-integration.html": '<script src="/review/assets/truth-integration-unit.js"></script><link href="/review/assets/truth-integration-unit.css">',
            "favicon.svg": "<svg/>", "icons.svg": "<svg/>", "fixtures/expansion-wing.json": "{}"}
        for name, value in sorted(frontend.items()): artifact("release/frontend/"+name, value.encode())
        exe = artifact("runtime/bin/python", b"UNIT NOT EXECUTABLE", 0o500)
        runtime = seal({"runtime_id": "unit-runtime", "interpreter_sha256": exe["sha256"],
            "file_inventory": [{"path": "bin/python", "size": exe["bytes"], "sha256": exe["sha256"], "mode": 0o500}],
            "platform_dependencies": []})
        artifact("runtime/runtime-manifest.json", canonical(runtime))
        inputs = {"source_commit": "a"*40, "source_inventory": [], "source_inventory_hash": hashlib.sha256(canonical([])).hexdigest(),
                  "policy": {"mode": "production", "environment": {"VITE_TRUTH_INTEGRATION_PREVIEW": "1"}, "sourcemap": False},
                  "toolchain": {"versions": {"vite": "8.2.2"}}}
        outputs = [{"path": f["path"].removeprefix("release/frontend/"), "bytes": f["bytes"], "sha256": f["sha256"]}
                   for f in files if f["path"].startswith("release/frontend/")]
        provenance = seal({"schema": "iios-truth-frontend-build-v1", "inputs": inputs,
                          "input_hash": digest(inputs), "outputs": outputs, "output_hash": hashlib.sha256(canonical(outputs)).hexdigest()})
        self.authority = session_authority(self.session, "unit-release", OWNERS, self.session.start)
        self.manifest = seal({"schema": "iios-full-day-shadow-package-v1", "release": "unit-release", "source_commit": "a"*40,
            "runtime_identity": "unit-runtime", "frontend_provenance": provenance, "session": self.session.identity,
            "authority_hash": digest(self.authority), "source_registry_hash": digest(self.registry), "files": files})
        selector = seal({"schema": "iios-shadow-session-selector-v1", "session": self.session.identity,
                         "session_file": "session.json", "registry_hash": digest(self.registry)})
        self.config = seal({"schema": "iios-full-day-shadow-topology-v1", "root": str(self.root), "host": "127.0.0.1", "port": 5291,
            "manifest_hash": digest(self.manifest), "session_hash": digest(self.session.record()), "authority_hash": digest(self.authority),
            "registry_hash": digest(self.registry), "selector_hash": digest(selector), "owners": OWNERS})
        for name, value in {"topology.json": self.config, "session.json": self.session.record(), "authority.json": self.authority,
                            "release-manifest.json": self.manifest, "sources.json": self.registry, "session-selector.json": selector}.items():
            immutable_file(self.root/name, canonical(value))
        self.children = FakeChildren()
        from truth_spine_session_package import RuntimeProbeReader
        self.reader = RuntimeProbeReader(root=self.root, manifest=self.manifest, manifest_pin=digest(self.manifest),
                                         children=self.children, session=self.session, store=self.store)
        self.publish_enabled = True
        self.supervisor = SessionSupervisor(session=self.session, store=self.store, children=self.children,
            authority=self.authority, approved_authority_hash=digest(self.authority), release="unit-release", owners=OWNERS,
            topology_hash=digest(self.config), start_child=self.children.start, probe_runtime=self.actual_probes, clock=self.clock)

    def write_cycle(self):
        from truth_spine_integration import atomic
        atomic(self.cycle_path, seal({"schema_version": "iios-multi-asset-projection-manifest-v1",
            "source_cycle_id": "unit-source-cycle", "generated_at": self.clock().isoformat()}))

    def actual_probes(self, now, generation, watermark):
        from truth_spine_full_day_service import publish_once
        from truth_spine_integration import atomic
        if self.publish_enabled:
            publish_once(self.root, self.session, self.manifest, self.registry, now)
        for role in ("scheduler", "publisher"):
            if role in self.children.active:
                atomic(self.root/(role+"-session-heartbeat.json"), seal({"session": self.session.identity, "role": role,
                    "release": "unit-release", "generation": generation["content_hash"], "startup_receipt_hash": "unit-startup-receipt",
                    "at": now.isoformat(), "next_wake": self.supervisor.lifecycle.state["next_capture"]}))
        probes = self.reader.collect(now, generation, watermark)
        atomic(self.root/"runtime-probes.json", seal({"probes": probes, "at": now.isoformat()}))
        return probes

    def test_real_publisher_reader_and_http_contract(self):
        from truth_spine_full_day_service import service_response
        self.assertEqual(self.supervisor.cycle()["ready"], 200)
        for route, code in (("live", 200), ("ready", 200), ("market-readiness", 503), ("research-readiness", 200)):
            self.assertEqual(service_response(self.root/"topology.json", "/health/"+route, now=self.clock())[0], code)
        code, view = service_response(self.root/"topology.json", "/truth-spine/full-session", now=self.clock())
        self.assertEqual(code, 200); self.assertEqual(view["readiness"], 200)
        self.assertEqual(view["watermark"]["count"], 2)
        self.assertTrue(all(v is False for v in view["capabilities"].values()))
        self.assertEqual(service_response(self.root/"topology.json", "/activate", now=self.clock())[0], 404)

    def test_full_day_actual_publisher_with_post_close_race(self):
        original = [Path(s["path"]).read_bytes() for s in self.inputs[:2]]
        while self.clock() < self.session.close_at:
            self.write_cycle(); self.assertEqual(self.supervisor.cycle()["ready"], 200)
            self.clock.advance(300)
        self.publish_enabled = False; self.write_cycle()
        self.assertEqual(self.supervisor.cycle()["ready"], 503)
        self.assertFalse(self.supervisor.lifecycle.state["post_close_reconciled"])
        self.clock.advance(5); self.publish_enabled = True
        self.assertEqual(self.supervisor.cycle()["ready"], 200)
        self.assertTrue(self.supervisor.lifecycle.state["post_close_reconciled"])
        while self.clock() < self.session.reconcile_end:
            self.write_cycle(); self.supervisor.cycle(); self.clock.advance(5)
        self.supervisor.cycle()
        self.assertEqual(self.supervisor.lifecycle.state["session_result"], "COMPLETE")
        self.assertEqual(original, [Path(s["path"]).read_bytes() for s in self.inputs[:2]])
        self.assertEqual(self.store.watermark()["count"], 2)
        self.assertFalse(self.children.active)

    def test_new_capture_issues_independent_cycle_not_fresh_permanent_evidence(self):
        original = self.cycle_path.read_bytes()
        self.supervisor.cycle(); self.clock.advance(901)
        self.assertEqual(self.supervisor.cycle()["ready"], 200)
        self.assertEqual(self.supervisor.lifecycle.state["capture_status"], "CURRENT")
        self.assertEqual(original, self.cycle_path.read_bytes())
        self.assertNotEqual(json.loads(original)["source_cycle_id"],
                            json.loads((self.root/"projections/current.json").read_bytes())["source_cycle"])

    def test_manually_resealed_projection_generation_is_rejected(self):
        from truth_spine_integration import atomic
        self.supervisor.cycle(); path = self.root/"projections/current.json"
        p = json.loads(path.read_bytes()); p["generation"] = "0"*64; atomic(path, seal(p))
        with self.assertRaisesRegex(ValueError, "SESSION_PROJECTION_NOT_DERIVED"):
            self.reader.collect(self.clock(), self.store.selected(), self.store.watermark())

    def test_all_heartbeat_binding_mutations_rejected(self):
        from truth_spine_integration import atomic
        self.supervisor.cycle(); path = self.root/"scheduler-session-heartbeat.json"; original = json.loads(path.read_bytes())
        for key in ("session", "release", "generation", "role", "startup_receipt_hash"):
            atomic(path, seal({**original, key: "wrong"}))
            with self.assertRaisesRegex(ValueError, "SESSION_HEARTBEAT_INVALID"):
                self.reader.collect(self.clock(), self.store.selected(), self.store.watermark())
        atomic(path, original)
        self.clock.advance(31)
        with self.assertRaisesRegex(ValueError, "SESSION_HEARTBEAT_INVALID"):
            self.reader.collect(self.clock(), self.store.selected(), self.store.watermark())

    def test_package_pin_unknown_file_runtime_and_frontend_tamper(self):
        from truth_spine_session_package import verify_artifacts
        verify_artifacts(self.root, self.manifest, digest(self.manifest))
        for key in ("runtime_identity", "source_commit"):
            changed = seal({**self.manifest, key: "b"*40})
            with self.assertRaises(ValueError): verify_artifacts(self.root, changed, digest(changed))
        immutable_file(self.root/"release/unknown", b"unknown")
        with self.assertRaisesRegex(ValueError, "INVENTORY_MISMATCH"):
            verify_artifacts(self.root, self.manifest, digest(self.manifest))

    def test_package_top_level_directory_permissions_are_checked(self):
        from truth_spine_session_package import verify_artifacts
        (self.root/"runtime").chmod(0o755)
        with self.assertRaisesRegex(ValueError, "SHADOW_OWNER_MODE_INVALID"):
            verify_artifacts(self.root, self.manifest, digest(self.manifest))

    def test_resealed_frontend_cannot_hide_unmanifested_html_reference(self):
        from truth_spine_session_package import verify_artifacts
        path = self.root/"release/frontend/truth-integration.html"
        path.chmod(0o600); path.write_bytes(b'<script src="/review/assets/unapproved.js"></script>'); path.chmod(0o400)
        changed = copy.deepcopy(self.manifest)
        for row in changed["files"]:
            if row["path"] == "release/frontend/truth-integration.html":
                row.update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        provenance = changed["frontend_provenance"]
        provenance["outputs"] = [{"path": r["path"].removeprefix("release/frontend/"), "bytes": r["bytes"], "sha256": r["sha256"]}
                                 for r in changed["files"] if r["path"].startswith("release/frontend/")]
        provenance["output_hash"] = hashlib.sha256(canonical(provenance["outputs"])).hexdigest()
        changed["frontend_provenance"] = seal(provenance); changed = seal(changed)
        with self.assertRaisesRegex(ValueError, "SESSION_FRONTEND_GRAPH_INVALID"):
            verify_artifacts(self.root, changed, digest(changed))

    def test_expiration_browser_remains_unavailable_not_current(self):
        from truth_spine_full_day_service import service_response
        self.supervisor.cycle(); self.clock.at = self.session.shutdown_end; self.supervisor.cycle()
        code, view = service_response(self.root/"topology.json", "/truth-spine/full-session", now=self.clock())
        self.assertEqual(code, 200); self.assertEqual(view["readiness"], 503)
        self.assertEqual(view["phase"], "SHUTDOWN_COMPLETE")
        self.assertEqual(service_response(self.root/"topology.json", "/health/ready", now=self.clock())[0], 503)

    def test_readonly_reader_and_capture_permission_boundary(self):
        self.supervisor.cycle(); before = self.store.path.read_bytes()
        reader = GenerationStore(self.root, self.session.identity, self.registry, digest(self.registry), readonly=True)
        reader.validate(); reader.entries()
        self.assertEqual(before, self.store.path.read_bytes())
        with self.assertRaises(PermissionError): reader.record("INCIDENT", {}, self.clock())
        def denied(): raise PermissionError("UNIT_EXPIRED")
        with self.assertRaises(PermissionError): self.store.capture(clock=self.clock, permit=denied)
        self.assertEqual(before, self.store.path.read_bytes())

    def test_template_and_pure_deployment_documents_no_creation(self):
        from truth_spine_session_package import deployment_documents, installation_template, capacity_budget
        path = Path(__file__).resolve().parents[2]/"config/truth-spine-full-day-shadow.json.template"
        self.assertEqual(json.loads(path.read_bytes()), installation_template())
        proposed = Path("/private/tmp/iios-truth-spine-full-day-unit-never-created")
        before = proposed.exists()
        docs = deployment_documents(proposed, self.session, self.manifest, self.registry, self.authority, OWNERS)
        self.assertEqual(proposed.exists(), before)
        self.assertEqual(docs["topology.json"]["selector_hash"], digest(docs["session-selector.json"]))
        self.assertEqual(docs["topology.json"]["port"], 5291)
        self.assertGreater(capacity_budget(self.session, self.registry)["required_free_bytes"], 64*1024*1024)
        with self.assertRaises(ValueError):
            deployment_documents(Path("/"), self.session, self.manifest, self.registry, self.authority, OWNERS)

    def test_runner_clock_and_package_local_entry_contract(self):
        source = (Path(__file__).resolve().parents[2]/"scripts/truth_spine_full_day_runner.py").read_text()
        self.assertIn("INSTALLED_PACKAGE_RUNNER_REQUIRED", source)
        self.assertIn("time.monotonic() >= until", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("--clock", source)
        self.assertNotIn("launchctl", source)
        self.assertIn("service_module='truth_spine_full_day_service'", source)


if __name__ == "__main__": unittest.main()
