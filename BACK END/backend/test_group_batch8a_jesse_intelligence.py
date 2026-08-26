import unittest
from dislocation_intelligence import financial_strength_score, rebound_assessment
from institutional_research_intelligence import aggregate_sector_sentiment
from macro_policy_intelligence import analyze_tariff_text, policy_distribution_summary
from thesis_integrity_v2 import classify_integrity

class GroupBatch8ATests(unittest.TestCase):
    def test_sector_sentiment(self):
        rows=[{"institution":"JPMorgan","published_at":"2099-01-01T00:00:00+00:00","sector_views":[{"sector":"SEMICONDUCTOR","sentiment":"FAVORABLE","conviction":.9}]},
              {"institution":"Deutsche Bank","published_at":"2099-01-01T00:00:00+00:00","sector_views":[{"sector":"SEMICONDUCTOR","sentiment":"FAVORABLE","conviction":.7}]}]
        r=aggregate_sector_sentiment(rows,sector="SEMICONDUCTOR"); self.assertEqual(r["sectors"][0]["sentiment"],"FAVORABLE"); self.assertEqual(r["sectors"][0]["institution_count"],2)
    def test_fed_probs(self):
        r=policy_distribution_summary({"CUT_25":70,"HOLD":25,"CUT_50":5}); self.assertEqual(r["most_likely_scenario"],"CUT_25"); self.assertAlmostEqual(sum(r["probabilities"].values()),1,places=5)
    def test_tariff_two_sided(self):
        r=analyze_tariff_text("US announces tariff on imported steel and aluminum."); impacts={(x["sector"],x["direction"]) for x in r["sector_impacts"]}
        self.assertIn(("DOMESTIC_METALS","FAVORABLE"),impacts); self.assertIn(("AUTOS_EV","UNFAVORABLE"),impacts)
    def test_financial_strength(self):
        s,reasons=financial_strength_score({"current_ratio":2,"debt_to_equity":50,"free_cash_flow":1000,"operating_cash_flow":1500,
                                            "profit_margin":.2,"return_on_equity":.22,"revenue_growth":.1,"earnings_growth":.12,"eps_ttm":5})
        self.assertGreaterEqual(s,75); self.assertIn("POSITIVE_FCF",reasons)
    def test_rebound_uncalibrated(self):
        r=rebound_assessment(90,-8,"POSSIBLE_TEMPORARY_DISLOCATION"); self.assertFalse(r["probability_calibrated"])
    def test_early_not_wrong(self):
        r=classify_integrity(thesis_status="INTACT",flags=[],observed_return_pct=-45); self.assertEqual(r["thesis_integrity_state"],"EARLY_BUT_INTACT"); self.assertFalse(r["price_alone_can_break_thesis"])
    def test_falsifier_break(self):
        r=classify_integrity(thesis_status="INTACT",flags=["FALSIFIER_TRIGGERED"],observed_return_pct=-3); self.assertEqual(r["thesis_integrity_state"],"THESIS_BROKEN")

if __name__=="__main__": unittest.main()
