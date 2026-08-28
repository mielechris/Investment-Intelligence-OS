from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEATER = ROOT / "FRONT END" / "src" / "InteractiveCaseTheater.tsx"
BROWSER = ROOT / "FRONT END" / "src" / "LiveFactoryBrowser.tsx"
ACTIVATOR = ROOT / "scripts" / "activate_batch9n_interactive_case_theater.py"


class Batch9NInteractiveCaseTheaterContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theater = THEATER.read_text(encoding="utf-8")
        cls.browser = BROWSER.read_text(encoding="utf-8")
        cls.activator = ACTIVATOR.read_text(encoding="utf-8")

    def test_9n_is_additive_on_top_of_9m(self) -> None:
        self.assertIn('import CharacterStoryEngine from "./CharacterStoryEngine"', self.browser)
        self.assertIn('import InteractiveCaseTheater from "./InteractiveCaseTheater"', self.browser)
        self.assertIn("<LivingFactoryExperience />", self.browser)
        self.assertIn("<CharacterStoryEngine />", self.browser)
        self.assertIn("<InteractiveCaseTheater />", self.browser)
        self.assertIn("<MarketValidationStackPanel />", self.browser)
        self.assertIn("<FactoryIntelligenceUI />", self.browser)

    def test_replay_reads_only_existing_same_origin_contracts(self) -> None:
        fetch_targets = re.findall(r'getJson<[^>]+>\(\s*([`\"])(.*?)\1', self.theater, flags=re.S)
        target_text = "\n".join(value for _, value in fetch_targets)
        self.assertIn("/living/overview", target_text)
        self.assertIn("/living/case/${encodeURIComponent(selected.caseId)}", target_text)
        self.assertNotIn("127.0.0.1:8002", self.theater)
        self.assertNotIn("sqlite3", self.theater)
        self.assertNotRegex(self.theater, r'method\s*:\s*["\'](?:POST|PUT|PATCH|DELETE)')
        self.assertNotRegex(self.theater, r'record_object|record_event|submit_paper_order|consume_authorization')

    def test_learning_join_is_exact_and_never_ticker_only(self) -> None:
        self.assertIn("outcomeByCaseId", self.theater)
        self.assertIn("outcomeByCandidateId", self.theater)
        self.assertIn("source_candidate_id", self.theater)
        self.assertNotIn("outcomeByTicker", self.theater)
        self.assertIn("ticker-only learning joins are prohibited", self.theater)
        self.assertIn("no outcome is borrowed from another case with the same ticker", self.theater)

    def test_all_required_replay_stages_exist(self) -> None:
        for marker in (
            '"DISCOVERY", "Discovery"',
            '"RESEARCH", "Research"',
            '"AGENTS", "8 Agents"',
            '"SKEPTIC", "Skeptic"',
            '"COMMITTEE", "Committee"',
            '"RISK", "Risk"',
            '"PAPER", "Paper"',
            '"MONITORING", "Monitoring"',
            '"OUTCOME", "Outcome"',
            '"LEARNING", "Learning"',
        ):
            self.assertIn(marker, self.theater)

    def test_missing_artifacts_remain_waiting(self) -> None:
        self.assertIn("WAITING", self.theater)
        self.assertIn("will not invent a Skeptic challenge", self.theater)
        self.assertIn("never fabricates a transcript", self.theater)
        self.assertIn("does not imply a paper order occurred", self.theater)
        self.assertIn("does not generate demonstration cases", self.theater)

    def test_replay_controls_are_ui_only(self) -> None:
        self.assertIn("PLAY REPLAY", self.theater)
        self.assertIn("UI CURSOR", self.theater)
        self.assertIn("NO FACTORY COMMANDS SENT", self.theater)
        self.assertIn("changes only a browser cursor", self.theater)
        self.assertIn("cannot rerun an agent", self.theater)
        self.assertIn("cannot rerun", self.theater)

    def test_activator_keeps_safety_boundaries(self) -> None:
        required = [
            'BRANCH = "feature/batch9n-interactive-case-theater"',
            "Parent Batch 9M: PRESERVED",
            "Existing Backend 8002: UNCHANGED",
            "Replay authority: BROWSER CURSOR ONLY",
            '"backend_write_permission": False',
            '"trade_execution_permission": False',
            '"live_execution": False',
            '"protected_launch_agents_unchanged": True',
        ]
        for marker in required:
            self.assertIn(marker, self.activator)


if __name__ == "__main__":
    unittest.main()
