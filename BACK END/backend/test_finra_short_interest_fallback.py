import unittest

from finra_short_interest_fallback import parse_finra_short_interest


class FinraShortInterestFallbackTests(unittest.TestCase):
    def test_parser_selects_latest_symbol_row(self):
        payload = [
            {
                "symbolCode": "MU",
                "settlementDate": "2026-07-15",
                "currentShortPositionQuantity": 32000000,
                "previousShortPositionQuantity": 30000000,
                "averageDailyVolumeQuantity": 18000000,
                "daysToCoverQuantity": 1.78,
                "changePercent": 6.67,
                "marketClassCode": "NMS",
            },
            {
                "symbolCode": "MU",
                "settlementDate": "2026-07-31",
                "currentShortPositionQuantity": 29892897,
                "previousShortPositionQuantity": 32000000,
                "averageDailyVolumeQuantity": 20500000,
                "daysToCoverQuantity": 1.46,
                "changePercent": -6.5847,
                "marketClassCode": "NMS",
            },
            {
                "symbolCode": "AAPL",
                "settlementDate": "2026-07-31",
                "currentShortPositionQuantity": 100,
            },
        ]
        parsed = parse_finra_short_interest(payload, "MU")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["settlement_date"], "2026-07-31")
        self.assertEqual(parsed["current_short"], 29892897)
        self.assertEqual(parsed["previous_short"], 32000000)
        self.assertEqual(parsed["avg_daily_volume"], 20500000)
        self.assertEqual(parsed["days_to_cover"], 1.46)
        self.assertAlmostEqual(parsed["change_percent"], -6.5847)

    def test_parser_derives_change_and_days_to_cover(self):
        payload = [
            {
                "symbolCode": "MU",
                "settlementDate": "2026-07-31",
                "currentShortPositionQuantity": 30000000,
                "previousShortPositionQuantity": 25000000,
                "averageDailyVolumeQuantity": 20000000,
            }
        ]
        parsed = parse_finra_short_interest(payload, "MU")
        self.assertEqual(parsed["change_percent"], 20.0)
        self.assertEqual(parsed["days_to_cover"], 1.5)

    def test_parser_rejects_other_symbol(self):
        payload = [{"symbolCode": "AAPL", "settlementDate": "2026-07-31", "currentShortPositionQuantity": 10}]
        self.assertIsNone(parse_finra_short_interest(payload, "MU"))


if __name__ == "__main__":
    unittest.main()
