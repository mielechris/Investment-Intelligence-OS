import unittest
from unittest.mock import patch

import grok_value_cycle_async as async_cycle


class GrokValueCycleAsyncTests(unittest.TestCase):
    def setUp(self):
        async_cycle._ACTIVE_JOB_ID = None

    @patch.object(async_cycle._JOB_POOL, "submit")
    @patch.object(async_cycle, "_record_job")
    def test_start_returns_immediately_without_execution_authority(self, record_job, submit):
        record_job.return_value = {
            "grok_value_cycle_job_id": "job1",
            "status": "QUEUED",
            "research_only": True,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        with patch.object(async_cycle.uuid4(), "hex", "job1") if False else patch.object(async_cycle, "uuid4") as uuid_factory:
            uuid_factory.return_value.hex = "job1"
            out = async_cycle.start_cycle_job({"native_symbol_limit": 4})
        self.assertEqual(out["status"], "STARTED")
        self.assertEqual(out["job"]["status"], "QUEUED")
        self.assertIn("/grok/value/cycle/jobs/job1", out["poll_path"])
        self.assertFalse(out["auto_trade_authority"])
        self.assertFalse(out["paper_order_permission"])
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])
        submit.assert_called_once()

    @patch.object(async_cycle._JOB_POOL, "submit")
    @patch.object(async_cycle, "_safe_job")
    def test_second_start_does_not_spawn_competing_cycle(self, safe_job, submit):
        async_cycle._ACTIVE_JOB_ID = "existing"
        safe_job.return_value = {
            "grok_value_cycle_job_id": "existing",
            "status": "RUNNING",
            "research_only": True,
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        out = async_cycle.start_cycle_job({})
        self.assertEqual(out["status"], "ALREADY_RUNNING")
        submit.assert_not_called()
        self.assertFalse(out["trade_execution_permission"])
        self.assertFalse(out["live_execution"])

    @patch.object(async_cycle, "_record_job")
    @patch.object(async_cycle, "run_forward_value_cycle")
    def test_background_job_records_complete_result(self, run_cycle, record_job):
        run_cycle.return_value = {"grok_value_cycle_id": "cycle_1", "status": "COMPLETE"}
        record_job.side_effect = lambda job_id, payload: {
            "grok_value_cycle_job_id": job_id,
            **payload,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        async_cycle._ACTIVE_JOB_ID = "job1"
        async_cycle._run_job("job1", {"native_symbol_limit": 4})
        statuses = [call.args[1]["status"] for call in record_job.call_args_list]
        self.assertEqual(statuses, ["RUNNING", "COMPLETE"])
        self.assertIsNone(async_cycle._ACTIVE_JOB_ID)


if __name__ == "__main__":
    unittest.main()
