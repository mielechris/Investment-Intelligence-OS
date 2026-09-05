from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .projection_publisher import EvaluationTimes, GovernedProjectionPublisher
from .projection_runtime import MANIFEST_NAME, PROJECTION_NAME, ProjectionStore
from .test_superbatch17 import NOW, envelopes, payloads


class TimestampSafePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp=tempfile.TemporaryDirectory();self.parent=Path(self.temp.name);self.parent.chmod(0o700)
        self.root=self.parent/"projection";ProjectionStore(self.root).create_with_rollback(generated_at=NOW.isoformat())
        self.publisher=GovernedProjectionPublisher(self.root)

    def tearDown(self) -> None: self.temp.cleanup()

    def seed(self):
        result=self.publisher.evaluate(envelopes(),now=NOW);self.assertEqual((result.state,result.sequence),("PUBLISHED",1))
        return ((self.root/PROJECTION_NAME).read_bytes(),(self.root/MANIFEST_NAME).read_bytes())

    def test_newer_timestamps_same_semantics_preserve_exact_bytes_and_time(self):
        before=self.seed();stored=json.loads(before[0]);later=NOW+timedelta(hours=1)
        result=self.publisher.evaluate(envelopes(moment=later),now=later)
        self.assertEqual((result.state,result.changed,result.sequence),("UNCHANGED",False,1))
        self.assertEqual(before,((self.root/PROJECTION_NAME).read_bytes(),(self.root/MANIFEST_NAME).read_bytes()))
        self.assertEqual(json.loads((self.root/PROJECTION_NAME).read_bytes())["projection_generated_at"],stored["projection_generated_at"])

    def test_newer_timestamp_and_semantic_change_publishes_once(self):
        self.seed();later=NOW+timedelta(hours=1);values=payloads()
        values["radar_cycle"]["cycle_id"]="cycle_17_changed";values["candidate_lineage"]["cycle_id"]="cycle_17_changed"
        changed=self.publisher.evaluate(envelopes(values,moment=later),now=later)
        self.assertEqual((changed.state,changed.changed,changed.sequence),("PUBLISHED",True,2))
        projection,manifest=ProjectionStore(self.root).read(now=later)
        self.assertGreaterEqual(datetime.fromisoformat(projection["projection_generated_at"]),
                                datetime.fromisoformat(projection["source_generated_at"]))
        self.assertEqual(manifest["projection_sha256"],__import__("hashlib").sha256((self.root/PROJECTION_NAME).read_bytes()).hexdigest())
        repeated=self.publisher.evaluate(envelopes(values,moment=later),now=later)
        self.assertEqual((repeated.state,repeated.changed,repeated.sequence),("UNCHANGED",False,2))

    def test_exact_boundary_and_mixed_source_times(self):
        values=envelopes();later=NOW+timedelta(minutes=5)
        for envelope in values.values():
            envelope["generated_at"]=later.isoformat();envelope["effective_at"]=later.isoformat()
        receipts=self.publisher._receipts(values,later)
        times=EvaluationTimes.resolve(receipts,observation_time=later,prior_projection_generated_at=NOW.isoformat())
        self.assertEqual(times.comparison_projection_generated_at,later)
        one=next(iter(values.values()));one["generated_at"]=(later-timedelta(minutes=1)).isoformat();one["effective_at"]=(later-timedelta(minutes=2)).isoformat()
        receipts=self.publisher._receipts(values,later)
        times=EvaluationTimes.resolve(receipts,observation_time=later,prior_projection_generated_at=NOW.isoformat())
        self.assertGreaterEqual(times.comparison_projection_generated_at,max(x["generated_at"] for x in receipts.values()))
        self.assertGreaterEqual(times.comparison_projection_generated_at,max(x["effective_at"] for x in receipts.values()))

    def test_future_required_and_optional_fail_without_mutation(self):
        before=self.seed();later=NOW+timedelta(minutes=5)
        for name in ("factory_health","professional_research"):
            value=envelopes(moment=later);value[name]["generated_at"]=(later+timedelta(microseconds=1)).isoformat()
            result=self.publisher.evaluate(value,now=later)
            self.assertEqual((result.state,result.sequence),("FAILED_CLOSED",None))
            self.assertEqual(before,((self.root/PROJECTION_NAME).read_bytes(),(self.root/MANIFEST_NAME).read_bytes()))

    def test_stale_session_and_freshness_transitions_remain_semantic(self):
        self.seed();later=NOW+timedelta(hours=1);value=envelopes(moment=NOW)
        stale=self.publisher.evaluate(value,now=later)
        self.assertEqual((stale.state,stale.sequence,stale.decision),("PUBLISHED",2,"FRESHNESS_BOUNDARY_CROSSED"))
        projection,_=ProjectionStore(self.root).read(now=later);self.assertEqual(projection["evidence_freshness_state"],"STALE")
        values=payloads();values["market_session"]["state"]="POST_MARKET"
        transition=self.publisher.evaluate(envelopes(values,moment=later),now=later)
        self.assertEqual((transition.sequence,transition.decision),(3,"MARKET_SESSION_TRANSITION"))

    def test_failure_replacement_restart_atomic_and_authority(self):
        self.seed();later=NOW+timedelta(minutes=5);values=payloads();values["radar_cycle"]["state"]="FAILED_CLOSED"
        failed=self.publisher.evaluate(envelopes(values,moment=later),now=later)
        self.assertEqual((failed.sequence,failed.decision),(2,"SANITIZED_FAILURE_REPLACEMENT"))
        restarted=GovernedProjectionPublisher(self.root).evaluate(envelopes(values,moment=later),now=later)
        self.assertEqual((restarted.state,restarted.sequence),("UNCHANGED",2))
        before=((self.root/PROJECTION_NAME).read_bytes(),(self.root/MANIFEST_NAME).read_bytes())
        interrupted=GovernedProjectionPublisher(self.root,before_commit=lambda:(_ for _ in ()).throw(RuntimeError("private")))
        changed=payloads();changed["radar_cycle"]["cycle_id"]="cycle_atomic";changed["candidate_lineage"]["cycle_id"]="cycle_atomic"
        self.assertEqual(interrupted.evaluate(envelopes(changed,moment=later+timedelta(minutes=1)),now=later+timedelta(minutes=1)).state,"FAILED_CLOSED")
        self.assertEqual(before,((self.root/PROJECTION_NAME).read_bytes(),(self.root/MANIFEST_NAME).read_bytes()))
        unsafe=payloads();unsafe["authority_locks"]["broker"]=True
        self.assertEqual(self.publisher.evaluate(envelopes(unsafe,moment=later),now=later).state,"FAILED_CLOSED")
        self.assertEqual(before,((self.root/PROJECTION_NAME).read_bytes(),(self.root/MANIFEST_NAME).read_bytes()))

    def test_browser_has_no_publication_route(self):
        provider=(Path(__file__).parents[3]/"FRONT END"/"src"/"ExpansionWingSnapshotProvider.tsx").read_text()
        publisher=(Path(__file__).parent/"projection_publisher.py").read_text()
        self.assertNotIn("/publish",provider)
        self.assertNotIn("fetch(",publisher)


if __name__=="__main__": unittest.main()
