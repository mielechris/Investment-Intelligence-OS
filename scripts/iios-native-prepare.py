import ast,ctypes,hashlib,io,json,os,platform,re,ssl,subprocess,sys,time,unittest,tempfile
from pathlib import Path,PurePosixPath
sys.dont_write_bytecode=True
os.umask(0o077)
source=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(source/'BACK END/backend'))
from iios_qualification_v2.roots import binding, expected_root, contained
if '--initialize-roots' in sys.argv:
    expected_root().parent.mkdir(mode=0o700,exist_ok=True)
bound=binding(initialize='--initialize-roots' in sys.argv)
base=contained(Path(bound['root'])/'qualification',bound)
root=Path(tempfile.mkdtemp(prefix='iios-provider-connection-source-tests-',dir=base))
# Legacy disposable fixtures are not v2 durable roots. The unchanged legacy
# retained_root guard requires this exact parent. All reports remain durable.
spine=Path(tempfile.mkdtemp(prefix='iios-sb38d-source-tests-',dir='/private/tmp'))
os.environ['IIOS_GATEWAY_TEST_ROOT']=str(root);os.environ['IIOS_SB38D_TEST_ROOT']=str(spine);os.environ['TMPDIR']=str(root);tempfile.tempdir=str(root)
evidence=Path(tempfile.mkdtemp(prefix='preparation-',dir=contained(Path(bound['root'])/'evidence',bound)))
head=subprocess.run(['/usr/bin/git','rev-parse','HEAD'],cwd=source,check=True,capture_output=True,text=True).stdout.strip()
def sha(b):return hashlib.sha256(b).hexdigest()
inventory={str(p.relative_to(source)):{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in source.rglob('*') if p.is_file() and '.git' not in p.parts}
def put(name,value):
 with (evidence/name).open('x') as f:
  json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
 (evidence/name).chmod(0o400)
put('source-candidate.json',dict(inventory=inventory))
print(json.dumps(dict(test_root=str(root),spine_root=str(spine))),flush=True)
GROUPS=['test_iios_bootstrap_diagnostic', 'test_alpha_dummy_tls', 'test_iios_native_role_transport', 'test_iios_native_audit', 'test_iios_native_confinement', 'test_iios_native_pipeline', 'test_iios_native_profile', 'test_iios_native_adapters', 'test_iios_native_image_policy', 'test_iios_native_runtime_reference', 'test_iios_native_terminal', 'test_iios_native_seal_binding', 'test_iios_native_static', 'test_iios_native_conductor', 'test_iios_native_admission', 'test_alpha_assembly_file_type', 'test_provider_gateway_contract', 'test_alpha_observation_qualification', 'test_alpha_session_contract', 'test_alpha_session_integration', 'test_alpha_session_package', 'test_alpha_session_evidence', 'test_alpha_session_preflight', 'test_alpha_short_observation', 'test_alpha_production_runtime', 'test_alpha_observation_lifecycle', 'test_alpha_observation_adapter', 'test_alpha_observation_billing', 'test_alpha_observation_launch', 'test_alpha_observation_execution', 'test_alpha_denial_collector', 'test_alpha_runtime_bootstrap', 'test_provider_gateway_live_contract', 'test_provider_gateway_qualification', 'test_provider_gateway_transport', 'test_provider_gateway_credentials', 'test_provider_gateway_wire', 'test_alpha_market_baseline.BulkTests', 'test_alpha_session_readiness.ReadinessTests.test_final_join_missing_stages_is_yellow_and_flags_false', 'test_alpha_session_readiness.ReadinessTests.test_synthetic_complete_chain_never_live_green', 'test_alpha_session_readiness.SharedSchedulerBoundaryTests', 'test_truth_spine_process_identity.StabilizationTests', 'test_truth_spine_process_identity.ReceiptTests', 'test_truth_spine_process_identity.InspectionDiagnosticTests', 'test_truth_spine_process_identity.ObservationEnvelopeTests', 'test_truth_spine_runner.HistoricalAcceptanceTests', 'test_truth_spine_runner.ObservationOwnerTests', 'test_truth_spine_runner.OfflineSchedulerHealthTests', 'test_truth_spine_runner.RunnerTests.test_fingerprint_complete_frozen_and_independently_verified', 'test_truth_spine_runner.RunnerTests.test_reused_pid_command_not_signaled', 'test_truth_spine_runner.RunnerTests.test_reused_pid_start_time_not_signaled', 'test_truth_spine_runner.RunnerTests.test_changed_root_not_signaled', 'test_truth_spine_runner.RunnerTests.test_changed_executable_not_signaled', 'test_truth_spine_runner.RunnerTests.test_changed_parent_not_signaled', 'test_truth_spine_runner.RunnerTests.test_missing_process_no_signal_and_retained', 'test_truth_spine_runner.RunnerTests.test_inspector_exception_no_signal', 'test_truth_spine_runner.RunnerTests.test_graceful_exit_untracks_only_after_wait', 'test_truth_spine_runner.RunnerTests.test_already_reaped_verified_child_never_signaled', 'test_truth_spine_runner.RunnerTests.test_timeout_force_stop_reverifies', 'test_truth_spine_runner.RunnerTests.test_identity_changes_after_timeout_no_force', 'test_truth_spine_runner.RunnerTests.test_terminate_exception_retains_child', 'test_truth_spine_runner.RunnerTests.test_wait_exception_retains_child', 'test_truth_spine_runner.RunnerTests.test_force_exception_retains_child', 'test_truth_spine_runner.RunnerTests.test_force_wait_timeout_retains_child', 'test_truth_spine_runner.RunnerTests.test_reverse_cleanup_continues_after_first_child_failure', 'test_truth_spine_runner.RunnerTests.test_all_stops_fail_still_close_logs_and_check_port', 'test_truth_spine_runner.RunnerTests.test_log_close_failure_does_not_skip_other_log', 'test_truth_spine_runner.RunnerTests.test_occupied_port_is_red', 'test_truth_spine_runner.RunnerTests.test_port_check_exception_is_red', 'test_truth_spine_runner.RunnerTests.test_normal_persistence_failure_emergency_and_other_output_attempted', 'test_truth_spine_runner.RunnerTests.test_all_persistence_failure_remains_red', 'test_truth_spine_runner.RunnerTests.test_repeated_cleanup_has_no_extra_signals_or_writes', 'test_truth_spine_runner.RunnerTests.test_partial_startup_unverified_child_never_signaled', 'test_truth_spine_runner.RunnerTests.test_keyboard_interrupt_still_cleans_up', 'test_truth_spine_runner.RunnerTests.test_primary_and_cleanup_exceptions_preserved_sanitized', 'test_truth_spine_runner.RunnerTests.test_unrestricted_runner_failure_not_persisted', 'test_truth_spine_runner.RunnerTests.test_complete_atomic_reports', 'test_truth_spine_runner.RunnerTests.test_atomic_failure_preserves_prior_bytes', 'test_truth_spine_runner.RunnerTests.test_atomic_writer_rejects_escape_and_symlink', 'test_truth_spine_runner.RunnerTests.test_unknown_executable_pin_rejects_spawn', 'test_truth_spine_runner.RunnerTests.test_duplicate_reaped_rejection_preserves_owner_and_events', 'test_truth_spine_runner.RunnerTests.test_duplicate_wrong_success_is_failure', 'test_truth_spine_runner.RunnerTests.test_live_duplicate_verified_before_rejection', 'test_truth_spine_runner.RunnerTests.test_live_duplicate_timeout_retained_for_verified_cleanup', 'test_truth_spine_runner.RunnerTests.test_unverified_duplicate_never_signaled', 'test_truth_spine_runner.RunnerTests.test_duplicate_lock_or_event_mutation_rejected', 'test_truth_spine_runner.RunnerTests.test_stop_keyboard_interrupt_still_attempts_other_children', 'test_truth_spine_runner.RunnerTests.test_bound_timeout_required', 'test_truth_spine_runner.RunnerTests.test_macos_inspector_fixed_bounded_commands', 'test_truth_spine_runner.RunnerTests.test_macos_missing_process_none', 'test_truth_spine_runner.RunnerTests.test_macos_inspection_timeout_and_oversize_fail_closed', 'test_truth_spine_runner.RunnerTests.test_port_inspection_errors_never_mistaken_for_clear', 'test_truth_spine_runner.RunnerTests.test_readiness_failure_requires_both_503', 'test_truth_spine_session.LifecycleTests', 'test_truth_spine_session.StoreTests', 'test_truth_spine_session.SupervisorTests', 'test_truth_spine_session.ProductionPathTests', 'test_truth_spine_session.SQLiteTransactionSnapshotTests', 'test_truth_spine_session.ObservationPublicationTests', 'test_truth_spine_session.ObservationCIContractTests', 'test_alpha_runtime_files', 'test_deployment_contract.FrameworkRuntimeTests', 'test_deployment_contract.DeploymentContractTest.test_runtime_contract_rejects_writable_missing_symlink_version_and_release_mismatch']
sys.path.insert(0,str(source/'BACK END/backend'));sys.path.insert(0,str(source/'scripts'));sys.path.insert(0,str(source/'tests/native'));sys.dont_write_bytecode=True
blocked=[]
# Lexical rejection precedes filesystem access. Descriptor-relative opens are
# resolved from descriptors issued by this wrapper, never from an untrusted cwd.
roots=(str(root),str(spine),str(evidence));fds={};active=[];real_open=os.open;real_close=os.close;real_dup=os.dup
protected={'keychains','ledgers','ledger','.ssh','.aws','credentials'}
def lexical(value):
    if not isinstance(value,(str,bytes,os.PathLike)):raise PermissionError('PATH_TYPE')
    value=os.fsdecode(os.fspath(value));p=PurePosixPath(value)
    if '\0' in value or '..' in p.parts or any(x.lower() in protected or x.startswith('~') for x in p.parts):
        raise PermissionError('PROTECTED_PATH')
    return str(p)
def allowed_write(path):
    return any(path==r or path.startswith(r+'/') for r in roots)
def scoped_open(path,flags,mode=0o777,*,dir_fd=None):
    value=lexical(path)
    if dir_fd is not None:
        if dir_fd not in fds:raise PermissionError('UNBOUND_DIRECTORY_FD')
        value=lexical(str(PurePosixPath(fds[dir_fd])/value))
    elif not PurePosixPath(value).is_absolute():value=lexical(str(source)+'/'+value)
    if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND) and not allowed_write(value):
        blocked.append('WRITE_ROOT');raise PermissionError('WRITE_ROOT')
    active.append(value)
    try:fd=real_open(path,flags,mode,dir_fd=dir_fd)
    finally:active.pop()
    fds[fd]=value;return fd
def scoped_dup(fd):
    if fd not in fds:raise PermissionError('UNBOUND_DIRECTORY_FD')
    duplicate=real_dup(fd);fds[duplicate]=fds[fd];return duplicate
def scoped_close(fd):
    try:return real_close(fd)
    finally:fds.pop(fd,None)
def policy(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.posix_spawn','os.exec',
            'os.kill','os.killpg','ctypes.dlopen','ctypes.dlsym'):
        return 'FORBIDDEN_EFFECT'
    if event=='open' and not isinstance(args[0],int):
        try:value=active[-1] if active else lexical(args[0])
        except PermissionError:return 'PROTECTED_PATH'
        if not PurePosixPath(value).is_absolute():value=str(source)+'/'+value
        mode,flags=args[1:];write=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if write and not allowed_write(value):return 'WRITE_ROOT'
    if event in ('os.mkdir','os.remove','os.rmdir','os.rename','os.chmod','os.link','os.symlink'):
        count=2 if event in ('os.rename','os.link','os.symlink') else 1
        for i in range(count):
            if isinstance(args[i],int):
                if args[i] not in fds or not allowed_write(fds[args[i]]):return 'WRITE_ROOT'
                continue
            try:value=lexical(args[i])
            except PermissionError:return 'PROTECTED_PATH'
            # A symlink target is stored text, not an accessed/mutated file.
            if event=='os.symlink' and i==0:continue
            if not PurePosixPath(value).is_absolute():
                index=(2+i) if count==2 else (2 if event in ('os.mkdir','os.chmod') else 1)
                fd=args[index] if len(args)>index else -1
                if fd not in (None,-1):
                    if fd not in fds:return 'UNBOUND_DIRECTORY_FD'
                    value=str(PurePosixPath(fds[fd])/value)
                else:value=str(source)+'/'+value
            if not allowed_write(value):return 'WRITE_ROOT'
    return None
def guard(event,args):
    category=policy(event,args)
    if category:blocked.append(category);raise PermissionError(category)
os.open=scoped_open;os.close=scoped_close;os.dup=scoped_dup
sys.addaudithook(guard)  # Before every test-module import and dispatch.
put('guard.json',dict(installed_before_import=True,native_execution=False,legacy_disposable_fixture=str(spine),durable_root_binding=bound))
def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item
class Result(unittest.TestResult):
    def __init__(self):super().__init__();self.rows=[];self.started={};self.outcomes={};self.locations={}
    def startTest(self,test):super().startTest(test);self.started[test.id()]=time.monotonic()
    def addSuccess(self,test):super().addSuccess(test);self.outcomes[test.id()]='PASS'
    def location(self,test,err):
        frame=err[2];location=None
        while frame:
            path=Path(frame.tb_frame.f_code.co_filename)
            if path.is_relative_to(source):location=dict(path=str(path.relative_to(source)),line=frame.tb_lineno)
            frame=frame.tb_next
        self.locations[test.id()]=location
    def addFailure(self,test,err):
        super().addFailure(test,err);self.location(test,err);self.outcomes[test.id()]='FAIL:'+err[0].__name__
        self.locations[test.id()]=(self.locations[test.id()] or {})|{'diagnostic':str(err[1])}
    def addError(self,test,err):
        super().addError(test,err);self.location(test,err);self.outcomes[test.id()]='ERROR:'+err[0].__name__
        self.locations[test.id()]=(self.locations[test.id()] or {})|{'diagnostic':str(err[1])}
    def addSkip(self,test,reason):super().addSkip(test,reason);self.outcomes[test.id()]='SKIPPED'
    def stopTest(self,test):
        self.rows.append(dict(test=test.id(),result=self.outcomes.get(test.id(),'UNRESOLVED'),location=self.locations.get(test.id()),seconds=time.monotonic()-self.started[test.id()]))
        super().stopTest(test)
start=time.monotonic();result=Result();failure=None
try:
    suite=unittest.defaultTestLoader.loadTestsFromNames(GROUPS)
    suite.addTests(unittest.defaultTestLoader.discover(str(source/'tests/native_v2')))
    ids=[test.id() for test in flatten(suite)]
    assert ids and len(ids)==len(set(ids)) and not any('_FailedTest' in name for name in ids)
    put('selection.json',dict(groups=GROUPS,ids=ids,sha256=sha(json.dumps(ids).encode()),
        deferred=['test_truth_spine_process_identity.EphemeralMacOSTests','test_truth_spine_runner.IsolatedOwnershipTests',
            'test_truth_spine_runner.RunnerTests.test_scheduler_actual_health_200_503_200_new_fingerprint']))
    suite.run(result)
except Exception as exc:failure=type(exc).__name__
closure={}
for name,module in tuple(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if path and Path(path).is_file():closure[name]=dict(path=path,sha256=sha(Path(path).read_bytes()))
source_unchanged=all(sha((source/p).read_bytes())==v['sha256'] for p,v in inventory.items())
passed=result.wasSuccessful() and result.testsRun>0 and not result.skipped and not blocked and failure is None and source_unchanged
put('results.json',dict(scope='PREPARATION_OFFLINE_ONLY',head=head,root_binding=bound,tests=result.testsRun,
    failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),blocked=blocked,
    failure_category=failure,passed=passed,seconds=time.monotonic()-start,rows=result.rows,
    source_unchanged=source_unchanged,production_qualified=False,selected_mac_qualified=False,native_execution=False,
    historical_cleanup='NOT_ESTABLISHED',credential_access=False,provider_access=False,provider_requests=0,broker_connection=False,broker_connected=False,paper_order_permission=False,
    trade_execution=False,trade_execution_permission=False,live_execution=False))
put('environment.json',dict(python=sys.version,executable=sys.executable,executable_sha256=sha(Path(sys.executable).read_bytes()),
    system=platform.system(),release=platform.release(),version=platform.version(),architecture=platform.machine(),
    image={k:os.environ.get(k,'UNAVAILABLE') for k in ('ImageOS','ImageVersion','RUNNER_OS','RUNNER_ARCH')},
    tls=ssl.OPENSSL_VERSION,module_closure=closure))
put('artifact-hashes.json',{p.name:sha(p.read_bytes()) for p in evidence.iterdir() if p.is_file()})
manifest=json.loads((evidence/'artifact-hashes.json').read_bytes())
assert set(manifest)=={p.name for p in evidence.iterdir()}-{'artifact-hashes.json'}
assert all(sha((evidence/name).read_bytes())==value for name,value in manifest.items())
evidence.chmod(0o500)
print(json.dumps(dict(head=head,tests=result.testsRun,passed=passed,failures=len(result.failures),errors=len(result.errors),evidence=str(evidence),seconds=time.monotonic()-start)))
sys.exit(0 if passed else 1)
