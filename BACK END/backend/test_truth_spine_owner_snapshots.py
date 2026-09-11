"""Offline tests for mutable v3 sources and immutable snapshot identity."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from truth_spine_contract import canonical, seal
from scripts import truth_spine_owner_snapshots as kit


class OwnerSnapshotContractTests(unittest.TestCase):
    def _config(self, root: Path, **changes):
        rows = []
        for kind, value in (("L7", b"L7"), ("L8", b"L8")):
            path = root / f"{kind.lower()}.db"; path.write_bytes(value); path.chmod(0o644); st = path.lstat()
            rows.append({"role": "L7_OPERATIONAL" if kind == "L7" else "L8_HISTORICAL", "path": str(path.resolve()),
                "device": st.st_dev, "inode": st.st_ino, "owner_uid": st.st_uid, "mode": 0o644,
                "file_type": "regular", "observed_utc": "2026-09-10T00:00:00Z",
                "provenance": ["accepted-audit", "machine-evidence"], "prior_observations": kit.HISTORICAL_OBSERVATIONS[kind], "mutable_source": True})
        record = {"schema": kit.CONFIG_SCHEMA, "created_utc": "2026-09-10T00:00:00Z",
            "owner_confirmation_hash": hashlib.sha256(kit.CONFIRMATION.encode()).hexdigest(),
            "source_commit": "a" * 40, "helper_sha256": kit.sha(Path(kit.capture_helper.__file__)),
            "owner_kit_sha256": kit.sha(Path(kit.__file__)), "sources": rows}
        record.update(changes); return seal(record)

    def test_mutable_size_and_mtime_advance_are_allowed(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"; cfg.write_bytes(canonical(self._config(root))); cfg.chmod(0o600)
            (root / "l8.db").write_bytes(b"advanced"); (root / "l8.db").touch()
            kit.validate_config_only(cfg, expected_commit="a" * 40, helper_sha256=kit.sha(Path(kit.capture_helper.__file__)), owner_kit_sha256=kit.sha(Path(kit.__file__)))

    def test_historical_hash_is_provenance_not_current_identity(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"; cfg.write_bytes(canonical(self._config(root))); cfg.chmod(0o600)
            record, _ = kit.load_config(cfg); self.assertEqual(record["sources"][0]["prior_observations"][0]["sha256"], kit.HISTORICAL_OBSERVATIONS["L7"][0]["sha256"])

    def test_device_inode_replacement_and_symlink_fail(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"; cfg.write_bytes(canonical(self._config(root))); cfg.chmod(0o600)
            (root / "l8.db").unlink(); (root / "l8.db.new").write_bytes(b"L8"); (root / "l8.db.new").chmod(0o644); (root / "l8.db").symlink_to(root / "l8.db.new")
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_PATH_INVALID"):
                kit.load_config(cfg, content=False)

    def test_prior_observation_cannot_be_labeled_current(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"; record = self._config(root)
            record["sources"][0]["current_sha256"] = record["sources"][0]["prior_observations"][0]["sha256"]
            cfg.write_bytes(canonical(seal({k: v for k, v in record.items() if k != "content_hash"}))); cfg.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_CONFIG_INVALID"):
                kit.load_config(cfg, content=False)

    def test_config_only_no_content_or_sqlite_and_bad_config_fails(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as raw:
            root = Path(raw); root.chmod(0o700); cfg = root / "sources.json"; cfg.write_bytes(canonical(self._config(root))); cfg.chmod(0o600)
            result = kit.validate_config_only(cfg, expected_commit="a" * 40, helper_sha256=kit.sha(Path(kit.capture_helper.__file__)), owner_kit_sha256=kit.sha(Path(kit.__file__)))
            self.assertFalse(result["ledger_content_opened"]); self.assertFalse(kit.OUTPUT_ROOT.exists())
            record = self._config(root); record["sources"][0]["role"] = "L8_HISTORICAL"; cfg.write_bytes(canonical(seal({k: v for k, v in record.items() if k != "content_hash"})))
            with self.assertRaisesRegex(ValueError, "OWNER_SOURCE_CONFIG_INVALID"):
                kit.load_config(cfg, content=False)

    def test_confirmation_remains_owner_only(self):
        self.assertIn("canonical iios l7 and l8", kit.CONFIRMATION.lower())
        with self.assertRaisesRegex(PermissionError, "OWNER_CONFIRMATION_REQUIRED"):
            kit.run(Path("/nonexistent"), Path("/nonexistent/config"), confirmation="no")


if __name__ == "__main__": unittest.main()
