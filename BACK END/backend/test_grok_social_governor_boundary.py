import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import grok_social_intelligence as social


class GrokSocialGovernorBoundaryTests(unittest.TestCase):
    def test_social_x_search_preflights_and_settles_success(self):
        create = Mock(return_value={"usage": {}})
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        admission = {"allow": True, "reservation_id": "reservation-1"}

        with patch.object(social, "preflight_xai_request", return_value=admission) as preflight, patch.object(social, "mark_xai_provider_invocation_started"), patch.object(social, "record_xai_response") as settled, patch.object(social, "max_x_search_tool_calls", return_value=2):
            social._run_x_search(client, prompt="prompt", from_date="2026-08-01", to_date="2026-08-02", case_id="case", query_label="query")

        preflight.assert_called_once()
        self.assertEqual(settled.call_args.kwargs["reservation_id"], "reservation-1")
        self.assertEqual(create.call_args.kwargs["extra_body"]["max_tool_calls"], 2)

    def test_unverified_pricing_rejects_before_credentials_or_client(self):
        denied = {"allow": False, "decision": "BLOCK_PRICING", "reasons": ["PRICING_UNVERIFIED"]}
        def getenv(name, default=None):
            if name == "XAI_API_KEY":
                raise AssertionError("credential read")
            return default

        with patch.object(social, "grok_enabled", return_value=True), patch.object(social, "preflight_xai_request", return_value=denied), patch.object(social.os, "getenv", side_effect=getenv), patch.object(social, "OpenAI", side_effect=AssertionError("client created")):
            with self.assertRaisesRegex(RuntimeError, "BLOCK_PRICING"):
                social.fetch_grok_social_context("topic")

    def test_missing_credentials_cancels_admitted_reservation_nonbillably(self):
        admission = {"allow": True, "reservation_id": "reservation-1"}
        with patch.object(social, "grok_enabled", return_value=True), patch.object(social, "preflight_xai_request", return_value=admission), patch.object(social.os, "getenv", return_value=""), patch.object(social, "cancel_xai_reservation") as cancel, patch.object(social, "OpenAI", side_effect=AssertionError("client created")):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                social.fetch_grok_social_context("topic")
        self.assertEqual(cancel.call_args.kwargs["reservation_id"], "reservation-1")

    def test_cancellation_is_idempotent_and_rejected_after_provider_start(self):
        with patch.object(social, "cancel_xai_reservation", side_effect=[{"already_cancelled": False}, {"already_cancelled": True}]) as cancel:
            self.assertFalse(cancel(reservation_id="reservation-1", reason="MISSING_CREDENTIALS")["already_cancelled"])
            self.assertTrue(cancel(reservation_id="reservation-1", reason="MISSING_CREDENTIALS")["already_cancelled"])


if __name__ == "__main__":
    unittest.main()