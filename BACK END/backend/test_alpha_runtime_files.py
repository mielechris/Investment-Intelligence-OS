"""Offline framework policy tests. Native xattr/ACL effects are substituted."""
import ast
import builtins
from copy import deepcopy
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import errno
import json
import stat

import alpha_runtime_files as rf
from alpha_session_evidence import verify_files
from provider_gateway_contract import content_hash


class MetadataCopyDiagnosticsTests(unittest.TestCase):
    def test_syscall_categories_are_bounded_and_unattributed(self):
        for number, category in ((errno.EACCES,'ACCESS_DENIED_UNATTRIBUTED'),
            (errno.EPERM,'OPERATION_DENIED_UNATTRIBUTED'),(errno.ENOTSUP,'UNSUPPORTED'),
            (errno.EROFS,'READ_ONLY_FILESYSTEM'),(1234,'UNKNOWN')):
            c=Mock();c.get_errno.return_value=number
            lib=Mock();lib.fsetxattr.return_value=-1
            with patch.object(rf,'_darwin',return_value=(c,lib)):
                with self.assertRaises(rf.RuntimeMetadataCopyError) as caught:
                    rf._write_xattr(44,'com.apple.cs.CodeSignature',b'OPAQUE-DO-NOT-RETAIN')
            detail=caught.exception.diagnostic
            self.assertEqual(detail['predicate'],'RUNTIME_XATTR_COPY')
            self.assertEqual(detail['result_category'],category)
            self.assertEqual(detail['errno'],number)
            self.assertNotIn('OPAQUE',json.dumps(detail))
            c.set_errno.assert_called_once_with(0)
            self.assertEqual(lib.fsetxattr.call_args.args[-2:],(0,0))

    def test_success_and_malformed_syscall_result(self):
        c=Mock();lib=Mock();lib.fsetxattr.return_value=0
        with patch.object(rf,'_darwin',return_value=(c,lib)):
            rf._write_xattr(44,'com.apple.cs.CodeDirectory',b'x')
            lib.fsetxattr.return_value=17;c.get_errno.return_value=999999
            with self.assertRaises(rf.RuntimeMetadataCopyError) as caught:
                rf._write_xattr(44,'com.apple.cs.CodeDirectory',b'x')
        self.assertEqual(caught.exception.diagnostic['result'],'UNKNOWN')
        self.assertIsNone(caught.exception.diagnostic['errno'])

    def test_diagnostics_reject_arbitrary_messages_paths_and_types(self):
        for value in ('/private/secret/token',{},[],None):
            detail=rf.RuntimeMetadataCopyError(value,value,attribute=value,error_number=value,result=value).diagnostic
            self.assertEqual(detail['predicate'],'RUNTIME_METADATA_UNKNOWN')
            self.assertEqual(detail['stage'],'UNKNOWN');self.assertEqual(detail['attribute'],'UNKNOWN')
            self.assertNotIn('/private',json.dumps(detail))

    def test_missing_and_substituted_destination_attributes(self):
        source={'com.apple.cs.CodeDirectory':b'first','com.apple.cs.CodeSignature':b'second'}
        for destination in ({},{'com.apple.cs.CodeDirectory':b'first'},
                            dict(source,**{'com.apple.cs.CodeSignature':b'changed'})):
            with patch.object(rf,'_read_xattrs',side_effect=[source,{},destination]),\
                patch.object(rf,'_check_acl'),patch.object(rf,'_write_xattr'),\
                patch.object(rf,'identity',return_value=()),patch.object(rf.os,'fstat'):
                with self.assertRaises(rf.RuntimeMetadataCopyError) as caught:
                    rf.copy_runtime_metadata(1,2,rf._metadata_digest(source))
            self.assertEqual(caught.exception.diagnostic['stage'],'DESTINATION_VERIFY')
            self.assertEqual(str(caught.exception),'RUNTIME_COPY_METADATA_CHANGED')

    def test_partial_copy_stops_without_retry_or_removal(self):
        source={'com.apple.cs.CodeDirectory':b'first','com.apple.cs.CodeSignature':b'second'}
        dest={};calls=[]
        def write(fd,name,value):
            calls.append(name)
            if len(calls)==2:raise rf.RuntimeMetadataCopyError('RUNTIME_XATTR_COPY','ATTRIBUTE_WRITE',
                attribute=name,result=-1,error_number=errno.ENOTSUP)
            dest[name]=value
        with patch.object(rf,'_read_xattrs',side_effect=lambda fd:dict(source if fd==1 else dest)),\
            patch.object(rf,'_write_xattr',side_effect=write),patch.object(rf,'_check_acl'),\
            patch.object(rf,'identity',return_value=()),patch.object(rf.os,'fstat'):
            with self.assertRaises(rf.RuntimeMetadataCopyError) as caught:
                rf.copy_runtime_metadata(1,2,rf._metadata_digest(source))
        self.assertEqual(calls,list(source));self.assertEqual(dest,{'com.apple.cs.CodeDirectory':b'first'})
        self.assertEqual(caught.exception.diagnostic['result_category'],'UNSUPPORTED')

    def test_source_mutation_and_pin_mismatch_remain_fail_closed(self):
        source={'com.apple.cs.CodeSignature':b'first'};changed={'com.apple.cs.CodeSignature':b'changed'}
        with patch.object(rf,'_read_xattrs',side_effect=[source,{},source,changed]),\
            patch.object(rf,'_write_xattr'),patch.object(rf,'_check_acl'),\
            patch.object(rf,'identity',return_value=()),patch.object(rf.os,'fstat'):
            with self.assertRaisesRegex(rf.RuntimeMetadataCopyError,'RUNTIME_COPY_METADATA_RACE') as caught:
                rf.copy_runtime_metadata(1,2,rf._metadata_digest(source))
        self.assertEqual(caught.exception.diagnostic['stage'],'SOURCE_RECHECK')
        with patch.object(rf,'_read_xattrs',return_value=source),patch.object(rf,'_check_acl'),\
            patch.object(rf.os,'fstat'),patch.object(rf,'_write_xattr') as writer:
            with self.assertRaisesRegex(rf.RuntimeMetadataCopyError,'RUNTIME_COPY_METADATA_PARENT'):
                rf.copy_runtime_metadata(1,2,{})
            writer.assert_not_called()


def policy_fields(metadata):
    p=rf.layout_policy()
    return dict(layout_policy=p,layout_parent=content_hash(p),metadata=metadata)


def structural_rows(count=15):
    names=['bin/python3.14','tls/ca.pem','lib/python3.14/site-packages/example-1.0.dist-info/METADATA']
    for n,low in (('Tcl','tcl'),('Tk','tk')):
        base='Frameworks/'+n+'.framework/Versions/9.0/'
        names += [base+x for x in (n,'Headers/header.h','Resources/Info.plist',low+'Config.sh','lib'+low+'stub.a')]
    names += ['data/item-'+str(i) for i in range(count-len(names))]
    rows=[dict(path=n,size=1,mode=0o500 if n=='bin/python3.14' else 0o400,sha256='a'*64) for n in names]
    dirs={'.'}
    for n in names+list(dict(rf._LINKS)):
        parts=n.split('/');dirs.update('/'.join(parts[:i]) for i in range(1,len(parts)))
    return rows,{n:{} for n in set(names)|dirs|set(dict(rf._LINKS))}


def make_tree(root):
    rows,_=structural_rows()
    for row in rows:
        p=root/row['path'];p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        data=(b'Name: example\nVersion: 1.0\n' if p.name=='METADATA' else b'not-executable-test-bytes')
        p.write_bytes(data);p.chmod(row['mode'])
    for name,target in rf._LINKS:(root/name).symlink_to(target)
    for p in sorted(root.rglob('*'),reverse=True):
        if not p.is_symlink() and p.is_dir():p.chmod(0o500)
    root.chmod(0o500)


class TreeCase(unittest.TestCase):
    """Shared disposable fixture; not an executable runtime."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='iios-provider-connection-source-tests-framework-')
        self.base=Path(self.temp.name).resolve();self.base.chmod(0o700)
        self.root=self.base/'tree';self.root.mkdir();make_tree(self.root)
        self.mocks=ExitStack();self.mocks.enter_context(patch.object(rf,'_read_xattrs',return_value={}))
        self.mocks.enter_context(patch.object(rf,'_check_acl'))
        self.mocks.enter_context(patch.object(rf,'_link_metadata',return_value={}))
        # The unchanged preparation guard does not translate symlink dir_fd.
        # Substitute that effect with an exact, inode-matched disposable path.
        # This adapter is test-only; production keeps descriptor-relative writes.
        real_symlink=os.symlink
        def test_symlink(target,name,target_is_directory=False,*,dir_fd=None):
            if dir_fd is None:return real_symlink(target,name,target_is_directory)
            root=self.base/'output/runtime-test';observed=os.fstat(dir_fd)
            for relative,pinned in rf._LINKS:
                path=root/relative
                if path.name==name and target==pinned:
                    st=path.parent.stat()
                    if (st.st_dev,st.st_ino)==(observed.st_dev,observed.st_ino):
                        return real_symlink(target,path)
            raise AssertionError('UNBOUND_TEST_LINK_WRITE')
        self.mocks.enter_context(patch.object(os,'symlink',side_effect=test_symlink))
        self.policy=rf.layout_policy();self.parent=content_hash(self.policy)
        self.observed=rf.inventory_runtime(str(self.root),self.policy,self.parent,approved_root=str(self.root))
    def tearDown(self):
        self.mocks.close()
        for p in self.base.rglob('*'):
            if not p.is_symlink() and p.is_dir():p.chmod(0o700)
        self.temp.cleanup()
    def verify(self):
        return rf.verify_runtime_tree(str(self.root),self.observed['files'],approved_root=str(self.root),
            **policy_fields(self.observed['metadata']))


class FrameworkTreeTests(TreeCase):
    def test_exact_twelve_links_and_no_execution(self):
        with patch('subprocess.run',side_effect=AssertionError('EXECUTION')):
            self.assertEqual(set(self.verify()),{r['path'] for r in self.observed['files']})
        self.assertEqual(len(self.policy['links']),12)
    def test_every_altered_link_rejected(self):
        for name,target in rf._LINKS:
            p=self.root/name;p.parent.chmod(0o700);p.unlink();p.symlink_to(target+'changed');p.parent.chmod(0o500)
            with self.subTest(name=name),self.assertRaises(ValueError):self.verify()
            p.parent.chmod(0o700);p.unlink();p.symlink_to(target);p.parent.chmod(0o500)
    def test_missing_extra_regularized_and_escaping_links(self):
        name,target=rf._LINKS[0];p=self.root/name
        for replacement in (None,'Versions/Changed','regular'):
            p.parent.chmod(0o700);p.unlink()
            if replacement=='regular':p.write_bytes(target.encode());p.chmod(0o400)
            elif replacement:p.symlink_to(replacement)
            p.parent.chmod(0o500)
            with self.subTest(replacement=replacement),self.assertRaises(ValueError):self.verify()
            p.parent.chmod(0o700)
            if replacement:p.unlink()
            p.symlink_to(target);p.parent.chmod(0o500)
        self.root.chmod(0o700);(self.root/'extra').symlink_to('bin/python3.14');self.root.chmod(0o500)
        with self.assertRaises(ValueError):self.verify()
    def test_escaping_link_observations_rejected_without_creating_them(self):
        for target in ('/outside','../escape','Versions/Current/../bad','Versions//9.0'):
            with patch.object(rf.os,'readlink',return_value=target):
                with self.assertRaises(ValueError):self.verify()

    def test_metadata_race_and_unknown_attribute(self):
        with patch.object(rf,'_read_xattrs',side_effect=[{}, {'unapproved':b'value'}]):
            with self.assertRaises(ValueError):self.verify()
        with patch.object(rf,'_read_xattrs',return_value={'unknown':b'x'}):
            with self.assertRaisesRegex(ValueError,'XATTR_NAME'):self.verify()
    def test_wrong_owner_hardlink_writable_target_and_parent(self):
        with patch.object(rf.os,'getuid',return_value=-1):
            with self.assertRaises(ValueError):self.verify()
        p=self.root/'tls/ca.pem';p.chmod(0o600)
        with self.assertRaises(ValueError):self.verify()
        p.chmod(0o400);self.root.chmod(0o700);os.link(p,self.root/'extra-hardlink');self.root.chmod(0o500)
        with self.assertRaises(ValueError):self.verify()
    def test_target_replacement_and_link_race(self):
        p=self.root/'tls/ca.pem';p.chmod(0o600);p.write_bytes(b'changed');p.chmod(0o400)
        with self.assertRaises(ValueError):self.verify()
        real=rf.os.readlink
        with patch.object(rf.os,'readlink',side_effect=lambda *a,**k:real(*a,**k)+'changed'):
            with self.assertRaises(ValueError):self.verify()
    def test_generic_v1_still_rejects_aliases(self):
        with self.assertRaises(ValueError):verify_files(str(self.root),self.observed['files'],approved_root=str(self.root))
    def test_empty_unknown_directory_rejected(self):
        self.root.chmod(0o700);(self.root/'unlisted').mkdir(mode=0o500);self.root.chmod(0o500)
        with self.assertRaises(ValueError):self.verify()
    def test_root_alias_rejected(self):
        alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError):rf.inventory_runtime(str(alias),self.policy,self.parent,approved_root=str(alias))


class FrameworkPolicyTests(unittest.TestCase):
    def test_every_policy_link_field_rehashed_mutation_rejected_before_io(self):
        for i in range(12):
            for key,value in [('path','lookalike'),('target','../escape'),('sha256','0'*64),('extra',False)]:
                p=rf.layout_policy();p['links'][i][key]=value
                with self.subTest(i=i,key=key),patch.object(rf,'open_root',side_effect=AssertionError('IO')):
                    with self.assertRaises(ValueError):rf.validate_layout_policy(p,content_hash(p))
    def test_policy_count_vendor_parent_and_order(self):
        for key,value in [('max_files',7001),('max_file_bytes',rf.MAX_FILE_BYTES+1),
            ('max_total_bytes',rf.MAX_TOTAL_BYTES+1),('distribution_sha256','b'*64),('schema','v1')]:
            p=rf.layout_policy();p[key]=value
            with self.assertRaises(ValueError):rf.validate_layout_policy(p,content_hash(p))
        p=rf.layout_policy();p['links'].reverse()
        with self.assertRaises(ValueError):rf.validate_layout_policy(p,content_hash(p))
        with self.assertRaises(ValueError):rf.validate_layout_policy(rf.layout_policy(),'0'*64)
    def test_7000_7001_and_unchanged_generic_5000(self):
        rows,meta=structural_rows(7000);rf._validate_rows(rows,meta,dict(rf._LINKS))
        rows,meta=structural_rows(7001)
        with self.assertRaisesRegex(ValueError,'FILE_COUNT'):rf._validate_rows(rows,meta,dict(rf._LINKS))
        with patch('os.open',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'EVIDENCE_FILE_COUNT'):verify_files('/disposable',rows,approved_root='/disposable')
    def test_ambiguous_root_rejected_before_filesystem(self):
        with patch.object(rf,'open_root',side_effect=AssertionError('NO_IO')):
            with self.assertRaisesRegex(ValueError,'ROOT_PATH'):
                rf.inventory_runtime('//disposable',rf.layout_policy(),content_hash(rf.layout_policy()),approved_root='//disposable')

    def test_byte_limits_and_alias_descendants(self):
        rows,meta=structural_rows()
        for size in (rf.MAX_FILE_BYTES+1,-1,True):
            r=deepcopy(rows);r[0]['size']=size
            with self.assertRaises(ValueError):rf._validate_rows(r,meta,dict(rf._LINKS))
        for r in rows:r['size']=rf.MAX_FILE_BYTES
        with self.assertRaisesRegex(ValueError,'TOTAL_BOUND'):rf._validate_rows(rows,meta,dict(rf._LINKS))
        rows,meta=structural_rows();rows[0]['path']='Frameworks/Tcl.framework/Headers/alias'
        with self.assertRaises(ValueError):rf._validate_rows(rows,meta,dict(rf._LINKS))
    def test_graph_cycle_escape_missing_and_depth(self):
        for links in ({'Frameworks/Tcl.framework/a':'a'}, {'Frameworks/Tcl.framework/a':'../bad'},
            {'Frameworks/Tcl.framework/a':'b','Frameworks/Tcl.framework/b':'c','Frameworks/Tcl.framework/c':'d'}):
            with self.assertRaises(ValueError):rf._terminal('Frameworks/Tcl.framework/a',links)
        rows,meta=structural_rows();rows=[r for r in rows if r['path']!='Frameworks/Tcl.framework/Versions/9.0/Tcl']
        with self.assertRaises(ValueError):rf._validate_rows(rows,meta,dict(rf._LINKS))
    def test_quarantine_signature_and_provenance_exact_bytes(self):
        values={'com.apple.quarantine':b'0083;1234abcd;Python;','com.apple.cs.CodeSignature':b'synthetic-signature'}
        before=rf._metadata_digest(values)
        self.assertEqual(before['com.apple.cs.CodeSignature']['sha256'],hashlib.sha256(values['com.apple.cs.CodeSignature']).hexdigest())
        for value in (b'0000;1234abcd;Python;',b'0083;bad;Python;',b'x\x00y',b''):
            with self.assertRaises(ValueError):rf._metadata_digest({'com.apple.quarantine':value})
        with self.assertRaises(ValueError):rf._metadata_digest({'com.apple.provenance':b'wrong'})
    def test_copy_metadata_exact_and_no_provenance_fabrication(self):
        values={'com.apple.cs.CodeSignature':b'synthetic','com.apple.quarantine':b'0283;1234abcd;Python;',
            'com.apple.provenance':b'01234567890'}
        destination={'com.apple.provenance':b'abcdefghijk'};written=[]
        def read(fd):return dict(values if fd==1 else destination)
        def write(fd,name,value):written.append(name);destination[name]=value
        with patch.object(rf,'_read_xattrs',side_effect=read),patch.object(rf,'_write_xattr',side_effect=write),\
            patch.object(rf,'_check_acl'),patch.object(rf,'identity',return_value=('stable',)),patch.object(rf.os,'fstat'):
            result=rf.copy_runtime_metadata(1,2,rf._metadata_digest(values))
            self.assertEqual(result,rf._metadata_digest(destination));self.assertNotIn('com.apple.provenance',written)
            with self.assertRaises(ValueError):rf.copy_runtime_metadata(1,2,{})
    def test_metadata_clear_unknown_transform_or_acl_rejected(self):
        source={'com.apple.quarantine':b'0083;1234abcd;Python;'}
        for changed in ({},{'com.apple.quarantine':b'0283;1234abcd;Python;'}):
            with patch.object(rf,'_read_xattrs',side_effect=[source,{},changed]),patch.object(rf,'_write_xattr'),\
                patch.object(rf,'_check_acl'),patch.object(rf,'identity',return_value=()),patch.object(rf.os,'fstat'):
                with self.assertRaises(ValueError):rf.copy_runtime_metadata(1,2,rf._metadata_digest(source))
        with patch.object(rf,'_check_acl',side_effect=ValueError('RUNTIME_ACL_PRESENT')),patch.object(rf.os,'fstat'):
            with self.assertRaisesRegex(ValueError,'ACL_PRESENT'):rf.copy_runtime_metadata(1,2,{})


class FrameworkRaceTests(TreeCase):
    def test_root_replacement_after_scan_rejected(self):
        second=self.base/'replacement';second.mkdir(mode=0o500)
        real=rf.open_root;calls=[]
        def open_checked(root,approved):
            calls.append(root)
            return real(root,approved) if len(calls)==1 else real(str(second),str(second))
        with patch.object(rf,'open_root',side_effect=open_checked):
            with self.assertRaisesRegex(ValueError,'ROOT_CHANGED'):self.verify()
    def test_link_inode_replacement_between_observations_rejected(self):
        from types import SimpleNamespace
        real=rf.os.stat;name=rf._LINKS[0][0].split('/')[-1];calls=[]
        def observed(path,*a,**k):
            st=real(path,*a,**k)
            if path==name and k.get('follow_symlinks') is False:
                calls.append(path)
                if len(calls)==2:
                    fields={key:getattr(st,key) for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_nlink')}
                    fields['st_ino']+=1;return SimpleNamespace(**fields)
            return st
        with patch.object(rf.os,'stat',side_effect=observed):
            with self.assertRaisesRegex(ValueError,'LINK_CHANGED'):self.verify()
    def test_read_growth_writable_parent_and_metadata_pin_rejected(self):
        with patch.object(rf.os,'read',return_value=b'x'*65536):
            with self.assertRaisesRegex(ValueError,'READ_BOUND'):self.verify()
        p=self.root/'Frameworks';p.chmod(0o700)
        with self.assertRaisesRegex(ValueError,'ALIAS_OR_MODE'):self.verify()
        p.chmod(0o500)
        metadata=deepcopy(self.observed['metadata']);metadata['.']={'com.apple.cs.CodeSignature':dict(size=1,sha256='a'*64)}
        with self.assertRaisesRegex(ValueError,'TREE_MISMATCH'):
            rf.verify_runtime_tree(str(self.root),self.observed['files'],approved_root=str(self.root),**policy_fields(metadata))
    def test_duplicate_files_links_and_metadata_overflow_before_io(self):
        p=rf.layout_policy();p['links'].append(p['links'][0])
        with self.assertRaises(ValueError):rf.validate_layout_policy(p,content_hash(p))
        rows=self.observed['files']+[self.observed['files'][0]]
        with patch.object(rf,'open_root',side_effect=AssertionError('NO_IO')):
            with self.assertRaises(ValueError):rf.verify_runtime_tree(str(self.root),rows,approved_root=str(self.root),**policy_fields(self.observed['metadata']))
        rows,meta=structural_rows();meta['.']={n:dict(size=1024*1024,sha256='a'*64) for n in rf._XATTRS}
        with self.assertRaisesRegex(ValueError,'TOTAL_BOUND'):rf._validate_rows(rows,meta,dict(rf._LINKS))


class DarwinMetadataInterfaceTests(unittest.TestCase):
    def test_empty_valid_acl_only_and_error_attribution(self):
        import ctypes,errno
        from unittest.mock import Mock
        lib=Mock();lib.acl_get_fd_np.return_value=123;lib.acl_valid.return_value=0
        def empty(*args):ctypes.set_errno(errno.EINVAL);return -1
        lib.acl_get_entry.side_effect=empty
        with patch.object(rf,'_darwin',return_value=(ctypes,lib)):
            rf._check_acl(99)
            lib.acl_free.assert_called_once_with(123)
            lib.acl_get_entry.side_effect=None;lib.acl_get_entry.return_value=0
            with self.assertRaisesRegex(ValueError,'ACL_PRESENT'):rf._check_acl(99)
            lib.acl_valid.return_value=-1
            with self.assertRaisesRegex(ValueError,'ACL_INVALID'):rf._check_acl(99)
    def test_unknown_xattr_name_fails_without_arbitrary_decode(self):
        import ctypes
        from unittest.mock import Mock
        lib=Mock();lib.flistxattr.side_effect=[2,2]
        # The all-zero buffer models a changing/malformed list; the scanner must
        # reject this rather than treating unknown bytes as approved metadata.
        def listing(fd,buf,size,flags):
            if buf is not None:buf.raw=b'\xff\0'
            return 2
        lib.flistxattr.side_effect=listing
        with patch.object(rf,'_darwin',return_value=(ctypes,lib)):
            with self.assertRaisesRegex(ValueError,'XATTR_NAME'):rf._read_xattrs(99)
            lib.fgetxattr.assert_not_called()


class LinkDescriptorMetadataTests(unittest.TestCase):
    def test_opened_link_identity_and_acl_checked_without_following(self):
        from types import SimpleNamespace
        import stat
        st=SimpleNamespace(st_dev=1,st_ino=2,st_size=3,st_mtime_ns=4,st_ctime_ns=5,
            st_mode=stat.S_IFLNK|0o777,st_uid=os.getuid(),st_nlink=1)
        with patch.object(os,'O_SYMLINK',getattr(os,'O_SYMLINK',0x200000),create=True),\
            patch.object(rf.os,'open',return_value=99) as opened,patch.object(rf.os,'close') as closed,\
            patch.object(rf.os,'fstat',return_value=st),patch.object(rf,'_read_xattrs',return_value={}),\
            patch.object(rf,'_check_acl') as acl:
            rf._link_metadata(88,'Tcl',st)
            self.assertTrue(opened.call_args.args[1]&os.O_SYMLINK);acl.assert_called_once_with(99)
            closed.assert_called_once_with(99)
            acl.side_effect=ValueError('RUNTIME_ACL_PRESENT')
            with self.assertRaisesRegex(ValueError,'ACL_PRESENT'):rf._link_metadata(88,'Tcl',st)
            self.assertEqual(closed.call_count,2)


class LinkProvenanceBindingTests(TreeCase):
    def test_exact_independent_link_metadata_pin_and_same_length_mutation(self):
        observed=rf._metadata_digest({'com.apple.provenance':b'01234567890'})
        with patch.object(rf,'_link_metadata',return_value=observed):
            measured=rf.inventory_runtime(str(self.root),self.policy,self.parent,approved_root=str(self.root))
            self.assertEqual(set(dict(rf._LINKS)),{p for p in measured['metadata'] if p in dict(rf._LINKS)})
            rf.verify_runtime_tree(str(self.root),measured['files'],approved_root=str(self.root),**policy_fields(measured['metadata']))
            for altered in ({},rf._metadata_digest({'com.apple.provenance':b'abcdefghijk'})):
                with patch.object(rf,'_link_metadata',return_value=altered):
                    with self.assertRaisesRegex(ValueError,'TREE_MISMATCH'):
                        rf.verify_runtime_tree(str(self.root),measured['files'],approved_root=str(self.root),**policy_fields(measured['metadata']))

    def test_missing_extra_and_wrong_metadata_rejected_before_io(self):
        for bad in ({'unexpected':dict(size=11,sha256='a'*64)},
                    {'com.apple.quarantine':dict(size=11,sha256='a'*64)},
                    {'com.apple.provenance':dict(size=10,sha256='a'*64)},
                    {'com.apple.provenance':dict(size=11,sha256='not-a-hash')}):
            meta=deepcopy(self.observed['metadata']);meta[rf._LINKS[0][0]]=bad
            with patch.object(rf,'open_root',side_effect=AssertionError('NO_IO')):
                with self.assertRaises(ValueError):
                    rf.verify_runtime_tree(str(self.root),self.observed['files'],approved_root=str(self.root),**policy_fields(meta))
        meta=deepcopy(self.observed['metadata']);del meta[rf._LINKS[0][0]]
        with patch.object(rf,'open_root',side_effect=AssertionError('NO_IO')):
            with self.assertRaisesRegex(ValueError,'METADATA_INVENTORY'):
                rf.verify_runtime_tree(str(self.root),self.observed['files'],approved_root=str(self.root),**policy_fields(meta))

    def test_link_metadata_counts_toward_unchanged_total(self):
        rows,meta=structural_rows();link=rf._LINKS[0][0]
        meta[link]={'com.apple.provenance':dict(size=11,sha256='a'*64)}
        with patch.object(rf,'MAX_TOTAL_BYTES',sum(x['size'] for x in rows)+10):
            with self.assertRaisesRegex(ValueError,'TOTAL_BOUND'):rf._validate_rows(rows,meta,dict(rf._LINKS))


class LinkProvenanceDescriptorTests(unittest.TestCase):
    def inspect(self, reads):
        from types import SimpleNamespace
        import stat
        st=SimpleNamespace(st_dev=1,st_ino=2,st_size=3,st_mtime_ns=4,st_ctime_ns=5,
            st_mode=stat.S_IFLNK|0o700,st_uid=os.getuid(),st_nlink=1)
        with patch.object(os,'O_SYMLINK',getattr(os,'O_SYMLINK',0x200000),create=True),\
            patch.object(rf.os,'open',return_value=99) as opened,patch.object(rf.os,'close') as closed,\
            patch.object(rf.os,'fstat',return_value=st),patch.object(rf,'_read_xattrs',side_effect=reads),\
            patch.object(rf,'_check_acl') as acl,patch.object(rf,'_write_xattr',side_effect=AssertionError('NO_METADATA_WRITE')):
            try:return rf._link_metadata(88,'Tcl',st)
            finally:
                self.assertTrue(opened.call_args.args[1]&os.O_SYMLINK)
                acl.assert_called_once_with(99);closed.assert_called_once_with(99)

    def test_opaque_creation_bytes_preserved_not_interpreted(self):
        value={'com.apple.provenance':b'01234567890'}
        self.assertEqual(self.inspect([value,value]),rf._metadata_digest(value))
        self.assertEqual(self.inspect([{},{}]),{})

    def test_unknown_metadata_wrong_size_and_changed_read_fail(self):
        value={'com.apple.provenance':b'01234567890'}
        for bad in ({'unknown':b'x'},{'com.apple.quarantine':b'0283;1234abcd;Python;'},
                    {'com.apple.cs.CodeSignature':b'x'},{'com.apple.provenance':b'wrong'}):
            with self.subTest(bad=tuple(bad)),self.assertRaises(ValueError):self.inspect([bad,bad])
        for second in ({},{'com.apple.provenance':b'abcdefghijk'}):
            with self.assertRaisesRegex(ValueError,'LINK_METADATA_CHANGED'):self.inspect([value,second])


class AbsentAclEvidenceTests(unittest.TestCase):
    def test_permission_error_does_not_become_absence(self):
        import ctypes,errno
        from unittest.mock import Mock
        lib=Mock()
        for error in (errno.EACCES,errno.EPERM,errno.EBADF,0):
            def fail(*args):ctypes.set_errno(error);return None
            lib.acl_get_fd_np.side_effect=fail
            with patch.object(rf,'_darwin',return_value=(ctypes,lib)),patch.object(rf,'_confirm_absent_acl') as confirm:
                with self.assertRaisesRegex(ValueError,'ACL_READ'):rf._check_acl(99)
                confirm.assert_not_called()
        def absent(*args):ctypes.set_errno(errno.ENOENT);return None
        lib.acl_get_fd_np.side_effect=absent
        with patch.object(rf,'_darwin',return_value=(ctypes,lib)),\
             patch.object(rf,'_confirm_absent_acl',side_effect=ValueError('MISSING_POSITIVE_PROOF')):
            with self.assertRaisesRegex(ValueError,'MISSING_POSITIVE_PROOF'):rf._check_acl(99)

    def test_successful_security_query_absence_and_identity_required(self):
        import ctypes
        from unittest.mock import Mock
        from types import SimpleNamespace
        st=SimpleNamespace(st_dev=1,st_ino=2,st_mode=0o100400,st_nlink=1,st_uid=501,
            st_gid=20,st_size=11,st_mtime_ns=3000000004,st_ctime_ns=5000000006)
        lib=Mock();lib.filesec_init.return_value=42
        def observed(fd,ptr,security):
            s=ptr._obj
            for field,value in [('dev',1),('ino',2),('mode',st.st_mode),('nlink',1),('uid',501),('gid',20),('size',11)]:setattr(s,field,value)
            s.mtime.sec=3;s.mtime.nsec=4;s.ctime.sec=5;s.ctime.nsec=6
            return 0
        def absent(sec,prop,ptr):self.assertEqual(prop,5);ptr._obj.value=0;return 0
        lib.fstatx_np.side_effect=observed;lib.filesec_query_property.side_effect=absent
        with patch.object(rf.os,'fstat',return_value=st):
            rf._confirm_absent_acl(99,ctypes,lib);lib.filesec_free.assert_called_with(42)
            for status,present in [(0,1),(0,-1),(-1,0)]:
                def changed(sec,prop,ptr):ptr._obj.value=present;return status
                lib.filesec_query_property.side_effect=changed
                with self.assertRaisesRegex(ValueError,'ACL_NOT_ABSENT'):rf._confirm_absent_acl(99,ctypes,lib)
            lib.filesec_query_property.side_effect=absent;lib.fstatx_np.side_effect=lambda *a:-1
            with self.assertRaisesRegex(ValueError,'ACL_READ'):rf._confirm_absent_acl(99,ctypes,lib)
            lib.fstatx_np.side_effect=lambda fd,ptr,sec:0
            with self.assertRaisesRegex(ValueError,'ACL_CHANGED'):rf._confirm_absent_acl(99,ctypes,lib)
            lib.fstatx_np.side_effect=observed
            changed_st=SimpleNamespace(**{**vars(st),'st_ino':3})
            with patch.object(rf.os,'fstat',side_effect=[st,changed_st]):
                with self.assertRaisesRegex(ValueError,'ACL_CHANGED'):rf._confirm_absent_acl(99,ctypes,lib)
        self.assertEqual(lib.filesec_free.call_count,7)


class CompletedPathTests(unittest.TestCase):
    def test_paths_are_exact_siblings_and_reject_escapes_before_io(self):
        root='/synthetic/runtime-test'
        self.assertEqual(rf.completed_paths(root),dict(manifest=root+'.manifest.json',envelope=root+'.envelope.json'))
        for value in ('relative/runtime-test','/synthetic/../runtime-test','/synthetic//runtime-test',
                      '/synthetic/runtime-test/','/synthetic/Keychains/runtime-test','/synthetic/runtime-test\x00'):
            with self.subTest(value=value),patch.object(os,'open',side_effect=AssertionError('IO')):
                with self.assertRaises(ValueError):rf.completed_paths(value)

    def test_external_record_parent_and_inode_race_are_rejected(self):
        from types import SimpleNamespace
        st=SimpleNamespace(st_mode=0o100400,st_uid=os.getuid(),st_nlink=1,st_size=1)
        parent=SimpleNamespace(st_mode=0o40700,st_uid=os.getuid())
        with patch.object(os,'open',return_value=42),patch.object(os,'close'),\
             patch.object(os,'fstat',side_effect=[parent,parent,parent,st,st]),\
             patch.object(os,'stat',return_value=st),patch.object(os,'read',side_effect=[b'x',b'']),\
             patch.object(rf,'identity',side_effect=['parent','before','changed']):
            with self.assertRaisesRegex(ValueError,'RUNTIME_EXTERNAL_RACE'):
                rf._external_bytes('/synthetic/runtime-test.manifest.json',b'x')


class AssemblyVerifierImportBoundaryTests(unittest.TestCase):
    def test_complete_module_import_graph_is_standard_library_only(self):
        tree=ast.parse(Path(rf.__file__).read_bytes())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node,ast.ImportFrom):imports.append((node.module or '').split('.')[0])
        self.assertEqual(set(imports),{'ctypes','errno','hashlib','json','os','pathlib',
                                      'platform','plistlib','re','stat','sys'})
        self.assertFalse(set(imports)&{'alpha_session_contract','alpha_session_evidence',
            'deployment_contract','provider_gateway_contract','truth_spine_session'})

    def test_fresh_execution_rejects_accidental_application_imports(self):
        source=Path(rf.__file__).read_bytes();real=builtins.__import__;attempted=[]
        denied=('alpha_','deployment_','provider_','truth_')
        def guarded(name,*args,**kwargs):
            if name.startswith(denied):
                attempted.append(name);raise AssertionError('APPLICATION_IMPORT_FORBIDDEN')
            return real(name,*args,**kwargs)
        namespace={'__name__':'alpha_runtime_files_isolated','__file__':rf.__file__}
        with patch.object(builtins,'__import__',side_effect=guarded):
            exec(compile(source,rf.__file__,'exec'),namespace)
        self.assertEqual(attempted,[])
        self.assertEqual(namespace['content_hash']({'a':1}),content_hash({'a':1}))
        self.assertEqual(namespace['layout_policy'](),rf.layout_policy())

    def test_canonical_hash_and_sensitive_document_behavior_are_unchanged(self):
        from deployment_contract import canonical as deployment_canonical,digest
        from provider_gateway_contract import safe_document
        from truth_spine_contract import canonical as truth_canonical
        values=({'schema':'example','nested':[1,True,None,'ASCII']},
                {'z':'\N{SNOWMAN}','a':1.25})
        for value in values:
            self.assertEqual(rf.canonical(value),truth_canonical(value))
            self.assertEqual(rf.canonical(value),deployment_canonical(value))
            self.assertEqual(rf.content_hash(value),content_hash(value))
            self.assertEqual(rf._digest(dict(value,content_hash='0'*64)),digest(dict(value,content_hash='0'*64)))
            safe_document(value);rf._safe_document(value)
        rejected=({'headers':{}},{'nested':{'Api_Key':'x'}},
                  {'value':'Bearer sample'}, {'value':'?token=sample'},
                  {'value':'-----BEGIN PRIVATE KEY'}, {'value':float('nan')},
                  {'value':object()})
        for value in rejected:
            with self.subTest(value=repr(value)):
                with self.assertRaises((TypeError,ValueError)):safe_document(value)
                with self.assertRaises((TypeError,ValueError)):rf._safe_document(value)

    def test_altered_runtime_documents_remain_rejected(self):
        rows,metadata=structural_rows();policy=rf.layout_policy();parent=content_hash(policy)
        document=dict(schema=rf.DESCRIPTOR_SCHEMA,files=rows,layout_policy=policy,
                      layout_parent=parent,metadata=metadata)
        rf.safe_runtime_document(document)
        changes=(('layout_parent','0'*64),('files',rows+[rows[0]]),
                 ('metadata',dict(metadata,unexpected={})))
        for key,value in changes:
            altered=deepcopy(document);altered[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                rf.safe_runtime_document(altered)


def production_projection_fixture():
    rows,_=structural_rows()
    additions={
        'bin/idle3','bin/idle3.14',
        'lib/python3.14/idlelib/entry.py',
        'lib/python3.14/lib-dynload/_tkinter.cpython-314-darwin.so',
        'lib/python3.14/test/test_tkinter/entry.py',
        'lib/python3.14/test/tkinterdata/image.bin',
        'lib/python3.14/tkinter/__init__.py',
        'lib/python3.14/site-packages/kept/module.py',
    }
    additions.update(path for path,_ in rf._PRODUCTION_WHEEL_CODE)
    for name in sorted(additions):
        rows.append(dict(path=name,size=1,mode=0o400,sha256='b'*64))
    rows=sorted(rows,key=lambda row:row['path'])
    directories={'.'}
    for name in [row['path'] for row in rows]+list(dict(rf._LINKS)):
        parts=name.split('/');directories.update('/'.join(parts[:i]) for i in range(1,len(parts)))
    metadata={name:{} for name in directories|set(dict(rf._LINKS))|{row['path'] for row in rows}}
    closure=dict(schema=rf.PRODUCTION_IMPORT_CLOSURE_SCHEMA,
        source_inventory_sha256='c'*64,
        modules=['hashlib','json','ssl'])
    policy=rf.production_layout_policy()
    return rows,metadata,closure,policy


class ProductionRuntimeProjectionTests(unittest.TestCase):
    def project(self,rows=None,metadata=None,closure=None,policy=None):
        base_rows,base_metadata,base_closure,base_policy=production_projection_fixture()
        rows=base_rows if rows is None else rows
        metadata=base_metadata if metadata is None else metadata
        closure=base_closure if closure is None else closure
        policy=base_policy if policy is None else policy
        return rf.project_production_runtime(rows,metadata,closure=closure,
            closure_parent=content_hash(closure),policy=policy,policy_parent=content_hash(policy))

    def test_exact_versioned_projection_excludes_unreachable_gui_stack(self):
        result=self.project();names={row['path'] for row in result['files']}
        self.assertIn('lib/python3.14/site-packages/kept/module.py',names)
        for prefix in rf._PRODUCTION_EXCLUDED_PREFIXES:
            self.assertFalse(any(name==prefix or name.startswith(prefix+'/') for name in names))
            self.assertFalse(any(name==prefix or name.startswith(prefix+'/') for name in result['metadata']))
        self.assertEqual(result['excluded_prefixes'],list(rf._PRODUCTION_EXCLUDED_PREFIXES))
        self.assertEqual(rf.validate_layout_policy(rf.production_layout_policy(),
            content_hash(rf.production_layout_policy())),{})

    def test_missing_altered_case_and_additional_policy_rejected(self):
        rows,metadata,closure,policy=production_projection_fixture()
        removed='bin/idle3';rows=[row for row in rows if row['path']!=removed];metadata.pop(removed)
        with self.assertRaisesRegex(ValueError,'EXCLUSION_MISSING'):self.project(rows,metadata,closure,policy)
        rows,metadata,closure,policy=production_projection_fixture()
        target=next(row for row in rows if row['path']=='bin/idle3');target['path']='bin/Idle3'
        metadata['bin/Idle3']=metadata.pop('bin/idle3')
        with self.assertRaisesRegex(ValueError,'EXCLUSION_ALIAS'):self.project(rows,metadata,closure,policy)
        policy=rf.production_layout_policy();policy['excluded_prefixes'].append('unreviewed')
        with self.assertRaisesRegex(ValueError,'LAYOUT_POLICY'):self.project(policy=policy)

    def test_forbidden_imports_and_closure_mutations_rejected(self):
        for module in ('tkinter','tkinter.ttk','_tkinter','idlelib','turtle','turtledemo.demo'):
            _,_,closure,_=production_projection_fixture();closure['modules']=sorted(closure['modules']+[module])
            with self.subTest(module=module),self.assertRaisesRegex(ValueError,'FORBIDDEN_IMPORT'):
                self.project(closure=closure)
        _,_,closure,_=production_projection_fixture()
        for mutation in (['json','hashlib','ssl'],['hashlib','json','json'],['hashlib','bad-name!','ssl']):
            changed=deepcopy(closure);changed['modules']=mutation
            with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,'IMPORT_CLOSURE'):
                self.project(closure=changed)

    def test_lookalike_traversal_and_unapproved_symlink_paths_fail_closed(self):
        for path in ('Frameworks/Tcl.framework/../escape',
                     'Frameworks//Tcl.framework/file','frameworks/tcl.framework/file'):
            with self.subTest(path=path),self.assertRaises(ValueError):rf._excluded_production_path(path)
        projected=self.project()
        mutated=dict(projected['metadata']);mutated[rf._LINKS[0][0]]={}
        with self.assertRaises(ValueError):rf._validate_rows(projected['files'],mutated,{})

    def test_final_policy_rejects_excluded_content_and_missing_required_code(self):
        projected=self.project();policy=rf.production_layout_policy();parent=content_hash(policy)
        document=dict(schema=rf.DESCRIPTOR_SCHEMA,files=projected['files'],layout_policy=policy,
                      layout_parent=parent,metadata=projected['metadata'])
        rf.safe_runtime_document(document)
        missing=deepcopy(document);path=rf._PRODUCTION_WHEEL_CODE[0][0]
        missing['files']=[row for row in missing['files'] if row['path']!=path];missing['metadata'].pop(path)
        with self.assertRaisesRegex(ValueError,'REQUIRED_CODE_MISSING'):rf.safe_runtime_document(missing)
        added=deepcopy(document);path='lib/python3.14/tkinter/reintroduced.py'
        added['files'].append(dict(path=path,size=1,mode=0o400,sha256='d'*64))
        for name in ('lib/python3.14/tkinter',path):added['metadata'][name]={}
        with self.assertRaisesRegex(ValueError,'EXCLUDED_CONTENT'):rf.safe_runtime_document(added)


def signing_evidence_fixture():
    policy=rf.production_layout_policy();pre=[];post=[]
    for index,item in enumerate(policy['required_derived_code']):
        common=dict(path=item['path'],size=100+index,file_type=item['file_type'],
            architectures=['x86_64','arm64'],load_commands_sha256=('%x'%(index+1))*64,
            install_names=item['install_names'],dependencies=item['dependencies'])
        pre.append(dict(common,sha256=('%x'%(index+5))*64,
                        signature='STRICT_VERIFICATION_FAILED_UNSIGNED'))
        post.append(dict(common,sha256=('%x'%(index+9))*64,
                         signature='IIOS_ADHOC_DERIVED_VERIFIED'))
    document=dict(schema=rf.PRODUCTION_SIGNING_EVIDENCE_SCHEMA,
        policy_parent=content_hash(policy),pre_transform=pre,post_sign=post,
        signing_order=policy['signing_order'],
        sign_commands=[['/usr/bin/codesign','--force','--sign','-','--timestamp=none',row['path']]
                       for row in policy['required_derived_code']],
        final_verification=['/usr/bin/codesign']+policy['final_verification']+['Python'],
        enclosing_runtime={'path':'Python','signed_after':[row['path'] for row in policy['required_derived_code']],
                           'signature':'IIOS_ADHOC_RESOURCE_SEAL_VERIFIED'})
    return document


class ProductionSigningContractTests(unittest.TestCase):
    def test_exact_bottom_up_contract_and_static_archive_disposition(self):
        document=signing_evidence_fixture()
        self.assertTrue(rf.validate_production_signing_evidence(document,content_hash(document)))
        policy=rf.production_layout_policy()
        self.assertFalse(policy['signing_deep'])
        self.assertEqual(policy['signing_order'][-1],'Python')
        self.assertEqual({row['path'] for row in policy['static_archives']},set(rf._PRODUCTION_STATIC_ARCHIVES))
        self.assertTrue(all(not row['runtime_executable'] and
            row['disposition']=='EXCLUDED_WITH_UNREACHABLE_FRAMEWORK'
            for row in policy['static_archives']))
        self.assertTrue(all('--deep' not in command for command in document['sign_commands']))
        policy['required_derived_code'][0]['dependencies'].append('/unexpected/lib.dylib')
        self.assertNotIn('/unexpected/lib.dylib',
            rf.production_layout_policy()['required_derived_code'][0]['dependencies'])

    def test_missing_additional_substituted_and_reordered_images_rejected(self):
        for kind in ('missing','additional','substituted','reordered'):
            document=signing_evidence_fixture()
            if kind=='missing':document['post_sign'].pop()
            elif kind=='additional':document['post_sign'].append(deepcopy(document['post_sign'][-1]))
            elif kind=='substituted':document['post_sign'][0]['path']='lib/substituted.so'
            else:document['post_sign'].reverse()
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                rf.validate_production_signing_evidence(document,content_hash(document))

    def test_architecture_signature_dependency_and_identity_mutations_rejected(self):
        changes=(('architectures',['arm64']),('signature','VERIFIED'),
                 ('load_commands_sha256','0'*64),
                 ('dependencies',['/usr/lib/libSystem.B.dylib','/unexpected/lib.dylib']),
                 ('sha256',signing_evidence_fixture()['pre_transform'][0]['sha256']))
        for key,value in changes:
            document=signing_evidence_fixture();document['post_sign'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                rf.validate_production_signing_evidence(document,content_hash(document))

    def test_unexpected_dependency_rejected_even_when_pre_and_post_match(self):
        document=signing_evidence_fixture()
        for phase in ('pre_transform','post_sign'):
            document[phase][0]['dependencies']=['/unexpected/lib.dylib']
        with self.assertRaisesRegex(ValueError,'SIGNING_IDENTITY'):
            rf.validate_production_signing_evidence(document,content_hash(document))

    def test_command_order_deep_signing_and_enclosing_order_rejected(self):
        document=signing_evidence_fixture();document['sign_commands'][0].insert(1,'--deep')
        with self.assertRaisesRegex(ValueError,'SIGNING_COMMAND'):
            rf.validate_production_signing_evidence(document,content_hash(document))
        document=signing_evidence_fixture();document['signing_order'].reverse()
        with self.assertRaises(ValueError):rf.validate_production_signing_evidence(document,content_hash(document))
        document=signing_evidence_fixture();document['enclosing_runtime']['signed_after'].reverse()
        with self.assertRaisesRegex(ValueError,'SIGNING_ENCLOSURE'):
            rf.validate_production_signing_evidence(document,content_hash(document))

    def test_independent_parent_and_complete_serialization_are_required(self):
        document=signing_evidence_fixture()
        with self.assertRaises(ValueError):rf.validate_production_signing_evidence(document,'0'*64)
        document['policy_parent']='0'*64
        with self.assertRaises(ValueError):rf.validate_production_signing_evidence(document,content_hash(document))


class SystemToolPinAdmissionTests(unittest.TestCase):
    def contract(self):
        return rf.lipo_system_tool_contract()

    def observation(self):
        return {key:deepcopy(value) for key,value in self.contract().items()
                if key not in ('schema','signature')}

    def test_exact_lipo_contract_requires_three_complete_observations(self):
        contract=self.contract();calls=[]
        def observe():
            calls.append(True);return self.observation()
        result=rf.admit_lipo_system_tool(contract,content_hash(contract),observer=observe)
        self.assertEqual(len(calls),3);self.assertEqual(result['observations'],3)
        self.assertEqual(result['status'],'ADMITTED_EXACT_SYSTEM_TOOL')
        self.assertEqual(result['signature_parent'],content_hash(contract['signature']))

    def test_contract_rejects_every_identity_and_signature_mutation(self):
        mutations=(
            ('literal_path','/usr/bin/lipo-substitute'),('resolved_path','/usr/bin/otool'),
            ('owner_uid',501),('owner_gid',20),('mode',0o775),('size',118927),
            ('sha256','0'*64),('device',1),('inode',2),('flags',0),
            ('hardlink_count',77),('hardlink_roots',['/usr/bin']),
            ('hardlink_topology',self.contract()['hardlink_topology'][:-1]),
        )
        for key,value in mutations:
            with self.subTest(key=key):
                contract=self.contract();contract[key]=value
                with self.assertRaisesRegex(ValueError,'SYSTEM_TOOL_CONTRACT'):
                    rf.validate_system_tool_contract(contract,content_hash(contract))
        for key,value in (('anchor','OTHER'),('designated_requirement','identifier "x"'),
                          ('cdhashes',{'arm64e':'0'*40,'x86_64':'1'*40}),
                          ('signature_size',1)):
            with self.subTest(signature=key):
                contract=self.contract();contract['signature'][key]=value
                with self.assertRaisesRegex(ValueError,'SYSTEM_TOOL_CONTRACT'):
                    rf.validate_system_tool_contract(contract,content_hash(contract))

    def test_observation_rejects_substitution_symlink_owner_mode_hash_and_topology(self):
        keys=('literal_path','resolved_path','file_type','owner_uid','mode','size','sha256',
              'hardlink_count','hardlink_topology','hardlink_topology_sha256','host')
        for key in keys:
            with self.subTest(key=key):
                changed=self.observation()
                if key=='host':changed[key]['product_build']='25F81'
                elif isinstance(changed[key],int):changed[key]+=1
                elif isinstance(changed[key],list):changed[key]=changed[key][:-1]
                else:changed[key]='MUTATED'
                with self.assertRaisesRegex(ValueError,'SYSTEM_TOOL_IDENTITY'):
                    rf.admit_lipo_system_tool(self.contract(),content_hash(self.contract()),
                                               observer=lambda:deepcopy(changed))

    def test_observations_must_remain_stable(self):
        values=[self.observation(),self.observation(),self.observation()]
        values[1]['ctime_ns']+=1
        with self.assertRaisesRegex(ValueError,'SYSTEM_TOOL_IDENTITY'):
            rf.admit_lipo_system_tool(self.contract(),content_hash(self.contract()),
                                       observer=lambda:values.pop(0))

    def test_lipo_exception_does_not_relax_any_other_pin(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ordinary';path.write_bytes(b'ordinary');os.chmod(path,0o500)
            alias=Path(root)/'alias';os.link(path,alias)
            row={'path':str(path),'size':8,'sha256':hashlib.sha256(b'ordinary').hexdigest()}
            with self.assertRaisesRegex(ValueError,'PIN_FILE_IDENTITY'):
                rf._admit_generic_pin(row)
            alias.unlink();path.unlink();target=Path(root)/'target';target.write_bytes(b'ordinary')
            os.chmod(target,0o500);path.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'PIN_FILE_IDENTITY'):
                rf._admit_generic_pin(row)

    def test_wrong_lipo_pin_and_missing_duplicate_or_unrelated_system_tool_reject(self):
        contract=self.contract();lipo={'path':'/usr/bin/lipo','size':contract['size'],
            'sha256':contract['sha256']};ordinary={'path':'/tmp/ordinary','size':1,'sha256':'0'*64}
        with patch.object(rf,'_admit_generic_pin') as generic:
            result=rf.admit_pin_inventory([ordinary,lipo],contract,content_hash(contract),
                system_observer=self.observation)
        generic.assert_called_once_with(ordinary);self.assertEqual(result['pins'],2)
        for rows in ([ordinary],[lipo,lipo],
                     [ordinary,dict(lipo,sha256='0'*64)],
                     [ordinary,{'path':'/usr/bin/otool','size':contract['size'],'sha256':contract['sha256']}],):
            with self.subTest(rows=rows),patch.object(rf,'_admit_generic_pin'):
                with self.assertRaises(ValueError):
                    rf.admit_pin_inventory(rows,contract,content_hash(contract),
                                           system_observer=self.observation)

    def test_admission_audit_rejects_writes_processes_network_and_signals(self):
        rf._admission_audit('open',('/tmp/read','r',os.O_RDONLY))
        denied=(('open',('/tmp/write','w',os.O_WRONLY|os.O_CREAT)),
                ('os.mkdir',('/tmp/x',0o700,-1)),('subprocess.Popen',('x',)),
                ('socket.connect',(('127.0.0.1',1),)),('os.kill',(1,15)))
        for event,args in denied:
            with self.subTest(event=event):
                with self.assertRaises(PermissionError):rf._admission_audit(event,args)

    def test_admission_only_dispatch_uses_shared_verifier_without_side_effects(self):
        from types import SimpleNamespace
        contract=self.contract();events=[]
        descriptor={'pins':[{'path':'/synthetic/pin','size':1,'sha256':'0'*64}]}
        admitted={'schema':rf.PIN_ADMISSION_SCHEMA,'pins':451,
                  'system_tool':{},'side_effects':False,
                  'assembly_child_created':False,'status':'PASS_PIN_ADMISSION_ONLY'}
        flags=SimpleNamespace(isolated=1,no_site=1,dont_write_bytecode=1)
        def add_hook(value):events.append(('audit',value))
        def generic(value):events.append(('file',value['path']))
        def inventory(*values,**keywords):
            events.append(('inventory',values[0]));return deepcopy(admitted)
        exact_environment={'LC_ALL':'C','TZ':'UTC',
                           '__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'}
        with patch.dict(os.environ,exact_environment,clear=True),\
             patch.object(rf.sys,'flags',flags),patch.object(rf.sys,'addaudithook',side_effect=add_hook),\
             patch.object(rf.os,'lstat',return_value=SimpleNamespace(st_size=1)),\
             patch.object(rf,'_admit_generic_pin',side_effect=generic),\
             patch.object(rf,'admit_pin_inventory',side_effect=inventory),\
             patch.object(rf.json,'load',side_effect=[descriptor,contract]),\
             patch.object(builtins,'open',unittest.mock.mock_open()),\
             patch.object(builtins,'print') as output,\
             patch.object(rf.os,'mkdir',side_effect=AssertionError('SIDE_EFFECT')),\
             patch.object(rf.os,'remove',side_effect=AssertionError('SIDE_EFFECT')),\
             patch.object(rf.os,'symlink',side_effect=AssertionError('SIDE_EFFECT')),\
             patch.object(rf.os,'kill',side_effect=AssertionError('SIDE_EFFECT')):
            self.assertEqual(rf.admission_only_main(['--admit-pins-only','/synthetic/descriptor',
                '1'*64,'/synthetic/contract','2'*64]),0)
        self.assertEqual(events[0][0],'audit')
        self.assertEqual([event[0] for event in events],['audit','file','file','inventory'])
        self.assertEqual(events[-1][1],descriptor['pins'])
        emitted=json.loads(output.call_args.args[0])
        self.assertFalse(emitted['assembly_child_created'])
        for key in ('runtime_executed','production_qualified','provider_access',
                    'credential_access','broker_connected','paper_order_permission',
                    'trade_execution_permission','live_execution'):
            self.assertFalse(emitted[key])

    def test_system_contract_binds_selected_host_and_independent_topology(self):
        contract=self.contract()
        self.assertEqual(contract['host']['product_build'],'25F80')
        self.assertEqual(contract['host']['kernel_release'],'25.5.0')
        self.assertEqual(contract['hardlink_count'],len(contract['hardlink_topology']))
        self.assertEqual(contract['hardlink_count'],78)
        self.assertEqual(contract['hardlink_topology_sha256'],hashlib.sha256(
            ('\n'.join(contract['hardlink_topology'])+'\n').encode()).hexdigest())
        self.assertEqual(contract['signature']['anchor'],'APPLE')
        self.assertTrue(contract['signature']['designated_requirement'].endswith('anchor apple'))


class AssemblyChildLaunchBindingTests(unittest.TestCase):
    def binding(self):
        document={
            'schema':rf.ASSEMBLY_CHILD_LAUNCH_SCHEMA,
            'interpreter_path':'/synthetic/runtime/bin/python3.14',
            'interpreter_size':17,
            'interpreter_sha256':'1'*64,
            'entrypoint_path':'/synthetic/control/assemble.py',
            'entrypoint_size':23,
            'entrypoint_sha256':'2'*64,
            'entrypoint_index':4,
            'argv':['/synthetic/runtime/bin/python3.14','-I','-B','-S',
                    '/synthetic/control/assemble.py','--assemble-once','3'*64],
            'cwd':'/synthetic/control',
            'environment':{'LC_ALL':'C','TZ':'UTC',
                           '__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},
        }
        return document

    @staticmethod
    def observation(row):
        return {'path':row['path'],'size':row['size'],'sha256':row['sha256'],
                'identity':(1,2,row['size'],3,4,stat.S_IFREG|0o500,501,1)}

    def test_separate_interpreter_and_entrypoint_bindings_are_admitted(self):
        binding=self.binding();calls=[]
        def observe(row):
            calls.append(row['path']);return self.observation(row)
        admitted=rf.admit_assembly_child_launch(binding,content_hash(binding),observer=observe)
        self.assertEqual(len(calls),6);self.assertEqual(admitted['observations_per_file'],3)
        self.assertEqual(admitted['interpreter_sha256'],'1'*64)
        self.assertEqual(admitted['entrypoint_sha256'],'2'*64)
        self.assertEqual(admitted['entrypoint_index'],4)

    def test_swapped_hashes_changed_files_and_reordered_argv_reject(self):
        mutations=[]
        value=self.binding();value['interpreter_path']='/synthetic/runtime/bin/changed';mutations.append(value)
        value=self.binding();value['entrypoint_path']='/synthetic/control/changed.py';mutations.append(value)
        value=self.binding();value['argv'][0]='/synthetic/runtime/bin/changed';mutations.append(value)
        value=self.binding();value['argv'][4],value['argv'][5]=value['argv'][5],value['argv'][4];mutations.append(value)
        value=self.binding();value['entrypoint_index']=5;mutations.append(value)
        for document in mutations:
            with self.subTest(document=document),self.assertRaises(ValueError):
                rf.validate_assembly_child_launch(document,content_hash(document))
        value=self.binding();value['interpreter_sha256'],value['entrypoint_sha256']=(
            value['entrypoint_sha256'],value['interpreter_sha256'])
        expected=self.binding()
        def actual(row):
            role='interpreter' if row['path']==expected['interpreter_path'] else 'entrypoint'
            return self.observation({'path':expected[role+'_path'],'size':expected[role+'_size'],
                                     'sha256':expected[role+'_sha256']})
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_FILE_IDENTITY'):
            rf.admit_assembly_child_launch(value,content_hash(value),observer=actual)

    def test_hash_role_cannot_be_substituted_during_admission(self):
        binding=self.binding()
        def swapped(row):
            value=self.observation(row)
            value['sha256']=('2'*64 if row['path']==binding['interpreter_path'] else '1'*64)
            return value
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_FILE_IDENTITY'):
            rf.admit_assembly_child_launch(binding,content_hash(binding),observer=swapped)

    def test_post_verification_mutation_rejects(self):
        binding=self.binding();calls={row:0 for row in ('interpreter','entrypoint')}
        def changing(row):
            role='interpreter' if row['path']==binding['interpreter_path'] else 'entrypoint'
            calls[role]+=1;value=self.observation(row)
            if role=='entrypoint' and calls[role]==3:
                value['identity']=value['identity'][:-1]+(2,)
            return value
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_FILE_MUTATION'):
            rf.admit_assembly_child_launch(binding,content_hash(binding),observer=changing)

    def test_mutation_after_admission_and_before_registration_rejects(self):
        binding=self.binding()
        admitted=rf.admit_assembly_child_launch(binding,content_hash(binding),
            observer=self.observation)
        def changed(row):
            value=self.observation(row)
            if row['path']==binding['entrypoint_path']:
                value['identity']=value['identity'][:-1]+(2,)
            return value
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_POST_VERIFICATION_MUTATION'):
            rf.reverify_assembly_child_launch(admitted,observer=changed)
        self.assertTrue(rf.reverify_assembly_child_launch(admitted,observer=self.observation))

    def test_real_file_admission_rejects_symlink_and_detects_hash(self):
        with tempfile.TemporaryDirectory() as root:
            runtime=Path(root)/'python';script=Path(root)/'assemble.py'
            runtime.write_bytes(b'interpreter-bytes');script.write_bytes(b'entrypoint-bytes')
            os.chmod(runtime,0o500);os.chmod(script,0o400)
            binding=self.binding()
            binding['interpreter_path']=str(runtime)
            binding['interpreter_size']=len(b'interpreter-bytes')
            binding['interpreter_sha256']=hashlib.sha256(b'interpreter-bytes').hexdigest()
            binding['entrypoint_path']=str(script)
            binding['entrypoint_size']=len(b'entrypoint-bytes')
            binding['entrypoint_sha256']=hashlib.sha256(b'entrypoint-bytes').hexdigest()
            binding['argv'][0]=str(runtime);binding['argv'][4]=str(script);binding['cwd']=root
            admitted=rf.admit_assembly_child_launch(binding,content_hash(binding))
            self.assertEqual(admitted['status'],'ADMITTED_ASSEMBLY_CHILD_LAUNCH')
            script.unlink();target=Path(root)/'target';target.write_bytes(b'entrypoint-bytes')
            os.chmod(target,0o400);script.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_FILE_IDENTITY'):
                rf.admit_assembly_child_launch(binding,content_hash(binding))

    def test_process_ownership_uses_interpreter_and_binds_script_position(self):
        binding=self.binding()
        admitted=rf.admit_assembly_child_launch(binding,content_hash(binding),
            observer=self.observation)
        observation={'executable':admitted['interpreter_path'],
            'executable_hash':admitted['interpreter_sha256'],
            'argv':tuple(admitted['argv']),'cwd':admitted['cwd']}
        self.assertEqual(rf.assembly_child_ownership_matches(observation,admitted),{
            'executable':True,'executable_hash':True,'argv':True,
            'entrypoint_position':True,'cwd':True})
        observation['executable_hash']=admitted['entrypoint_sha256']
        self.assertFalse(rf.assembly_child_ownership_matches(observation,admitted)['executable_hash'])
        observation['executable_hash']=admitted['interpreter_sha256']
        observation['argv']=tuple(admitted['argv'][:4]+[admitted['argv'][5],admitted['argv'][4],
            *admitted['argv'][6:]])
        self.assertFalse(rf.assembly_child_ownership_matches(observation,admitted)['argv'])

    def test_observed_entrypoint_position_and_admission_mutation_reject(self):
        binding=self.binding()
        admitted=rf.admit_assembly_child_launch(binding,content_hash(binding),observer=self.observation)
        row={'executable':binding['interpreter_path'],'executable_hash':binding['interpreter_sha256'],
             'argv':binding['argv'][:4]+list(reversed(binding['argv'][4:])), 'cwd':binding['cwd']}
        self.assertFalse(rf.assembly_child_ownership_matches(row,admitted)['entrypoint_position'])
        admitted['argv'][5]='--changed'
        with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_ADMISSION_MUTATION'):
            rf.reverify_assembly_child_launch(admitted,observer=self.observation)

    def test_real_file_changes_replacements_and_parent_alias_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            runtime=root/'python';script=root/'assemble.py'
            runtime.write_bytes(b'interpreter-bytes');script.write_bytes(b'entrypoint-bytes')
            binding=self.binding()
            for role,path in (('interpreter',runtime),('entrypoint',script)):
                binding[role+'_path']=str(path)
                binding[role+'_size']=path.stat().st_size
                binding[role+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            binding['argv'][0]=str(runtime);binding['argv'][4]=str(script);binding['cwd']=str(root)
            for path in (runtime,script):
                admitted=rf.admit_assembly_child_launch(binding,content_hash(binding))
                original=path.read_bytes();path.write_bytes(b'X'*len(original))
                with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_FILE_HASH'):
                    rf.reverify_assembly_child_launch(admitted)
                path.write_bytes(original)
                admitted=rf.admit_assembly_child_launch(binding,content_hash(binding))
                replacement=root/'replacement';replacement.write_bytes(original);replacement.replace(path)
                with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_POST_VERIFICATION_MUTATION'):
                    rf.reverify_assembly_child_launch(admitted)
            alias=root/'alias';alias.symlink_to(root,target_is_directory=True)
            binding['entrypoint_path']=str(alias/'assemble.py');binding['argv'][4]=binding['entrypoint_path']
            with self.assertRaisesRegex(ValueError,'ASSEMBLY_CHILD_PATH_SUBSTITUTION'):
                rf.admit_assembly_child_launch(binding,content_hash(binding))
