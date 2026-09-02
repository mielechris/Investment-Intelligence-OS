import unittest
from unittest.mock import patch

import grok_governed_observation as observation
import grok_social_intelligence as social


class GrokGovernedObservationTests(unittest.TestCase):
    def test_read_model_is_advisory_only_and_sanitized(self):
        view = observation.advisory_read_model({"case_id": "case_1", "citation_count": 2, "admitted_count": 1, "quarantined_count": 1, "reservation_id": "r1", "actual_cost_ticks": 10})
        self.assertEqual(view["label"], "UNTRUSTED ADVISORY RESEARCH")
        self.assertFalse(view["qualification_evidence"])
        self.assertFalse(view["promotion_authority"])
        self.assertFalse(view["trade_execution_permission"])
        self.assertNotIn("raw_candidate_tickers", view)

    @patch.object(observation, "record_object")
    @patch.object(observation, "get_object", return_value=None)
    def test_observation_tracks_quarantine_and_has_no_authority(self, get_object, record_object):
        payload = observation.record_observation({"citation_count": 2, "admitted_count": 1, "quarantined_count": 2, "actual_cost_ticks": 10})
        self.assertEqual(len(payload["entries"]), 1)
        self.assertFalse(payload["capital_authority"])
        self.assertFalse(payload["live_execution"])
        record_object.assert_called_once()

    @patch.object(observation, "get_object", return_value={"entries": [{"admitted_count": 1, "quarantined_count": 2, "actual_cost_ticks": 10, "useful_insight": True, "false_positive": False}]})
    def test_status_is_read_only_and_reports_authority_flags(self, get_object):
        status = observation.observation_status()
        self.assertEqual(status["requests_observed"], 1)
        self.assertEqual(status["quarantined_count"], 2)
        self.assertFalse(status["promotion_authority"])
        self.assertFalse(status["live_execution"])

    def test_observation_status_route_is_owned_by_social_router_once(self):
        paths = [route.path for route in social.router.routes]
        self.assertEqual(paths.count("/grok/observation/status"), 1)


if __name__ == "__main__":
    unittest.main()