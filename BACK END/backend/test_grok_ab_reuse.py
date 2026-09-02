import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import grok_ab_reuse as reuse


class GrokABReuseTests(unittest.TestCase):
    def test_validated_context_requires_verified_admitted_and_locked_context(self):
        valid = {
            "grok_social_context_id": "grok_social_1",
            "citation_count": 54,
            "admitted_count": 5,
            "items_by_agent": {"skeptic": [{"claim": "x"}]},
            "qualification_evidence": False,
            "capital_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        with patch.object(reuse, "latest_object", return_value=valid):
            result = reuse.validated_latest_context("case_1")
        self.assertEqual(result["admitted_count"], 5)

        unsafe = {**valid, "capital_authority": True}
        with patch.object(reuse, "latest_object", return_value=unsafe):
            with self.assertRaises(ValueError):
                reuse.validated_latest_context("case_1")

    def test_fresh_base_evidence_is_public_nonstale_and_does_not_mutate_case(self):
        case = {"case_id": "case_1", "topic": "LLY research"}
        profile = {
            "ticker": "LLY",
            "source_requests": [{"source": "gdelt_news", "params": {"query": "LLY"}}],
        }
        fresh_item = {
            "source": "GDELT",
            "source_type": "news_aggregator",
            "evidence_type": "news",
            "title": "Fresh LLY headline",
            "claim": "Fresh LLY headline",
            "timestamp": reuse.utc_now(),
            "reliability_score": 0.55,
        }
        quote_item = {
            "source": "Yahoo Finance",
            "source_type": "market_data",
            "evidence_type": "market_data",
            "title": "LLY market snapshot",
            "claim": "LLY price=1",
            "timestamp": reuse.utc_now(),
            "reliability_score": 0.78,
        }

        def latest(object_type, *, case_id=None, topic=None):
            return profile if object_type == "monitor_profile" else None

        with patch.object(reuse, "get_object", return_value=case), \
             patch.object(reuse, "latest_object", side_effect=latest), \
             patch.object(reuse.source_ingestion, "ingest_sources", return_value={
                 "evidence_items": [fresh_item],
                 "successful_sources": 1,
                 "failed_sources": 0,
             }), \
             patch.object(reuse, "fetch_market_quote", return_value={
                 "status": "ok",
                 "items": [quote_item],
                 "provider": "Yahoo Finance",
                 "current_price": 1.0,
                 "error": None,
             }):
            result = reuse.build_fresh_base_evidence("case_1")

        self.assertEqual(result["mode"], reuse.FRESH_BASE_EVIDENCE_MODE)
        self.assertGreaterEqual(result["packet"]["summary"]["evidence_count"], 1)
        self.assertNotIn("ALL_EVIDENCE_STALE", result["packet"]["summary"].get("critical_flags") or [])
        self.assertFalse(result["live_case_evidence_mutated"])
        self.assertEqual(result["new_xai_search_calls"], 0)

    def test_patch_snapshot_changes_only_snapshot_case_evidence(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "snapshot.db"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE ledger_objects (object_id TEXT PRIMARY KEY, object_type TEXT, case_id TEXT, parent_id TEXT, topic TEXT, payload_json TEXT, created_at TEXT)"
            )
            original = {"case_id": "case_1", "topic": "LLY", "evidence": [{"claim": "old"}]}
            connection.execute(
                "INSERT INTO ledger_objects VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("case_1", "case", "case_1", None, "LLY", json.dumps(original), "2026-01-01T00:00:00+00:00"),
            )
            connection.commit()
            connection.close()

            packet = {
                "items": [{"claim": "fresh", "timestamp": reuse.utc_now()}],
                "summary": {"evidence_count": 1, "critical_flags": []},
            }
            reuse.patch_snapshot_case_evidence(path, "case_1", packet)

            connection = sqlite3.connect(path)
            row = connection.execute("SELECT payload_json FROM ledger_objects WHERE object_id='case_1'").fetchone()
            connection.close()
            payload = json.loads(row[0])
            self.assertEqual(payload["evidence"][0]["claim"], "fresh")
            self.assertEqual(payload["ab_base_evidence_mode"], reuse.FRESH_BASE_EVIDENCE_MODE)

    def test_plan_guarantees_zero_new_xai_search_calls_and_no_execution(self):
        plan = reuse.grok_ab_reuse_plan()
        self.assertEqual(plan["new_xai_search_calls"], 0)
        self.assertTrue(plan["requires_existing_verified_context"])
        self.assertTrue(plan["fresh_base_evidence_option"])
        self.assertFalse(plan["fresh_base_evidence_live_case_mutation"])
        self.assertTrue(plan["fresh_base_evidence_same_packet_for_both_arms"])
        self.assertFalse(plan["architecture_promotion_automatic"])
        self.assertFalse(plan["auto_trade_authority"])
        self.assertFalse(plan["paper_order_permission"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])


if __name__ == "__main__":
    unittest.main()
