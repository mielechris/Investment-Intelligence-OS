"""Read-only file verification for candidate admission; never launches or authorizes.

All roots and manifest hashes must be independently supplied by the caller.
No evidence is discovered from home directories, credentials, or the ledger.
"""
import hashlib
import json
import os
from pathlib import PurePosixPath
import stat

from alpha_session_contract import require, instant
from alpha_session_package import verify_bound_package, sha
from deployment_contract import RUNTIME_MANIFEST_SCHEMA, digest
from provider_gateway_contract import content_hash, locked_authority, pin, safe_document
from provider_gateway_live_contract import CLAIMS

MAX_FILES = 5000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def path_parts(value, *, absolute=False):
    require(type(value) is str and '\x00' not in value, 'EVIDENCE_PATH')
    path = PurePosixPath(value)
    require(path.is_absolute() == absolute and str(path) == value and
            '..' not in path.parts and value not in ('', '.', '/'), 'EVIDENCE_PATH')
    parts = path.parts[1:] if absolute else path.parts
    require(len(parts) <= 32, 'EVIDENCE_PATH_DEPTH')
    return parts


def identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns,
            st.st_mode, st.st_uid, st.st_nlink)


def open_root(root, approved_root):
    # Equality and lexical checks precede ALL filesystem operations.
    require(type(root) is str and root == approved_root, 'EVIDENCE_ROOT_NOT_APPROVED')
    parts = path_parts(root, absolute=True)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        st = os.fstat(fd)
        require(st.st_uid == os.getuid() and not st.st_mode & 0o222, 'EVIDENCE_ROOT_MODE')
        return fd
    except BaseException:
        os.close(fd)
        raise


def verify_files(root, rows, *, approved_root, retain=()):
    """Exact inventory, bounded streaming reads and no-follow directory traversal.

    This is a point-in-time check; future execution must revalidate and confine.
    Only explicitly requested small JSON evidence bytes are retained in memory.
    """
    require(type(root) is str and root == approved_root, 'EVIDENCE_ROOT_NOT_APPROVED')
    path_parts(root, absolute=True)
    require(type(rows) is list and 0 < len(rows) <= MAX_FILES, 'EVIDENCE_FILE_COUNT')
    entries, directories, total = {}, set(), 0
    for row in rows:
        require(type(row) is dict and set(row) == {'path','size','mode','sha256'}, 'EVIDENCE_FILE_SCHEMA')
        parts = path_parts(row['path'])
        require(row['path'] not in entries and type(row['size']) is int and
                0 <= row['size'] <= MAX_FILE_BYTES and type(row['mode']) is int and
                row['mode'] in (0o400,0o500) and sha(row['sha256']), 'EVIDENCE_FILE_BOUND')
        total += row['size']
        require(total <= MAX_TOTAL_BYTES, 'EVIDENCE_TOTAL_BOUND')
        entries[row['path']] = row
        directories.update('/'.join(parts[:i]) for i in range(1,len(parts)))
    require(not directories.intersection(entries) and set(retain) <= set(entries) and
            sum(entries[name]['size'] for name in retain) <= 4*1024*1024, 'EVIDENCE_RETAIN_BOUND')
    fd = open_root(root, approved_root)
    before = identity(os.fstat(fd))
    bodies, observed = {}, set()

    def walk(parent, prefix=''):
        parent_before = identity(os.fstat(parent))
        for name in sorted(os.listdir(parent)):
            relative = prefix+name
            st = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if relative in directories:
                require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and
                        not st.st_mode & 0o222, 'EVIDENCE_DIRECTORY_MODE')
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    require(identity(os.fstat(child)) == identity(st), 'EVIDENCE_DIRECTORY_CHANGED')
                    walk(child,relative+'/')
                    require(identity(os.fstat(child)) == identity(os.stat(name,dir_fd=parent,follow_symlinks=False)),
                            'EVIDENCE_DIRECTORY_CHANGED')
                finally: os.close(child)
            else:
                require(relative in entries, 'EVIDENCE_EXTRA_FILE')
                row = entries[relative]
                require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid() and
                        stat.S_IMODE(st.st_mode) == row['mode'] and st.st_size == row['size'], 'EVIDENCE_FILE_IDENTITY')
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                try:
                    require(identity(os.fstat(child)) == identity(st), 'EVIDENCE_FILE_CHANGED')
                    hasher, count, chunks = hashlib.sha256(), 0, []
                    while True:
                        block = os.read(child, min(65536,row['size']-count+1))
                        if not block: break
                        count += len(block)
                        require(count <= row['size'], 'EVIDENCE_READ_BOUND')
                        hasher.update(block)
                        if relative in retain: chunks.append(block)
                    require(count == row['size'] and hasher.hexdigest() == row['sha256'], 'EVIDENCE_HASH')
                    require(identity(os.fstat(child)) == identity(st) ==
                            identity(os.stat(name,dir_fd=parent,follow_symlinks=False)), 'EVIDENCE_FILE_CHANGED')
                    if relative in retain: bodies[relative] = b''.join(chunks)
                    observed.add(relative)
                finally: os.close(child)
        require(identity(os.fstat(parent)) == parent_before, 'EVIDENCE_DIRECTORY_CHANGED')

    try:
        walk(fd)
        require(observed == set(entries), 'EVIDENCE_MISSING_FILE')
        after = open_root(root, approved_root)
        try: require(identity(os.fstat(after)) == before, 'EVIDENCE_ROOT_CHANGED')
        finally: os.close(after)
    finally: os.close(fd)
    return bodies


def json_document(raw):
    def unique(pairs):
        result = {}
        for key,value in pairs:
            require(key not in result, 'EVIDENCE_DUPLICATE_KEY')
            result[key] = value
        return result
    result = json.loads(raw,object_pairs_hook=unique)
    safe_document(result)
    return result


def verify_candidate_evidence(candidate, candidate_hash, plan, account, runtime, allowance, *,
                              runtime_manifest, claims_manifest, claims_manifest_hash,
                              approved_runtime_root, approved_claims_root, **package_inputs):
    """Verifies file identities and reviewed claim bindings, not semantic truth.

    The ordinary deployment/runtime, native confinement, live preflight and
    execution-authority validators remain mandatory and are not called here.
    """
    verified = verify_bound_package(candidate,candidate_hash,plan,account,runtime,allowance,**package_inputs)
    from alpha_runtime_files import safe_runtime_document
    safe_runtime_document(runtime_manifest); pin(runtime_manifest,runtime['runtime_manifest_sha256'])
    from alpha_runtime_files import MANIFEST_SCHEMA, COMPLETED_MANIFEST_SCHEMA, COMPLETION_FIELDS, EXTENSION_FIELDS, verify_manifest
    version3 = runtime_manifest.get('schema') == COMPLETED_MANIFEST_SCHEMA
    version2 = runtime_manifest.get('schema') in (MANIFEST_SCHEMA, COMPLETED_MANIFEST_SCHEMA)
    require(type(runtime_manifest) is dict and set(runtime_manifest) == ({
        'schema','runtime_id','release_commit','runtime_root','interpreter','interpreter_sha256',
        'python_version','dependency_inventory','file_inventory','platform_dependencies','content_hash'} |
        (EXTENSION_FIELDS if version2 else set()) | (COMPLETION_FIELDS if version3 else set())), 'EVIDENCE_RUNTIME_SCHEMA')
    require(runtime_manifest.get('schema') in (RUNTIME_MANIFEST_SCHEMA, MANIFEST_SCHEMA, COMPLETED_MANIFEST_SCHEMA) and
            runtime_manifest.get('content_hash') == digest(runtime_manifest) and
            runtime_manifest.get('release_commit') == verified['source_commit'] and
            runtime_manifest.get('python_version') == runtime['python_version'], 'EVIDENCE_RUNTIME_BINDING')
    root = runtime_manifest['runtime_root']
    require(root == approved_runtime_root, 'EVIDENCE_ROOT_NOT_APPROVED')
    path_parts(root,absolute=True)
    interpreter = runtime_manifest['interpreter']
    require(type(interpreter) is str and interpreter.startswith(root+'/'), 'EVIDENCE_INTERPRETER_PATH')
    name = interpreter[len(root)+1:]; path_parts(name)
    rows = runtime_manifest['file_inventory']
    require(type(rows) is list, 'EVIDENCE_RUNTIME_FILES')
    matches = [r for r in rows if r.get('path') == name]
    require(len(matches)==1 and matches[0]['mode']==0o500 and
            matches[0]['sha256']==runtime_manifest['interpreter_sha256']==runtime['interpreter_sha256'],
            'EVIDENCE_INTERPRETER_BINDING')
    require(content_hash(runtime_manifest['platform_dependencies']) == runtime['platform_manifest_sha256'],
            'EVIDENCE_PLATFORM_BINDING')
    # The existing immutable runtime manifest excludes itself from file_inventory.
    # Bind its actual bytes as well, without altering that deployed schema.
    from provider_gateway_contract import canonical
    manifest_bytes = canonical(runtime_manifest)
    require(all(r['path'] != 'runtime-manifest.json' for r in rows), 'EVIDENCE_MANIFEST_RECURSION')
    if version2:
        verify_manifest(root,runtime_manifest,source_commit=verified['source_commit'])
    else:
        verify_files(root,rows+[{'path':'runtime-manifest.json','size':len(manifest_bytes),'mode':0o400,
                                'sha256':hashlib.sha256(manifest_bytes).hexdigest()}],approved_root=approved_runtime_root)
    safe_document(claims_manifest); pin(claims_manifest,claims_manifest_hash)
    require(set(claims_manifest)=={'schema','account_parent','root','files','claims'} and
            claims_manifest['schema']=='iios-alpha-reviewed-claim-files-v1' and
            claims_manifest['account_parent']==package_inputs['input_pins']['account'] and
            set(claims_manifest['claims'])==set(CLAIMS), 'EVIDENCE_CLAIMS_MANIFEST')
    names = list(claims_manifest['claims'].values())
    require(len(set(names))==len(CLAIMS), 'EVIDENCE_CLAIM_REUSE')
    bodies = verify_files(claims_manifest['root'],claims_manifest['files'],approved_root=approved_claims_root,retain=names)
    for claim,name in claims_manifest['claims'].items():
        doc = json_document(bodies[name]); pin(doc,account['claim_parents'][claim])
        require(set(doc)=={'schema','claim','account_identity','tier_identity','provider','endpoint','feed',
                          'symbols_parent','source_commit','session','valid_from','expires_at','review_parent'},
                'EVIDENCE_CLAIM_SCHEMA')
        require(doc['schema']=='iios-alpha-reviewed-account-claim-v1' and doc['claim']==claim and
                all(doc[k]==account[k] for k in ('account_identity','tier_identity','provider','endpoint','feed',
                                                'source_commit','session')) and
                doc['symbols_parent']==content_hash(account['symbols']) and sha(doc['review_parent']), 'EVIDENCE_CLAIM_BINDING')
        require(instant(doc['valid_from'])<=instant(account['valid_from']) and
                instant(doc['expires_at'])>=instant(account['expires_at']), 'EVIDENCE_CLAIM_WINDOW')
    return {'schema':'iios-alpha-candidate-evidence-check-v1','status':'FILES_AND_BINDINGS_VERIFIED_ONLY',
            'package_parent':candidate_hash,'claims_manifest_parent':claims_manifest_hash,
            'runtime_parent':runtime['runtime_manifest_sha256'], 'authority':locked_authority(),
            'production_qualified':False,'execution_authorized':False,
            'pending':['SEMANTIC_ACCOUNT_REVIEW','PLATFORM_AND_RUNNING_INTERPRETER',
                       'OS_CONFINEMENT','LIVE_PREFLIGHT','PRODUCTION_LIFECYCLE','EXECUTION_AUTHORITY']}
