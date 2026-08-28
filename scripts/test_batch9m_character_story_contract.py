from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "FRONT END" / "src" / "CharacterStoryEngine.tsx"
BROWSER = ROOT / "FRONT END" / "src" / "LiveFactoryBrowser.tsx"
TELEMETRY = ROOT / "BACK END" / "backend" / "factory_telemetry.py"


class Batch9MCharacterStoryContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.story = STORY.read_text(encoding="utf-8")
        cls.browser = BROWSER.read_text(encoding="utf-8")
        cls.telemetry = TELEMETRY.read_text(encoding="utf-8")

    def test_story_engine_is_composed_without_replacing_9l(self) -> None:
        self.assertIn('import CharacterStoryEngine from "./CharacterStoryEngine"', self.browser)
        self.assertIn("<LivingFactoryExperience />", self.browser)
        self.assertIn("<CharacterStoryEngine />", self.browser)
        self.assertIn("<MarketValidationStackPanel />", self.browser)
        self.assertIn("<FactoryIntelligenceUI />", self.browser)

    def test_dialogue_source_is_read_only_living_snapshot_only(self) -> None:
        fetch_targets = re.findall(r'fetch\((?:`|")([^`"]+)', self.story)
        self.assertEqual(fetch_targets, ["/living/overview"])
        self.assertNotIn("sqlite3", self.story)
        self.assertNotIn("127.0.0.1:8002", self.story)
        self.assertNotRegex(self.story, r'fetch\([^\n]+method\s*:\s*["\'](?:POST|PUT|PATCH|DELETE)')
        self.assertIn("NO EVENT → NO DIALOGUE", self.story)
        self.assertIn("not raw agent output", self.story.lower())
        self.assertIn("never create activity", self.story)

    def test_all_9g_meaningful_event_types_have_explicit_story_handling(self) -> None:
        match = re.search(
            r"MEANINGFUL_EVENT_TYPES\s*=\s*\{(?P<body>.*?)\n\}",
            self.telemetry,
            flags=re.S,
        )
        self.assertIsNotNone(match)
        event_types = set(re.findall(r'"([A-Z0-9_]+)"', match.group("body")))
        expected = {
            "OPPORTUNITY_PROMOTED_TO_CASE",
            "COMMITTEE_COMPLETE",
            "RISK_COMPLETE",
            "GOVERNED_PAPER_ORDER_CREATED",
            "AUTO_MONITOR_FAILED",
            "OPPORTUNITY_AUTOMATION_CYCLE_FAILED",
            "HIGH_SPEED_MARKET_RADAR_COMPLETE",
        }
        self.assertEqual(event_types, expected)
        for event_type in event_types:
            self.assertIn(f'type === "{event_type}"', self.story)

    def test_cast_is_max_plus_exact_eight_specialists(self) -> None:
        keys = re.findall(r'\n\s*key: "([a-z_]+)",\n\s*name:', self.story)
        self.assertEqual(
            keys,
            [
                "max",
                "policy",
                "macro",
                "fundamentals",
                "market_structure",
                "commodities",
                "geo_weather",
                "skeptic",
                "portfolio",
            ],
        )
        self.assertIn("Cute thesis. Now tell me how it dies.", self.story)
        self.assertIn("A good idea can still be a stupid position.", self.story)

    def test_character_layer_preserves_governance_language(self) -> None:
        required = [
            "LIVE EXECUTION FALSE",
            "not trade instructions",
            "not a market signal",
            "Paper means rehearsal",
            "Nobody invents what did not happen",
            "No extra story until the ledger gives us one",
        ]
        for marker in required:
            self.assertIn(marker, self.story)


if __name__ == "__main__":
    unittest.main()
