import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cross_case_memory as memory


class CrossCaseMemoryTests(unittest.TestCase):
    @patch.object(memory, "find_historical_analogs")
    @patch.object(memory, "get_object")
    def test_memory_is_nonqualifying_and_research_only(self, get_object, analogs):
        get_object.return_value = {"case_id": "case_now", "topic": "Test"}
        analogs.return_value = {
            "analogs": [{
                "case_id": "case_old",
                "topic": "Prior test",
                "similarity": 0.8,
                "shared_regime_tags": ["rates"],
                "committee_disposition": "WATCH",
                "committee_confidence": 0.6,
                "historical_outcome_known": False,
                "outcome": None,
            }]
        }
        context = memory.build_memory_context("case_now")
        self.assertEqual(context["memory_item_count"], 1)
        item = context["memory_items"][0]
        self.assertTrue(item["memory_inference_only"])
        self.assertFalse(item["gap_resolution_eligible"])
        self.assertFalse(context["qualification_evidence"])
        self.assertFalse(context["trade_execution_permission"])

    def test_installer_appends_memory_only_to_agent_evidence(self):
        seen = []

        def run_one(agent_key, topic, evidence):
            seen.extend(evidence)
            return {"agent_key": agent_key, "status": "complete"}

        def orchestration(case_id):
            module._run_one("policy", "topic", [{"source": "base"}])
            return {"orchestration": {}, "committee": {}}

        module = SimpleNamespace(
            _cross_case_memory_installed=False,
            _run_one=run_one,
            run_eight_agent_orchestration=orchestration,
        )
        with patch.object(memory, "build_memory_context", return_value={
            "memory_items": [{"source": "memory"}],
            "memory_item_count": 1,
        }):
            memory.install_cross_case_memory(module)
            result = module.run_eight_agent_orchestration("case_x")

        self.assertEqual([row["source"] for row in seen], ["base", "memory"])
        self.assertEqual(result["memory_context"]["memory_item_count"], 1)
        self.assertFalse(result["memory_context"]["qualification_evidence"])


if __name__ == "__main__":
    unittest.main()
