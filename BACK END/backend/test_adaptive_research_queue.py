import unittest
from unittest.mock import patch

import adaptive_research_queue as queue


class AdaptiveResearchQueueTests(unittest.TestCase):
    def setUp(self):
        self.objects = {}
        self.events = []

        def get_object(object_id):
            if object_id.startswith("case_"):
                return {"case_id": object_id, "topic": f"Topic {object_id}"}
            return self.objects.get(object_id)

        def record_object(object_id, object_type, case_id, payload, **kwargs):
            self.objects[object_id] = dict(payload)

        def list_objects(case_id, object_type=None):
            return [
                dict(value)
                for value in self.objects.values()
                if value.get("research_queue_item_id")
            ]

        self.patchers = [
            patch.object(queue, "get_object", side_effect=get_object),
            patch.object(queue, "record_object", side_effect=record_object),
            patch.object(queue, "list_objects", side_effect=list_objects),
            patch.object(queue, "record_event", side_effect=lambda *args, **kwargs: self.events.append((args, kwargs))),
            patch.object(queue, "configured_case_workers", return_value=2),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()

    def test_backpressure_activates_at_high_watermark(self):
        below = queue.backpressure_state(queue.HIGH_WATERMARK - 1)
        at = queue.backpressure_state(queue.HIGH_WATERMARK)
        self.assertFalse(below["backpressure_active"])
        self.assertTrue(at["backpressure_active"])
        self.assertTrue(at["intake_open"])

    def test_queue_capacity_fails_closed(self):
        state = queue.backpressure_state(queue.MAX_QUEUE_DEPTH, 0)
        self.assertFalse(state["intake_open"])
        self.assertEqual(state["capacity_remaining"], 0)

    def test_enqueue_is_deduplicated_and_never_grants_execution(self):
        first = queue.enqueue_case("case_a", priority_score=80, ticker="AAA")
        second = queue.enqueue_case("case_a", priority_score=10, ticker="AAA")
        self.assertFalse(first["already_queued"])
        self.assertTrue(second["already_queued"])
        item = first["item"]
        self.assertEqual(item["state"], queue.PENDING)
        self.assertFalse(item["paper_order_permission"])
        self.assertFalse(item["trade_execution_permission"])
        self.assertFalse(item["live_execution"])

    def test_drain_uses_priority_and_bounded_worker_count(self):
        queue.enqueue_case("case_low", priority_score=10, ticker="LOW")
        queue.enqueue_case("case_high", priority_score=90, ticker="HIGH")
        queue.enqueue_case("case_mid", priority_score=50, ticker="MID")

        captured = []

        def fake_batch(case_ids):
            captured.extend(case_ids)
            return {
                "status": "complete",
                "results": [
                    {
                        "case_id": case_id,
                        "status": "complete",
                        "orchestration_id": f"orch_{case_id}",
                        "committee_disposition": "WATCH",
                        "committee_confidence": 0.5,
                    }
                    for case_id in case_ids
                ],
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
            }

        with patch.object(queue, "run_case_batch", side_effect=fake_batch):
            result = queue.drain_queue()

        self.assertEqual(captured, ["case_high", "case_mid"])
        self.assertEqual(result["selected"], 2)
        self.assertEqual(self.objects[queue._queue_item_id("case_high")]["state"], queue.COMPLETE)
        self.assertEqual(self.objects[queue._queue_item_id("case_low")]["state"], queue.PENDING)
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_ranked_intake_pauses_under_backpressure(self):
        for i in range(queue.HIGH_WATERMARK):
            queue.enqueue_case(f"case_{i}", priority_score=100 - i)

        with patch.object(queue, "opportunity_queue") as opportunity_queue:
            result = queue.enqueue_ranked_opportunities(5)
        opportunity_queue.assert_not_called()
        self.assertEqual(result["status"], "backpressure")
        self.assertEqual(result["selected"], 0)
        self.assertFalse(result["trade_execution_permission"])

    def test_one_worker_failure_is_isolated(self):
        queue.enqueue_case("case_good", priority_score=90)
        queue.enqueue_case("case_bad", priority_score=80)

        with patch.object(
            queue,
            "run_case_batch",
            return_value={
                "status": "partial",
                "results": [
                    {
                        "case_id": "case_good",
                        "status": "complete",
                        "orchestration_id": "orch_good",
                        "committee_disposition": "WATCH",
                        "committee_confidence": 0.4,
                    },
                    {
                        "case_id": "case_bad",
                        "status": "error",
                        "error": "simulated failure",
                    },
                ],
            },
        ):
            result = queue.drain_queue()

        self.assertEqual(self.objects[queue._queue_item_id("case_good")]["state"], queue.COMPLETE)
        self.assertEqual(self.objects[queue._queue_item_id("case_bad")]["state"], queue.ERROR)
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_queue_routes_are_research_only(self):
        paths = {route.path.lower() for route in queue.router.routes}
        self.assertIn("/research-queue/plan", paths)
        self.assertIn("/research-queue/drain", paths)
        self.assertFalse(any("broker" in path or "authorization" in path or "paper-order" in path or "live" in path for path in paths))


if __name__ == "__main__":
    unittest.main()
