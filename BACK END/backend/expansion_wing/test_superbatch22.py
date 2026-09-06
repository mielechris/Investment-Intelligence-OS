from __future__ import annotations

import json
import unittest
from pathlib import Path

from expansion_wing.museum_commissioning import (
    AUTHORITY, CONTROL_ROOM_PANELS, MODULE_ROWS, SESSION_PHASES, SYNTHETIC_LABEL,
    ambient_scene, control_room_projection, method_readiness, module_registry,
    post_close_report, professional_readiness, rehearsal, synthetic_sleeves,
    validate_commissioning,
)

HERE = Path(__file__).parent
ROOT = HERE.parents[2]


class MuseumCommissioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((HERE / "fixtures/superbatch22_rehearsal.json").read_text())

    def test_historical_registry_consolidates_28_modules_without_competing_shells(self):
        registry = module_registry()
        self.assertEqual(len(registry), 28)
        self.assertEqual(len({item["module_id"] for item in registry}), 28)
        self.assertEqual(tuple(item["module_id"] for item in registry), CONTROL_ROOM_PANELS)
        self.assertTrue(all(item["disposition"] in {"REUSED", "CONSOLIDATED"} for item in registry))

    def test_control_room_exposes_28_truthful_panels_and_no_control_route(self):
        value = control_room_projection({"sections": {"books": {"state": "CURRENT", "data": {"generated_at": "2026-09-08T20:00:00Z"}}}})
        self.assertEqual(value["panel_count"], 28)
        self.assertEqual(value["browser_methods"], ("GET", "HEAD"))
        self.assertFalse(value["publisher_control"])
        self.assertFalse(any(value["authority"].values()))
        for panel in value["panels"]:
            self.assertEqual(set(panel), {"module_id", "state", "evidence_timestamp", "effective_timestamp", "freshness", "provenance_category", "eligible", "blocker", "next_expected_observation", "scope", "summary"})

    def test_living_quiet_scenes_never_imply_evidence_or_activity(self):
        for phase in SESSION_PHASES:
            for reduced in (False, True):
                value = ambient_scene(session_phase=phase, evidence_state="UNAVAILABLE", reduced_motion=reduced)
                self.assertFalse(value["evidence_movement"])
                for key in ("candidate_implied", "trade_implied", "position_implied", "recommendation_implied", "profit_implied", "provider_implied", "current_evidence_implied"):
                    self.assertFalse(value[key])

    def test_monday_holiday_is_closed_and_all_contracts_remain_visible(self):
        value = rehearsal(self.fixture["scenarios"][0]); validate_commissioning(value)
        self.assertEqual(value["phase"], "CLOSED_HOLIDAY")
        self.assertEqual((len(value["products"]), len(value["methods"]), len(value["sleeves"])), (24, 16, 24))
        self.assertEqual(value["candidate_count"], 0)
        self.assertTrue(all(item["state"] == "INSUFFICIENT_SAMPLE" and item["score"] is None for item in value["methods"]))

    def test_all_tuesday_rehearsals_cover_every_product_method_and_sleeve(self):
        self.assertEqual(len(self.fixture["scenarios"]), 21)
        for scenario in self.fixture["scenarios"]:
            value = rehearsal(scenario); validate_commissioning(value)
            self.assertEqual(len({item["product_id"] for item in value["products"]}), 24)
            self.assertEqual(len({item["method_id"] for item in value["methods"]}), 16)
            self.assertEqual(len({item["sleeve_id"] for item in value["sleeves"]}), 24)
            self.assertLessEqual(value["candidate_count"], 5)
            self.assertFalse(any(value["authority"].values()))

    def test_fixture_candidate_requires_exact_lineage_and_never_gains_authority(self):
        scenario = next(item for item in self.fixture["scenarios"] if item["scenario"] == "valid_immutable_candidate")
        value = rehearsal(scenario); validate_commissioning(value)
        self.assertEqual(value["candidate_count"], 1)
        candidate = value["candidates"][0]
        self.assertTrue(candidate["fixture"] and candidate["immutable_lineage"])
        self.assertFalse(candidate["research_eligible"] or candidate["paper_eligible"] or any(candidate["authority"].values()))

    def test_sleeves_are_independent_complete_and_not_operational_capital(self):
        sleeves = synthetic_sleeves()
        self.assertEqual(len(sleeves), 24)
        self.assertTrue(all(item["synthetic_basis"] == 10_000 and item["label"] == SYNTHETIC_LABEL for item in sleeves))
        self.assertTrue(all(not item["pooled"] and not item["operational_capital"] for item in sleeves))
        self.assertTrue(all(item["realized_outcome"] is None and item["unrealized_outcome"] is None for item in sleeves))

    def test_methods_preserve_missing_results_as_null(self):
        methods = method_readiness()
        self.assertEqual(len(methods), 16)
        self.assertTrue(all(item["score"] is None and item["state"] == "INSUFFICIENT_SAMPLE" for item in methods))
        self.assertTrue(all(item["failure_behavior"] == "FAILED_CLOSED" for item in methods))

    def test_professional_sources_remain_attributed_and_non_promotional(self):
        rows = professional_readiness()
        self.assertEqual(len(rows), 6)
        for item in rows:
            self.assertTrue(item["attributed_hypothesis"])
            self.assertFalse(item["candidate_creation"] or item["promotion"] or item["paper_sleeve_creation"] or item["recommendation"])
            self.assertIsNone(item["score"])
            self.assertFalse(any(item["authority"].values()))

    def test_post_close_report_never_derives_profitability_from_fixture(self):
        result = rehearsal(self.fixture["scenarios"][-2])
        report = post_close_report(result)
        self.assertEqual(report["products_tested"], 24)
        self.assertEqual(report["rankable_methods"], 0)
        self.assertFalse(report["profitability_claim"])
        self.assertEqual(report["operational_paper_changes"], 0)

    def test_no_private_or_mutating_boundary_is_introduced(self):
        source = (HERE / "museum_commissioning.py").read_text()
        for prohibited in ("latest_shadow_counterfactual", "session_results", "subprocess", "requests.", "urllib", "Keychain", "ledger.write", "broker.connect"):
            self.assertNotIn(prohibited, source)
        self.assertEqual(AUTHORITY, {"provider": False, "credential": False, "automatic_promotion": False, "paper_order": False, "broker": False, "ledger_write": False, "live_execution": False})


if __name__ == "__main__": unittest.main()
