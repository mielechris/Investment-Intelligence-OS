import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute

import factory_intelligence_ui as ui


class GroupBatch8GFactoryIntelligenceUITests(unittest.TestCase):
    def _factory(self):
        return {
            "rooms": [
                {
                    "key": "EVIDENCE",
                    "label": "Evidence Acquisition",
                    "count": 1,
                    "activity_count": 2,
                }
            ],
            "activity": {
                "recent_event_count": 2,
                "recent_events": [
                    {
                        "event_type": "AGENT_COMPLETE",
                        "payload": {"agent_key": "policy"},
                    }
                ],
            },
            "cases": [
                {
                    "case_id": "case_test",
                    "ticker": "TEST",
                    "topic": "Test thesis",
                    "stage": "COMMITTEE",
                    "agent_count": 8,
                    "committee": "WATCH",
                    "committee_confidence": 0.71,
                    "risk": "HOLD",
                    "qualified": False,
                    "trade_execution_permission": True,
                    "live_execution": True,
                }
            ],
            "portfolio": {},
            "validation": {},
            "safety": {
                "violations": 0,
                "all_invariants": True,
            },
        }

    def _council(self):
        return {
            "packet_count": 1,
            "latest_packet": {
                "multi_model_council_packet_id": "mm_test",
                "case_id": "case_test",
                "views": [
                    {
                        "model": "IIOS_OPENAI_CORE",
                        "status": "AVAILABLE",
                        "stance": "MIXED",
                        "confidence": 0.75,
                        "summary": "Governed core view.",
                        "citation_count": 2,
                    },
                    {
                        "model": "KIMI_RESEARCH",
                        "status": "AVAILABLE",
                        "stance": "FAVORABLE",
                        "confidence": 0.8,
                        "summary": "Deep research view.",
                        "citation_count": 5,
                        "untrusted_model_output": True,
                    },
                ],
                "reconciliation": {
                    "available_model_count": 2,
                    "consensus_stance": "FAVORABLE",
                    "consensus_score": 0.51,
                    "divergence_score": 0.5,
                    "directional_conflict": False,
                    "skeptic_escalation_recommended": True,
                },
            },
        }

    def _calibration(self):
        return {
            "calibration_version": "TEST",
            "evaluation_count": 10,
            "minimum_samples_per_model_task": 5,
            "minimum_mature_models_per_task": 2,
            "recommended_weight_bounds": {
                "minimum": 0.75,
                "maximum": 1.25,
            },
            "latest_calibration": {
                "tasks": {
                    "POLICY_MACRO": {
                        "status": "READY_FOR_MANUAL_REVIEW",
                        "mature_model_count": 2,
                        "minimum_mature_models_required": 2,
                        "model_recommendations": {
                            "IIOS_OPENAI_CORE": {
                                "sample_count": 5,
                                "mature": True,
                                "quality_score": 0.91,
                                "composite_score": 0.90,
                                "recommended_task_weight": 1.08,
                                "recommendation_active": True,
                            },
                            "KIMI_RESEARCH": {
                                "sample_count": 5,
                                "mature": True,
                                "quality_score": 0.82,
                                "composite_score": 0.80,
                                "recommended_task_weight": 0.92,
                                "recommendation_active": True,
                            },
                        },
                    }
                }
            },
        }

    def _production(self):
        return {
            "strict_universe_verified": True,
            "cme_fedwatch": {
                "latest_snapshot_source_verified": True,
            },
        }

    @patch.object(
        ui.grok_provider,
        "configuration_status",
        return_value={
            "configured": False,
            "credential_present": False,
            "credential_exposed": False,
        },
    )
    @patch.object(
        ui.kimi_provider,
        "configuration_status",
        return_value={
            "configured": True,
            "credential_present": True,
            "credential_exposed": False,
            "model_preference": "kimi-k3",
        },
    )
    @patch.object(ui, "production_source_status")
    @patch.object(ui, "calibration_status")
    @patch.object(ui, "council_status")
    @patch.object(ui, "factory_room_status")
    def test_overview_uses_real_sources_and_never_copies_authority(
        self,
        factory,
        council,
        calibration,
        production,
        _kimi,
        _grok,
    ):
        factory.return_value = self._factory()
        council.return_value = self._council()
        calibration.return_value = self._calibration()
        production.return_value = self._production()

        overview = ui.build_overview()

        self.assertEqual(overview["data_state"], "LIVE")
        self.assertEqual(overview["system_version"], "0.20.0")
        self.assertEqual(overview["case_count"], 1)
        self.assertEqual(
            overview["council"]["reconciliation"][
                "consensus_stance"
            ],
            "FAVORABLE",
        )
        self.assertFalse(
            overview["cases"][0][
                "trade_execution_permission"
            ]
        )
        self.assertFalse(
            overview["cases"][0]["live_execution"]
        )
        self.assertFalse(
            overview["auto_trade_authority"]
        )
        self.assertFalse(
            overview["trade_execution_permission"]
        )
        self.assertFalse(overview["live_execution"])

    @patch.object(
        ui.grok_provider,
        "configuration_status",
        side_effect=RuntimeError("secret-value-must-not-render"),
    )
    @patch.object(
        ui.kimi_provider,
        "configuration_status",
        side_effect=RuntimeError("provider down"),
    )
    @patch.object(
        ui,
        "production_source_status",
        side_effect=RuntimeError("provider down"),
    )
    @patch.object(
        ui,
        "calibration_status",
        side_effect=RuntimeError("database down"),
    )
    @patch.object(
        ui,
        "council_status",
        side_effect=RuntimeError("database down"),
    )
    @patch.object(
        ui,
        "factory_room_status",
        side_effect=RuntimeError("database down"),
    )
    def test_dependency_failures_render_partial_unknown_not_invented(
        self,
        _factory,
        _council,
        _calibration,
        _production,
        _kimi,
        _grok,
    ):
        overview = ui.build_overview()
        rendered = repr(overview)

        self.assertEqual(overview["data_state"], "PARTIAL")
        self.assertEqual(overview["case_count"], 0)
        self.assertEqual(
            overview["calibration"]["availability"],
            "NO_CALIBRATION_AVAILABLE",
        )
        self.assertNotIn(
            "secret-value-must-not-render",
            rendered,
        )
        for source in overview[
            "source_availability"
        ].values():
            self.assertEqual(
                source["availability"],
                "OFFLINE",
            )

    @patch.object(ui, "get_object")
    @patch.object(ui, "latest_object")
    def test_case_detail_is_read_only_and_zero_authority(
        self,
        latest,
        get_object,
    ):
        get_object.return_value = {
            "case_id": "case_test",
            "topic": "Test thesis",
            "ticker": "TEST",
        }
        latest.side_effect = lambda object_type, case_id=None: {
            "committee_decision": {
                "decision_id": "decision_1",
                "disposition": "WATCH",
                "confidence": 0.7,
            },
            "risk_authorization": {
                "decision": "APPROVED",
                "trade_execution_permission": True,
            },
            "governed_paper_execution": {
                "execution": "PAPER_ORDER_CREATED",
                "live_execution": True,
            },
            ui.COUNCIL_TYPE: {
                "multi_model_council_packet_id": "mm_1",
                "views": [],
            },
        }.get(object_type)

        detail = ui.build_case_detail("case_test")

        self.assertEqual(detail["case_id"], "case_test")
        self.assertFalse(detail["capital_authority"])
        self.assertFalse(detail["auto_trade_authority"])
        self.assertFalse(
            detail["trade_execution_permission"]
        )
        self.assertFalse(detail["live_execution"])

    @patch.object(ui, "get_object", return_value=None)
    def test_unknown_case_fails_closed(self, _get_object):
        with self.assertRaisesRegex(
            ValueError,
            "Unknown case_id",
        ):
            ui.build_case_detail("missing_case")

    def test_calibration_is_task_specific_and_manual_only(self):
        matrix = ui._calibration_matrix(
            self._calibration()
        )
        self.assertFalse(
            matrix["universal_model_weighting"]
        )
        self.assertTrue(
            matrix["manual_promotion_required"]
        )
        self.assertFalse(
            matrix[
                "automatically_applied_to_council"
            ]
        )
        policy = next(
            row
            for row in matrix["tasks"]
            if row["task_type"] == "POLICY_MACRO"
        )
        self.assertEqual(
            policy["status"],
            "READY_FOR_MANUAL_REVIEW",
        )
        self.assertFalse(
            policy[
                "automatically_applied_to_council"
            ]
        )

    def test_ui_router_is_get_only(self):
        routes = [
            route
            for route in ui.router.routes
            if isinstance(route, APIRoute)
        ]
        self.assertEqual(len(routes), 3)
        self.assertTrue(
            all(
                "GET" in route.methods
                and route.methods <= {"GET", "HEAD"}
                for route in routes
            )
        )

    def test_status_declares_truth_and_safety_contract(self):
        status = ui.status()
        self.assertTrue(status["installed"])
        self.assertTrue(status["read_only_aggregation"])
        self.assertTrue(status["unknown_state_semantics"])
        self.assertFalse(status["committee_override"])
        self.assertFalse(status["risk_override"])
        self.assertFalse(status["capital_authority"])
        self.assertFalse(status["auto_trade_authority"])
        self.assertFalse(
            status["trade_execution_permission"]
        )
        self.assertFalse(status["live_execution"])


if __name__ == "__main__":
    unittest.main()
