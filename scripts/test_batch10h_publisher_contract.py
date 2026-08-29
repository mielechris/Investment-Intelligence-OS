from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class Batch10HPublisherContractTest(unittest.TestCase):
    def test_missing_research_publishes_truthful_warmup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "browser" / "historical_market_intelligence.json"
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("iios_historical_market_intelligence_publisher.py")), "--research-dir", str(root / "research"), "--output", str(output)], check=True, capture_output=True, text=True)
            self.assertIn("HISTORICAL_RESEARCH_WARM_UP", result.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "HISTORICAL_RESEARCH_WARM_UP")
            self.assertFalse(payload["safety"]["capital_authority"])
            self.assertFalse(payload["safety"]["trade_execution_permission"])
            self.assertFalse(payload["safety"]["live_execution"])


if __name__ == "__main__":
    unittest.main()
