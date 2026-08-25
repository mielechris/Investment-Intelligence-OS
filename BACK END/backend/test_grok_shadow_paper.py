import unittest
from unittest.mock import patch

import grok_shadow_paper as shadow


class GrokShadowPaperTests(unittest.TestCase):
    def test_arm_state_never_creates_position(self):
        self.assertEqual(shadow._arm_state("NO_TRADE"), "CASH_NO_POSITION")
        self.assertEqual(shadow._arm_state("WATCH"), "WATCH_ONLY_NO_POSITION")

    @patch.object(shadow, "_rows")
    def test_status_remains_measurement_only(self, rows):
        rows.side_effect = lambda object_type: [
            {"differentiated_action": False}
        ] if object_type == "grok_shadow_paper_pair" else []
        out = shadow.shadow_paper_status()
        self.assertEqual(out["pair_count"], 1)
        self.assertEqual(out["actual_paper_orders_created"], 0)
        self.assertFalse(out["arm_specific_pnl_available"])
        self.assertFalse(out["auto_trade_authority"])
        self.assertFalse(out["paper_order_permission"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])


if __name__ == "__main__":
    unittest.main()
