"""Versioned, archive-specific runtime tree policy. No execution or activation.

The generic evidence verifier remains link-free. This verifier observes only
physical entries; it never traverses a symlink, even an admitted one.
"""
import errno
import hashlib
import os
from pathlib import PurePosixPath
import re
import stat

from alpha_session_contract import require
from alpha_session_evidence import path_parts, open_root, identity
from provider_gateway_contract import content_hash

MANIFEST_SCHEMA = 'iios-immutable-python-runtime-v2'
DESCRIPTOR_SCHEMA = 'iios-observation-runtime-files-v2'
BUILD_SCHEMA = 'iios-production-runtime-build-input-v2'
MAX_FILES = 7000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
VENDOR = '70c5239ad2d62925d2947e46921d0ddd3d35be3d2f0a2d50db33da507dbcb419'
EXTENSION_FIELDS = {'layout_policy', 'layout_parent', 'metadata'}
_XATTRS = frozenset({'com.apple.cs.CodeDirectory', 'com.apple.cs.CodeRequirements',
                    'com.apple.cs.CodeSignature', 'com.apple.quarantine', 'com.apple.provenance'})
_LINKS = tuple(sorted((
    (f'Frameworks/{name}.framework/{path}', target)
    for name, lower in (('Tcl', 'tcl'), ('Tk', 'tk'))
    for path, target in (('Versions/Current', '9.0'),
        (name, 'Versions/Current/' + name), ('Headers', 'Versions/Current/Headers'),
        ('Resources', 'Versions/Current/Resources'),
        (lower + 'Config.sh', 'Versions/Current/' + lower + 'Config.sh'),
        ('lib' + lower + 'stub.a', 'Versions/9.0/lib' + lower + 'stub.a'))
)))


def layout_policy():
    return {'schema': 'iios-python3147-framework-layout-v1', 'distribution_sha256': VENDOR,
            'links': [{'path': p, 'target': t, 'sha256': hashlib.sha256(t.encode()).hexdigest()}
                      for p, t in _LINKS], 'max_files': MAX_FILES,
            'max_file_bytes': MAX_FILE_BYTES, 'max_total_bytes': MAX_TOTAL_BYTES}


def validate_layout_policy(policy, expected):
    # An edited/rehashed policy cannot become an independent approval.
    approved = layout_policy()
    require(type(policy) is dict and policy == approved and
            type(expected) is str and expected == content_hash(approved) == content_hash(policy),
            'RUNTIME_LAYOUT_POLICY')
    return dict(_LINKS)


def extension(document):
    require(EXTENSION_FIELDS <= set(document), 'RUNTIME_EXTENSION')
    validate_layout_policy(document['layout_policy'], document['layout_parent'])
    return {k: document[k] for k in EXTENSION_FIELDS}


def _root(root, approved):
    require(type(root) is str and root == approved, 'RUNTIME_ROOT_APPROVAL')
    require('//' not in root, 'RUNTIME_ROOT_PATH')
    parts = path_parts(root, absolute=True)
    require(not any(p.lower() in {'keychains', 'ledger', 'ledgers', 'l7', 'l8', '.ssh',
        '.aws', '.env', 'application support'} or p.startswith('~') for p in parts), 'RUNTIME_ROOT_PATH')


def _terminal(path, links):
    current = PurePosixPath(path); framework = PurePosixPath(*current.parts[:2]); seen = set(); hops = 0
    while True:
        require(str(current) not in seen, 'RUNTIME_LINK_CYCLE'); seen.add(str(current))
        for i in range(1, len(current.parts) + 1):
            prefix = PurePosixPath(*current.parts[:i])
            if str(prefix) in links:
                target = links[str(prefix)]
                require(not target.startswith('/') and '..' not in PurePosixPath(target).parts and
                        str(PurePosixPath(target)) == target, 'RUNTIME_LINK_TARGET')
                current = prefix.parent / target / PurePosixPath(*current.parts[i:]); hops += 1
                require(hops <= 2 and current.is_relative_to(framework), 'RUNTIME_LINK_CONTAINMENT')
                break
        else:
            return str(current)


def _metadata_digest(values):
    require(type(values) is dict and set(values) <= _XATTRS, 'RUNTIME_XATTR_NAME')
    out = {}
    for name, value in values.items():
        require(type(value) is bytes and len(value) <= 1024 * 1024, 'RUNTIME_XATTR_BOUND')
        if name == 'com.apple.provenance':
            require(len(value) == 11, 'RUNTIME_PROVENANCE_FORMAT')
        if name == 'com.apple.quarantine':
            # No removal/normalization: all actual bytes are independently pinned.
            raw = value.rstrip(b'\0'); raw = raw[2:] if raw.startswith(b'q/') else raw
            fields = raw.split(b';')
            require(len(raw) <= 128 and all(32 <= c < 127 for c in raw) and len(fields) == 4 and
                re.fullmatch(b'(?:0083|0283)', fields[0]) and
                re.fullmatch(b'[0-9a-fA-F]{8}', fields[1]), 'RUNTIME_QUARANTINE_FORMAT')
        out[name] = {'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
    return out


def _darwin():
    # Lazy and effect-bound: no dylib access at module import or pure admission.
    import ctypes
    import sys
    require(sys.platform == 'darwin', 'RUNTIME_METADATA_PLATFORM')
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    lib.flistxattr.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    lib.flistxattr.restype = ctypes.c_ssize_t
    lib.fgetxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                             ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.fgetxattr.restype = ctypes.c_ssize_t
    lib.fsetxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                             ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.fsetxattr.restype = ctypes.c_int
    return ctypes, lib


def _read_xattrs(fd):
    c, lib = _darwin(); size = lib.flistxattr(fd, None, 0, 0)
    require(0 <= size <= 4096, 'RUNTIME_XATTR_LIST')
    buf = c.create_string_buffer(size)
    require(lib.flistxattr(fd, buf, size, 0) == size, 'RUNTIME_XATTR_RACE')
    names = buf.raw.split(b'\0')[:-1] if size else []
    require(not size or (buf.raw.endswith(b'\0') and all(names)), 'RUNTIME_XATTR_LIST')
    values = {}
    for name in names:
        if not name: continue
        require(name in {n.encode('ascii') for n in _XATTRS} and name.decode('ascii') not in values, 'RUNTIME_XATTR_NAME')
        n = lib.fgetxattr(fd, name, None, 0, 0, 0)
        require(0 <= n <= 1024 * 1024, 'RUNTIME_XATTR_BOUND')
        value = c.create_string_buffer(n)
        require(lib.fgetxattr(fd, name, value, n, 0, 0) == n, 'RUNTIME_XATTR_RACE')
        values[name.decode('ascii')] = value.raw
    return values


_COPY_PREDICATES = frozenset({
    'RUNTIME_COPY_METADATA_PARENT', 'RUNTIME_COPY_METADATA_DESTINATION',
    'RUNTIME_COPY_METADATA_CHANGED', 'RUNTIME_COPY_METADATA_RACE',
    'RUNTIME_XATTR_NAME', 'RUNTIME_XATTR_BOUND', 'RUNTIME_XATTR_LIST',
    'RUNTIME_XATTR_RACE', 'RUNTIME_XATTR_WRITE', 'RUNTIME_XATTR_COPY',
    'RUNTIME_PROVENANCE_FORMAT', 'RUNTIME_QUARANTINE_FORMAT',
    'RUNTIME_ACL_ABI', 'RUNTIME_ACL_READ', 'RUNTIME_ACL_NOT_ABSENT',
    'RUNTIME_ACL_CHANGED', 'RUNTIME_ACL_INVALID', 'RUNTIME_ACL_PRESENT',
    'RUNTIME_METADATA_PLATFORM', 'RUNTIME_METADATA_UNKNOWN'})
_COPY_STAGES = frozenset({'SOURCE_ACL', 'DESTINATION_ACL', 'SOURCE_READ',
    'SOURCE_PIN', 'DESTINATION_READ', 'DESTINATION_INITIAL', 'ATTRIBUTE_WRITE',
    'DESTINATION_VERIFY', 'SOURCE_RECHECK', 'DESTINATION_ACL_RECHECK'})


class RuntimeMetadataCopyError(ValueError):
    """Fixed diagnostics only; never include paths, attribute bytes or messages."""
    def __init__(self, predicate, stage, *, attribute=None, result=None, error_number=None):
        predicate = predicate if type(predicate) is str and predicate in _COPY_PREDICATES else 'RUNTIME_METADATA_UNKNOWN'
        super().__init__(predicate)
        categories = {errno.EACCES: 'ACCESS_DENIED_UNATTRIBUTED',
            errno.EPERM: 'OPERATION_DENIED_UNATTRIBUTED', errno.ENOTSUP: 'UNSUPPORTED',
            errno.EROFS: 'READ_ONLY_FILESYSTEM', errno.EINVAL: 'INVALID_ARGUMENT',
            errno.EBADF: 'BAD_DESCRIPTOR', errno.ENOSPC: 'NO_SPACE',
            errno.EIO: 'IO_ERROR', errno.ERANGE: 'RANGE', errno.E2BIG: 'TOO_LARGE'}
        self.diagnostic = dict(predicate=predicate,
            stage=stage if type(stage) is str and stage in _COPY_STAGES else 'UNKNOWN',
            attribute=attribute if type(attribute) is str and attribute in _XATTRS else 'UNKNOWN',
            syscall='fsetxattr' if stage == 'ATTRIBUTE_WRITE' else 'NOT_RECORDED',
            result=result if type(result) is int and result in (-1, 0) else 'UNKNOWN',
            errno=error_number if type(error_number) is int and 0 <= error_number <= 4095 else None,
            result_category=categories.get(error_number, 'UNKNOWN') if type(error_number) is int else 'UNKNOWN')


def _write_xattr(fd, name, value):
    require(name in _XATTRS - {'com.apple.provenance'}, 'RUNTIME_XATTR_WRITE')
    c, lib = _darwin(); buf = c.create_string_buffer(value)
    c.set_errno(0)
    result = lib.fsetxattr(fd, name.encode('ascii'), buf, len(value), 0, 0)
    error_number = c.get_errno()
    if result != 0:
        raise RuntimeMetadataCopyError('RUNTIME_XATTR_COPY', 'ATTRIBUTE_WRITE',
            attribute=name, result=result, error_number=error_number)



def _confirm_absent_acl(fd, c, lib):
    """Positive descriptor security query; ENOENT alone is never acceptance.

    Darwin sys/stat.h __DARWIN_STRUCT_STAT64 and sys/fcntl.h FILESEC_ACL.
    Compare the returned stat to independent fstat observations, including
    timestamps, so a failed query or unexpected ABI cannot look like absence.
    """
    class Timespec(c.Structure):
        _fields_ = [('sec', c.c_int64), ('nsec', c.c_int64)]
    class DarwinStat(c.Structure):
        _fields_ = [('dev',c.c_int32),('mode',c.c_uint16),('nlink',c.c_uint16),
            ('ino',c.c_uint64),('uid',c.c_uint32),('gid',c.c_uint32),('rdev',c.c_int32),
            ('atime',Timespec),('mtime',Timespec),('ctime',Timespec),('birth',Timespec),
            ('size',c.c_int64),('blocks',c.c_int64),('blksize',c.c_int32),
            ('flags',c.c_uint32),('gen',c.c_uint32),('spare',c.c_int32),('qspare',c.c_int64*2)]
    require(c.sizeof(c.c_void_p)==8 and c.sizeof(DarwinStat)==144, 'RUNTIME_ACL_ABI')
    lib.filesec_init.argtypes=[]; lib.filesec_init.restype=c.c_void_p
    lib.filesec_free.argtypes=[c.c_void_p]; lib.filesec_free.restype=None
    lib.fstatx_np.argtypes=[c.c_int,c.POINTER(DarwinStat),c.c_void_p]; lib.fstatx_np.restype=c.c_int
    lib.filesec_query_property.argtypes=[c.c_void_p,c.c_int,c.POINTER(c.c_int)]
    lib.filesec_query_property.restype=c.c_int
    before=os.fstat(fd); security=lib.filesec_init()
    require(bool(security), 'RUNTIME_ACL_READ')
    try:
        observed=DarwinStat(); present=c.c_int(-1)
        require(lib.fstatx_np(fd,c.byref(observed),security)==0, 'RUNTIME_ACL_READ')
        require(lib.filesec_query_property(security,5,c.byref(present))==0 and
                present.value==0, 'RUNTIME_ACL_NOT_ABSENT')
        require((observed.dev,observed.ino,observed.mode,observed.nlink,observed.uid,
            observed.gid,observed.size,observed.mtime.sec*10**9+observed.mtime.nsec,
            observed.ctime.sec*10**9+observed.ctime.nsec)==
            (before.st_dev,before.st_ino,before.st_mode,before.st_nlink,before.st_uid,
             before.st_gid,before.st_size,before.st_mtime_ns,before.st_ctime_ns) and
            identity(os.fstat(fd))==identity(before), 'RUNTIME_ACL_CHANGED')
    finally: lib.filesec_free(security)


def _check_acl(fd):
    c, lib = _darwin()
    lib.acl_get_fd_np.argtypes = [c.c_int, c.c_int]; lib.acl_get_fd_np.restype = c.c_void_p
    lib.acl_get_entry.argtypes = [c.c_void_p, c.c_int, c.POINTER(c.c_void_p)]
    lib.acl_free.argtypes = [c.c_void_p]
    c.set_errno(0)
    acl = lib.acl_get_fd_np(fd, 0x100)
    if not acl:
        require(c.get_errno() == errno.ENOENT, 'RUNTIME_ACL_READ')
        _confirm_absent_acl(fd, c, lib)
        return
    try:
        entry = c.c_void_p()
        lib.acl_valid.argtypes = [c.c_void_p]; lib.acl_valid.restype = c.c_int
        require(lib.acl_valid(acl) == 0, 'RUNTIME_ACL_INVALID')
        c.set_errno(0)
        # Darwin returns zero for an entry; an empty valid ACL returns EINVAL.
        status = lib.acl_get_entry(acl, 0, c.byref(entry))
        require(status == -1 and c.get_errno() == errno.EINVAL and not entry.value, 'RUNTIME_ACL_PRESENT')
    finally: lib.acl_free(acl)


def _link_metadata(parent, name, expected):
    require(hasattr(os, 'O_SYMLINK'), 'RUNTIME_LINK_METADATA_PLATFORM')
    fd = os.open(name, os.O_RDONLY | os.O_SYMLINK, dir_fd=parent)
    try:
        require(stat.S_ISLNK(os.fstat(fd).st_mode) and identity(os.fstat(fd)) == identity(expected), 'RUNTIME_LINK_CHANGED')
        _check_acl(fd)
        # Opaque local creation metadata, never vendor/signing authority. Length
        # is structural only: verify_runtime_tree also compares the independent
        # expected digest. Inventory observation alone cannot grant admission.
        values = _read_xattrs(fd)
        require(set(values) <= {'com.apple.provenance'}, 'RUNTIME_LINK_METADATA')
        observed = _metadata_digest(values)
        require(_read_xattrs(fd) == values, 'RUNTIME_LINK_METADATA_CHANGED')
        require(identity(os.fstat(fd)) == identity(expected), 'RUNTIME_LINK_CHANGED')
        return observed
    finally: os.close(fd)


def _validate_rows(rows, metadata, links):
    require(type(rows) is list and 0 < len(rows) <= MAX_FILES, 'RUNTIME_FILE_COUNT')
    entries = {}; directories = set(); total = 0
    for row in rows:
        require(type(row) is dict and set(row) == {'path','size','mode','sha256'}, 'RUNTIME_FILE_SCHEMA')
        parts = path_parts(row['path'])
        require(row['path'] not in entries and row['path'] not in links and
                type(row['size']) is int and 0 <= row['size'] <= MAX_FILE_BYTES and
                type(row['mode']) is int and row['mode'] in (0o400, 0o500) and
                type(row['sha256']) is str and re.fullmatch('[a-f0-9]{64}', row['sha256']), 'RUNTIME_FILE_BOUND')
        entries[row['path']] = row; total += row['size']
        directories.update('/'.join(parts[:i]) for i in range(1, len(parts)))
    for link in links:
        parts = path_parts(link); directories.update('/'.join(parts[:i]) for i in range(1, len(parts)))
    require(not (set(entries) | set(links)) & directories, 'RUNTIME_ALIAS_DESCENDANT')
    require(all(_terminal(p, links) in set(entries) | directories for p in links), 'RUNTIME_LINK_MISSING_TARGET')
    require(type(metadata) is dict and set(metadata) == set(entries) | directories | set(links) | {'.'}, 'RUNTIME_METADATA_INVENTORY')
    metadata_total = 0
    for path, values in metadata.items():
        require(type(values) is dict and set(values) <= _XATTRS, 'RUNTIME_METADATA_SCHEMA')
        if path in links:
            require(set(values) <= {'com.apple.provenance'}, 'RUNTIME_LINK_METADATA')
        for name, value in values.items():
            require(type(value) is dict and set(value) == {'size','sha256'} and
                type(value['size']) is int and 0 <= value['size'] <= 1024 * 1024 and
                type(value['sha256']) is str and re.fullmatch('[a-f0-9]{64}',value['sha256']), 'RUNTIME_METADATA_BOUND')
            if path in links:
                require(value['size'] == 11, 'RUNTIME_LINK_METADATA_BOUND')
            metadata_total += value['size']
    require(metadata_total <= MAX_METADATA_BYTES and total + metadata_total <= MAX_TOTAL_BYTES, 'RUNTIME_TOTAL_BOUND')
    return entries, directories


def _scan(root, approved_root, links):
    """Physical FD walk, complete before/after identity+metadata checks."""
    _root(root, approved_root); fd = open_root(root, approved_root); before = identity(os.fstat(fd))
    files = []; metadata = {}; identities = {}; found_links = set(); directories = set(); total = 0; nodes = 0; metadata_bytes = 0
    def remember_metadata(key, attrs):
        nonlocal metadata_bytes
        metadata_bytes += sum(v['size'] for v in attrs.values())
        require(metadata_bytes <= MAX_METADATA_BYTES and total + metadata_bytes <= MAX_TOTAL_BYTES,'RUNTIME_TOTAL_BOUND')
        metadata[key] = attrs
    def walk(parent, prefix=''):
        nonlocal total, nodes
        initial = identity(os.fstat(parent)); _check_acl(parent)
        key = prefix[:-1] if prefix else '.'; attrs = _metadata_digest(_read_xattrs(parent)); remember_metadata(key, attrs)
        for name in sorted(os.listdir(parent)):
            relative = prefix + name; path_parts(relative); nodes += 1
            require(nodes <= MAX_FILES * 32 + 12, 'RUNTIME_TREE_BOUND')
            st = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(st.st_uid == os.getuid(), 'RUNTIME_OWNER')
            if relative in links:
                require(stat.S_ISLNK(st.st_mode) and st.st_nlink == 1 and st.st_size == len(links[relative].encode()), 'RUNTIME_LINK_IDENTITY')
                require(os.readlink(name, dir_fd=parent) == links[relative], 'RUNTIME_LINK_BYTES')
                remember_metadata(relative, _link_metadata(parent, name, st))
                require(identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == identity(st) and
                        os.readlink(name, dir_fd=parent) == links[relative], 'RUNTIME_LINK_CHANGED')
                found_links.add(relative); continue
            require(not stat.S_ISLNK(st.st_mode) and not st.st_mode & 0o222, 'RUNTIME_UNAPPROVED_ALIAS_OR_MODE')
            if stat.S_ISDIR(st.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                directories.add(relative)
                try:
                    require(identity(os.fstat(child)) == identity(st), 'RUNTIME_DIRECTORY_CHANGED'); walk(child, relative + '/')
                    require(identity(os.fstat(child)) == identity(st) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'RUNTIME_DIRECTORY_CHANGED')
                finally: os.close(child)
            else:
                require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                    stat.S_IMODE(st.st_mode) in (0o400,0o500) and st.st_size <= MAX_FILE_BYTES, 'RUNTIME_FILE_IDENTITY')
                total += st.st_size; require(total + metadata_bytes <= MAX_TOTAL_BYTES and len(files) < MAX_FILES, 'RUNTIME_TOTAL_BOUND')
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                try:
                    require(identity(os.fstat(child)) == identity(st), 'RUNTIME_FILE_CHANGED'); _check_acl(child)
                    attrs = _metadata_digest(_read_xattrs(child)); remember_metadata(relative, attrs)
                    h = hashlib.sha256(); count = 0
                    while True:
                        block = os.read(child, min(65536, st.st_size-count+1))
                        if not block: break
                        count += len(block); require(count <= st.st_size, 'RUNTIME_READ_BOUND'); h.update(block)
                    require(count == st.st_size and _metadata_digest(_read_xattrs(child)) == attrs and
                        identity(os.fstat(child)) == identity(st) == identity(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'RUNTIME_FILE_CHANGED')
                    files.append({'path':relative,'size':count,'mode':stat.S_IMODE(st.st_mode),'sha256':h.hexdigest()})
                    identities[relative] = (st.st_dev, st.st_ino)
                finally: os.close(child)
        require(identity(os.fstat(parent)) == initial and _metadata_digest(_read_xattrs(parent)) == metadata[key], 'RUNTIME_DIRECTORY_CHANGED')
    try:
        walk(fd)
        require(found_links == set(links), 'RUNTIME_MISSING_LINK')
        require(all(_terminal(x, links) in set(identities) | directories for x in links), 'RUNTIME_LINK_MISSING_TARGET')
        after = open_root(root, approved_root)
        try: require(identity(os.fstat(after)) == before == identity(os.fstat(fd)), 'RUNTIME_ROOT_CHANGED')
        finally: os.close(after)
    finally: os.close(fd)
    files.sort(key=lambda x:x['path']); _validate_rows(files,metadata,links)
    return {'files':files,'metadata':metadata,'identities':identities}


def inventory_runtime(root, policy, expected, *, approved_root):
    return _scan(root, approved_root, validate_layout_policy(policy, expected))


def verify_runtime_tree(root, rows, *, approved_root, layout_policy, layout_parent, metadata):
    _root(root, approved_root); links = validate_layout_policy(layout_policy, layout_parent)
    _validate_rows(rows, metadata, links)  # All structural rejection precedes filesystem access.
    result = _scan(root, approved_root, links)
    require(result['files'] == sorted(rows,key=lambda x:x['path']) and result['metadata'] == metadata, 'RUNTIME_TREE_MISMATCH')
    return result['identities']


def safe_runtime_document(document):
    """Public-data validation for exact v2 runtime metadata path maps only.

    Path keys are not provider-document field names. Validate their complete
    archive-specific structure first, then validate names as string values and
    attribute documents as ordinary sensitive-document structures. Hashing and
    independent admission always use the original, unmodified document.
    This syntax check alone grants neither root approval nor file admission.
    """
    from provider_gateway_contract import safe_document
    require(type(document) is dict, 'RUNTIME_DOCUMENT_SCHEMA')
    schema = document.get('schema')
    if schema not in (BUILD_SCHEMA, MANIFEST_SCHEMA):
        safe_document(document)
        return
    links = validate_layout_policy(document['layout_policy'], document['layout_parent'])
    rows = document['files'] if schema == BUILD_SCHEMA else document['file_inventory']
    metadata = document['metadata']
    if schema == MANIFEST_SCHEMA:
        from deployment_contract import canonical
        raw = canonical(document)
        rows = rows + [dict(path='runtime-manifest.json', size=len(raw), mode=0o400,
                            sha256=hashlib.sha256(raw).hexdigest())]
    _validate_rows(rows, metadata, links)
    approved_headers = {'Headers'} | {p for p in links if p.endswith('/Headers')} | {
        _terminal(p, links) for p in links if p.endswith('/Headers')}
    for path in metadata:
        parts = path.split('/')
        for index, part in enumerate(parts):
            if part.lower() == 'headers':
                require('/'.join(parts[:index+1]) in approved_headers, 'RUNTIME_HEADERS_LOCATION')
    view = dict(document)
    # Only the exact root directory key collides with provider field names.
    # All other metadata keys retain the original sensitive-key checks.
    view['metadata'] = {k:v for k,v in metadata.items() if k != 'Headers'}
    safe_document(view)
    if 'Headers' in metadata:
        require('Headers' not in {r['path'] for r in rows} and
                any(r['path'].startswith('Headers/') for r in rows), 'RUNTIME_HEADERS_DIRECTORY')
        safe_document('Headers')
        safe_document(metadata['Headers'])


def copy_runtime_metadata(source_fd, destination_fd, expected):
    stage = 'SOURCE_ACL'
    try:
        before = identity(os.fstat(source_fd)); _check_acl(source_fd)
        stage = 'DESTINATION_ACL'; _check_acl(destination_fd)
        stage = 'SOURCE_READ'; values = _read_xattrs(source_fd)
        stage = 'SOURCE_PIN'
        require(_metadata_digest(values) == expected, 'RUNTIME_COPY_METADATA_PARENT')
        stage = 'DESTINATION_READ'; initial = _read_xattrs(destination_fd)
        stage = 'DESTINATION_INITIAL'
        require(set(initial) <= {'com.apple.provenance'}, 'RUNTIME_COPY_METADATA_DESTINATION')
        stage = 'ATTRIBUTE_WRITE'
        for name, value in values.items():
            if name != 'com.apple.provenance': _write_xattr(destination_fd, name, value)
        stage = 'DESTINATION_VERIFY'
        result = _read_xattrs(destination_fd); _metadata_digest(result)
        require({k:v for k,v in result.items() if k!='com.apple.provenance'} ==
                {k:v for k,v in values.items() if k!='com.apple.provenance'}, 'RUNTIME_COPY_METADATA_CHANGED')
        stage = 'SOURCE_RECHECK'
        require(identity(os.fstat(source_fd)) == before and _read_xattrs(source_fd) == values, 'RUNTIME_COPY_METADATA_RACE')
        stage = 'DESTINATION_ACL_RECHECK'; _check_acl(destination_fd)
        return _metadata_digest(result)
    except RuntimeMetadataCopyError:
        raise
    except Exception as error:
        code = error.args[0] if type(error) is ValueError and error.args else None
        raise RuntimeMetadataCopyError(code, stage) from None


def verify_manifest(root, manifest, *, source_commit):
    """Complete static v2 admission; never executes the interpreter."""
    from deployment_contract import digest, canonical, PYTHON_VERSION
    required = {'schema','runtime_id','release_commit','runtime_root','interpreter',
        'interpreter_sha256','python_version','dependency_inventory','file_inventory',
        'platform_dependencies','content_hash'} | EXTENSION_FIELDS
    require(type(manifest) is dict and set(manifest) == required and
        manifest['schema'] == MANIFEST_SCHEMA and manifest['content_hash'] == digest(manifest), 'RUNTIME_MANIFEST_INVALID')
    require(manifest['release_commit'] == source_commit and type(source_commit) is str and
        re.fullmatch('[a-f0-9]{40}',source_commit) and manifest['runtime_root'] == root and
        manifest['python_version'] == PYTHON_VERSION, 'RUNTIME_MANIFEST_BINDING')
    require(manifest['interpreter'] == root + '/bin/python3.14', 'RUNTIME_INTERPRETER_INVALID')
    rows = manifest['file_inventory']
    require(type(rows) is list and all(r['path'] != 'runtime-manifest.json' for r in rows), 'RUNTIME_MANIFEST_RECURSION')
    matches = [r for r in rows if r['path'] == 'bin/python3.14']
    require(len(matches) == 1 and matches[0]['mode'] == 0o500 and
        matches[0]['sha256'] == manifest['interpreter_sha256'], 'RUNTIME_INTERPRETER_INVALID')
    raw = canonical(manifest)
    return verify_runtime_tree(root, rows + [dict(path='runtime-manifest.json',mode=0o400,
        size=len(raw),sha256=hashlib.sha256(raw).hexdigest())], approved_root=root, **extension(manifest))
