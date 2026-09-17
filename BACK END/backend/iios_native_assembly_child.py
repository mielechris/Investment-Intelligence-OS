"""Prepared private assembly operation; execution requires separate owner approval.

No pip, installer hooks, network, provider API, subprocess or service operations.
Inputs are admitted before the one exclusive destination is created. Failures
preserve partial artifacts. This creates bytes, never qualification evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import zipfile

R = ACCEPTANCE = QUARANTINE = None
RECEIPT_HASH = None
LIMIT_NS = None
SOURCE = None
STAGE = 'CLI'
FIXED_CODES = frozenset({'INPUT_IDENTITY','INPUT_SHORT','INPUT_GREW','INPUT_RACE','INPUT_HASH',
    'SEAL_ACK_PARENT','SEAL_RECEIPT_SIZE','SEAL_RECEIPT_PARENT','SEAL_FILE_SET','SEAL_METADATA','SEAL_UNEXPECTED_MUTATION','SEAL_IDENTITY','FINAL_METADATA_IDENTITY','BUILD_CLOCK','BUILD_DEADLINE','BUILD_CLEANUP_EXPORT_RESERVE','BUILD_SCOPE','BUILD_ENV','BUILD_FLAGS',
    'BUILD_INTERPRETER','BOOTSTRAP_ACCEPTANCE','BUILD_ROOTS','BUILD_EFFECT_DENIED','BUILD_WRITE_ROOT',
    'BUILD_DESTRUCTIVE_DENIED','LINK_INPUT_CHANGED','LINK_METADATA','PAYLOAD_PIN','BUILD_MEMBER_PATH',
    'BUILD_DIRECTORY_OWNER','STAGING_COMPLETE_IDENTITY','MANIFEST_REVIEW_CEILING','FINAL_PAYLOAD_IDENTITY',
    'BUILD_METADATA_MEMBERSHIP','BUILD_METADATA_CHANGED','BUILD_CLI','BUILD_COPY_MODE','BUILD_COPY_SEAL','BUILD_SOURCE_CHANGED','BUILD_COPY_BOUND','BUILD_COPY_CHANGED','RUNTIME_TREE_MISMATCH',
    'SENSITIVE_DOCUMENT_REJECTED','BUILD_SCHEMA','BUILD_TARGET','BUILD_REQUIRED_FILES','BUILD_PLATFORM_MODE','BUILD_DEPENDENCIES','RUNTIME_TOTAL_BOUND','RUNTIME_OWNER','RUNTIME_FILE_CHANGED','RUNTIME_COPY_METADATA_RACE'})
FIXED_CODES |= frozenset(['BUILD_PARENT_MODE', 'ASSEMBLY_OUTPUT_BINDING', 'ASSEMBLY_OUTPUT_BOUNDARY_MODE', 'ASSEMBLY_OUTPUT_CONTAINMENT', 'ASSEMBLY_OUTPUT_CONTAINMENT_CHANGED', 'ASSEMBLY_OUTPUT_NOT_EMPTY', 'ASSEMBLY_OUTPUT_PARENT_CHANGED', 'ASSEMBLY_OUTPUT_PARENT_IDENTITY', 'ASSEMBLY_OUTPUT_RACE', 'ASSEMBLY_OUTPUT_SCOPE'])
FIXED_CODES |= frozenset({'RUNTIME_LAYOUT_POLICY','RUNTIME_IMPORT_CLOSURE','RUNTIME_FORBIDDEN_IMPORT',
    'RUNTIME_EXCLUSION_ALIAS','RUNTIME_EXCLUSION_MISSING','RUNTIME_EXCLUDED_CONTENT',
    'RUNTIME_REQUIRED_CODE_MISSING','RUNTIME_PRODUCTION_POLICY'})


# Artifact-only adapter: reuse the admitted physical-link verifier, never the
# Linux-only os.listxattr surface and never follow a framework alias.
LINK_PREDICATES = frozenset({'LINK_POLICY','LINK_OWNER','LINK_IDENTITY','LINK_TARGET',
    'LINK_PARENT_CHANGED','LINK_METADATA_PIN','RUNTIME_LINK_METADATA_PLATFORM',
    'RUNTIME_LINK_CHANGED','RUNTIME_LINK_METADATA','RUNTIME_LINK_METADATA_CHANGED',
    'RUNTIME_XATTR_LIST','RUNTIME_XATTR_RACE','RUNTIME_XATTR_NAME','RUNTIME_XATTR_BOUND',
    'RUNTIME_PROVENANCE_FORMAT','RUNTIME_ACL_ABI','RUNTIME_ACL_READ',
    'RUNTIME_ACL_NOT_ABSENT','RUNTIME_ACL_CHANGED','RUNTIME_ACL_INVALID','RUNTIME_ACL_PRESENT',
    'RUNTIME_METADATA_PLATFORM','BUILD_EFFECT_DENIED','BUILD_WRITE_ROOT','BUILD_DESTRUCTIVE_DENIED'})

class LinkInspectionError(ValueError):
    def __init__(self, error, stage, api, link):
        import errno
        code = error.args[0] if error.args and type(error.args[0]) is str else None
        number = error.errno if isinstance(error, OSError) and type(error.errno) is int and 0 <= error.errno <= 4095 else None
        if isinstance(error, (AttributeError, NotImplementedError)):
            category = 'API_UNAVAILABLE_OR_UNSUPPORTED'
        elif code in {'BUILD_EFFECT_DENIED','BUILD_WRITE_ROOT','BUILD_DESTRUCTIVE_DENIED'}:
            category = 'ATTRIBUTABLE_APPLICATION_AUDIT_DENIAL'
        elif number in (errno.EACCES, errno.EPERM): category = 'ACCESS_DENIED_UNATTRIBUTED'
        elif number in (errno.ENOTSUP, errno.ENOSYS): category = 'API_UNAVAILABLE_OR_UNSUPPORTED'
        elif code in {'LINK_PARENT_CHANGED','RUNTIME_LINK_CHANGED','RUNTIME_LINK_METADATA_CHANGED','RUNTIME_XATTR_RACE','RUNTIME_ACL_CHANGED'}:
            category = 'RACE_DETECTED'
        elif code in {'LINK_METADATA_PIN','RUNTIME_LINK_METADATA','RUNTIME_XATTR_NAME','RUNTIME_PROVENANCE_FORMAT'}:
            category = 'METADATA_MISMATCH'
        elif code in LINK_PREDICATES: category = 'PREDICATE_REJECTED'
        else: category = 'UNKNOWN'
        super().__init__('LINK_INSPECTION_FAILED')
        self.diagnostic = dict(stage=stage,api=api,follow_symlinks=False,
            inode_access='O_SYMLINK_DESCRIPTOR' if stage=='METADATA_READ' else 'NOFOLLOW_PARENT_RELATIVE',
            predicate=code if code in LINK_PREDICATES else 'UNKNOWN',
            errno=number,errno_status='OBSERVED_EXCEPTION_ERRNO' if number is not None else 'NOT_AVAILABLE',
            category=category,exception_type=type(error).__name__ if type(error) in
            (ValueError,TypeError,AttributeError,NotImplementedError,OSError,PermissionError,FileNotFoundError) else 'OTHER',
            path_sha256=hashlib.sha256(link['path'].encode()).hexdigest(),target_sha256=link['sha256'])

def verify_link(parent, link, expected_metadata, creation_provenance=None):
    import alpha_runtime_files as rf
    from alpha_session_evidence import identity
    stage='POLICY';api='validate_layout_policy'
    try:
        need(link in rf.layout_policy()['links'], 'LINK_POLICY')
        name=link['path'].split('/')[-1]
        stage='PARENT_IDENTITY';api='os.fstat'
        before_parent=identity(os.fstat(parent))
        stage='LINK_IDENTITY';api='os.stat(follow_symlinks=False)'
        before=os.stat(name,dir_fd=parent,follow_symlinks=False)
        need(before.st_uid==os.getuid(),'LINK_OWNER')
        need(stat.S_ISLNK(before.st_mode) and before.st_nlink==1 and
             before.st_size==len(link['target'].encode()),'LINK_IDENTITY')
        stage='TARGET';api='os.readlink'
        need(os.readlink(name,dir_fd=parent)==link['target'],'LINK_TARGET')
        stage='METADATA_READ';api='alpha_runtime_files._link_metadata:O_SYMLINK/flistxattr/fgetxattr/ACL'
        observed=rf._link_metadata(parent,name,before)
        stage='METADATA_PIN';api='independent_metadata_digest_comparison'
        permitted=[expected_metadata]
        if creation_provenance is not None and 'com.apple.provenance' not in expected_metadata:
            permitted.append(dict(expected_metadata,**{'com.apple.provenance':creation_provenance}))
        need(observed in permitted,'LINK_METADATA_PIN')
        stage='RECHECK';api='os.stat/os.readlink/os.fstat'
        need(identity(os.stat(name,dir_fd=parent,follow_symlinks=False))==identity(before) and
             os.readlink(name,dir_fd=parent)==link['target'],'RUNTIME_LINK_CHANGED')
        need(identity(os.fstat(parent))==before_parent,'LINK_PARENT_CHANGED')
        return observed
    except Exception as error:
        raise LinkInspectionError(error,stage,api,link) from None

def failure_category(error):
    code=error.args[0] if error.args and type(error.args[0]) is str else None
    result={'status':'STOP','stage':STAGE,'category':code if code in FIXED_CODES else 'UNCLASSIFIED_ERROR',
        'exception_type':type(error).__name__ if type(error) in (ValueError,TypeError,TimeoutError,PermissionError,
            OSError,FileExistsError,FileNotFoundError,ImportError,ModuleNotFoundError) else 'OTHER',
        'production_qualified':False,'broker_connected':False,'paper_order_permission':False,
        'trade_execution_permission':False,'live_execution':False}
    if type(error) is LinkInspectionError:
        result.update(category='LINK_INSPECTION_FAILED',exception_type='LinkInspectionError',link=error.diagnostic)
    module=sys.modules.get('alpha_runtime_files')
    kind=getattr(module,'RuntimeMetadataCopyError',None)
    if kind is not None and type(error) is kind:
        result.update(category=error.args[0],exception_type='RuntimeMetadataCopyError',metadata=error.diagnostic)
    row=getattr(error,'copy_file_identity',None)
    if type(row) is dict and set(row)=={'sha256','size','path_sha256'} and all(
        type(row[k]) is str and len(row[k])==64 and all(c in '0123456789abcdef' for c in row[k])
        for k in ('sha256','path_sha256')) and type(row['size']) is int and 0<=row['size']<=64*1024*1024:
        result['file_identity']=row
    if getattr(error,'copy_cleanup_failure',None)=='BUILD_COPY_SEAL':
        result['cleanup_failure']='BUILD_COPY_SEAL'
    return result

def need(value, code):
    if not value: raise ValueError(code)

def raw_pin(path, expected, maximum=64*1024*1024):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1 and
             0<=before.st_size<=maximum,'INPUT_IDENTITY')
        chunks=[];left=before.st_size
        while left:
            part=os.read(fd,min(65536,left));need(bool(part),'INPUT_SHORT');chunks.append(part);left-=len(part)
        need(not os.read(fd,1),'INPUT_GREW')
        after=os.fstat(fd);last=os.stat(path,follow_symlinks=False)
        key=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_uid,s.st_mode,s.st_nlink)
        need(key(before)==key(after)==key(last),'INPUT_RACE')
        raw=b''.join(chunks);need(hashlib.sha256(raw).hexdigest()==expected,'INPUT_HASH');return raw
    finally:os.close(fd)

def check_clock(start,deadline,now):
    need(all(type(x) is int and 0<x<2**63 for x in (start,deadline,now)),'BUILD_CLOCK')
    need(deadline-start==LIMIT_NS and start<=now<deadline,'BUILD_DEADLINE')

def deny_external_effects(event,args):
    if event.startswith(('socket.','subprocess.','os.exec','os.spawn')) or event in ('os.system','os.kill','os.killpg'):
        raise PermissionError('BUILD_EFFECT_DENIED')

def metadata_matches(actual,expected,creation_provenance):
    need(set(actual)==set(expected),'BUILD_METADATA_MEMBERSHIP')
    for name,values in actual.items():
        original=expected[name]
        permitted=[original]
        if 'com.apple.provenance' not in original:
            permitted.append(dict(original,**{'com.apple.provenance':creation_provenance}))
        need(values in permitted,'BUILD_METADATA_CHANGED')

def parent_fd(root_fd,name,create=False):
    parts=name.split('/')
    need(all(p and p not in ('.','..') and '\x00' not in p and '\\' not in p for p in parts),'BUILD_MEMBER_PATH')
    current=os.dup(root_fd)
    try:
        for part in parts[:-1]:
            if create:
                try:os.mkdir(part,0o700,dir_fd=current)
                except FileExistsError:pass
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
            need(os.fstat(nxt).st_uid==os.getuid(),'BUILD_DIRECTORY_OWNER')
            os.close(current);current=nxt
        return current,parts[-1]
    except BaseException:os.close(current);raise

def exclusive_bytes(root_fd,row,raw):
    need(len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'PAYLOAD_PIN')
    parent,name=parent_fd(root_fd,row['path'],True)
    try:
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,row['mode'],dir_fd=parent)
        with os.fdopen(fd,'wb') as out:
            out.write(raw);out.flush();os.fchmod(out.fileno(),row['mode']);os.fsync(out.fileno())
        os.fsync(parent)
    finally:os.close(parent)


def main(expected, budget_parent,configuration):
    global STAGE,R,ACCEPTANCE,QUARANTINE,RECEIPT_HASH,LIMIT_NS,SOURCE
    R=Path(configuration['boundary']);ACCEPTANCE=Path(configuration['acceptance']);QUARANTINE=Path(configuration['quarantine'])
    RECEIPT_HASH=configuration['bootstrap_receipt_parent'];SOURCE=configuration['source'];LIMIT_NS=configuration['total_ns']
    STAGE='PREFLIGHT'
    # Fresh private assembly budget, not a reset of the consumed acceptance run.
    budget=json.loads(raw_pin(R/'ASSEMBLY-CLOCK.json',budget_parent,4096))
    need(set(budget)=={'basis','start_ns','deadline_ns','source_commit'} and budget['basis']=='DARWIN_CLOCK_MONOTONIC_RAW_NS' and budget['source_commit']==SOURCE,'BUILD_CLOCK')
    started=budget['start_ns'];deadline=budget['deadline_ns'];check_clock(started,deadline,time.clock_gettime_ns(6))
    def check():
        now=time.clock_gettime_ns(6);check_clock(started,deadline,now)
        need(now<configuration['work_end'],'BUILD_CLEANUP_EXPORT_RESERVE')
    plan=json.loads(raw_pin(R/'ASSEMBLY-PLAN-v3.json',expected,8_000_000))
    need(plan['schema']=='iios-production-assembly-preparation-v2' and
         plan['scope']=='PRODUCTION_RUNTIME_ASSEMBLY_PREPARATION_ONLY','BUILD_SCOPE')
    need(dict(os.environ)=={'LC_ALL':'C','TZ':'UTC','__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},'BUILD_ENV')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'BUILD_FLAGS')
    boot=Path(plan['bootstrap_root'])
    need(sys.executable==str(boot/'bin/python3.14'),'BUILD_INTERPRETER')
    accepted=json.loads(raw_pin(ACCEPTANCE/'execution-output/FINAL-ACCEPTANCE.json',RECEIPT_HASH))
    need(accepted['bootstrap_accepted'] is True and accepted['status']=='PASS_BOOTSTRAP_IDENTITY_ONLY' and
         accepted['tree_parent']==plan['bootstrap_tree_parent'] and all(accepted['acceptance_comparisons'].values()),'BOOTSTRAP_ACCEPTANCE')
    for row in plan['source_files']:raw_pin(R/'control'/row['path'],row['sha256'])
    for row in plan['platform_references']:raw_pin(Path(row['path']),row['sha256'])
    raw_pin(Path(plan['creation_provenance']['evidence']),plan['creation_provenance']['evidence_sha256'])
    # Deny external effects before importing any IIOS build code. No provider or
    # credential entrypoint is called; the build scope grants no such authority.
    sys.addaudithook(deny_external_effects)
    # These are exact frozen IIOS source copies, not a historical site-packages import.
    sys.path.insert(0,str(R/'control'))
    STAGE='BUILD_CONTROL_IMPORTS'
    from alpha_runtime_files import verify_runtime_tree,inventory_runtime,extension,copy_runtime_metadata,verify_manifest
    from alpha_production_runtime import copy_row,assemble,directory
    from provider_gateway_contract import content_hash,canonical
    from alpha_runtime_bootstrap import admit_build_control
    evidence=json.loads(raw_pin(R/'BUILD-CONTROL-REVIEW.json',plan['build_control_review_sha256']))
    STAGE='BUILD_CONTROL_ADMISSION'
    admit_build_control(evidence,content_hash(evidence),**plan['build_control_parents'])
    seal=json.loads(raw_pin(ACCEPTANCE/'pins/FINAL-SEALED-BOOTSTRAP.json',plan['bootstrap_seal_sha256']))
    verify_runtime_tree(str(boot),seal['files'],approved_root=str(boot),**extension(seal));check()
    lock=raw_pin(R/'production-python-requirements.lock',plan['lock_sha256'])
    # Read each complete wheel once, independently hash it, then operate on those
    # in-memory bytes. No path can be substituted between hash and extraction.
    import io
    archives={}
    for wheel in plan['wheel_members']:
        check();archives[wheel['wheel']]=raw_pin(QUARANTINE/wheel['wheel'],wheel['sha256'])
    roots=plan['roots'];output_binding=plan['assembly_output_parent'];execution=Path(output_binding['execution_path'])
    need(output_binding['boundary_path']==str(R) and execution==R/'assembly-output/execution-01','BUILD_ROOTS')
    need(roots=={'execution':str(execution),'staging':str(execution/'staging'),
        'output_parent':str(execution/'output'),'runtime':str(execution/'output/runtime-pilot'),
        'release':str(execution/'release'),'qualification_control':str(execution/'control'),
        'disposable_output':str(execution/'disposable')},'BUILD_ROOTS')
    # No subprocess is admitted, and all new filesystem mutations are confined
    # to this exclusive tree. This Python guard is NOT OS confinement proof.
    prefix=str(execution)+'/'
    def within(p):return type(p) is str and (p==str(execution) or p.startswith(prefix)) and '..' not in p.split('/')
    def audit(event,args):
        deny_external_effects(event,args)
        if event=='open' and not isinstance(args[0],int):
            flags=args[2] or 0
            if flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
                # FD-relative writes in the existing assembler are allowed only
                # through its already admitted descriptors, never absolute escape.
                p=os.fspath(args[0]);need(within(p) or (not p.startswith('/') and '..' not in p.split('/')),'BUILD_WRITE_ROOT')
        if event in ('os.remove','os.rmdir','os.rename','os.link'):raise PermissionError('BUILD_DESTRUCTIVE_DENIED')
    sys.addaudithook(audit)
    STAGE='EXCLUSIVE_OUTPUT'
    from alpha_runtime_files import open_assembly_output_parent
    root_fd=open_assembly_output_parent(output_binding,plan['assembly_output_parent_parent'])
    try:
        os.mkdir('execution-01',0o700,dir_fd=root_fd)
        parent_now=os.stat(output_binding['parent_path'],follow_symlinks=False)
        held=os.fstat(root_fd)
        expected_parent=output_binding['parent_identity']
        need((parent_now.st_dev,parent_now.st_ino,parent_now.st_uid,parent_now.st_mode)==(held.st_dev,held.st_ino,held.st_uid,held.st_mode)==(expected_parent[0],expected_parent[1],expected_parent[6],expected_parent[5]),'ASSEMBLY_OUTPUT_RACE')
    finally:os.close(root_fd)
    stage=execution/'staging';efd=os.open(execution,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        os.mkdir('staging',0o700,dir_fd=efd);os.mkdir('output',0o700,dir_fd=efd)
    finally:os.close(efd)
    with (execution/'ATTEMPT-STARTED.json').open('x') as out:
        json.dump({'scope':'PRIVATE_ASSEMBLY_BYTES_ONLY','plan_parent':expected,'start_ns':started,'deadline_ns':deadline},out)
    STAGE='BOOTSTRAP_COPY'
    infd=os.open(boot,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    outfd=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    planned_names={row['path'] for row in plan['planned_files']}
    try:
        for row in seal['files']:
            if row['path'] not in planned_names:
                continue
            check();copy_row(infd,outfd,row,metadata=seal['metadata'][row['path']])
    finally:os.close(infd);os.close(outfd)
    STAGE='BOOTSTRAP_LINKS'
    for link in plan['layout_policy']['links']:
        check()
        infd=os.open(boot,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        outfd=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            src_parent,src_name=parent_fd(infd,link['path'])
            try:
                verify_link(src_parent,link,seal['metadata'][link['path']])
                dst_parent,dst_name=parent_fd(outfd,link['path'],True)
                try:
                    os.symlink(link['target'],dst_name,dir_fd=dst_parent)
                    verify_link(dst_parent,link,seal['metadata'][link['path']],plan['creation_provenance']['attribute'])
                    verify_link(src_parent,link,seal['metadata'][link['path']])
                finally:os.close(dst_parent)
            finally:os.close(src_parent)
        finally:os.close(infd);os.close(outfd)
    def write_row(row,raw):
        check();fd=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:exclusive_bytes(fd,row,raw)
        finally:os.close(fd)
    STAGE='WHEEL_AND_SOURCE_COPY'
    for wheel in plan['wheel_members']:
        with zipfile.ZipFile(io.BytesIO(archives[wheel['wheel']])) as z:
            for row in wheel['rows']:write_row(row,z.read(row['path'].removeprefix('lib/python3.14/site-packages/')))
    for row in plan['source_files']:
        write_row(dict(path='iios_source/'+row['path'],size=row['size'],sha256=row['sha256'],mode=0o400),
                  raw_pin(R/'control'/row['path'],row['sha256']))
    # Preserve original directory xattrs; new entries must have no metadata.
    files=set(planned_names);links={x['path'] for x in plan['layout_policy']['links']}
    for name,meta in plan['anticipated_metadata'].items():
        if name in files or name in links:continue
        if name=='runtime-manifest.json' or name not in seal['metadata']:continue
        aroot=os.open(boot,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        broot=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            a=os.dup(aroot) if name=='.' else parent_fd(aroot,name+'/__metadata_only')[0]
            try:
                b=os.dup(broot) if name=='.' else parent_fd(broot,name+'/__metadata_only')[0]
                try:copy_runtime_metadata(a,b,meta)
                finally:os.close(b)
            finally:os.close(a)
        finally:os.close(aroot);os.close(broot)
    directories=set()
    for row in plan['planned_files']:
        parts=row['path'].split('/');directories.update('/'.join(parts[:i]) for i in range(1,len(parts)))
    for name in sorted(directories,key=lambda x:(-x.count('/'),x)):
        rootfd=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            parent,leaf=parent_fd(rootfd,name)
            try:
                fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                try:os.fchmod(fd,0o500)
                finally:os.close(fd)
            finally:os.close(parent)
        finally:os.close(rootfd)
    os.chmod(stage,0o500);check()
    STAGE='STAGING_VERIFICATION'
    observed=inventory_runtime(str(stage),plan['layout_policy'],plan['layout_parent'],approved_root=str(stage))
    expected_meta=dict(plan['anticipated_metadata']);expected_meta.pop('runtime-manifest.json')
    need(observed['files']==plan['planned_files'],'STAGING_COMPLETE_IDENTITY')
    metadata_matches(observed['metadata'],expected_meta,plan['creation_provenance']['attribute'])
    STAGE='RESOURCE_SEAL_HANDOFF'
    staging=dict(schema='iios-resource-seal-handoff-v1',source_commit=plan['source_base'],
        plan_parent=expected,budget_parent=budget_parent,observed=observed,
        bootstrap_parent=RECEIPT_HASH,production_qualified=False)
    with (execution/'STAGING-RESULT.json').open('xb') as out:out.write(canonical(staging))
    os.chmod(execution/'STAGING-RESULT.json',0o400)
    # Only the independently owned outer supervisor may perform the pinned OS
    # sealing command. This child never gains subprocess or network authority.
    while not (execution/'RESOURCE-SEAL-ACK.json').exists():
        check();time.sleep(.02)
    STAGE='RESOURCE_SEAL_VERIFICATION'
    from iios_native_seal_protocol import read_owned_json
    ack,_=read_owned_json(execution/'RESOURCE-SEAL-ACK.json',4096)
    need(set(ack)=={'receipt_sha256','receipt_size','staging_parent','budget_parent'} and
        ack['staging_parent']==hashlib.sha256(canonical(staging)).hexdigest() and
        ack['budget_parent']==budget_parent,'SEAL_ACK_PARENT')
    receipt_raw=raw_pin(execution/'RESOURCE-SEAL-RECEIPT.json',ack['receipt_sha256'],32768)
    need(len(receipt_raw)==ack['receipt_size'],'SEAL_RECEIPT_SIZE')
    receipt=json.loads(receipt_raw)
    need(receipt['source_commit']==plan['source_base'] and receipt['staging_parent']==ack['staging_parent'] and
        receipt['budget_parent']==budget_parent and receipt['status']=='PASS_BOTTOM_UP_RESOURCE_SEAL_ONLY' and
        receipt['production_qualified'] is False and receipt['seal_kind']=='IIOS_BOTTOM_UP_ADHOC_RESOURCE_SEAL','SEAL_RECEIPT_PARENT')
    sealed=inventory_runtime(str(stage),plan['layout_policy'],plan['layout_parent'],approved_root=str(stage))
    from iios_native_seal_protocol import verify_seal_delta
    verify_seal_delta(observed,sealed,receipt)
    observed=sealed
    spec=dict(schema='iios-completed-runtime-build-input-v3',source_commit=plan['source_base'],input_root=str(stage),
        output_parent=roots['output_parent'],output_name='runtime-pilot',files=observed['files'],interpreter='bin/python3.14',
        tls_bundle=plan['tls_bundle'],platform_dependencies=plan['platform_references'],provenance={'distribution':plan['layout_policy']['distribution_sha256'],
        'build_recipe':expected,'toolchain':plan['bootstrap_receipt_sha256'],'dependency_artifacts':plan['wheel_manifest_sha256'],
        'closure_review':plan['closure_review_sha256']},lock_sha256=plan['lock_sha256'],python_version='3.14.7',system='Darwin',
        architecture='arm64',layout_policy=plan['layout_policy'],layout_parent=plan['layout_parent'],metadata=observed['metadata'])
    from alpha_runtime_files import sealed_payload_parent
    spec['completion']=dict(dependency_lock_sha256=plan['lock_sha256'],
        bootstrap_acceptance_sha256=RECEIPT_HASH,bootstrap_tree_sha256=plan['bootstrap_seal_sha256'],
        vendor_distribution_sha256=plan['layout_policy']['distribution_sha256'],
        vendor_signature_receipt_sha256=receipt['vendor_signature_receipt_sha256'],
        assembly_seal_receipt_sha256=ack['receipt_sha256'],assembly_seal_kind='IIOS_ADHOC_RESOURCE_SEAL',
        host_contract=receipt['host_contract'],sealed_payload_sha256=sealed_payload_parent(spec))
    # Platform references are verified evidence documents, not fictitious disk
    # copies of shared-cache images. Native library acceptance remains separate.
    with (execution/'BUILD-INPUT.json').open('xb') as out:out.write(canonical(spec))
    STAGE='ASSEMBLER'
    result=assemble(spec,content_hash(spec),source_commit=plan['source_base'],approved_input_root=str(stage),
        approved_output_parent=roots['output_parent'],approved_platform_paths=tuple(x['path'] for x in plan['platform_references']),lock_bytes=lock,expected_lock_hash=plan['lock_sha256'])
    STAGE='FINAL_STATIC_VERIFICATION'
    check();manifest=result['manifest'];need(len(canonical(manifest))<=4*1024*1024,'MANIFEST_REVIEW_CEILING')
    need(manifest['file_inventory']==observed['files'],'FINAL_PAYLOAD_IDENTITY')
    need(manifest['metadata']==observed['metadata'],'FINAL_METADATA_IDENTITY')
    verify_manifest(roots['runtime'],manifest,source_commit=plan['source_base'])
    verify_runtime_tree(str(boot),seal['files'],approved_root=str(boot),**extension(seal));check()
    result.update(scope='PRIVATE_ASSEMBLY_BYTES_ONLY',candidate_inventory_sha256=plan['candidate_inventory_sha256'],
        bootstrap_parent=RECEIPT_HASH,seconds=(time.clock_gettime_ns(6)-started)/1e9,provider_access=False,
        credential_access=False,broker_connected=False,paper_order_permission=False,trade_execution_permission=False,live_execution=False)
    STAGE='PUBLICATION'
    with (execution/'ASSEMBLY-RESULT.json').open('xb') as out:out.write(canonical(result))
    check();print(json.dumps({'status':result['status'],'scope':result['scope'],'seconds':result['seconds']}))
