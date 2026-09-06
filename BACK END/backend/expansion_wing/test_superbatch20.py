from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from expansion_wing.acceptance_server import Compositor
from expansion_wing.multi_product_research import (
    AUTHORITY, FAMILY_REQUIREMENTS, METHODS, PRODUCTS, MultiProductPaperLaboratory,
    method_scoreboard, validate_product_evidence,
)
from expansion_wing.tuesday_opening_day import (
    ProfessionalResearchRecord, SCHEMA_VERSION, SYNTHETIC_LABEL,
    method_readiness, product_readiness, professional_readiness_audit,
    tuesday_command_projection, validate_browser_projection,
)

ROOT = Path(__file__).parents[3]
HERE = Path(__file__).parent
NOW = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)


def evidence(product_id: str, **updates):
    product = next(item for item in PRODUCTS if item.product_id == product_id)
    value = {key: "FIXTURE_VALUE" for key in FAMILY_REQUIREMENTS[product.family]}
    value.update({"observed_at": "2026-09-08T14:59:30Z", "source_timestamp": "2026-09-08T14:59:20Z",
                  "effective_timestamp": "2026-09-08T14:59:25Z", "provenance_hash": "a" * 64})
    if product.family == "OPTION":
        value.update({key: 1.0 for key in ("strike", "multiplier", "bid", "ask", "mark", "open_interest", "volume",
                     "implied_volatility", "delta", "gamma", "theta", "vega", "maximum_modeled_loss", "spread_bps", "fees", "slippage_bps")})
        value.update({"underlying_observed_at": "2026-09-08T14:59:30Z", "ask": 1.1})
    if product.family == "CREDIT": value["callable_status"] = "NONCALLABLE"
    if product.family == "COMMODITY": value["roll_policy"] = "DOCUMENTED"
    value.update(updates)
    return value


class TuesdayContracts(unittest.TestCase):
    def test_exact_product_and_method_readiness_is_fail_closed(self):
        products, methods = product_readiness(), method_readiness()
        self.assertEqual((len(products), len(methods)), (24, 16))
        self.assertTrue(all(x["candidate_count"] is None and not x["research_eligible"] and not x["paper_eligible"] for x in products))
        self.assertTrue(all(x["source_state"] == "NOT_ACTIVATED" and x["synthetic_label"] == SYNTHETIC_LABEL for x in products))
        self.assertTrue(all(x["ranking_state"] == "INSUFFICIENT_SAMPLE" and x["score"] is None for x in methods))

    def test_all_family_contracts_reject_missing_future_and_proxy_equivalence(self):
        for product in PRODUCTS:
            missing = validate_product_evidence(product.product_id, {}, now=NOW)
            self.assertIn(missing["state"], {"INCOMPLETE", "RESEARCH_ONLY_UNPRICEABLE"})
            future = validate_product_evidence(product.product_id, evidence(product.product_id, observed_at="2026-09-08T15:00:01Z"), now=NOW)
            self.assertEqual(future["state"], "FAILED_CLOSED")
            if product.exposure_classification == "PROXY": self.assertIn("NO_PROXY_EQUIVALENCE", product.prohibited_assumptions)

    def test_options_bonds_futures_and_income_fail_specific_missing_fields(self):
        self.assertEqual(validate_product_evidence("listed_equity_etf_options", evidence("listed_equity_etf_options", delta=None), now=NOW)["state"], "RESEARCH_ONLY_UNPRICEABLE")
        self.assertEqual(validate_product_evidence("municipal_bonds_etfs", evidence("municipal_bonds_etfs", tax_treatment_basis=None), now=NOW)["state"], "INCOMPLETE")
        self.assertEqual(validate_product_evidence("commodity_futures_references", evidence("commodity_futures_references", roll_policy="UNKNOWN"), now=NOW)["reason"], "FUTURES_EXPIRY_ROLL_REQUIRED")
        self.assertEqual(validate_product_evidence("reits_listed_real_estate", evidence("reits_listed_real_estate", distribution_yield_basis=None), now=NOW)["state"], "INCOMPLETE")

    def test_professional_contract_is_attributed_non_promotional(self):
        item = ProfessionalResearchRecord("observation_fixture", "analyst", "firm", "FUNDAMENTAL", ("us_large_cap_equities",),
            "2026-09-01T12:00:00Z", "2026-09-01T12:00:00Z", "2026-09-02T12:00:00Z", "PUBLIC_OFFICIAL",
            "DISCLOSED_DELAY", "CONFLICTS_DISCLOSED", True, "PRIMARY", "INDEPENDENTLY_CORROBORATED",
            "Attributed fixture hypothesis", "Fixture invalidation", "RESEARCH_ONLY")
        value = item.browser_projection(now=NOW)
        self.assertFalse(value["endorsement"]); self.assertTrue(value["promotion_prohibited"]); self.assertFalse(any(value["authority"].values()))
        self.assertEqual(len(professional_readiness_audit()), 5)

    def test_scoreboard_never_turns_insufficient_data_into_zero(self):
        value = method_scoreboard(())
        self.assertEqual(value["state"], "INSUFFICIENT_SAMPLE"); self.assertIsNone(value["rankings"]); self.assertFalse(value["missing_is_zero"])

    def test_command_projection_separates_container_and_evidence(self):
        snapshot = {"sections": {"projection_activation": {"state": "AVAILABLE", "data": {"freshness_state": "CURRENT", "publisher_state": "UNAVAILABLE"}},
            "projection_freshness": {"state": "STALE", "data": {}}, "market_session": {"state": "AVAILABLE", "data": {"state": "CLOSED_HOLIDAY"}},
            "books": {"state": "CURRENT", "data": {"nav": 10000.0, "cash": 10000.0, "positions": 0, "transactions": 0, "orders": 0, "fills": 0}},
            "authority_lock": {"state": "AVAILABLE", "data": {key: False for key in AUTHORITY}}}}
        value = tuesday_command_projection(snapshot, fixture=True); validate_browser_projection(value)
        self.assertEqual(value["schema_version"], SCHEMA_VERSION); self.assertEqual(value["projection_container"], "CURRENT")
        self.assertEqual(value["underlying_evidence"], "STALE"); self.assertEqual(value["publisher_observation"], "UNAVAILABLE")
        self.assertEqual(value["paper"]["nav"], 10000.0); self.assertFalse(any(value["authority"].values()))

    def test_unsafe_authority_is_rejected(self):
        value = tuesday_command_projection({"sections": {"authority_lock": {"state": "AVAILABLE", "data": {"broker": True}}}}, fixture=True)
        with self.assertRaisesRegex(ValueError, "TUESDAY_PROJECTION_INVALID"): validate_browser_projection(value)

    def test_rehearsal_has_all_52_named_synthetic_scenarios(self):
        value = json.loads((HERE / "fixtures/superbatch20_tuesday_rehearsal.json").read_text())
        self.assertEqual(value["scenario_count"], 52); self.assertEqual(len(value["scenarios"]), 52)
        self.assertEqual(len(set(value["scenarios"])), 52); self.assertFalse(any(value["authority"].values()))

    def test_browser_contract_has_no_private_or_control_surface(self):
        source = (ROOT / "FRONT END/src/MobExpansionWing.tsx").read_text()
        provider = (ROOT / "FRONT END/src/ExpansionWingSnapshotProvider.tsx").read_text()
        self.assertEqual(provider.count("fetch("), 1); self.assertNotIn("fetch(", source)
        for prohibited in ("session_results", "latest_shadow_counterfactual", "createOrder", "broker/connect", "ledger/write"):
            self.assertNotIn(prohibited, source)

    def test_ui_and_responsive_contracts_cover_tuesday_rooms(self):
        source = (ROOT / "FRONT END/src/MobExpansionWing.tsx").read_text(); css = (ROOT / "FRONT END/src/MobExpansionWing.css").read_text()
        for marker in ("Tuesday Test Day Command Center", "Independent Sleeve Laboratory", "Post-Close Audit", SYNTHETIC_LABEL): self.assertIn(marker, source)
        for marker in ("min-width:0", "overflow-x:clip", "focus-visible", "prefers-reduced-motion", "scroll-margin-top"): self.assertIn(marker, css)


if __name__ == "__main__": unittest.main()
