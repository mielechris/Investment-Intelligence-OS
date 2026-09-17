import hashlib
import struct
import unittest
from alpha_assembly_file_type import validate_file_type, DerivedFileTypeError, PATHS


def image(kinds=(8, 8), cpus=(0x1000007, 0x100000c)):
    raw = bytearray(112);raw[:8] = struct.pack('>II', 0xcafebabe, 2)
    for i, (cpu, kind) in enumerate(zip(cpus, kinds)):
        offset = 48+32*i
        struct.pack_into('>IIIII', raw, 8+20*i, cpu, 0, offset, 32, 0)
        struct.pack_into('<IIIIIIII', raw, offset, 0xfeedfacf, cpu, 0, kind, 0, 0, 0, 0)
    return bytes(raw)


class FileTypeTests(unittest.TestCase):
    def call(self, kind='MACH_O_BUNDLE', raw=None, out=None, **overrides):
        raw = image() if raw is None else raw
        args = dict(path=sorted(PATHS)[0], expected=kind, returncode=0,
                    stdout=out if out is not None else b'Mach-O universal binary: bundle',
                    stderr=b'', raw=raw, expected_sha256=hashlib.sha256(raw).hexdigest())
        args.update(overrides)
        return validate_file_type(**args)

    def reject(self, **args):
        with self.assertRaises(DerivedFileTypeError) as result:self.call(**args)
        return result.exception.file_type_failure

    def test_bundle(self):self.assertEqual(self.call()['observed_category'], 'MACH_O_BUNDLE')
    def test_dylib(self):self.assertEqual(self.call('MACH_O_DYLIB', image((6,6)), b'Mach-O universal binary: dynamically linked shared library')['observed_category'], 'MACH_O_DYLIB')
    def test_swapped_policy(self):self.reject(kind='MACH_O_DYLIB')
    def test_swapped_output(self):self.reject(out=b'Mach-O universal binary: dynamically linked shared library')
    def test_swapped_bytes(self):self.reject(raw=image((6,6)))
    def test_unknown(self):self.assertEqual(self.reject(kind='UNTRUSTED')['expected_category'], 'UNKNOWN')
    def test_old_short_name(self):self.reject(kind='BUNDLE')
    def test_unhashable_kind(self):self.reject(kind=[])
    def test_altered_bytes(self):self.assertEqual(self.reject(expected_sha256='0'*64)['bytes_parent'], 'MISMATCH')
    def test_mixed_slices(self):self.assertEqual(self.reject(raw=image((8,6)))['observed_category'], 'MIXED_SLICES')
    def test_slice_order(self):self.reject(raw=image(cpus=(0x100000c,0x1000007)))
    def test_unknown_slice_type(self):self.reject(raw=image((2,2)))
    def test_thin(self):self.reject(raw=image()[48:])
    def test_truncation(self):
        for n in (0,4,8,47,48,80,111):self.reject(raw=image()[:n])
    def test_overlapping_slices(self):
        raw=bytearray(image());struct.pack_into('>I',raw,36,48);self.reject(raw=bytes(raw))
    def test_fat_inner_cpu_mismatch(self):
        raw=bytearray(image());struct.pack_into('<I',raw,52,0x100000c);self.reject(raw=bytes(raw))
    def test_missing_universal_marker(self):self.reject(out=b'Mach-O 64-bit bundle')
    def test_ambiguous_native_type(self):self.reject(out=b'Mach-O universal binary: bundle dynamically linked shared library')
    def test_oversize(self):self.reject(out=b'x'*32769)
    def test_failed_tool(self):self.reject(returncode=1)
    def test_boolean_returncode(self):self.reject(returncode=False)
    def test_stderr(self):self.reject(stderr=b'untrusted value')
    def test_unadmitted_path(self):self.assertEqual(self.reject(path='../untrusted')['path'],'UNADMITTED_PATH')
    def test_sanitized_failure(self):
        result=self.reject(out=b'private value',stderr=b'another private value')
        self.assertNotIn('private value',str(result));self.assertEqual(set(result),{'path','expected_category','observed_category','native_file_result','bytes_parent'})




class FileBindingTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'image';self.path.write_bytes(image());self.hash=hashlib.sha256(image()).hexdigest();self.calls=[]
    def tearDown(self):self.tmp.cleanup()
    def tool(self,*args):self.calls.append(args);return 0,b'Mach-O universal binary: bundle',b''
    def check(self):
        from alpha_assembly_file_type import inspect_file_type
        return inspect_file_type(self.tool,self.path,sorted(PATHS)[0],'MACH_O_BUNDLE',1,{},self.hash)
    def test_stable_file(self):self.assertEqual(self.check()['bytes_parent'],'MATCH')
    def test_changed_bytes_before_tool(self):
        self.path.write_bytes(image((6,6)))
        with self.assertRaises(DerivedFileTypeError):self.check()
        self.assertEqual(self.calls,[])
    def test_mutation_during_native_query(self):
        def mutate(*args):self.path.write_bytes(image((6,6)));return 0,b'Mach-O universal binary: bundle',b''
        self.tool=mutate
        with self.assertRaisesRegex(ValueError,'DERIVED_FILE_MUTATION'):self.check()
    def test_replacement_during_query(self):
        def replace(*args):
            other=self.path.with_name('replacement');other.write_bytes(image());other.replace(self.path);return 0,b'Mach-O universal binary: bundle',b''
        self.tool=replace
        with self.assertRaisesRegex(ValueError,'DERIVED_FILE_MUTATION'):self.check()
    def test_symlink_rejected(self):
        link=self.path.with_name('link');link.symlink_to(self.path);self.path=link
        with self.assertRaises(OSError):self.check()

if __name__ == '__main__':unittest.main()
