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

from truth_spine_sqlite_capture import launch_capture, profile, sha, verify_snapshot


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
        for name in ('open_wronly','open_rdwr','create-wal','create-shm','modify-wal','modify-shm',
                     'truncate','rename','unlink','chmod','parent_create','outside_create',
                     'network_connect','credential_fixture','symlink_escape','traversal_escape'):
            self.assertTrue(proof[name]['denied'], name)
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
        with self.assertRaisesRegex(RuntimeError, 'CAPTURE_CHILD_FAILED_CLOSED'):
            launch_capture(self.source, root, evidence_root=self.evidence_dir, timeout=10)
        self.assertFalse((root/'receipt.json').exists())
        self.assertFalse((root/'snapshot.db').exists())
        self.assertEqual(before, {p.name:sha(p.read_bytes()) for p in self.source_dir.iterdir() if p.is_file()})
        self.assertIn(json.loads((root/'failure.json').read_bytes())['sqlite_code'],
                      (sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_READONLY_CANTINIT))

    def test_exact_write_root_profile(self):
        policy = profile(self.source, self.output_dir/'new', Path(sys.executable).resolve(),
                         Path(__file__).resolve(), Path(sys.base_prefix))
        self.assertEqual(policy.count('(allow file-write*'), 1)
        self.assertIn('(deny file-read-data (subpath "/Library/Keychains")', policy)
        self.assertIn('(deny mach-lookup)', policy)
        self.assertIn('(deny network*)', policy)

    def test_existing_output_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, 'NEW_SEPARATE_CAPTURE_OUTPUT_REQUIRED'):
            launch_capture(self.source, self.output_dir, evidence_root=self.evidence_dir)
        link = self.output_dir/'link'; link.symlink_to(self.source_dir)
        with self.assertRaises(ValueError): launch_capture(self.source, link/'new', evidence_root=self.evidence_dir)

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
