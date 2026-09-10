"""SB3.6A: real capture/receipt/publisher paths, isolated stores and fake OS only."""
from contextlib import closing
import copy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_truth_spine_session as fixtures
from truth_spine_contract import canonical, digest
from truth_spine_generations import GenerationStore, cycle_identity
from truth_spine_full_day_service import publish_once, service_response
from truth_spine_session_package import captured_cycle, installation_template


class SourceCycleTests(unittest.TestCase):
    setUp = fixtures.ProductionPathTests.setUp
    write_cycle = fixtures.ProductionPathTests.write_cycle
    actual_probes = fixtures.ProductionPathTests.actual_probes

    def receipt(self, *, fresh=True):
        return captured_cycle(self.root, self.store.selected(), store=self.store, session=self.session,
                              now=self.clock(), require_fresh=fresh)

    def issue(self):
        return self.store.issue_source_cycle(self.session, topology_hash=digest(self.config),
            authority_hash=digest(self.authority), owners=fixtures.OWNERS, now=self.clock())

    def corrupt_receipt(self, value, seq=1):
        # Isolated adversarial disk corruption; NEVER an operational repair path.
        with closing(self.store.connect()) as db, db:
            db.execute("DROP TRIGGER IF EXISTS cycle_no_update")
            db.execute("UPDATE source_cycles SET payload=? WHERE seq=?", (canonical(value).decode(), seq))

    def test_completed_capture_creates_exact_receipt_and_original_clocks(self):
        self.assertEqual(self.supervisor.cycle()["ready"], 200)
        c = self.receipt()
        self.assertEqual(c["source_cycle_id"], cycle_identity(c))
        self.assertEqual(c["source_cycle_id"], hashlib.sha256(canonical({k:v for k,v in c.items() if k != "source_cycle_id"})).hexdigest())
        self.assertEqual(c["admitted_watermark"], self.store.watermark())
        self.assertEqual(c["stores"], self.store.selected()["files"])
        self.assertEqual(set(c["ledger_captures"]), {"operational", "historical"})
        self.assertFalse(c["globally_simultaneous"])
        self.assertEqual(c["producer_role"], "capture_scheduler")
        self.assertNotEqual(c["producer_identity"], c["consumer_identity"])
        self.assertTrue(all(f["integrity"] == "SQLITE_QUICK_CHECK_OK" for f in c["stores"][:2]))

    def test_inclusive_900_second_freshness_and_901_rejection(self):
        self.supervisor.cycle(); self.clock.advance(900)
        self.receipt(); self.clock.advance(1)
        with self.assertRaisesRegex(ValueError, "SOURCE_CYCLE_STALE"): self.receipt()

    def test_stale_permanent_input_is_not_accepted_as_shadow_receipt(self):
        self.supervisor.cycle()
        old = json.loads(self.cycle_path.read_bytes())
        self.corrupt_receipt(old)
        with self.assertRaises(ValueError): self.receipt()
        # The consumer does not synthesize a replacement from retained input.
        with self.assertRaises(ValueError): publish_once(self.root, self.session, self.manifest, self.registry, self.clock())

    def test_touched_old_receipt_remains_stale(self):
        self.supervisor.cycle(); self.clock.advance(901)
        os.utime(self.store.path, None)
        with self.assertRaisesRegex(ValueError, "SOURCE_CYCLE_STALE"): self.receipt()

    def test_copied_reserialized_old_receipt_remains_stale(self):
        self.supervisor.cycle(); c = self.receipt(); self.clock.advance(901)
        self.corrupt_receipt(json.loads(json.dumps(c, indent=4)))
        with self.assertRaisesRegex(ValueError, "SOURCE_CYCLE_STALE"): self.receipt()

    def test_future_receipt_and_backward_consumer_clock_rejected(self):
        self.supervisor.cycle(); self.clock.advance(-1)
        with self.assertRaisesRegex(ValueError, "SOURCE_CYCLE_STALE"): self.receipt()

    def test_failed_capture_cannot_refresh_receipt(self):
        self.supervisor.cycle(); old = self.receipt(); self.clock.advance(901)
        with patch.object(self.store, "_adapt", side_effect=ValueError("UNIT_CAPTURE_FAILURE")):
            self.assertEqual(self.supervisor.cycle()["ready"], 503)
        self.assertEqual(self.receipt(fresh=False), old)
        with self.assertRaisesRegex(ValueError, "LIFECYCLE|STALE"):
            publish_once(self.root, self.session, self.manifest, self.registry, self.clock())

    def test_publisher_reader_cannot_issue(self):
        self.supervisor.cycle(); before = self.store.path.read_bytes()
        reader = GenerationStore(self.root, self.session.identity, self.registry, digest(self.registry), readonly=True)
        with self.assertRaisesRegex(PermissionError, "READER_CANNOT_ISSUE"):
            reader.issue_source_cycle(self.session, topology_hash=digest(self.config),
                authority_hash=digest(self.authority), owners=fixtures.OWNERS, now=self.clock())
        publish_once(self.root, self.session, self.manifest, self.registry, self.clock())
        self.assertEqual(before, self.store.path.read_bytes())

    def mutation_rejected(self, mutate):
        self.supervisor.cycle(); c = copy.deepcopy(self.receipt()); mutate(c)
        c["source_cycle_id"] = cycle_identity(c)
        self.corrupt_receipt(c)
        with self.assertRaises((ValueError, KeyError)): self.receipt()

    def test_capture_mismatch(self):
        self.mutation_rejected(lambda c: c.update(generation="0"*64))

    def test_l7_hash_mismatch(self):
        self.mutation_rejected(lambda c: c["ledger_captures"]["operational"].update(snapshot_sha256="0"*64))

    def test_l8_hash_mismatch(self):
        self.mutation_rejected(lambda c: c["ledger_captures"]["historical"].update(snapshot_sha256="0"*64))

    def test_watermark_mismatch(self):
        self.mutation_rejected(lambda c: c["admitted_watermark"].update(count=50))

    def test_topology_mismatch(self):
        self.mutation_rejected(lambda c: c.update(topology_hash="0"*64))

    def test_authority_mismatch(self):
        self.mutation_rejected(lambda c: c.update(authority_hash="0"*64))

    def test_session_mismatch(self):
        self.mutation_rejected(lambda c: c.update(session="another-session"))

    def test_phase_mismatch(self):
        self.mutation_rejected(lambda c: c.update(phase="REGULAR_SESSION"))

    def test_publisher_claimed_producer_rejected(self):
        self.mutation_rejected(lambda c: c.update(producer_role="publisher"))

    def test_future_publication_resealed_rejected(self):
        self.mutation_rejected(lambda c: c.update(published_at=(self.clock()+timedelta(seconds=901)).isoformat()))

    def test_parent_fork_rejected(self):
        self.supervisor.cycle(); self.clock.advance(900); self.supervisor.cycle()
        c = self.receipt(); c["previous_source_cycle"] = "0"*64
        c["source_cycle_id"] = cycle_identity(c); self.corrupt_receipt(c, 2)
        with self.assertRaises(ValueError): self.receipt()

    def test_missing_parent_rejected(self):
        self.supervisor.cycle(); self.clock.advance(900); self.supervisor.cycle()
        with closing(self.store.connect()) as db, db:
            db.execute("DROP TRIGGER cycle_no_delete"); db.execute("DELETE FROM source_cycles WHERE seq=1")
        with self.assertRaises(ValueError): self.receipt()

    def test_altered_ancestor_rejected(self):
        self.supervisor.cycle(); ancestor = self.receipt(); self.clock.advance(900); self.supervisor.cycle()
        ancestor["published_at"] = (self.session.start+timedelta(seconds=1)).isoformat()
        ancestor["source_cycle_id"] = cycle_identity(ancestor); self.corrupt_receipt(ancestor)
        with self.assertRaises(ValueError): self.receipt()

    def test_idempotence_and_restart_do_not_refresh_or_duplicate(self):
        self.supervisor.cycle(); c = self.receipt(); before = self.store.path.read_bytes()
        self.clock.advance(5); self.assertEqual(self.issue(), c)
        self.store = GenerationStore(self.root, self.session.identity, self.registry, digest(self.registry))
        self.assertEqual(self.issue(), c); self.assertEqual(before, self.store.path.read_bytes())
        self.assertEqual(self.store.watermark()["count"], 2)

    def test_interrupt_after_admission_recovers_without_recapture(self):
        self.store.capture(clock=self.clock); capture = self.store.selected()
        with self.assertRaisesRegex(ValueError, "SOURCE_CYCLE_CAPTURE_REQUIRED"): self.receipt()
        self.store = GenerationStore(self.root, self.session.identity, self.registry, digest(self.registry))
        self.issue(); self.assertEqual(self.receipt()["generation"], capture["content_hash"])
        self.assertEqual(len(list(self.store.captures.iterdir())), 1)

    def test_old_pending_capture_cannot_receive_new_publication(self):
        self.store.capture(clock=self.clock); self.clock.advance(31)
        with self.assertRaisesRegex(ValueError, "PUBLICATION_WINDOW_INVALID"): self.issue()

    def test_clock_reversal_and_monotonic_disagreement_reject_capture(self):
        for delta in (-1, 10):
            calls = iter([self.clock()]*5 + [self.clock()+timedelta(seconds=delta)]*10)
            with self.subTest(delta=delta), self.assertRaisesRegex(ValueError, "CLOCK|TIME"):
                self.store.capture(clock=lambda: next(calls))
        self.assertIsNone(self.store.selected())

    def test_post_close_capture_receipt_publisher_order_and_lag(self):
        self.supervisor.cycle(); self.clock.at = self.session.close_at; self.publish_enabled = False
        self.assertEqual(self.supervisor.cycle()["ready"], 503)
        final = self.receipt(); self.assertEqual(final["phase"], "POST_CLOSE_RECONCILIATION")
        old = json.loads((self.root/"projections/current.json").read_bytes())
        self.assertNotEqual(old["source_cycle"], final["source_cycle_id"])
        self.assertFalse(self.supervisor.lifecycle.state["post_close_reconciled"])
        self.clock.advance(5); self.publish_enabled = True
        self.assertEqual(self.supervisor.cycle()["ready"], 200)
        p = json.loads((self.root/"projections/current.json").read_bytes())
        self.assertEqual(p["source_cycle"], final["source_cycle_id"])
        self.assertEqual(p["watermark"], final["admitted_watermark"])
        self.assertTrue(self.supervisor.lifecycle.state["post_close_reconciled"])

    def test_classifications_original_inputs_and_zero_authority_preserved(self):
        original = [Path(s["path"]).read_bytes() for s in self.inputs]
        self.supervisor.cycle(); first = self.receipt(); self.clock.advance(900); self.supervisor.cycle()
        self.assertNotEqual(first["source_cycle_id"], self.receipt()["source_cycle_id"])
        self.assertEqual([f["classifications"] for f in first["stores"]],
                         [f["classifications"] for f in self.receipt()["stores"]])
        self.assertEqual(original, [Path(s["path"]).read_bytes() for s in self.inputs])
        self.assertEqual(self.store.watermark()["count"], 2)
        self.assertTrue(all(v is False for v in self.supervisor.lifecycle.state["capabilities"].values()))

    def test_correct_browser_route_and_no_implicit_historical_api_alias(self):
        self.assertEqual(installation_template()["review_url"],
            "http://127.0.0.1:5291/review/northstar-session.html?fullSession=1")
        self.assertEqual(service_response(self.root/"topology.json", "/truth-spine/museum", now=self.clock())[0], 404)

    def test_fresh_probe_wrapper_cannot_hide_expired_nested_cycle(self):
        from truth_spine_contract import seal
        from truth_spine_integration import atomic
        self.supervisor.cycle(); self.clock.advance(901)
        p = json.loads((self.root/"runtime-probes.json").read_bytes())
        p["probes"] = {k: seal({**v, "observed_at": self.clock().isoformat(),
            "expires_at": (self.clock()+timedelta(seconds=15)).isoformat()}) for k,v in p["probes"].items()}
        atomic(self.root/"runtime-probes.json", seal(p))
        self.assertEqual(service_response(self.root/"topology.json", "/health/ready", now=self.clock())[0], 503)

    def test_interrupted_receipt_commit_recovery_is_exactly_once(self):
        self.store.capture(clock=self.clock)
        original = self.store.path.read_bytes()
        with patch("truth_spine_generations.canonical", side_effect=OSError("UNIT_INTERRUPTED_RECEIPT")):
            with self.assertRaises(OSError): self.issue()
        self.assertEqual(original, self.store.path.read_bytes())
        c = self.issue(); self.assertEqual(c, self.issue())

    def test_receipt_not_issued_before_admission_integrity_transaction(self):
        self.supervisor.cycle(); old = self.receipt()
        with closing(sqlite3.connect(self.inputs[0]["path"])) as db, db:
            db.execute("UPDATE ledger_objects SET payload_json='{}'")
        self.clock.advance(900)
        self.assertEqual(self.supervisor.cycle()["ready"], 503)
        self.assertEqual(self.receipt(fresh=False), old)

    def test_authority_expiry_before_receipt_commit_leaves_no_receipt(self):
        self.store.capture(clock=self.clock)
        before = self.store.path.read_bytes()
        with self.assertRaises(PermissionError):
            self.store.issue_source_cycle(self.session, topology_hash=digest(self.config),
                authority_hash=digest(self.authority), owners=fixtures.OWNERS, now=self.clock(),
                permit=unittest.mock.Mock(side_effect=[None, PermissionError("UNIT_EXPIRED")]))
        self.assertEqual(before, self.store.path.read_bytes())
        with self.assertRaisesRegex(ValueError, "SOURCE_CYCLE_CAPTURE_REQUIRED"): self.receipt()


if __name__ == "__main__": unittest.main()
