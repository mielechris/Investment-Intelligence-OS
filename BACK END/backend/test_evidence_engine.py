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

    def test_current_quarterly_filing_remains_high_quality(self):
        now = datetime.now(timezone.utc)
        item = normalize_item({
            "claim": "Filed quarterly results quantify average selling price sensitivity",
            "source": "Micron Form 10-Q",
            "url": "https://investors.micron.com/q3-10q.pdf",
            "source_type": "filing",
            "evidence_type": "quarterly_filing",
            "observed_at": (now - timedelta(days=170)).isoformat(),
            "reliability_score": 0.995,
        }, now=now)
        self.assertFalse(item["stale"])
        self.assertEqual(item["freshness_window_hours"], 24 * 180)
        self.assertGreaterEqual(item["freshness_score"], 0.75)
        self.assertGreaterEqual(item["quality_score"], 0.65)

    def test_current_quarterly_company_material_remains_high_quality(self):
        now = datetime.now(timezone.utc)
        item = normalize_item({
            "claim": "Micron reports HBM4 revenue and high-volume shipments",
            "source": "Micron quarterly prepared remarks",
            "url": "https://investors.micron.com/q3-prepared-remarks",
            "source_type": "company",
            "evidence_type": "quarterly_company",
            "observed_at": (now - timedelta(days=170)).isoformat(),
            "reliability_score": 0.99,
        }, now=now)
        self.assertFalse(item["stale"])
        self.assertGreaterEqual(item["freshness_score"], 0.75)
        self.assertGreaterEqual(item["quality_score"], 0.65)

    def test_latest_annual_filing_remains_high_quality_until_next_cycle(self):
        now = datetime.now(timezone.utc)
        item = normalize_item({
            "claim": "Micron Form 10-K identifies HBM as a higher-margin product contributing to DRAM margin improvement",
            "source": "Micron Form 10-K",
            "url": "https://www.sec.gov/Archives/edgar/data/723125/example.htm",
            "source_type": "filing",
            "evidence_type": "annual_filing",
            "observed_at": (now - timedelta(days=330)).isoformat(),
            "reliability_score": 0.995,
        }, now=now)
        self.assertFalse(item["stale"])
        self.assertEqual(item["freshness_window_hours"], 24 * 400)
        self.assertGreaterEqual(item["freshness_score"], 0.75)
        self.assertGreaterEqual(item["quality_score"], 0.65)

    def test_current_annual_company_disclosure_remains_high_quality(self):
        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        item = normalize_item({
            "claim": "Micron states its HBM customer base expanded to six customers.",
            "source": "Micron Fiscal Q4 2025 Prepared Remarks",
            "url": "https://investors.micron.com/static-files/5ea95475-639b-4cfc-91fd-b9b4a2bb5e63",
            "source_type": "company",
            "evidence_type": "annual_company",
            "observed_at": "2025-09-23T00:00:00+00:00",
            "reliability_score": 0.99,
        }, now=now)
        self.assertFalse(item["stale"])
        self.assertEqual(item["freshness_window_hours"], 24 * 400)
        self.assertGreaterEqual(item["quality_score"], 0.65)

    def test_current_monthly_official_data_remains_high_quality(self):
        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        item = normalize_item({
            "claim": "U.S. semiconductor industrial production index=191.8973",
            "source": "Federal Reserve / FRED",
            "url": "https://fred.stlouisfed.org/series/IPG3344S",
            "source_type": "official",
            "evidence_type": "monthly_official",
            "observed_at": "2026-07-01",
            "reliability_score": 0.99,
        }, now=now)
        self.assertFalse(item["stale"])
        self.assertEqual(item["freshness_window_hours"], 24 * 90)
        self.assertGreaterEqual(item["quality_score"], 0.65)

    def test_quarterly_evidence_expires_after_window(self):
        now = datetime.now(timezone.utc)
        item = normalize_item({
            "claim": "Old quarterly company evidence",
            "source": "Company IR",
            "source_type": "company",
            "evidence_type": "quarterly_company",
            "observed_at": (now - timedelta(days=181)).isoformat(),
            "reliability_score": 0.99,
        }, now=now)
        self.assertTrue(item["stale"])
        self.assertEqual(item["freshness_score"], 0.0)

    def test_occ_options_remains_high_quality_across_weekend(self):
        now = datetime(2026, 8, 24, 5, 5, tzinfo=timezone.utc)
        item = normalize_item({
            "claim": "MU OCC options positioning with call and put open interest",
            "source": "OCC options open interest · user verified",
            "url": "https://www.theocc.com/market-data/example",
            "source_type": "market_data",
            "evidence_type": "options",
            "observed_at": "2026-08-21",
            "reliability_score": 0.97,
        }, now=now)
        self.assertFalse(item["stale"])
        self.assertEqual(item["freshness_window_hours"], 24 * 4)
        self.assertGreaterEqual(item["freshness_score"], 0.75)
        self.assertGreaterEqual(item["quality_score"], 0.65)

    def test_governed_options_fact_overrides_generic_market_data_freshness(self):
        now = datetime(2026, 8, 24, 5, 23, tzinfo=timezone.utc)
        item = normalize_item({
            "claim": "MU OCC options positioning as of 2026-08-21: call OI=1682816; put OI=1965042; put/call OI=1.1677; bias=BALANCED.",
            "source": "OCC options open interest · user verified",
            "url": "https://www.theocc.com/market-data/market-data-reports/series-and-trading-data/series-search?symbol=mu&symbolType=U",
            "source_type": "market_data",
            "evidence_type": "market_data",
            "primary_fact_key": "options",
            "observed_at": "2026-08-21",
            "reliability_score": 0.97,
        }, now=now)
        self.assertEqual(item["evidence_type"], "options")
        self.assertFalse(item["stale"])
        self.assertEqual(item["freshness_window_hours"], 24 * 4)
        self.assertGreaterEqual(item["quality_score"], 0.65)

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
