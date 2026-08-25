import unittest

from valuation_market_micron_filing_fallback import (
    MICRON_Q3_2026_DILUTED_SHARES_M,
    derive_ttm_pe,
    micron_ttm_eps,
)


class MicronValuationFilingFallbackTests(unittest.TestCase):
    def test_filing_backed_ttm_eps_formula(self):
        self.assertAlmostEqual(micron_ttm_eps(), 44.24, places=2)

    def test_ttm_pe_derivation_uses_admitted_market_price(self):
        self.assertAlmostEqual(derive_ttm_pe(963.2), 21.7722, places=4)

    def test_q3_diluted_share_count_is_filing_value(self):
        self.assertEqual(MICRON_Q3_2026_DILUTED_SHARES_M, 1145.0)


if __name__ == "__main__":
    unittest.main()
