"""Disposable Truth Spine orchestration; no provider or production capability.

Native effects stay in the existing role runner and fixed dummy comparisons.
The controller accepts their bound records only after owning-handle cleanup.
"""
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
from iios_native_conductor import STAGES,require,digest,canonical,pin_file,QualificationFailure
from iios_native_image_policy import PRODUCTION,bound_json
from iios_native_assembly import publish
from iios_native_ownership import LaunchBinding
from iios_native_confinement import SandboxBinding,CHECKS,trial

STAGE=STAGES[8]

def need(value,predicate):require(value,STAGE,predicate)
def sha(raw):return hashlib.sha256(raw).hexdigest()


def copy_sources(context,rows,destination):
    inventory={r['relative']:r['sha256'] for r in context.manifest['source']['inventory']};files=[];seen=set()
    for row in rows:
        need(set(row)=={'relative','name','sha256'} and row['name']==Path(row['name']).name and row['name'] not in seen,'LIFECYCLE_SOURCE_NAME')
        need(inventory.get(row['relative'])==row['sha256'],'LIFECYCLE_SOURCE_INVENTORY')
        path=Path(context.manifest['source']['root'])/row['relative'];pin_file(path,row['sha256']);raw=path.read_bytes()
        need(sha(raw)==row['sha256'],'LIFECYCLE_SOURCE_MUTATION');publish(destination/row['name'],raw)
        files.append({'path':row['name'],'size':len(raw),'mode':0o400,'sha256':sha(raw)});seen.add(row['name'])
    need({'alpha_observation_qualification.py','truth_spine_full_day_runner.py','truth_spine_full_day_service.py'}<=seen,'LIFECYCLE_EXISTING_ENTRYPOINTS')
    return sorted(files,key=lambda r:r['path'])


from iios_native_profile import reviewed_profile


def prepare(context,parents,policy,deadline,budget):
    from alpha_runtime_files import COMPLETED_DESCRIPTOR_SCHEMA,extension,verify_manifest
    from provider_gateway_contract import content_hash,locked_authority
    from truth_spine_observation_roles import admit_roles,configuration,seed
    execution=context.root/'payload/assembly-output/execution-01'
    need(parents[STAGES[4]]['detail']['execution']==str(execution),'LIFECYCLE_ASSEMBLY_ROOT')
    assembled=json.loads((execution/'ASSEMBLY-RESULT.json').read_bytes());m=assembled['manifest']
    need(policy['runtime_root']==str(execution/'output/runtime-pilot'),'LIFECYCLE_FINAL_RUNTIME_ROOT')
    verify_manifest(policy['runtime_root'],m,source_commit=context.manifest['source']['commit'])
    runtime=dict(schema=COMPLETED_DESCRIPTOR_SCHEMA,root=policy['runtime_root'],interpreter='bin/python3.14',
        files=m['file_inventory'],completed_manifest=m,**extension(m))
    roots={k:str(execution/v) for k,v in {'runtime':'output/runtime-pilot','release':'release','control':'control','output':'disposable'}.items()}
    # These siblings are outside the sealed final-runtime inventory.
    for key in ('release','control'):Path(roots[key]).mkdir(mode=0o700)
    d=context.manifest['native']['lifecycle'];files={'release':copy_sources(context,d['release_sources'],Path(roots['release'])),'control':[]}
    profile,review_parent=reviewed_profile(context.manifest,d,roots)
    controls={'profile.sb':profile}
    from alpha_dummy_tls import create_dummy_tls
    import ssl
    tls_policy=d['dummy_tls_recipe']
    need(tls_policy=={'scope':'SYNTHETIC_TEST_ONLY','generator':'/usr/bin/openssl','maximum_ns':30_000_000_000},'LIFECYCLE_DUMMY_TLS_RECIPE')
    tls_root=execution/'dummy-tls';tls_root.mkdir(mode=0o700)
    tls_end=min(deadline,budget.work_end,context.clock()+tls_policy['maximum_ns'])
    def command(argv):
        need(argv[0]=='/usr/bin/openssl','LIFECYCLE_DUMMY_TLS_TOOL')
        for path in (tls_root/'private-key.pem',tls_root/'certificate.pem'):need(not path.exists() and not path.is_symlink(),'LIFECYCLE_DUMMY_TLS_ABSENCE')
        rc,out,err=context.tool(argv,tls_end,context.manifest['tool_pins']);need(rc==0,'LIFECYCLE_DUMMY_TLS_GENERATION')
        context.check('LIFECYCLE_DUMMY_TLS_DEADLINE')
    certificate,key=create_dummy_tls(tls_root/'certificate.cnf',tls_root,command=command,put=publish)
    for name,path in (('loopback.crt',certificate),('loopback.pem',key)):
        st=path.lstat();need(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and st.st_nlink==1 and st.st_size<=16384,'LIFECYCLE_DUMMY_TLS_FILE')
        path.chmod(0o400);controls[name]=path.read_bytes()
    peer_hash=sha(ssl.PEM_cert_to_DER_cert(controls['loopback.crt'].decode('ascii')))
    for name,raw in sorted(controls.items()):
        publish(Path(roots['control'])/name,raw);files['control'].append({'path':name,'size':len(raw),'mode':0o400,'sha256':sha(raw)})
    now=context.clock();final=min(deadline,budget.work_end,now+780_000_000_000)
    need(final-now>180_000_000_000,'LIFECYCLE_SHARED_RESERVES')
    startup=now+60_000_000_000;stop=final-120_000_000_000
    stamp=datetime.now(timezone.utc);s=context.root.lstat();output_identity=[s.st_dev,s.st_ino,s.st_uid,stat.S_IMODE(s.st_mode)]
    need(parents[STAGES[3]]['detail']['output_identity']==output_identity,'LIFECYCLE_OUTPUT_IDENTITY')
    image_relative=context.manifest['native']['runtime_acceptance']['image_relative']
    image_row=next((r for r in policy['rows'] if r.get('file')==image_relative and r['kind']=='PRIVATE_SEALED'),None)
    need(image_row is not None,'LIFECYCLE_PROCESS_IMAGE_POLICY')
    from iios_native_role_transport import POLICY
    linkage={'inspection_policy':POLICY,'inspection_tools':{p:context.manifest['tool_pins'][p] for p in ('/bin/ps','/usr/sbin/lsof')},'clock_basis':'DARWIN_CLOCK_MONOTONIC_RAW_NS','process_image':{'path':policy['runtime_root']+'/'+image_relative,'sha256':image_row['sha256']},'manifest':context.parent,'source':context.manifest['source']['commit'],
        'runtime_reference':digest(parents[STAGES[6]]),'runtime_acceptance':digest(parents[STAGES[7]]),
        'host':digest(parents[STAGES[1]]),'output_root':str(context.root),'output_identity':output_identity,'execution_root':str(execution)}
    previous=None;seeds=[]
    for slot in range(3):previous=content_hash(seed(slot,previous));seeds.append(previous)
    doc={'schema':'iios-disposable-observation-roles-v3','scope':'DISPOSABLE_NATIVE_QUALIFICATION_ONLY',
        'source_commit':context.manifest['source']['commit'],'roots':roots,'runtime':runtime,'runtime_parent':content_hash(runtime),
        'input_files':files,'release_parent':content_hash(files['release']),'control_parent':content_hash(files['control']),
        'seed_parents':seeds,'valid_from':stamp.isoformat(),'expires_at':(stamp+timedelta(seconds=(final-now)/1e9)).isoformat(),
        'launch':{'host':'127.0.0.1','port':38493,'peer_hash':peer_hash,'sandbox_hash':context.manifest['tool_pins']['/usr/bin/sandbox-exec'],
            'host_identity':d['host_identity'],'start_ns':now,'startup_ns':startup,'stop_ns':stop,'final_ns':final},
        'authority':locked_authority(),'conductor':linkage}
    cap=admit_roles(doc,content_hash(doc),approved_roots=roots,now=stamp)
    config=configuration(cap);config_path=execution/'qualification.json';publish(config_path,canonical(config))
    return cap,config,config_path,{'path':roots['control']+'/profile.sb','sha256':sha(profile)},review_parent


CHILD='''import sys
sys.dont_write_bytecode=True
_preparing=True
def guard(event,args):
    if event in ('os.kill','os.killpg','os.system','os.posix_spawn','os.fork','os.forkpty','os.exec'):
        raise PermissionError('DISPOSABLE_UNDECLARED_EFFECT')
    if _preparing:
        if event.startswith(('socket.','subprocess.')) or event in ('os.mkdir','os.remove','os.rename','os.link','os.symlink','os.chmod','os.chown','os.truncate'):
            raise PermissionError('DISPOSABLE_PREPARATION_EFFECT')
        if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or isinstance(args[2],int) and args[2]&(1|2|8|512|1024|2048)):
            raise PermissionError('DISPOSABLE_PREPARATION_WRITE')
sys.addaudithook(guard)
import os,json,select,time
D=__DESCRIPTOR__
sys.path.insert(0,D['release'])
from alpha_observation_qualification import load_config,run_parent
from datetime import datetime,timezone
from iios_native_conductor import failure,STAGES
try:
    print('READY_V1',flush=True)
    if not select.select([0],[],[],30)[0] or os.read(0,16)!=b'ACK_V1\\n':raise ValueError('LIFECYCLE_OWNER_ACK')
    if time.clock_gettime_ns(6)>=D['deadline']:raise ValueError('LIFECYCLE_SHARED_DEADLINE')
    c,cap=load_config(D['config'],D['config_parent'],D['roots'],now=datetime.now(timezone.utc))
    from truth_spine_observation_roles import bind_conductor_clock
    bind_conductor_clock(cap)
    from iios_native_role_transport import install
    transport=install(cap)
    _preparing=False
    result=transport.finish(run_parent(c,cap))
    print(json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
    raise SystemExit(0 if result['status']=='FUNCTIONAL_PASS' else 1)
except Exception as error:
    print(json.dumps({'status':'FAIL',**failure(error,STAGES[8],'LIFECYCLE_CHILD_FAILURE')}),flush=True)
    raise SystemExit(1)
'''


def verify_functional(value,parent):
    from provider_gateway_contract import locked_authority
    fixed={'scope':'DISPOSABLE_NATIVE_QUALIFICATION_ONLY','production_qualified':False,
        'provider_access':False,'credential_access':False,'seeded':True,'requests_attempted':0,
        'broker_connected':False,'paper_order_permission':False,'trade_execution_permission':False,'live_execution':False}
    need(type(value) is dict and set(value)==set(fixed)|{'schema','status','admission_parent','primary_failure','cleanup','provider_requests','seed_records','http','confinement','authority'} and all(type(value.get(k)) is type(v) and value.get(k)==v for k,v in fixed.items()),'LIFECYCLE_RESULT_SCOPE')
    need(value.get('schema')=='iios-disposable-functional-result-v1' and value.get('status')=='FUNCTIONAL_PASS' and value.get('admission_parent')==parent,'LIFECYCLE_FUNCTIONAL_RESULT')
    need(value.get('authority')==locked_authority() and all(v is False for v in value['authority'].values()),'LIFECYCLE_AUTHORITY_FALSE')
    need(value.get('primary_failure') is None and value.get('provider_requests')==0 and type(value.get('provider_requests')) is int and value.get('seed_records')==3,'LIFECYCLE_DISPOSABLE_RESULT')
    need(value.get('confinement')=='UNQUALIFIED_UNTIL_CONTROLLED_COMPARISONS','LIFECYCLE_NO_CONFINEMENT_RELABEL')
    http=value.get('http');need(type(http) is list and len(http)==2,'LIFECYCLE_HTTP_COMPLETE')
    for method,row in zip(('GET','HEAD'),http):
        need(type(row) is dict and set(row)==set(fixed)|{'method','status','tls_verified','provider_requests'},'LIFECYCLE_HTTP_SCHEMA')
        need(row.get('method')==method and row.get('status')==200 and row.get('tls_verified') is True and row.get('provider_requests')==0,'LIFECYCLE_ACK_TLS_HEALTH')
        need(all(type(row.get(k)) is type(v) and row.get(k)==v for k,v in fixed.items()),'LIFECYCLE_HTTP_SCOPE')
    cleanup=value.get('cleanup');need(type(cleanup) is dict and set(cleanup)==set(fixed)|{'verified','cooperative','roles','listener_owner_reconciled','port_clear','failures'} and all(type(cleanup.get(k)) is type(v) and cleanup.get(k)==v for k,v in fixed.items()) and cleanup.get('verified') is True and cleanup.get('cooperative') is True and cleanup.get('roles')==['scheduler','publisher','backend'] and cleanup.get('failures')==[], 'LIFECYCLE_COOPERATIVE_CLEANUP')
    need(cleanup.get('port_clear')==[True,True,True] and all(x is True for x in cleanup['port_clear']) and cleanup.get('listener_owner_reconciled') is True,'LIFECYCLE_LISTENER_RECONCILIATION')
    return True


def decode_functional(raw,parent):
    need(type(raw) is bytes and len(raw)<=4*1024*1024,'LIFECYCLE_REPORT_OVERFLOW')
    def unique(pairs):
        out={}
        for key,value in pairs:need(key not in out,'LIFECYCLE_DUPLICATE_FIELD');out[key]=value
        return out
    def nonfinite(value):raise QualificationFailure(STAGE,'LIFECYCLE_NONFINITE_VALUE','JSON','NONFINITE')
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite)
    verify_functional(value,parent);return value


def verify_inspector_tools(context,deadline):
    from iios_native_role_transport import TOOLS
    for path in TOOLS:
        expected=context.manifest['tool_pins'].get(path)
        need(expected is not None,'LIFECYCLE_INSPECTOR_TOOL_PIN')
        pin_file(path,expected)
        rc,out,err=context.tool(['/usr/bin/codesign','--verify','--strict','-R=anchor apple',path],deadline,context.manifest['tool_pins'])
        need(rc==0,'LIFECYCLE_INSPECTOR_APPLE_SIGNATURE')
        pin_file(path,expected)
    return True


def run_stage(context,row,deadline,budget):
    parents={s:context.require_completed(s) for s in (STAGES[1],STAGES[2],STAGES[3],STAGES[4],STAGES[5],STAGES[6],STAGES[7])}
    reference=parents[STAGES[6]];acceptance=parents[STAGES[7]]
    need(reference['detail']['scope']==acceptance['detail']['scope']==PRODUCTION,'LIFECYCLE_PRODUCTION_SCOPE')
    need(acceptance['detail']['reference_receipt_parent']==digest(reference),'LIFECYCLE_RUNTIME_PARENT')
    policy_path=context.root/'PRODUCTION-RUNTIME-IMAGE-POLICY.json'
    need(reference['detail']['policy_path']==str(policy_path),'LIFECYCLE_EXTERNAL_REFERENCE_PATH')
    policy=json.loads(policy_path.read_bytes());need(digest(policy)==reference['detail']['policy_parent'],'LIFECYCLE_REFERENCE_HASH')
    verify_inspector_tools(context,deadline)
    cap,config,config_path,profile,profile_review=prepare(context,parents,policy,deadline,budget)
    from provider_gateway_contract import content_hash
    doc=cap.document();d=context.manifest['native']['runtime_acceptance']
    private={r['file']:r for r in policy['rows'] if r['kind']=='PRIVATE_SEALED'}
    images={name:{'path':policy['runtime_root']+'/'+d[name+'_relative'],'sha256':private[d[name+'_relative']]['sha256']} for name in ('launcher','image')}
    descriptor={'config':str(config_path),'config_parent':content_hash(config),'roots':doc['roots'],'release':doc['roots']['release'],'deadline':min(deadline,budget.work_end)}
    script=config_path.parent/'conductor-lifecycle.py';script_hash=publish(script,CHILD.replace('__DESCRIPTOR__',repr(descriptor)).encode())
    # Script is separate from the immutable role release inventory; its exact
    # bytes are independently pinned in the owning launch binding.
    args=('-I','-B','-S',str(script));inner=LaunchBinding(images['launcher']['path'],images['launcher']['sha256'],images['image']['path'],images['image']['sha256'],str(script),script_hash,
        (images['launcher']['path'],)+args,(images['image']['path'],)+args,4)
    binding=SandboxBinding(inner,'/usr/bin/sandbox-exec',context.manifest['tool_pins']['/usr/bin/sandbox-exec'],profile['path'],profile['sha256'])
    execution=context.execute_owned(binding,doc['launch']['startup_ns'],min(deadline,budget.work_end),environment=context.manifest['native']['lifecycle']['environment'])
    from iios_native_ownership import verify_execution
    verify_execution(execution,STAGE)
    result=decode_functional(execution['report'],cap.identity);need(result.get('status')=='FUNCTIONAL_PASS' and result.get('admission_parent')==cap.identity,'LIFECYCLE_FUNCTIONAL_RESULT')
    need(result['primary_failure'] is None and result['cleanup']['verified'] is True and result['cleanup']['cooperative'] is True,'LIFECYCLE_COOPERATIVE_CLEANUP')
    need(result['cleanup']['port_clear']==[True,True,True] and result['cleanup']['listener_owner_reconciled'] is True,'LIFECYCLE_LISTENER_RECONCILIATION')
    need(result['provider_requests']==0 and result['seed_records']==3 and result['production_qualified'] is False,'LIFECYCLE_DISPOSABLE_RESULT')
    need(execution['cleanup']['verified'] is True and execution['cleanup']['signals']==0,'LIFECYCLE_PARENT_CLEANUP')
    output=Path(doc['roots']['output']);probe_root=output/'confinement';probe_root.mkdir(mode=0o700)
    blocked=config_path.parent/'dummy-denied';blocked.mkdir(mode=0o700)
    for name in ('file','credential-marker'):publish(blocked/name,b'IIOS_DISPOSABLE_DUMMY\n')
    tool=context.manifest['native']['lifecycle']['dummy_executable']
    need(tool['path']=='/usr/bin/true' and tool['sha256']==context.manifest['tool_pins']['/usr/bin/true'],'LIFECYCLE_DUMMY_SYSTEM_TOOL')
    pin_file(tool['path'],tool['sha256']);raw=Path(tool['path']).read_bytes()
    need(sha(raw)==tool['sha256'],'LIFECYCLE_DUMMY_EXECUTABLE');publish(blocked/'dummy-exec',raw,0o500)
    targets={'filesystem':str(blocked/'file'),'credential_boundary':str(blocked/'credential-marker'),'subprocess':str(blocked/'dummy-exec'),'network':'127.0.0.1:38494'}
    comparisons={}
    for kind in CHECKS:
        context.check('CONFINEMENT_SHARED_DEADLINE')
        parameters=dict(kind=kind,launcher=images['launcher'],image=images['image'],profile=profile,root=probe_root,target=targets[kind],deadline=min(deadline,budget.work_end))
        baseline=trial(context,confined=False,**parameters)
        confined=trial(context,confined=True,allowed=baseline['trial'],**parameters)
        comparisons[kind]={'baseline':baseline,'confined':confined}
    value={'schema':'IIOS_DISPOSABLE_CONFINEMENT_AND_LIFECYCLE_V1','parents':{s:digest(p) for s,p in parents.items()},
        'conductor':doc['conductor'],'profile_review':profile_review,'profile_sha256':profile['sha256'],
        'functional':result,'comparisons':comparisons,'production_qualified':False,'authority':context.manifest['authority']}
    destination=context.root/'DISPOSABLE-QUALIFICATION.json';parent=publish(destination,canonical(value))
    return context.receipt(row,artifacts=[{'path':str(destination),'sha256':parent}],extra={'qualification_parent':digest(value),
        'runtime_reference_parent':digest(reference),'runtime_acceptance_parent':digest(acceptance),'production_qualified':False,
        'ownership':execution['ownership'],'cleanup':execution['cleanup']})
