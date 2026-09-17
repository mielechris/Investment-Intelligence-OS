import copy,errno,json,os,tempfile,unittest
from pathlib import Path
from iios_native_conductor import *
from iios_native_evidence import export,verify_export,fresh_root
from iios_native_ownership import OwnedProcess,reconcile_pid
from collections import namedtuple


def manifest():
    return {'schema':SCHEMA,'version':1,'scope':'NON_PROVIDER_MAC_QUALIFICATION','nonce':'a'*64,
            'expires_at':10000,'maximum_executions':1,'authority':dict.fromkeys(AUTHORITIES,False),
            'separate_gates':['PROVIDER_PILOT','FULL_MARKET_DAY'],'limits':{'total_ns':1000,'work_ns':800,'cleanup_ns':100,'export_ns':100},
            'history':{'attempt7':'UNVERIFIED','attempt8':'VERIFIED_TERMINATION','attempt10':'UNVERIFIED'},
            'stages':[{'id':s,'effectful':s in EFFECTFUL,'read_only_retries':0,'maximum_ns':50,'predicates':['EXACT_INPUT','STAGE_COMPLETE']} for s in STAGES]}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();os.chmod(self.root,0o700);self.m=manifest();self.now=10;self.calls=[];self.clean=[];self.exported=[]
    def tearDown(self):self.tmp.cleanup()
    def receipt(self,s):return {'stage':s,'status':'GREEN','manifest':digest(self.m),'history':copy.deepcopy(self.m['history']),'predicates':dict.fromkeys(next(r for r in self.m['stages'] if r['id']==s)['predicates'],True),'authority':self.m['authority'],'artifacts':[]}
    def adapter(self,s):
        def call(*args):self.calls.append(s);return self.receipt(s)
        return call
    def engine(self,overrides=None,**kw):
        adapters={s:self.adapter(s) for s in STAGES};adapters.update(overrides or {})
        def clean(deadline):self.clean.append(deadline);return {'verified':True,'outstanding':0}
        def exported(r,d):self.exported.append(r.copy())
        options=dict(clock_identity=lambda:"FIXTURE_BOOT",clock=lambda:self.now,wall=lambda:100,verify_receipt=lambda r:None,cleanup=clean,export=exported);options.update(kw)
        return Conductor(self.m,digest(self.m),self.root,adapters,**options)
    def test_all_nine_transitions_once(self):
        r=self.engine().run();self.assertEqual(r['status'],'GREEN');self.assertEqual(self.calls,list(STAGES));self.assertEqual(len(self.clean),1)
        j=Journal(self.root,digest(self.m));records=j.load();self.assertEqual([r['stage'] for r in records if r['kind']=='GREEN'],list(STAGES))
    def test_failure_at_every_stage_stops_continuation(self):
        for index,s in enumerate(STAGES):
            with self.subTest(stage=s),tempfile.TemporaryDirectory() as root:
                self.root=Path(root).resolve();self.calls=[]
                def fail(*a):raise QualificationFailure(s,'EXACT_NATIVE_PREDICATE','EXPECTED','OBSERVED',exception='PermissionError',errno_category='EPERM')
                r=self.engine({s:fail}).run();self.assertEqual(r['status'],'RED');self.assertEqual(self.calls,list(STAGES[:index]));self.assertEqual(r['primary_failure']['predicate'],'EXACT_NATIVE_PREDICATE')
    def test_effectful_retry_forbidden(self):
        for r in self.m['stages']:
            if r['effectful']:
                x=copy.deepcopy(self.m);x['stages'][STAGES.index(r['id'])]['read_only_retries']=1
                with self.assertRaises(QualificationFailure):validate_manifest(x,digest(x),now=0)
    def test_read_only_reviewed_retry(self):
        row=self.m['stages'][2];row.update(read_only_retries=1,retry_review='b'*64,retry_predicates=['TRANSIENT_OBSERVATION']);calls=[]
        def transient(*a):
            calls.append(1)
            if len(calls)==1:raise QualificationFailure(STAGES[2],'TRANSIENT_OBSERVATION','AVAILABLE','BUSY',retryable=True)
            return self.receipt(STAGES[2])
        r=self.engine({STAGES[2]:transient}).run();self.assertEqual(r['status'],'GREEN');self.assertEqual(len(calls),2);self.assertEqual(len(r['read_only_retry_failures']),1)
    def test_unreviewed_read_only_retry_rejected(self):
        self.m['stages'][0]['read_only_retries']=1
        with self.assertRaises(QualificationFailure):self.engine()
    def test_read_only_retry_never_expands_predicates(self):
        self.m['stages'][0].update(read_only_retries=2,retry_review='b'*64,retry_predicates=['OTHER']);calls=[]
        def fail(*a):calls.append(1);raise QualificationFailure(STAGES[0],'DENIED','PASS','DENIED',retryable=True)
        r=self.engine({STAGES[0]:fail}).run();self.assertEqual(len(calls),1);self.assertEqual(r['primary_failure']['predicate'],'DENIED')
    def test_lower_errno_preserved(self):
        def denied(*a):raise PermissionError(errno.EACCES,'never retain this')
        r=self.engine({STAGES[1]:denied}).run();self.assertEqual(r['primary_failure']['errno_category'],'EACCES');self.assertNotIn('never retain',str(r))
    def test_lower_predicate_preserved(self):
        def denied(*a):raise ValueError('DERIVED_FILE_TYPE')
        self.assertEqual(self.engine({STAGES[4]:denied}).run()['primary_failure']['predicate'],'DERIVED_FILE_TYPE')
    def test_primary_cleanup_export_separate(self):
        def primary(*a):raise ValueError('DERIVED_FILE_TYPE')
        def cleanup(*a):raise PermissionError(errno.EPERM,'raw')
        def exporting(*a):raise OSError(errno.EIO,'raw')
        r=self.engine({STAGES[4]:primary},cleanup=cleanup,export=exporting).run()
        self.assertEqual(r['primary_failure']['predicate'],'DERIVED_FILE_TYPE');self.assertEqual(r['cleanup_failures'][0]['errno_category'],'EPERM');self.assertEqual(r['secondary_failures'][0]['errno_category'],'EIO')
    def test_partial_cleanup_no_green(self):
        r=self.engine(cleanup=lambda d:{'verified':False,'outstanding':1}).run();self.assertNotEqual(r['status'],'GREEN');self.assertEqual(r['history'],self.m['history'])
    def test_manifest_tampering(self):
        with self.assertRaises(QualificationFailure):validate_manifest(self.m,'0'*64,now=0)
    def test_expired_authority(self):
        self.m['expires_at']=99
        with self.assertRaises(QualificationFailure):self.engine()
    def test_authority_defaults_false(self):
        self.m['authority']['provider_access']=True
        with self.assertRaises(QualificationFailure):self.engine()
    def test_skipped_state_rejected(self):
        self.m['stages'].pop(3)
        with self.assertRaises(QualificationFailure):self.engine()
    def test_misclassified_effect_rejected(self):
        self.m['stages'][4]['effectful']=False
        with self.assertRaises(QualificationFailure):self.engine()
    def test_budget_cannot_reset(self):
        def expire(*a):self.now=811;return self.receipt(STAGES[0])
        r=self.engine({STAGES[0]:expire}).run();self.assertEqual(r['primary_failure']['predicate'],'OUTER_WORK_DEADLINE')
    def test_stage_deadline(self):
        def expire(*a):self.now=60;return self.receipt(STAGES[0])
        self.assertEqual(self.engine({STAGES[0]:expire}).run()['primary_failure']['predicate'],'STAGE_DEADLINE')
    def test_cleanup_before_export_reserve(self):
        order=[]
        def clean(*a):order.append('cleanup');self.now=905;return {'verified':True,'outstanding':0}
        def stage(*a):order.append('export_stage');self.now=950;return self.receipt(STAGES[-1])
        r=self.engine({STAGES[-1]:stage},cleanup=clean).run();self.assertEqual(order,['cleanup','export_stage']);self.assertEqual(r['status'],'GREEN')
    def test_incomplete_predicates(self):
        def incomplete(*a):r=self.receipt(STAGES[4]);r['predicates'].pop('EXACT_INPUT');return r
        self.assertEqual(self.engine({STAGES[4]:incomplete}).run()['primary_failure']['predicate'],'ALL_PREDICATES_PASSED')
    def test_history_reclassification_rejected(self):
        def changed(*a):r=self.receipt(STAGES[2]);r['history']['attempt10']='VERIFIED_TERMINATION';return r
        self.assertEqual(self.engine({STAGES[2]:changed}).run()['primary_failure']['predicate'],'RECEIPT_PARENTS')
    def prefix(self,count=2):
        j=Journal(self.root,digest(self.m));b=Budget.create(self.now,self.m['limits']);j.append('BEGIN','CONDUCTOR',{'budget':b.__dict__,'history':self.m['history'],'nonce':self.m['nonce'],'clock_identity':'FIXTURE_BOOT'})
        for s in STAGES[:count]:j.append('START',s,{});j.append('GREEN',s,self.receipt(s))
        return j
    def test_resume_only_completed_prefix(self):
        j=self.prefix();r=self.engine().run(resume=True,resume_tip=j.records[-1]['hash']);self.assertEqual(r['status'],'GREEN');self.assertEqual(self.calls,list(STAGES[2:]))
    def test_no_untrusted_resume_tip(self):
        self.prefix();r=self.engine().run(resume=True);self.assertEqual(r['primary_failure']['predicate'],'RESUME_TRUSTED_TIP');self.assertEqual(self.calls,[])
    def test_interrupted_effect_never_replayed(self):
        j=self.prefix(4);j.append('START',STAGES[4],{})
        r=self.engine().run(resume=True,resume_tip=j.records[-1]['hash']);self.assertEqual(r['primary_failure']['predicate'],'INTERRUPTED_STAGE_NO_REPLAY');self.assertEqual(self.calls,[])
    def test_checkpoint_tamper(self):
        j=self.prefix();p=self.root/'checkpoint-0001.json';v=json.loads(p.read_text());v['payload']['altered']=True;p.write_text(json.dumps(v))
        r=self.engine().run(resume=True,resume_tip=j.records[-1]['hash']);self.assertEqual(r['primary_failure']['predicate'],'CHECKPOINT_HASH')
    def test_stale_resume_deadline(self):
        j=self.prefix();self.now=2000;r=self.engine().run(resume=True,resume_tip=j.records[-1]['hash']);self.assertEqual(r['primary_failure']['predicate'],'OUTER_WORK_DEADLINE')
    def test_final_execution_cannot_resume(self):
        self.engine().run();j=Journal(self.root,digest(self.m));j.load();r=self.engine().run(resume=True,resume_tip=j.records[-1]['hash']);self.assertEqual(r['primary_failure']['predicate'],'EXECUTION_ALREADY_FINAL')
    def test_evidence_export_and_tamper(self):
        r=self.engine(export=lambda r,d:export(self.root,r,d,lambda:self.now)).run();self.assertEqual(verify_export(self.root,digest(self.m))['status'],'GREEN')
        (self.root/'checkpoint-0000.json').write_text('{}')
        with self.assertRaises(QualificationFailure):verify_export(self.root,digest(self.m))
    def test_unexpected_evidence_file(self):
        self.engine(export=lambda r,d:export(self.root,r,d,lambda:self.now)).run();(self.root/'unadmitted').write_text('x')
        with self.assertRaises(QualificationFailure):verify_export(self.root,digest(self.m))
    def test_fresh_root_exclusive(self):
        s=self.root.stat();identity=[s.st_dev,s.st_ino,s.st_uid,0o700];q=fresh_root(self.root,'qualification-test',identity);self.assertEqual(q.stat().st_mode&0o777,0o700)
        with self.assertRaises(FileExistsError):fresh_root(self.root,'qualification-test',identity)
    def test_wrong_parent_mode(self):
        s=self.root.stat();os.chmod(self.root,0o755)
        with self.assertRaises(QualificationFailure):fresh_root(self.root,'qualification-test',[s.st_dev,s.st_ino,s.st_uid,0o700])


Obs=namedtuple('Obs','pid parent_pid start_time executable executable_hash argv command cwd')
class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.row=Obs(100,99,'start','/image','hash',('/image','script'),'/image script','/root');self.signals=[]
        class Child:
            pid=100
            def poll(self):return None
            def wait(self,timeout):return 0
        self.child=Child();self.inspect=lambda pid:self.row
    def owner(self):return OwnedProcess(self.child,lambda pid:self.inspect(pid),parent=99,argv=['/image','script'],cwd='/root',executable='/image',executable_hash='hash',stage=STAGES[4],clock=lambda:1,deadline=100)
    def test_all_predicates_preserved(self):
        from iios_native_ownership import PREDICATES
        o=self.owner();rows=o.register();self.assertEqual(len(rows),3);self.assertEqual(set(rows[0]['matches']),set(PREDICATES))
    def test_each_identity_change_never_signaled(self):
        for field,value in dict(pid=101,parent_pid=1,start_time='reused',executable='/other',executable_hash='other',argv=('/other',),command='other',cwd='/other').items():
            self.row=Obs(100,99,'start','/image','hash',('/image','script'),'/image script','/root');o=self.owner();o.register();self.row=self.row._replace(**{field:value})
            with self.assertRaises(QualificationFailure):o.signal(15,authorized=True,send=lambda *a:self.signals.append(a))
        self.assertEqual(self.signals,[])
    def test_denied_inspection_never_signaled(self):
        o=self.owner();o.register()
        def denied(pid):raise PermissionError(errno.EPERM,'raw')
        self.inspect=denied
        with self.assertRaises(PermissionError):o.signal(15,authorized=True,send=lambda *a:self.signals.append(a))
        self.assertEqual(self.signals,[])
    def test_signal_requires_explicit_authority(self):
        o=self.owner();o.register()
        with self.assertRaises(QualificationFailure):o.signal(15,authorized=False,send=lambda *a:self.signals.append(a))
    def test_early_exit_rejected(self):
        self.child.poll=lambda:0
        with self.assertRaises(QualificationFailure):self.owner().register()
    def test_verified_handle_and_independent_absence(self):
        o=self.owner();o.register();self.inspect=lambda pid:None;self.assertTrue(o.finish(1)['verified'])
    def test_later_absence_does_not_register_ownership(self):
        self.inspect=lambda pid:None
        with self.assertRaises(QualificationFailure):self.owner().finish(1)
    def test_reconciliation_absence_only(self):
        r=reconcile_pid(100,lambda p:None,stage=STAGES[2],deadline=100,clock=lambda:1);self.assertFalse(r['cleanup_upgraded']);self.assertFalse(r['historical_ownership'])
    def test_reconciliation_partial_denial_never_absence(self):
        seq=iter([None,self.row,None])
        with self.assertRaises(QualificationFailure):reconcile_pid(100,lambda p:next(seq),stage=STAGES[2],deadline=100,clock=lambda:1)

if __name__=='__main__':unittest.main()
