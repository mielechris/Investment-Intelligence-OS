from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.multi_asset_source_factory import (
    AUTHORITY, PROVIDERS, EntitlementRegistry, ProviderEntitlement, RequestGovernor, RequestPolicy,
    SourceEnvelope, control_room_projection, modeled_observation, product_source_matrix,
    professional_evidence, rehearsal_scenarios,
)
from expansion_wing.multi_product_research import FAMILY_REQUIREMENTS

NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "superbatch23_multi_asset_source_factory.json").read_text())


def entitlement(provider: str, approved: bool = False) -> ProviderEntitlement:
    return ProviderEntitlement(provider, "SYNTHETIC_TIER" if approved else None,
        "2026-09-07T00:00:00Z" if approved else None, True if approved else None,
        True if approved else None, False if approved else None, True if approved else None,
        True if approved else None, True if approved else None, "REQUIRED" if approved else None,
        "BOUNDED" if approved else None, 1 if approved else None, 10 if approved else None,
        ("EQUITY_ETF",) if approved else (), None if provider in {"KOYFIN_MANUAL","MARKET_VISION"}
        else f"SELECTOR_{provider}", "OWNER_APPROVED" if approved else "UNAPPROVED",
        "OPAQUE_OWNER" if approved else None, "2026-09-07T00:01:00Z" if approved else None)


def registry(approved: str | None = None) -> EntitlementRegistry:
    return EntitlementRegistry(tuple(entitlement(provider, provider == approved) for provider in PROVIDERS))


def value_for(field: str):
    if field in {"volume", "open_interest", "multiplier"}: return 100
    if field in {"coupon", "yield", "duration", "convexity", "strike", "bid", "ask", "mark",
                 "implied_volatility", "delta", "gamma", "theta", "vega", "maximum_modeled_loss",
                 "break_even", "spread_bps", "fees", "slippage_bps", "tick_value", "expense_ratio"}: return 1.0
    if field in {"early_exercise"}: return False
    if field in {"observed_at", "underlying_observed_at"}: return "2026-09-07T11:55:00Z"
    if field in {"issue_date"}: return "2026-01-01"
    if field in {"maturity_date", "expiration", "expiry"}: return "2027-01-01"
    return f"SYNTHETIC_{field.upper()}"


def envelope(family="EQUITY_ETF", **changes) -> SourceEnvelope:
    base = SourceEnvelope("FINANCIAL_DATASETS", "NASDAQ:MU", family, "NASDAQ",
        "2026-09-07T11:55:00Z", "2026-09-07T11:55:00Z", "2026-09-07T11:56:00Z",
        "REGULAR", "ADJUSTED", "ADJUSTED", "OBSERVED", "a"*64, "DISPLAY_APPROVED", 1,
        "CURRENT", "COMPLETE", "DIRECT", "NONE",
        tuple((field, value_for(field)) for field in FAMILY_REQUIREMENTS[family]))
    return replace(base, **changes)


class EntitlementTests(unittest.TestCase):
    def test_registry_has_exact_seven_and_unknown_is_unapproved(self):
        value=registry(); self.assertEqual(len(value.browser_safe()), 7)
        self.assertEqual({row["provider"] for row in value.browser_safe()}, set(PROVIDERS))
        with self.assertRaisesRegex(PermissionError, "ENTITLEMENT_UNAPPROVED"): value.require("FINANCIAL_DATASETS")

    def test_approved_record_requires_owner_and_complete_rights(self):
        entitlement("FINANCIAL_DATASETS", True).validate()
        with self.assertRaisesRegex(ValueError, "ENTITLEMENT_INCOMPLETE"):
            replace(entitlement("FINANCIAL_DATASETS", True), browser_display=None).validate()
        with self.assertRaisesRegex(ValueError, "MANUAL_SOURCE_AUTOMATION_PROHIBITED"):
            replace(entitlement("KOYFIN_MANUAL"), credential_selector="BAD").validate()

    def test_display_and_redistribution_fail_closed(self):
        record=replace(entitlement("FINANCIAL_DATASETS", True), browser_display=False)
        value=EntitlementRegistry(tuple(record if p==record.provider else entitlement(p) for p in PROVIDERS))
        self.assertIs(value.require("FINANCIAL_DATASETS"), record)
        with self.assertRaisesRegex(PermissionError,"REDISTRIBUTION_PROHIBITED"): value.require("FINANCIAL_DATASETS",display=True)


class EnvelopeTests(unittest.TestCase):
    def test_all_eight_family_contracts_accept_complete_fixture(self):
        record=entitlement("FINANCIAL_DATASETS",True)
        for family in FAMILY_REQUIREMENTS:
            with self.subTest(family=family): envelope(family).validate(record,now=NOW)

    def test_unknown_private_nested_missing_future_and_duplicate_rejected(self):
        record=entitlement("FINANCIAL_DATASETS",True)
        cases=(replace(envelope(),asset_family="UNKNOWN"),
            replace(envelope(),evidence=envelope().evidence+(("credential","secret"),)),
            replace(envelope(),evidence=(("nested",{"x":1}),)),
            replace(envelope(),retrieval_time="2026-09-08T00:00:00Z"),
            replace(envelope(),evidence=envelope().evidence[:-1]))
        for item in cases:
            with self.subTest(item=item), self.assertRaises((ValueError,PermissionError)): item.validate(record,now=NOW)
        seen=set(); envelope().validate(record,now=NOW,seen=seen)
        with self.assertRaisesRegex(ValueError,"DUPLICATE_IDENTITY"): envelope().validate(record,now=NOW,seen=seen)

    def test_unapproved_entitlement_and_browser_license_redaction(self):
        with self.assertRaisesRegex(PermissionError,"ENTITLEMENT_UNAPPROVED"):
            envelope().validate(entitlement("FINANCIAL_DATASETS"),now=NOW)
        hidden=envelope().browser_safe(replace(entitlement("FINANCIAL_DATASETS",True),browser_display=False))
        self.assertEqual(hidden["instrument_id"],"WITHHELD_BY_LICENSE")
        encoded=json.dumps(hidden); self.assertNotIn("SYNTHETIC_",encoded); self.assertFalse(hidden["values_displayed"])


class GovernorTests(unittest.TestCase):
    def test_disabled_browser_budget_singleflight_and_no_retry(self):
        with self.assertRaises(ValueError): RequestPolicy(retry_limit=1).validate()
        with self.assertRaisesRegex(PermissionError,"PROVIDER_DISABLED"): RequestGovernor(RequestPolicy()).authorize("FMP",1)
        governor=RequestGovernor(RequestPolicy(True,2,1))
        with self.assertRaisesRegex(PermissionError,"BROWSER_REQUEST_PROHIBITED"): governor.authorize("FMP",1,browser=True)
        governor.authorize("FMP",1)
        with self.assertRaisesRegex(RuntimeError,"SINGLE_FLIGHT_ACTIVE"): governor.authorize("FMP",1)
        governor.finish("FMP")
        with self.assertRaisesRegex(RuntimeError,"BUDGET_EXHAUSTED"): governor.authorize("FMP",1)


class ProductAndPaperTests(unittest.TestCase):
    def test_exact_twenty_four_products_and_independent_failure(self):
        rows=product_source_matrix((envelope(),))
        self.assertEqual(len(rows),24); self.assertEqual({row["synthetic_account_base"] for row in rows},{10_000})
        self.assertTrue(all(row["operational_paper_fund"] is False for row in rows))
        by_id={row["product_id"]:row for row in rows}
        self.assertEqual(by_id["us_large_cap_equities"]["source_state"],"PAPER_TEST_READY")
        self.assertEqual(by_id["listed_equity_etf_options"]["source_state"],"RESEARCH_ONLY_UNPRICEABLE")
        self.assertEqual(by_id["crypto_spot_references"]["source_state"],"UNAVAILABLE")

    def test_complete_evidence_creates_modeled_not_operational_observation(self):
        value=modeled_observation(envelope(),entitlement("FINANCIAL_DATASETS",True),now=NOW,
            size_hypothesis="FIXED_RISK",invalidation="SYNTHETIC_INVALIDATION",holding_period="ONE_DAY")
        self.assertEqual(value["state"],"MODELED_OBSERVATION"); self.assertFalse(value["operational_paper_fund"])
        self.assertTrue(all(flag is False for flag in value["authority"].values()))

    def test_proxy_distinctions(self):
        rows=product_source_matrix((envelope("COMMODITY"),envelope("FX"),envelope("CRYPTO")))
        values={row["product_id"]:row["source_state"] for row in rows}
        self.assertEqual(values["commodity_etf_etc_proxies"],"PROXY_ONLY")
        self.assertEqual(values["fx_spot_references"],"PROXY_ONLY")
        self.assertEqual(values["crypto_etfs_listed_proxies"],"PROXY_ONLY")


class ManualAndProjectionTests(unittest.TestCase):
    def test_manual_professional_sources_never_promote(self):
        for source in ("KOYFIN","MARKET_VISION","JESSE_INTERVIEW","FINANCIAL_ADVISER","PUBLIC_MANAGER","ISSUER","SEC"):
            value=professional_evidence(source=source,attributed=True,rights_approved=True,corroborated=True,
                timestamp="2026-09-07T00:00:00Z")
            self.assertFalse(value["candidate_creation"]); self.assertFalse(value["candidate_promotion"])

    def test_control_projection_is_scalar_bounded_and_browser_passive(self):
        value=control_room_projection(registry(),now="2026-09-07T12:00:00Z")
        self.assertEqual(len(value["product_sources"]),24); self.assertEqual(value["activation_state"],"NOT_ACTIVATED")
        self.assertEqual((value["requests"],value["credits"]),(0,0))
        self.assertTrue(all(flag is False for flag in value["authority"].values()))
        encoded=json.dumps(value,sort_keys=True)
        for term in ("api_key","credential_selector","source_body","provider_body","private_path"):
            self.assertNotIn(term,encoded)

    def test_rehearsal_inventory_and_fixture_identity(self):
        self.assertEqual(len(rehearsal_scenarios()),17); self.assertEqual(len(set(rehearsal_scenarios())),17)
        self.assertTrue(FIXTURE["fixture"]); self.assertEqual(FIXTURE["expected_product_count"],24)
        self.assertTrue(FIXTURE["operational_paper_fund_separate"])
        self.assertEqual(FIXTURE["financial_datasets_account_tier"],"FREE")
        self.assertFalse(FIXTURE["financial_datasets_paid_credits_demonstrated"])


if __name__ == "__main__": unittest.main()
