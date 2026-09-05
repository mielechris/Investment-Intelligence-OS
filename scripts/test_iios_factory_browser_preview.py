from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import iios_factory_browser_preview as preview


class FactoryBrowserPreviewTest(unittest.TestCase):
    def _write(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_stack_reads_sanitized_sidecars_without_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            telemetry = root / "telemetry"
            state = root / "market-validation"
            self._write(
                telemetry / "latest.json",
                {
                    "generated_at": "2099-01-01T00:00:00+00:00",
                    "health": {"state": "HEALTHY"},
                    "radar": {"governed_universe_count": 518},
                    "safety": {"live_execution": False},
                },
            )
            self._write(
                state / "latest_market_validation.json",
                {"status": "WAITING", "benchmark_complete": False},
            )
            self._write(
                state / "browser" / "shadow_strategy.json",
                {"status": "WARMUP_COLLECTING_COMPLETE_SESSIONS", "complete_session_count": 1},
            )
            self._write(
                state / "browser" / "outcome_learning.json",
                {"status": "WAITING_FOR_COMPLETE_9H_SESSIONS", "outcome_count": 0},
            )

            stack = preview.build_validation_stack(
                telemetry_dir=telemetry,
                state_dir=state,
            )
            self.assertEqual(stack["schema_version"], preview.SCHEMA_VERSION)
            self.assertEqual(
                stack["layers"]["factory_telemetry"]["payload"]["radar"]["governed_universe_count"],
                518,
            )
            self.assertEqual(stack["safety"]["ledger_access"], "NONE")
            self.assertFalse(stack["safety"]["live_execution"])

    def test_missing_sidecar_is_explicit_waiting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stack = preview.build_validation_stack(
                telemetry_dir=root / "telemetry",
                state_dir=root / "market-validation",
            )
            self.assertEqual(stack["layers"]["market_validation"]["availability"], "WAITING")
            self.assertIsNone(stack["layers"]["market_validation"]["payload"])


if __name__ == "__main__":
    unittest.main()
