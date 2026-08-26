import json
import os
import unittest
from unittest.mock import patch

import kimi_provider
import kimi_research_intelligence as kimi_research
import kimi_swarm_bridge


WORKER_OUTPUT = {
    "summary": "The source is constructive on semiconductors but identifies valuation risk.",
    "sector_views": [
        {
            "sector": "SEMICONDUCTOR",
            "sentiment": "FAVORABLE",
            "conviction": 0.77,
            "drivers": ["AI infrastructure demand"],
            "risks": ["valuation"],
            "tickers": ["NVDA"],
        }
    ],
    "key_assumptions": ["AI capex remains durable"],
    "catalysts": ["earnings"],
    "risks": ["multiple compression"],
    "falsifiers": ["AI capex contraction"],
    "open_questions": ["How durable is demand?"],
    "citations": [
        {
            "source_title": "Public Research Note",
            "source_url": "https://example.test/report",
            "section_locator": "Outlook section",
            "supports": "The analyst expects durable AI infrastructure demand.",
        }
    ],
    "confidence": 0.8,
}

SYNTHESIS_OUTPUT = {
    "executive_summary": "Research is favorable overall, with valuation as the main unresolved issue.",
    "consensus": ["AI infrastructure demand remains supportive"],
    "disagreements": [
        {
            "topic": "valuation",
            "side_a": "current multiples are justified",
            "side_b": "multiples embed too much growth",
            "assumption_causing_divergence": "duration of AI capex growth",
            "what_would_resolve_it": "forward estimate revisions and realized capex",
        }
    ],
    "sector_matrix": [
        {
            "sector": "SEMICONDUCTOR",
            "sentiment": "FAVORABLE",
            "conviction": 0.7,
            "drivers": ["AI demand"],
            "risks": ["valuation"],
            "tickers": ["NVDA"],
        }
    ],
    "assumption_conflicts": ["AI capex duration"],
    "company_divergences": [],
    "open_questions": ["How fast do estimates rise?"],
    "recommended_followup_research": ["Track revisions"],
    "confidence": 0.75,
}


class GroupBatch8DKimiTests(unittest.TestCase):
    def test_provider_status_never_exposes_api_key(self):
        with patch.dict(
            os.environ,
            {
                "IIOS_KIMI_API_KEY": "super-secret-kimi-key",
                "IIOS_KIMI_BASE_URL": "https://api.moonshot.cn/v1",
                "IIOS_KIMI_MODEL": "kimi-k3",
            },
            clear=False,
        ):
            status = kimi_provider.configuration_status()
            rendered = repr(status)
        self.assertTrue(status["configured"])
        self.assertTrue(status["credential_present"])
        self.assertFalse(status["credential_exposed"])
        self.assertNotIn("super-secret-kimi-key", rendered)
        self.assertEqual(status["model_preference"], "kimi-k3")

    def test_provider_capability_claims_are_conservative(self):
        with patch.dict(os.environ, {}, clear=True):
            status = kimi_provider.configuration_status()
        self.assertFalse(status["consumer_deep_research_api_available"])
        self.assertTrue(status["deep_research_via_k3_orchestration"])
        self.assertTrue(status["json_mode"])
        self.assertTrue(status["formula_web_search_supported"])

    def test_document_manifest_never_contains_source_text(self):
        secret = "TOP SECRET SOURCE TEXT THAT MUST NOT PERSIST"
        docs = kimi_research.normalize_documents(
            [
                {
                    "title": "Authorized Research",
                    "institution": "Test Bank",
                    "content": secret,
                    "access_tier": "AUTHORIZED_USER_SUPPLIED",
                }
            ]
        )
        manifest = kimi_research.document_manifest(docs[0])
        self.assertNotIn("content", manifest)
        self.assertFalse(manifest["full_text_persisted"])
        self.assertNotIn(secret, json.dumps(manifest))
        self.assertTrue(manifest["content_hash"])

    def test_parallel_research_persists_only_normalized_analysis(self):
        secret = "TOP SECRET SOURCE TEXT THAT MUST NOT PERSIST"
        provider_status = {
            "configured": True,
            "credential_present": True,
            "credential_exposed": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        worker = {
            "status": "CAPTURED",
            "model": "kimi-k3",
            "output": WORKER_OUTPUT,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        synthesis = {
            "status": "CAPTURED",
            "model": "kimi-k3",
            "output": SYNTHESIS_OUTPUT,
            "usage": {"prompt_tokens": 50, "completion_tokens": 25},
        }
        with patch.object(kimi_research.kimi_provider, "configuration_status", return_value=provider_status), patch.object(
            kimi_research.kimi_provider,
            "chat_json",
            side_effect=[worker, synthesis],
        ), patch.object(kimi_research, "record_object") as record_object, patch.object(
            kimi_research, "record_event"
        ):
            result = kimi_research.run_research(
                {
                    "case_id": "case_test",
                    "objective": "Test research",
                    "documents": [
                        {
                            "title": "Public Research Note",
                            "institution": "Test Bank",
                            "source_url": "https://example.test/report",
                            "content": secret,
                        }
                    ],
                }
            )

        self.assertEqual(result["status"], "COMPLETE")
        packet = result["packet"]
        self.assertFalse(packet["full_report_persisted"])
        self.assertTrue(packet["normalized_analysis_only"])
        self.assertTrue(packet["context_only"])
        self.assertFalse(packet["qualification_evidence"])
        self.assertFalse(packet["gap_resolution_eligible"])
        self.assertFalse(packet["fact_resolution_authority"])
        self.assertFalse(packet["committee_override"])
        self.assertFalse(packet["capital_authority"])
        self.assertFalse(packet["trade_signal"])
        self.assertFalse(packet["auto_trade_authority"])
        self.assertFalse(packet["paper_order_permission"])
        self.assertFalse(packet["trade_execution_permission"])
        self.assertFalse(packet["live_execution"])
        self.assertNotIn(secret, json.dumps(packet, default=str))
        self.assertTrue(record_object.called)

    def test_unconfigured_provider_fails_closed_without_inventing_analysis(self):
        with patch.object(
            kimi_research.kimi_provider,
            "configuration_status",
            return_value={"configured": False, "credential_present": False},
        ):
            result = kimi_research.run_research(
                {
                    "documents": [
                        {"title": "Source", "content": "Some research text"}
                    ]
                }
            )
        self.assertEqual(result["status"], "PROVIDER_NOT_CONFIGURED")
        self.assertFalse(result["full_report_persisted"])
        self.assertFalse(result["live_execution"])

    def test_kimi_context_can_never_resolve_evidence_gap(self):
        packet = {
            "kimi_research_packet_id": "kimi_research_test",
            "created_at": "2026-08-26T00:00:00+00:00",
            "synthesis": SYNTHESIS_OUTPUT,
        }
        with patch.object(kimi_research, "list_objects", return_value=[packet]):
            items = kimi_research.kimi_research_evidence("case_test")
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

    def test_native_swarm_bridge_requires_explicit_local_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            status = kimi_swarm_bridge.configuration_status()
            result = kimi_swarm_bridge.run_native_swarm(prompt="Research these two items")
        self.assertFalse(status["configured"])
        self.assertFalse(status["repo_write_access_granted"])
        self.assertEqual(result["status"], "SOURCE_NOT_CONFIGURED")
        self.assertFalse(result["live_execution"])

    def test_native_swarm_status_never_exposes_token(self):
        with patch.dict(
            os.environ,
            {
                "IIOS_KIMI_CODE_SERVER_URL": "http://127.0.0.1:58627",
                "IIOS_KIMI_CODE_SERVER_TOKEN": "secret-local-token",
            },
            clear=False,
        ):
            status = kimi_swarm_bridge.configuration_status()
            rendered = repr(status)
        self.assertTrue(status["configured"])
        self.assertTrue(status["server_host_approved"])
        self.assertFalse(status["credential_exposed"])
        self.assertNotIn("secret-local-token", rendered)


if __name__ == "__main__":
    unittest.main()
