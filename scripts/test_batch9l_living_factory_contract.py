from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import iios_factory_browser_preview as preview


class Batch9LLivingFactoryContractTest(unittest.TestCase):
    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_living_snapshot_merges_sidecars_and_read_only_backend_gets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            telemetry = root / "telemetry"
            state = root / "market-validation"
            self._write(
                telemetry / "latest.json",
                {
                    "generated_at": "2099-01-01T00:00:00+00:00",
                    "radar": {"governed_universe_count": 518},
                    "recent_promotions": [
                        {
                            "case_id": "case_nvda",
                            "ticker": "NVDA",
                            "source_candidate_id": "candidate_9e_nvda",
                            "agents": {"completed_count": 8},
                        }
                    ],
                    "safety": {"live_execution": False},
                },
            )
            self._write(
                state / "latest_market_validation.json",
                {"status": "WARM-UP", "metrics": {}},
            )
            self._write(
                state / "shadow_strategy" / "latest_shadow_counterfactual.json",
                {"status": "WARM-UP", "complete_session_count": 1},
            )
            self._write(
                state / "browser" / "outcome_learning.json",
                {"status": "WARM-UP", "outcome_count": 0},
            )

            def fake_get(path: str, *, timeout_seconds: float = 3.0) -> dict[str, Any]:
                del timeout_seconds
                if path == "/experience/factory-intelligence/overview":
                    return {
                        "cases": [{"case_id": "case_nvda", "ticker": "NVDA"}],
                        "factory": {"desks": []},
                        "safety": {"live_execution": False},
                    }
                if path == "/intelligence/dislocation/status":
                    return {
                        "latest_scan": {
                            "dislocation_scan_id": "scan_jesse",
                            "losers": [
                                {
                                    "ticker": "NVDA",
                                    "recommendation": "WATCH",
                                    "decline_analysis": {
                                        "classification": "POSSIBLE_TEMPORARY_DISLOCATION"
                                    },
                                }
                            ],
                        },
                        "live_execution": False,
                    }
                raise AssertionError(f"Unexpected backend path: {path}")

            with patch.object(preview, "_backend_get_json", side_effect=fake_get):
                snapshot = preview.build_living_factory_snapshot(
                    telemetry_dir=telemetry,
                    state_dir=state,
                )

            self.assertEqual(snapshot["schema_version"], preview.LIVING_SCHEMA_VERSION)
            self.assertEqual(snapshot["factory"]["availability"], "AVAILABLE")
            self.assertEqual(snapshot["jesse_dislocation"]["availability"], "AVAILABLE")
            self.assertEqual(
                snapshot["validation"]["layers"]["factory_telemetry"]["payload"]["radar"]["governed_universe_count"],
                518,
            )
            self.assertFalse(snapshot["safety"]["direct_ledger_access"])
            self.assertEqual(snapshot["safety"]["backend_access"], "READ_ONLY_GET_ONLY")
            self.assertFalse(snapshot["safety"]["backend_write_permission"])
            self.assertFalse(snapshot["safety"]["trade_execution_permission"])
            self.assertFalse(snapshot["safety"]["live_execution"])

    def test_backend_proxy_allow_list_rejects_arbitrary_paths_and_case_ids(self) -> None:
        self.assertEqual(
            preview._validate_backend_path("/intelligence/dislocation/status"),
            "/intelligence/dislocation/status",
        )
        self.assertEqual(
            preview._validate_backend_path("/experience/factory-intelligence/case/case_nvda-01"),
            "/experience/factory-intelligence/case/case_nvda-01",
        )
        with self.assertRaises(ValueError):
            preview._validate_backend_path("/committee/run")
        with self.assertRaises(ValueError):
            preview._validate_backend_path("/experience/factory-intelligence/case/../../etc/passwd")

    def test_backend_failure_is_explicit_waiting_not_synthetic_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(preview, "_backend_get_json", side_effect=RuntimeError("backend unavailable")):
                snapshot = preview.build_living_factory_snapshot(
                    telemetry_dir=root / "telemetry",
                    state_dir=root / "market-validation",
                )
            self.assertEqual(snapshot["factory"]["availability"], "WAITING")
            self.assertIsNone(snapshot["factory"]["payload"])
            self.assertEqual(snapshot["jesse_dislocation"]["availability"], "WAITING")
            self.assertIsNone(snapshot["jesse_dislocation"]["payload"])
            self.assertFalse(snapshot["safety"]["live_execution"])


if __name__ == "__main__":
    unittest.main()
