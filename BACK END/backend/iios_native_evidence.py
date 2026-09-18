"""Exclusive run roots, stable input pins and complete sealed evidence inventories."""
import hashlib
import json
import os
from pathlib import Path
import stat
from iios_native_conductor import canonical,digest,pin_file,require,STAGES


def owned_directory(path):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts,'CONDUCTOR','ABSOLUTE_LEXICAL_ROOT')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        st=os.fstat(fd)
        require(st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o700,'CONDUCTOR','OWNER_ONLY_ROOT')
        return fd
    except BaseException:os.close(fd);raise


def fresh_root(parent,name,expected_identity):
    require(type(name) is str and name.startswith('qualification-') and '/' not in name and '..' not in name,'CONDUCTOR','FRESH_ROOT_NAME')
    fd=owned_directory(parent)
    try:
        before=os.fstat(fd)
        require([before.st_dev,before.st_ino,before.st_uid,stat.S_IMODE(before.st_mode)]==expected_identity,'CONDUCTOR','OUTPUT_PARENT_IDENTITY')
        os.mkdir(name,0o700,dir_fd=fd)
        child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            info=os.fstat(child)
            require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'CONDUCTOR','FRESH_ROOT_MODE')
        finally:os.close(child)
        current=owned_directory(parent)
        try:
            observed=os.fstat(current)
            require((before.st_dev,before.st_ino,before.st_uid,before.st_mode)==(observed.st_dev,observed.st_ino,observed.st_uid,observed.st_mode),'CONDUCTOR','OUTPUT_PARENT_REPLACED')
            rebound=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
            try:
                actual=os.fstat(rebound)
                require((info.st_dev,info.st_ino,info.st_uid,info.st_mode)==(actual.st_dev,actual.st_ino,actual.st_uid,actual.st_mode),'CONDUCTOR','OUTPUT_ROOT_REPLACED')
            finally:os.close(rebound)
        finally:os.close(current)
        return Path(parent)/name
    finally:os.close(fd)


def put(root,name,value):
    require('/' not in name and name not in ('.','..'),'CONDUCTOR','RECORD_NAME')
    fd=owned_directory(root)
    try:
        output=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(output,'wb') as stream:stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
        os.fsync(fd)
    finally:os.close(fd)


def inventory(root,*,exclude=()):
    root=Path(root);rows=[]
    for path in sorted(root.rglob('*')):
        relative=str(path.relative_to(root))
        if relative in exclude:continue
        st=path.lstat()
        require(not stat.S_ISLNK(st.st_mode),STAGES[-1],'EXPORT_SYMLINK')
        if stat.S_ISDIR(st.st_mode):continue
        require(stat.S_ISREG(st.st_mode),STAGES[-1],'EXPORT_REGULAR_FILE')
        before=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        h=hashlib.sha256(path.read_bytes()).hexdigest();after=path.lstat()
        require(before==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),STAGES[-1],'EXPORT_FILE_MUTATION')
        rows.append({'path':relative,'size':st.st_size,'sha256':h})
    return rows


def verify_inventory(root,rows,*,exclude=()):
    require(inventory(root,exclude=exclude)==rows,STAGES[-1],'COMPLETE_EVIDENCE_INVENTORY')


def export(root,report,deadline,clock):
    require(clock()<deadline,STAGES[-1],'EXPORT_DEADLINE')
    put(root,'REPORT.json',report)
    rows=inventory(root,exclude=('INVENTORY.json','EXPORT.json'))
    put(root,'INVENTORY.json',{'manifest':report['manifest'],'files':rows})
    verify_inventory(root,rows,exclude=('INVENTORY.json','EXPORT.json'))
    require(clock()<deadline,STAGES[-1],'EXPORT_DEADLINE')
    put(root,'EXPORT.json',{'manifest':report['manifest'],'inventory_sha256':hashlib.sha256((Path(root)/'INVENTORY.json').read_bytes()).hexdigest(),
                            'report_sha256':hashlib.sha256((Path(root)/'REPORT.json').read_bytes()).hexdigest(),'deadline_ns':deadline,'verified_at_ns':clock()})
    require(clock()<deadline,STAGES[-1],'EXPORT_DEADLINE')
    verify_export(root,report['manifest'])


def verify_export(root,manifest):
    root=Path(root);seal=json.loads((root/'EXPORT.json').read_bytes());index=json.loads((root/'INVENTORY.json').read_bytes())
    require(seal['manifest']==index['manifest']==manifest,STAGES[-1],'EXPORT_PARENT')
    pin_file(root/'INVENTORY.json',seal['inventory_sha256']);pin_file(root/'REPORT.json',seal['report_sha256'])
    require(seal['verified_at_ns']<seal['deadline_ns'],STAGES[-1],'EXPORT_DEADLINE')
    verify_inventory(root,index['files'],exclude=('INVENTORY.json','EXPORT.json'))
    report=json.loads((root/'REPORT.json').read_bytes())
    binding=report.get('admission_stage_receipt')
    if binding is not None:
        require(binding['path']=='ADMISSION-STAGE-RECEIPT.json',STAGES[-1],'FAILURE_RECEIPT_PATH')
        pin_file(root/binding['path'],binding['sha256'])
        receipt=json.loads((root/binding['path']).read_bytes())
        require(receipt['manifest']==manifest and receipt['nonce']==report['nonce'] and receipt['status']==report['status']=='RED'
                and receipt['failure']==report['primary_failure'] and receipt['workload_cleanup']==report['workload_cleanup']
                and receipt['helper_cleanup']==report['helper_cleanup'],STAGES[-1],'FAILURE_RECEIPT_BINDING')
    return report


def export_admission_failure(manifest,parent,detail,initial_start,clock,*,before_dispatcher=False,audit_receipt=None):
    """Bound early audit failures when no execution root exists; never overwrite.

    Called only after explicit manifest admission and native-audit installation.
    No stage, process inspection, child, signal or cleanup action is executed.
    Storage failure remains a separate failure, never a fabricated export pass.
    """
    require(digest(manifest)==parent,STAGES[0],'FAILURE_EXPORT_MANIFEST')
    deadline=initial_start+manifest['limits']['total_ns']
    require(clock()<deadline,STAGES[-1],'EXPORT_DEADLINE')
    root=fresh_root(manifest['output_parent'],manifest['output_name'],manifest['output_parent_identity'])
    receipt={'schema':'IIOS_EARLY_ADMISSION_STAGE_RECEIPT_V1','stage':detail['stage'],'status':'RED',
        'manifest':parent,'nonce':manifest['nonce'],'source':digest(manifest['source']),
        'audit_parent':digest(audit_receipt) if audit_receipt is not None else None,'failure':dict(detail),
        'workload_cleanup':'NOT_APPLICABLE_NO_CHILD_CREATED' if before_dispatcher else 'NOT_ESTABLISHED',
        'helper_cleanup':'NOT_ESTABLISHED','before_dispatcher':before_dispatcher}
    put(root,'ADMISSION-STAGE-RECEIPT.json',receipt)
    report={'schema':'iios-native-qualification-conductor-v1','manifest':parent,'nonce':manifest['nonce'],
        'admission_stage_receipt':{'path':'ADMISSION-STAGE-RECEIPT.json','sha256':digest(receipt)},
        'workload_cleanup':receipt['workload_cleanup'],'helper_cleanup':receipt['helper_cleanup'],
        'status':'RED','completed_stages':[],'primary_failure':dict(detail),'secondary_failures':[],
        'cleanup_failures':[],'cleanup_receipt':None,'cleanup_classification':'NOT_ESTABLISHED',
        'read_only_retry_failures':[],'history':manifest['history'],'authority':manifest['authority'],
        'provider_pilot_authorized':False,'full_market_day_authorized':False,
        'record_kind':'EARLY_ADMISSION_FAILURE_WITH_STAGE_RECEIPT'}
    export(root,report,deadline,clock)
    return report
