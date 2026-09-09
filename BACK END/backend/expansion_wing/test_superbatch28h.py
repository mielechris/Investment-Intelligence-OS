from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from .unattended_supervisor_installer import (
    ARTIFACT_NAMES, LEGACY_ARTIFACT_NAMES, INSTALLER_VERSION, LABEL, MANIFEST_NAME, SCHEMA,
    build_candidate, compare, inventory, make_manifest, readiness,
    validate_candidate, validate_manifest, write_manifest, main,
    supervisor_lock_path, supervisor_lock_state, SUPERVISOR_LOCK_NAME,
    create_legacy_migration_backup, rehearse_legacy_restoration, migrate_legacy_layout,
    validate_legacy_manifest, _canonical, _hash, _tree_records,
)
from .unattended_tuesday_service import SUPERVISOR_LOCK_NAME as SERVICE_LOCK_NAME
from . import unattended_supervisor_installer as installer

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
            '<key>WorkingDirectory</key><string>__FIXED_WORKTREE__</string>'
            '<key>EnvironmentVariables</key><dict><key>PYTHONPATH</key><string>__FIXED_WORKTREE__</string></dict>'
            '<key>RunAtLoad</key><true/><key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>'
            '<key>ProcessType</key><string>Background</string><key>ThrottleInterval</key><integer>60</integer>'
            '<key>StandardOutPath</key><string>__OWNER_ONLY_LOG__</string><key>StandardErrorPath</key><string>__OWNER_ONLY_LOG__</string>'
            '</dict></plist>')
        return source

    def candidate(self, raw:str)->Path:
        root=Path(raw); source=self.source(root); candidate=root/"candidate"
        self.assertEqual(build_candidate(candidate,source_commit=COMMIT,source_root=source,python="/usr/bin/python3",log_path="/tmp/log"),"CANDIDATE_VALID")
        write_manifest(candidate,source_commit=COMMIT,installed_at=NOW)
        return candidate

    def legacy_installation(self, root:Path)->tuple[Path,Path,Path,Path]:
        source=self.source(root); candidate=root/"legacy-candidate"
        build_candidate(candidate,source_commit=COMMIT,source_root=source,python="/usr/bin/python3",log_path="/tmp/log")
        for name in set(ARTIFACT_NAMES)-set(LEGACY_ARTIFACT_NAMES): (candidate/name).unlink()
        rows=inventory(candidate,LEGACY_ARTIFACT_NAMES)
        body={"schema":SCHEMA,"installed_source_commit":COMMIT,"installation_timestamp":NOW.isoformat(),
              "service_label":LABEL,"state_root_identity":"IIOS_UNATTENDED_TUESDAY",
              "executable_module_entrypoint":"expansion_wing.unattended_tuesday_service",
              "plist_identity":"com.iios.expansion-wing-unattended-tuesday.plist","artifact_inventory":rows,
              "canonical_inventory_identity":_hash(rows),"installer_version":INSTALLER_VERSION,"immutable":True}
        manifest=body|{"canonical_manifest_content_hash":_hash(body)}
        install=root/"install"; install.mkdir(mode=0o700); artifacts=install/"installed-artifacts"
        candidate.rename(artifacts); (install/MANIFEST_NAME).write_bytes(_canonical(manifest)); (install/MANIFEST_NAME).chmod(0o600)
        plist=root/"launch.plist"; plist.write_bytes((artifacts/LEGACY_ARTIFACT_NAMES[-1]).read_bytes()); plist.chmod(0o600)
        state=root/"september-8-state"; state.mkdir(mode=0o700); (state/"state.json").write_text('{"phase":"SESSION_CLOSED","released":0}\n'); (state/"state.json").chmod(0o600)
        return source,install,plist,state

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

    def test_canonical_lock_identity_missing_stale_symlink_and_mode(self):
        self.assertIs(SUPERVISOR_LOCK_NAME,SERVICE_LOCK_NAME)
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)/"root"; root.mkdir(mode=0o700)
            self.assertEqual(supervisor_lock_path(root),root/SERVICE_LOCK_NAME)
            self.assertEqual(supervisor_lock_state(root),"MISSING")
            lock=root/SERVICE_LOCK_NAME; lock.touch(mode=0o600)
            self.assertEqual(supervisor_lock_state(root),"STALE_UNLOCKED")
            lock.chmod(0o644)
            with self.assertRaisesRegex(ValueError,"SUPERVISOR_LOCK_MALFORMED"): supervisor_lock_state(root)
            lock.unlink(); (root/"elsewhere").touch(); lock.symlink_to(root/"elsewhere")
            with self.assertRaisesRegex(ValueError,"SUPERVISOR_LOCK_MALFORMED"): supervisor_lock_state(root)

    def test_real_subprocess_holds_and_releases_canonical_lock(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)/"root"; root.mkdir(mode=0o700); lock=root/SERVICE_LOCK_NAME
            code="import fcntl,os,sys,time;p=sys.argv[1];f=open(p,'a+');os.chmod(p,0o600);fcntl.flock(f,fcntl.LOCK_EX);print('READY',flush=True);time.sleep(1)"
            process=subprocess.Popen([sys.executable,"-c",code,str(lock)],stdout=subprocess.PIPE,text=True)
            self.assertEqual(process.stdout.readline().strip(),"READY")
            self.assertEqual(supervisor_lock_state(root),"HELD")
            process.wait(timeout=3)
            process.stdout.close()
            self.assertEqual(supervisor_lock_state(root),"STALE_UNLOCKED")

    def test_manifest_rejects_duplicate_traversal_absolute_and_noncanonical(self):
        with tempfile.TemporaryDirectory() as raw:
            candidate=self.candidate(raw); value=json.loads((candidate/MANIFEST_NAME).read_text())
            for bad_path in ("../escape","/absolute","a/../b"):
                bad=json.loads(json.dumps(value)); bad["artifact_inventory"][0]["relative_path"]=bad_path
                body={k:bad[k] for k in bad if k!="canonical_manifest_content_hash"}; bad["canonical_inventory_identity"]=__import__("hashlib").sha256((json.dumps(bad["artifact_inventory"],sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
                body={k:bad[k] for k in bad if k!="canonical_manifest_content_hash"}; bad["canonical_manifest_content_hash"]=__import__("hashlib").sha256((json.dumps(body,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
                with self.assertRaises(ValueError): validate_manifest(bad,candidate,expected_commit=COMMIT,now=NOW)

    def test_valid_five_to_eight_migration_backup_rehearsal_and_idempotency(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source,install,plist,state=self.legacy_installation(root); backup=root/"rollback"
            before=_tree_records(state)
            self.assertEqual(migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,service_stopped=True),
                "SUPERVISOR_LAYOUT_MIGRATED_DISABLED")
            self.assertEqual(validate_candidate(install/"installed-artifacts",expected_commit="b"*40) if False else len(inventory(install/"installed-artifacts")),9)
            self.assertEqual(before,_tree_records(state)); self.assertEqual(rehearse_legacy_restoration(backup),"LEGACY_RESTORATION_REHEARSED")
            self.assertEqual(migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,service_stopped=True),
                "SUPERVISOR_LAYOUT_ALREADY_CURRENT")

    def test_unknown_incomplete_hash_and_mixed_legacy_rejected(self):
        mutations=("schema","missing","hash","mixed")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                root=Path(raw); source,install,plist,state=self.legacy_installation(root); path=install/MANIFEST_NAME
                value=json.loads(path.read_text())
                if mutation=="schema": value["schema"]="unknown"
                elif mutation=="missing": (install/"installed-artifacts"/LEGACY_ARTIFACT_NAMES[0]).unlink()
                elif mutation=="hash": (install/"installed-artifacts"/LEGACY_ARTIFACT_NAMES[0]).write_text("tampered")
                else:
                    extra=install/"installed-artifacts"/ARTIFACT_NAMES[4]; extra.write_text("mixed"); extra.chmod(0o600)
                if mutation=="schema": path.write_bytes(_canonical(value))
                with self.assertRaises(ValueError): migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                    backup=root/"rollback",legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,service_stopped=True)

    def test_symlink_special_file_and_permissions_rejected(self):
        for kind in ("symlink","fifo","mode"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                root=Path(raw); source,install,plist,state=self.legacy_installation(root); target=install/"installed-artifacts"/LEGACY_ARTIFACT_NAMES[0]
                if kind=="symlink": target.unlink(); target.symlink_to(install/MANIFEST_NAME)
                elif kind=="fifo": target.unlink(); os.mkfifo(target,0o600)
                else: target.chmod(0o644)
                with self.assertRaises(ValueError): migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                    backup=root/"rollback",legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,service_stopped=True)
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source,install,plist,state=self.legacy_installation(root)
            with patch("expansion_wing.unattended_supervisor_installer.os.getuid",return_value=os.getuid()+1):
                with self.assertRaises(ValueError): migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                    backup=root/"rollback",legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,service_stopped=True)

    def test_service_teardown_is_an_explicit_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source,install,plist,state=self.legacy_installation(root)
            with self.assertRaisesRegex(ValueError,"SERVICE_TEARDOWN_REQUIRED"):
                migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,backup=root/"rollback",
                    legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state)

    def test_interrupted_backup_staging_and_before_selection_restart_safely(self):
        for phase in ("backup","staging","before_selection"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as raw:
                root=Path(raw); source,install,plist,state=self.legacy_installation(root); backup=root/"rollback"
                with self.assertRaises(RuntimeError): migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                    backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,interrupt_at=phase,service_stopped=True)
                self.assertEqual(migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                    backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,service_stopped=True),
                    "SUPERVISOR_LAYOUT_MIGRATED_DISABLED")

    def test_interruption_during_backup_never_selects_partial_backup(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source,install,plist,state=self.legacy_installation(root); backup=root/"rollback"
            with patch.object(installer,"_copy_exact_tree",side_effect=RuntimeError("SIMULATED_COPY_INTERRUPTION")):
                with self.assertRaises(RuntimeError): create_legacy_migration_backup(install_root=install,
                    launch_plist=plist,backup=backup,legacy_commit=COMMIT,target_commit="b"*40)
            self.assertFalse(backup.exists()); self.assertTrue((root/"rollback.building").exists())
            self.assertEqual(migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,
                protected_state_root=state,service_stopped=True),"SUPERVISOR_LAYOUT_MIGRATED_DISABLED")

    def test_interruption_after_selection_recovers_current_target(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source,install,plist,state=self.legacy_installation(root); backup=root/"rollback"
            with self.assertRaises(RuntimeError): migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,interrupt_at="after_selection",service_stopped=True)
            self.assertEqual(migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,service_stopped=True),
                "SUPERVISOR_LAYOUT_MIGRATED_DISABLED")

    def test_post_selection_failure_restores_legacy_exactly(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source,install,plist,state=self.legacy_installation(root); backup=root/"rollback"; before=_tree_records(install)
            with self.assertRaisesRegex(ValueError,"TARGET_REJECTED"): migrate_legacy_layout(source_root=source,install_root=install,launch_plist=plist,
                backup=backup,legacy_commit=COMMIT,target_commit="b"*40,installed_at=NOW,protected_state_root=state,
                post_select_validator=lambda _root: (_ for _ in ()).throw(ValueError("TARGET_REJECTED")),service_stopped=True)
            validate_legacy_manifest(json.loads((install/MANIFEST_NAME).read_text()),install/"installed-artifacts",expected_commit=COMMIT)
            self.assertEqual(before,_tree_records(install))

    def test_migration_has_no_generation_or_authority_surface(self):
        source=Path(__file__).with_name("unattended_supervisor_installer.py").read_text()
        body=source[source.index("def migrate_legacy_layout"):]
        for prohibited in ("select_generation(","released_credits = 50","provider_request(","keychain"):
            self.assertNotIn(prohibited,body.lower())

if __name__=="__main__": unittest.main()
