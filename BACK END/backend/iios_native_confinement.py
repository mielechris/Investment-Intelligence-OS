"""Bounded dummy comparisons using the existing ownership and OS denial collector.

These are proposed native effects until a separately authorized conductor runs.
No retained errno, child claim or policy query is promoted to OS attribution.
"""
from dataclasses import asdict,dataclass
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import types
from iios_native_conductor import STAGES,require,digest,pin_file,canonical,QualificationFailure
from iios_native_ownership import LaunchBinding
from iios_native_assembly import publish

STAGE=STAGES[8]
CHECKS=('filesystem','network','subprocess','credential_boundary')
OPERATIONS={'filesystem':'file-read-data','network':'network-inbound','subprocess':'process-exec','credential_boundary':'file-read-data'}


@dataclass(frozen=True)
class SandboxBinding:
    """Pin the wrapper separately; preserve every final-image/argv predicate."""
    inner: LaunchBinding
    sandbox: str
    sandbox_hash: str
    profile: str
    profile_hash: str
    @property
    def command(self):return (self.sandbox,'-f',self.profile)+self.inner.command
    @property
    def observed_argv(self):return self.inner.observed_argv
    @property
    def image(self):return self.inner.image
    @property
    def image_hash(self):return self.inner.image_hash
    def verify(self):
        result=self.inner.verify();rows=[]
        for path,parent in ((self.sandbox,self.sandbox_hash),(self.profile,self.profile_hash)):
            require(str(Path(path).resolve(strict=True))==path,STAGE,'CONFINEMENT_WRAPPER_SYMLINK')
            pin_file(path,parent);st=os.stat(path,follow_symlinks=False)
            rows.append((path,st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_size,st.st_mtime_ns,st.st_ctime_ns))
        return result+tuple(rows)
    def reverify(self,before):require(self.verify()==before,STAGE,'CONFINEMENT_WRAPPER_MUTATION')


# The report is published while the independently inspected owning handle stays
# live. The parent releases it only after the existing OS collector finishes.
PROBE='''import os,json,select,time,errno,socket,subprocess,stat,hashlib
D=__DESCRIPTOR__
clock=lambda:time.clock_gettime_ns(6)
def need(ok,code):
    if not ok:raise ValueError(code)
print('READY_V1',flush=True)
need(select.select([0],[],[],min(30,max(0,(D['deadline']-clock())/1e9)))[0],'PROBE_ACK_DEADLINE')
need(os.read(0,16)==b'ACK_V1\\n','PROBE_ACK')
need(clock()<D['deadline'],'PROBE_DEADLINE')
outcome='ALLOWED';number=None;child=None
try:
    if D['operation']=='file-read-data':
        fd=os.open(D['target'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            need((info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_size)==tuple(D['target_identity']),'PROBE_DUMMY_IDENTITY')
            need(stream.read(33)==b'IIOS_DISPOSABLE_DUMMY\\n','PROBE_DUMMY_BYTES')
    elif D['operation']=='network-inbound':
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:sock.bind(('127.0.0.1',38494))
    elif D['operation']=='process-exec':
        info=os.stat(D['target'],follow_symlinks=False)
        need((info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_size)==tuple(D['target_identity']),'PROBE_DUMMY_IDENTITY')
        fd=os.open(D['target'],os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:need(hashlib.sha256(stream.read()).hexdigest()==D['target_sha256'],'PROBE_DUMMY_EXECUTABLE')
        child=subprocess.Popen([D['target']],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={'LC_ALL':'C','TZ':'UTC'},close_fds=True)
        while child.poll() is None:
            need(clock()<D['deadline'],'PROBE_DUMMY_EXIT_DEADLINE');time.sleep(.005)
        need(child.wait(timeout=.001)==0,'PROBE_DUMMY_EXIT')
    else:raise ValueError('PROBE_OPERATION')
except PermissionError as error:
    need(error.errno in (1,13),'PROBE_DENIAL_ERRNO');outcome='DENIED';number=error.errno
value={'nonce':D['nonce'],'descriptor_parent':D['parent'],'outcome':outcome,'errno':number}
fd=os.open(D['record'],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
with os.fdopen(fd,'w') as stream:stream.write(json.dumps(value,sort_keys=True,separators=(',',':'))+'\\n');stream.flush();os.fsync(stream.fileno())
while not os.path.exists(D['release']):
    need(clock()<D['deadline'],'PROBE_RELEASE_DEADLINE');time.sleep(.005)
with open(D['release'],'r') as stream:need(json.load(stream)=={'descriptor_parent':D['parent']},'PROBE_RELEASE_PARENT')
print(json.dumps({'status':'PROBE_COMPLETE','descriptor_parent':D['parent']}),flush=True)
'''

# All operation failures use the same bounded fixed-token envelope as assembly.
_prefix,_body=PROBE.split('clock=lambda:',1)
PROBE=_prefix+'def main():\n'+''.join('    '+line+'\n' for line in ('clock=lambda:'+_body).splitlines())+"\ntry:main()\nexcept Exception as error:\n    code=error.args[0] if error.args else 'PROBE_OPERATION_FAILED'\n    if type(code) is not str or not code or len(code)>95 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in code):code='PROBE_OPERATION_FAILED'\n    print(json.dumps({'status':'FAIL','stage':'DISPOSABLE_CONFINEMENT_AND_LIFECYCLE','predicate':code,'exception_subtype':type(error).__name__,'errno_category':errno.errorcode.get(getattr(error,'errno',None),'NONE')}),flush=True)\n    raise SystemExit(1)\n"
del _prefix,_body


def observation(row):
    value=asdict(row);value['argv']=list(value['argv']);return value


def collect_comparison(context,allowed,denied,spec,owner):
    """Reuse the exact existing collector with the conductor's bounded transport."""
    import alpha_denial_collector as collector
    import alpha_observation_qualification as qualification
    from provider_gateway_contract import content_hash
    expected=content_hash(spec);command=collector.query(spec,expected)
    original_inspect=collector.inspect_macos;original_process=collector.subprocess;original_time=collector.time
    def popen(argv,**kw):
        require(argv==command and kw['cwd']==spec['cwd'] and kw['env']==dict(collector.ENV),STAGE,'DENIAL_EXACT_COMMAND')
        context.check('DENIAL_OUTER_DEADLINE');pin_file(argv[0],spec['log_sha256'])
        return context.spawn(argv,**kw)
    def now():context.check('DENIAL_OUTER_DEADLINE');return original_time.monotonic_ns()
    try:
        collector.inspect_macos=context.inspect
        collector.subprocess=types.SimpleNamespace(Popen=popen,PIPE=original_process.PIPE)
        collector.time=types.SimpleNamespace(monotonic_ns=now,sleep=original_time.sleep)
        return qualification.controlled_denial(allowed,denied,spec,expected,owner=owner,
            owner_parent=content_hash(owner),comparison_parent=content_hash({'allowed':allowed,'denied':denied}))
    finally:
        collector.inspect_macos=original_inspect;collector.subprocess=original_process;collector.time=original_time


def trial(context,*,kind,confined,launcher,image,profile,root,target,deadline,allowed=None):
    from provider_gateway_contract import content_hash,locked_authority
    label=kind+('-confined' if confined else '-baseline');record=root/(label+'.json');release=root/(label+'-release.json')
    d={'nonce':context.manifest['nonce'],'operation':OPERATIONS[kind],'target':target,
        'record':str(record),'release':str(release),'deadline':deadline}
    if kind!='network':
        info=os.stat(target,follow_symlinks=False)
        import stat
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid(),STAGE,'CONFINEMENT_DUMMY_IDENTITY')
        d['target_identity']=(info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_size)
        d['target_sha256']=hashlib.sha256(Path(target).read_bytes()).hexdigest()
    d['parent']=digest(d);script=root/(label+'.py');script_hash=publish(script,PROBE.replace('__DESCRIPTOR__',repr(d)).encode())
    args=('-I','-B','-S',str(script));binding=LaunchBinding(launcher['path'],launcher['sha256'],image['path'],image['sha256'],str(script),script_hash,
        (launcher['path'],)+args,(image['path'],)+args,4)
    if confined:
        binding=SandboxBinding(binding,'/usr/bin/sandbox-exec',context.manifest['tool_pins']['/usr/bin/sandbox-exec'],profile['path'],profile['sha256'])
    evidence={};started=datetime.now(timezone.utc).replace(microsecond=0)
    def tick(owner):
        context.check('CONFINEMENT_TRIAL_DEADLINE')
        if evidence or not record.exists():return
        from iios_native_seal_protocol import read_owned_json
        result,_=read_owned_json(record,4096)
        require(set(result)=={'nonce','descriptor_parent','outcome','errno'} and result['nonce']==d['nonce'] and result['descriptor_parent']==d['parent'],STAGE,'CONFINEMENT_TRIAL_PARENT')
        require((result['outcome'],result['errno']) in ((('DENIED',1),('DENIED',13)) if confined else (('ALLOWED',None),)),STAGE,'CONFINEMENT_EXPECTED_OUTCOME')
        owner.verify();identity=observation(owner.registered);identity_parent=content_hash(identity)
        value={'scope':'DISPOSABLE_DENIAL_ONLY','operation':d['operation'],'target':target,
            'input_parent':digest({'kind':kind,'target':target,'nonce':d['nonce']}),
            'host_parent':digest(context.manifest['terminal_binding']['host']),'uid':os.getuid(),
            'profile_parent':profile['sha256'] if confined else None,'owner_parent':identity_parent,
            'outcome':result['outcome'],'errno':result['errno'],'authority':locked_authority()}
        evidence['trial']=value
        if confined:
            end=datetime.now(timezone.utc).replace(microsecond=0)+timedelta(seconds=1)
            require(0<(end-started).total_seconds()<=10,STAGE,'CONFINEMENT_DENIAL_WINDOW')
            spec={'schema':'iios-bounded-os-denial-v1','scope':'DISPOSABLE_DENIAL_ONLY','pid':owner.child.pid,
                'name':Path(image['path']).name,'executable':image['path'],'operation':d['operation'],'target':target,
                'start':started.isoformat(),'end':end.isoformat(),'cwd':context.manifest['cwd'],
                'log_sha256':context.manifest['tool_pins']['/usr/bin/log'],'launch_parent':digest(d),
                'host_parent':value['host_parent'],'profile_parent':profile['sha256'],'owner_parent':identity_parent,'authority':locked_authority()}
            correlated=collect_comparison(context,allowed,value,spec,identity)
            lower=correlated.get('failure_detail')
            if lower:
                from iios_native_conductor import QualificationFailure
                raise QualificationFailure(lower['stage'],lower['predicate'],lower['expected'],lower['observed'],exception=lower['exception_subtype'],errno_category=lower['errno_category'])
            require(correlated['attribution']=='CONTROLLED_CORRELATED_DENIAL' and correlated['category']=='OS_DENIAL_REPORT_MATCH',STAGE,'CONFINEMENT_ATTRIBUTED_DENIAL','OS_REPORT_MATCH',correlated['category'])
            evidence['correlation']=correlated
        owner.verify();publish(release,canonical({'descriptor_parent':d['parent']}))
    execution=context.execute_owned(binding,min(deadline,context.clock()+30_000_000_000),deadline,on_tick=tick)
    from iios_native_ownership import verify_execution
    verify_execution(execution,STAGE)
    require(evidence and execution['cleanup']['verified'] is True and execution['cleanup']['signals']==0,STAGE,'CONFINEMENT_TRIAL_CLEANUP')
    report=json.loads(execution['report']);require(report=={'status':'PROBE_COMPLETE','descriptor_parent':d['parent']},STAGE,'CONFINEMENT_TRIAL_COMPLETION')
    return dict(evidence,ownership=execution['ownership'],cleanup=execution['cleanup'])
