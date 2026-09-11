"""Offline contract tests for the owner-operated snapshot kit."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from truth_spine_contract import seal
from scripts import truth_spine_owner_snapshots as kit


class OwnerSnapshotContractTests(unittest.TestCase):
    def test_pinned_two_source_config_is_accepted_without_opening_sources(self):
        with tempfile.TemporaryDirectory(prefix="owner-snapshot-config-", dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700)
            l7 = root / "l7.db"; l8 = root / "l8.db"
            l7.write_bytes(b"L7-DISPOSABLE"); l8.write_bytes(b"L8-DISPOSABLE")
            for path in (l7, l8): path.chmod(0o600)
            config = seal({"schema": kit.CONFIG_SCHEMA, "sources": [
                {"kind": "L7", "alias": "L7", "path": str(l7), "size": l7.stat().st_size, "sha256": kit.sha(l7)},
                {"kind": "L8", "alias": "L8", "path": str(l8), "size": l8.stat().st_size, "sha256": kit.sha(l8)},
            ]})
            cfg = root / "sources.json"; cfg.write_bytes(kit.canonical(config)); cfg.chmod(0o600)
            loaded, sources = kit.load_config(cfg)
            self.assertEqual(loaded, config)
            self.assertEqual(sources, {l7: "L7", l8: "L8"})

    def test_source_byte_change_and_duplicate_identity_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="owner-snapshot-config-", dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700)
            l7 = root / "l7.db"; l8 = root / "l8.db"
            l7.write_bytes(b"L7"); l8.write_bytes(b"L8")
            for path in (l7, l8): path.chmod(0o600)
            rows = [
                {"kind": "L7", "alias": "L7", "path": str(l7), "size": 2, "sha256": kit.sha(l7)},
                {"kind": "L8", "alias": "L8", "path": str(l8), "size": 2, "sha256": kit.sha(l8)},
            ]
            cfg = root / "sources.json"; cfg.write_bytes(kit.canonical(seal({"schema": kit.CONFIG_SCHEMA, "sources": rows}))); cfg.chmod(0o600)
            l8.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_IDENTITY_MISMATCH"):
                kit.load_config(cfg)

    def test_confirmation_is_exact_and_browser_cannot_invoke(self):
        self.assertIn("do not authorize source modification", kit.CONFIRMATION.lower())
        self.assertTrue(kit.OUTPUT_ROOT.is_absolute())
        with self.assertRaisesRegex(PermissionError, "OWNER_CONFIRMATION_REQUIRED"):
            kit.run(Path("/nonexistent"), Path("/nonexistent/config"), confirmation="yes")


if __name__ == "__main__":
    unittest.main()
