"""Assemble pinned immutable bytes; never install, run, download or qualify them.

Archive extraction/building and semantic provenance review precede this API.
Its manifest is a deployment input, not production or native acceptance.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from alpha_session_contract import require
from alpha_session_evidence import verify_files, open_root, path_parts, identity
from deployment_contract import (RUNTIME_MANIFEST_SCHEMA, PYTHON_VERSION, canonical,
                                 digest, dependency_inventory, inventory_tree)
from provider_gateway_contract import safe_document, pin, locked_authority
from alpha_session_package import sha
from truth_spine_lineage import check_pin

SCHEMA = 'iios-production-runtime-build-input-v1'
PROVENANCE = {'distribution', 'build_recipe', 'toolchain', 'dependency_artifacts', 'closure_review'}


def select_wheels(metadata, metadata_hash, *, lock_bytes):
    """Deterministic Darwin/arm64 CPython3.14 candidates, not import approval.

    Reject Windows ARM lookalikes. Requires-Python, dependency closure, native
    load commands and archive contents still require independent review.
    """
    safe_document(metadata); pin(metadata, metadata_hash)
    versions = lock_versions(lock_bytes)
    require(metadata.get('lock_sha256') == hashlib.sha256(lock_bytes).hexdigest(), 'WHEEL_LOCK')
    require(type(metadata.get('rows')) is list and len(metadata['rows']) == len(versions), 'WHEEL_ROWS')
    selected = []; seen = set()
    for row in metadata['rows']:
        name = re.sub('[-_.]+', '-', row['name']).lower()
        require(name not in seen and name in versions and row['version'] == versions[name], 'WHEEL_DISTRIBUTION')
        seen.add(name); candidates = []
        for artifact in row['artifacts']:
            filename = artifact['filename']
            require(type(filename) is str and re.fullmatch('[A-Za-z0-9_.+-]{1,240}', filename), 'WHEEL_FILENAME')
            tags = filename[:-4].rsplit('-', 3) if filename.endswith('.whl') else []
            if len(tags) != 4: continue
            prefix, interpreter, abi, platform = tags
            expected_prefix = name.replace('-', '_') + '-' + row['version']
            if prefix.lower() != expected_prefix.lower(): continue
            pure = interpreter in ('py3', 'py2.py3') and abi == 'none' and platform == 'any'
            mac = re.fullmatch(r'macosx_(\d+)_(\d+)_(arm64|universal2)', platform)
            compatible = (interpreter == 'cp314' and abi == 'cp314') or (
                re.fullmatch(r'cp3(?:[7-9]|1[0-4])', interpreter) and abi == 'abi3')
            native = mac and int(mac[1]) <= 26 and compatible
            if not (pure or native): continue
            parsed = urlsplit(artifact['url'])
            require(parsed.scheme == 'https' and parsed.hostname == 'files.pythonhosted.org' and
                    parsed.username is None and parsed.password is None and parsed.port is None and
                    not parsed.query and not parsed.fragment and parsed.path.endswith('/'+filename) and
                    sha(artifact['sha256']) and type(artifact['bytes']) is int and
                    0 < artifact['bytes'] <= 64*1024*1024, 'WHEEL_ARTIFACT')
            rank = 0 if native and mac[3] == 'arm64' else 1 if native else 2
            candidates.append((rank, filename, artifact))
        require(bool(candidates), 'WHEEL_COMPATIBLE_MISSING')
        _, _, artifact = sorted(candidates, key=lambda x: x[:2])[0]
        selected.append({'distribution': name, 'version': row['version'], **artifact})
    return sorted(selected, key=lambda x: x['distribution'])


def lexical(value, *, absolute=True):
    parts = path_parts(value, absolute=absolute)
    require(not any(p.lower() in {'keychains', 'ledger', 'ledgers', 'l7', 'l8', '.ssh',
                                 '.aws', '.env', 'application support', 'runtimes'} or
                    p.startswith('~') or 'runtime-template' in p or 'acceptance-sb' in p or
                    'installed-shadow' in p for p in parts), 'BUILD_PATH_REJECTED')
    return parts


def directory(path):
    """No-follow traversal; parent is caller-approved, owner-only mutable staging."""
    parts = lexical(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        st = os.fstat(fd)
        require(st.st_uid == os.getuid() and not st.st_mode & 0o077, 'BUILD_PARENT_MODE')
        return fd
    except BaseException:
        os.close(fd)
        raise


def lock_versions(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 65536, 'BUILD_LOCK')
    versions = {}
    for line in raw.decode('ascii').splitlines():
        if not line: continue
        require(re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+', line) is not None, 'BUILD_LOCK')
        name, version = line.split('==')
        name = re.sub('[-_.]+', '-', name).lower()
        require(name not in versions, 'BUILD_LOCK_DUPLICATE')
        versions[name] = version
    require(bool(versions), 'BUILD_LOCK')
    return versions


def admit(spec, expected, *, source_commit, approved_input_root, approved_output_parent,
          approved_platform_paths, lock_bytes, expected_lock_hash):
    safe_document(spec); pin(spec, expected)
    require(type(spec) is dict and set(spec) == {'schema', 'source_commit', 'input_root', 'output_parent',
            'output_name', 'files', 'interpreter', 'tls_bundle', 'platform_dependencies',
            'provenance', 'lock_sha256', 'python_version', 'system', 'architecture'}, 'BUILD_SCHEMA')
    require(spec['schema'] == SCHEMA and type(source_commit) is str and
            re.fullmatch('[0-9a-f]{40}', source_commit) and spec['source_commit'] == source_commit, 'BUILD_SOURCE')
    require(spec['input_root'] == approved_input_root and spec['output_parent'] == approved_output_parent,
            'BUILD_ROOT_APPROVAL')
    lexical(spec['input_root']); lexical(spec['output_parent'])
    require(type(spec['output_name']) is str and re.fullmatch('runtime-[a-z0-9-]{1,64}', spec['output_name']),
            'BUILD_OUTPUT_NAME')
    destination = spec['output_parent'] + '/' + spec['output_name']
    require(not (Path(destination).is_relative_to(spec['input_root']) or
                 Path(spec['input_root']).is_relative_to(destination)), 'BUILD_ROOT_OVERLAP')
    require(spec['python_version'] == PYTHON_VERSION and spec['system'] == 'Darwin' and
            spec['architecture'] == 'arm64', 'BUILD_TARGET')
    require(sha(expected_lock_hash) and spec['lock_sha256'] == expected_lock_hash and
            hashlib.sha256(lock_bytes).hexdigest() == expected_lock_hash, 'BUILD_LOCK_PIN')
    versions = lock_versions(lock_bytes)
    require(type(spec['provenance']) is dict and set(spec['provenance']) == PROVENANCE and
            all(sha(v) for v in spec['provenance'].values()), 'BUILD_PROVENANCE')
    require(type(spec['files']) is list, 'BUILD_FILES')
    for row in spec['files']: lexical(row['path'], absolute=False)
    entries = {row['path']: row for row in spec['files']}
    require('runtime-manifest.json' not in entries and spec['interpreter'] == 'bin/python3.14' and
            spec['interpreter'] in entries and entries[spec['interpreter']]['mode'] == 0o500 and
            spec['tls_bundle'] in entries and entries[spec['tls_bundle']]['mode'] == 0o400, 'BUILD_REQUIRED_FILES')
    require(type(approved_platform_paths) is tuple and type(spec['platform_dependencies']) is list and
            tuple(row['path'] for row in spec['platform_dependencies']) == approved_platform_paths and
            len(set(approved_platform_paths)) == len(approved_platform_paths), 'BUILD_PLATFORM_APPROVAL')
    for row in spec['platform_dependencies']:
        lexical(row['path']); require(type(row['mode']) is int and row['mode'] in (0o400, 0o500), 'BUILD_PLATFORM_MODE')
    # All lexical checks precede filesystem access. The shared validators retain
    # their owner, hardlink, immutable-mode, inventory and race checks unchanged.
    verify_files(spec['input_root'], spec['files'], approved_root=approved_input_root)
    for row in spec['platform_dependencies']: check_pin(row)
    deps = dependency_inventory(Path(spec['input_root']))
    found = {}
    for row in deps:
        name = re.sub('[-_.]+', '-', row['name']).lower()
        require(name not in found, 'BUILD_DEPENDENCY_DUPLICATE')
        found[name] = row['version']
    require(found == versions, 'BUILD_DEPENDENCIES')
    return destination, deps


def copy_row(source_fd, output_fd, row):
    """FD-relative streaming copy; no source execution or path-following writes."""
    parts = path_parts(row['path'])
    src, dst = os.dup(source_fd), os.dup(output_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=src)
            os.close(src); src = child
            try: os.mkdir(part, 0o700, dir_fd=dst)
            except FileExistsError: pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dst)
            os.close(dst); dst = child
        incoming = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src)
        try:
            before = os.fstat(incoming)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1 and
                    before.st_size == row['size'] and stat.S_IMODE(before.st_mode) == row['mode'], 'BUILD_SOURCE_CHANGED')
            outgoing = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, row['mode'], dir_fd=dst)
            h, count = hashlib.sha256(), 0
            with os.fdopen(outgoing, 'wb') as stream:
                while True:
                    chunk = os.read(incoming, min(65536, row['size'] - count + 1))
                    if not chunk: break
                    count += len(chunk); require(count <= row['size'], 'BUILD_COPY_BOUND')
                    h.update(chunk); stream.write(chunk)
                stream.flush(); os.fsync(stream.fileno())
            require(count == row['size'] and h.hexdigest() == row['sha256'] and
                    identity(os.fstat(incoming)) == identity(before) ==
                    identity(os.stat(parts[-1], dir_fd=src, follow_symlinks=False)), 'BUILD_COPY_CHANGED')
            os.fsync(dst)
        finally: os.close(incoming)
    finally: os.close(src); os.close(dst)


def assemble(spec, expected, **approvals):
    destination, deps = admit(spec, expected, **approvals)
    parent = directory(spec['output_parent'])
    source = output = None
    try:
        # Exclusive create; an interrupted build is preserved, never resumed.
        os.mkdir(spec['output_name'], 0o700, dir_fd=parent)
        output = os.open(spec['output_name'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        output_identity = os.fstat(output)
        source = open_root(spec['input_root'], approvals['approved_input_root'])
        for row in spec['files']: copy_row(source, output, row)
        verify_files(spec['input_root'], spec['files'], approved_root=approvals['approved_input_root'])
        for row in spec['platform_dependencies']: check_pin(row)
        root = Path(destination)
        require((root.stat().st_dev, root.stat().st_ino) == (output_identity.st_dev, output_identity.st_ino),
                'BUILD_OUTPUT_REPLACED')
        for path in sorted(root.rglob('*'), reverse=True):
            require(not path.is_symlink(), 'BUILD_OUTPUT_ALIAS')
            if path.is_dir(): path.chmod(0o500)
        observed = inventory_tree(root)
        require(observed == sorted(spec['files'], key=lambda row: row['path']) and
                dependency_inventory(root) == deps, 'BUILD_OUTPUT_INVENTORY')
        interpreter = next(row for row in observed if row['path'] == spec['interpreter'])
        manifest = dict(schema=RUNTIME_MANIFEST_SCHEMA, runtime_id='alpha-runtime-' + expected[:24],
            release_commit=approvals['source_commit'], runtime_root=destination,
            interpreter=destination + '/' + spec['interpreter'], interpreter_sha256=interpreter['sha256'],
            python_version=PYTHON_VERSION, dependency_inventory=deps, file_inventory=observed,
            platform_dependencies=[{'path': p['path'], 'sha256': p['sha256']} for p in spec['platform_dependencies']])
        manifest['content_hash'] = digest(manifest)
        data = canonical(manifest)
        fd = os.open('runtime-manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=output)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.fchmod(output, 0o500); os.fsync(output); os.fsync(parent)
        verify_files(destination, observed + [{'path': 'runtime-manifest.json', 'size': len(data),
                     'mode': 0o400, 'sha256': hashlib.sha256(data).hexdigest()}], approved_root=destination)
        return {'schema': 'iios-production-runtime-assembly-result-v1', 'input_parent': expected,
                'manifest': manifest, 'manifest_sha256': hashlib.sha256(data).hexdigest(),
                'status': 'ASSEMBLED_BYTES_ONLY', 'authority': locked_authority(),
                'production_qualified': False, 'execution_authorized': False,
                'pending': ['PROVENANCE_SEMANTICS', 'NATIVE_IMPORTS_PLATFORM_TLS', 'OS_CONFINEMENT', 'PRODUCTION_ADMISSION']}
    finally:
        for fd in (source, output, parent):
            if fd is not None: os.close(fd)
