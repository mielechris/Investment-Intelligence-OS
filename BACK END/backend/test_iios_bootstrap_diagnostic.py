"""Offline mutations of complete ordered discovery scans and Mach-O mappings."""
import copy
import struct
import unittest
from iios_bootstrap_diagnostic import mapped_header, review_scans

class DiscoveryTests(unittest.TestCase):
    def fixture(self):
        row=dict(index=0,path='/synthetic/image',uuid='a'*32,address=4096,slide=0,
                 file_type=2,kind='PRIVATE_SEALED',backing={'sha256':'b'*64,'size':128},
                 header_sha256='c'*64,segments=[{'address':4096}])
        catalog={row['path']:{k:row[k] for k in ('uuid','kind','backing')}}
        return [row],catalog
    def test_measured_count_is_not_historical_count(self):
        rows,catalog=self.fixture()
        self.assertEqual(review_scans(rows,copy.deepcopy(rows),catalog,['d'*32]*2,'d'*32),1)
    def test_missing_additional_substituted_and_reordered_scan_rejected(self):
        rows,catalog=self.fixture();second=copy.deepcopy(rows[0]);second.update(index=1,path='/synthetic/second',address=8192)
        rows.append(second);catalog[second['path']]=catalog[rows[0]['path']]
        for mutation in (rows[:1],rows+[second],list(reversed(rows))):
            with self.assertRaises(ValueError):review_scans(rows,mutation,catalog,['d'*32]*2,'d'*32)
        changed=copy.deepcopy(rows);changed[0]['uuid']='e'*32
        with self.assertRaises(ValueError):review_scans(rows,changed,catalog,['d'*32]*2,'d'*32)
    def test_independent_catalog_substitution_and_unknown_identity_rejected(self):
        rows,catalog=self.fixture()
        for field,value in [('path','/synthetic/unknown'),('uuid','e'*32),('kind','APPLE_SIGNED_CACHE'),('backing',{})]:
            changed=copy.deepcopy(rows);changed[0][field]=value
            with self.assertRaises(ValueError):review_scans(changed,changed,catalog,['d'*32]*2,'d'*32)
    def test_duplicate_path_and_mapping_rejected(self):
        rows,catalog=self.fixture();duplicate=copy.deepcopy(rows[0]);duplicate['index']=1;rows.append(duplicate)
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):review_scans(rows,rows,catalog,['d'*32]*2,'d'*32)
        rows[1]['path']='/synthetic/alias';catalog[rows[1]['path']]=catalog[rows[0]['path']]
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):review_scans(rows,rows,catalog,['d'*32]*2,'d'*32)
    def test_final_reference_cannot_admit_extra_missing_or_reordered(self):
        rows,catalog=self.fixture();expected=[tuple(rows[0][k] for k in ('path','uuid','kind','backing'))]
        self.assertEqual(review_scans(rows,rows,catalog,['d'*32]*2,'d'*32,expected),1)
        for wrong in ([],expected+expected,list(reversed(expected+[("different",)*4]))):
            with self.assertRaises(ValueError):review_scans(rows,rows,catalog,['d'*32]*2,'d'*32,wrong)
    def test_cache_changed_and_count_bounds(self):
        rows,catalog=self.fixture()
        for caches in (['d'*32,'e'*32],['d'*32]):
            with self.assertRaises(ValueError):review_scans(rows,rows,catalog,caches,'d'*32)
        with self.assertRaises(ValueError):review_scans([],[],{},['d'*32]*2,'d'*32)
    def header(self):
        seg=struct.pack('<II16sQQQQiiII',0x19,72,b'__TEXT',4096,4096,0,4096,5,5,0,0)
        uid=struct.pack('<II16s',0x1b,24,bytes.fromhex('a'*32))
        return struct.pack('<8I',0xfeedfacf,0x100000c,0,2,2,96,0,0)+seg+uid
    def test_complete_header_mapping(self):
        value=mapped_header(self.header(),8192,4096)
        self.assertEqual(value['uuid'],'a'*32);self.assertEqual(value['segments'][0]['address'],8192)
    def test_truncation_arch_uuid_and_mapping_reject(self):
        raw=self.header()
        for bad in (raw[:31],raw[:-1],b'bad!'+raw[4:],raw[:-16]+bytes(16)):
            with self.assertRaises(ValueError):mapped_header(bad,4096,0)
        with self.assertRaises(ValueError):mapped_header(raw,8192,0)

    def test_dyld_file_type_requires_explicit_os_role(self):
        raw=bytearray(self.header());struct.pack_into('<I',raw,12,7)
        with self.assertRaises(ValueError):mapped_header(bytes(raw),4096,0)
        self.assertEqual(mapped_header(bytes(raw),4096,0,allow_dyld=True)['file_type'],7)
    def test_dyld_kind_cannot_substitute_for_private_executable(self):
        rows,catalog=self.fixture();rows[0]['file_type']=7
        with self.assertRaisesRegex(ValueError,'IMAGE_KIND'):review_scans(rows,rows,catalog,['d'*32]*2,'d'*32)


class AuditPreludeTests(unittest.TestCase):
    def fixture(self):
        import ast,os
        from pathlib import Path
        script=Path(__file__).resolve().parents[2]/'scripts/prepare_bootstrap_diagnostic.py'
        tree=ast.parse(script.read_bytes())
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='prelude' for t in n.targets))
        text=assignment.value.func.value.value
        generated=ast.parse(text.replace('BINDING_LITERAL','{}'))
        functions=[n for n in generated.body if isinstance(n,ast.FunctionDef)]
        scope={'os':os,'_READS':frozenset(['/synthetic/sealed.py']),'_DISCOVERY':{'/synthetic/stdlib':('a.py','b.py')}}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'reviewed-audit-prelude','exec'),scope)
        return scope
    def test_network_process_signal_and_enumeration_denied(self):
        audit=self.fixture()['_audit']
        for event,args in [('socket.connect',()),('socket.__new__',()),('subprocess.Popen',()),('os.fork',()),('os.kill',()),('os.listdir',()),('os.scandir',())]:
            with self.assertRaises(PermissionError):audit(event,args)
    def test_only_exact_pinned_read_and_no_writes(self):
        import os
        audit=self.fixture()['_audit'];audit('open',('/synthetic/sealed.py','r',0))
        for args in [('/synthetic/other.py','r',0),('/synthetic/sealed.py','w',os.O_WRONLY),(99,'r',0),('/synthetic/sealed.py','r',os.O_APPEND)]:
            with self.assertRaises(PermissionError):audit('open',args)
    def test_only_dyld_symbols_and_bounded_memory_reads(self):
        audit=self.fixture()['_audit'];audit('ctypes.dlopen',(None,));audit('ctypes.dlsym',(None,'_dyld_image_count'));audit('ctypes.string_at',(4096,32))
        for event,args in [('ctypes.dlopen',('/synthetic/library',)),('ctypes.dlsym',(None,'connect')),('ctypes.string_at',(0,32)),('ctypes.string_at',(4096,65569))]:
            with self.assertRaises(PermissionError):audit(event,args)
    def test_import_discovery_uses_only_sealed_directory_members(self):
        from types import SimpleNamespace
        cache=self.fixture()['_sealed_cache'];finder=SimpleNamespace(path='/synthetic/stdlib');cache(finder)
        self.assertEqual(finder._path_cache,{'a.py','b.py'})
        with self.assertRaises(PermissionError):cache(SimpleNamespace(path='/synthetic/unpinned'))


class ProfileBoundaryTests(unittest.TestCase):
    def test_root_exception_is_literal_and_restrictions_remain(self):
        import ast
        from pathlib import Path
        tree=ast.parse((Path(__file__).resolve().parents[2]/'scripts/prepare_bootstrap_diagnostic.py').read_bytes())
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='profile' for t in n.targets))
        node=assignment.value
        while isinstance(node,ast.Call):node=node.func.value
        profile=node.value
        self.assertIn('(allow file-read-data (literal "/"))',profile)
        self.assertNotIn('(subpath "/")',profile)
        for rule in ('(deny network*)','(deny process-fork)','(deny process-exec)','(deny file-write*)','(deny file-read-data)'):
            self.assertIn(rule,profile)
        self.assertLess(profile.index('(deny file-read-data)'),profile.index('(allow file-read-data (literal "/"))'))


class CacheHeaderTests(unittest.TestCase):
    def fixture(self):
        import hashlib
        raw=bytearray(DiscoveryTests().header())
        struct.pack_into('<Q',raw,72,16384)
        raw=bytes(raw)
        return raw,dict(address=4096,file_offset=16384,sha256=hashlib.sha256(raw).hexdigest(),cache_file='/synthetic/cache')
    def test_cache_offset_requires_exact_independent_pin(self):
        raw,pin=self.fixture()
        with self.assertRaisesRegex(ValueError,'HEADER_MAPPING'):mapped_header(raw,4096,0)
        self.assertEqual(mapped_header(raw,8192,4096,cache_pin=pin)['segments'][0]['file_offset'],16384)
    def test_cache_pin_mutations_fail_closed(self):
        raw,pin=self.fixture()
        for key,value in [('address',4097),('file_offset',16385),('sha256','0'*64)]:
            with self.assertRaises(ValueError):mapped_header(raw,8192,4096,cache_pin={**pin,key:value})
    def test_private_zero_offset_remains_required(self):
        raw=DiscoveryTests().header()
        self.assertEqual(mapped_header(raw,4096,0)['segments'][0]['file_offset'],0)


class RebuiltReferenceTests(unittest.TestCase):
    def fixture(self):
        from iios_bootstrap_diagnostic import reference_rows
        rows,_=DiscoveryTests().fixture()
        origins=[dict(module='sample',path='/synthetic/sample.py',sha256='e'*64)]
        ref=dict(schema='IIOS_REBUILT_BOOTSTRAP_IMAGE_REFERENCE_V1',scope='REBUILT_BOOTSTRAP_IDENTITY_ONLY',historical_cleanup='NOT_ESTABLISHED',historical_reference_recovered=False,bootstrap_accepted=False,mapped_memory_integrity='UNVERIFIED',boot_attestation='UNRESOLVED',runtime_root='/synthetic',boot_session_uuid='boot',imports=['sample'],cache_uuid='d'*32,expected_count=1,ordered_rows=reference_rows(rows),module_origins=origins)
        return ref,rows,origins
    def verify(self,ref,rows,origins,**kw):
        from iios_bootstrap_diagnostic import verify_reference
        args=dict(runtime_root='/synthetic',boot='boot',imports=['sample'],cache_uuid='d'*32);args.update(kw)
        return verify_reference(ref,rows,origins,**args)
    def test_exact_reference_passes_without_acceptance_claim(self):
        ref,rows,origins=self.fixture();self.assertTrue(self.verify(ref,rows,origins));self.assertFalse(ref['bootstrap_accepted'])
    def test_aslr_observations_can_change_without_identity_change(self):
        ref,rows,origins=self.fixture();rows[0]['address']+=4096;rows[0]['slide']+=4096;rows[0]['segments'][0]['address']+=4096
        self.assertTrue(self.verify(ref,rows,origins))
    def test_missing_extra_duplicate_rejected(self):
        ref,rows,origins=self.fixture()
        for changed in ([],rows+rows):
            with self.assertRaises(ValueError):self.verify(ref,changed,origins)
    def test_substituted_header_uuid_backing_mapping_rejected(self):
        ref,rows,origins=self.fixture()
        for key,value in [('uuid','b'*32),('header_sha256','e'*64),('backing',{}),('segments',[{'address':4096,'vmaddr':999}])]:
            changed=copy.deepcopy(rows);changed[0][key]=value
            with self.assertRaises(ValueError):self.verify(ref,changed,origins)
    def test_reordered_rows_rejected(self):
        from iios_bootstrap_diagnostic import reference_rows
        ref,rows,origins=self.fixture();second=copy.deepcopy(rows[0]);second.update(index=1,path='/synthetic/second',address=8192);rows.append(second);ref.update(expected_count=2,ordered_rows=reference_rows(rows))
        with self.assertRaises(ValueError):self.verify(ref,list(reversed(rows)),origins)
    def test_scope_boot_runtime_import_cache_rejected(self):
        ref,rows,origins=self.fixture()
        for kw in ({'boot':'changed'},{'runtime_root':'/elsewhere'},{'imports':['extra']},{'cache_uuid':'e'*32}):
            with self.assertRaises(ValueError):self.verify(ref,rows,origins,**kw)
        ref['schema']='SCOPED_BOOTSTRAP_IMAGE_REFERENCE_V1'
        with self.assertRaises(ValueError):self.verify(ref,rows,origins)
    def test_changed_module_origins_rejected(self):
        ref,rows,origins=self.fixture()
        with self.assertRaises(ValueError):self.verify(ref,rows,[])
        self.assertTrue(self.verify(ref,rows,[dict(module='__main__',path='/new/entry.py',sha256='f'*64)]+origins))
    def test_historical_cleanup_and_claims_cannot_be_promoted(self):
        ref,rows,origins=self.fixture()
        for key,value in [('historical_cleanup','VERIFIED'),('historical_reference_recovered',True),('bootstrap_accepted',True),('mapped_memory_integrity','VERIFIED'),('boot_attestation','VERIFIED')]:
            with self.assertRaises(ValueError):self.verify({**ref,key:value},rows,origins)
