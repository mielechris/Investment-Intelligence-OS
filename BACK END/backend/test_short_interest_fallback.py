import unittest

from short_interest_fallback import parse_nasdaq_short_interest


class ShortInterestFallbackTests(unittest.TestCase):
    def test_parser_extracts_latest_nasdaq_row_and_prior(self):
        payload = {
            "data": {
                "shortInterestTable": {
                    "rows": [
                        {
                            "settlementDate": "08/14/2026",
                            "interest": "29,892,897",
                            "avgDailyShareVolume": "49,821,495",
                            "daysToCover": "0.60",
                        },
                        {
                            "settlementDate": "07/31/2026",
                            "interest": "31,250,000",
                            "avgDailyShareVolume": "48,000,000",
                            "daysToCover": "0.65",
                        },
                    ]
                }
            }
        }
        parsed = parse_nasdaq_short_interest(payload)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["settlement_date"], "2026-08-14")
        self.assertEqual(parsed["current_short"], 29_892_897)
        self.assertEqual(parsed["previous_short"], 31_250_000)
        self.assertEqual(parsed["avg_daily_volume"], 49_821_495)
        self.assertAlmostEqual(parsed["days_to_cover"], 0.60)
        self.assertAlmostEqual(parsed["change_percent"], -4.3427296, places=3)

    def test_parser_accepts_alternate_exchange_field_names(self):
        payload = {
            "data": {
                "rows": [
                    {
                        "settlement_date": "2026-08-14",
                        "currentShortPositionQuantity": 1000,
                        "previousShortPositionQuantity": 800,
                        "averageDailyVolumeQuantity": 500,
                        "daysToCoverQuantity": 2.0,
                        "changePercent": 25.0,
                    }
                ]
            }
        }
        parsed = parse_nasdaq_short_interest(payload)
        self.assertEqual(parsed["current_short"], 1000)
        self.assertEqual(parsed["previous_short"], 800)
        self.assertEqual(parsed["change_percent"], 25.0)

    def test_parser_rejects_payload_without_short_interest_rows(self):
        self.assertIsNone(parse_nasdaq_short_interest({"data": {"rows": [{"foo": "bar"}]}}))


if __name__ == "__main__":
    unittest.main()
