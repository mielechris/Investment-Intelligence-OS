"""Fresh-root assembly adapter around the existing copy/seal/assemble pipeline."""
import hashlib
import json
import os
from pathlib import Path
import stat
from iios_native_conductor import STAGES,require,digest,pin_file,canonical
from iios_native_image_policy import bound_json
from iios_native_evidence import owned_directory
from iios_native_ownership import LaunchBinding

STAGE=STAGES[4]
def need(ok,predicate):require(ok,STAGE,predicate)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def publish(path,raw,mode=0o400):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return sha(raw)


def output_parent(boundary):
    """Same production output admission contract, with an exclusively new parent."""
    from alpha_runtime_files import admit_assembly_output_parent,ASSEMBLY_OUTPUT_PARENT_SCHEMA
    from provider_gateway_contract import content_hash
    boundary=Path(boundary);fd=owned_directory(boundary)
    try:os.mkdir('assembly-output',0o700,dir_fd=fd)
    finally:os.close(fd)
    parent=boundary/'assembly-output';s=parent.lstat();ident=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_nlink]
    paths=list(reversed(boundary.parents))+[boundary];rows=[]
    for path in paths:
        s=path.lstat();need(not stat.S_ISLNK(s.st_mode),'ASSEMBLY_CONTAINMENT_SYMLINK')
        rows.append({'path':str(path),'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode)})
    result={'schema':ASSEMBLY_OUTPUT_PARENT_SCHEMA,'boundary_path':str(boundary),'parent_path':str(parent),
            'execution_path':str(parent/'execution-01'),'owner_uid':os.getuid(),'mode':0o700,'parent_identity':ident,'containment':rows,'records':[]}
    admit_assembly_output_parent(result,content_hash(result));return result


def prepare(context,budget,deadline):
    from provider_gateway_contract import content_hash,canonical as build_canonical
    d=context.manifest['native']['assembly'];root=context.root/'payload'
    plan=bound_json(d['plan']);plan['source_base']=context.manifest['source']['commit']
    config={'boundary':str(root),'acceptance':d['acceptance'],'quarantine':d['quarantine'],
            'bootstrap_receipt_parent':d['bootstrap_receipt_parent'],'source':plan['source_base'],
            'total_ns':budget.end-budget.start,'work_end':min(deadline,budget.work_end)}
    need(plan['bootstrap_receipt_sha256']==config['bootstrap_receipt_parent'],'ASSEMBLY_BOOTSTRAP_RECEIPT')
    # Every supplied source row is admitted against this exact commit inventory.
    inventory={r['relative']:r['sha256'] for r in context.manifest['source']['inventory']}
    controls=root/'control';controls.mkdir(mode=0o700);sources={}
    for row in d['control_sources']:
        context.check();name=row['name'];need(name==Path(name).name and name not in sources,'ASSEMBLY_CONTROL_NAME')
        need(row['relative'] in inventory and inventory[row['relative']]==row['sha256'],'ASSEMBLY_CONTROL_SOURCE')
        path=Path(context.manifest['source']['root'])/row['relative'];pin_file(path,row['sha256']);raw=path.read_bytes()
        need(sha(raw)==row['sha256'],'ASSEMBLY_CONTROL_MUTATION');publish(controls/name,raw);sources[name]=raw
    needed={r['path'] for r in plan['source_files']};need(needed<=set(sources),'ASSEMBLY_SOURCE_CLOSURE')
    for row in plan['source_files']:row.update(sha256=sha(sources[row['path']]),size=len(sources[row['path']]))
    source_rows={r['path']:r for r in plan['source_files']}
    for row in plan['planned_files']:
        if row['path'].startswith('iios_source/'):
            source=source_rows[row['path'][len('iios_source/'):]];row.update(sha256=source['sha256'],size=source['size'])
    for name,binding in d['preparation_records'].items():
        need(name==Path(name).name and name not in ('ASSEMBLY-PLAN-v3.json','ASSEMBLY-CLOCK.json'),'ASSEMBLY_PREPARATION_NAME')
        pin_file(binding['path'],binding['sha256']);raw=Path(binding['path']).read_bytes();need(sha(raw)==binding['sha256'],'ASSEMBLY_PREPARATION_MUTATION');publish(root/name,raw)
    parent=output_parent(root);execution=Path(parent['execution_path'])
    plan['assembly_output_parent']=parent;plan['assembly_output_parent_parent']=content_hash(parent)
    plan['roots']={'execution':str(execution),'staging':str(execution/'staging'),'output_parent':str(execution/'output'),
                   'runtime':str(execution/'output/runtime-pilot'),'release':str(execution/'release'),
                   'qualification_control':str(execution/'control'),'disposable_output':str(execution/'disposable')}
    plan_parent=publish(root/'ASSEMBLY-PLAN-v3.json',build_canonical(plan))
    clock={'basis':'DARWIN_CLOCK_MONOTONIC_RAW_NS','start_ns':budget.start,'deadline_ns':budget.end,'source_commit':plan['source_base']}
    budget_parent=publish(root/'ASSEMBLY-CLOCK.json',build_canonical(clock))
    child=Path(d['child']['path']);pin_file(child,d['child']['sha256']);raw=child.read_bytes();need(sha(raw)==d['child']['sha256'],'ASSEMBLY_CHILD_PIN')
    invocation="main("+repr(plan_parent)+','+repr(budget_parent)+','+repr(config)+")"
    wrapper=raw+b'\n'+("\nif __name__=='__main__':\n    import select,errno\n    try:\n        print('READY_V1',flush=True)\n        need(select.select([0],[],[],30)[0],'BUILD_ACK_DEADLINE')\n        need(os.read(0,16)==b'ACK_V1\\n','BUILD_ACK')\n        "+invocation+"\n    except BaseException as error:\n        code=error.args[0] if error.args else 'ASSEMBLY_EXCEPTION'\n        if type(code) is not str or len(code)>95 or not code or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in code):code='ASSEMBLY_EXCEPTION'\n        print(json.dumps({'status':'FAIL','stage':STAGE,'predicate':code,'exception_subtype':type(error).__name__,'errno_category':errno.errorcode.get(getattr(error,'errno',None),'NONE')}),flush=True)\n        raise SystemExit(1)\n").encode()
    script=root/'assembly-child.py';script_hash=publish(script,wrapper)
    descriptor=dict(d['sealer'],source=plan['source_base'],plan_parent=plan_parent,budget_parent=budget_parent,tool_pins=context.manifest['tool_pins'])
    return plan,execution,script,script_hash,descriptor


def run_stage(context,row,deadline,budget):
    context.require_completed(STAGES[3]);safety=context.require_completed(STAGES[2])
    need(context.manifest['historical_pids']==[35731] and all(r['status']=='CURRENT_REGISTERED_PID_ABSENT' for r in safety['detail']['observations']),'ASSEMBLY_PID_SAFETY_PARENT')
    context.check();plan,execution,script,script_hash,descriptor=prepare(context,budget,deadline)
    from iios_native_sealer import configure,Sealer
    configure(context);sealer=Sealer(descriptor)
    d=context.manifest['native']['assembly'];launch=d['launch'];args=('-I','-B','-S',str(script))
    binding=LaunchBinding(launch['launcher'],launch['launcher_hash'],launch['image'],launch['image_hash'],str(script),script_hash,
                          (launch['launcher'],)+args,(launch['image'],)+args,4)
    result=context.execute_owned(binding,min(deadline,context.clock()+30_000_000_000),deadline,
                                 on_tick=lambda owner:sealer(owner.child,owner.registered,deadline))
    from iios_native_ownership import verify_execution
    verify_execution(result,STAGE)
    need(sealer.done and result['cleanup']['verified'] is True,'ASSEMBLY_SEAL_AND_CLEANUP')
    record=execution/'ASSEMBLY-RESULT.json';raw=record.read_bytes();assembled=json.loads(raw)
    need(assembled['status']=='ASSEMBLED_BYTES_ONLY' and assembled['scope']=='PRIVATE_ASSEMBLY_BYTES_ONLY','ASSEMBLY_RESULT_SCOPE')
    return context.receipt(row,artifacts=[{'path':str(record),'sha256':sha(raw)}],extra={'execution':str(execution),
        'ownership':result['ownership'],'cleanup':result['cleanup'],'manifest_sha256':assembled['manifest_sha256'],
        'envelope_sha256':assembled['envelope_sha256'],'runtime_executed':False})
