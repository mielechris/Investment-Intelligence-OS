import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


class FakeResponse:
    output_text = json.dumps({
        "headline": "Deterministic committee result",
        "summary": "Eight specialist outputs were reviewed under paper-mode governance.",
        "agreement": "The case requires evidence-aware monitoring.",
        "dissent": "The thesis is not strong enough to authorize capital.",
        "bull_case": "The supplied thesis could improve if confirming evidence arrives.",
        "bear_case": "Missing evidence and uncertainty weaken the thesis.",
        "required_evidence": ["fresh confirming market evidence"],
        "confidence": 0.72,
        "disposition": "WATCH",
        "floor_comment": "The committee approved more homework."
    })


class FakeResponses:
    def create(self, **kwargs):
        return FakeResponse()


class FakeOpenAI:
    def __init__(self, *args, **kwargs):
        self.responses = FakeResponses()


class FactoryChainTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IIOS_DB_PATH"] = str(Path(self.tempdir.name) / "factory_test.db")

        import ledger
        import main
        self.ledger = importlib.reload(ledger)
        self.main = importlib.reload(main)
        self.ledger.init_ledger()

    def tearDown(self):
        self.tempdir.cleanup()

    def specialist_stub(self, agent_key, topic, evidence=None):
        return {
            "agent_key": agent_key,
            "agent": self.main.AGENT_CONFIGS[agent_key]["name"],
            "room": self.main.AGENT_CONFIGS[agent_key]["room"],
            "status": "complete",
            "topic": topic,
            "headline": f"{agent_key} complete",
            "view": "Deterministic specialist test output.",
            "confidence": 0.70,
            "disposition": "WATCH",
            "missing_evidence": [],
            "falsifier": "Contradictory fresh evidence.",
            "floor_comment": "Test desk complete.",
        }

    def test_full_factory_chain_persists_audit_lineage(self):
        now = datetime.now(timezone.utc).isoformat()
        with patch.object(self.main, "run_specialist", side_effect=self.specialist_stub), \
             patch.object(self.main, "OpenAI", FakeOpenAI):
            result = self.main.run_factory(
                self.main.TopicRequest(
                    topic="Deterministic semiconductor paper thesis",
                    evidence=[{
                        "claim": "Fresh deterministic market evidence",
                        "source": "Federal Reserve",
                        "url": "https://www.federalreserve.gov/example",
                        "source_type": "official",
                        "evidence_type": "policy",
                        "observed_at": now,
                    }],
                )
            )

        self.assertEqual(
            result["chain"],
            [
                "CASE_CREATED",
                "EVIDENCE_NORMALIZED",
                "EIGHT_SPECIALISTS_COMPLETE",
                "COMMITTEE_COMPLETE",
                "RISK_COMPLETE",
                "PAPER_EXECUTION_CHECKED",
            ],
        )
        self.assertEqual(result["risk"]["decision"], "VETOED")
        self.assertEqual(result["execution"]["status"], "blocked")
        self.assertEqual(result["execution"]["execution"], "NOT_SUBMITTED")

        case_id = result["case"]["case_id"]
        audit = self.main.get_case_audit(case_id)
        self.assertEqual(len(audit["evidence_packets"]), 1)
        self.assertEqual(len(audit["agent_results"]), 8)
        self.assertEqual(len(audit["committee_decisions"]), 1)
        self.assertEqual(len(audit["risk_authorizations"]), 1)
        self.assertEqual(len(audit["executions"]), 1)

        event_types = [event["event_type"] for event in audit["events"]]
        self.assertIn("CASE_CREATED", event_types)
        self.assertIn("EVIDENCE_NORMALIZED", event_types)
        self.assertEqual(event_types.count("AGENT_COMPLETE"), 8)
        self.assertIn("COMMITTEE_COMPLETE", event_types)
        self.assertIn("RISK_COMPLETE", event_types)
        self.assertIn("PAPER_EXECUTION_CHECKED", event_types)


if __name__ == "__main__":
    unittest.main()
