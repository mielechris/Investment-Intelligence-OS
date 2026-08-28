from __future__ import annotations

import re
import unittest
from pathlib import Path

import iios_factory_browser_preview as preview

ROOT = Path(__file__).resolve().parents[1]
THEATER = ROOT / "FRONT END" / "src" / "InteractiveCaseTheater.tsx"
BROWSER = ROOT / "FRONT END" / "src" / "LiveFactoryBrowser.tsx"


class Batch9NInteractiveCaseTheaterContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theater = THEATER.read_text(encoding="utf-8")
        cls.browser = BROWSER.read_text(encoding="utf-8")

    def test_theater_is_composed_after_9l_and_9m(self) -> None:
        self.assertIn('import InteractiveCaseTheater from "./InteractiveCaseTheater"', self.browser)
        self.assertIn("<LivingFactoryExperience />", self.browser)
        self.assertIn("<CharacterStoryEngine />", self.browser)
        self.assertIn("<InteractiveCaseTheater />", self.browser)
        self.assertIn("<MarketValidationStackPanel />", self.browser)
        self.assertIn("<FactoryIntelligenceUI />", self.browser)

    def test_replay_uses_only_read_only_same_origin_contracts(self) -> None:
        self.assertIn('getJson<LivingSnapshot>("/living/overview"', self.theater)
        self.assertIn('getJson<CaseDetail>(`/living/case/${encodeURIComponent(selected.caseId)}`', self.theater)
        self.assertNotIn("127.0.0.1:8002", self.theater)
        self.assertNotIn("sqlite3", self.theater)
        self.assertNotRegex(self.theater, r'method\s*:\s*["\'](?:POST|PUT|PATCH|DELETE)')
        for forbidden in (
            "record_object",
            "record_event",
            "submit_paper_order",
            "consume_authorization",
            "execute_trade",
        ):
            self.assertNotIn(forbidden, self.theater)

    def test_exact_replay_stage_contract(self) -> None:
        stage_pairs = re.findall(r'\["([A-Z_]+)", "([^"]+)"\]', self.theater)
        self.assertEqual(
            stage_pairs[:10],
            [
                ("DISCOVERY", "Discovery"),
                ("RESEARCH", "Research"),
                ("AGENTS", "8 Agents"),
                ("SKEPTIC", "Skeptic"),
                ("COMMITTEE", "Committee"),
                ("RISK", "Risk"),
                ("PAPER", "Paper"),
                ("MONITORING", "Monitoring"),
                ("OUTCOME", "Outcome"),
                ("LEARNING", "Learning"),
            ],
        )

    def test_missing_raw_specialist_text_is_never_fabricated(self) -> None:
        self.assertIn("RAW AGENT TEXT NOT EXPOSED BY READ-ONLY CONTRACT", self.theater)
        self.assertIn("RAW SKEPTIC TEXT NOT EXPOSED BY READ-ONLY CONTRACT", self.theater)
        self.assertIn("never fabricates an agent debate transcript", self.theater)
        self.assertIn("will not invent a Skeptic challenge", self.theater)
        self.assertIn("No learning label is manufactured", self.theater)

    def test_replay_is_cursor_only_and_cannot_execute(self) -> None:
        required = [
            "REPLAY CURSOR ONLY · DOES NOT EXECUTE FACTORY",
            "UI CURSOR",
            "NO FACTORY COMMANDS SENT",
            "This theater changes only a browser cursor",
            "LIVE EXECUTION FALSE",
        ]
        for marker in required:
            self.assertIn(marker, self.theater)

    def test_signal_provenance_is_preserved_in_case_library(self) -> None:
        for badge in ("BOTH", "9E RADAR", "JESSE DISLOCATION", "MANUAL / OTHER"):
            self.assertIn(badge, self.theater)
        self.assertIn("Signal provenance", self.theater)

    def test_current_9j_browser_schema_is_canonical_and_legacy_aliases_are_truthful(self) -> None:
        payload = {
            "status": "ACTIVE",
            "recent_outcomes": [
                {
                    "ticker": "NVDA",
                    "case_id": "case_nvda",
                    "session_id": "2026-08-28",
                    "market_outcome": "UP",
                    "decision_quality": "GOOD_CALL",
                    "longest_available_horizon": "5d",
                    "forward_return_pct": 8.25,
                    "benchmark_return_pct": 1.75,
                    "relative_return_pct": 6.50,
                    "benchmark_source": "SPY",
                    "measured_at": "2026-09-04T20:00:00+00:00",
                },
                {
                    "ticker": "LITE",
                    "case_id": "case_lite",
                    "session_id": "2026-08-28",
                    "market_outcome": "UP",
                    "decision_quality": "GOOD_CALL",
                    "longest_available_horizon": "20d",
                    "forward_return_pct": 12.0,
                    "benchmark_return_pct": 3.0,
                    "relative_return_pct": 9.0,
                    "measured_at": "2026-09-25T20:00:00+00:00",
                },
            ],
        }
        normalized = preview._normalize_outcome_learning_payload(payload)
        nvda, lite = normalized["recent_outcomes"]

        self.assertEqual(nvda["market_outcome"], "UP")
        self.assertEqual(nvda["decision_quality"], "GOOD_CALL")
        self.assertEqual(nvda["forward_return_pct"], 8.25)
        self.assertEqual(nvda["benchmark_return_pct"], 1.75)
        self.assertEqual(nvda["relative_return_pct"], 6.50)
        self.assertEqual(nvda["longest_available_horizon"], "5d")
        self.assertEqual(nvda["market_outcome_label"], "UP")
        self.assertEqual(nvda["decision_quality_label"], "GOOD_CALL")
        self.assertEqual(nvda["labeled_at"], nvda["measured_at"])
        self.assertEqual(nvda["return_5d_pct"], 8.25)
        self.assertNotIn("return_1d_pct", nvda)
        self.assertNotIn("return_3d_pct", nvda)

        self.assertEqual(lite["return_20d_pct"], 12.0)
        self.assertNotIn("return_5d_pct", lite)
        self.assertEqual(
            list(lite)[:10],
            [
                "ticker",
                "case_id",
                "session_id",
                "market_outcome",
                "decision_quality",
                "longest_available_horizon",
                "forward_return_pct",
                "benchmark_return_pct",
                "relative_return_pct",
                "measured_at",
            ],
        )


if __name__ == "__main__":
    unittest.main()
