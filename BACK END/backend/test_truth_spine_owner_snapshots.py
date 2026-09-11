"""Offline contract tests for the v2 owner snapshot kit."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from truth_spine_contract import canonical, seal
from scripts import truth_spine_owner_snapshots as kit


class OwnerSnapshotContractTests(unittest.TestCase):
    def _config(self, root: Path, **changes):
        l7, l8 = root / "l7.db", root / "l8.db"
        for path, value in ((l7, b"L7-DISPOSABLE"), (l8, b"L8-DISPOSABLE")):
            path.write_bytes(value); path.chmod(0o600)
        rows = []
        for kind, path in (("L7", l7), ("L8", l8)):
            st = path.lstat()
            rows.append({"kind": kind, "alias": kind, "path": str(path.resolve()), "size": st.st_size,
                         "sha256": kit.sha(path), "device": st.st_dev, "inode": st.st_ino,
                         "owner_uid": st.st_uid, "mode": 0o600, "file_type": "regular",
                         "provenance": ["accepted-test-metadata"]})
        record = {"schema": kit.CONFIG_SCHEMA, "created_utc": "2026-09-10T00:00:00Z",
                  "owner_confirmation_hash": hashlib.sha256(kit.CONFIRMATION.encode()).hexdigest(),
                  "source_commit": "a" * 40, "helper_sha256": kit.sha(Path(kit.capture_helper.__file__)),
                  "owner_kit_sha256": kit.sha(Path(kit.__file__)), "sources": rows}
        record.update(changes)
        return seal(record)

    def test_v2_config_accepts_and_config_only_does_not_open_sources(self):
        with tempfile.TemporaryDirectory(prefix="owner-snapshot-config-", dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"
            cfg.write_bytes(canonical(self._config(root))); cfg.chmod(0o600)
            loaded, sources = kit.load_config(cfg)
            self.assertEqual(loaded["schema"], kit.CONFIG_SCHEMA)
            self.assertEqual(set(sources.values()), {"L7", "L8"})
            result = kit.validate_config_only(cfg, expected_commit="a" * 40,
                helper_sha256=kit.sha(Path(kit.capture_helper.__file__)), owner_kit_sha256=kit.sha(Path(kit.__file__)))
            self.assertFalse(result["ledger_content_opened"])

    def test_config_only_is_metadata_only_even_when_content_changes(self):
        with tempfile.TemporaryDirectory(prefix="owner-snapshot-config-", dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"
            cfg.write_bytes(canonical(self._config(root))); cfg.chmod(0o600)
            (root / "l8.db").write_bytes(b"changed")
            kit.validate_config_only(cfg, expected_commit="a" * 40,
                                     helper_sha256=kit.sha(Path(kit.capture_helper.__file__)), owner_kit_sha256=kit.sha(Path(kit.__file__)))
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_IDENTITY_MISMATCH"):
                kit.load_config(cfg)

    def test_placeholders_unknown_fields_and_bad_confirmation_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="owner-snapshot-config-", dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"
            record = self._config(root); record["sources"][0]["path"] = "<owner-supplied-path>"
            cfg.write_bytes(canonical(seal({k: v for k, v in record.items() if k != "content_hash"}))); cfg.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_PATH_INVALID"):
                kit.validate_config_only(cfg, expected_commit="a" * 40, helper_sha256=kit.sha(Path(kit.capture_helper.__file__)), owner_kit_sha256=kit.sha(Path(kit.__file__)))
            record = self._config(root); record["unexpected"] = True
            cfg.write_bytes(canonical(seal({k: v for k, v in record.items() if k != "content_hash"})))
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_CONFIG_INVALID"):
                kit.load_config(cfg)

    def test_identical_sources_rejected(self):
        with tempfile.TemporaryDirectory(prefix="owner-snapshot-config-", dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"
            record = self._config(root); record["sources"][1] = dict(record["sources"][0], kind="L8", alias="L8")
            cfg.write_bytes(canonical(seal({k: v for k, v in record.items() if k != "content_hash"}))); cfg.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_IDENTITY_DUPLICATE"):
                kit.load_config(cfg)

    def test_confirmation_and_browser_invocation_fail_closed(self):
        self.assertIn("canonical iios l7 and l8", kit.CONFIRMATION.lower())
        with self.assertRaisesRegex(PermissionError, "OWNER_CONFIRMATION_REQUIRED"):
            kit.run(Path("/nonexistent"), Path("/nonexistent/config"), confirmation="yes")


if __name__ == "__main__":
    unittest.main()
