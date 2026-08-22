import unittest
from datetime import datetime, timedelta, timezone

from evidence_engine import build_packet, normalize_item


class EvidenceEngineTests(unittest.TestCase):
    def test_official_fresh_evidence_scores_high(self):
        now = datetime.now(timezone.utc)
        item = normalize_item({
            "claim": "Federal Reserve released a policy statement",
            "source": "Federal Reserve",
            "url": "https://www.federalreserve.gov/example",
            "evidence_type": "policy",
            "observed_at": now.isoformat(),
        }, now=now)
        self.assertEqual(item["source_type"], "official")
        self.assertFalse(item["stale"])
        self.assertGreaterEqual(item["reliability_score"], 0.9)
        self.assertGreaterEqual(item["quality_score"], 0.9)

    def test_stale_market_data_is_flagged(self):
        now = datetime.now(timezone.utc)
        item = normalize_item({
            "claim": "Price snapshot",
            "source": "test market feed",
            "evidence_type": "market_data",
            "source_type": "market_data",
            "observed_at": (now - timedelta(hours=3)).isoformat(),
        }, now=now)
        self.assertTrue(item["stale"])
        self.assertEqual(item["freshness_score"], 0.0)

    def test_conflicting_packet_is_detected(self):
        now = datetime.now(timezone.utc).isoformat()
        packet = build_packet([
            {"claim":"Demand accelerating","source":"source-a","observed_at":now,"conflict_group":"demand","stance":"bullish"},
            {"claim":"Demand slowing","source":"source-b","observed_at":now,"conflict_group":"demand","stance":"bearish"},
        ])
        self.assertEqual(packet["summary"]["conflict_count"], 1)
        self.assertIn("CONFLICTING_EVIDENCE_PRESENT", packet["summary"]["critical_flags"])

    def test_empty_packet_is_explicitly_flagged(self):
        packet = build_packet([])
        self.assertEqual(packet["summary"]["evidence_count"], 0)
        self.assertIn("NO_EVIDENCE_SUPPLIED", packet["summary"]["critical_flags"])


if __name__ == "__main__":
    unittest.main()
