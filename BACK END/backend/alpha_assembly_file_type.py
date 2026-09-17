"""Offline derived-image admission and bounded, non-authorizing failure evidence."""
import hashlib
import struct

MARKERS = {'MACH_O_BUNDLE': b'bundle',
           'MACH_O_DYLIB': b'dynamically linked shared library'}
PATHS = frozenset((
    'lib/python3.14/site-packages/charset_normalizer/cd.cpython-314-darwin.so',
    'lib/python3.14/site-packages/charset_normalizer/md.cpython-314-darwin.so',
    'lib/python3.14/site-packages/google/_upb/_message.abi3.so',
    'lib/python3.14/site-packages/grpc/_cython/cygrpc.cpython-314-darwin.so',
))
LIMIT = 32768


class DerivedFileTypeError(ValueError):
    def __init__(self, evidence):
        super().__init__('DERIVED_FILE_TYPE')
        self.file_type_failure = evidence


def binary_category(raw):
    """Accept exactly the reviewed universal x86_64/arm64 Mach-O slice order."""
    if type(raw) is not bytes or len(raw) < 48 or raw[:4] != b'\xca\xfe\xba\xbe':
        return 'INVALID_UNIVERSAL'
    if struct.unpack_from('>I', raw, 4)[0] != 2:
        return 'INVALID_UNIVERSAL'
    kinds = []
    end = 48
    for i, cpu in enumerate((0x1000007, 0x100000c)):
        observed, subtype, offset, size, alignment = struct.unpack_from('>IIIII', raw, 8+20*i)
        if (observed != cpu or alignment > 31 or offset % (1 << alignment) or
                offset < end or size < 32 or offset+size > len(raw)):
            return 'INVALID_UNIVERSAL'
        end = offset+size
        if raw[offset:offset+4] != b'\xcf\xfa\xed\xfe':
            return 'INVALID_UNIVERSAL'
        if struct.unpack_from('<I', raw, offset+4)[0] != cpu:
            return 'INVALID_UNIVERSAL'
        kinds.append({8: 'MACH_O_BUNDLE', 6: 'MACH_O_DYLIB'}.get(
            struct.unpack_from('<I', raw, offset+12)[0], 'UNKNOWN'))
    return kinds[0] if kinds[0] == kinds[1] else 'MIXED_SLICES'


def validate_file_type(path, expected, returncode, stdout, stderr, raw, expected_sha256):
    """Keep fixed native-result categories, never raw tool output or arbitrary paths."""
    valid_output = (type(stdout) is bytes and type(stderr) is bytes and
                    len(stdout) <= LIMIT and len(stderr) <= LIMIT)
    text = stdout if valid_output else b''
    categories = [name for name, marker in MARKERS.items() if marker in text]
    observed = binary_category(raw)
    projected = {'exit_category': 'ZERO' if type(returncode) is int and returncode == 0 else 'NONZERO_OR_INVALID',
                 'output_category': 'BOUNDED' if valid_output else 'INVALID_OR_OVERSIZE',
                 'universal_marker': b'Mach-O universal binary' in text,
                 'type_category': categories[0] if len(categories) == 1 else 'AMBIGUOUS_OR_UNKNOWN',
                 'stderr_category': 'EMPTY' if stderr == b'' else 'PRESENT_OR_INVALID'}
    hash_matches = (type(raw) is bytes and type(expected_sha256) is str and
                    len(expected_sha256) == 64 and hashlib.sha256(raw).hexdigest() == expected_sha256)
    evidence = {'path': path if type(path) is str and path in PATHS else 'UNADMITTED_PATH',
                'expected_category': expected if type(expected) is str and expected in MARKERS else 'UNKNOWN',
                'observed_category': observed, 'native_file_result': projected,
                'bytes_parent': 'MATCH' if hash_matches else 'MISMATCH'}
    if not (evidence['path'] != 'UNADMITTED_PATH' and evidence['expected_category'] != 'UNKNOWN' and
            hash_matches and projected['exit_category'] == 'ZERO' and valid_output and
            stderr == b'' and projected['universal_marker'] and categories == [expected] and observed == expected):
        raise DerivedFileTypeError(evidence)
    return evidence


def inspect_file_type(tool, path, relative, expected, deadline, pins, expected_sha256):
    """Bind the native query to stable no-follow bytes and an independent parent hash."""
    import os
    import stat
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)
    if relative not in PATHS:
        return validate_file_type(relative, expected, 1, b'', b'', b'', expected_sha256)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 64*1024*1024:
            raise ValueError('DERIVED_FILE_IDENTITY')
        chunks = [];left = before.st_size
        while left:
            chunk = os.read(fd, min(left, 65536))
            if not chunk:raise ValueError('DERIVED_FILE_SHORT')
            chunks.append(chunk);left -= len(chunk)
        raw = b''.join(chunks)
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            return validate_file_type(relative, expected, 1, b'', b'', raw, expected_sha256)
        rc, out, err = tool(['/usr/bin/file', '-b', str(path)], deadline, pins)
        if identity(before) != identity(os.fstat(fd)) or identity(before) != identity(os.stat(path, follow_symlinks=False)):
            raise ValueError('DERIVED_FILE_MUTATION')
        return validate_file_type(relative, expected, rc, out, err, raw, expected_sha256)
    finally:
        os.close(fd)
