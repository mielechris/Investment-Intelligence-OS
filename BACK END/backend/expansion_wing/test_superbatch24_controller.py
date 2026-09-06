from __future__ import annotations
import unittest
from pathlib import Path
from .tuesday_controller import (AUTHORITY, CreditGovernor, GATE_ORDER, PHASES, PILOTS, SCENARIOS,
    TuesdayPhaseMachine, credential_gate_trace, monday_holiday_rehearsal, post_close_report,
    rehearsal_matrix, service_contract)

class ControllerTests(unittest.TestCase):
    def test_fixed_registry(self):
        self.assertEqual(PILOTS, ("MU","SPY","XLK","VNQ","TLT","GLD","UUP","IBIT","PFF","BIL"))
    def test_holiday_zero_activity(self):
        value=monday_holiday_rehearsal(); self.assertEqual(value["market"],"CLOSED_HOLIDAY")
        self.assertTrue(all(value[k]==0 for k in ("provider_requests","credits","keychain_access","candidates","synthetic_observations","operational_positions","orders","fills","projection_mutations")))
    def test_exact_phase_machine_and_no_skip(self):
        self.assertEqual(len(PHASES),12); machine=TuesdayPhaseMachine(controller_enabled=True)
        self.assertEqual(machine.advance("OPENING_EVIDENCE_COLLECTION",actor="OWNER"),"FAILED_CLOSED")
    def test_all_review_phases_require_owner(self):
        for target in ("HUMAN_CANDIDATE_REVIEW","COMMITTEE_REVIEW","RISK_REVIEW"):
            prior={"HUMAN_CANDIDATE_REVIEW":"OPENING_EVIDENCE_COLLECTION","COMMITTEE_REVIEW":"HUMAN_CANDIDATE_REVIEW","RISK_REVIEW":"COMMITTEE_REVIEW"}[target]
            machine=TuesdayPhaseMachine(prior,True,[prior]); self.assertEqual(machine.advance(target,actor="CONTROLLER"),"FAILED_CLOSED")
    def test_browser_never_advances(self):
        machine=TuesdayPhaseMachine(controller_enabled=True); self.assertEqual(machine.advance("OPENING_EVIDENCE_AUTHORIZED",actor="OWNER",browser=True),"FAILED_CLOSED")
    def test_restart_recovers_exact_phase_and_sequence(self):
        machine=TuesdayPhaseMachine(controller_enabled=True); machine.advance("OPENING_EVIDENCE_AUTHORIZED",actor="OWNER")
        recovered=TuesdayPhaseMachine.recover(machine.checkpoint()); self.assertEqual(recovered.checkpoint(),machine.checkpoint())
    def test_governor_caps_and_no_retry(self):
        governor=CreditGovernor(30)
        for i in range(3): self.assertEqual(governor.reserve("MU",("OPENING_EVIDENCE","INTRADAY_MARK","CLOSING_MARK")[i],f"mu-{i}"),"RESERVED")
        self.assertEqual(governor.reserve("MU","CLOSING_MARK","mu-4"),"CREDIT_BUDGET_EXHAUSTED")
        self.assertEqual(governor.reserve("MU","OPENING_EVIDENCE","mu-0"),"DUPLICATE_REQUEST_REJECTED")
    def test_cache_repeat_costs_zero(self):
        governor=CreditGovernor(30); governor.reserve("MU","OPENING_EVIDENCE","x"); governor.settle("x","CONFIRMED")
        before=governor.report(); self.assertEqual(governor.cache_repeat("x"),"CACHE_HIT_ZERO_CREDIT"); after=governor.report()
        self.assertEqual((before["attempted"],before["confirmed"]),(after["attempted"],after["confirmed"]))
    def test_credential_is_last_before_request(self):
        self.assertEqual(GATE_ORDER[-2:],("CREDENTIAL_RETRIEVAL","PROVIDER_REQUEST"))
        denied=credential_gate_trace(operational=True,session="REGULAR",human_authorized=False,entitlement=True,ticker="MU",phase="OPENING_EVIDENCE",budget_valid=True,lock_acquired=True,selector_valid=True)
        self.assertFalse(denied["credential_access"]); self.assertEqual(denied["failed_gate"],"HUMAN_AUTHORIZATION")
    def test_service_is_uninstalled_nonnetworked(self):
        value=service_contract(); self.assertFalse(value["installed"]); self.assertFalse(value["activated"]); self.assertFalse(value["network_listener"]); self.assertEqual(value["authority"],AUTHORITY)
        template=(Path(__file__).parents[3]/"config/com.iios.expansion-wing-tuesday-controller.plist.template").read_text()
        for phrase in ("<key>Disabled</key><true/>","<key>RunAtLoad</key><false/>","<key>KeepAlive</key><false/>","expansion_wing.tuesday_controller_service"):
            self.assertIn(phrase,template)
        for prohibited in ("--activate","broker","ledger","Keychain","api-key"):
            self.assertNotIn(prohibited,template)
    def test_thirty_scenarios_are_explicit_and_inert(self):
        value=rehearsal_matrix(); self.assertEqual(len(SCENARIOS),30); self.assertEqual(value["scenario_count"],30)
        self.assertTrue(all(row["provider_requests"]==row["credits"]==0 and not row["operational_mutation"] for row in value["results"]))
    def test_post_close_is_null_safe(self):
        value=post_close_report(CreditGovernor(30),{"MU":{"nav":10000,"cash":10000,"position":None}})
        self.assertEqual(value["method_eligibility"],"INSUFFICIENT_SAMPLE"); self.assertIsNone(value["drawdown"]); self.assertTrue(value["operational_noninterference"])
    def test_authority_is_false_everywhere(self):
        self.assertTrue(all(value is False for value in AUTHORITY.values()))

if __name__ == "__main__": unittest.main()
