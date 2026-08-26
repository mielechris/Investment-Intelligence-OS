import os
import unittest
from unittest.mock import patch

import grok_provider
import multi_model_intelligence_council as council


class GroupBatch8EMultiModelTests(unittest.TestCase):
    def test_grok_status_never_exposes_secret(self):
        with patch.dict(
            os.environ,
            {
                "IIOS_GROK_API_KEY": "super-secret-xai-key",
                "IIOS_GROK_BASE_URL": "https://api.x.ai/v1",
                "IIOS_GROK_MODEL": "grok-4.6",
            },
            clear=False,
        ):
            status = grok_provider.configuration_status()
            rendered = repr(status)
        self.assertTrue(status["configured"])
        self.assertTrue(status["credential_present"])
        self.assertFalse(status["credential_exposed"])
        self.assertNotIn("super-secret-xai-key", rendered)
        self.assertEqual(status["model_preference"], "grok-4.6")

    def test_grok_realtime_requires_search_tools(self):
        with patch.dict(os.environ, {}, clear=True):
            status = grok_provider.configuration_status()
        self.assertTrue(status["x_search_supported"])
        self.assertTrue(status["web_search_supported"])
        self.assertTrue(status["realtime_requires_search_tools"])
        self.assertFalse(status["live_execution"])

    def test_directional_model_conflict_escalates_to_skeptic(self):
        result = council.reconcile_views(
            [
                {"status": "AVAILABLE", "stance": "FAVORABLE", "confidence": 0.8},
                {"status": "AVAILABLE", "stance": "UNFAVORABLE", "confidence": 0.8},
                {"status": "AVAILABLE", "stance": "MIXED", "confidence": 0.5},
            ]
        )
        self.assertTrue(result["directional_conflict"])
        self.assertTrue(result["skeptic_escalation_recommended"])
        self.assertGreaterEqual(result["divergence_score"], 0.5)

    def test_matching_models_do_not_force_escalation(self):
        result = council.reconcile_views(
            [
                {"status": "AVAILABLE", "stance": "FAVORABLE", "confidence": 0.8},
                {"status": "AVAILABLE", "stance": "FAVORABLE", "confidence": 0.7},
            ]
        )
        self.assertFalse(result["directional_conflict"])
        self.assertFalse(result["skeptic_escalation_recommended"])
        self.assertEqual(result["consensus_stance"], "FAVORABLE")

    def test_grok_output_normalization_preserves_source_urls_only(self):
        view = council.normalize_grok_output(
            {
                "stance": "bearish",
                "confidence": 0.72,
                "summary": "Narrative is deteriorating.",
                "crowding_hype_signals": ["crowded long"],
            },
            ["https://x.com/example/status/1", "https://example.com/news"],
        )
        self.assertEqual(view["stance"], "UNFAVORABLE")
        self.assertEqual(view["citation_count"], 2)
        self.assertTrue(view["untrusted_model_output"])

    def test_council_packet_has_zero_execution_authority(self):
        iios = {
            "model": "IIOS_OPENAI_CORE",
            "status": "AVAILABLE",
            "stance": "MIXED",
            "confidence": 0.8,
            "summary": "Watch",
            "citation_count": 1,
        }
        kimi = {
            "model": "KIMI_RESEARCH",
            "status": "UNAVAILABLE",
            "stance": "MIXED",
            "confidence": 0.0,
            "summary": "not configured",
            "citation_count": 0,
        }
        grok = {
            "model": "GROK_NARRATIVE",
            "status": "PROVIDER_NOT_CONFIGURED",
            "stance": "MIXED",
            "confidence": 0.0,
            "summary": "not configured",
            "citation_count": 0,
        }
        with patch.object(council, "get_object", return_value={"case_id": "case_test"}), patch.object(
            council, "_iios_view", return_value=iios
        ), patch.object(council, "_kimi_view", return_value=kimi), patch.object(
            council, "_grok_view", return_value=grok
        ), patch.object(council, "record_object") as record_object, patch.object(council, "record_event"):
            packet = council.run_council("case_test")

        self.assertTrue(record_object.called)
        self.assertTrue(packet["governed_iios_committee_remains_authoritative"])
        self.assertFalse(packet["committee_override"])
        self.assertFalse(packet["risk_override"])
        self.assertFalse(packet["qualification_evidence"])
        self.assertFalse(packet["gap_resolution_eligible"])
        self.assertFalse(packet["fact_resolution_authority"])
        self.assertFalse(packet["capital_authority"])
        self.assertFalse(packet["trade_signal"])
        self.assertFalse(packet["auto_trade_authority"])
        self.assertFalse(packet["paper_order_permission"])
        self.assertFalse(packet["trade_execution_permission"])
        self.assertFalse(packet["live_execution"])
        self.assertEqual(packet["model_weighting_mode"], "NO_UNIVERSAL_WEIGHT_UNTIL_TASK_CALIBRATION")

    def test_missing_grok_provider_does_not_invent_view(self):
        with patch.object(
            council.grok_provider,
            "configuration_status",
            return_value={"configured": False, "credential_present": False},
        ):
            view = council._grok_view(
                "case_test",
                {"model": "KIMI_RESEARCH", "status": "UNAVAILABLE"},
                {"model": "IIOS_OPENAI_CORE", "status": "AVAILABLE"},
            )
        self.assertEqual(view["status"], "PROVIDER_NOT_CONFIGURED")
        self.assertEqual(view["confidence"], 0.0)
        self.assertIn("not configured", view["summary"].lower())

    def test_council_context_can_never_resolve_evidence_gap(self):
        packet = {
            "multi_model_council_packet_id": "mm_test",
            "created_at": "2026-08-26T00:00:00+00:00",
            "reconciliation": {
                "consensus_stance": "MIXED",
                "divergence_score": 0.75,
            },
            "skeptic_escalation_recommended": True,
        }
        with patch.object(council, "latest_object", return_value=packet):
            items = council.council_evidence("case_test")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertTrue(item["context_only"])
        self.assertTrue(item["untrusted_model_output"])
        self.assertTrue(item["requires_independent_corroboration"])
        self.assertFalse(item["qualification_evidence"])
        self.assertFalse(item["gap_resolution_eligible"])
        self.assertFalse(item["fact_resolution_authority"])
        self.assertFalse(item["capital_authority"])
        self.assertFalse(item["trade_signal"])
        self.assertFalse(item["trade_execution_permission"])


if __name__ == "__main__":
    unittest.main()
