"""Versioned, archive-specific runtime tree policy. No execution or activation.

The generic evidence verifier remains link-free. This verifier observes only
physical entries; it never traverses a symlink, even an admitted one.
"""
import errno
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat

MANIFEST_SCHEMA = 'iios-immutable-python-runtime-v2'
DESCRIPTOR_SCHEMA = 'iios-observation-runtime-files-v2'
BUILD_SCHEMA = 'iios-production-runtime-build-input-v2'
COMPLETED_MANIFEST_SCHEMA = 'iios-completed-python-runtime-v3'
COMPLETED_BUILD_SCHEMA = 'iios-completed-runtime-build-input-v3'
COMPLETED_DESCRIPTOR_SCHEMA = 'iios-completed-runtime-files-v3'
COMPLETION_FIELDS = {'completion'}
MAX_FILES = 7000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
VENDOR = '70c5239ad2d62925d2947e46921d0ddd3d35be3d2f0a2d50db33da507dbcb419'
EXTENSION_FIELDS = {'layout_policy', 'layout_parent', 'metadata'}
PYTHON_VERSION = '3.14.7'
_DENIED_KEYS = frozenset({
    'apikey', 'api_key', 'key', 'secret', 'password', 'authorization', 'headers',
    'cookie', 'cookies', 'set-cookie', 'token', 'credential', 'credential_value',
    'access_token', 'refresh_token', 'apca-api-key-id', 'apca-api-secret-key',
    'x-api-key',
})
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


# This module is the assembly/static-verification boundary.  Keep its complete
# import graph in the standard library so the Python 3.9 build-control process
# never imports production services or their Python 3.14-only dependencies.
def require(condition, code):
    if not condition:
        raise ValueError(code)


def canonical(value):
    """Existing deployment-manifest byte contract."""
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True) + '\n').encode('ascii')


def _public_canonical(value):
    """Existing provider/public-document byte contract (NaN is forbidden)."""
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def content_hash(value):
    return hashlib.sha256(_public_canonical(value)).hexdigest()


def _digest(value):
    clean = dict(value) if isinstance(value, dict) else value
    if isinstance(clean, dict):
        clean.pop('content_hash', None)
    return hashlib.sha256(canonical(clean)).hexdigest()


def _safe_document(value, serialized=None):
    """Provider-equivalent public JSON validation without application imports."""
    if serialized is None:
        serialized = set()
    if isinstance(value, dict):
        for key, child in value.items():
            require(isinstance(key, str) and key.lower() not in _DENIED_KEYS,
                    'SENSITIVE_DOCUMENT_REJECTED')
            _safe_document(child, serialized)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _safe_document(child, serialized)
    elif isinstance(value, str):
        require(re.search(r'(?i)(bearer\s|api[_-]?key[=:]|password[=:]|'
                          r'[?&](token|key)=|-----BEGIN .*PRIVATE KEY)', value) is None,
                'SENSITIVE_DOCUMENT_REJECTED')
    else:
        require(value is None or type(value) in (int, float, bool),
                'PUBLIC_JSON_REQUIRED')
    primitive = type(value) in (str, int, float, bool, type(None))
    key = (type(value), value) if primitive else None
    if not primitive or key not in serialized:
        _public_canonical(value)
        if primitive and len(serialized) < 1024:
            serialized.add(key)


def path_parts(value, *, absolute=False):
    require(type(value) is str and '\x00' not in value, 'EVIDENCE_PATH')
    path = PurePosixPath(value)
    require(path.is_absolute() == absolute and str(path) == value and
            '..' not in path.parts and value not in ('', '.', '/'), 'EVIDENCE_PATH')
    parts = path.parts[1:] if absolute else path.parts
    require(len(parts) <= 32, 'EVIDENCE_PATH_DEPTH')
    return parts


def identity(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, value.st_mode, value.st_uid, value.st_nlink)


def open_root(root, approved_root):
    require(type(root) is str and root == approved_root, 'EVIDENCE_ROOT_NOT_APPROVED')
    parts = path_parts(root, absolute=True)
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        observed = os.fstat(descriptor)
        require(observed.st_uid == os.getuid() and not observed.st_mode & 0o222,
                'EVIDENCE_ROOT_MODE')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


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
    require(type(document) is dict, 'RUNTIME_DOCUMENT_SCHEMA')
    schema = document.get('schema')
    if schema not in (BUILD_SCHEMA, MANIFEST_SCHEMA, DESCRIPTOR_SCHEMA, COMPLETED_BUILD_SCHEMA, COMPLETED_MANIFEST_SCHEMA, COMPLETED_DESCRIPTOR_SCHEMA):
        _safe_document(document)
        return
    links = validate_layout_policy(document['layout_policy'], document['layout_parent'])
    rows = document['file_inventory'] if schema in (MANIFEST_SCHEMA, COMPLETED_MANIFEST_SCHEMA) else document['files']
    metadata = document['metadata']
    if schema == MANIFEST_SCHEMA:
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
    if schema == COMPLETED_DESCRIPTOR_SCHEMA:
        require(document['completed_manifest'].get('schema')==COMPLETED_MANIFEST_SCHEMA,'RUNTIME_COMPLETED_DESCRIPTOR')
        safe_runtime_document(document['completed_manifest'])
        del view['completed_manifest']
    # Only the exact root directory key collides with provider field names.
    # All other metadata keys retain the original sensitive-key checks.
    view['metadata'] = {k:v for k,v in metadata.items() if k != 'Headers'}
    _safe_document(view)
    if 'Headers' in metadata:
        require('Headers' not in {r['path'] for r in rows} and
                any(r['path'].startswith('Headers/') for r in rows), 'RUNTIME_HEADERS_DIRECTORY')
        _safe_document('Headers')
        _safe_document(metadata['Headers'])


def safe_runtime_envelope(document):
    """Exact existing runtime-bearing envelopes, never a provider validator."""
    require(type(document) is dict, 'RUNTIME_ENVELOPE_SCHEMA')
    schema = document.get('schema')
    view = dict(document)
    if schema == 'iios-disposable-observation-roles-v2':
        runtime = document['runtime']
        require(runtime.get('schema') in (DESCRIPTOR_SCHEMA, COMPLETED_DESCRIPTOR_SCHEMA), 'RUNTIME_ENVELOPE_VERSION')
        safe_runtime_document(runtime)
        del view['runtime']
    elif schema == 'iios-observation-launch-v2':
        runtime = dict(schema=DESCRIPTOR_SCHEMA, files=document['inventories']['runtime'],
                       **extension(document))
        safe_runtime_document(runtime)
        del view['metadata']
    elif schema == 'iios-truth-observation-execution-v1':
        runtime = document['preflight']['runtime_manifest']
        safe_runtime_document(runtime)
        view['preflight'] = dict(document['preflight'])
        del view['preflight']['runtime_manifest']
    _safe_document(view)


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
    if manifest.get('schema') == COMPLETED_MANIFEST_SCHEMA:
        return verify_completed_manifest(root, manifest, source_commit=source_commit)
    required = {'schema','runtime_id','release_commit','runtime_root','interpreter',
        'interpreter_sha256','python_version','dependency_inventory','file_inventory',
        'platform_dependencies','content_hash'} | EXTENSION_FIELDS
    require(type(manifest) is dict and set(manifest) == required and
        manifest['schema'] == MANIFEST_SCHEMA and manifest['content_hash'] == _digest(manifest), 'RUNTIME_MANIFEST_INVALID')
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


def completed_paths(root):
    """Exact sibling names, validated lexically before any filesystem access."""
    _root(root, root)
    path = PurePosixPath(root)
    require(re.fullmatch('runtime-[a-z0-9-]{1,64}', path.name), 'RUNTIME_COMPLETED_NAME')
    return {kind: str(path.parent / (path.name + suffix)) for kind, suffix in (
        ('manifest', '.manifest.json'), ('envelope', '.envelope.json'))}


def validate_completion(value):
    """Structural pins, not a substitute for independent provenance review."""
    _safe_document(value)
    require(type(value) is dict and set(value) == {'dependency_lock_sha256',
        'bootstrap_acceptance_sha256','bootstrap_tree_sha256','vendor_distribution_sha256',
        'vendor_signature_receipt_sha256','assembly_seal_receipt_sha256','assembly_seal_kind',
        'host_contract','sealed_payload_sha256'}, 'RUNTIME_COMPLETION_SCHEMA')
    for key in set(value) - {'host_contract','assembly_seal_kind'}:
        require(type(value[key]) is str and re.fullmatch('[a-f0-9]{64}',value[key]), 'RUNTIME_COMPLETION_PIN')
    require(value['vendor_distribution_sha256'] == VENDOR and
        value['assembly_seal_kind'] == 'IIOS_ADHOC_RESOURCE_SEAL', 'RUNTIME_SIGNATURE_KIND')
    host=value['host_contract']
    require(type(host) is dict and set(host)=={'system','release','version','machine','uid','host_identity_sha256'} and
        host['system']=='Darwin' and host['machine']=='arm64' and type(host['uid']) is int and host['uid']>0 and
        type(host['host_identity_sha256']) is str and re.fullmatch('[a-f0-9]{64}',host['host_identity_sha256']),
        'RUNTIME_HOST_CONTRACT')
    for key in ('release','version'):
        require(type(host[key]) is str and 0<len(host[key])<=256 and
            all(32<=ord(c)<127 for c in host[key]), 'RUNTIME_HOST_CONTRACT')


def sealed_payload_parent(document):
    rows=document['file_inventory'] if 'file_inventory' in document else document['files']
    return content_hash(dict(files=rows, **extension(document)))


def completed_envelope(manifest):
    """One-way graph: seal -> payload; manifest -> seal; envelope -> manifest.

    No envelope digest is placed in the manifest or sealed runtime tree.
    The caller's independent canonical manifest pin binds completion claims.
    Native signature/provenance qualification remains a separate prerequisite.
    """
    validate_completion(manifest['completion'])
    return dict(schema='iios-completed-runtime-envelope-v1',source_commit=manifest['release_commit'],
        runtime_root=manifest['runtime_root'],manifest_sha256=hashlib.sha256(canonical(manifest)).hexdigest(),
        completion=manifest['completion'],production_qualified=False)


def _external_bytes(path, expected):
    """No-follow, bounded, owner-only immutable sibling with race checks."""
    _root(path,path);parts=path_parts(path,absolute=True)
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
        parent=identity(os.fstat(fd))
        require(os.fstat(fd).st_uid==os.getuid() and not os.fstat(fd).st_mode&0o077,'RUNTIME_EXTERNAL_PARENT')
        stream=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(stream)
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and
                before.st_nlink==1 and stat.S_IMODE(before.st_mode)==0o400 and
                before.st_size==len(expected)<=MAX_METADATA_BYTES,'RUNTIME_EXTERNAL_IDENTITY')
            data=bytearray()
            while len(data)<len(expected):
                chunk=os.read(stream,min(65536,len(expected)-len(data)))
                require(bool(chunk),'RUNTIME_EXTERNAL_SHORT');data.extend(chunk)
            require(not os.read(stream,1) and bytes(data)==expected,'RUNTIME_EXTERNAL_CONTENT')
            require(identity(os.fstat(stream))==identity(before)==identity(os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)) and
                identity(os.fstat(fd))==parent,'RUNTIME_EXTERNAL_RACE')
        finally:os.close(stream)
    finally:os.close(fd)


def verify_completed_manifest(root, manifest, *, source_commit):
    required={'schema','runtime_id','release_commit','runtime_root','interpreter','interpreter_sha256',
        'python_version','dependency_inventory','file_inventory','platform_dependencies','content_hash'}|EXTENSION_FIELDS|COMPLETION_FIELDS
    require(type(manifest) is dict and set(manifest)==required and
        manifest['schema']==COMPLETED_MANIFEST_SCHEMA and manifest['content_hash']==_digest(manifest),
        'RUNTIME_COMPLETED_SCHEMA')
    require(type(source_commit) is str and re.fullmatch('[a-f0-9]{40}',source_commit) and
        manifest['release_commit']==source_commit and manifest['runtime_root']==root and
        manifest['python_version']==PYTHON_VERSION,'RUNTIME_MANIFEST_BINDING')
    paths=completed_paths(root);safe_runtime_document(manifest);validate_completion(manifest['completion'])
    rows=manifest['file_inventory'];names=[r['path'] for r in rows]
    require(names==sorted(names) and len(names)==len(set(names)) and
        not any(n in names for n in ('runtime-manifest.json',PurePosixPath(paths['manifest']).name,
            PurePosixPath(paths['envelope']).name)), 'RUNTIME_COMPLETED_RECURSION_OR_ORDER')
    require({'Python','_CodeSignature/CodeResources','bin/python3.14'}<=set(names), 'RUNTIME_SEAL_FILES')
    require(manifest['completion']['sealed_payload_sha256']==sealed_payload_parent(manifest),'RUNTIME_SEALED_PAYLOAD')
    executable=next(r for r in rows if r['path']=='bin/python3.14')
    require(manifest['interpreter']==root+'/bin/python3.14' and executable['mode']==0o500 and
        executable['sha256']==manifest['interpreter_sha256'],'RUNTIME_INTERPRETER_INVALID')
    raw=canonical(manifest);envelope=canonical(completed_envelope(manifest))
    # Preserve former aggregate capacity: external records still consume limits.
    require(len(rows)+2<=MAX_FILES and sum(r['size'] for r in rows)+len(raw)+len(envelope)+
        len(canonical(manifest['metadata']))<=MAX_TOTAL_BYTES,'RUNTIME_COMPLETED_TOTAL_BOUND')
    identities=verify_runtime_tree(root,rows,approved_root=root,**extension(manifest))
    _external_bytes(paths['manifest'],raw);_external_bytes(paths['envelope'],envelope)
    return identities


def verify_completed_descriptor(document, *, source_commit):
    require(document.get('schema')==COMPLETED_DESCRIPTOR_SCHEMA,'RUNTIME_COMPLETED_DESCRIPTOR')
    manifest=document['completed_manifest']
    require(manifest['schema']==COMPLETED_MANIFEST_SCHEMA and manifest['runtime_root']==document['root'] and
        manifest['file_inventory']==document['files'] and extension(manifest)==extension(document) and
        manifest['interpreter']==document['root']+'/'+document['interpreter'],'RUNTIME_COMPLETED_DESCRIPTOR_BINDING')
    return verify_completed_manifest(document['root'],manifest,source_commit=source_commit)
