"""Native dispatcher for independently reviewed v1 stage adapters.

There are deliberately no fallbacks to consumed legacy commands. Only a complete
manifest whose adapter bindings are admitted can reach this module's run().
"""
import errno
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import types
from iios_native_conductor import Conductor,STAGES,require,QualificationFailure,digest,pin_file
from iios_native_admission import admit_source,require_execution_ready,terminal_categories,REQUIRED_NATIVE
from iios_native_evidence import fresh_root,owned_directory,export
from iios_native_ownership import reconcile_pid
from iios_native_terminal import admit_terminal


def clock():
    return time.clock_gettime_ns(6)  # Darwin CLOCK_MONOTONIC_RAW; survives controller restart.


class NativeContext:
    def __init__(self,manifest,parent,root):
        self.manifest=manifest;self.parent=parent;self.root=Path(root);self.stage=STAGES[0]
        self.deadline=None;self.children=[];self.query_handles=[];self.events=[];self.conductor=None
        self.clock=clock
    def require_completed(self,stage):
        require(self.conductor is not None and stage in self.conductor.completed,self.stage,'PREREQUISITE_GREEN_RECEIPT','DURABLE_GREEN','MISSING')
        records=[r for r in self.conductor.journal.records if r['kind']=='GREEN' and r['stage']==stage]
        require(len(records)==1,self.stage,'PREREQUISITE_RECEIPT_UNIQUE')
        receipt=records[0]['payload'];self.conductor.verify_checkpoint_receipt(receipt)
        return json.loads(json.dumps(receipt))
    def query(self,argv):
        require(len(argv)==6 and argv[:3]==['/bin/ps','-ww','-p'] and argv[3].isascii() and argv[3].isdecimal() and argv[4]=='-o' and argv[5] in ('comm=','ppid='),self.stage,'ANCESTRY_QUERY_COMMAND')
        rc,out,err=self.tool(argv,self.deadline,self.manifest['tool_pins'])
        require(rc==0 and not err,self.stage,'ANCESTRY_QUERY_RESULT','SUCCESS','FAILED')
        return out.decode().strip()
    def tool(self,argv,deadline,pins):
        self.check('TOOL_DEADLINE')
        require(argv[0] in pins and pins==self.manifest['tool_pins'],self.stage,'TOOL_PIN')
        pin_file(argv[0],pins[argv[0]])
        require(self.manifest['environment']=={'LC_ALL':'C','TZ':'UTC','__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},self.stage,'TOOL_ENVIRONMENT')
        child=subprocess.Popen(argv,cwd=self.manifest['cwd'],env=self.manifest['environment'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
        self.query_handles.append(child)
        try:
            out,err=child.communicate(timeout=min(30,max(0.001,(min(deadline,self.deadline)-clock())/1e9)))
            require(len(out)<=32768 and len(err)<=32768,self.stage,'TOOL_OUTPUT_BOUND')
            require(clock()<min(deadline,self.deadline),self.stage,'TOOL_DEADLINE')
            return child.returncode,out,err
        finally:
            child.stdout.close();child.stderr.close()
    def check(self,predicate='OUTER_WORK_DEADLINE'):
        require(clock()<self.deadline,self.stage,predicate,'BEFORE_DEADLINE','EXPIRED')
    def inspect(self,pid):
        """Same OS inspector/predicates; signal-free bounded transport and exact errors."""
        self.check('INSPECTION_DEADLINE')
        import truth_spine_process_identity as identity
        last={'query':'PID_EXISTENCE','failure':'NONE'}
        def retain(value):
            last.update(query=value['query'],failure=value['failure'])
        permitted={('/bin/ps','-ww','-p',str(pid),'-o',field) for field in ('lstart=','ppid=','comm=')}
        permitted.add(('/usr/sbin/lsof','-a','-p',str(pid),'-d','cwd','-Fn'))
        def read(argv,*,capture_output,text,timeout,env):
            require(tuple(argv) in permitted and capture_output is True and text is True and timeout==1,self.stage,'PINNED_INSPECTOR_COMMAND')
            self.check('INSPECTION_DEADLINE')
            tools=self.manifest['tool_pins'];require(argv[0] in tools,self.stage,'INSPECTION_TOOL_PIN');pin_file(argv[0],tools[argv[0]])
            # No context manager, subprocess.run timeout kill, or signals.
            proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,close_fds=True);self.query_handles.append(proc)
            out,err=proc.communicate(timeout=min(1,max(0.001,(self.deadline-clock())/1e9)))
            require(len(out)<=65536 and len(err)<=65536,self.stage,'INSPECTOR_OUTPUT_BOUND')
            self.check('INSPECTION_DEADLINE')
            return types.SimpleNamespace(returncode=proc.returncode,stdout=out.decode(),stderr=err.decode())
        old=identity.subprocess;identity.subprocess=types.SimpleNamespace(run=read,TimeoutExpired=subprocess.TimeoutExpired)
        try:return identity.inspect_macos(pid,diagnostic=retain)
        except QualificationFailure:raise
        except Exception as error:
            category=errno.errorcode.get(getattr(error,'errno',None),'NONE')
            observed=last['failure'] if last['failure']!='NONE' else 'INSPECTION_EXCEPTION'
            raise QualificationFailure(self.stage,last['query'],'AVAILABLE',observed,exception=type(error).__name__,errno_category=category) from None
        finally:identity.subprocess=old
    def receipt(self,row,artifacts=(),extra=None):
        return {'stage':row['id'],'status':'GREEN','manifest':self.parent,'history':self.manifest['history'],
                'predicates':dict.fromkeys(row['predicates'],True),'authority':self.manifest['authority'],
                'artifacts':list(artifacts),'detail':extra or {}}
    def verify_receipt(self,receipt):
        for row in receipt['artifacts']:
            path=Path(row['path'])
            require(path.is_absolute() and path.is_relative_to(self.root) and '..' not in path.parts,receipt['stage'],'RECEIPT_OUTPUT_ROOT')
            pin_file(path,row['sha256'])
    def cleanup(self,deadline):
        failures=[]
        for owned in reversed(self.children):
            try:
                # Never send signals. A timeout retains the owner and exact failure.
                owned.finish(max(0.001,(deadline-clock())/1e9))
            except Exception as error:
                from iios_native_conductor import failure
                failures.append(failure(error,'CLEANUP','OWNED_CHILD_CLEANUP'))
        outstanding=sum(not owner.reaped for owner in self.children)+sum(p.returncode is None for p in self.query_handles)
        if failures:
            item=failures[0]
            error=QualificationFailure(item['stage'],item['predicate'],item['expected'],item['observed'],exception=item['exception_subtype'],errno_category=item['errno_category'])
            error.secondary_cleanup=failures[1:];raise error
        return {'verified':outstanding==0,'outstanding':outstanding}


def run(manifest,parent):
    require_execution_ready(manifest);admit_source(manifest)
    root=fresh_root(manifest['output_parent'],manifest['output_name'],manifest['output_parent_identity'])
    # All source imports use the independently verified source inventory. Suppress
    # source-tree bytecode lookup as well as writes; this directory is never created.
    sys.pycache_prefix=str(root/'unused-bytecode');sys.dont_write_bytecode=True
    context=NativeContext(manifest,parent,root)
    def builtin(row,deadline,budget):
        context.stage=row['id'];context.deadline=deadline;stage=row['id'];extra={}
        if stage==STAGES[0]:admit_source(manifest)
        elif stage==STAGES[1]:
            host={'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'uid':os.getuid()}
            admit_terminal(manifest['terminal_binding'],environment=dict(os.environ),ttys=[os.isatty(fd) for fd in (0,1,2)],host=host,parent_pid=os.getppid(),query=context.query,clock=clock,deadline=deadline)
        elif stage==STAGES[2]:
            extra={'observations':[reconcile_pid(pid,context.inspect,stage=stage,deadline=deadline,clock=clock) for pid in manifest['historical_pids']]}
        elif stage==STAGES[3]:
            fd=owned_directory(root)
            try:os.mkdir('payload',0o700,dir_fd=fd)
            finally:os.close(fd)
            child=owned_directory(root/'payload');os.close(child)
        elif stage==STAGES[8]:
            require(not any(p.returncode is None for p in context.query_handles),stage,'INSPECTION_HELPERS_REAPED')
        return context.receipt(row,extra=extra)
    adapters={s:builtin for s in STAGES if s not in REQUIRED_NATIVE}
    for row in manifest['stages']:
        if row['id'] not in REQUIRED_NATIVE:continue
        def call(row,deadline,budget):
            context.stage=row['id'];context.deadline=deadline
            context.check('ADAPTER_LOAD_DEADLINE')
            binding=row['native_binding']
            pin_file(binding['adapter_path'],binding['adapter_sha256'])
            namespace={'__name__':'iios_reviewed_native_adapter','__file__':binding['adapter_path']}
            exec(compile(Path(binding['adapter_path']).read_bytes(),binding['adapter_path'],'exec'),namespace)
            context.check('ADAPTER_LOAD_DEADLINE')
            return namespace['run_stage'](context,row,deadline,budget)
        adapters[row['id']]=call
    conductor=Conductor(manifest,parent,root,adapters,clock=clock,wall=time.time,
                        verify_receipt=context.verify_receipt,cleanup=context.cleanup,
                        export=lambda report,deadline:export(root,report,deadline,clock))
    context.conductor=conductor
    return conductor.run()
