"""Separate process-boundary gate; never launches a fixture, worker or network.

Run directly with Python -I -S -B. The mocked offline gate continues to deny
all subprocesses. Every exporter child starts with no project import path.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO/'tests/native'), str(REPO/'BACK END/backend')]
import alpha_radar_ci as ci
from alpha_radar_runner import lifecycle_envelope


class FreshExportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='iios-provider-connection-source-tests-export-', dir='/private/tmp'))
        self.runtime = self.root/'runtime'; self.source = self.runtime/'source'
        self.source.mkdir(parents=True); (self.root/'export').mkdir(); (self.root/'execution-output').mkdir()
        rows = []
        for name in ci.SOURCE_NAMES:
            relative = ('tests/native/' if name.startswith('alpha_radar') else 'BACK END/backend/')+name
            data = (REPO/relative).read_bytes(); path = self.source/name
            path.write_bytes(data); path.chmod(0o400)
            rows.append({'path': 'source/'+name, 'size': len(data), 'sha256': ci.digest(data), 'mode': 0o400})
        self.source.chmod(0o500); self.runtime.chmod(0o500)
        r = {'root': str(self.runtime), 'source_commit': 'a'*40, 'files': rows,
             'source_files': sorted(row['path'] for row in rows)}
        d = {'runtime': r, 'expected': {'runtime': ci.digest(ci.canonical(r))}, 'package': {},
             'authorized_root': str(self.root), 'native_tools': {}, 'maximum_duration_seconds': 120}
        self.write('descriptor.json', d)
        self.write('export/prepared-pins.json', {'descriptor_sha256': ci.digest(ci.canonical(d)),
            'runtime': r, 'parents': d['expected'], 'source_commit': 'a'*40})
        ld = {**d, 'schema': 'iios-ci-native-lifecycle-v1'}
        self.parents = {**d['expected'], 'lifecycle_descriptor': ci.digest(ci.canonical(ld))}
        self.write('lifecycle-descriptor.json', ld)
        self.write('export/lifecycle-pins.json', {'descriptor': ld,
            'descriptor_sha256': ci.digest(ci.canonical(ld)), 'parents': self.parents,
            'preparation_descriptor_parent': ci.digest(ci.canonical(d))})
        self.receipt = lifecycle_envelope({'classification': 'LIFECYCLE_PASS'}, self.parents)
        self.write('execution-output/lc-final.json', self.receipt)

    def write(self, name, value):
        (self.root/name).write_bytes(ci.canonical(value))

    def run_export(self, success):
        before = (self.root/'execution-output/lc-final.json').read_bytes()
        result = subprocess.run([sys.executable, '-I', '-S', '-B', str(REPO/'tests/native/alpha_radar_ci.py'),
            'export', '--root', str(self.root)], cwd=self.root, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout.decode())
        self.assertEqual((self.root/'execution-output/lc-final.json').read_bytes(), before)
        self.assertEqual((self.root/'export/EVIDENCE-INVENTORY.json').exists(), success)
        if not success:
            self.assertTrue((self.root/'export/export-failure.json').exists())

    def test_fresh_isolated_export(self):
        self.run_export(True)
        self.assertEqual(json.loads((self.root/'export/lc-final.json').read_bytes()), self.receipt)
        rows = json.loads((self.root/'export/EVIDENCE-INVENTORY.json').read_bytes())
        for row in rows:
            data = (self.root/'export'/row['path']).read_bytes()
            self.assertEqual(row['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(row['size'], len(data))

    def test_missing_source_rejected(self):
        self.source.chmod(0o700); (self.source/'alpha_market_baseline.py').unlink(); self.source.chmod(0o500)
        self.run_export(False)

    def test_altered_source_rejected(self):
        path = self.source/'alpha_market_baseline.py'; path.chmod(0o600)
        path.write_bytes(b'raise RuntimeError("must never import")\n'); path.chmod(0o400)
        self.run_export(False)

    def test_source_alias_rejected(self):
        self.source.chmod(0o700); path = self.source/'alpha_market_baseline.py'; path.unlink()
        path.symlink_to(REPO/'BACK END/backend/alpha_market_baseline.py'); self.source.chmod(0o500)
        self.run_export(False)

    def test_forged_receipt_rejected(self):
        self.receipt['value']['classification'] = 'FORGED'
        self.write('execution-output/lc-final.json', self.receipt); self.run_export(False)

    def test_cross_parent_receipt_rejected(self):
        self.write('execution-output/lc-final.json', lifecycle_envelope({}, {'lifecycle_descriptor': 'b'*64}))
        self.run_export(False)

    def test_authority_escalation_rejected(self):
        self.receipt['live_execution'] = True
        self.write('execution-output/lc-final.json', self.receipt); self.run_export(False)

    def test_pin_rebinding_rejected(self):
        pins = json.loads((self.root/'export/lifecycle-pins.json').read_bytes())
        pins['parents']['lifecycle_descriptor'] = 'b'*64
        self.write('export/lifecycle-pins.json', pins); self.run_export(False)

    def test_publication_collision_preserves_existing_evidence(self):
        target = self.root/'export/lc-final.json'; target.write_bytes(b'PREEXISTING')
        self.run_export(False); self.assertEqual(target.read_bytes(), b'PREEXISTING')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    if args.root is not None:
        ci.root_check(args.root)
    bindings = ci.source_bindings()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FreshExportTests)
    count = suite.countTestCases()
    result = unittest.TextTestRunner().run(suite)
    ci.verify_bindings(bindings)
    success = result.wasSuccessful() and result.testsRun == count and not result.skipped
    if args.root is not None:
        ci.document(args.root/'export/fresh-export-results.json', {
            'scope': 'FRESH_PROCESS_EXPORT_ONLY', 'collected': count, 'executed': result.testsRun,
            'success': success, 'skipped': len(result.skipped), 'source_bindings': bindings,
            'fixture_launches': 0, 'worker_launches': 0, 'requests': 0})
    sys.exit(0 if success else 1)
