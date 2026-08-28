import unittest
from unittest.mock import patch

import observation_heartbeat_sync as sync


class Batch10DObservationHeartbeatSyncTests(unittest.TestCase):
    @patch.object(sync, "record_event")
    @patch.object(sync, "record_object")
    def test_checkpoint_persists_telemetry_only_and_forces_authority_locked(
        self,
        record_object,
        record_event,
    ):
        payload = {
            "last_cycle_completed_at": "2026-08-28T16:00:00+00:00",
            "market_phase": "REGULAR_SESSION",
            "last_scan_status": "complete",
            "last_scan_count": 518,
            "last_queue_count": 3,
            "promoted_case_count": 1,
            "paper_mode": False,
            "auto_trade_authority": True,
            "paper_order_permission": True,
            "trade_execution_permission": True,
            "live_execution": True,
        }

        result = sync.persist_observation_checkpoint(payload)

        stored = record_object.call_args.args[3]
        self.assertEqual(stored["market_phase"], "REGULAR_SESSION")
        self.assertEqual(stored["last_scan_count"], 518)
        self.assertEqual(
            stored["observation_heartbeat_source"],
            "BATCH9A_BACKEND_8002_BRIDGE",
        )
        self.assertTrue(stored["paper_mode"])
        self.assertFalse(stored["auto_trade_authority"])
        self.assertFalse(stored["paper_order_permission"])
        self.assertFalse(stored["trade_execution_permission"])
        self.assertFalse(stored["live_execution"])
        self.assertEqual(result["status"], "accepted")
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])
        record_event.assert_called_once()

    def test_checkpoint_requires_completed_timestamp(self):
        with self.assertRaises(ValueError):
            sync.persist_observation_checkpoint({"market_phase": "REGULAR_SESSION"})


if __name__ == "__main__":
    unittest.main()
