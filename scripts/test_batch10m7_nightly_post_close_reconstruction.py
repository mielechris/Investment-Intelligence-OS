#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import activate_batch10m7_nightly_post_close_reconstruction as activation
import iios_nightly_post_close_reconstruction as nightly


class Batch10M7NightlyReconstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def event_report() -> dict:
        return {
            "status": "AVAILABLE",
            "surface": "Historical_Event_Reconstruction",
            "reconstructions": [{"symbol": symbol, "status": "AVAILABLE"} for symbol in ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META"]],
            "cycle": {"next_cursor": 0},
        }

    @staticmethod
    def macro_report() -> dict:
        return {
            "status": "AVAILABLE",
            "surface": "Historical_Macro_Regime_Library",
            "research_summary": {"normalized_symbols_ready": 8},
        }

    def test_before_post_close_does_not_run_engines(self) -> None:
        event = Mock()
        macro = Mock()
        payload = nightly.run_once(
            base_dir=self.base_dir,
            asof_et="2026-08-31T16:00:00-04:00",
            event_runner=event,
            macro_runner=macro,
        )
        self.assertEqual(payload["status"], "WAITING_FOR_POST_CLOSE")
        event.assert_not_called()
        macro.assert_not_called()
        self.assertFalse((self.base_dir / "nightly-reconstruction" / "nightly_reconstruction_state.json").exists())

    def test_weekend_does_not_run_engines(self) -> None:
        event = Mock()
        macro = Mock()
        payload = nightly.run_once(
            base_dir=self.base_dir,
            asof_et="2026-08-30T18:00:00-04:00",
            event_runner=event,
            macro_runner=macro,
        )
        self.assertEqual(payload["status"], "MARKET_CLOSED_WEEKEND")
        event.assert_not_called()
        macro.assert_not_called()

    def test_post_close_runs_10j_then_10k_and_persists_truth(self) -> None:
        calls: list[str] = []

        def event_runner(**kwargs):
            calls.append("10J")
            self.assertEqual(kwargs["symbols_per_cycle"], 8)
            self.assertEqual(kwargs["historical_dir"], self.base_dir / "historical-research")
            self.assertEqual(kwargs["event_dir"], self.base_dir / "historical-event-reconstruction")
            return self.event_report()

        def macro_runner(**kwargs):
            calls.append("10K")
            self.assertEqual(kwargs["historical_dir"], self.base_dir / "historical-research")
            self.assertEqual(kwargs["macro_dir"], self.base_dir / "historical-macro-regime")
            return self.macro_report()

        payload = nightly.run_once(
            base_dir=self.base_dir,
            asof_et="2026-08-31T16:20:00-04:00",
            event_runner=event_runner,
            macro_runner=macro_runner,
        )
        self.assertEqual(calls, ["10J", "10K"])
        self.assertEqual(payload["status"], "COMPLETE")
        self.assertEqual(payload["event_reconstruction"]["reconstruction_count"], 8)
        self.assertEqual(payload["macro_regime"]["status"], "AVAILABLE")
        self.assertFalse(payload["safety"]["live_execution"])
        self.assertFalse(payload["safety"]["trade_execution_permission"])
        self.assertTrue(payload["safety"]["live_capital_locked"])
        self.assertTrue(payload["safety"]["no_case_promotion_authority"])
        self.assertTrue((self.base_dir / "nightly-reconstruction" / "latest_nightly_reconstruction.json").exists())
        self.assertTrue((self.base_dir / "nightly-reconstruction" / "nightly_reconstruction_2026-08-31.json").exists())

    def test_same_market_date_is_idempotent(self) -> None:
        event = Mock(return_value=self.event_report())
        macro = Mock(return_value=self.macro_report())
        first = nightly.run_once(
            base_dir=self.base_dir,
            asof_et="2026-08-31T16:20:00-04:00",
            event_runner=event,
            macro_runner=macro,
        )
        second = nightly.run_once(
            base_dir=self.base_dir,
            asof_et="2026-08-31T20:00:00-04:00",
            event_runner=event,
            macro_runner=macro,
        )
        self.assertEqual(first["status"], "COMPLETE")
        self.assertEqual(second["status"], "ALREADY_RECONSTRUCTED")
        self.assertEqual(event.call_count, 1)
        self.assertEqual(macro.call_count, 1)

    def test_force_is_controlled_backfill_not_authority_change(self) -> None:
        payload = nightly.run_once(
            base_dir=self.base_dir,
            asof_et="2026-08-31T12:00:00-04:00",
            force=True,
            event_runner=Mock(return_value=self.event_report()),
            macro_runner=Mock(return_value=self.macro_report()),
        )
        self.assertEqual(payload["status"], "COMPLETE")
        self.assertTrue(payload["post_close_guard"]["force_override"])
        self.assertFalse(payload["safety"]["live_execution"])
        self.assertFalse(payload["safety"]["trade_execution_permission"])
        self.assertTrue(payload["safety"]["no_broker_authority"])

    def test_error_fails_closed_and_does_not_advance_market_date(self) -> None:
        payload = nightly.run_once(
            base_dir=self.base_dir,
            asof_et="2026-08-31T16:30:00-04:00",
            event_runner=Mock(side_effect=RuntimeError("fixture failure")),
            macro_runner=Mock(return_value=self.macro_report()),
        )
        self.assertEqual(payload["status"], "ERROR")
        self.assertTrue(payload["retryable"])
        self.assertFalse(payload["state_advance"])
        state = nightly._read_json(self.base_dir / "nightly-reconstruction" / "nightly_reconstruction_state.json")
        self.assertIsNone(state.get("last_completed_market_date_et"))
        self.assertFalse(payload["safety"]["live_execution"])

    def test_status_is_read_only(self) -> None:
        payload = nightly.status(base_dir=self.base_dir)
        self.assertEqual(payload["status"], "NOT_YET_RUN")
        self.assertFalse(payload["safety"]["live_execution"])
        self.assertFalse((self.base_dir / "nightly-reconstruction").exists())

    def test_terminal_bridge_contract_is_isolated(self) -> None:
        repo = Path("/Users/example/Documents/GitHub/Investment-Intelligence-OS")
        base = Path("/Users/example/Library/Application Support/IIOS")
        command = activation.build_command(repo_root=repo, base_dir=base)
        plist = activation.build_plist(command_path=Path("/Users/example/.iios/nightly-reconstruction/run.command"))

        self.assertIn("iios_nightly_post_close_reconstruction.py --run-once", command)
        self.assertEqual(plist["ProgramArguments"][:4], ["/usr/bin/open", "-g", "-a", "Terminal"])
        self.assertEqual(plist["StartInterval"], 900)
        self.assertFalse(plist["RunAtLoad"])
        self.assertNotIn("start_batch9a", command)
        self.assertNotIn("start_batch9b", command)
        self.assertNotIn("iios_high_speed_factory_runner", command)
        self.assertNotIn("Documents/GitHub", str(activation.RUNTIME_ROOT))

    def test_activation_status_preserves_factory_authority(self) -> None:
        with patch.object(activation, "_loaded", return_value=True):
            payload = activation.status(base_dir=self.base_dir)
        self.assertEqual(payload["status"], "LOADED")
        self.assertEqual(payload["transport"], "TERMINAL_BRIDGE")
        self.assertEqual(payload["preserved_stack"]["9A_observation"], "UNCHANGED")
        self.assertEqual(payload["preserved_stack"]["9B_paper_trading"], "UNCHANGED")
        self.assertEqual(payload["preserved_stack"]["9E_radar"], "UNCHANGED")
        self.assertEqual(payload["preserved_stack"]["backend_8002"], "UNCHANGED")
        self.assertFalse(payload["safety"]["live_execution"])
        self.assertFalse(payload["safety"]["trade_execution_permission"])


if __name__ == "__main__":
    unittest.main()
