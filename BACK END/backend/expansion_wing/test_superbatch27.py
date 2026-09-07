from __future__ import annotations

import json
import unittest
from pathlib import Path

from .tuesday_whole_factory import (
    DAILY_CEILING, DECISIONS, LOCKED_AUTHORITY, MIGRATION_SCHEMA, PILOT_BY_PRODUCT,
    STAGE_LIMITS, STRUCTURAL_PRODUCTS, StagedCreditGovernor, browser_projection,
    candidate_decision, compile_request_plan, core_request_plan, fixture_rehearsal, method_product_matrix,
    migrate_disabled_v1, post_close_report, product_test_matrix, scanner_status,
)


def request(product="us_large_cap_equities", instrument="MU", stage="A", identity="request-fixture-0001", cost=1):
    return {"stage": stage, "product_room": product, "instrument": instrument,
            "endpoint": "COMPANY_FACTS", "purpose": "CURRENT_EVIDENCE", "estimated_cost": cost,
            "request_identity": identity, "earliest": "2026-09-08T13:00:00Z",
            "latest": "2026-09-08T20:00:00Z", "prerequisites": ("ENTITLEMENT", "OWNER_RELEASE"),
            "cache_policy": "CONTENT_HASH", "retry_policy": "NO_RETRY",
            "failure_behavior": "FAIL_CLOSED", "sanitized_fields": ("identity", "timestamp", "hash"),
            "browser_invocation": False}


class ProductAndMethodTests(unittest.TestCase):
    def test_exact_24_grouping_and_fixed_pilots(self):
        rows=product_test_matrix(); self.assertEqual(len(rows),24)
        self.assertEqual(sum(r["test_mode"]=="LIVE_EVIDENCE_ELIGIBLE" for r in rows),10)
        self.assertEqual(sum(r["test_mode"]=="LIVE_EVIDENCE_PENDING_IDENTITY" for r in rows),4)
        self.assertEqual(sum(r["test_mode"]=="STRUCTURAL_FAIL_CLOSED" for r in rows),10)
        self.assertEqual({r["instrument"] for r in rows if r["instrument"]},{"MU","SPY","XLK","VNQ","TLT","GLD","UUP","IBIT","PFF","BIL"})
        self.assertEqual(len(PILOT_BY_PRODUCT),10); self.assertEqual(len(STRUCTURAL_PRODUCTS),10)
        self.assertTrue(all(r["tuesday_participation"] for r in rows))

    def test_independent_sleeves_null_performance_and_no_authority(self):
        sleeves=[r["synthetic_sleeve"] for r in product_test_matrix()]
        self.assertTrue(all(s["starting_basis"]==10_000 and not s["pooled"] and s["performance"] is None for s in sleeves))
        self.assertEqual(sum(s["starting_basis"] for s in sleeves),240_000)
        self.assertTrue(all(not any(r["authority"].values()) for r in product_test_matrix()))

    def test_384_method_product_rows_all_blocked_and_null(self):
        rows=method_product_matrix(); self.assertEqual(len(rows),24*16)
        self.assertTrue(all(not r["eligible"] and r["result"] is None and not r["automatic_promotion"] for r in rows))
        historical=[r for r in rows if r["method_id"]=="trend_following"]
        self.assertTrue(all(r["reason_blocked"]=="ADJUSTMENT_TREATMENT_UNSPECIFIED" for r in historical))


class GovernorAndPlanTests(unittest.TestCase):
    def test_zero_release_and_staged_owner_releases(self):
        g=StagedCreditGovernor(); self.assertEqual(g.report()["released"],{"A":0,"B":0,"C":0})
        self.assertEqual(g.reserve("A","request-0001",1),"STAGE_BUDGET_EXHAUSTED")
        self.assertEqual(g.release("B",50,owner="owner",timestamp="time",reason="review"),"PRIOR_STAGE_REVIEW_REQUIRED")
        self.assertEqual(g.release("A",100,owner="owner",timestamp="time",reason="core"),"RELEASED")
        self.assertEqual(g.release("B",50,owner="owner",timestamp="time",reason="evidence"),"RELEASED")
        self.assertEqual(g.release("C",50,owner="owner",timestamp="time",reason="reserve"),"RELEASED")
        self.assertEqual(sum(g.releases.values()),DAILY_CEILING); self.assertEqual(STAGE_LIMITS,{"A":100,"B":50,"C":50})
        self.assertFalse(any(g.report()[k] for k in ("auto_release","auto_reload","automatic_retries","browser_invocation")))

    def test_reservation_duplicate_ambiguous_and_cache_accounting(self):
        g=StagedCreditGovernor(); g.release("A",2,owner="o",timestamp="t",reason="r")
        self.assertEqual(g.reserve("A","request-0001",1),"RESERVED")
        self.assertEqual(g.reserve("A","request-0001",1),"DUPLICATE_OR_INVALID_REQUEST")
        self.assertEqual(g.settle("A",1,"AMBIGUOUS"),"AMBIGUOUS")
        self.assertEqual(g.report()["used"]["A"],1)

    def test_valid_plan_and_rejections(self):
        plan=compile_request_plan([request()],{"A":100,"B":0,"C":0})
        self.assertEqual(plan["total"],1); self.assertFalse(any(plan["authority"].values()))
        cases=[]
        x=request(); x["estimated_cost"]=None; cases.append((x,"UNKNOWN_ENDPOINT_COST"))
        x=request(); x["retry_policy"]="RETRY"; cases.append((x,"UNSAFE_INVOCATION"))
        x=request(); x["browser_invocation"]=True; cases.append((x,"UNSAFE_INVOCATION"))
        x=request(product="treasury_bills_cash",instrument="BIL"); cases.append((x,"UNSUPPORTED_PRODUCT"))
        for row,reason in cases:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason): compile_request_plan([row],{"A":100,"B":0,"C":0})
        with self.assertRaisesRegex(ValueError,"DUPLICATE_REQUEST_IDENTITY"): compile_request_plan([request(),request()],{"A":100,"B":0,"C":0})
        with self.assertRaisesRegex(ValueError,"BUDGET_EXCEEDED"): compile_request_plan([request(cost=10)],{"A":9,"B":0,"C":0})
        with self.assertRaisesRegex(ValueError,"PER_INSTRUMENT_LIMIT_EXCEEDED"): compile_request_plan([request(cost=11)],{"A":100,"B":0,"C":0})

    def test_core_plan_is_exact_bounded_and_deterministic(self):
        rows=core_request_plan(); self.assertEqual(len(rows),50); self.assertEqual(sum(r["estimated_cost"] for r in rows),50)
        self.assertEqual(compile_request_plan(rows,{"A":100,"B":0,"C":0})["total"],50)


class GovernanceMigrationTests(unittest.TestCase):
    def state(self):
        return {"schema_version":"iios-tuesday-controller-state-v1","activated":False,
                "phase":"TUESDAY_PREMARKET_LOCKED","sequence":3,"global_credit_ceiling":30,
                "requests_used":0,"credits_used":0,"request_identities":[],"authority":LOCKED_AUTHORITY.copy()}

    def test_isolated_migration_monotonic_preserves_history_and_releases_zero(self):
        old=self.state(); migrated=migrate_disabled_v1(old)
        self.assertEqual(migrated["schema_version"],MIGRATION_SCHEMA); self.assertEqual(migrated["sequence"],4)
        self.assertEqual(migrated["released"],{"A":0,"B":0,"C":0}); self.assertFalse(migrated["activated"])
        self.assertEqual(old["global_credit_ceiling"],30)

    def test_ambiguous_unsafe_and_activated_migration_fail(self):
        for mutate,reason in ((lambda s:s.update(activated=True),"INCOMPATIBLE"),
                              (lambda s:s.update(requests_used=1),"AMBIGUOUS"),
                              (lambda s:s["authority"].update(provider=True),"UNSAFE")):
            value=self.state(); mutate(value)
            with self.assertRaisesRegex(ValueError,reason): migrate_disabled_v1(value)

    def test_scanner_aggregate_never_creates_identity(self):
        value=scanner_status(universe_size=519)
        self.assertEqual(value["browser_triggered_scans"],0); self.assertFalse(value["aggregate_counts_create_identities"])
        self.assertEqual(value["candidate_count"],0); self.assertFalse(value["automatic_promotion"])

    def test_human_decisions_do_not_promote_or_observe(self):
        self.assertEqual(set(DECISIONS),{d for d in DECISIONS})
        value=candidate_decision("APPROVE_FOR_COMMITTEE_REVIEW",current_evidence=True,immutable_identity=True,human_actor=True)
        self.assertTrue(value["committee_eligible"]); self.assertFalse(value["automatic_promotion"]); self.assertFalse(value["synthetic_observation_eligible"])
        with self.assertRaisesRegex(ValueError,"HUMAN_DECISION_REQUIRED"): candidate_decision("APPROVE_FOR_COMMITTEE_REVIEW",current_evidence=True,immutable_identity=True,human_actor=False)

    def test_null_safe_post_close(self):
        value=post_close_report(); self.assertIsNone(value["method_success"]); self.assertIsNone(value["profitability"])
        self.assertEqual(value["operational_paper_activity"],{"positions":0,"transactions":0,"orders":0,"fills":0})

    def test_browser_projection_is_fixture_only_and_bounded(self):
        value=browser_projection(); self.assertEqual(value["mode"],"FIXTURE_NON_LIVE_REHEARSAL")
        self.assertEqual(value["product_counts"],{"total":24,"participating":24,"pilots":10,"pending_identity":4,"structural":10,"operational_trading":0})
        self.assertEqual(value["methods"]["matrix_rows"],384); self.assertEqual(value["credit_governor"]["remaining"],0)
        self.assertFalse(value["controller"]["activated"]); self.assertEqual(value["controller"]["operational_allowance"],0)

    def test_fixture_matches_projection_contract(self):
        fixture=json.loads((Path(__file__).parent/"fixtures/superbatch27_whole_factory.json").read_text())
        value=browser_projection()
        self.assertEqual(fixture["fixture_identity"],"SYNTHETIC_FIXTURE_NON_LIVE")
        self.assertEqual(fixture["expected_counts"],value["product_counts"])
        self.assertEqual(fixture["stages"],value["credit_governor"]["stage_limits"])
        self.assertEqual(set(fixture["scenarios"]),set(fixture["required_scenarios"]))
        result=fixture_rehearsal(fixture["scenarios"]); self.assertEqual(result["scenario_count"],34)
        self.assertTrue(all(not row["operational_mutation"] and row["provider_requests"]==0 and row["credits"]==0 for row in result["results"]))


if __name__ == "__main__": unittest.main()
