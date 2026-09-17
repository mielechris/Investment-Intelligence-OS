"""Conductor ownership: three independent observations; no child-supplied identity."""
from dataclasses import dataclass
import os
from pathlib import Path
from iios_native_conductor import QualificationFailure, require, failure, pin_file

PREDICATES=('pid','parent_pid','start_time_present','executable','executable_hash','argv','command','cwd','stable')


def comparisons(row,first,pid,parent,argv,cwd,executable,executable_hash):
    if row is None:return dict.fromkeys(PREDICATES,False)
    return {'pid':row.pid==pid,'parent_pid':row.parent_pid==parent,'start_time_present':bool(row.start_time),
            'executable':row.executable==executable,'executable_hash':row.executable_hash==executable_hash,
            'argv':tuple(row.argv)==tuple(argv),'command':row.command==' '.join(argv),'cwd':row.cwd==cwd,'stable':row==first}


class OwnedProcess:
    def __init__(self,child,inspect,*,parent,argv,cwd,executable,executable_hash,stage,clock,deadline):
        self.child=child;self.inspect=inspect;self.parent=parent;self.argv=argv;self.cwd=cwd
        self.executable=executable;self.executable_hash=executable_hash;self.stage=stage;self.clock=clock;self.deadline=deadline;self.registered=None
        self.observations=[];self.signals=[];self.reaped=False
    def register(self):
        rows=[]
        for sample in range(3):
            require(self.clock()<self.deadline,self.stage,'OWNERSHIP_DEADLINE')
            require(self.child.poll() is None,self.stage,'EARLY_EXIT_BEFORE_OWNERSHIP')
            row=self.inspect(self.child.pid)
            require(self.child.poll() is None,self.stage,'EARLY_EXIT_DURING_OWNERSHIP')
            rows.append(row)
            matches=comparisons(row,rows[0],self.child.pid,self.parent,self.argv,self.cwd,self.executable,self.executable_hash)
            self.observations.append({'sample':sample+1,'matches':matches})
            for name,passed in matches.items():require(passed,self.stage,'OWNERSHIP_'+name.upper(),'MATCH','MISMATCH_OR_ABSENT')
        self.registered=rows[0];return self.observations
    def verify(self):
        require(self.registered is not None,self.stage,'REGISTERED_OWNERSHIP')
        row=self.inspect(self.child.pid)
        matches=comparisons(row,self.registered,self.child.pid,self.parent,self.argv,self.cwd,self.executable,self.executable_hash)
        for name,passed in matches.items():require(passed,self.stage,'FRESH_OWNERSHIP_'+name.upper(),'MATCH','MISMATCH_OR_ABSENT')
        require(self.child.poll() is None,self.stage,'OWNING_HANDLE_LIVE')
        return row
    def signal(self,number,*,authorized,send):
        require(authorized is True,self.stage,'SIGNAL_AUTHORIZATION')
        self.verify()
        require(self.clock()<self.deadline,self.stage,'SIGNAL_DEADLINE')
        send(self.child.pid,number);self.signals.append(number)
    def finish(self,timeout):
        require(self.registered is not None,self.stage,'REGISTERED_OWNERSHIP')
        code=self.child.wait(timeout=timeout);self.reaped=True
        require(code==0,self.stage,'COOPERATIVE_EXIT_ZERO','ZERO','NONZERO')
        require(self.inspect(self.child.pid) is None,self.stage,'INDEPENDENT_PROCESS_ABSENCE','ABSENT','PRESENT')
        return {'verified':True,'outstanding':0,'exit_code':0,'reaped':True,'independently_absent':True,'signals':len(self.signals)}


def reconcile_pid(pid,inspect,*,stage,deadline,clock,observations=3):
    require(observations==3,stage,'THREE_EXISTENCE_OBSERVATIONS')
    rows=[]
    for sample in range(3):
        require(clock()<deadline,stage,'RECONCILIATION_DEADLINE')
        row=inspect(pid);rows.append({'sample':sample+1,'existence':'ABSENT' if row is None else 'PRESENT'})
    require(all(row['existence']=='ABSENT' for row in rows),stage,'HISTORICAL_PID_CURRENTLY_ABSENT','ABSENT_ALL_THREE','PRESENT_OR_CHANGED')
    return {'status':'CURRENT_REGISTERED_PID_ABSENT','observations':rows,'historical_ownership':False,'cleanup_upgraded':False}


@dataclass(frozen=True)
class LaunchBinding:
    """Launcher, process image and script are independently pinned identities.

    argv is the actual OS-observed argv (framework argv[0] may differ from the
    launcher path). The launch command and observed argv are separately pinned.
    """
    launcher: str
    launcher_hash: str
    image: str
    image_hash: str
    script: str
    script_hash: str
    command: tuple
    observed_argv: tuple
    script_index: int

    def verify(self):
        stage='SOURCE_AND_CI_ADMISSION'
        require(self.command and self.command[0]==self.launcher,stage,'LAUNCHER_COMMAND_POSITION')
        require(self.observed_argv and self.observed_argv[0]==self.image,stage,'PROCESS_ARGV_ZERO')
        require(type(self.script_index) is int and 0<self.script_index<len(self.command) and self.script_index<len(self.observed_argv),stage,'SCRIPT_ARGV_INDEX')
        require(self.command[self.script_index]==self.script==self.observed_argv[self.script_index],stage,'SCRIPT_ARGV_POSITION')
        require(self.command[1:]==self.observed_argv[1:],stage,'EXACT_ARGV_ORDER')
        snapshot=[]
        for path,parent in ((self.launcher,self.launcher_hash),(self.image,self.image_hash),(self.script,self.script_hash)):
            require(Path(path).is_absolute() and '..' not in Path(path).parts,stage,'LAUNCH_PATH_ABSOLUTE')
            # Reject every alias in the launch paths, not just the final component.
            require(str(Path(path).resolve(strict=True))==path,stage,'LAUNCH_PATH_SYMLINK')
            pin_file(path,parent);st=os.stat(path,follow_symlinks=False)
            snapshot.append((path,st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_size,st.st_mtime_ns,st.st_ctime_ns))
        return tuple(snapshot)

    def reverify(self,before):
        require(self.verify()==before,'SOURCE_AND_CI_ADMISSION','POST_VERIFICATION_MUTATION')
