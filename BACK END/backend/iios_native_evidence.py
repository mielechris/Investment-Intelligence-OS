"""Exclusive run roots, stable input pins and complete sealed evidence inventories."""
import hashlib
import json
import os
from pathlib import Path
import stat
from iios_native_conductor import canonical,digest,pin_file,require,STAGES,QualificationFailure,failure


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


def closed_paths(manifest):
    source_root=Path(manifest['source']['root']);require(source_root.is_absolute() and '..' not in source_root.parts,STAGES[0],'CLOSED_SOURCE_ROOT')
    rows=[]
    for row in manifest['source']['inventory']:
        relative=Path(row['relative']);require(not relative.is_absolute() and '..' not in relative.parts and str(relative)==row['relative'],STAGES[0],'SOURCE_INVENTORY_PATH')
        rows.append({'path':str(source_root/relative),'sha256':row['sha256']})
    for key in ('ci','dispatcher'):
        if key in manifest:rows.append(manifest[key])
    rows.extend({'path':p,'sha256':h} for p,h in manifest.get('tool_pins',{}).items())
    rows+=manifest['inputs']+manifest['historical_records'];expected={}
    index_path=manifest.get('execution_inventory',{}).get('path')
    for row in rows:
        path=row['path'];p=Path(path)
        require(type(path) is str and p.is_absolute() and '..' not in p.parts and str(p)==path,STAGES[0],'CLOSED_INPUT_PATH')
        if path==index_path:continue
        require(path not in expected or expected[path]==row['sha256'],STAGES[0],'CLOSED_INPUT_CONFLICT')
        expected[path]=row['sha256']
    return expected


def directory_identity(path):
    """No-follow traversal and stable directory metadata, without enumeration."""
    p=Path(path);require(p.is_absolute() and '..' not in p.parts and str(p)==str(path),STAGES[0],'CLOSED_DIRECTORY_PATH')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);held=[]
    key=lambda s:[s.st_dev,s.st_ino,s.st_uid,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
    try:
        for part in p.parts[1:]:
            before=os.stat(part,dir_fd=fd,follow_symlinks=False)
            require(stat.S_ISDIR(before.st_mode),STAGES[0],'CLOSED_DIRECTORY_TYPE')
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            try:require(key(before)==key(os.fstat(child)),STAGES[0],'CLOSED_DIRECTORY_RACE')
            except BaseException:os.close(child);raise
            held.append((fd,part,child,key(before)));fd=child
        result=key(os.fstat(fd))
        for parent,name,child,original in reversed(held):
            # Shared ancestor entry times may change for unrelated users. Their
            # containment/ownership identity must still remain exact.
            require(original[:4]==key(os.fstat(child))[:4]==key(os.stat(name,dir_fd=parent,follow_symlinks=False))[:4],STAGES[0],'CLOSED_DIRECTORY_CONTAINMENT')
        require(result==key(os.fstat(fd)),STAGES[0],'CLOSED_DIRECTORY_RACE')
        return result
    finally:
        os.close(fd)
        for parent,_,_,_ in reversed(held):os.close(parent)


def closed_guard_paths(manifest,paths):
    roots=[Path(p) for p in manifest['closed_input_roots']]
    require(roots and len(set(roots))==len(roots) and all(p.is_absolute() and '..' not in p.parts for p in roots),STAGES[0],'CLOSED_ROOTS')
    guards={str(p) for path in paths for p in Path(path).parents if any(p==r or r in p.parents for r in roots)}|{str(r) for r in roots}
    for name in manifest.get('closed_extra_directories',[]):
        p=Path(name);require(p.is_absolute() and '..' not in p.parts and any(p==r or r in p.parents for r in roots),STAGES[0],'CLOSED_EXTRA_DIRECTORY_SCOPE')
        guards.add(name)
    return sorted(guards)


def build_closed_inventory(manifest):
    """Preparation only: capture metadata for already declared paths, no discovery."""
    expected=closed_paths(manifest);directories={};files=[]
    guards={p:directory_identity(p) for p in closed_guard_paths(manifest,expected)}
    for path,parent in sorted(expected.items()):
        result=pin_file(path,parent,metadata=True)
        row={'path':path,'sha256':parent,'size':result['size'],'identity':list(result['identity'])};files.append(row)
        ancestors=list(reversed(Path(path).parents))[1:]
        for p,identity in zip(ancestors,result['ancestors']):
            identity=list(identity)
            require(str(p) not in directories or directories[str(p)]==identity,STAGES[0],'CLOSED_ANCESTOR_RACE');directories[str(p)]=identity
    require(all(directory_identity(p)==s for p,s in guards.items()),STAGES[0],'CLOSED_DIRECTORY_MUTATION')
    return {'schema':'CLOSED_EXECUTION_INPUT_INVENTORY_V1','source_commit':manifest['source']['commit'],'files':files,
            'directories':directories,'sealed_directories':guards}


def verify_closed_inventory(manifest,*,verify_files=True):
    binding=manifest['execution_inventory'];raw=pin_file(binding['path'],binding['sha256'],source_bytes=True)['bytes'];index=json.loads(raw)
    require(index.get('schema')=='CLOSED_EXECUTION_INPUT_INVENTORY_V1' and index.get('source_commit')==manifest['source']['commit'],STAGES[0],'CLOSED_INVENTORY_SCOPE')
    rows=index['files'];expected=closed_paths(manifest)
    require(type(rows) is list and 0<len(rows)<=100000 and [r['path'] for r in rows]==sorted(expected),STAGES[0],'CLOSED_INPUT_SEQUENCE','EXACT_ORDERED_SET','MISSING_ADDITIONAL_REORDERED_OR_DUPLICATE')
    require(all(r['sha256']==expected[r['path']] for r in rows),STAGES[0],'CLOSED_INPUT_HASH_BINDINGS')
    directories=index['directories'];guards=index['sealed_directories']
    require(sorted(directories)==sorted({str(p) for path in expected for p in Path(path).parents if str(p)!='/'}),STAGES[0],'CLOSED_ANCESTOR_SET')
    require(sorted(guards)==closed_guard_paths(manifest,expected),STAGES[0],'CLOSED_DIRECTORY_SET')
    def verify_guards():
        for p,snapshot in guards.items():
            try:require(directory_identity(p)==snapshot,STAGES[0],'CLOSED_DIRECTORY_MUTATION','PINNED_METADATA','CHANGED')
            except Exception as error:
                detail=failure(error,STAGES[0],'CLOSED_DIRECTORY_READ');rejected=QualificationFailure(detail['stage'],detail['predicate'],detail['expected'],detail['observed'],exception=detail['exception_subtype'],errno_category=detail['errno_category'])
                rejected.detail.update(detail);rejected.detail['closed_directory']={'path':p if len(p)<=512 else 'PINNED_PATH_OVER_BOUND','operation':'NOFOLLOW_DIRECTORY_METADATA','inventory_parent':binding['sha256']}
                raise rejected from None
    verify_guards()
    if verify_files:
        for position,row in enumerate(rows):
            try:
                result=pin_file(row['path'],row['sha256'],metadata=True)
                require(type(row['size']) is int and result['size']==row['size'],STAGES[0],'CLOSED_INPUT_SIZE')
                require(list(result['identity'])==row['identity'],STAGES[0],'CLOSED_INPUT_IDENTITY')
                for p,observed in zip(list(reversed(Path(row['path']).parents))[1:],result['ancestors']):
                    require(list(observed)==directories[str(p)],STAGES[0],'CLOSED_INPUT_CONTAINMENT')
            except Exception as error:
                detail=failure(error,STAGES[0],'CLOSED_INPUT_READ');rejected=QualificationFailure(detail['stage'],detail['predicate'],detail['expected'],detail['observed'],exception=detail['exception_subtype'],errno_category=detail['errno_category'])
                rejected.detail.update(detail);rejected.detail['closed_input']={'index':position,'path':row['path'] if len(row['path'])<=512 else 'PINNED_PATH_OVER_BOUND','operation':'NOFOLLOW_DIRECT_PIN','inventory_parent':binding['sha256']}
                raise rejected from None
    verify_guards();return index


def verify_closed_export(root,manifest,closed):
    """Historical verification against a pinned closed input table; never scan."""
    root=Path(root);files={Path(r['path']):r for r in closed['files'] if root in Path(r['path']).parents}
    def read(name):
        path=root/name;require(path in files,STAGES[0],'CLOSED_EXPORT_INPUT')
        row=files[path];result=pin_file(path,row['sha256'],source_bytes=True,metadata=True)
        require(result['size']==row['size'] and list(result['identity'])==row['identity'],STAGES[0],'CLOSED_EXPORT_IDENTITY')
        return json.loads(result['bytes'])
    seal=read('EXPORT.json');index=read('INVENTORY.json')
    require(seal['manifest']==index['manifest']==manifest and seal['verified_at_ns']<seal['deadline_ns'],STAGES[0],'CLOSED_EXPORT_PARENT')
    require(files[root/'INVENTORY.json']['sha256']==seal['inventory_sha256'] and files[root/'REPORT.json']['sha256']==seal['report_sha256'],STAGES[0],'CLOSED_EXPORT_HASH')
    expected=sorted(str(p.relative_to(root)) for p in files if p not in (root/'EXPORT.json',root/'INVENTORY.json'))
    require([r['path'] for r in index['files']]==expected,STAGES[0],'CLOSED_EXPORT_SEQUENCE')
    for row in index['files']:
        p=Path(row['path']);require(not p.is_absolute() and '..' not in p.parts and str(p)==row['path'],STAGES[0],'CLOSED_EXPORT_CONTAINMENT')
        pinned=files[root/p];require(row['sha256']==pinned['sha256'] and row['size']==pinned['size'],STAGES[0],'CLOSED_EXPORT_MEMBER')
        result=pin_file(root/p,pinned['sha256'],metadata=True)
        require(list(result['identity'])==pinned['identity'],STAGES[0],'CLOSED_EXPORT_IDENTITY')
    report=read('REPORT.json')
    receipt=report.get('admission_stage_receipt')
    if receipt:
        require(receipt['path']=='ADMISSION-STAGE-RECEIPT.json' and receipt['sha256']==files[root/receipt['path']]['sha256'],STAGES[0],'CLOSED_FAILURE_RECEIPT')
        value=read(receipt['path']);require(value['failure']==report['primary_failure'] and value['manifest']==manifest and value['nonce']==report['nonce'],STAGES[0],'CLOSED_FAILURE_PARENT')
    return report,[root/name for name in expected if re_checkpoint_name(name)]


def re_checkpoint_name(name):
    import re
    return re.fullmatch(r'checkpoint-[0-9]{4}\.json',name) is not None
