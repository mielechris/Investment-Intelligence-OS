import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
import requirement_lineage_guard as guard


class GapHunterNineDeskUpgradeTests(unittest.TestCase):
    @patch.object(guard, "record_event")
    @patch.object(guard, "record_object")
    @patch.object(guard, "get_object")
    @patch("eight_agent_orchestrator.run_eight_agent_orchestration")
    def test_gap_hunt_is_superseded_by_nine_desk_reunderwrite(
        self,
        run_nine,
        get_object,
        record_object,
        record_event,
    ):
        case_id = "case_mu"
        packet_id = "packet_gap_mu"

        module = SimpleNamespace()
        module._latest_decision = lambda _case_id: {
            "decision_id": "prior_decision",
            "case_id": case_id,
            "topic": "Micron opportunity review",
            "required_evidence": ["fresh MU evidence"],
            "confidence": 0.9,
            "disposition": "WATCH",
            "agents": {},
            "evidence_summary": {},
        }
        module._qualification_assessment = lambda committee, risk, matrix: {
            "stage": "WATCH",
            "qualified_buy_candidate": False,
            "unmet_requirements": ["governed_blockers_clear"],
            "checks": {},
            "paper_buy_enabled": False,
            "paper_mode": True,
            "live_execution": False,
        }

        def prior_run(_case_id):
            # This represents successful evidence acquisition/persistence from the
            # legacy Gap Hunter stage. Its Committee authority will be superseded.
            return {
                "gap_hunt_id": "gap_hunt_mu",
                "case_id": case_id,
                "topic": "Micron opportunity review",
                "resolution_matrix": [],
                "qualification": {"evidence_packet_id": packet_id},
                "committee": {"decision_id": "legacy"},
                "risk": {},
                "execution": {},
            }

        module.run_gap_hunt = prior_run

        get_object.side_effect = lambda object_id: (
            {
                "evidence_packet_id": packet_id,
                "case_id": case_id,
                "items": [{"claim": "fresh evidence"}],
                "summary": {"evidence_count": 1},
            }
            if object_id == packet_id
            else {
                "case_id": case_id,
                "topic": "Micron opportunity review",
                "evidence": [],
                "evidence_summary": {},
            }
        )

        run_nine.return_value = {
            "orchestration": {
                "orchestration_id": "orch_mu",
                "trade_execution_permission": False,
                "live_execution": False,
            },
            "historical_pattern": {
                "historical_signal": "MIXED_PRECEDENT",
                "trade_execution_permission": False,
                "live_execution": False,
            },
            "committee": {
                "decision_id": "decision_nine",
                "case_id": case_id,
                "topic": "Micron opportunity review",
                "required_evidence": ["remaining evidence"],
                "confidence": 0.88,
                "disposition": "WATCH",
                "agents": {},
                "evidence_summary": {"evidence_count": 1},
                "paper_mode": True,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        }

        original_evaluate = main.evaluate_decision
        original_submit = main.submit_paper_order
        main.evaluate_decision = lambda committee: {
            "risk_authorization_id": "risk_nine",
            "decision": "VETOED",
            "triggered_rules": ["OPEN_EVIDENCE_REQUIREMENTS"],
            "required_evidence_reconciliation": {"blocking_count": 1},
        }
        main.submit_paper_order = lambda request: {
            "status": "BLOCKED",
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }
        try:
            guard.install_requirement_lineage_guard(module)
            result = module.run_gap_hunt(case_id)
        finally:
            main.evaluate_decision = original_evaluate
            main.submit_paper_order = original_submit

        self.assertTrue(result["nine_desk_committee_authoritative"])
        self.assertFalse(result["legacy_committee_authoritative"])
        self.assertEqual(result["committee"]["decision_id"], "decision_nine")
        self.assertEqual(result["historical_pattern"]["historical_signal"], "MIXED_PRECEDENT")
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])
        run_nine.assert_called_once_with(case_id)
        self.assertGreaterEqual(record_object.call_count, 3)
        self.assertGreaterEqual(record_event.call_count, 2)


if __name__ == "__main__":
    unittest.main()
