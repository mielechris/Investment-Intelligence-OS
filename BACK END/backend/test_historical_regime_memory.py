import unittest
from unittest.mock import patch

import historical_regime_memory as memory


class HistoricalRegimeMemoryTests(unittest.TestCase):
    def test_regime_tags_are_deterministic(self):
        case = {"topic": "AI data center demand with Fed rates", "evidence": []}
        tags = memory.regime_tags(case)
        self.assertIn("ai_capex", tags)
        self.assertIn("rates", tags)

    @patch.object(memory, "latest_object")
    @patch.object(memory, "_all_cases")
    @patch.object(memory, "get_object")
    def test_analogs_are_internal_and_non_executable(self, get_object, all_cases, latest_object):
        get_object.return_value = {"case_id": "case_now", "topic": "Oil supply and Permian demand", "evidence": []}
        all_cases.return_value = [
            {"case_id": "case_now", "topic": "Oil supply and Permian demand", "evidence": []},
            {"case_id": "case_prior", "topic": "Oil production and Permian supply", "evidence": []},
        ]
        latest_object.side_effect = lambda object_type, case_id=None, **kwargs: (
            {"disposition": "WATCH", "confidence": 0.6}
            if object_type == "committee_decision"
            else {}
        )
        result = memory.find_historical_analogs("case_now")
        self.assertEqual(result["analog_count"], 1)
        self.assertEqual(result["analogs"][0]["analogy_scope"], "INTERNAL_IIOS_CASE_MEMORY")
        self.assertFalse(result["analogs"][0]["historical_outcome_known"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])


if __name__ == "__main__":
    unittest.main()
