"""Conductor ownership: three independent observations; no child-supplied identity."""
from dataclasses import dataclass
import os
import json
import re
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
    try:
        for sample in range(3):
            require(clock()<deadline,stage,'RECONCILIATION_DEADLINE')
            row=inspect(pid)
            observation={'sample':sample+1,'existence':'ABSENT' if row is None else 'PRESENT'}
            if row is not None:
                observation['current_identity_categories']={name:'PRESENT' if getattr(row,name,None) else 'MISSING'
                    for name in ('parent_pid','start_time','executable','executable_hash','argv','command','cwd')}
            rows.append(observation)
            require(clock()<deadline,stage,'RECONCILIATION_DEADLINE')
        require(all(row['existence']=='ABSENT' for row in rows),stage,'HISTORICAL_PID_CURRENTLY_ABSENT','ABSENT_ALL_THREE','PRESENT_OR_CHANGED')
        return {'status':'CURRENT_REGISTERED_PID_ABSENT','observations':rows,'historical_ownership':False,'cleanup_upgraded':False}
    except Exception as error:
        detail=failure(error,stage,'CURRENT_PROCESS_OBSERVATION')
        rejected=QualificationFailure(detail['stage'],detail['predicate'],detail['expected'],detail['observed'],
                                      exception=detail['exception_subtype'],errno_category=detail['errno_category'])
        rejected.detail.update(detail);rejected.detail['current_process_observations']=rows
        rejected.detail['historical_ownership']=False;raise rejected from None


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


def verify_execution(result,stage):
    """Require the complete owner result at every adapter receipt boundary."""
    require(type(result) is dict,stage,'OWNERSHIP_RESULT_SCHEMA')
    observations=result.get('ownership');cleanup=result.get('cleanup')
    require(type(observations) is list and len(observations)==3,stage,'OWNERSHIP_COMPLETE_OBSERVATIONS')
    for sample,row in enumerate(observations,1):
        require(type(row) is dict and set(row)=={'sample','matches'} and type(row['sample']) is int and row['sample']==sample and
            type(row['matches']) is dict and set(row['matches'])==set(PREDICATES) and all(v is True for v in row['matches'].values()),stage,'OWNERSHIP_COMPLETE_PREDICATES')
    require(type(cleanup) is dict and all(type(cleanup.get(k)) is int for k in ('outstanding','exit_code','signals')) and all(cleanup.get(k) is True for k in ('verified','reaped','independently_absent')) and cleanup=={'verified':True,'outstanding':0,'exit_code':0,
        'reaped':True,'independently_absent':True,'signals':0},stage,'OWNERSHIP_COMPLETE_CLEANUP')
    return True


BOOT_UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')


def unresolved_binding(manifest):
    """Verify consumed evidence; neither missing PID nor old cleanup is inferred."""
    from iios_native_conductor import Journal
    from iios_native_evidence import verify_closed_inventory,verify_closed_export
    stage='HISTORICAL_PROCESS_RECONCILIATION'
    binding=manifest.get('unresolved_child')
    require(type(binding) is dict and set(binding)=={'report','begin','export','inventory','history_key','pid'},stage,'UNRESOLVED_CHILD_BINDING')
    require(binding['pid'] is None and manifest['history'].get(binding['history_key'])=='NOT_ESTABLISHED',stage,'HISTORICAL_CLEANUP_IMMUTABLE')
    root=Path(binding['report']['path']).parent
    admitted={r['path']:r['sha256'] for r in manifest['historical_records']}
    for key,name in (('report','REPORT.json'),('begin','checkpoint-0000.json'),('export','EXPORT.json'),('inventory','INVENTORY.json')):
        row=binding[key]
        require(row['path']==str(root/name) and admitted.get(row['path'])==row['sha256'],stage,'UNRESOLVED_EVIDENCE_PARENT')
        pin_file(row['path'],row['sha256'])
    report=json.loads((root/'REPORT.json').read_bytes())
    closed=verify_closed_inventory(manifest,verify_files=False)
    verified,paths=verify_closed_export(root,report['manifest'],closed)
    require(verified==report,stage,'UNRESOLVED_EXPORT')
    records=Journal(root,report['manifest']).load(paths=paths)
    require(records and records[0]['kind']=='BEGIN' and records[-1]['kind']=='FINAL' and records[-1]['payload']==report,stage,'UNRESOLVED_JOURNAL')
    require(report['status']=='RED' and report['cleanup_receipt'] is None and
            any(r['predicate']=='REGISTERED_OWNERSHIP' for r in report['cleanup_failures']),stage,'UNRESOLVED_CLEANUP_EVIDENCE')
    boot=records[0]['payload'].get('clock_identity')
    require(type(boot) is str and BOOT_UUID.fullmatch(boot) is not None,stage,'HISTORICAL_BOOT_IDENTITY')
    return binding,boot


def reconcile_unresolved(manifest,observe_boot,*,deadline,clock):
    """Unknown PID: only proven boot turnover establishes present absence.

    No process search, PID inference, signal, cleanup or historical reclassification.
    Three fresh host observations are NOT represented as three PID inspections.
    Same-session execution fails closed because the historical PID was not saved.
    """
    from iios_native_conductor import digest
    stage='HISTORICAL_PROCESS_RECONCILIATION';rows=[]
    try:
        binding,old_boot=unresolved_binding(manifest)
        first=None
        for sample in range(1,4):
            require(clock()<deadline,stage,'UNRESOLVED_RECONCILIATION_DEADLINE')
            current=observe_boot()
            require(clock()<deadline,stage,'UNRESOLVED_RECONCILIATION_DEADLINE')
            require(type(current) is str and BOOT_UUID.fullmatch(current) is not None,stage,'CURRENT_BOOT_IDENTITY')
            rows.append({'sample':sample,'operation':'PINNED_SYSCTL_BOOTSESSIONUUID','expected':'DIFFERENT_FROM_HISTORICAL',
                         'observed':'SAME_BOOT_SESSION' if current==old_boot else 'DIFFERENT_BOOT_SESSION',
                         'stable':first is None or current==first})
            if first is None:first=current
            require(current==first,stage,'CURRENT_BOOT_STABILITY')
        require(first!=old_boot,stage,'UNRESOLVED_CHILD_PID_REQUIRED','PRIOR_BOOT_ENDED','SAME_BOOT_PID_UNKNOWN')
        return {'schema':'UNRESOLVED_CHILD_CURRENT_CONDITIONS_V1','status':'CURRENT_HISTORICAL_CHILD_ABSENT_PRIOR_BOOT_ENDED',
                'evidence_parent':digest(binding),'observations':rows,'observation_kind':'HOST_BOOT_SESSION_NOT_PID_QUERY',
                'current_boot_parent':digest(first),'historical_boot_parent':digest(old_boot),'historical_cleanup':'NOT_ESTABLISHED',
                'historical_cleanup_upgraded':False,'signals':0,'retries':0}
    except Exception as error:
        detail=failure(error,stage,'UNRESOLVED_CHILD_OBSERVATION')
        rejected=QualificationFailure(detail['stage'],detail['predicate'],detail['expected'],detail['observed'],
                                      exception=detail['exception_subtype'],errno_category=detail['errno_category'])
        rejected.detail.update(detail);rejected.detail['reconciliation_observations']=rows
        rejected.detail['historical_cleanup']='NOT_ESTABLISHED';raise rejected from None
