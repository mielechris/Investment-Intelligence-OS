import unittest
from unittest.mock import patch

import opportunity_dispatch as dispatch


class OpportunityDispatchTests(unittest.TestCase):

    @patch("opportunity_dispatch.record_event")
    @patch("opportunity_dispatch.opportunity_queue")
    def test_batch_dispatch_is_hard_capped(self, queue, record_event):
        queue.return_value = []
        self.assertEqual(dispatch.MAX_BATCH_DISPATCH, 3)
        result = dispatch.dispatch_ranked_queue(limit=99)
        self.assertLessEqual(result["requested"], 3)
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_dispatch_routes_have_no_execution_or_authorization(self):
        paths = {route.path.lower() for route in dispatch.router.routes}
        self.assertIn("/opportunities/{candidate_id}/dispatch", paths)
        self.assertIn("/opportunities/dispatch-queue", paths)
        self.assertFalse(
            any(
                "paper-authorization" in path
                or "governed-paper-execution" in path
                or "broker" in path
                or "live" in path
                for path in paths
            )
        )


if __name__ == "__main__":
    unittest.main()
