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
import re
import select
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
    def run_owned_runtime(self,script,script_hash,policy,startup,deadline):
        from iios_native_ownership import LaunchBinding,OwnedProcess
        from iios_native_image_policy import MAX_REPORT_BYTES
        d=self.manifest['native']['runtime_acceptance'];root=Path(policy['runtime_root'])
        files={r['file']:r for r in policy['rows'] if r['kind']=='PRIVATE_SEALED'}
        launcher=root/d['launcher_relative'];image=root/d['image_relative']
        require(d['launcher_relative'] in files and d['image_relative'] in files,self.stage,'RUNTIME_PROCESS_IMAGES_IN_POLICY')
        now=self.clock();startup=now+60_000_000_000;work=now+90_000_000_000
        require(work<deadline,self.stage,'RUNTIME_EXISTING_DEADLINE_CONTRACT')
        args=('-I','-B','-S',str(script),str(startup),str(work),d['clock_contract'])
        binding=LaunchBinding(str(launcher),files[d['launcher_relative']]['sha256'],str(image),files[d['image_relative']]['sha256'],
                              str(script),script_hash,(str(launcher),)+args,(str(image),)+args,4)
        return self.execute_owned(binding,startup,deadline)

    def execute_owned(self,binding,startup,deadline,*,on_tick=None):
        from iios_native_ownership import OwnedProcess
        from iios_native_image_policy import MAX_REPORT_BYTES
        snapshot=binding.verify();self.check();binding.reverify(snapshot)
        proc=subprocess.Popen(binding.command,cwd=self.manifest['cwd'],env=self.manifest['environment'],
                              stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,bufsize=0)
        owner=OwnedProcess(proc,self.inspect,parent=os.getpid(),argv=binding.observed_argv,cwd=self.manifest['cwd'],
                           executable=binding.image,executable_hash=binding.image_hash,stage=self.stage,clock=self.clock,deadline=deadline)
        self.children.append(owner)
        data=bytearray();errors=bytearray();streams=[proc.stdout,proc.stderr];acked=False
        for stream in streams:os.set_blocking(stream.fileno(),False)
        try:
            while streams:
                if acked and on_tick is not None:on_tick(owner)
                require(self.clock()<(deadline if acked else startup),self.stage,'RUNTIME_TRANSPORT_DEADLINE')
                for stream in select.select(streams,[],[],.01)[0]:
                    raw=os.read(stream.fileno(),4096)
                    if not raw:streams.remove(stream);continue
                    buf=data if stream is proc.stdout else errors
                    require(len(buf)+len(raw)<=MAX_REPORT_BYTES,self.stage,'RUNTIME_REPORT_OVERFLOW');buf.extend(raw)
                require(not errors,self.stage,'RUNTIME_STDERR_REJECTED')
                if not acked and b'\n' in data:
                    first,rest=bytes(data).split(b'\n',1);require(first==b'READY_V1',self.stage,'RUNTIME_READY_PROTOCOL')
                    owner.register();binding.reverify(snapshot);owner.verify()
                    require(self.clock()<startup,self.stage,'RUNTIME_ACK_DEADLINE')
                    require(os.write(proc.stdin.fileno(),b'ACK_V1\n')==7,self.stage,'RUNTIME_ACK_WRITE')
                    proc.stdin.close();data=bytearray(rest);acked=True
            require(acked,self.stage,'RUNTIME_READY_REQUIRED')
            if on_tick is not None:on_tick(owner)
            try:child_result=json.loads(data)
            except (ValueError,UnicodeError):child_result={}
            if type(child_result) is dict and child_result.get('status')=='FAIL':
                detail=child_result.get('failure_detail',child_result)
                raise QualificationFailure(child_result.get('stage',self.stage),child_result.get('predicate','CHILD_FAILURE'),
                    'PASS','CHILD_REJECTED',exception=detail.get('exception_subtype','Exception'),errno_category=detail.get('errno_category','NONE'))
            cleanup=owner.finish(max(.001,(deadline-self.clock())/1e9))
            return {'report':bytes(data),'ownership':owner.observations,'cleanup':cleanup}
        finally:
            for stream in (proc.stdin,proc.stdout,proc.stderr):
                if not stream.closed:stream.close()

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


def run(manifest,parent,*,resume_binding=None):
    require_execution_ready(manifest);admit_source(manifest)
    initial_start=clock()
    if resume_binding is None:
        root=fresh_root(manifest['output_parent'],manifest['output_name'],manifest['output_parent_identity'])
    else:
        require(type(resume_binding) is dict and set(resume_binding)=={'root','root_identity','tip'},'CONDUCTOR','NATIVE_RESUME_BINDING')
        root=Path(manifest['output_parent'])/manifest['output_name']
        require(str(root)==resume_binding['root'],'CONDUCTOR','NATIVE_RESUME_ROOT')
        fd=owned_directory(root)
        try:
            st=os.fstat(fd);require([st.st_dev,st.st_ino,st.st_uid,st.st_mode]==resume_binding['root_identity'],'CONDUCTOR','NATIVE_RESUME_ROOT_IDENTITY')
        finally:os.close(fd)
    # All source imports use the independently verified source inventory. Suppress
    # source-tree bytecode lookup as well as writes; this directory is never created.
    sys.pycache_prefix=str(root/'unused-bytecode');sys.dont_write_bytecode=True
    context=NativeContext(manifest,parent,root)
    context.deadline=initial_start+min(manifest['limits']['work_ns'],30_000_000_000)
    if resume_binding is not None:
        from iios_native_conductor import Journal,Budget
        records=Journal(root,parent).load()
        require(records and records[-1]['hash']==resume_binding['tip'],'CONDUCTOR','RESUME_TRUSTED_TIP')
        require(records[0]['kind']=='BEGIN','CONDUCTOR','RESUME_HEADER')
        old_budget=Budget(**records[0]['payload']['budget']);old_budget.check(clock(),'CONDUCTOR')
        context.deadline=min(context.deadline,old_budget.work_end)
    boot_observation=[]
    def boot_identity():
        if boot_observation:return boot_observation[0]
        rc,out,err=context.tool(['/usr/sbin/sysctl','-n','kern.bootsessionuuid'],context.deadline,manifest['tool_pins'])
        require(rc==0 and not err and re.fullmatch(rb'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\n?',out) is not None,'CONDUCTOR','BOOT_SESSION_IDENTITY')
        boot_observation.append(out.decode().strip().lower());return boot_observation[0]
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
        elif stage==STAGES[9]:
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
                        export=lambda report,deadline:export(root,report,deadline,clock),clock_identity=boot_identity,initial_start=initial_start)
    context.conductor=conductor
    if resume_binding is not None:
        # Verify the entire durable chain before any new native stage. Repeated
        # read-only admission does not replace, reset or rewrite old receipts.
        conductor.preflight_resume(resume_binding['tip'])
        context.stage=STAGES[1]
        host={'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'uid':os.getuid()}
        admit_terminal(manifest['terminal_binding'],environment=dict(os.environ),ttys=[os.isatty(fd) for fd in (0,1,2)],host=host,parent_pid=os.getppid(),query=context.query,clock=clock,deadline=context.deadline)
        context.stage=STAGES[2]
        require(manifest['historical_pids']==[35731],STAGES[2],'RESUME_REGISTERED_PID_BINDING')
        reconcile_pid(35731,context.inspect,stage=STAGES[2],deadline=context.deadline,clock=clock)
    return conductor.run(resume=resume_binding is not None,resume_tip=resume_binding['tip'] if resume_binding is not None else None)
