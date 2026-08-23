import unittest

import insider_secondary_fallback as secondary


SAMPLE = """
<table>
<tr><th>Transaction Date</th><th>Insider</th><th>Buy/Sell</th><th>Number of Shares</th><th>Average Share Price</th><th>Total Transaction</th><th>Details</th></tr>
<tr><td>7/24/2026</td><td>Sanjay Mehrotra CEO</td><td>Sell</td><td>8,715</td><td>$951.72</td><td>$8,294,239.80</td><td>Details</td></tr>
<tr><td>6/12/2026</td><td>Sample Director Director</td><td>Buy</td><td>1,000</td><td>$800.00</td><td>$800,000.00</td><td>Details</td></tr>
</table>
"""


class InsiderSecondaryFallbackTests(unittest.TestCase):
    def test_parses_buy_and_sell_as_context_only(self):
        records = secondary.parse_marketbeat_insider_rows(SAMPLE, ticker="MU")
        self.assertEqual(len(records), 2)
        sale = records[0]
        buy = records[1]
        self.assertEqual(sale["transaction_nature"], "OPEN_MARKET_SALE")
        self.assertEqual(sale["reporting_owner"], "Sanjay Mehrotra")
        self.assertEqual(sale["reporting_owner_role"], "CEO")
        self.assertEqual(sale["shares"], 8715.0)
        self.assertAlmostEqual(sale["price_per_share"], 951.72)
        self.assertEqual(sale["admission_status"], "CONTEXT_ONLY")
        self.assertTrue(sale["requires_primary_corroboration"])
        self.assertEqual(buy["transaction_nature"], "OPEN_MARKET_PURCHASE")
        self.assertEqual(buy["transaction_date"], "2026-06-12")

    def test_secondary_never_claims_primary_filing(self):
        record = secondary.parse_marketbeat_insider_rows(SAMPLE, ticker="MU")[0]
        self.assertEqual(record["form"], "SECONDARY")
        self.assertEqual(record["source_type"], "secondary_public_aggregator")
        self.assertTrue(record["secondary_source"])
        self.assertIsNone(record["accession_number"])


if __name__ == "__main__":
    unittest.main()
