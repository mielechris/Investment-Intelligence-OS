import unittest

from institutional_secondary_fallback import (
    parse_marketbeat_analyst,
    parse_marketbeat_catalyst,
    parse_marketbeat_options,
    parse_marketbeat_ownership,
    parse_marketbeat_short_interest,
)


class InstitutionalSecondaryFallbackTests(unittest.TestCase):
    def test_ownership_parser_preserves_13f_lag_context(self):
        text = """
        Current Institutional Ownership Percentage 80.84%
        Number of Institutional Buyers (last 12 months) 2363
        Total Institutional Inflows (last 12 months) $119.92B
        Number of Institutional Sellers (last 12 months) 1201
        Total Institutional Outflows (last 12 months) $23.07B
        Reporting Date 8/17/2026
        """
        parsed = parse_marketbeat_ownership("", text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["directional_context"], "ACCUMULATION_BIAS")
        self.assertIn("lagged", parsed["summary"].lower())
        self.assertEqual(parsed["details"]["institutional_ownership_pct"], 80.84)

    def test_analyst_parser_labels_fallback_scope_honestly(self):
        text = "Consensus Rating Buy Based on 39 Analyst Ratings Consensus Price Target $1,261.26 30.46% Upside"
        html = """
        <table>
          <tr><td>8/21/2026</td><td>BMO</td><td></td><td>Initiated Coverage</td><td>Outperform</td><td>$1,300</td></tr>
          <tr><td>8/19/2026</td><td>Zacks</td><td></td><td>Downgrade</td><td>Strong-Buy to Hold</td><td></td></tr>
          <tr><td>8/14/2026</td><td>New Street</td><td></td><td>Upgrade</td><td>Neutral to Buy</td><td>$1,250</td></tr>
        </table>
        """
        parsed = parse_marketbeat_analyst(html, text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["details"]["consensus_rating"].lower(), "buy")
        self.assertIn("not true eps-estimate", parsed["details"]["fallback_scope"].lower())

    def test_short_interest_parser(self):
        text = """
        Current Short Interest 29,892,897 shares
        Previous Short Interest 36,211,849 shares
        Change Vs. Previous Month -17.45%
        Short Interest Ratio 0.6 Days to Cover
        Last Record Date July 31, 2026
        Short Percent of Float 2.65%
        """
        parsed = parse_marketbeat_short_interest("", text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["directional_context"], "SHORTS_DECREASING")
        self.assertEqual(parsed["details"]["shares_short"], 29892897)

    def test_options_parser_uses_future_expiry_only(self):
        html = """
        <table>
          <tr><td>8/28/2026</td><td>$900</td><td>$10</td><td>Call</td><td>100</td><td>0</td><td>0</td><td>200</td></tr>
          <tr><td>8/28/2026</td><td>$900</td><td>$8</td><td>Put</td><td>50</td><td>0</td><td>0</td><td>300</td></tr>
        </table>
        """
        parsed = parse_marketbeat_options(html, "")
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed["details"]["put_call_open_interest_ratio"], 1.5)
        self.assertEqual(parsed["directional_context"], "PUT_HEAVY")

    def test_catalyst_parser_marks_date_estimated(self):
        text = "Micron Technology's next earnings date is estimated for Tuesday, September 22nd, 2026 based on past reporting schedules."
        parsed = parse_marketbeat_catalyst("", text)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["details"]["estimated_not_confirmed"])
        self.assertIn("2026-09-22", parsed["details"]["next_earnings"])


if __name__ == "__main__":
    unittest.main()
