"""Versioned non-provider qualification transaction. Importing performs no effects.

Adapters are independently pinned and admitted by the manifest. The core owns
ordering, budgets, immutable checkpoints, failure retention and final reduction.
"""
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = 'iios-native-qualification-conductor-v1'
STAGES = (
    'SOURCE_AND_CI_ADMISSION', 'HOST_AND_TERMINAL_ADMISSION',
    'HISTORICAL_PROCESS_RECONCILIATION', 'FRESH_OUTPUT_ROOT_QUALIFICATION',
    'PRIVATE_RUNTIME_ASSEMBLY', 'STATIC_SIGNATURE_AND_INVENTORY',
    'STATIC_RUNTIME_REFERENCE', 'FINAL_RUNTIME_ACCEPTANCE', 'DISPOSABLE_CONFINEMENT_AND_LIFECYCLE',
    'EVIDENCE_EXPORT_AND_VERIFICATION',
)
EFFECTFUL = frozenset(STAGES[i] for i in (3, 4, 6, 7, 8, 9))
AUTHORITIES = ('provider_access', 'credential_access', 'broker_connected',
               'paper_order_permission', 'trade_execution_permission', 'live_execution')
TOKEN = re.compile(r'[A-Z][A-Z0-9_]{0,95}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def token(value, fallback):
    return value if type(value) is str and TOKEN.fullmatch(value) else fallback


class QualificationFailure(Exception):
    def __init__(self, stage, predicate, expected, observed, *, exception='NONE', errno_category='NONE', retryable=False):
        self.detail = {'stage': token(stage, 'CONDUCTOR'), 'predicate': token(predicate, 'INVALID_PREDICATE'),
                       'expected': token(expected, 'INVALID_CATEGORY'), 'observed': token(observed, 'INVALID_CATEGORY'),
                       'exception_subtype': exception if type(exception) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,95}', exception) else 'Exception',
                       'errno_category': token(errno_category, 'OTHER_ERRNO')}
        self.retryable = retryable is True
        super().__init__(self.detail['predicate'])


def failure(error, stage, predicate, expected='PASS'):
    """Retain validated lower-level facts; never persist raw exception messages."""
    if isinstance(error, QualificationFailure):
        return dict(error.detail)
    lower = getattr(error, 'predicate', None)
    if lower is None and error.args:
        lower = error.args[0]
    number = getattr(error, 'errno', None)
    category = errno.errorcode.get(number, 'OTHER_ERRNO') if number is not None else 'NONE'
    result=QualificationFailure(stage, token(lower, predicate), expected,
                                'EXCEPTION_RAISED', exception=type(error).__name__, errno_category=category).detail
    from alpha_assembly_file_type import DerivedFileTypeError,PATHS,MARKERS
    if isinstance(error,DerivedFileTypeError):
        value=error.file_type_failure
        keys={'path','expected_category','observed_category','native_file_result','bytes_parent'}
        if type(value) is dict and set(value)==keys:
            native=value['native_file_result']
            categories={'exit_category':{'ZERO','NONZERO_OR_INVALID'},'output_category':{'BOUNDED','INVALID_OR_OVERSIZE'},
                        'type_category':set(MARKERS)|{'AMBIGUOUS_OR_UNKNOWN'},'stderr_category':{'EMPTY','PRESENT_OR_INVALID'}}
            valid=(all(type(value[k]) is str for k in keys-{'native_file_result'}) and value['path'] in PATHS|{'UNADMITTED_PATH'} and value['expected_category'] in set(MARKERS)|{'UNKNOWN'} and
                   value['observed_category'] in set(MARKERS)|{'UNKNOWN','INVALID_UNIVERSAL','MIXED_SLICES'} and
                   value['bytes_parent'] in {'MATCH','MISMATCH'} and type(native) is dict and set(native)==set(categories)|{'universal_marker'} and
                   type(native['universal_marker']) is bool and all(type(native[k]) is str and native[k] in options for k,options in categories.items()))
            if valid:result['file_type_failure']=json.loads(canonical(value))
    return result


def require(value, stage, predicate, expected='PASS', observed='REJECTED'):
    if not value:raise QualificationFailure(stage, predicate, expected, observed)


def validate_manifest(value, expected, *, now):
    stage=STAGES[0]
    require(type(expected) is str and HEX.fullmatch(expected) and digest(value)==expected, stage, 'MANIFEST_HASH')
    require(value.get('schema')==SCHEMA and value.get('version')==1, stage, 'MANIFEST_VERSION')
    require(value.get('scope')=='NON_PROVIDER_MAC_QUALIFICATION', stage, 'AUTHORIZATION_SCOPE')
    require(value.get('authority')==dict.fromkeys(AUTHORITIES,False), stage, 'AUTHORITY_FALSE')
    require(value.get('separate_gates')==['PROVIDER_PILOT','FULL_MARKET_DAY'], stage, 'SEPARATE_AUTHORIZATION_GATES')
    require(type(value.get('nonce')) is str and HEX.fullmatch(value['nonce']),stage,'RUN_NONCE')
    require(type(value.get('expires_at')) in (int,float) and now<value['expires_at'],stage,'AUTHORIZATION_EXPIRED')
    require(value.get('maximum_executions')==1,stage,'EXECUTION_LIMIT')
    limits=value.get('limits',{})
    require(set(limits)=={'total_ns','work_ns','cleanup_ns','export_ns'},stage,'BUDGET_SCHEMA')
    require(all(type(x) is int and x>0 for x in limits.values()) and limits['total_ns']==sum(limits[k] for k in ('work_ns','cleanup_ns','export_ns')),stage,'BUDGET_RESERVES')
    stages=value.get('stages',[])
    require([x.get('id') for x in stages]==list(STAGES),stage,'STAGE_ORDER')
    for row in stages:
        name=row['id'];require(row.get('effectful')==(name in EFFECTFUL),stage,'EFFECT_CLASSIFICATION')
        retries=row.get('read_only_retries')
        require(type(retries) is int and 0<=retries<=2 and (not row['effectful'] or retries==0),stage,'RETRY_POLICY')
        require(retries==0 or (type(row.get('retry_review')) is str and HEX.fullmatch(row['retry_review']) and type(row.get('retry_predicates')) is list and row['retry_predicates'] and all(type(p) is str and TOKEN.fullmatch(p) for p in row['retry_predicates'])),stage,'READ_ONLY_RETRY_REVIEW')
        require(type(row.get('maximum_ns')) is int and 0<row['maximum_ns']<=limits['work_ns'],stage,'STAGE_BUDGET')
        require(type(row.get('predicates')) is list and row['predicates'] and len(set(row['predicates']))==len(row['predicates']) and all(TOKEN.fullmatch(x) for x in row['predicates']),stage,'PREDICATE_COVERAGE')
    require(type(value.get('history')) is dict and all(type(k) is str and type(v) is str for k,v in value['history'].items()),stage,'HISTORICAL_CLASSIFICATIONS')
    return value


@dataclass(frozen=True)
class Budget:
    start: int
    work_end: int
    cleanup_end: int
    end: int
    @classmethod
    def create(cls,start,limits):
        return cls(start,start+limits['work_ns'],start+limits['work_ns']+limits['cleanup_ns'],start+limits['total_ns'])
    def check(self,now,stage,phase='work'):
        end={'work':self.work_end,'cleanup':self.cleanup_end,'export':self.end}[phase]
        require(self.start<=now<end,stage,'OUTER_'+phase.upper()+'_DEADLINE','BEFORE_DEADLINE','EXPIRED_OR_CLOCK_REVERSED')


def pin_file(path, expected, *, source_bytes=False):
    """Pin regular bytes through retained no-follow directory handles.

    Preparation and native admission use the same policy: aliases are not inputs.
    Every ancestor is opened without following links, then checked again against
    its retained parent. A same-bytes replacement is still an identity failure.
    """
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts,STAGES[0],'INPUT_ABSOLUTE_PATH')
    handles=[];chain=[];fd=None
    identity=lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_mode)
    key=lambda s:identity(s)+(s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    try:
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);handles.append(parent)
        for part in path.parts[1:-1]:
            before=os.stat(part,dir_fd=parent,follow_symlinks=False)
            require(stat.S_ISDIR(before.st_mode),STAGES[0],'INPUT_ANCESTOR_DIRECTORY')
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            handles.append(child)
            require(identity(before)==identity(os.fstat(child)),STAGES[0],'INPUT_ANCESTOR_MUTATION')
            chain.append((parent,part,child,identity(before)));parent=child
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        before=os.fstat(fd);require(stat.S_ISREG(before.st_mode),STAGES[0],'INPUT_REGULAR_FILE')
        h=hashlib.sha256();chunks=[];size=0
        while True:
            b=os.read(fd,65536)
            if not b:break
            h.update(b)
            if source_bytes:
                size+=len(b);require(size<=16*1024*1024,STAGES[0],'SOURCE_BYTES_BOUND');chunks.append(b)
        require(key(before)==key(os.fstat(fd))==key(os.stat(path.name,dir_fd=parent,follow_symlinks=False)),STAGES[0],'INPUT_MUTATION')
        for owner,name,child,original in reversed(chain):
            require(original==identity(os.fstat(child))==identity(os.stat(name,dir_fd=owner,follow_symlinks=False)),STAGES[0],'INPUT_ANCESTOR_MUTATION')
        require(h.hexdigest()==expected,STAGES[0],'INPUT_HASH')
        return dict(sha256=expected,size=before.st_size,**({'bytes':b''.join(chunks),'identity':key(before),'ancestors':tuple(x[3] for x in chain)} if source_bytes else {}))
    finally:
        if fd is not None:os.close(fd)
        for handle in reversed(handles):os.close(handle)


class Journal:
    """Append-only hash chain; no truncated or uncommitted stage may be replayed."""
    def __init__(self,root,manifest_hash):
        self.root=Path(root);self.manifest_hash=manifest_hash;self.records=[]
    def load(self):
        files=sorted(self.root.glob('checkpoint-*.json'));previous=self.manifest_hash
        for index,path in enumerate(files):
            require(path.name==f'checkpoint-{index:04d}.json','CONDUCTOR','CHECKPOINT_SEQUENCE')
            require(not path.is_symlink(),'CONDUCTOR','CHECKPOINT_SYMLINK')
            record=json.loads(path.read_bytes());parent=record.pop('hash',None)
            require(record.get('sequence')==index and record.get('previous')==previous and record.get('manifest')==self.manifest_hash and digest(record)==parent,'CONDUCTOR','CHECKPOINT_HASH')
            previous=parent;record['hash']=parent;self.records.append(record)
        return self.records
    def append(self,kind,stage,payload):
        record={'sequence':len(self.records),'previous':self.records[-1]['hash'] if self.records else self.manifest_hash,
                'manifest':self.manifest_hash,'kind':kind,'stage':stage,'payload':payload}
        record['hash']=digest(record)
        record=json.loads(canonical(record))
        path=self.root/f'checkpoint-{len(self.records):04d}.json'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(canonical(record));stream.flush();os.fsync(stream.fileno())
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
        self.records.append(record);return record
    def completed(self,verify):
        complete=[];inflight=None
        for record in self.records[1:]:
            kind=record['kind'];stage=record['stage']
            if kind=='START':
                require(inflight is None and len(complete)<len(STAGES) and stage==STAGES[len(complete)],stage,'CHECKPOINT_TRANSITION')
                inflight=stage
            elif kind=='GREEN':
                require(inflight==stage,stage,'CHECKPOINT_TRANSITION');verify(record['payload']);complete.append(stage);inflight=None
            elif kind=='READ_ONLY_RETRY':
                require(inflight==stage,stage,'CHECKPOINT_TRANSITION')
            elif kind=='FINAL':
                raise QualificationFailure(stage,'EXECUTION_ALREADY_FINAL','UNCONSUMED','CONSUMED')
            else:raise QualificationFailure(stage,'CHECKPOINT_KIND','KNOWN','INVALID')
        require(inflight is None,'CONDUCTOR','INTERRUPTED_STAGE_NO_REPLAY','COMPLETED_CHECKPOINT','INFLIGHT')
        return complete


class CleanupBoundaryStop(Exception):
    pass


class Conductor:
    def __init__(self,manifest,manifest_hash,root,adapters,*,clock,wall,verify_receipt,cleanup,export,clock_identity=None,initial_start=None):
        self.m=json.loads(canonical(validate_manifest(manifest,manifest_hash,now=wall())));self.parent=manifest_hash;self.root=Path(root)
        self.history=json.loads(canonical(self.m['history']))
        self.adapters=adapters;self.clock=clock;self.wall=wall;self.verify_receipt=verify_receipt;self.cleanup=cleanup;self.export=export
        self.clock_identity=clock_identity;self.initial_start=initial_start
        self.journal=Journal(root,manifest_hash);self.events=[];self.primary=None;self.secondary=[];self.cleanup_failures=[];self.completed=[]
    def record_cleanup_failure(self,error):
        self.cleanup_failures.append(failure(error,'CLEANUP','CLEANUP_EXCEPTION'))
        for item in getattr(error,'secondary_cleanup',()):
            self.cleanup_failures.append(QualificationFailure(item['stage'],item['predicate'],item['expected'],item['observed'],exception=item['exception_subtype'],errno_category=item['errno_category']).detail)
    def verify_checkpoint_receipt(self,receipt):
        stage=receipt.get('stage')
        require(stage in STAGES,'CONDUCTOR','RESUME_RECEIPT_STAGE')
        row=self.m['stages'][STAGES.index(stage)]
        require(receipt.get('status')=='GREEN',stage,'RESUME_RECEIPT_GREEN')
        require(receipt.get('manifest')==self.parent and receipt.get('history')==self.history,stage,'RESUME_RECEIPT_PARENTS')
        require(receipt.get('predicates')==dict.fromkeys(row['predicates'],True),stage,'RESUME_RECEIPT_PREDICATES')
        require(receipt.get('authority')==self.m['authority'],stage,'RESUME_RECEIPT_AUTHORITY')
        self.verify_receipt(receipt)
    def preflight_resume(self,tip):
        journal=Journal(self.root,self.parent);records=journal.load()
        require(bool(records) and records[0]['kind']=='BEGIN','CONDUCTOR','RESUME_HEADER')
        require(type(tip) is str and HEX.fullmatch(tip) and records[-1]['hash']==tip,'CONDUCTOR','RESUME_TRUSTED_TIP')
        header=records[0]['payload']
        require(header['history']==self.history and header['nonce']==self.m['nonce'],'CONDUCTOR','RESUME_HEADER_PARENTS')
        require(self.clock_identity is not None and header.get('clock_identity') is not None and self.clock_identity()==header['clock_identity'],'CONDUCTOR','RESUME_CLOCK_IDENTITY')
        journal.completed(self.verify_checkpoint_receipt)
        Budget(**header['budget']).check(self.clock(),'CONDUCTOR')
        require(self.wall()<self.m['expires_at'],'CONDUCTOR','AUTHORIZATION_EXPIRED')
    def run(self,*,resume=False,resume_tip=None):
        # An advisory exclusive lock prevents two admitted controllers consuming
        # the same root concurrently. It never signals or queries another PID.
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise QualificationFailure('CONDUCTOR','EXECUTION_ROOT_LOCK','EXCLUSIVE','BUSY') from None
            if resume:
                try:self.preflight_resume(resume_tip)
                except BaseException as error:
                    # A rejected resume cannot append to, export into, or clean up
                    # a failed/untrusted historical run.
                    return {'schema':SCHEMA,'manifest':self.parent,'nonce':self.m['nonce'],'status':'RED',
                            'completed_stages':[],'primary_failure':failure(error,'CONDUCTOR','RESUME_PREFLIGHT'),
                            'secondary_failures':[],'cleanup_failures':[],'read_only_retry_failures':[],
                            'history':self.history,'authority':self.m['authority'],'provider_pilot_authorized':False,
                            'full_market_day_authorized':False,'historical_root_unchanged':True}
            return self._run(resume=resume,resume_tip=resume_tip)
        finally:os.close(fd)
    def _run(self,*,resume=False,resume_tip=None):
        stage='CONDUCTOR';budget=None;cleaned=False;cleanup_receipt=None
        try:
            if resume:
                records=self.journal.load();require(bool(records) and records[0]['kind']=='BEGIN','CONDUCTOR','RESUME_HEADER')
                require(type(resume_tip) is str and HEX.fullmatch(resume_tip) and records[-1]['hash']==resume_tip,'CONDUCTOR','RESUME_TRUSTED_TIP')
                header=records[0]['payload'];require(header['history']==self.m['history'],'CONDUCTOR','HISTORY_IMMUTABLE')
                require(self.clock_identity is not None and header.get('clock_identity') is not None and self.clock_identity()==header['clock_identity'],'CONDUCTOR','RESUME_CLOCK_IDENTITY')
                require(header.get('nonce')==self.m['nonce'],'CONDUCTOR','RESUME_NONCE')
                budget=Budget(**header['budget']);self.completed=self.journal.completed(self.verify_checkpoint_receipt)
            else:
                require(not list(self.root.glob('checkpoint-*.json')),'CONDUCTOR','FRESH_EXECUTION')
                budget=Budget.create(self.clock() if self.initial_start is None else self.initial_start,self.m['limits'])
                self.journal.append('BEGIN','CONDUCTOR',{'budget':budget.__dict__,'history':self.m['history'],'nonce':self.m['nonce'],'clock_identity':self.clock_identity() if self.clock_identity else None})
            for row in self.m['stages'][len(self.completed):]:
                require(digest(self.m)==self.parent,'CONDUCTOR','MANIFEST_MUTATION')
                stage=row['id'];phase='export' if stage==STAGES[-1] else 'work'
                if stage==STAGES[-1]:
                    cleaned=True
                    try:
                        budget.check(self.clock(),'CLEANUP','cleanup')
                        result=self.cleanup(budget.cleanup_end)
                        budget.check(self.clock(),'CLEANUP','cleanup')
                        require(result.get('verified') is True and result.get('outstanding')==0,'CLEANUP','CLEANUP_VERIFIED')
                        cleanup_receipt=dict(result)
                    except BaseException as error:
                        self.record_cleanup_failure(error)
                        raise CleanupBoundaryStop()
                budget.check(self.clock(),stage,phase)
                require(self.wall()<self.m['expires_at'],stage,'AUTHORIZATION_EXPIRED')
                require(stage in self.adapters,stage,'PINNED_ADAPTER_REQUIRED','AVAILABLE','MISSING')
                self.journal.append('START',stage,{'effectful':row['effectful']})
                deadline=min(self.clock()+row['maximum_ns'],budget.end if phase=='export' else budget.work_end)
                for attempt in range(row['read_only_retries']+1):
                    try:
                        receipt=self.adapters[stage](json.loads(canonical(row)),deadline,budget)
                        require(digest(self.m)==self.parent,stage,'MANIFEST_MUTATION')
                        budget.check(self.clock(),stage,phase)
                        require(self.clock()<deadline,stage,'STAGE_DEADLINE')
                        require(receipt.get('stage')==stage and receipt.get('status')=='GREEN',stage,'STAGE_RECEIPT_GREEN')
                        require(receipt.get('manifest')==self.parent and receipt.get('history')==self.m['history'],stage,'RECEIPT_PARENTS')
                        require(receipt.get('predicates')==dict.fromkeys(row['predicates'],True),stage,'ALL_PREDICATES_PASSED')
                        require(receipt.get('authority')==self.m['authority'],stage,'RECEIPT_AUTHORITY')
                        self.verify_receipt(receipt)
                        self.journal.append('GREEN',stage,receipt);self.completed.append(stage);break
                    except BaseException as error:
                        detail=failure(error,stage,'ADAPTER_EXCEPTION')
                        if (not row['effectful'] and isinstance(error,QualificationFailure) and error.retryable and
                                detail['predicate'] in row.get('retry_predicates',[]) and attempt<row['read_only_retries'] and self.clock()<deadline):
                            self.events.append(detail);self.journal.append('READ_ONLY_RETRY',stage,detail);continue
                        raise
        except CleanupBoundaryStop:pass
        except BaseException as error:
            self.primary=failure(error,stage,'CONDUCTOR_EXCEPTION')
            for item in getattr(error,'secondary_cleanup',()):
                self.cleanup_failures.append(QualificationFailure(item['stage'],item['predicate'],item['expected'],item['observed'],exception=item['exception_subtype'],errno_category=item['errno_category']).detail)
        if budget is not None and not cleaned:
            try:
                budget.check(self.clock(),'CLEANUP','cleanup')
                cleanup=self.cleanup(budget.cleanup_end)
                budget.check(self.clock(),'CLEANUP','cleanup')
                require(cleanup.get('verified') is True and cleanup.get('outstanding')==0,'CLEANUP','CLEANUP_VERIFIED')
                cleanup_receipt=dict(cleanup)
            except BaseException as error:self.record_cleanup_failure(error)
        report={'schema':SCHEMA,'manifest':self.parent,'nonce':self.m['nonce'],
                'status':'GREEN' if len(self.completed)==len(STAGES) and self.primary is None and not self.cleanup_failures else 'RED',
                'completed_stages':list(self.completed),'primary_failure':self.primary,'secondary_failures':self.secondary,
                'cleanup_failures':self.cleanup_failures,'cleanup_receipt':cleanup_receipt,'read_only_retry_failures':self.events,'history':self.history,
                'authority':self.m['authority'],'provider_pilot_authorized':False,'full_market_day_authorized':False}
        if self.cleanup_failures:report['status']='YELLOW' if self.primary is None else 'RED'
        # Final journal and report are provisional until the independently verified export seal exists.
        try:self.journal.append('FINAL',stage,report)
        except BaseException as error:
            self.secondary.append(failure(error,'CONDUCTOR','FINAL_CHECKPOINT_EXCEPTION'));report['status']='RED'
        try:
            require(budget is not None,'EVIDENCE_EXPORT_AND_VERIFICATION','EXPORT_BUDGET_AVAILABLE')
            budget.check(self.clock(),STAGES[-1],'export')
            self.export(report,budget.end)
            budget.check(self.clock(),STAGES[-1],'export')
        except BaseException as error:
            self.secondary.append(failure(error,STAGES[-1],'EXPORT_EXCEPTION'));report['status']='RED'
            try:self.journal.append('EXPORT_FAILURE',STAGES[-1],report)
            except Exception:pass
        return report
