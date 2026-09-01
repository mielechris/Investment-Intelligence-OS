import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import grok_social_intelligence as social


class GrokSocialGovernorBoundaryTests(unittest.TestCase):
    def test_social_x_search_preflights_and_settles_success(self):
        create = Mock(return_value={"usage": {}})
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        admission = {"allow": True, "reservation_id": "reservation-1"}

        with patch.object(social, "preflight_xai_request", return_value=admission) as preflight, patch.object(social, "record_xai_response") as settled, patch.object(social, "max_x_search_tool_calls", return_value=2):
            social._run_x_search(client, prompt="prompt", from_date="2026-08-01", to_date="2026-08-02", case_id="case", query_label="query")

        preflight.assert_called_once()
        self.assertEqual(settled.call_args.kwargs["reservation_id"], "reservation-1")
        self.assertEqual(create.call_args.kwargs["extra_body"]["max_tool_calls"], 2)


if __name__ == "__main__":
    unittest.main()