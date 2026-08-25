import unittest

import ipo_monitoring as ipo


ATOM = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <entry>
    <title>Example Corp (CIK 0000000001) (S-1)</title>
    <updated>2026-08-24T20:00:00-04:00</updated>
    <summary>Initial registration statement</summary>
    <link href='https://www.sec.gov/Archives/edgar/data/1/example.htm'/>
  </entry>
</feed>
"""


class IpoMonitoringTests(unittest.TestCase):
    def test_atom_parser_creates_research_only_official_filing(self):
        rows = ipo.parse_atom_filings(ATOM, form_type="S-1", observed_at="2026-08-25T00:00:00+00:00")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row["ipo_filing_id"].startswith("ipo_filing_"))
        self.assertEqual(row["form_type"], "S-1")
        self.assertEqual(row["source"], "SEC EDGAR")
        self.assertEqual(row["source_type"], "official_filing")
        self.assertFalse(row["trade_signal"])
        self.assertFalse(row["auto_trade_authority"])
        self.assertFalse(row["trade_execution_permission"])
        self.assertFalse(row["live_execution"])

    def test_filing_id_is_deterministic(self):
        first = ipo.parse_atom_filings(ATOM, form_type="S-1")[0]["ipo_filing_id"]
        second = ipo.parse_atom_filings(ATOM, form_type="S-1")[0]["ipo_filing_id"]
        self.assertEqual(first, second)

    def test_plan_requires_manual_promotion_and_manual_agent_run(self):
        plan = ipo.ipo_monitor_plan()
        self.assertFalse(plan["automatic_scan"])
        self.assertFalse(plan["automatic_promotion"])
        self.assertFalse(plan["automatic_agent_run"])
        self.assertEqual(plan["promotion_target"], "STANDARD_IIOS_GOVERNED_CASE")
        self.assertFalse(plan["auto_trade_authority"])
        self.assertFalse(plan["paper_order_permission"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])

    def test_promoted_evidence_is_sec_only_and_nonexecuting(self):
        filing = ipo.parse_atom_filings(ATOM, form_type="S-1")[0]
        evidence = ipo._filing_evidence(filing)
        self.assertEqual(evidence["source"], "SEC EDGAR")
        self.assertEqual(evidence["form"], "S-1")
        self.assertEqual(evidence["reliability_score"], 0.99)


if __name__ == "__main__":
    unittest.main()
