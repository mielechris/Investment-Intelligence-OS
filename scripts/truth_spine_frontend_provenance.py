"""Offline, source-bound frontend builds. Never trusts an unproven dist tree.

Only new temporary build roots are written. No package installation, network,
credential discovery, or permanent runtime operation is implemented here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'BACK END/backend'))
from truth_spine_frontend_graph import NORTHSTAR_ENV, ENTRY, validate_northstar_graph

SCHEMA = 'iios-truth-frontend-build-v1'
ENV = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'NODE_ENV': 'production',
       'VITE_TRUTH_INTEGRATION_PREVIEW': '1', 'TZ': 'UTC', 'LANG': 'C', 'LC_ALL': 'C'}
POLICY = {'mode': 'production', 'config_loader': 'runner', 'sourcemap': False,
          'entry': 'truth-integration.html', 'base': '/review/', 'environment': ENV,
          'dependency_cache_exclusions': ['.tmp', '.vite', '.vite-temp', '.cache', '__pycache__', '*.tsbuildinfo']}
NODE = Path('/usr/local/bin/node')
NPM = Path('/usr/local/bin/npm')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, category):
    if not condition:
        raise ValueError(category)


def environment_cache(path):
    return bool(set(Path(path).parts) & {'.tmp', '.vite', '.vite-temp', '.cache', '__pycache__'}) or str(path).endswith('.tsbuildinfo')


def inventory(root, *, dependency=False):
    root = Path(root).resolve()
    rows = []
    for p in sorted(root.rglob('*')):
        if dependency and environment_cache(p.relative_to(root)):
            continue
        if p.is_symlink():
            require(dependency and p.parent.name == '.bin' and p.resolve().is_relative_to(root), 'SYMLINK_REJECTED')
        if p.is_dir():
            continue
        info = p.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), 'FILE_OWNER_OR_TYPE_INVALID')
        rows.append({'path': p.relative_to(root).as_posix(), 'bytes': info.st_size, 'sha256': sha(p)})
    return rows


def git(source, *args):
    return subprocess.check_output(['git', *args], cwd=source, text=True, timeout=30)


def source_inputs(source, commit, *, review=False):
    source = Path(source).resolve()
    require(git(source, 'rev-parse', 'HEAD').strip() == commit, 'SOURCE_COMMIT_MISMATCH')
    names = sorted(filter(None, git(source, 'ls-files', '-z', 'FRONT END').split('\0')))
    require(names and (review or not git(source, 'diff', 'HEAD', '--', 'FRONT END')), 'FRONTEND_SOURCE_MODIFIED')
    extra = git(source, 'ls-files', '--others', '--exclude-standard', '-z', '--', 'FRONT END')
    require(review or not extra, 'FRONTEND_SOURCE_EXTRA')
    if review: names = sorted(set(names) | set(filter(None, extra.split('\0'))))
    rows = []
    for name in names:
        p = source/name
        require(not p.is_symlink() and p.is_file(), 'FRONTEND_SOURCE_TYPE_INVALID')
        require(not any(x in p.parts for x in ('dist', 'node_modules', '__pycache__')), 'TRACKED_BUILD_ARTIFACT')
        rows.append({'path': str(Path(name).relative_to('FRONT END')), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    frontend = source/'FRONT END'
    require(not list(frontend.glob('.env*')), 'ENV_FILE_NOT_PERMITTED')
    return rows


def toolchain(frontend):
    deps = inventory(frontend/'node_modules', dependency=True)
    lock = json.loads((frontend/'package-lock.json').read_bytes())['packages']
    packages = []
    for row in deps:
        if row['path'].endswith('/package.json'):
            rel = row['path'].removesuffix('/package.json')
            key = 'node_modules/'+rel
            if key not in lock:
                continue  # Data/example package.json is still byte-bound above.
            value = json.loads((frontend/'node_modules'/row['path']).read_bytes())
            require(value.get('version') == lock[key].get('version'), 'DEPENDENCY_LOCK_MISMATCH')
            packages.append({'path': key, 'name': value.get('name'), 'version': value.get('version'),
                             'package_hash': row['sha256'], 'lock_integrity': lock[key].get('integrity')})
    versions = {name: json.loads((frontend/'node_modules'/name/'package.json').read_bytes())['version']
                for name in ('vite', 'rolldown', '@vitejs/plugin-react', 'typescript', 'react', 'react-dom')}
    require(versions['vite'] == '8.2.2', 'VITE_VERSION_MISMATCH')
    node_version = subprocess.check_output([str(NODE), '--version'], env=ENV, text=True, timeout=10).strip()
    # Read npm's installed identity directly: no npm config, user .npmrc,
    # registry lookup, update notifier or credential-bearing configuration.
    npm_package = NPM.resolve().parents[1]/'package.json'
    npm_version = json.loads(npm_package.read_bytes())['version']
    require(node_version == 'v24.19.0', 'NODE_VERSION_MISMATCH')
    require(npm_version == '11.17.0', 'NPM_VERSION_MISMATCH')
    return {'node': {'version': node_version, 'sha256': sha(NODE), 'path': str(NODE.resolve())},
            'npm': {'version': npm_version, 'sha256': sha(NPM.resolve()), 'package_hash': sha(npm_package)},
            'versions': versions, 'dependency_inventory': deps,
            'dependency_inventory_hash': digest(deps), 'packages': packages}


def inputs(source, commit, *, northstar=False, review=False):
    source = Path(source).resolve()
    rows = source_inputs(source, commit, review=review)
    return {'source_commit': commit, 'source_root': str(source), 'source_inventory': rows,
            'source_inventory_hash': digest(rows), 'package_json_hash': sha(source/'FRONT END/package.json'),
            'lockfile_hash': sha(source/'FRONT END/package-lock.json'),
            'vite_config_hash': sha(source/'FRONT END/vite.config.ts'),
            'tsconfig_hashes': {r['path']: r['sha256'] for r in rows if r['path'].startswith('tsconfig')},
            'policy': ({**POLICY, 'entry': ENTRY, 'environment': NORTHSTAR_ENV} if northstar else POLICY), 'toolchain': toolchain(source/'FRONT END'),
            'builder_hashes': {name: sha(Path(__file__).parent/name) for name in
                               ('truth_spine_frontend_provenance.py', 'truth_spine_frontend_build.mjs',
                                '../BACK END/backend/truth_spine_frontend_graph.py')}}


def validate_outputs(dist, expected=None, *, northstar=False):
    dist = Path(dist)
    require(dist.is_dir() and not dist.is_symlink(), 'FRONTEND_DIST_INVALID')
    rows = inventory(dist)
    if expected is not None:
        require(rows == expected, 'FRONTEND_OUTPUT_MISMATCH')
    if northstar:
        validate_northstar_graph({r['path']: (dist/r['path']).read_bytes() for r in rows})
        return rows
    paths = {r['path'] for r in rows}
    fixed = {'truth-integration.html', 'favicon.svg', 'icons.svg', 'fixtures/expansion-wing.json'}
    js = {p for p in paths if re.fullmatch(r'assets/truth-integration-[A-Za-z0-9_-]+\.js', p)}
    css = {p for p in paths if re.fullmatch(r'assets/truth-integration-[A-Za-z0-9_-]+\.css', p)}
    require(len(rows) == 6 and len(js) == len(css) == 1 and paths == fixed | js | css, 'SIX_FILE_ALLOWLIST_INVALID')
    html = (dist/'truth-integration.html').read_text()
    refs = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', html)
    require(set(refs) == {'/review/'+p for p in js | css}, 'HTML_ASSET_GRAPH_INVALID')
    for name in js | css | {'truth-integration.html'}:
        text = (dist/name).read_text()
        require(not re.search(r'/Users/|/home/|/private/tmp/|[A-Z]:\\|sourceMappingURL|sourceURL', text), 'FRONTEND_PATH_OR_MAP_LEAKAGE')
    return rows


def compare_builds(first, second):
    require(first['inputs'] == second['inputs'], 'BUILD_INPUTS_DIFFER')
    require(first['outputs'] == second['outputs'] and first['observation'] == second['observation'], 'NONDETERMINISTIC_BUILD')
    return first['output_hash']


def verify(build_root, source, commit):
    root = Path(build_root).resolve()
    path = root/'frontend-provenance.json'
    require(path.is_file() and not path.is_symlink(), 'FRONTEND_PROVENANCE_REQUIRED')
    record = json.loads(path.read_bytes())
    require(set(record) == {'schema', 'inputs', 'input_hash', 'outputs', 'output_hash', 'observation', 'content_hash'}, 'PROVENANCE_SCHEMA_INVALID')
    require(record['schema'] == SCHEMA, 'PROVENANCE_SCHEMA_INVALID')
    require(record['content_hash'] == digest({k:v for k,v in record.items() if k != 'content_hash'}), 'PROVENANCE_HASH_INVALID')
    northstar = record['inputs']['policy']['entry'] == ENTRY
    expected = inputs(source, commit, northstar=True) if northstar else inputs(source, commit)
    require(record['inputs'] == expected and record['input_hash'] == digest(expected), 'BUILD_INPUT_BINDING_MISMATCH')
    validate_outputs(root/'frontend/dist', record['outputs'], northstar=northstar)
    require(record['output_hash'] == digest(record['outputs']), 'OUTPUT_HASH_INVALID')
    return record


def build(source, destination, commit, *, northstar=False, review=False):
    source, root = Path(source).resolve(), Path(destination).absolute()
    checkout_test = (root.is_relative_to(source/'tests/northstar/artifacts')
                     and root.name.startswith('iios-frontend-build-unit-'))
    temporary = root.parent == Path('/private/tmp') and (root.name.startswith('iios-frontend-build-')
                 or root.name in {'iios-northstar-sb37-build-a', 'iios-northstar-sb37-build-b'})
    require((temporary or checkout_test) and not any(p.is_symlink() for p in (root, *root.parents))
            and not root.exists() and not root.is_symlink(), 'NEW_ISOLATED_BUILD_ROOT_REQUIRED')
    before = inputs(source, commit, northstar=northstar, review=review)
    if checkout_test: root.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    root.mkdir(mode=0o700)
    front = root/'frontend'; front.mkdir(mode=0o700)
    for row in before['source_inventory']:
        target = front/row['path']; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/'FRONT END'/row['path'], target)
    shutil.copytree(source/'FRONT END/node_modules', front/'node_modules', symlinks=False,
                    ignore=lambda directory, names: [name for name in names if environment_cache(name)])
    require(inventory(front/'node_modules', dependency=True) == before['toolchain']['dependency_inventory'], 'COPIED_DEPENDENCY_MISMATCH')
    require(not any(environment_cache(p.relative_to(front/'node_modules')) for p in (front/'node_modules').rglob('*')), 'COPIED_CACHE_REJECTED')
    driver = root/'build.mjs'; shutil.copyfile(Path(__file__).with_name('truth_spine_frontend_build.mjs'), driver)
    env = {**(NORTHSTAR_ENV if northstar else ENV), 'TMPDIR': str(root)}
    subprocess.run([str(NODE), str(driver)], cwd=front, env=env, timeout=180, check=True, capture_output=True)
    require(inputs(source, commit, northstar=northstar, review=review) == before, 'BUILD_INPUT_CHANGED')
    require(inventory(front/'node_modules', dependency=True) == before['toolchain']['dependency_inventory'], 'BUILD_MUTATED_DEPENDENCIES')
    require(not (source/'FRONT END').is_symlink(), 'SOURCE_ROOT_INVALID')
    outputs = validate_outputs(front/'dist', northstar=northstar)
    observation = json.loads((front/'build-observation.json').read_bytes())
    record = {'schema': 'iios-source-review-build-NOT-INSTALLABLE' if review else SCHEMA, 'inputs': before, 'input_hash': digest(before),
              'outputs': outputs, 'output_hash': digest(outputs), 'observation': observation}
    record['content_hash'] = digest(record)
    with (root/'frontend-provenance.json').open('xb') as stream:
        os.fchmod(stream.fileno(), 0o400); stream.write(encoded(record)); stream.flush(); os.fsync(stream.fileno())
    for p in (front/'dist').rglob('*'):
        if p.is_file(): p.chmod(0o400)
    for p in root.rglob('*'):
        p.chmod(0o700 if p.is_dir() else 0o400)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--northstar', action='store_true')
    parser.add_argument('--source-review-only', action='store_true', help='Offline review only; production verification rejects this provenance schema')
    a = parser.parse_args()
    record = verify(a.build_root, a.source, a.commit) if a.verify_only else build(a.source, a.build_root, a.commit, northstar=a.northstar, review=a.source_review_only)
    print(json.dumps({'input_hash': record['input_hash'], 'output_hash': record['output_hash'],
                      'manifest_hash': sha(a.build_root/'frontend-provenance.json'), 'outputs': record['outputs']}))


if __name__ == '__main__':
    main()
