import unittest
from types import SimpleNamespace
from unittest.mock import patch

import agent_calibration_weighting as calibration


class AgentCalibrationWeightingTests(unittest.TestCase):
    @patch.object(calibration, "build_agent_scorecards", return_value=[])
    def test_immature_samples_keep_all_weights_neutral(self, scorecards):
        policy = calibration.build_calibration_policy()
        self.assertFalse(policy["weighting_active"])
        self.assertTrue(all(row["effective_weight"] == 1.0 for row in policy["agents"].values()))
        self.assertFalse(policy["trade_execution_permission"])

    @patch.object(calibration, "build_agent_scorecards")
    def test_weighting_activates_only_when_all_desks_mature(self, scorecards):
        scorecards.return_value = [
            {
                "agent_key": key,
                "decisive_observations": 25,
                "average_calibration_score": 0.8,
            }
            for key in calibration.AGENT_KEYS
        ]
        policy = calibration.build_calibration_policy()
        self.assertTrue(policy["weighting_active"])
        self.assertTrue(all(row["effective_weight"] > 1.0 for row in policy["agents"].values()))

    def test_installer_does_not_override_guards(self):
        def synthesize(*args, **kwargs):
            return {"disposition": "NO_TRADE", "orchestration_guard": {"failed_checks": ["x"]}}

        module = SimpleNamespace(_calibration_context_installed=False, _synthesize_committee=synthesize)
        with patch.object(calibration, "build_calibration_policy", return_value={
            "weighting_active": False,
            "agents": {key: {"effective_weight": 1.0} for key in calibration.AGENT_KEYS},
        }):
            calibration.install_calibration_context(module)
            result = module._synthesize_committee(specialists={})
        self.assertEqual(result["disposition"], "NO_TRADE")
        self.assertEqual(result["orchestration_guard"]["failed_checks"], ["x"])
        self.assertFalse(result["calibration_weighting_active"])


if __name__ == "__main__":
    unittest.main()
