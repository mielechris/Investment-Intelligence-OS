"""Offline framework policy tests. Native xattr/ACL effects are substituted."""
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
