"""Actual macOS kernel boundary tests on disposable databases, never live inputs."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

from truth_spine_sqlite_capture import (coordination_profile_attestation,
                                        launch_capture, profile, sha, verify_snapshot)


@unittest.skipUnless(sys.platform == 'darwin', 'Seatbelt requires macOS; not an isolation acceptance elsewhere')
class SeatbeltCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sqlite-capture-')
        self.root = Path(self.temp.name).resolve()
        self.source_dir = self.root/'source'; self.source_dir.mkdir(mode=0o700)
        self.output_dir = self.root/'outputs'; self.output_dir.mkdir(mode=0o700)
        self.evidence_dir = self.root/'incidents'; self.evidence_dir.mkdir(mode=0o700)
        self.source = self.source_dir/'fixture.db'
        self.writer = sqlite3.connect(self.source)
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.writer.execute('CREATE TABLE example(id INTEGER PRIMARY KEY)')
        self.writer.execute('INSERT INTO example VALUES(1)'); self.writer.commit()
        (self.source_dir/'credential-fixture.dat').write_bytes(b'SYNTHETIC_NO_CREDENTIAL')

    def tearDown(self):
        self.writer.close()
        # TemporaryDirectory owns these disposable fixtures only.
        self.temp.cleanup()

    def test_negative_capabilities(self):
        before = {p.name:sha(p.read_bytes()) for p in self.source_dir.iterdir() if p.is_file()}
        result = launch_capture(self.source, self.output_dir/'negative', evidence_root=self.evidence_dir, timeout=15, probe=True)
        proof = result['negative_capabilities']
        self.assertEqual(result['status'], 'VERIFIED')
        for name in ('open_wronly','open_rdwr','rollback_journal','truncate','rename','unlink','chmod','parent_create','outside_create',
                     'network_connect','credential_fixture','symlink_escape','traversal_escape'):
            self.assertTrue(proof[name]['denied'], name)
        self.assertTrue(proof['coordinate-wal']['allowed'])
        self.assertTrue(proof['coordinate-shm']['allowed'])
        self.assertTrue(proof['child_inherits_denials'])
        self.assertTrue(proof['read_database'])
        self.assertTrue(proof['read-wal'])
        self.assertTrue(proof['read-shm'])
        self.assertTrue(proof['destination_write'])
        self.assertEqual(before, {p.name:sha(p.read_bytes()) for p in self.source_dir.iterdir() if p.is_file()})

    def test_existing_wal_snapshot_survives_later_source_advancement(self):
        root = self.output_dir/'capture'
        result = launch_capture(self.source, root, evidence_root=self.evidence_dir, timeout=15)
        self.writer.execute('INSERT INTO example VALUES(2)'); self.writer.commit()
        self.writer.execute('PRAGMA wal_checkpoint(PASSIVE)')
        verify_snapshot(root/'snapshot.db', result)
        with sqlite3.connect((root/'snapshot.db').as_uri()+'?mode=ro&immutable=1', uri=True) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM example').fetchone(), (1,))
        self.assertEqual(self.writer.execute('SELECT count(*) FROM example').fetchone(), (2,))
        self.assertEqual((root/'snapshot.db').stat().st_mode & 0o777, 0o400)

    def test_no_companions_fails_closed_without_source_creation(self):
        self.writer.close()
        before = {p.name:sha(p.read_bytes()) for p in self.source_dir.iterdir() if p.is_file()}
        root = self.output_dir/'no-companions'
        # The production profile permits exact companions, but a genuinely
        # unwritable source directory must still fail closed before BEGIN.
        self.source_dir.chmod(0o500)
        try:
            with self.assertRaisesRegex(RuntimeError, 'CAPTURE_CHILD_FAILED_CLOSED'):
                launch_capture(self.source, root, evidence_root=self.evidence_dir, timeout=10)
            self.assertFalse((root/'receipt.json').exists())
            self.assertFalse((root/'snapshot.db').exists())
            self.assertEqual(before, {p.name:sha(p.read_bytes()) for p in self.source_dir.iterdir() if p.is_file()})
            self.assertIn(json.loads((root/'failure.json').read_bytes())['sqlite_code'],
                          (sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_READONLY_CANTINIT,
                           sqlite3.SQLITE_READONLY_DIRECTORY))
        finally:
            self.source_dir.chmod(0o700)

    def test_exact_write_root_profile(self):
        policy = profile(self.source, self.output_dir/'new', Path(sys.executable).resolve(),
                         Path(__file__).resolve(), Path(sys.base_prefix))
        attestation = coordination_profile_attestation(self.source, self.output_dir/'new', policy)
        self.assertEqual(attestation['method'], 'PROFILE_EXACT_LITERALS_AND_SQLITE_SEQUENCE')
        self.assertEqual(attestation['allowed_suffixes'], ['-wal', '-shm'])
        self.assertFalse(attestation['main_database_writes'])
        self.assertFalse(attestation['source_parent_writes'])
        self.assertEqual(policy.count('(allow file-write*'), 1)
        self.assertIn(str(self.source)+'-wal', policy)
        self.assertIn(str(self.source)+'-shm', policy)
        self.assertNotIn(str(self.source)+'-journal', policy)
        self.assertIn('(deny file-read-data (subpath "/Library/Keychains")', policy)
        self.assertIn('(deny mach-lookup)', policy)
        self.assertIn('(deny network*)', policy)

    def test_nonexistent_companions_are_attested_from_profile_not_sandbox_query(self):
        """Absent WAL/SHM paths are admitted only by exact profile semantics."""
        for suffix in ('-wal', '-shm'):
            companion = Path(str(self.source) + suffix)
            if companion.exists(): companion.unlink()
        output = self.output_dir/'attestation'
        policy = profile(self.source, output, Path(sys.executable).resolve(),
                         Path(__file__).resolve(), Path(sys.base_prefix))
        result = coordination_profile_attestation(self.source, output, policy)
        self.assertEqual(result['allowed_suffixes'], ['-wal', '-shm'])
        self.assertFalse((Path(str(self.source) + '-wal')).exists())
        self.assertFalse((Path(str(self.source) + '-shm')).exists())
        with self.assertRaisesRegex(PermissionError, 'OS_CAPTURE_COORDINATION_PROFILE_INVALID'):
            coordination_profile_attestation(self.source, output, policy.replace('(literal '+json.dumps(str(Path(str(self.source)+'-shm')))+')', '(literal "/tmp/unrelated-shm")'))

    def test_existing_output_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, 'NEW_SEPARATE_CAPTURE_OUTPUT_REQUIRED'):
            launch_capture(self.source, self.output_dir, evidence_root=self.evidence_dir)
        link = self.output_dir/'link'; link.symlink_to(self.source_dir)
        with self.assertRaises(ValueError): launch_capture(self.source, link/'new', evidence_root=self.evidence_dir)

    def test_runtime_metadata_is_sanitized_and_source_independent(self):
        from truth_spine_sqlite_capture import sqlite_runtime_metadata
        metadata = sqlite_runtime_metadata()
        self.assertTrue(metadata['python'])
        self.assertTrue(metadata['sqlite_runtime_version'])
        self.assertIsInstance(metadata['compile_options'], list)
        self.assertNotIn(str(self.source), repr(metadata))

    def test_missing_companions_are_created_only_for_sqlite_and_publish(self):
        self.writer.close()
        for suffix in ('-wal', '-shm'):
            companion = Path(str(self.source) + suffix)
            if companion.exists(): companion.unlink()
        root = self.output_dir/'missing-companions'
        result = launch_capture(self.source, root, evidence_root=self.evidence_dir, timeout=10)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertTrue((root/'snapshot.db').exists())
        self.assertEqual(result['coordination']['before']['-wal']['exists'], False)
        self.assertEqual(result['coordination']['before']['-shm']['exists'], False)

    def test_companion_metadata_is_metadata_only_and_exactly_scoped(self):
        from truth_spine_sqlite_capture import companion_metadata
        observed = companion_metadata(self.source)
        self.assertEqual(set(observed), {'-wal', '-shm'})
        for value in observed.values():
            if value['exists']:
                self.assertEqual(value['owner_uid'], os.getuid())
                self.assertTrue(value['mode'] & 0o400)
        self.assertFalse((self.source.parent / (self.source.name + '-journal')).exists())

    def test_companions_disappear_after_transaction_is_established(self):
        """A post-BEGIN WAL/SHM disappearance is a real disposable-process case."""
        for index in range(200000):
            self.writer.execute('INSERT INTO example VALUES(?)', (index + 2,))
        self.writer.commit()
        target = self.output_dir/'companions-disappear'
        done = threading.Event()

        def remove_after_snapshot_staging(_pid, output):
            def worker():
                deadline = time.monotonic() + 8
                marker = output/'snapshot.incomplete.db'
                while time.monotonic() < deadline and not marker.exists():
                    time.sleep(0.005)
                if not marker.exists():
                    return
                for suffix in ('-wal', '-shm'):
                    companion = Path(str(self.source) + suffix)
                    if companion.exists(): companion.unlink()
                done.set()
            threading.Thread(target=worker, daemon=True).start()

        result = launch_capture(self.source, target, evidence_root=self.evidence_dir,
                                timeout=15, on_child_started=remove_after_snapshot_staging)
        self.assertTrue(done.wait(2))
        self.assertEqual(result['status'], 'VERIFIED')
        verify_snapshot(target/'snapshot.db', result)

    def test_actual_capture_process_interruption_has_no_success_publication(self):
        """Killing the admitted disposable child leaves only sanitized incident evidence."""
        for index in range(200000):
            self.writer.execute('INSERT INTO example VALUES(?)', (index + 2,))
        self.writer.commit()
        target = self.output_dir/'interrupted'
        killed = threading.Event()

        def kill_during_capture(pid, output):
            def worker():
                marker = output/'snapshot.incomplete.db'
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and not marker.exists():
                    time.sleep(0.005)
                if marker.exists():
                    os.kill(pid, 9)
                    killed.set()
            threading.Thread(target=worker, daemon=True).start()

        with self.assertRaisesRegex(RuntimeError, 'CAPTURE_CHILD_FAILED_CLOSED'):
            launch_capture(self.source, target, evidence_root=self.evidence_dir,
                           timeout=15, on_child_started=kill_during_capture)
        self.assertTrue(killed.wait(2))
        self.assertFalse((target/'receipt.json').exists())
        self.assertFalse((target/'snapshot.db').exists())
        incident = list(self.evidence_dir.glob('capture-*'))
        self.assertTrue(incident)
        self.assertTrue((incident[-1]/'incident.json').exists())


if __name__ == '__main__': unittest.main()
