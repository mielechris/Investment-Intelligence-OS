from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import iios_factory_telemetry_exporter_v2 as exporter


class FactoryTelemetryExporterV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = "mielechris/IIOS-Telemetry"
        self.issue = 1
        self.snapshot = {
            "fingerprint": "abc123",
            "schema_version": "batch9g-factory-telemetry-v2",
            "health": {"state": "HEALTHY"},
            "safety": {
                "telemetry_read_only": True,
                "live_execution": False,
            },
        }
        self.now = datetime(
            2026,
            8,
            28,
            18,
            0,
            tzinfo=timezone.utc,
        )

    def body(
        self,
        *,
        fingerprint: str,
        heartbeat_at: datetime,
    ) -> str:
        return (
            exporter.FINGERPRINT_MARKER.format(
                fingerprint=fingerprint
            )
            + "\n"
            + exporter._heartbeat_marker(heartbeat_at)
        )

    @patch.object(
        exporter.batch9f_exporter,
        "_require_private_repo",
    )
    @patch.object(
        exporter.batch9f_exporter,
        "_existing_issue_body",
    )
    @patch.object(
        exporter.batch9f_exporter,
        "_run_gh",
    )
    def test_same_state_with_fresh_heartbeat_is_unchanged(
        self,
        run_gh,
        existing_body,
        require_private,
    ) -> None:
        existing_body.return_value = self.body(
            fingerprint="abc123",
            heartbeat_at=self.now - timedelta(seconds=60),
        )
        result = exporter.publish_private_github_issue(
            self.snapshot,
            repo=self.repo,
            issue=self.issue,
            heartbeat_seconds=300,
            now=self.now,
        )
        self.assertEqual(result["status"], "UNCHANGED")
        require_private.assert_called_once_with(self.repo)
        run_gh.assert_not_called()

    @patch.object(
        exporter.batch9f_exporter,
        "_require_private_repo",
    )
    @patch.object(
        exporter.batch9f_exporter,
        "_existing_issue_body",
    )
    @patch.object(
        exporter.batch9f_exporter,
        "_run_gh",
    )
    def test_same_state_refreshes_stale_heartbeat(
        self,
        run_gh,
        existing_body,
        require_private,
    ) -> None:
        existing_body.return_value = self.body(
            fingerprint="abc123",
            heartbeat_at=self.now - timedelta(seconds=301),
        )
        result = exporter.publish_private_github_issue(
            self.snapshot,
            repo=self.repo,
            issue=self.issue,
            heartbeat_seconds=300,
            now=self.now,
        )
        self.assertEqual(
            result["status"],
            "HEARTBEAT_PUBLISHED",
        )
        require_private.assert_called_once_with(self.repo)
        run_gh.assert_called_once()
        payload = run_gh.call_args.args[-1]
        self.assertIn("iios-heartbeat:", payload)

    @patch.object(
        exporter.batch9f_exporter,
        "_require_private_repo",
    )
    @patch.object(
        exporter.batch9f_exporter,
        "_existing_issue_body",
    )
    @patch.object(
        exporter.batch9f_exporter,
        "_run_gh",
    )
    def test_meaningful_state_change_publishes_immediately(
        self,
        run_gh,
        existing_body,
        require_private,
    ) -> None:
        existing_body.return_value = self.body(
            fingerprint="old456",
            heartbeat_at=self.now - timedelta(seconds=10),
        )
        result = exporter.publish_private_github_issue(
            self.snapshot,
            repo=self.repo,
            issue=self.issue,
            heartbeat_seconds=300,
            now=self.now,
        )
        self.assertEqual(result["status"], "PUBLISHED")
        require_private.assert_called_once_with(self.repo)
        run_gh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
