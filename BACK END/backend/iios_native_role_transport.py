"""Signal-free bounded transport for existing disposable role inspectors.

Only their transport is substituted. Inspector parsing, identity predicates and
listener reconciliation remain the existing implementation. Failed handles are
retained and cannot be presented as verified cleanup.
"""
import os
import select
import subprocess
import time
import types
from pathlib import Path
import re
from iios_native_conductor import STAGES,require,pin_file
STAGE=STAGES[8]
TOOLS=('/bin/ps','/usr/sbin/lsof')
INSPECT_ENV={'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC'}
LISTENER_ENV={'LANG':'C','LC_ALL':'C','TZ':'UTC'}
COMMAND_TEMPLATES=[['/bin/ps','-ww','-p','REGISTERED_PID','-o',field] for field in ('lstart=','ppid=','comm=')]+[
    ['/usr/sbin/lsof','-a','-p','REGISTERED_PID','-d','cwd','-Fn'],
    ['/usr/sbin/lsof','-a','-p','REGISTERED_PID','-nP','-iTCP:38493','-sTCP:LISTEN','-Fp']]
POLICY={'version':1,'apple_anchor_required':True,'commands':COMMAND_TEMPLATES,'pid_scope':'SELF_OR_REGISTERED_OWNING_HANDLE','timeout_ns':1_000_000_000,'output_bytes_per_stream':65536,'shell':False,'signals':0}
_ACTIVE=None

class ReadOnlyTransport:
    def __init__(self,pins,deadline,clock=None,popen=None,*,self_pid=None):
        require(type(pins) is dict and set(pins)==set(TOOLS) and all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in pins.values()),STAGE,'ROLE_INSPECTION_TOOL_IDENTITIES')
        self.self_pid=os.getpid() if self_pid is None else self_pid;self.registered={}
        require(type(self.self_pid) is int and self.self_pid>1,STAGE,'ROLE_SELF_PID')
        self.pins=dict(pins);self.deadline=deadline;self.clock=clock or time.monotonic_ns
        self.popen=popen or subprocess.Popen;self.handles=[];self.uncertain=0
    def register(self,child):
        pid=child.pid
        require(type(pid) is int and pid>1 and pid!=self.self_pid and pid not in self.registered and child.poll() is None,STAGE,'ROLE_REGISTERED_HANDLE')
        self.registered[pid]=child
    def tool_identity(self,path):
        require(path in self.pins,STAGE,'ROLE_INSPECTION_TOOL_PATH')
        require(str(Path(path).resolve(strict=True))==path,STAGE,'ROLE_INSPECTION_TOOL_SYMLINK')
        pin_file(path,self.pins[path]);s=Path(path).stat()
        return (s.st_dev,s.st_ino,s.st_uid,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    def run(self,argv,**kw):
        require(type(argv) is list and all(type(v) is str for v in argv) and len(argv)>3,STAGE,'ROLE_INSPECTION_COMMAND')
        template=list(argv);raw=template[3];template[3]='REGISTERED_PID'
        require(template in COMMAND_TEMPLATES and raw.isascii() and raw.isdecimal() and str(int(raw))==raw,STAGE,'ROLE_INSPECTION_COMMAND')
        pid=int(raw);require(pid==self.self_pid or pid in self.registered,STAGE,'ROLE_INSPECTION_REGISTERED_PID')
        if pid in self.registered:require(self.registered[pid].pid==pid,STAGE,'ROLE_INSPECTION_HANDLE_MUTATION')
        listener=template==COMMAND_TEMPLATES[-1]
        expected=({'env':LISTENER_ENV,'stdin':subprocess.PIPE,'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'timeout':2,'check':False} if listener else {'capture_output':True,'text':True,'timeout':1,'env':INSPECT_ENV})
        require(kw==expected,STAGE,'ROLE_INSPECTION_OPTIONS')
        require(self.clock()<self.deadline,STAGE,'ROLE_INSPECTION_OUTER_DEADLINE');before=self.tool_identity(argv[0])
        end=min(self.deadline,self.clock()+POLICY['timeout_ns'])
        self.uncertain+=1
        child=self.popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=kw['env'],close_fds=True)
        self.handles.append(child);self.uncertain-=1
        streams=[child.stdout,child.stderr];buffers={s:bytearray() for s in streams}
        try:
            for stream in streams:os.set_blocking(stream.fileno(),False)
            while streams or child.poll() is None:
                require(self.clock()<end,STAGE,'ROLE_INSPECTION_TIMEOUT')
                for stream in select.select(streams,[],[],.005)[0]:
                    block=os.read(stream.fileno(),min(4096,65537-len(buffers[stream])))
                    if not block:streams.remove(stream);continue
                    require(len(buffers[stream])+len(block)<=65536,STAGE,'ROLE_INSPECTION_OVERFLOW');buffers[stream].extend(block)
            child.wait(timeout=0)
            require(self.tool_identity(argv[0])==before,STAGE,'ROLE_INSPECTION_TOOL_MUTATION')
            result=[bytes(buffers[s]) for s in (child.stdout,child.stderr)]
            if kw.get('text'):result=[v.decode() for v in result]
            return types.SimpleNamespace(returncode=child.returncode,stdout=result[0],stderr=result[1])
        finally:
            child.stdout.close();child.stderr.close()
    def verify_cleanup(self):
        require(self.uncertain==0 and all(p.poll() is not None for p in self.handles),STAGE,'ROLE_INSPECTION_CLEANUP_UNVERIFIED')
        for child in self.handles:child.wait(timeout=0)
        return True

    def finish(self,result):
        try:self.verify_cleanup()
        except Exception as error:
            from iios_native_conductor import failure
            detail=failure(error,STAGE,'ROLE_INSPECTION_CLEANUP')
            result['status']='FAILED_CLOSED'
            if result.get('primary_failure') is None:result['primary_failure']=detail
            cleanup=result.setdefault('cleanup',{})
            if cleanup is None:cleanup={};result['cleanup']=cleanup
            cleanup.update(verified=False,cooperative=False)
            cleanup.setdefault('failures',[]).append(detail)
        return result


def install(capability):
    """Call after exact v3 descriptor admission, before role/parent effects."""
    global _ACTIVE
    d=capability.document()
    require(d['schema']=='iios-disposable-observation-roles-v3',STAGE,'ROLE_TRANSPORT_SCOPE')
    import truth_spine_process_identity as identity
    import alpha_observation_launch as launch
    require(d['conductor']['inspection_policy']==POLICY,STAGE,'ROLE_INSPECTION_POLICY')
    transport=ReadOnlyTransport(d['conductor']['inspection_tools'],d['launch']['final_ns']);_ACTIVE=transport
    original_listener=launch.listener_pids
    def scoped_listener(port):
        require(port==38493,STAGE,'ROLE_LISTENER_PORT')
        return sorted({value for pid in sorted(transport.registered) for value in original_listener(port,registered_pid=pid)})
    launch.listener_pids=scoped_listener
    # Per-module proxies avoid replacing subprocess.run for unrelated code.
    for module in (identity,launch):
        proxy=types.SimpleNamespace(**{k:getattr(subprocess,k) for k in dir(subprocess) if not k.startswith('__')})
        proxy.run=transport.run;module.subprocess=proxy
    return transport


def register_child(child):
    require(_ACTIVE is not None,STAGE,'ROLE_TRANSPORT_INSTALLED')
    _ACTIVE.register(child)
