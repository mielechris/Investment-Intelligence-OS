import unittest

from options_positioning_occ import parse_occ_open_interest_csv


class OCCOptionsPositioningTests(unittest.TestCase):
    def test_parser_aggregates_call_and_put_open_interest_for_symbol(self):
        text = """Underlying Symbol,Call/Put,Expiration Date,Strike Price,Open Interest
MU,CALL,09/18/2026,900,1000
MU,PUT,09/18/2026,900,700
MU,C,10/16/2026,950,500
MU,P,10/16/2026,950,800
NVDA,CALL,09/18/2026,200,9999
"""
        parsed = parse_occ_open_interest_csv(text, "MU", report_date="2026-08-21")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["call_open_interest"], 1500)
        self.assertEqual(parsed["put_open_interest"], 1500)
        self.assertEqual(parsed["put_call_oi_ratio"], 1.0)
        self.assertEqual(parsed["positioning_bias"], "BALANCED")
        self.assertEqual(parsed["series_count"], 4)
        self.assertEqual(parsed["nearest_expiry"], "2026-09-18")

    def test_parser_labels_call_heavy_without_treating_it_as_buy_signal(self):
        text = """Product Symbol,Option Type,Contract Date,Open Interest
MU,CALL,2026-09-18,2000
MU,PUT,2026-09-18,1000
"""
        parsed = parse_occ_open_interest_csv(text, "MU", report_date="2026-08-21")
        self.assertEqual(parsed["put_call_oi_ratio"], 0.5)
        self.assertEqual(parsed["positioning_bias"], "CALL_HEAVY")

    def test_parser_requires_explicit_call_put_side(self):
        text = """Underlying Symbol,Option Symbol,Open Interest
MU,MU260918C00900000,1000
MU,MU260918P00900000,1000
"""
        self.assertIsNone(parse_occ_open_interest_csv(text, "MU", report_date="2026-08-21"))


if __name__ == "__main__":
    unittest.main()
