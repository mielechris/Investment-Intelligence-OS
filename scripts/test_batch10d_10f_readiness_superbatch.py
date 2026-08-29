from __future__ import annotations

import unittest

import iios_capital_preservation_stress_lab as stress
import iios_governed_capital_readiness as readiness
import iios_institutional_investment_firm_os as firm


class Batch10ReadinessSuperbatchTest(unittest.TestCase):
    def test_cash_only_book_stays_not_ready_for_live_capital(self) -> None:
        portfolio={"nav":10000.0,"position_count":0,"positions":[]}
        s=stress.build_stress(portfolio=portfolio,regime={"regime_label":"BIDIRECTIONAL_HIGH_DISPERSION"})
        q={"status":"INSUFFICIENT_PAPER_SAMPLE"}
        r=readiness.build_readiness(qualification=q,stress=s)
        f=firm.build_firm_os(readiness=r,qualification=q,portfolio=portfolio,regime={"regime_label":"BIDIRECTIONAL_HIGH_DISPERSION"})
        self.assertEqual(s["status"],"CASH_ONLY_NO_MARKET_STRESS_EXPOSURE")
        self.assertEqual(r["status"],"NOT_READY_FOR_LIVE_CAPITAL")
        self.assertGreater(r["unresolved_gate_count"],0)
        self.assertIn("LIVE_CAPITAL_NOT_AUTHORIZED",f["status"])
        self.assertFalse(r["safety"]["auto_enable_live"])
        self.assertFalse(f["safety"]["capital_authority"])

    def test_stress_scenarios_are_hypothetical_not_forecasts_or_orders(self) -> None:
        p={"nav":10000.0,"positions":[{"ticker":"A","direction":"LONG","market_value":5000.0},{"ticker":"B","direction":"SHORT","market_value":2000.0}]}
        s=stress.build_stress(portfolio=p)
        self.assertTrue(s["scenarios"])
        self.assertTrue(all(row["deterministic_hypothetical"] is True and row["forecast"] is False for row in s["scenarios"]))
        self.assertFalse(s["safety"]["auto_reduce_exposure"])
        self.assertFalse(s["safety"]["trade_execution_permission"])

    def test_even_paper_qualified_state_keeps_manual_capital_gates(self) -> None:
        q={"status":"PAPER_QUALIFIED_FOR_HUMAN_READINESS_REVIEW"}
        s={"worst_scenario":{"estimated_nav_change_pct":-4.0}}
        r=readiness.build_readiness(qualification=q,stress=s)
        self.assertTrue(r["paper_qualification_passed"])
        self.assertEqual(r["status"],"NOT_READY_FOR_LIVE_CAPITAL")
        manual=[row for row in r["gates"] if row["state"]=="UNRESOLVED_MANUAL_GATE"]
        self.assertGreaterEqual(len(manual),5)
        self.assertFalse(r["safety"]["auto_connect_broker"])
        self.assertFalse(r["safety"]["auto_fund_account"])
        self.assertFalse(r["safety"]["live_execution"])


if __name__=="__main__":unittest.main()
