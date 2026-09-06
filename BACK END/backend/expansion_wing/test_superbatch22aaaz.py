from __future__ import annotations
import json, time, unittest
from pathlib import Path
from expansion_wing.north_star_commissioning import CASE_FIELDS, CASE_SCHEMA, SYNTHETIC_LABEL, browser_safe_case_registry, commissioning, provider_inventory, synthetic_accounts, validate_commissioning
from expansion_wing.case_registry_adapter import BackgroundCaseRegistry, MAX_CASES, sanitize_overview

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

class NorthStarCommissioningTests(unittest.TestCase):
    @staticmethod
    def source_case(case_id="case_authenticated_0001", ticker="ABC", stage="COMMITTEE"):
        return {"active_room":"COMMITTEE","agent_count":8,"authorization":{},"capital":{},"case_id":case_id,"committee":{},"committee_confidence":None,"latest_event":"COMMITTEE_COMPLETE","latest_event_at":"2026-09-05T20:00:00Z","live_execution":False,"paper_execution":False,"qualified":False,"risk":{},"sizing":{},"stage":stage,"ticker":ticker,"topic":"Browser-approved case title","trade_execution_permission":False}
    def test_missing_case_source_is_unavailable_not_empty(self):
        value = browser_safe_case_registry(None, source_state="UNAVAILABLE")
        self.assertEqual((value["schema_version"], value["total"], value["cases"], value["mu_case_state"]), (CASE_SCHEMA, None, [], "UNAVAILABLE"))
    def test_strict_case_allowlist_and_incomplete_mu(self):
        fixture=json.loads((HERE/"fixtures/superbatch22_north_star.json").read_text()); value=browser_safe_case_registry(fixture["synthetic_cases"],source_state="INCOMPLETE")
        self.assertEqual(value["mu_case_state"],"INCOMPLETE"); self.assertEqual(value["total"],1); self.assertEqual(set(value["cases"][0]),CASE_FIELDS); self.assertFalse(value["cases"][0]["paper_eligibility"])
    def test_unknown_private_duplicate_future_and_malformed_cases_fail(self):
        base=json.loads((HERE/"fixtures/superbatch22_north_star.json").read_text())["synthetic_cases"][0]
        for records in ([{**base,"provider_body":"private"}],[base,base],[{**base,"updated_at":"2099-01-01T00:00:00Z"}],[{**base,"stage":"PROMOTED"}]):
            with self.assertRaises(ValueError): browser_safe_case_registry(records,source_state="CURRENT")
    def test_24_independent_accounts_do_not_form_240k_portfolio(self):
        accounts=synthetic_accounts(); self.assertEqual(len(accounts),24); self.assertEqual(len({x["account_id"] for x in accounts}),24); self.assertTrue(all(x["label"]==SYNTHETIC_LABEL and x["starting_basis"]==10_000 and not x["pooled"] and not x["operational_capital"] for x in accounts))
    def test_unobserved_results_stay_null_and_authority_false(self):
        value=commissioning(); validate_commissioning(value)
        for account in value["synthetic_accounts"]:
            self.assertTrue(all(account[k] is None for k in ("realized_result","unrealized_result","fees","spread","slippage","drawdown","favorable_excursion","adverse_excursion","calibration"))); self.assertFalse(any(account["authority"].values()))
        self.assertEqual(value["operational_paper"],{"nav":10_000.0,"cash":10_000.0,"positions":0,"transactions":0,"orders":0,"fills":0})
    def test_16_methods_are_unranked_without_authentic_outcomes(self):
        value=commissioning(); self.assertEqual(len(value["methods"]),16); self.assertTrue(all(x["state"]=="INSUFFICIENT_SAMPLE" and x["score"] is None and not x["ranking_eligible"] for x in value["methods"]))
    def test_source_waves_fail_independently_and_make_no_requests(self):
        value=commissioning(); self.assertEqual(set(value["source_waves"]),set("ABCDEF")); self.assertTrue(all(x["state"]=="NOT_ACTIVATED" and x["requests"]==0 and x["credits"]==0 for x in value["source_waves"].values())); self.assertEqual((value["provider_requests"],value["provider_credits"]),(0,0))
    def test_provider_possession_never_implies_rights_or_authority(self):
        rows=provider_inventory(); self.assertTrue(all(not x["provider_authority"] and not x["broker_interface"] and not x["ledger_interface"] for x in rows)); self.assertTrue(any(x["classification"]=="RIGHTS_REVIEW_REQUIRED" for x in rows))
    def test_frontend_has_24_direct_product_selectors_and_case_registry(self):
        source=(ROOT/"FRONT END/src/MobExpansionWing.tsx").read_text(); self.assertIn('aria-label="Twenty-four product rooms"',source); self.assertIn("Authenticated Case Registry",source); self.assertIn("Synthetic comparison basis — not deployable capital.",source); self.assertNotIn("$240,000",source)
    def test_no_private_or_mutating_boundary(self):
        source=(HERE/"north_star_commissioning.py").read_text()
        for marker in ("latest_shadow_counterfactual","requests.","urllib","subprocess","Keychain","ledger.write","broker.connect"): self.assertNotIn(marker,source)

    def test_slow_source_refreshes_in_background_and_cold_start_is_unavailable(self):
        def fetcher(_endpoint, _timeout, _maximum):
            time.sleep(.05); return {"data_state":"LIVE","case_count":1,"cases":[self.source_case()]}
        adapter=BackgroundCaseRegistry(fetcher=fetcher)
        self.assertEqual((adapter.snapshot()["state"],adapter.snapshot()["total"]),("UNAVAILABLE",None))
        adapter.start()
        deadline=time.monotonic()+1
        while adapter.snapshot()["total"] is None and time.monotonic()<deadline: time.sleep(.01)
        value=adapter.snapshot(); adapter.close()
        self.assertEqual((value["state"],value["total"],value["counts"]["committee"]),("CURRENT",1,1))

    def test_retained_registry_survives_sanitized_source_failure_without_retimestamp(self):
        calls=[{"data_state":"LIVE","case_count":1,"cases":[self.source_case()]},RuntimeError("private source path")]
        def fetcher(*_args):
            value=calls.pop(0)
            if isinstance(value,Exception): raise value
            return value
        adapter=BackgroundCaseRegistry(fetcher=fetcher)
        self.assertTrue(adapter.refresh_once()); first=adapter.snapshot(); self.assertFalse(adapter.refresh_once()); retained=adapter.snapshot(); adapter.close()
        self.assertEqual(first["cases"],retained["cases"]); self.assertEqual(retained["error_category"],"CASE_SOURCE_UNAVAILABLE"); self.assertNotIn("private",json.dumps(retained))

    def test_source_count_fields_identity_future_and_private_values_fail_closed(self):
        base=self.source_case()
        cases=([base]*(MAX_CASES+1), [{**base,"unknown":1}], [{**base,"case_id":"bad space"}], [{**base,"latest_event_at":"2099-01-01T00:00:00Z"}])
        for rows_ in cases:
            with self.assertRaises(ValueError): sanitize_overview({"data_state":"LIVE","case_count":len(rows_),"cases":rows_})

    def test_mu_recovery_uses_only_authenticated_identity(self):
        value=sanitize_overview({"data_state":"LIVE","case_count":1,"cases":[self.source_case(ticker="MU",stage="RISK")]})
        self.assertEqual((value["total"],value["mu_case_state"],value["counts"]["risk"]),(1,"INCOMPLETE",1))
        self.assertFalse(value["cases"][0]["paper_eligibility"])

    def test_recovered_registry_preserves_all_40_immutable_cases_and_stage_counts(self):
        cases = [self.source_case(f"case_authenticated_{index:04d}", f"T{index:02d}", "COMMITTEE" if index <= 35 else "RISK") for index in range(1, 41)]
        value = sanitize_overview({"data_state":"LIVE", "generated_at":"2026-09-05T20:00:00Z", "case_count":40, "cases":cases})
        self.assertEqual((value["total"], value["counts"]["active"], value["counts"]["committee"], value["counts"]["risk"]), (40, 40, 35, 5))
        self.assertEqual((value["counts"]["awaiting_evidence"], value["counts"]["rejected"], value["counts"]["closed"], value["counts"]["with_outcomes"], value["counts"]["without_browser_details"]), (0, 0, 0, 0, 40))
        self.assertEqual(len({item["case_id"] for item in value["cases"]}), 40)
        self.assertEqual(value["source_observed_at"], "2026-09-05T20:00:00Z")

    def test_preview_owns_one_case_worker_and_browser_never_calls_backend(self):
        preview=(ROOT/"scripts/iios_factory_browser_preview.py").read_text(); provider=(ROOT/"FRONT END/src/ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertEqual(preview.count("BackgroundCaseRegistry()"),1); self.assertNotIn("8002",provider); self.assertIn("case_reader=",preview)

if __name__=="__main__": unittest.main()
