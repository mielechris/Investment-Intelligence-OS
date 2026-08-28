import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import APIRouter

import deep_watch_obligations as dwo


class DeepWatchObligationTests(unittest.TestCase):
    def test_requirement_classification_never_drops_requirement(self):
        primary = dwo.classify_requirement(
            "Independent server-demand, hyperscaler-capex, backlog conversion, customer-inventory, and channel-inventory evidence"
        )
        self.assertIn(primary["kind"], {"PRIMARY_EVIDENCE", "CONTEXT_EVIDENCE"})

        portfolio = dwo.classify_requirement(
            "Portfolio holdings and factor exposures to determine marginal diversification and acceptable position sizing"
        )
        self.assertEqual(portfolio["kind"], "PORTFOLIO_CONTEXT")

        generic = dwo.classify_requirement(
            "Independent verification of a completely novel catalyst"
        )
        self.assertEqual(generic["kind"], "CONTEXT_EVIDENCE")

    def test_first_observation_is_baseline_not_material_change(self):
        current = {
            "kind": "PRIMARY_EVIDENCE",
            "status": "PARTIAL",
            "coverage_pct": 50,
            "covered_fact_keys": ["a"],
        }
        changed, reasons = dwo.material_change(None, current)
        self.assertFalse(changed)
        self.assertEqual(reasons, ["BASELINE_CREATED"])

    def test_primary_fact_coverage_change_is_material(self):
        prior = {
            "kind": "PRIMARY_EVIDENCE",
            "status": "PARTIAL",
            "coverage_pct": 50,
            "covered_fact_keys": ["a"],
        }
        current = {
            "kind": "PRIMARY_EVIDENCE",
            "status": "COMPLETE_FACT_COVERAGE",
            "coverage_pct": 100,
            "covered_fact_keys": ["a", "b"],
        }
        changed, reasons = dwo.material_change(prior, current)
        self.assertTrue(changed)
        self.assertIn("COVERAGE_STATE_CHANGED", reasons)
        self.assertIn("FACT_COVERAGE_CHANGED", reasons)

    def test_small_portfolio_snapshot_refresh_is_not_material(self):
        prior = {
            "kind": "PORTFOLIO_CONTEXT",
            "status": "CURRENT",
            "portfolio_snapshot_id": "p1",
            "combined_overlap_weight_pct": 20.0,
            "concentration_level": "LOW",
        }
        current = {
            "kind": "PORTFOLIO_CONTEXT",
            "status": "CURRENT",
            "portfolio_snapshot_id": "p2",
            "combined_overlap_weight_pct": 22.0,
            "concentration_level": "LOW",
        }
        changed, reasons = dwo.material_change(prior, current)
        self.assertFalse(changed)
        self.assertEqual(reasons, [])

    def test_material_portfolio_change_retriggers(self):
        prior = {
            "kind": "PORTFOLIO_CONTEXT",
            "status": "CURRENT",
            "portfolio_snapshot_id": "p1",
            "combined_overlap_weight_pct": 20.0,
            "concentration_level": "LOW",
        }
        current = {
            "kind": "PORTFOLIO_CONTEXT",
            "status": "CURRENT",
            "portfolio_snapshot_id": "p2",
            "combined_overlap_weight_pct": 31.0,
            "concentration_level": "MODERATE",
        }
        changed, reasons = dwo.material_change(prior, current)
        self.assertTrue(changed)
        self.assertIn("PORTFOLIO_OVERLAP_CHANGED", reasons)

    @patch.object(dwo, "_reunderwrite")
    @patch.object(dwo, "sync_obligations")
    @patch.object(dwo, "_maybe_capture_primary")
    @patch.object(dwo, "_requirements")
    @patch.object(dwo, "latest_object")
    @patch.object(dwo, "get_object")
    def test_cycle_only_reunderwrites_on_material_change(
        self,
        get_object,
        latest_object,
        requirements,
        capture,
        sync,
        reunderwrite,
    ):
        get_object.return_value = {"case_id": "case_x", "topic": "Example"}
        latest_object.return_value = {"enabled": True}
        requirements.return_value = ({"decision_id": "d1"}, ["one requirement"])
        capture.return_value = {"attempted": False}
        sync.return_value = {
            "material_change_count": 1,
            "material_changes": [{"obligation_key": "o1"}],
        }
        reunderwrite.return_value = {"deep_watch_reunderwrite_id": "r1"}

        result = dwo.run_obligation_cycle(Mock(), "case_x")

        self.assertEqual(result["state"], "REUNDERWRITTEN")
        reunderwrite.assert_called_once()
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    @patch.object(dwo, "_reunderwrite")
    @patch.object(dwo, "sync_obligations")
    @patch.object(dwo, "_maybe_capture_primary")
    @patch.object(dwo, "_requirements")
    @patch.object(dwo, "latest_object")
    @patch.object(dwo, "get_object")
    def test_cycle_does_not_reunderwrite_baseline(
        self,
        get_object,
        latest_object,
        requirements,
        capture,
        sync,
        reunderwrite,
    ):
        get_object.return_value = {"case_id": "case_x", "topic": "Example"}
        latest_object.return_value = {"enabled": True}
        requirements.return_value = ({"decision_id": "d1"}, ["one requirement"])
        capture.return_value = {"attempted": False}
        sync.return_value = {"material_change_count": 0, "material_changes": []}

        result = dwo.run_obligation_cycle(Mock(), "case_x")

        self.assertEqual(result["state"], "WATCHING")
        reunderwrite.assert_not_called()

    def test_install_wraps_monitor_and_mounts_no_execution_authority(self):
        primary = Mock()
        monitoring = SimpleNamespace(
            refresh_profile=lambda profile: {"profile": profile},
            router=APIRouter(),
        )
        dwo.install_deep_watch_obligation_engine(primary, monitoring)
        self.assertTrue(callable(monitoring.refresh_profile))

        paths = {route.path.lower() for route in dwo.router.routes}
        self.assertIn("/deep-watch/{case_id}/status", paths)
        self.assertIn("/deep-watch/{case_id}/run", paths)
        self.assertFalse(any("execute" in path or "broker" in path or "authorization" in path for path in paths))


if __name__ == "__main__":
    unittest.main()
