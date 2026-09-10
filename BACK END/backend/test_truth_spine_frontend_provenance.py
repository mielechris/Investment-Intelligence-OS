"""Offline provenance rejection tests; no shadow root or runtime is created."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
import os
import uuid
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys

SCRIPTS = Path(__file__).resolve().parents[2]/'scripts'
spec = importlib.util.spec_from_file_location('truth_spine_frontend_provenance', SCRIPTS/'truth_spine_frontend_provenance.py')
p = importlib.util.module_from_spec(spec); sys.modules[spec.name] = p; spec.loader.exec_module(p)
spec = importlib.util.spec_from_file_location('provenance_acceptance', SCRIPTS/'truth_spine_integration_acceptance.py')
acceptance = importlib.util.module_from_spec(spec); spec.loader.exec_module(acceptance)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='iios-provenance-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.dist = self.root/'frontend/dist'; self.dist.mkdir(parents=True)
        self.assets = {'assets/truth-integration-abc.js': 'console.log("HISTORICAL")',
                       'assets/truth-integration-def.css': 'main{display:block}',
                       'truth-integration.html': '<script src="/review/assets/truth-integration-abc.js"></script><link href="/review/assets/truth-integration-def.css">',
                       'favicon.svg': '<svg/>', 'icons.svg': '<svg/>', 'fixtures/expansion-wing.json': '{}'}
        for name, data in self.assets.items():
            target = self.dist/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(data)
        self.expected = {'source_commit': 'a'*40, 'source_root': str(self.root/'source'),
                         'source_inventory': [], 'source_inventory_hash': p.digest([]),
                         'package_json_hash': 'package', 'lockfile_hash': 'lock',
                         'policy': copy.deepcopy(p.POLICY),
                         'toolchain': {'node': {'sha256': 'node'}, 'versions': {'vite': '8.2.2'}}}
        rows = p.validate_outputs(self.dist)
        self.record = {'schema': p.SCHEMA, 'inputs': copy.deepcopy(self.expected), 'input_hash': p.digest(self.expected),
                       'outputs': rows, 'output_hash': p.digest(rows), 'observation': {'modules': []}}
        self.save()
        self.inputs = patch.object(p, 'inputs', return_value=self.expected).start()
        self.addCleanup(patch.stopall)

    def save(self):
        self.record.pop('content_hash', None)
        self.record['content_hash'] = p.digest(self.record)
        (self.root/'frontend-provenance.json').write_bytes(p.encoded(self.record))

    def verify(self):
        return p.verify(self.root, self.root/'source', 'a'*40)

    def change_input(self, key, value):
        self.record['inputs'][key] = value
        self.record['input_hash'] = p.digest(self.record['inputs'])
        self.save()
        with self.assertRaisesRegex(ValueError, 'BUILD_INPUT_BINDING_MISMATCH'):
            self.verify()

    def test_valid_offline_verification_without_subprocess_or_network(self):
        with patch.object(p.subprocess, 'run', side_effect=AssertionError('unexpected execution')):
            self.assertEqual(self.verify()['output_hash'], self.record['output_hash'])

    def test_wrong_commit(self): self.change_input('source_commit', 'b'*40)
    def test_modified_source(self): self.change_input('source_inventory_hash', 'changed')
    def test_wrong_lockfile(self): self.change_input('lockfile_hash', 'changed')
    def test_wrong_package(self): self.change_input('package_json_hash', 'changed')
    def test_recomputed_children_wrong_source_root(self): self.change_input('source_root', str(self.root/'different-source'))

    def test_wrong_node_identity(self):
        value = copy.deepcopy(self.expected['toolchain']); value['node']['sha256'] = 'wrong'
        self.change_input('toolchain', value)

    def test_wrong_vite_identity(self):
        value = copy.deepcopy(self.expected['toolchain']); value['versions']['vite'] = '8.2.3'
        self.change_input('toolchain', value)

    def test_missing_flag(self):
        value = copy.deepcopy(p.POLICY); value['environment'].pop('VITE_TRUTH_INTEGRATION_PREVIEW')
        self.change_input('policy', value)

    def test_changed_flag(self):
        value = copy.deepcopy(p.POLICY); value['environment']['VITE_TRUTH_INTEGRATION_PREVIEW'] = '0'
        self.change_input('policy', value)

    def test_stale_unmanifested_dist(self):
        (self.root/'frontend-provenance.json').unlink()
        with self.assertRaisesRegex(ValueError, 'FRONTEND_PROVENANCE_REQUIRED'): self.verify()

    def test_extra_asset(self):
        (self.dist/'assets/old.js').write_text('old')
        with self.assertRaises(ValueError): self.verify()

    def test_extra_asset_even_resealed(self):
        (self.dist/'assets/old.js').write_text('old')
        self.record['outputs'] = p.inventory(self.dist); self.record['output_hash'] = p.digest(self.record['outputs']); self.save()
        with self.assertRaisesRegex(ValueError, 'SIX_FILE_ALLOWLIST_INVALID'): self.verify()

    def test_missing_asset(self):
        (self.dist/'icons.svg').unlink()
        with self.assertRaises(ValueError): self.verify()

    def test_mutated_javascript(self):
        (self.dist/'assets/truth-integration-abc.js').write_text('mutated')
        with self.assertRaises(ValueError): self.verify()

    def test_mutated_css(self):
        (self.dist/'assets/truth-integration-def.css').write_text('mutated')
        with self.assertRaises(ValueError): self.verify()

    def reseal_outputs(self):
        self.record['outputs'] = p.inventory(self.dist)
        self.record['output_hash'] = p.digest(self.record['outputs']); self.save()

    def test_unmanifested_html_reference(self):
        (self.dist/'truth-integration.html').write_text('<script src="/review/assets/old.js"></script>')
        self.reseal_outputs()
        with self.assertRaisesRegex(ValueError, 'HTML_ASSET_GRAPH_INVALID'): self.verify()

    def test_source_map_asset_rejected(self):
        (self.dist/'assets/private.map').write_text('{}'); self.reseal_outputs()
        with self.assertRaises(ValueError): self.verify()

    def test_source_map_comment_rejected(self):
        (self.dist/'assets/truth-integration-abc.js').write_text('//# sourceMappingURL=private.map')
        self.reseal_outputs()
        with self.assertRaisesRegex(ValueError, 'FRONTEND_PATH_OR_MAP_LEAKAGE'): self.verify()

    def test_absolute_developer_path(self):
        # Use the documented temporary prefix, never a real personal path.
        (self.dist/'assets/truth-integration-abc.js').write_text('"/private/tmp/build/source.tsx"')
        self.reseal_outputs()
        with self.assertRaisesRegex(ValueError, 'FRONTEND_PATH_OR_MAP_LEAKAGE'): self.verify()

    def test_symlink_rejected(self):
        path = self.dist/'icons.svg'; path.unlink(); path.symlink_to(self.dist/'favicon.svg')
        with self.assertRaises(ValueError): self.verify()

    def test_corrupt_manifest(self):
        self.record['output_hash'] = 'bad'
        (self.root/'frontend-provenance.json').write_bytes(p.encoded(self.record))
        with self.assertRaises(ValueError): self.verify()

    def test_nondeterministic_repeated_output_rejected(self):
        other = copy.deepcopy(self.record); other['outputs'][0]['sha256'] = 'different'
        with self.assertRaisesRegex(ValueError, 'NONDETERMINISTIC_BUILD'): p.compare_builds(self.record, other)

    def test_different_build_input_rejected(self):
        other = copy.deepcopy(self.record); other['inputs']['source_commit'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'BUILD_INPUTS_DIFFER'): p.compare_builds(self.record, other)

    def test_identical_repeated_output_accepted(self):
        self.assertEqual(p.compare_builds(self.record, copy.deepcopy(self.record)), self.record['output_hash'])

    def test_preparation_fails_before_root_or_socket_no_old_dist_fallback(self):
        proposed = self.root/'must-not-exist'
        args = SimpleNamespace(root=proposed, source=self.root/'source', frontend_build=self.root,
                               frontend_input_hash=self.record['input_hash'], port=5290)
        (self.dist/'assets/truth-integration-abc.js').write_text('stale')
        with patch.object(acceptance.subprocess, 'check_output', side_effect=['a'*40, '']), \
             patch.object(acceptance.socket, 'socket', side_effect=AssertionError('socket before validation')) as socket:
            with self.assertRaises(ValueError): acceptance.prepare(args)
            socket.assert_not_called()
        self.assertFalse(proposed.exists())

    def test_source_modified_detected_before_build_root_creation(self):
        # The actual production source check reads Git's HEAD/diff, not a
        # provenance document's claims. No fake readiness/authority is involved.
        with patch.object(p, 'git', side_effect=['a'*40, 'FRONT END/package.json\0', 'diff']):
            with self.assertRaisesRegex(ValueError, 'FRONTEND_SOURCE_MODIFIED'):
                p.source_inputs(self.root, 'a'*40)

    def test_source_wrong_commit_detected(self):
        with patch.object(p, 'git', return_value='b'*40):
            with self.assertRaisesRegex(ValueError, 'SOURCE_COMMIT_MISMATCH'):
                p.source_inputs(self.root, 'a'*40)

    def test_recomputed_asset_hashes_cannot_bypass_independent_manifest_pin(self):
        expected_manifest_hash = p.sha(self.root/'frontend-provenance.json')
        (self.dist/'assets/truth-integration-abc.js').write_text('different application')
        self.reseal_outputs()
        args = SimpleNamespace(root=self.root/'not-created', source=self.root/'source', frontend_build=self.root,
                               frontend_input_hash=self.record['input_hash'], frontend_manifest_hash=expected_manifest_hash, port=5290)
        with patch.object(acceptance.subprocess, 'check_output', side_effect=['a'*40, '']), \
             patch.object(acceptance.socket, 'socket', side_effect=AssertionError('must not bind')):
            with self.assertRaisesRegex(ValueError, 'FRONTEND_MANIFEST_PIN_MISMATCH'): acceptance.prepare(args)
        self.assertFalse(args.root.exists())

    def package(self):
        from truth_spine_contract import digest
        backend = [{'path': 'backend/example.py', 'bytes': 1, 'sha256': 'x'}]
        return {'source_state': 'CLEAN_COMMITTED_SOURCE', 'source_base': 'a'*40,
                'source_inventory_hash': digest({'files': backend}), 'frontend_provenance': self.record,
                'frontend_input_hash': self.record['input_hash'], 'frontend_content_hash': self.record['output_hash'],
                'files': backend+[{**r, 'path': 'frontend/'+r['path']} for r in self.record['outputs']]}

    def test_installed_manifest_reconciles_without_source_checkout(self):
        from truth_spine_integration import validate_frontend_provenance
        validate_frontend_provenance(self.package())

    def test_installed_manifest_missing_provenance_rejected(self):
        from truth_spine_integration import validate_frontend_provenance
        value = self.package(); value.pop('frontend_provenance')
        with self.assertRaises(ValueError): validate_frontend_provenance(value)

    def test_installed_manifest_wrong_commit_rejected(self):
        from truth_spine_integration import validate_frontend_provenance
        value = self.package(); value['source_base'] = 'b'*40
        with self.assertRaises(ValueError): validate_frontend_provenance(value)

    def test_installed_asset_mismatch_rejected(self):
        from truth_spine_integration import validate_frontend_provenance
        value = self.package(); value['files'][1]['sha256'] = 'changed'
        with self.assertRaises(ValueError): validate_frontend_provenance(value)


class IndependentBuildTests(unittest.TestCase):
    def test_two_clean_builds_and_readonly_verification(self):
        source = Path(__file__).resolve().parents[2]
        commit = p.git(source, 'rev-parse', 'HEAD').strip()
        roots = [Path('/private/tmp')/('iios-frontend-build-unit-'+uuid.uuid4().hex) for _ in range(2)]
        retained = source/'FRONT END/dist'
        before = p.inventory(retained) if retained.exists() else None
        try:
            with patch.dict(os.environ, {'TZ':'Pacific/Honolulu', 'LANG':'en_US.UTF-8'}):
                first = p.build(source, roots[0], commit)
            with patch.dict(os.environ, {'TZ':'Asia/Tokyo', 'LANG':'C'}):
                second = p.build(source, roots[1], commit)
            self.assertEqual(p.compare_builds(first, second), first['output_hash'])
            for root in roots:
                self.assertFalse(any(p.environment_cache(x.relative_to(root/'frontend/node_modules'))
                                     for x in (root/'frontend/node_modules').rglob('*')))
                prior = p.inventory(root)
                self.assertEqual(p.verify(root, source, commit)['input_hash'], first['input_hash'])
                self.assertEqual(prior, p.inventory(root))
            self.assertEqual(p.inventory(retained) if retained.exists() else None, before)
        finally:
            for root in roots:
                if root.is_dir(): shutil.rmtree(root)


if __name__ == '__main__': unittest.main()
