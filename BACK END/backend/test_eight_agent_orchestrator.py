import unittest

import eight_agent_orchestrator as orch


class EightAgentOrchestratorTests(unittest.TestCase):

    def _specialists(self, *, complete=True):
        status = "complete" if complete else "error"
        return {
            key: {
                "agent_key": key,
                "agent": key,
                "status": status,
                "disposition": "WATCH",
                "confidence": 0.7,
                "headline": f"{key} headline",
                "view": f"{key} view",
                "falsifier": f"{key} falsifier",
            }
            for key in orch.FIRST_WAVE + orch.SECOND_WAVE
        }

    def test_wave_plan_contains_exactly_eight_agents(self):
        plan = orch.agent_wave_plan()
        self.assertEqual(len(plan["all_agents"]), 8)
        self.assertEqual(len(set(plan["all_agents"])), 8)
        self.assertEqual(plan["second_wave"], ["skeptic", "portfolio"])
        self.assertFalse(plan["trade_execution_permission"])
        self.assertFalse(plan["live_execution"])

    def test_peer_context_is_governed_analysis_not_trade_evidence(self):
        specialists = self._specialists()
        peer = orch._peer_context_items({key: specialists[key] for key in orch.FIRST_WAVE})
        self.assertEqual(len(peer), len(orch.FIRST_WAVE))
        for item in peer:
            self.assertEqual(item["evidence_type"], "agent_context")
            self.assertFalse(item["gap_resolution_eligible"])
            self.assertFalse(item["trade_signal"])
            self.assertFalse(item["trade_execution_permission"])

    def test_portfolio_evidence_can_include_skeptic_challenge(self):
        specialists = self._specialists()
        completed = {key: specialists[key] for key in orch.FIRST_WAVE}
        skeptic_evidence = orch.second_wave_evidence([], completed)
        self.assertEqual(len(skeptic_evidence), 6)
        self.assertFalse(any("skeptic" in str(item.get("url") or "") for item in skeptic_evidence))

        completed["skeptic"] = specialists["skeptic"]
        portfolio_evidence = orch.second_wave_evidence([], completed)
        self.assertEqual(len(portfolio_evidence), 7)
        self.assertTrue(any("skeptic" in str(item.get("url") or "") for item in portfolio_evidence))
        self.assertTrue(all(item.get("gap_resolution_eligible") is False for item in portfolio_evidence))

    def test_committee_guard_allows_watch_only_when_all_desks_complete(self):
        result = orch.committee_guard(
            specialists=self._specialists(),
            evidence_summary={"critical_flags": []},
            requested_disposition="WATCH",
        )
        self.assertEqual(result["final_disposition"], "WATCH")
        self.assertTrue(result["committee_can_watch"])
        self.assertEqual(result["failed_checks"], [])
        self.assertFalse(result["paper_order_permission"])
        self.assertFalse(result["trade_execution_permission"])
        self.assertFalse(result["live_execution"])

    def test_missing_agent_forces_no_trade(self):
        specialists = self._specialists()
        specialists.pop("portfolio")
        result = orch.committee_guard(
            specialists=specialists,
            evidence_summary={"critical_flags": []},
            requested_disposition="WATCH",
        )
        self.assertEqual(result["final_disposition"], "NO_TRADE")
        self.assertIn("all_eight_agents_complete", result["failed_checks"])
        self.assertIn("portfolio_complete", result["failed_checks"])

    def test_stale_or_missing_evidence_forces_no_trade(self):
        for flag in ("NO_EVIDENCE_SUPPLIED", "ALL_EVIDENCE_STALE"):
            with self.subTest(flag=flag):
                result = orch.committee_guard(
                    specialists=self._specialists(),
                    evidence_summary={"critical_flags": [flag]},
                    requested_disposition="WATCH",
                )
                self.assertEqual(result["final_disposition"], "NO_TRADE")

    def test_orchestrator_routes_have_no_execution_or_authorization(self):
        paths = {route.path.lower() for route in orch.router.routes}
        self.assertIn("/orchestration/plan", paths)
        self.assertTrue(any(path.endswith("/run") for path in paths))
        self.assertFalse(any("execute" in path or "broker" in path or "authorization" in path for path in paths))


if __name__ == "__main__":
    unittest.main()
