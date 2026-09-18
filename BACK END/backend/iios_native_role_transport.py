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
from iios_native_conductor import STAGES,require,pin_file
STAGE=STAGES[8]

class ReadOnlyTransport:
    def __init__(self,pins,deadline,clock=None,popen=None):
        self.pins=dict(pins);self.deadline=deadline;self.clock=clock or time.monotonic_ns
        self.popen=popen or subprocess.Popen;self.handles=[];self.uncertain=0
    def run(self,argv,**kw):
        inspector=(len(argv)==6 and argv[:3]==['/bin/ps','-ww','-p'] and argv[3].isascii() and argv[3].isdecimal() and argv[4]=='-o' and argv[5] in ('lstart=','ppid=','comm=')) or (len(argv)==7 and argv[:3]==['/usr/sbin/lsof','-a','-p'] and argv[3].isascii() and argv[3].isdecimal() and argv[4:]==['-d','cwd','-Fn'])
        listener=argv==['/usr/sbin/lsof','-nP','-iTCP:38493','-sTCP:LISTEN','-Fp']
        require(inspector or listener,STAGE,'ROLE_INSPECTION_COMMAND')
        require(set(kw)<= {'capture_output','text','timeout','env','stdin','stdout','stderr','check'} and kw.get('env')==({'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC'} if inspector else {'LANG':'C','LC_ALL':'C','TZ':'UTC'}) and kw.get('timeout') in (1,2) and kw.get('check',False) is False,STAGE,'ROLE_INSPECTION_OPTIONS')
        require(self.clock()<self.deadline,STAGE,'ROLE_INSPECTION_OUTER_DEADLINE');pin_file(argv[0],self.pins[argv[0]])
        end=min(self.deadline,self.clock()+int(kw['timeout']*1e9))
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
    d=capability.document()
    require(d['schema']=='iios-disposable-observation-roles-v3',STAGE,'ROLE_TRANSPORT_SCOPE')
    import truth_spine_process_identity as identity
    import alpha_observation_launch as launch
    transport=ReadOnlyTransport(d['conductor']['inspection_tools'],d['launch']['final_ns'])
    # Per-module proxies avoid replacing subprocess.run for unrelated code.
    for module in (identity,launch):
        proxy=types.SimpleNamespace(**{k:getattr(subprocess,k) for k in dir(subprocess) if not k.startswith('__')})
        proxy.run=transport.run;module.subprocess=proxy
    return transport
