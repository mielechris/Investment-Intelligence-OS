from __future__ import annotations

import hashlib
import json
import os
import plistlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment_contract import (ACTIVE_RELEASE_SCHEMA, LEDGER_MIGRATION_SCHEMA, canonical, digest,
    file_hash, inspect_ledger, migrate_ledger_mode, restore_ledger_mode, render_service_plists,
    validate_active_release, validate_runtime_manifest, validate_service_plists)

COMMIT = "a" * 40


class DeploymentContractTest(unittest.TestCase):
    def ledger(self, root: Path) -> Path:
        path = root / "ledger.db"
        connection = sqlite3.connect(path); connection.execute("CREATE TABLE probe (id INTEGER)"); connection.commit(); connection.close()
        path.chmod(0o644)
        return path

    def test_ledger_requires_explicit_migration_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); ledger = self.ledger(root); before = ledger.read_bytes(); expected = file_hash(ledger)
            with self.assertRaisesRegex(RuntimeError, "LEDGER_IDENTITY_INVALID"):
                inspect_ledger(ledger, expected_path=ledger, expected_uid=os.getuid(), expected_gid=ledger.stat().st_gid,
                               expected_mode=0o600, expected_sha256=expected)
            receipt = migrate_ledger_mode(path=ledger, expected_path=ledger, expected_uid=os.getuid(),
                                          expected_gid=ledger.stat().st_gid, expected_sha256=expected)
            self.assertEqual((receipt["schema"], ledger.stat().st_mode & 0o777, ledger.read_bytes()),
                             (LEDGER_MIGRATION_SCHEMA, 0o600, before))
            self.assertEqual(restore_ledger_mode(path=ledger, receipt=receipt), "LEDGER_MODE_ROLLED_BACK")
            self.assertEqual((ledger.stat().st_mode & 0o777, ledger.read_bytes()), (0o644, before))

    def test_ledger_rejects_wrong_path_hash_mode_symlink_sidecar_and_content_change(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); ledger = self.ledger(root); expected = file_hash(ledger); gid = ledger.stat().st_gid
            cases = [dict(expected_path=root/"other"), dict(expected_sha256="0"*64), dict(expected_mode=0o600)]
            base = dict(expected_path=ledger, expected_uid=os.getuid(), expected_gid=gid,
                        expected_mode=0o644, expected_sha256=expected)
            for change in cases:
                with self.assertRaises(RuntimeError): inspect_ledger(ledger, **(base | change))
            link = root/"link.db"; link.symlink_to(ledger)
            with self.assertRaises(RuntimeError): inspect_ledger(link, **(base | {"expected_path":link}))
            (root/"ledger.db-wal").write_bytes(b"x")
            with self.assertRaises(RuntimeError): inspect_ledger(ledger, **base)

    def runtime(self, root: Path) -> tuple[Path, dict]:
        runtime = root/"runtime"; (runtime/"bin").mkdir(parents=True); (runtime/"lib").mkdir()
        interpreter = runtime/"bin/python3.14"; interpreter.write_bytes(b"python"); interpreter.chmod(0o500)
        dependency = runtime/"lib/example-1.dist-info/METADATA"; dependency.parent.mkdir(); dependency.write_bytes(b"Name: example\nVersion: 1\n"); dependency.chmod(0o400)
        dependency.parent.chmod(0o500); (runtime/"bin").chmod(0o500); (runtime/"lib").chmod(0o500); runtime.chmod(0o500)
        rows = [{"path":"bin/python3.14","size":len(b"python"),"mode":0o500,"sha256":file_hash(interpreter)},
                {"path":"lib/example-1.dist-info/METADATA","size":len(b"Name: example\nVersion: 1\n"),"mode":0o400,"sha256":file_hash(dependency)}]
        body = {"schema":"iios-immutable-python-runtime-v1","runtime_id":"runtime-test","release_commit":COMMIT,
                "runtime_root":str(runtime),"interpreter":str(interpreter),"interpreter_sha256":file_hash(interpreter),
                "python_version":"3.14.7","dependency_inventory":[{"name":"example","version":"1","metadata_path":"lib/example-1.dist-info/METADATA","metadata_sha256":file_hash(dependency)}],"file_inventory":rows,
                "platform_dependencies":[]}
        return runtime, body|{"content_hash":digest(body)}

    def test_runtime_contract_rejects_writable_missing_symlink_version_and_release_mismatch(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); runtime, manifest=self.runtime(root)
            with patch("deployment_contract.subprocess.run") as run:
                run.return_value.stdout="Python 3.14.7\n"
                self.assertEqual(validate_runtime_manifest(runtime,manifest,expected_release_commit=COMMIT),manifest)
                with self.assertRaises(RuntimeError): validate_runtime_manifest(runtime,manifest,expected_release_commit="b"*40)
                (runtime/"lib/example-1.dist-info/METADATA").chmod(0o600)
                with self.assertRaisesRegex(RuntimeError,"RUNTIME_WRITABLE"):
                    validate_runtime_manifest(runtime,manifest,expected_release_commit=COMMIT)

    def test_service_plists_reject_checkout_bound_and_mixed_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); release=root/"release"; runtime=root/"runtime"; backend=release/"source/BACK END/backend"
            backend.mkdir(parents=True); (runtime/"bin").mkdir(parents=True); python=runtime/"bin/python3.14"; python.touch()
            ledger=root/"ledger.db"; ledger.touch(); plists=[]
            for label in ("com.iios.backend8002","com.iios.v7living-truth-sidecar","com.iios.expansion-wing-projection-publisher","com.iios.expansion-wing-unattended-tuesday"):
                path=root/(label+".plist"); path.write_bytes(plistlib.dumps({"Label":label,"ProgramArguments":[str(python),"-m"],
                    "WorkingDirectory":str(backend),"EnvironmentVariables":{"PYTHONPATH":str(backend),"IIOS_DB_PATH":str(ledger)}})); plists.append(path)
            self.assertEqual(len(validate_service_plists(plists,release_root=release,runtime_root=runtime,ledger_path=ledger,interpreter=python)),4)
            bad=plistlib.loads(plists[0].read_bytes()); bad["ProgramArguments"][0]="/tmp/GitHub/checkout/.venv/bin/python"
            plists[0].write_bytes(plistlib.dumps(bad))
            with self.assertRaisesRegex(RuntimeError,"SERVICE_DEPLOYMENT_INVALID"):
                validate_service_plists(plists,release_root=release,runtime_root=runtime,ledger_path=ledger,interpreter=python)

    def test_all_four_reviewed_templates_render_only_runtime_and_release_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); release=Path("/opt/iios/releases/test"); runtime=Path("/opt/iios/runtimes/test")
            hashes=render_service_plists(source_root=Path(__file__).parents[2],destination=base/"deployment",
                release_root=release,runtime_root=runtime,ledger_path=Path("/var/lib/iios/ledger.db"),log_root=Path("/var/log/iios"))
            self.assertEqual(len(hashes),4)
            combined=b"".join(path.read_bytes() for path in (base/"deployment").iterdir())
            self.assertNotIn(b"/GitHub/",combined); self.assertNotIn(b".venv",combined)

    def test_active_release_binds_runtime_release_ledger_and_migration(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); release=root/"release"; runtime=root/"runtime"; release.mkdir(); runtime.mkdir()
            (release/"release-manifest.json").write_bytes(b"release\n"); (runtime/"runtime-manifest.json").write_bytes(b"{}\n")
            ledger=root/"ledger.db"; ledger.touch()
            binding={"release_id":"release","git_commit":COMMIT,"release_root":str(release),"runtime_id":"runtime","runtime_root":str(runtime),"operational_ledger_path":str(ledger)}
            body={"schema":ACTIVE_RELEASE_SCHEMA,**binding,"release_manifest_sha256":file_hash(release/"release-manifest.json"),
                  "runtime_manifest_sha256":file_hash(runtime/"runtime-manifest.json"),
                  "ledger_path_contract_hash":hashlib.sha256(canonical(binding)).hexdigest(),"ledger_migration_contract_hash":"b"*64}
            path=root/"active.json"; path.write_bytes(canonical(body|{"content_hash":digest(body)})); path.chmod(0o600)
            with patch("deployment_contract.validate_runtime_manifest",return_value={}):
                self.assertEqual(validate_active_release(path,configured_ledger=str(ledger))["runtime_id"],"runtime")
            value=json.loads(path.read_bytes()); value["runtime_root"]=str(root/"GitHub/escape")
            path.write_bytes(canonical(value));
            with self.assertRaises(RuntimeError): validate_active_release(path,configured_ledger=str(ledger))


if __name__ == "__main__":
    unittest.main()
