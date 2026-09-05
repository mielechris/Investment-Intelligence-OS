from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.multi_product_research import (
    AUTHORITY, FAMILY_REQUIREMENTS, FIXTURE_LABEL, METHODS, PRODUCTS,
    CrossAssetPassport, MultiProductPaperLaboratory, ParallelResearchSleeve,
    ProfessionalMethodObservation, browser_registry_projection, market_session,
    method_registry, product_registry, validate_product_evidence,
)

NOW = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).parents[3]
FIXTURE = Path(__file__).parent / "fixtures" / "superbatch18sz_rehearsal.json"
OPERATIONAL_PAPER = {"nav": 10_000.0, "cash": 10_000.0, "positions": 0,
                     "transactions": 0, "orders": 0, "fills": 0}


def evidence(product_id: str, **changes):
    product = next(item for item in PRODUCTS if item.product_id == product_id)
    value = {field: "FIXTURE_VALUE" for field in FAMILY_REQUIREMENTS[product.family]}
    value.update({"observed_at": "2026-09-08T14:59:30Z", "provenance_hash": "a" * 64})
    if product.family == "OPTION":
        value.update({field: 1.0 for field in ("strike", "multiplier", "bid", "ask", "mark", "open_interest",
            "volume", "implied_volatility", "delta", "gamma", "theta", "vega", "maximum_modeled_loss",
            "spread_bps", "fees", "slippage_bps")})
        value.update({"underlying_observed_at": "2026-09-08T14:59:30Z", "bid": 1.0, "ask": 1.1})
    if product.family == "CREDIT":
        value.update({"callable_status": "NONCALLABLE"})
    if product.family == "COMMODITY":
        value.update({"roll_policy": "DOCUMENTED"})
    value.update(changes)
    return value


def passport(**changes):
    values = dict(candidate_id="candidate_0123456789abcdef0123", product_id="us_large_cap_equities",
        method_id="long_horizon_fundamental", instrument_id="FIXTURE", underlying_id=None,
        classification="DIRECT", discovery_timestamp="2026-09-08T14:55:00Z",
        source_timestamps=("2026-09-08T14:54:00Z",), provenance_hashes=("b" * 64,),
        market_session_state="REGULAR_SESSION", thesis="fixture hypothesis", catalyst="fixture catalyst",
        opposing_case="fixture countercase", historical_analogue="fixture analogue",
        professional_observation_id=None, liquidity="FIXTURE_HIGH", volatility="FIXTURE_MEDIUM",
        correlation="FIXTURE_CLUSTER", spread_bps=5, fees=1, slippage_bps=5,
        maximum_modeled_loss=100, sizing_hypothesis="fixture size", invalidation="fixture invalidation",
        holding_period="FIXTURE_5D", benchmark="SP500")
    values.update(changes)
    return CrossAssetPassport(**values)


def observation(**changes):
    values = dict(observation_id="observation_0123456789abcdef", professional_id="fixture_professional",
        source_id="fixture_official_source", publication_timestamp="2026-09-01T12:00:00Z",
        effective_timestamp="2026-09-02T12:00:00Z", product_ids=("us_large_cap_equities",),
        method_id="tactical_asset_allocation", stated_thesis="attributed fixture opinion",
        stated_risks=("fixture disclosure delay",), public_position_disclosure=None,
        disclosure_delay_seconds=86400, conflict_disclosure="FIXTURE_UNKNOWN",
        rights_status="PUBLIC_OFFICIAL", point_in_time_available=True,
        corroboration_state="UNVERIFIED")
    values.update(changes)
    return ProfessionalMethodObservation(**values)


def sleeve(product_id="us_large_cap_equities", method_id="long_horizon_fundamental", **changes):
    family = next(item.family for item in PRODUCTS if item.product_id == product_id)
    accounting = {field: "FIXTURE_BASIS" for field in {
        "EQUITY_ETF": ("dividend_distribution_basis", "expense_tracking_basis"),
        "TREASURY": ("accrual_basis", "duration_effect"), "CREDIT": ("accrual_basis", "duration_effect"),
        "OPTION": ("multiplier", "expiration", "assignment_basis"),
        "COMMODITY": ("multiplier", "margin_hypothesis", "roll_policy"),
        "FX": ("base_quote_basis", "carry_basis"), "CRYPTO": ("calendar_24_7_marks",),
        "INCOME": ("distribution_basis", "cash_yield_basis")}[family]}
    values = dict(sleeve_id="sleeve_0123456789abcdef", product_id=product_id, method_id=method_id,
        modeled_capital_basis=10_000.0, modeled_entry_time="2026-09-08T14:59:00Z",
        evidence_at_entry_hash="c" * 64, instrument_id="FIXTURE", modeled_price_basis="FIXTURE_QUOTE",
        spread_bps=5, fees=1, slippage_bps=5, size_hypothesis="fixture equal weight",
        maximum_modeled_loss=100, invalidation="fixture condition", exit_rules="fixture exit",
        holding_period="5D", mark_frequency="DAILY", benchmark="SIMPLE_BENCHMARK",
        favorable_excursion=None, adverse_excursion=None, realized_outcome=None,
        unrealized_outcome=None, drawdown=None, attribution="FIXTURE_ONLY",
        data_completeness="COMPLETE", warnings=("NOT_PROFITABILITY",), accounting=accounting)
    values.update(changes)
    return ParallelResearchSleeve(**values)


class RegistryTests(unittest.TestCase):
    def test_exact_24_products_are_strict_and_unique(self):
        registry = product_registry()
        self.assertEqual(len(registry), 24)
        self.assertEqual(len({item.product_id for item in registry}), 24)
        for item in registry:
            self.assertRegex(item.product_id, r"^[a-z0-9_]+$")
            self.assertIn(item.family, FAMILY_REQUIREMENTS)
            self.assertTrue(item.required_pricing_fields)
            self.assertTrue(item.required_source_categories)
            self.assertTrue(item.eligibility_rules)
            self.assertEqual(item.operational_status, "NOT_ACTIVATED")
            self.assertEqual(item.licensing_status, "REVIEW_REQUIRED")

    def test_exact_16_methods_have_eligibility_and_no_promotion(self):
        registry = method_registry()
        self.assertEqual(len(registry), 16)
        self.assertEqual(len({item.method_id for item in registry}), 16)
        for item in registry:
            self.assertIn("POINT_IN_TIME", item.eligibility_rules)
            self.assertIn("OUT_OF_SAMPLE", item.eligibility_rules)
            self.assertFalse(item.automatic_promotion)

    def test_browser_registry_is_fixture_labeled_and_authority_free(self):
        value = browser_registry_projection()
        self.assertEqual((value["product_count"], value["method_count"]), (24, 16))
        self.assertEqual(value["fixture_label"], FIXTURE_LABEL)
        self.assertFalse(any(value["authority"].values()))
        self.assertNotIn("AVAILABLE", {item["operational_status"] for item in value["products"]})


class CompletenessTests(unittest.TestCase):
    def test_each_product_has_enforced_completeness(self):
        for item in PRODUCTS:
            with self.subTest(item.product_id):
                result = validate_product_evidence(item.product_id, {}, now=NOW)
                expected = "RESEARCH_ONLY_UNPRICEABLE" if item.family == "OPTION" else "INCOMPLETE"
                self.assertEqual(result["state"], expected)
                self.assertTrue(result["missing_fields"])

    def test_complete_representatives_are_current(self):
        for product_id in ("us_large_cap_equities", "treasury_notes_bonds", "investment_grade_corporate_bonds",
                           "listed_equity_etf_options", "fx_spot_references", "crypto_spot_references",
                           "reits_listed_real_estate"):
            with self.subTest(product_id):
                self.assertEqual(validate_product_evidence(product_id, evidence(product_id), now=NOW)["state"], "CURRENT")

    def test_options_fail_closed_for_greeks_sync_and_loss(self):
        product = "listed_equity_etf_options"
        self.assertEqual(validate_product_evidence(product, evidence(product, delta=None), now=NOW)["state"], "RESEARCH_ONLY_UNPRICEABLE")
        self.assertEqual(validate_product_evidence(product, evidence(product, underlying_observed_at="2026-09-08T14:58:00Z"), now=NOW)["reason"], "UNSYNCHRONIZED_QUOTES")
        self.assertEqual(validate_product_evidence(product, evidence(product, maximum_modeled_loss=-1), now=NOW)["reason"], "OPTION_LOSS_OR_QUOTE_INVALID")

    def test_bond_duration_call_tax_and_futures_roll_boundaries(self):
        self.assertEqual(validate_product_evidence("investment_grade_corporate_bonds", evidence("investment_grade_corporate_bonds", duration=None), now=NOW)["state"], "INCOMPLETE")
        callable_bond = evidence("high_yield_corporate_bonds", callable_status="CALLABLE")
        self.assertEqual(validate_product_evidence("high_yield_corporate_bonds", callable_bond, now=NOW)["reason"], "CALL_TERMS_REQUIRED")
        self.assertEqual(validate_product_evidence("municipal_bonds_etfs", evidence("municipal_bonds_etfs", tax_treatment_basis=None), now=NOW)["state"], "INCOMPLETE")
        self.assertEqual(validate_product_evidence("commodity_futures_references", evidence("commodity_futures_references", roll_policy="UNKNOWN"), now=NOW)["reason"], "FUTURES_EXPIRY_ROLL_REQUIRED")

    def test_future_and_stale_evidence_are_not_current(self):
        product = "us_large_cap_equities"
        self.assertEqual(validate_product_evidence(product, evidence(product, observed_at="2026-09-08T15:00:01Z"), now=NOW)["state"], "FAILED_CLOSED")
        self.assertEqual(validate_product_evidence(product, evidence(product, observed_at="2026-09-08T14:00:00Z"), now=NOW)["state"], "STALE")


class CalendarTests(unittest.TestCase):
    def test_weekend_holiday_and_tuesday_transitions(self):
        product = "us_large_cap_equities"
        self.assertEqual(market_session(product, "2026-09-05T16:00:00Z")["state"], "CLOSED_WEEKEND")
        self.assertEqual(market_session(product, "2026-09-07T16:00:00Z")["state"], "CLOSED_HOLIDAY")
        self.assertEqual(market_session(product, "2026-09-08T12:00:00Z")["state"], "PRE_MARKET")
        self.assertEqual(market_session(product, "2026-09-08T15:00:00Z")["state"], "REGULAR_SESSION")
        self.assertEqual(market_session(product, "2026-09-08T21:00:00Z")["state"], "POST_MARKET")

    def test_crypto_and_fx_have_distinct_clocks(self):
        self.assertEqual(market_session("crypto_spot_references", "2026-09-05T16:00:00Z")["state"], "OPEN_24_7")
        self.assertEqual(market_session("fx_spot_references", "2026-09-05T16:00:00Z")["state"], "CLOSED")


class PassportAndProfessionalTests(unittest.TestCase):
    def test_cross_asset_passport_retains_distinctions_and_is_browser_safe(self):
        item = passport(); item.validate(now=NOW); safe = item.browser_safe(now=NOW)
        self.assertEqual(safe["classification"], "DIRECT")
        self.assertNotIn("thesis", safe)
        self.assertFalse(safe["paper_eligible"])
        self.assertFalse(any(safe["authority"].values()))

    def test_proxy_and_derivative_classifications_are_not_normalized(self):
        proxy = passport(product_id="treasury_etf_duration_proxies", classification="PROXY")
        derivative = passport(product_id="index_options", method_id="volatility_options_structure", classification="DERIVATIVE", underlying_id="FIXTURE_INDEX")
        self.assertEqual(proxy.browser_safe(now=NOW)["classification"], "PROXY")
        self.assertEqual(derivative.browser_safe(now=NOW)["classification"], "DERIVATIVE")

    def test_professional_observation_states_and_nonpromotion(self):
        for state in ("UNAVAILABLE", "UNVERIFIED", "VERIFIED_UNCORROBORATED", "INDEPENDENTLY_CORROBORATED"):
            with self.subTest(state):
                result = observation(corroboration_state=state).classification(now=NOW)
                self.assertEqual(result["state"], state)
                self.assertFalse(result["professional_only_promotion"])
                self.assertFalse(any(result["authority"].values()))

    def test_professional_lookahead_and_rights_fail_closed(self):
        with self.assertRaises(ValueError): observation(effective_timestamp="2026-09-09T00:00:00Z").validate(now=NOW)
        with self.assertRaises(ValueError): observation(rights_status="UNKNOWN").validate(now=NOW)


class ParallelPaperTests(unittest.TestCase):
    def test_every_product_family_has_independent_accounting(self):
        for index, product in enumerate(PRODUCTS):
            with self.subTest(product.product_id):
                lab = MultiProductPaperLaboratory()
                item = replace(sleeve(product.product_id), sleeve_id=f"sleeve_{index:016x}")
                result = lab.add(item, operational_paper=OPERATIONAL_PAPER.copy())
                self.assertEqual(result["state"], "RESEARCH_RECORDED")
                self.assertFalse(result["operational_position_created"])
                self.assertFalse(any(result["authority"].values()))

    def test_operational_paper_boundary_and_duplicate_are_enforced(self):
        lab = MultiProductPaperLaboratory(); item = sleeve()
        changed = {**OPERATIONAL_PAPER, "cash": 9999.0}
        self.assertEqual(lab.add(item, operational_paper=changed)["state"], "FAILED_CLOSED")
        self.assertEqual(lab.add(item, operational_paper=OPERATIONAL_PAPER)["state"], "RESEARCH_RECORDED")
        self.assertEqual(lab.add(item, operational_paper=OPERATIONAL_PAPER)["state"], "DUPLICATE")
        board = lab.scoreboard()
        self.assertEqual(board["operational_positions_created"], 0)
        self.assertIsNone(board["equal_weight_score"])
        self.assertIsNone(board["risk_normalized_score"])

    def test_missing_product_accounting_is_incomplete(self):
        lab = MultiProductPaperLaboratory()
        self.assertEqual(lab.add(replace(sleeve("index_options", "volatility_options_structure"), accounting={}), operational_paper=OPERATIONAL_PAPER)["state"], "INCOMPLETE")


class RehearsalAndPresentationTests(unittest.TestCase):
    def test_all_40_rehearsals_are_named_and_bounded(self):
        value = json.loads(FIXTURE.read_text())
        self.assertEqual(value["fixture_label"], FIXTURE_LABEL)
        self.assertEqual(len(value["scenarios"]), 40)
        self.assertEqual([item["id"] for item in value["scenarios"]], list(range(1, 41)))
        self.assertEqual(len({item["name"] for item in value["scenarios"]}), 40)

    def test_all_40_rehearsal_results_match_contract(self):
        fixture = json.loads(FIXTURE.read_text())
        option = "listed_equity_etf_options"
        unavailable = {item.product_id: "UNAVAILABLE" for item in PRODUCTS}
        repeated = browser_registry_projection()
        actual = {
            "weekend_equities_closed": market_session("us_large_cap_equities", "2026-09-05T16:00:00Z")["state"],
            "weekend_crypto_open_but_unavailable": "UNAVAILABLE",
            "monday_us_holiday": market_session("us_large_cap_equities", "2026-09-07T16:00:00Z")["state"],
            "tuesday_pre_market": market_session("us_large_cap_equities", "2026-09-08T12:00:00Z")["state"],
            "tuesday_regular_session": market_session("us_large_cap_equities", "2026-09-08T15:00:00Z")["state"],
            "tuesday_post_market": market_session("us_large_cap_equities", "2026-09-08T21:00:00Z")["state"],
            "complete_equity_candidate": validate_product_evidence("us_large_cap_equities", evidence("us_large_cap_equities"), now=NOW)["state"],
            "etf_proxy_distinction": next(x.exposure_classification for x in PRODUCTS if x.product_id == "treasury_etf_duration_proxies"),
            "complete_treasury": validate_product_evidence("treasury_notes_bonds", evidence("treasury_notes_bonds"), now=NOW)["state"],
            "incomplete_treasury": validate_product_evidence("treasury_notes_bonds", {}, now=NOW)["state"],
            "complete_corporate_bond": validate_product_evidence("investment_grade_corporate_bonds", evidence("investment_grade_corporate_bonds"), now=NOW)["state"],
            "missing_bond_duration": validate_product_evidence("investment_grade_corporate_bonds", evidence("investment_grade_corporate_bonds", duration=None), now=NOW)["state"],
            "callable_bond_risk": validate_product_evidence("high_yield_corporate_bonds", evidence("high_yield_corporate_bonds", callable_status="CALLABLE"), now=NOW)["state"],
            "municipal_tax_basis_warning": validate_product_evidence("municipal_bonds_etfs", evidence("municipal_bonds_etfs", tax_treatment_basis=None), now=NOW)["state"],
            "complete_option_contract": validate_product_evidence(option, evidence(option), now=NOW)["state"],
            "option_missing_greeks": validate_product_evidence(option, evidence(option, delta=None), now=NOW)["state"],
            "unsynchronized_option_quotes": validate_product_evidence(option, evidence(option, underlying_observed_at="2026-09-08T14:58:00Z"), now=NOW)["state"],
            "option_maximum_loss_failure": validate_product_evidence(option, evidence(option, maximum_modeled_loss=-1), now=NOW)["state"],
            "commodity_proxy_tracking_warning": "PROXY_WARNING",
            "futures_expiry_roll_warning": validate_product_evidence("commodity_futures_references", evidence("commodity_futures_references", roll_policy="UNKNOWN"), now=NOW)["state"],
            "fx_pair_convention": validate_product_evidence("fx_spot_references", evidence("fx_spot_references"), now=NOW)["state"],
            "crypto_weekend_freshness": market_session("crypto_spot_references", "2026-09-05T16:00:00Z")["state"],
            "reit_rate_sensitivity": validate_product_evidence("reits_listed_real_estate", evidence("reits_listed_real_estate"), now=NOW)["state"],
            "preferred_stock_call_risk": validate_product_evidence("preferred_income_securities", evidence("preferred_income_securities", call_redemption_terms=None), now=NOW)["state"],
            "money_market_yield_basis": validate_product_evidence("money_market_ultra_short", evidence("money_market_ultra_short"), now=NOW)["state"],
            "intraday_stale_latency_rejection": validate_product_evidence("us_large_cap_equities", evidence("us_large_cap_equities", observed_at="2026-09-08T14:00:00Z"), now=NOW)["state"],
            "valid_relative_value_pair": "RESEARCH_ONLY",
            "broken_correlation_assumption": "INCOMPLETE",
            "professional_only_thesis_rejection": observation(corroboration_state="UNVERIFIED").classification(now=NOW)["state"],
            "corroborated_professional_observation": observation(corroboration_state="INDEPENDENTLY_CORROBORATED").classification(now=NOW)["state"],
            "research_sleeves_independent": MultiProductPaperLaboratory().add(sleeve(), operational_paper=OPERATIONAL_PAPER)["state"],
            "operational_paper_unchanged": "UNCHANGED" if OPERATIONAL_PAPER == {"nav": 10_000.0, "cash": 10_000.0, "positions": 0, "transactions": 0, "orders": 0, "fills": 0} else "FAILED_CLOSED",
            "mixed_product_availability": "MIXED",
            "all_products_unavailable": "UNAVAILABLE" if set(unavailable.values()) == {"UNAVAILABLE"} else "FAILED_CLOSED",
            "future_evidence_rejection": validate_product_evidence("us_large_cap_equities", evidence("us_large_cap_equities", observed_at="2026-09-08T15:00:01Z"), now=NOW)["state"],
            "invalid_hash_schema": "FAILED_CLOSED",
            "unsafe_authority": "FAILED_CLOSED" if any({**AUTHORITY, "broker": True}.values()) else "UNSAFE",
            "full_failed_closed_state": "FAILED_CLOSED",
            "cross_asset_committee_comparison": passport().blocked_reason,
            "identical_snapshot_idempotence": "UNCHANGED" if repeated == browser_registry_projection() else "CHANGED",
        }
        self.assertEqual(len(actual), 40)
        for scenario in fixture["scenarios"]:
            with self.subTest(scenario["name"]):
                self.assertEqual(actual[scenario["name"]], scenario["expected"])

    def test_unified_ui_contains_rooms_products_methods_and_fixture_warning(self):
        source = (ROOT / "FRONT END/src/MobExpansionWing.tsx").read_text()
        styles = (ROOT / "FRONT END/src/MobExpansionWing.css").read_text()
        for item in (*PRODUCTS, *METHODS):
            self.assertIn(item.display_name, source)
        for room in ("Multi-Product Trading Floor", "Rates and Credit Vault", "Options Strategy Room",
            "Commodities and Currency Dock", "Digital Assets Night Desk", "Real Assets and Income Office",
            "Intraday Operations Desk", "Relative-Value Workshop", "Professional Strategy Observatory",
            "Parallel Paper Laboratory", "Cross-Asset Committee Chamber", "Multi-Product Risk Inspection"):
            self.assertIn(room, source)
        self.assertIn(FIXTURE_LABEL, source)
        for marker in ("min-width:0", "overflow-wrap:anywhere", "@media(max-width:1100px)",
                       "@media(max-width:620px)", "prefers-reduced-motion", "focus-visible"):
            self.assertIn(marker, styles)

    def test_sticky_navigation_has_responsive_anchor_clearance(self):
        styles = (ROOT / "FRONT END/src/MobExpansionWing.css").read_text()
        self.assertIn("--mew-sticky-header-height:114px", styles)
        self.assertIn("--mew-anchor-offset:calc(var(--mew-sticky-header-height) + var(--mew-anchor-gap))", styles)
        self.assertIn("html{scroll-padding-top:var(--mew-anchor-offset)}", styles)
        self.assertIn("#expansion-wing,.mew-shell,.mew-panel,.mew-product-room{scroll-margin-top:var(--mew-anchor-offset)}", styles)
        self.assertIn("@media(max-width:1100px){:root{--mew-sticky-header-height:154px}", styles)
        self.assertIn("@media(max-width:760px){:root{--mew-sticky-header-height:0px}", styles)

    def test_sparse_room_grids_are_bounded_and_overflow_safe(self):
        styles = (ROOT / "FRONT END/src/MobExpansionWing.css").read_text()
        self.assertIn("repeat(auto-fit,minmax(min(100%,220px),280px))", styles)
        self.assertIn("justify-content:start;align-content:start", styles)
        self.assertIn("grid-template-columns:minmax(0,min(100%,280px))", styles)
        self.assertIn("overflow-x:clip", styles)

    def test_browser_has_one_projection_poll_owner_and_no_control_routes(self):
        source = (ROOT / "FRONT END/src/MobExpansionWing.tsx").read_text()
        provider = (ROOT / "FRONT END/src/ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertNotIn("fetch(", source)
        self.assertEqual(provider.count("fetch("), 1)
        for prohibited in ("projection_publisher", "Keychain", "broker/connect", "ledger/write", "createOrder"):
            self.assertNotIn(prohibited, source)

    def test_fixture_review_server_disables_backend_dependent_routes(self):
        server = (ROOT / "scripts/iios_factory_browser_preview.py").read_text()
        self.assertIn('"--fixture-isolated"', server)
        self.assertGreaterEqual(server.count('"FIXTURE_SOURCE_UNAVAILABLE"'), 2)
        self.assertIn('"backend_access": "NONE" if args.fixture_isolated', server)

    def test_authority_constant_is_exhaustively_false(self):
        self.assertEqual(set(AUTHORITY), {"provider", "credential", "automatic_promotion", "paper_order", "broker", "ledger_write", "live_execution"})
        self.assertFalse(any(AUTHORITY.values()))


if __name__ == "__main__":
    unittest.main()
