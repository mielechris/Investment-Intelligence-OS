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
    from alpha_runtime_files import safe_runtime_document
    safe_runtime_document(spec); pin(spec, expected)
    from alpha_runtime_files import (BUILD_SCHEMA, COMPLETED_BUILD_SCHEMA, COMPLETION_FIELDS,
        EXTENSION_FIELDS, extension, verify_runtime_tree, VENDOR, validate_completion, sealed_payload_parent)
    version3 = spec.get('schema') == COMPLETED_BUILD_SCHEMA
    version2 = spec.get('schema') in (BUILD_SCHEMA, COMPLETED_BUILD_SCHEMA)
    if version2:
        extension(spec)
        require(spec['provenance']['distribution'] == VENDOR, 'BUILD_DISTRIBUTION_LAYOUT')
    require(type(spec) is dict and set(spec) == ({'schema', 'source_commit', 'input_root', 'output_parent',
            'output_name', 'files', 'interpreter', 'tls_bundle', 'platform_dependencies',
            'provenance', 'lock_sha256', 'python_version', 'system', 'architecture'} |
            (EXTENSION_FIELDS if version2 else set()) | (COMPLETION_FIELDS if version3 else set())), 'BUILD_SCHEMA')
    require(spec['schema'] in (SCHEMA, BUILD_SCHEMA, COMPLETED_BUILD_SCHEMA) and type(source_commit) is str and
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
    if version3:
        validate_completion(spec['completion'])
        require(spec['completion']['dependency_lock_sha256']==expected_lock_hash and
            spec['completion']['sealed_payload_sha256']==sealed_payload_parent(spec), 'BUILD_COMPLETED_PARENTS')
        require([r['path'] for r in spec['files']]==sorted(r['path'] for r in spec['files']) and
            {'Python','_CodeSignature/CodeResources'} <= {r['path'] for r in spec['files']},'BUILD_COMPLETED_SEAL')
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
    if version2:
        require(len(spec['files']) + (2 if version3 else 1) <= 7000, 'BUILD_MANIFEST_FILE_CAPACITY')
        verify_runtime_tree(spec['input_root'],spec['files'],approved_root=approved_input_root,**extension(spec))
    else:
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


def copy_row(source_fd, output_fd, row, *, metadata=None):
    """FD-relative streaming copy; no source execution or path-following writes."""
    parts = path_parts(row['path'])
    require(type(row['mode']) is int and row['mode'] in (0o400, 0o500), 'BUILD_COPY_MODE')
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
            # Darwin authorizes xattr writes against the inode mode, even when
            # this exclusive descriptor was opened writable. Seal only after
            # metadata copying; the temporary file is owner-only, non-executable.
            outgoing = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dst)
            h, count = hashlib.sha256(), 0
            with os.fdopen(outgoing, 'wb') as stream:
                primary = None
                try:
                    os.fchmod(stream.fileno(), 0o600)  # independent of caller umask
                    while True:
                        chunk = os.read(incoming, min(65536, row['size'] - count + 1))
                        if not chunk: break
                        count += len(chunk); require(count <= row['size'], 'BUILD_COPY_BOUND')
                        h.update(chunk); stream.write(chunk)
                    stream.flush()
                    if metadata is not None:
                        from alpha_runtime_files import copy_runtime_metadata
                        copy_runtime_metadata(incoming,stream.fileno(),metadata)
                except BaseException as error:
                    primary = error
                    raise
                finally:
                    try:
                        os.fchmod(stream.fileno(), row['mode'])
                        require(stat.S_IMODE(os.fstat(stream.fileno()).st_mode) == row['mode'], 'BUILD_COPY_SEAL')
                        os.fsync(stream.fileno())
                    except BaseException:
                        if primary is None:
                            raise ValueError('BUILD_COPY_SEAL') from None
                        # Keep the original error; cleanup cannot replace it.
                        primary.copy_cleanup_failure = 'BUILD_COPY_SEAL'
            require(count == row['size'] and h.hexdigest() == row['sha256'] and
                    identity(os.fstat(incoming)) == identity(before) ==
                    identity(os.stat(parts[-1], dir_fd=src, follow_symlinks=False)), 'BUILD_COPY_CHANGED')
            os.fsync(dst)
        finally: os.close(incoming)
    except BaseException as error:
        # Hash-only row context, usable by bounded artifact supervisors without
        # retaining paths, data, xattr contents or unrestricted exception text.
        error.copy_file_identity = {
            'sha256': row['sha256'] if type(row['sha256']) is str and re.fullmatch('[a-f0-9]{64}',row['sha256']) else 'UNKNOWN',
            'size': row['size'] if type(row['size']) is int and 0 <= row['size'] <= 64*1024*1024 else None,
            'path_sha256': hashlib.sha256(row['path'].encode()).hexdigest()}
        raise
    finally: os.close(src); os.close(dst)


def assemble(spec, expected, **approvals):
    destination, deps = admit(spec, expected, **approvals)
    from alpha_runtime_files import (BUILD_SCHEMA, MANIFEST_SCHEMA, COMPLETED_BUILD_SCHEMA, COMPLETED_MANIFEST_SCHEMA,
        extension, inventory_runtime, verify_runtime_tree, verify_manifest, copy_runtime_metadata,
        completed_paths, completed_envelope)
    version3=spec['schema']==COMPLETED_BUILD_SCHEMA
    if spec['schema'] in (BUILD_SCHEMA, COMPLETED_BUILD_SCHEMA):
        def subdirectory(fd, parts):
            child = os.dup(fd)
            try:
                for part in parts:
                    nxt = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=child)
                    os.close(child); child = nxt
                return child
            except BaseException:
                os.close(child); raise
        parent = directory(spec['output_parent']); source = output = manifest_fd = None
        try:
            os.mkdir(spec['output_name'],0o700,dir_fd=parent)
            output = os.open(spec['output_name'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            output_id = os.fstat(output)
            source = open_root(spec['input_root'],approvals['approved_input_root'])
            for row in spec['files']:
                copy_row(source,output,row,metadata=spec['metadata'][row['path']])
            for link in spec['layout_policy']['links']:
                parts = path_parts(link['path']); fd = subdirectory(output,parts[:-1])
                try: os.symlink(link['target'],parts[-1],dir_fd=fd)
                finally: os.close(fd)
            # Preserve directory metadata as well; never follow or chmod aliases.
            file_names = {r['path'] for r in spec['files']}
            link_names = {r['path'] for r in spec['layout_policy']['links']}
            directories = sorted(set(spec['metadata']) - file_names - link_names - {'.'},key=lambda x:(-x.count('/'),x))
            for name in directories + ['.']:
                parts = () if name == '.' else path_parts(name)
                incoming = subdirectory(source,parts); outgoing = subdirectory(output,parts)
                try:
                    copy_runtime_metadata(incoming,outgoing,spec['metadata'][name])
                    if name != '.': os.fchmod(outgoing,0o500)
                finally: os.close(incoming); os.close(outgoing)
            verify_runtime_tree(spec['input_root'],spec['files'],approved_root=spec['input_root'],**extension(spec))
            for row in spec['platform_dependencies']: check_pin(row)
            # Create the manifest inode before sealing. Its metadata can be pinned
            # without recursively including the manifest's own data hash.
            if not version3:
                manifest_fd = os.open('runtime-manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=output)
            os.fchmod(output,0o500)
            observed = inventory_runtime(destination,spec['layout_policy'],spec['layout_parent'],approved_root=destination)
            rows = [r for r in observed['files'] if r['path'] != 'runtime-manifest.json']
            require(rows == sorted(spec['files'],key=lambda r:r['path']) and dependency_inventory(Path(destination)) == deps,
                'BUILD_OUTPUT_INVENTORY')
            interpreter = next(r for r in rows if r['path'] == spec['interpreter'])
            manifest = dict(schema=COMPLETED_MANIFEST_SCHEMA if version3 else MANIFEST_SCHEMA,runtime_id='alpha-runtime-'+expected[:24],
                release_commit=approvals['source_commit'],runtime_root=destination,interpreter=destination+'/'+spec['interpreter'],
                interpreter_sha256=interpreter['sha256'],python_version=PYTHON_VERSION,dependency_inventory=deps,
                file_inventory=rows,platform_dependencies=[{'path':r['path'],'sha256':r['sha256']} for r in spec['platform_dependencies']],
                layout_policy=spec['layout_policy'],layout_parent=spec['layout_parent'],metadata=observed['metadata'])
            if version3: manifest['completion']=spec['completion']
            manifest['content_hash'] = digest(manifest); data = canonical(manifest)
            if version3:
                # Input content is finalized and sealed BEFORE this copy. No
                # signature mutation, provider activity or subprocess occurs here.
                # Detached records are siblings, never resources of the bundle.
                paths=completed_paths(destination)
                records=((paths['manifest'],data),(paths['envelope'],canonical(completed_envelope(manifest))))
                from alpha_runtime_files import MAX_TOTAL_BYTES, MAX_FILES
                require(len(rows)+2<=MAX_FILES and sum(r['size'] for r in rows)+
                    sum(len(raw) for _,raw in records)+len(canonical(manifest['metadata']))<=MAX_TOTAL_BYTES,
                    'RUNTIME_COMPLETED_TOTAL_BOUND')
                for path,raw in records:
                    fd=os.open(Path(path).name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=parent)
                    try:
                        view=memoryview(raw)
                        while view:
                            count=os.write(fd,view);require(count>0,'BUILD_WRITE');view=view[count:]
                        os.fsync(fd)
                    finally:os.close(fd)
                os.fsync(parent)
                require(identity(os.fstat(output))==identity(os.stat(spec['output_name'],dir_fd=parent,follow_symlinks=False)),
                    'BUILD_OUTPUT_REPLACED')
                verify_manifest(destination,manifest,source_commit=approvals['source_commit'])
                return dict(schema='iios-completed-runtime-assembly-result-v3',input_parent=expected,manifest=manifest,
                    manifest_sha256=hashlib.sha256(data).hexdigest(),envelope_sha256=hashlib.sha256(records[1][1]).hexdigest(),
                    manifest_path=paths['manifest'],envelope_path=paths['envelope'],status='ASSEMBLED_BYTES_ONLY',
                    authority=locked_authority(),production_qualified=False,execution_authorized=False,
                    pending=['FINAL_LOCATION_OS_SIGNATURE_VERIFICATION','NATIVE_IMPORTS_PLATFORM_TLS','OS_CONFINEMENT','PRODUCTION_ADMISSION'])
            # Byte limits include the final serialized manifest and metadata.
            from alpha_runtime_files import _validate_rows, validate_layout_policy
            manifest_row = dict(path='runtime-manifest.json',size=len(data),mode=0o400,sha256=hashlib.sha256(data).hexdigest())
            _validate_rows(rows+[manifest_row],manifest['metadata'],validate_layout_policy(spec['layout_policy'],spec['layout_parent']))
            view = memoryview(data)
            while view:
                count = os.write(manifest_fd,view); require(count > 0,'BUILD_WRITE'); view = view[count:]
            os.fsync(manifest_fd); os.fsync(output); os.fsync(parent)
            require((os.stat(spec['output_name'],dir_fd=parent,follow_symlinks=False).st_dev,
                os.stat(spec['output_name'],dir_fd=parent,follow_symlinks=False).st_ino) == (output_id.st_dev,output_id.st_ino),
                'BUILD_OUTPUT_REPLACED')
            verify_manifest(destination,manifest,source_commit=approvals['source_commit'])
            return {'schema':'iios-production-runtime-assembly-result-v2','input_parent':expected,'manifest':manifest,
                'manifest_sha256':hashlib.sha256(data).hexdigest(),'status':'ASSEMBLED_BYTES_ONLY',
                'authority':locked_authority(),'production_qualified':False,'execution_authorized':False,
                'pending':['PROVENANCE_SEMANTICS','NATIVE_IMPORTS_PLATFORM_TLS','OS_CONFINEMENT','PRODUCTION_ADMISSION']}
        finally:
            for fd in (manifest_fd,source,output,parent):
                if fd is not None: os.close(fd)
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
