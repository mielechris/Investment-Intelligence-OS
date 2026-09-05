from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from expansion_wing.acceptance_server import Compositor
from expansion_wing.projection_runtime import (
    FixedProjectionReader, INVENTORY, MANIFEST_NAME, PROJECTION_NAME, ProjectionStore,
    ROOT_IDENTIFIER, ROLLBACK_NAME, compose_from_sanitized_snapshot,
)
from expansion_wing.tuesday_rehearsal import rehearsal_projection

UTC = timezone.utc
NOW = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)


class Calendar:
    def holiday_status(self, _day): return False


def projection(at=NOW):
    return rehearsal_projection(at, Calendar(), scenario="regular_zero_candidates")


def sanitized_snapshot(*, lineage="UNAVAILABLE", candidates=None):
    candidates = [] if candidates is None else candidates
    return {"schema_version": "expansion-wing-truth-v1", "mode": "READ_ONLY",
        "sections": {
            "books": {"state": "CURRENT", "data": {"nav": 10_000, "cash": 10_000, "positions": 0,
                "transactions": 0, "orders": 0, "fills": 0}},
            "radar": {"state": "CURRENT", "data": {"candidate_source_cycle_id": "cycle_15nr" if lineage != "UNAVAILABLE" else None,
                "candidate_source_artifact_hash": "a" * 64 if lineage != "UNAVAILABLE" else None}},
            "candidate_conveyor": {"state": lineage, "data": {"candidates": candidates}},
        }, "authority": {"credential_access": False, "ledger_write_authority": False,
            "broker_connectivity": False, "live_execution_authority": False}}


def rewrite_projection(root: Path, mutate) -> None:
    value = json.loads((root / PROJECTION_NAME).read_bytes()); mutate(value)
    unhashed = {key: item for key, item in value.items() if key != "projection_hash"}
    value["projection_hash"] = hashlib.sha256(json.dumps(unhashed, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    manifest = json.loads((root / MANIFEST_NAME).read_bytes())
    manifest["projection_sha256"] = hashlib.sha256(encoded).hexdigest()
    manifest["projection_size_bytes"] = len(encoded)
    (root / PROJECTION_NAME).write_bytes(encoded); (root / PROJECTION_NAME).chmod(0o600)
    (root / MANIFEST_NAME).write_bytes(json.dumps(manifest, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("ascii")); (root / MANIFEST_NAME).chmod(0o600)


class ProjectionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.parent = Path(self.temporary.name)
        self.parent.chmod(0o700)
        self.root = self.parent / "projection"
        self.store = ProjectionStore(self.root)
        self.store.create_with_rollback(generated_at=NOW.isoformat())

    def tearDown(self): self.temporary.cleanup()

    def test_owner_only_inventory_atomic_publish_and_manifest(self):
        result = self.store.publish(projection(), now=NOW)
        self.assertTrue(result.changed); self.assertEqual(result.sequence, 1)
        self.assertEqual({item.name for item in self.root.iterdir()}, INVENTORY)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        for name in INVENTORY: self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o600)
        value, manifest = self.store.read(now=NOW)
        self.assertEqual(value["projection_hash"], projection()["projection_hash"])
        self.assertEqual(manifest["root_identifier"], ROOT_IDENTIFIER)
        self.assertEqual(manifest["projection_sha256"], result.projection_sha256)
        self.assertFalse(any(item.name.startswith(".") for item in self.root.iterdir()))

    def test_identical_publication_is_idempotent_and_change_is_monotonic(self):
        first = self.store.publish(projection(), now=NOW); before = (self.root / PROJECTION_NAME).stat().st_mtime_ns
        second = self.store.publish(projection(), now=NOW)
        self.assertFalse(second.changed); self.assertEqual((first.sequence, second.sequence), (1, 1))
        self.assertEqual(before, (self.root / PROJECTION_NAME).stat().st_mtime_ns)
        changed = projection(); changed["projection_generated_at"] = (NOW + timedelta(seconds=1)).isoformat()
        changed["source_generated_at"] = changed["projection_generated_at"]
        import hashlib
        encoded = json.dumps({k:v for k,v in changed.items() if k != "projection_hash"}, sort_keys=True,
                             separators=(",", ":"), ensure_ascii=True).encode("ascii")
        changed["projection_hash"] = hashlib.sha256(encoded).hexdigest()
        third = self.store.publish(changed, now=NOW + timedelta(seconds=1)); self.assertEqual(third.sequence, 2)

    def test_symlink_special_mode_unknown_inventory_hash_and_future_rejected(self):
        self.store.publish(projection(), now=NOW)
        (self.root / "unexpected").write_text("x")
        with self.assertRaisesRegex(RuntimeError, "INVENTORY"): self.store.read(now=NOW)
        (self.root / "unexpected").unlink()
        (self.root / PROJECTION_NAME).chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "UNSAFE"): self.store.read(now=NOW)
        (self.root / PROJECTION_NAME).chmod(0o600)
        (self.root / PROJECTION_NAME).unlink(); (self.root / PROJECTION_NAME).symlink_to(self.root / MANIFEST_NAME)
        with self.assertRaisesRegex(RuntimeError, "UNSAFE"): self.store.read(now=NOW)

    def test_reader_disabled_default_and_status_is_browser_safe(self):
        self.store.publish(projection(), now=NOW)
        disabled = FixedProjectionReader(root=self.root)
        with self.assertRaisesRegex(RuntimeError, "DISABLED"): disabled.read()
        self.assertEqual(disabled.status()["reader_state"], "DISABLED")
        enabled = FixedProjectionReader(root=self.root, enabled=True, validation_clock=NOW)
        self.assertEqual(enabled.status()["hash_validation"], "VALID")
        self.assertEqual(enabled.status()["reader_state"], "ACTIVE")
        self.assertEqual(enabled.status()["integrity_state"], "VALID")
        self.assertTrue(enabled.status()["evidence_current"])
        encoded = json.dumps(enabled.status())
        self.assertNotIn(str(self.root), encoded); self.assertNotIn("credential", encoded.lower())
        stale = FixedProjectionReader(root=self.root, enabled=True, validation_clock=NOW + timedelta(seconds=901))
        before = {name: (self.root / name).read_bytes() for name in INVENTORY}
        stale_value = stale.read(); stale_status = stale.status()
        self.assertEqual((stale_status["reader_state"], stale_status["integrity_state"]), ("ACTIVE", "VALID"))
        self.assertEqual((stale_status["hash_validation"], stale_status["freshness_state"]), ("VALID", "STALE"))
        self.assertEqual(stale_status["publisher_state"], "UNAVAILABLE")
        self.assertFalse(stale_status["evidence_current"])
        self.assertEqual(stale_value["candidate_conveyor"], {"state": "UNAVAILABLE", "candidates": []})
        self.assertTrue(all(lane["state"] == "STALE" and lane["freshness"] == "STALE" and
            lane["candidate_count"] is None and not lane["research_eligible"] and not lane["paper_eligible"]
            for lane in stale_value["lane_states"].values()))
        self.assertEqual(stale_value["professional_observatory"]["state"], "UNAVAILABLE")
        self.assertIsNone(stale_value["professional_observatory"]["observation_count"])
        self.assertFalse(any(stale_value["authority"].values()))
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in INVENTORY})

    def test_projection_age_boundary_and_immediately_stale(self):
        self.store.publish(projection(), now=NOW)
        boundary = FixedProjectionReader(root=self.root, enabled=True,
            validation_clock=NOW + timedelta(seconds=900))
        self.assertEqual(boundary.status()["freshness_state"], "CURRENT")
        self.assertTrue(boundary.status()["evidence_current"])
        above = FixedProjectionReader(root=self.root, enabled=True,
            validation_clock=NOW + timedelta(seconds=900, microseconds=1))
        self.assertEqual(above.status()["freshness_state"], "STALE")
        self.assertFalse(above.status()["evidence_current"])

    def test_invalid_integrity_remains_failed_closed(self):
        self.store.publish(projection(), now=NOW)
        raw = bytearray((self.root / PROJECTION_NAME).read_bytes()); raw[-2] ^= 1
        (self.root / PROJECTION_NAME).write_bytes(raw); (self.root / PROJECTION_NAME).chmod(0o600)
        reader = FixedProjectionReader(root=self.root, enabled=True, validation_clock=NOW)
        self.assertEqual(reader.status()["reader_state"], "FAILED_CLOSED")
        self.assertEqual(reader.status()["integrity_state"], "INVALID")
        with self.assertRaises(RuntimeError): reader.read()

    def test_future_invalid_schema_and_missing_timestamp_remain_failed_closed(self):
        mutations = (
            lambda value: value.update(projection_generated_at=(NOW + timedelta(seconds=1)).isoformat()),
            lambda value: value.update(schema_version="unknown-projection-v0"),
            lambda value: value.pop("projection_generated_at"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.tearDown(); self.setUp(); self.store.publish(projection(), now=NOW)
                rewrite_projection(self.root, mutate)
                reader = FixedProjectionReader(root=self.root, enabled=True, validation_clock=NOW)
                self.assertEqual(reader.status()["reader_state"], "FAILED_CLOSED")
                self.assertEqual(reader.status()["integrity_state"], "INVALID")

    def test_rollback_manifest_precedes_projection_and_unknown_root_is_preserved(self):
        other = self.parent / "other"; other.mkdir(mode=0o700); (other / "unknown").write_text("keep")
        with self.assertRaisesRegex(RuntimeError, "INVENTORY"):
            ProjectionStore(other).create_with_rollback(generated_at=NOW.isoformat())
        self.assertEqual((other / "unknown").read_text(), "keep")
        self.assertTrue((self.root / ROLLBACK_NAME).is_file())
        self.assertFalse((self.root / PROJECTION_NAME).exists())


class PublisherAndIntegrationTests(unittest.TestCase):
    def test_partial_current_projection_preserves_unknown_and_zero_distinctions(self):
        value = compose_from_sanitized_snapshot(sanitized_snapshot(), generated_at=NOW.isoformat(),
                                                market_session_state="POST_MARKET")
        self.assertEqual(value["candidate_conveyor"], {"state": "UNAVAILABLE", "candidates": []})
        self.assertTrue(all(lane["candidate_count"] is None for lane in value["lane_states"].values()))
        self.assertEqual(value["paper_research_sleeves"]["state"], "AVAILABLE_EMPTY")
        self.assertEqual(value["paper_research_sleeves"]["operational_position_count"], 0)
        self.assertIsNone(value["provider"]["confirmed_credits"])

    def test_immutable_candidate_lineage_is_bounded_and_failed_cycle_does_not_carry(self):
        row = {"candidate_id": "candidate_0123456789abcdef", "ticker": "MU",
               "discovered_at": "2026-09-08T19:59:00+00:00", "missing_fields": ["company_profile"]}
        rows = [{**row, "candidate_id": f"candidate_{index:016x}"} for index in range(5)]
        value = compose_from_sanitized_snapshot(sanitized_snapshot(lineage="CURRENT", candidates=rows),
            generated_at=NOW.isoformat(), market_session_state="POST_MARKET")
        self.assertEqual(len(value["candidate_conveyor"]["candidates"]), 5)
        self.assertTrue(all(item["source_cycle_id"] == "cycle_15nr" for item in value["candidate_conveyor"]["candidates"]))
        failed = sanitized_snapshot(lineage="FAILED_CLOSED", candidates=[row])
        value = compose_from_sanitized_snapshot(failed, generated_at=NOW.isoformat(), market_session_state="POST_MARKET")
        self.assertEqual(value["candidate_conveyor"], {"state": "UNAVAILABLE", "candidates": []})

    def test_professional_observations_and_research_sleeves_have_no_promotion_or_position_authority(self):
        value = compose_from_sanitized_snapshot(sanitized_snapshot(), generated_at=NOW.isoformat(),
                                                market_session_state="POST_MARKET")
        self.assertFalse(value["professional_observatory"]["endorsement"])
        self.assertFalse(value["paper_research_sleeves"]["paper_authority"])
        self.assertEqual(value["paper_research_sleeves"]["operational_position_count"], 0)
        self.assertFalse(any(value["authority"].values()))

    def test_bad_paper_baseline_and_candidate_shape_fail_closed(self):
        bad = sanitized_snapshot(); bad["sections"]["books"]["data"]["positions"] = None
        with self.assertRaisesRegex(ValueError, "PAPER_BASELINE"):
            compose_from_sanitized_snapshot(bad, generated_at=NOW.isoformat(), market_session_state="POST_MARKET")
        bad = sanitized_snapshot(lineage="CURRENT", candidates=[{"private": "evidence"}])
        with self.assertRaisesRegex(ValueError, "CANDIDATE_SOURCE"):
            compose_from_sanitized_snapshot(bad, generated_at=NOW.isoformat(), market_session_state="POST_MARKET")

    def test_compositor_exposes_sanitized_activation_status(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); root.chmod(0o700); store_root = root / "projection"
            clock = datetime.now(UTC) - timedelta(seconds=1)
            store = ProjectionStore(store_root); store.create_with_rollback(generated_at=clock.isoformat()); store.publish(projection(clock), now=clock)
            reader = FixedProjectionReader(root=store_root, enabled=True, validation_clock=clock)
            missing = [root / f"missing-{i}" for i in range(4)]
            compositor = Compositor(*missing, "http://127.0.0.1:1", multi_asset_reader=reader.read)
            compositor._reachability = lambda: "UNAVAILABLE"
            snapshot = compositor.snapshot()
            status = snapshot["sections"]["projection_activation"]
            self.assertEqual((status["state"], status["data"]["hash_validation"]), ("AVAILABLE", "VALID"))
            self.assertNotIn(str(root), json.dumps(status))

    def test_compositor_exposes_authenticated_stale_state_without_advancement(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); root.chmod(0o700); store_root = root / "projection"
            clock = datetime.now(UTC) - timedelta(seconds=901)
            store = ProjectionStore(store_root); store.create_with_rollback(generated_at=clock.isoformat())
            store.publish(projection(clock), now=clock)
            reader = FixedProjectionReader(root=store_root, enabled=True,
                validation_clock=clock + timedelta(seconds=901))
            missing = [root / f"missing-{i}" for i in range(4)]
            compositor = Compositor(*missing, "http://127.0.0.1:1", multi_asset_reader=reader.read)
            compositor._reachability = lambda: "UNAVAILABLE"
            snapshot = compositor.snapshot(); sections = snapshot["sections"]
            status = sections["projection_activation"]
            self.assertEqual(status["state"], "STALE")
            self.assertEqual(status["data"]["reader_state"], "ACTIVE")
            self.assertEqual(status["data"]["integrity_state"], "VALID")
            self.assertEqual(status["data"]["freshness_state"], "STALE")
            self.assertEqual(status["data"]["publisher_state"], "UNAVAILABLE")
            self.assertFalse(status["data"]["evidence_current"])
            self.assertEqual(sections["candidate_conveyor"]["data"]["candidates"], [])
            self.assertEqual(sections["professional_strategy_observatory"]["state"], "UNAVAILABLE")
            self.assertTrue(all(not lane["research_eligible"] and not lane["paper_eligible"]
                for lane in sections["multi_asset_factory"]["data"]["lane_states"].values()))

    def test_no_provider_keychain_broker_ledger_or_runtime_control(self):
        source = Path(__file__).with_name("projection_runtime.py").read_text()
        for prohibited in ("X-API-KEY", "security find-generic-password", "subprocess", "broker_order", "ledger.db"):
            self.assertNotIn(prohibited, source)

    def test_frontend_rendering_contract_wraps_and_summarizes_without_changing_truth(self):
        root = Path(__file__).parents[3] / "FRONT END" / "src"
        component = (root / "ExpansionWingFactory.tsx").read_text()
        styles = (root / "ExpansionWingFactory.css").read_text()
        for marker in ("Summary", "Audit detail", "Candidate Conveyor", "Control Room"):
            self.assertIn(marker, component)
        for marker in ("repeat(5,minmax(0,1fr))", "repeat(2,minmax(0,1fr))",
                       "grid-template-columns:minmax(0,1fr)", "overflow:hidden"):
            self.assertIn(marker, styles)
        self.assertIn('candidate_count==null?"UNKNOWN"', component)


if __name__ == "__main__": unittest.main()
