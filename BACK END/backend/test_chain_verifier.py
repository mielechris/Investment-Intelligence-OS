import unittest

from chain_verifier import verify_audit


class ChainVerifierTests(unittest.TestCase):
    def valid_audit(self):
        case_id = "case_test"
        packet_id = "packet_test"
        decision_id = "decision_test"
        risk_id = "risk_test"
        execution_id = "paper_test"
        keys = [
            "policy",
            "macro",
            "fundamentals",
            "market_structure",
            "commodities",
            "geo_weather",
            "skeptic",
            "portfolio",
        ]
        agents = [
            {
                "agent_key": key,
                "agent_result_id": f"agent_{key}",
                "case_id": case_id,
                "falsifier": "A contrary observation would weaken this view.",
                "missing_evidence": [],
            }
            for key in keys
        ]
        return {
            "case": {
                "case_id": case_id,
                "evidence_packet_id": packet_id,
                "paper_mode": True,
            },
            "evidence_packets": [
                {
                    "case_id": case_id,
                    "evidence_packet_id": packet_id,
                }
            ],
            "agent_results": agents,
            "committee_decisions": [
                {
                    "case_id": case_id,
                    "decision_id": decision_id,
                    "agents": {agent["agent_key"]: agent for agent in agents},
                    "paper_mode": True,
                }
            ],
            "risk_authorizations": [
                {
                    "case_id": case_id,
                    "decision_id": decision_id,
                    "risk_authorization_id": risk_id,
                    "allowed_notional": 0,
                    "paper_mode": True,
                    "decision": "WATCH_ONLY",
                }
            ],
            "executions": [
                {
                    "case_id": case_id,
                    "decision_id": decision_id,
                    "risk_authorization_id": risk_id,
                    "execution_id": execution_id,
                    "paper_mode": True,
                    "live_execution": False,
                    "execution": "NOT_SUBMITTED",
                }
            ],
            "events": [
                {"event_type": "CASE_CREATED"},
                {"event_type": "EVIDENCE_NORMALIZED"},
                *[{"event_type": "AGENT_COMPLETE"} for _ in range(8)],
                {"event_type": "COMMITTEE_COMPLETE"},
                {"event_type": "RISK_COMPLETE"},
                {"event_type": "PAPER_EXECUTION_CHECKED"},
            ],
        }

    def test_valid_chain_passes(self):
        result = verify_audit(self.valid_audit())
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["counts"]["agent_results"], 8)

    def test_missing_agent_fails(self):
        audit = self.valid_audit()
        audit["agent_results"].pop()
        result = verify_audit(audit)
        self.assertFalse(result["passed"])
        self.assertTrue(any("Expected 8 agent results" in error for error in result["errors"]))

    def test_broken_risk_lineage_fails(self):
        audit = self.valid_audit()
        audit["risk_authorizations"][0]["decision_id"] = "decision_wrong"
        result = verify_audit(audit)
        self.assertFalse(result["passed"])
        self.assertIn("Risk decision_id lineage mismatch", result["errors"])

    def test_live_execution_flag_fails(self):
        audit = self.valid_audit()
        audit["executions"][0]["live_execution"] = True
        result = verify_audit(audit)
        self.assertFalse(result["passed"])
        self.assertIn("Live execution flag must be false", result["errors"])


if __name__ == "__main__":
    unittest.main()
