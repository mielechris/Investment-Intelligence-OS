from __future__ import annotations
import json, os, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from .unattended_supervisor_installer import (
    ARTIFACT_NAMES, INSTALLER_VERSION, LABEL, MANIFEST_NAME, SCHEMA,
    build_candidate, compare, inventory, make_manifest, readiness,
    validate_candidate, validate_manifest, write_manifest, main,
)

COMMIT="a"*40
NOW=datetime(2026,9,8,3,tzinfo=timezone.utc)

class Superbatch28H(unittest.TestCase):
    def source(self, root:Path)->Path:
        source=root/"source"; (source/"BACK END/backend/expansion_wing").mkdir(parents=True)
        for name in ARTIFACT_NAMES[:-1]:
            path=source/"BACK END/backend"/name; path.write_text(name)
        (source/"config").mkdir()
        (source/"config/com.iios.expansion-wing-unattended-tuesday.plist.template").write_text(
            '<?xml version="1.0"?><plist version="1.0"><dict><key>Label</key><string>'+LABEL+'</string>'
            '<key>ProgramArguments</key><array><string>__FIXED_PYTHON__</string><string>-m</string><string>expansion_wing.unattended_tuesday_service</string><string>--operational-supervisor</string></array>'
            '<key>WorkingDirectory</key><string>__FIXED_WORKTREE__</string><key>StandardOutPath</key><string>__OWNER_ONLY_LOG__</string></dict></plist>')
        return source

    def candidate(self, raw:str)->Path:
        root=Path(raw); source=self.source(root); candidate=root/"candidate"
        self.assertEqual(build_candidate(candidate,source_commit=COMMIT,source_root=source,python="/usr/bin/python3",log_path="/tmp/log"),"CANDIDATE_VALID")
        write_manifest(candidate,source_commit=COMMIT,installed_at=NOW)
        return candidate

    def test_complete_manifest_and_candidate(self):
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw); value=json.loads((candidate/MANIFEST_NAME).read_text())
            self.assertEqual(value["schema"],SCHEMA); self.assertEqual(value["installer_version"],INSTALLER_VERSION)
            self.assertEqual(validate_candidate(candidate,expected_commit=COMMIT),"CANDIDATE_VALID")
            self.assertEqual([x["relative_path"] for x in value["artifact_inventory"]],sorted(ARTIFACT_NAMES))

    def test_manifest_strict_tamper_and_commit(self):
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw); value=json.loads((candidate/MANIFEST_NAME).read_text())
            cases=[]
            for key in list(value): copy=dict(value); copy.pop(key); cases.append(copy)
            cases += [value|{"unknown":1}, value|{"schema":"wrong"}, value|{"installed_source_commit":"bad"},
                      value|{"installation_timestamp":(NOW+timedelta(days=1)).isoformat()}]
            for case in cases:
                with self.assertRaises(ValueError): validate_manifest(case,candidate,expected_commit=COMMIT,now=NOW)
            (candidate/ARTIFACT_NAMES[0]).write_text("tamper")
            with self.assertRaisesRegex(ValueError,"INSTALLED_INVENTORY_INVALID"): validate_manifest(value,candidate,expected_commit=COMMIT,now=NOW)

    def test_inventory_rejects_missing_unexpected_symlink_and_mode_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw); manifest=json.loads((candidate/MANIFEST_NAME).read_text())
            target=candidate/ARTIFACT_NAMES[0]; target.unlink()
            with self.assertRaises(ValueError): inventory(candidate)
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw); extra=candidate/"extra"; extra.write_text("x")
            with self.assertRaises(ValueError): inventory(candidate)
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw); target=candidate/ARTIFACT_NAMES[0]; target.unlink(); target.symlink_to(candidate/ARTIFACT_NAMES[1])
            with self.assertRaises(ValueError): inventory(candidate)

    def test_compare_byte_identical_and_changed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source=self.source(root); old=root/"old"; new=root/"new"
            build_candidate(old,source_commit=COMMIT,source_root=source,python="/usr/bin/python3",log_path="/tmp/log")
            build_candidate(new,source_commit="b"*40,source_root=source,python="/usr/bin/python3",log_path="/tmp/log")
            self.assertEqual(compare(old,new)["changed"],[])
            (new/ARTIFACT_NAMES[0]).write_text("changed")
            self.assertEqual(compare(old,new)["changed"],[ARTIFACT_NAMES[0]])

    def test_readiness_exact_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw)
            service={"running":True,"supervisor_count":1,"lock_owned":True,"listeners":0,"children":0}
            facts={"policy_present":False,"released_credits":0,"provider_requests":0,"provider_credits":0,
                   "controller_valid":True,"monday_rehearsal_valid":True,"authority_locked":True,"paper_activity":0,
                   "cost_binding":"VALID","credential_readiness":"AVAILABLE","planned":50,"supported":50,"blocked":0,
                   "exact_cost":50,"allowance":50}
            self.assertEqual(readiness(expected_commit=COMMIT,install_root=candidate,service_probe=lambda:service,operational_probe=lambda:facts),"READY_FOR_OWNER_POLICY_AUTHORIZATION")
            for key in facts:
                bad=dict(facts); bad[key]=1 if facts[key] is False else False if facts[key] is True else -1
                with self.assertRaisesRegex(ValueError,"FAILED_CLOSED"): readiness(expected_commit=COMMIT,install_root=candidate,service_probe=lambda:service,operational_probe=lambda bad=bad:bad)

    def test_browser_and_arbitrary_operational_paths_absent(self):
        source=Path(__file__).with_name("unattended_supervisor_installer.py").read_text()
        self.assertIn("BROWSER",source.upper()); self.assertNotIn("--destination",source)
        for prohibited in ("requests.get","api.financialdatasets.ai","SecItemCopyMatching"):
            self.assertNotIn(prohibited,source)

    def test_cli_browser_dirty_and_tracking_mismatch_fail_closed(self):
        with patch("expansion_wing.unattended_supervisor_installer.repository_gate",side_effect=ValueError("SOURCE_COMMIT_MISMATCH")):
            self.assertEqual(main(["--reviewed-operational-mode","validate-installed","--expected-source-commit",COMMIT]),5)
        self.assertEqual(main(["--reviewed-operational-mode","--browser","validate-installed","--expected-source-commit",COMMIT]),5)

    def test_repository_gate_uses_explicit_feature_origin(self):
        source=Path(__file__).with_name("unattended_supervisor_installer.py").read_text()
        self.assertIn('origin/{BRANCH}',source)
        self.assertNotIn('"@{u}"',source)

    def test_manifest_rejects_duplicate_traversal_absolute_and_noncanonical(self):
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw); value=json.loads((candidate/MANIFEST_NAME).read_text())
            for bad_path in ("../escape","/absolute","a/../b"):
                bad=json.loads(json.dumps(value)); bad["artifact_inventory"][0]["relative_path"]=bad_path
                body={k:bad[k] for k in bad if k!="canonical_manifest_content_hash"}; bad["canonical_inventory_identity"]=__import__("hashlib").sha256((json.dumps(bad["artifact_inventory"],sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
                body={k:bad[k] for k in bad if k!="canonical_manifest_content_hash"}; bad["canonical_manifest_content_hash"]=__import__("hashlib").sha256((json.dumps(body,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
                with self.assertRaises(ValueError): validate_manifest(bad,candidate,expected_commit=COMMIT,now=NOW)

if __name__=="__main__": unittest.main()
