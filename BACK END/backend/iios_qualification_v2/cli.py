"""One stable command; execution is restricted to the enrolled self-hosted job."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import time

class _QualificationSourceLoader(importlib.machinery.SourceFileLoader):
    """Compile qualification source directly; never consult or write a pyc cache."""
    def get_code(self, fullname):
        raw=Path(self.path).read_bytes()
        self.source_sha256=hashlib.sha256(raw).hexdigest()
        return compile(raw,self.path,'exec',dont_inherit=True,optimize=sys.flags.optimize)


class _QualificationSourceFinder:
    def find_spec(self, fullname, path=None, target=None):
        if fullname!='iios_qualification_v2' and not fullname.startswith('iios_qualification_v2.'):
            return None
        parts=fullname.split('.')
        if not all(p.isidentifier() for p in parts):raise ImportError('QUALIFICATION_MODULE_NAME')
        base=Path(__file__).resolve().parent
        filename=base/'__init__.py' if len(parts)==1 else base.joinpath(*parts[1:]).with_suffix('.py')
        if not filename.is_file() or filename.is_symlink():raise ImportError('QUALIFICATION_SOURCE_ONLY')
        loader=_QualificationSourceLoader(fullname,str(filename))
        return importlib.util.spec_from_file_location(fullname,filename,loader=loader,
            submodule_search_locations=[str(base)] if len(parts)==1 else None)


if __package__ in (None,''):
    sys.dont_write_bytecode=True
    sys.meta_path.insert(0,_QualificationSourceFinder())
    sys.path.append(str(Path(__file__).resolve().parents[1]))
from iios_qualification_v2.state import AUTHORITY, STAGES, Store, decode, directory, digest, export, file_hash, historical_exception, require, canonical, sanitized
from iios_qualification_v2 import runtime
from iios_qualification_v2 import native
from iios_qualification_v2 import provenance
from iios_qualification_v2 import roots as durable
from iios_qualification_v2.preflight_evidence import EvidenceUnavailable, Writer, parents_from_host


def execute(store, stages, *, source, boot, resume, issuer, evidence, status=None, controller=None):
    """No retry loop. A caller supplies one ordered set of native stage implementations."""
    require(tuple(stages)==STAGES[:-1], 'STAGE_SET')
    store.begin(source,boot,resume=resume)
    completed=[];failure=None;cleanup=None;launch=None;launch_hash=None
    name='controller_launch'
    diagnostic_source=Path(__file__).resolve().parents[3]
    try:
        require(issuer is None or controller is not None,'CONTROLLER_RECEIPT_REQUIRED')
        if controller is not None:
            records=store.load()
            context=dict(source=source,boot=boot,issuer_sha256=digest(issuer),
                         previous=records[-1]['hash'],output_root=str(evidence))
            observed=controller()
            launch=provenance.launch_receipt(observed,context=context)
            provenance.validate_launch(launch,controller(),context=context,records=records)
            launch_hash=digest(sanitized(launch))
            store.append('CONTROLLER_LAUNCH',launch)
        for name, operation in stages.items():
            if status:status(name,'STARTED')
            store.append('STAGE_STARTED',dict(stage=name,source=source,boot=boot))
            value=operation()
            store.append('STAGE_PASSED',dict(stage=name,source=source,boot=boot,receipt=value))
            if status:status(name,'PASSED')
            completed.append(name)
            if name=='cleanup':cleanup=value
    except BaseException as error:
        failure=dict(stage=name,category=type(error).__name__ if type(error).__module__=='builtins' else 'CUSTOM_EXCEPTION',
                     predicate=provenance.exception_predicate(error),
                     exception=provenance.exception_evidence(error,diagnostic_source,stage=name,controller_sha256=launch_hash))
        if hasattr(error,'evidence'):failure['protocol']=sanitized(error.evidence)
        store.append('STAGE_FAILED',failure)
        if status:status(name,'FAILED')
        if name!='cleanup':
            try:
                cleanup=stages['cleanup']()
                store.append('FAILURE_CLEANUP',cleanup)
            except BaseException as cleanup_error:
                cleanup=dict(verified=False,status='NOT_ESTABLISHED',
                    exception=provenance.exception_evidence(cleanup_error,diagnostic_source,stage='cleanup',controller_sha256=launch_hash))
                if hasattr(cleanup_error,'evidence'):cleanup.update(sanitized(cleanup_error.evidence))
                store.append('FAILURE_CLEANUP',cleanup)
    status=('GREEN' if issuer is not None else 'OFFLINE_PASS') if failure is None else 'RED'
    summary=dict(schema='iios-native-qualification-v2',profile='observation',status=status,
                 source=source,boot=boot,issuer=issuer,controller_launch=launch,controller_sha256=launch_hash,completed=completed,failure=failure,cleanup=cleanup,
                 authority=AUTHORITY,provider_requests=0,scope='SYNTHETIC_THREE_ROLE_QUALIFICATION_ONLY',
                 root_binding=store.root_binding,production_qualified=False,historical_cleanup='NOT_ESTABLISHED')
    store.append('EXPORT_PENDING',summary)
    try:
        destination=export(store,evidence,summary)
        store.append('FINAL',dict(status=status,export=destination,manifest_sha256=file_hash(Path(destination)/'manifest.json')))
    except BaseException as error:
        summary.update(status='RED',failure=dict(stage='export',category=type(error).__name__ if type(error).__module__=='builtins' else 'CUSTOM_EXCEPTION',
            exception=provenance.exception_evidence(error,diagnostic_source,stage='export',controller_sha256=launch_hash)))
        store.append('EXPORT_FAILED',summary['failure'])
        return summary
    return dict(summary,export=destination)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Durable IIOS selected-Mac qualification; no automatic retries.')
    parser.add_argument('--profile',choices=['observation'],required=True)
    parser.add_argument('--initialize-roots',action='store_true',help='Explicitly create the exact owner-only durable root; reject existing directories')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--check',action='store_true',help='Static source/lock preparation only; cannot issue native evidence')
    parser.add_argument('--stage-artifacts',type=Path,help='Copy exact already-acquired wheels from a durable qualification directory; no downloads')
    parser.add_argument('--rebuild-runtime',action='store_true',help='Explicitly quarantine one incomplete venv, then build a clean replacement')
    parser.add_argument('--app-preflight',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    os.umask(0o077)
    source=Path(__file__).resolve().parents[3]
    config=decode((source/'config/native-qualification-v2.json').read_bytes())
    config=runtime.bind_vendor_framework_contract(source,config)
    lock=source/'config/production-python-requirements.lock';artifacts=source/'config/production-python-artifacts.lock.json'
    pins=runtime.lock_binding(lock,artifacts)
    if args.check:
        print(canonical(dict(status='PREPARATION_ONLY',lock_sha256=file_hash(lock),wheels=len(pins['wheels']),native_executed=False)).decode(),end='')
        return 0
    bound=durable.binding(initialize=args.initialize_roots)
    roots={name:durable.contained(Path(bound['root'])/name,bound) for name in durable.CHILDREN}
    if args.initialize_roots:
        print(canonical(dict(status='ROOTS_INITIALIZED',root_binding=bound,native_executed=False)).decode(),end='')
        return 0
    if args.stage_artifacts:
        origin=args.stage_artifacts.resolve(strict=True)
        require(origin.is_relative_to(roots['qualification']),'ARTIFACT_SOURCE_DURABLE_ONLY')
        target=directory(roots['runtime']/'wheelhouse')
        for row in pins['wheels']:
            item=origin/row['filename'];runtime.verify_wheel(item,row)
            dest=target/item.name
            if dest.exists():runtime.verify_wheel(dest,row);continue
            with dest.open('xb') as out, item.open('rb') as inp:shutil.copyfileobj(inp,out)
            dest.chmod(0o400);runtime.verify_wheel(dest,row)
        print('PREPARATION_ONLY: exact offline wheels staged; no runtime execution')
        return 0
    writer=None;engine_started=False;host_path=roots['qualification']/'selected-host.json'
    try:
        writer=Writer(roots['evidence'],bound)
        runtime.ENV['TMPDIR']=str(directory(roots['qualification']/'scratch'))
        issuer, expected_source=native.selected_host(host_path)
        binding=(runtime.source_binding_local(source,expected_source) if issuer.get('launch_mode')=='local_app'
                 else runtime.source_binding(source,expected_source))
        if args.app_preflight:
            current=native.boot();store=Store(durable.contained(roots['qualification']/'native-v2',bound),root_binding=bound)
            with store.locked():records=store.load()
            print(canonical(dict(schema=1,status='PREFLIGHT_GREEN',repository=binding['repository'],
                  commit=binding['commit'],branch=binding.get('branch'),inventory_sha256=binding['inventory_sha256'],
                  selected_mac=issuer.get('hardware_uuid'),profile=args.profile,evidence_destination=str(roots['evidence']),
                  preflight_evidence=True,provider_requests=0,authority=AUTHORITY,resume_required=bool(records),
                  runtime_rebuild_required=runtime.partial_rebuild_required(roots['runtime'],runtime.runtime_identity(config,lock,artifacts)),
                  current_boot=current,historical_cleanup='NOT_ESTABLISHED')).decode(),end='')
            return 0
        engine_started=True
    except BaseException as error:
        if isinstance(error,EvidenceUnavailable) or writer is None:
            print(canonical(dict(status='RED',stage='ADMISSION',predicate='EVIDENCE_EXPORT_UNAVAILABLE',
                  diagnostic='EVIDENCE_EXPORT_UNAVAILABLE',authority=AUTHORITY,provider_requests=0,native_qualified=False)).decode(),end='')
            return 1
        receipt=writer.write(error=error,stage='ADMISSION',parents=parents_from_host(host_path),
                             expected=dict(category='LOCAL_APP_PREFLIGHT'),observed=dict(category=type(error).__name__))
        print(canonical(dict(status='RED',stage='ADMISSION',predicate=str(error)[:160],authority=AUTHORITY,
              provider_requests=0,native_qualified=False,preflight_evidence=receipt)).decode(),end='')
        return 1
    import signal
    def cancelled(signum,frame):raise RuntimeError('CONTROLLER_CANCELLED')
    signal.signal(signal.SIGTERM,cancelled)
    current=native.boot()
    store=Store(durable.contained(roots['qualification']/'native-v2',bound),root_binding=bound)
    with store.locked():
        records=store.load()
        require(not records or args.resume,'EXPLICIT_RESUME_REQUIRED')
        from truth_spine_process_identity import inspect_macos
        reconciled=native.reconcile(records,current,inspect_macos)
        history=historical_exception(config['historical'],current)
        revision=sum(r['event']=='BEGIN' for r in records)
        work=durable.contained(store.root/'work'/f'revision-{revision:06d}',bound)
        holder={};deadline=time.monotonic()+config['maximum_seconds']
        def checked(fn):
            def run():
                require(durable.binding()==bound,'DURABLE_BINDING_CHANGED')
                require(time.monotonic()<deadline,'TOTAL_DEADLINE')
                runtime.unchanged(source,binding);require(native.boot()==current,'BOOT_CHANGED')
                result=fn()
                runtime.unchanged(source,binding);require(native.boot()==current,'BOOT_CHANGED')
                return result
            return run
        def selected_runtime():
            quarantine=durable.contained(roots['qualification']/'native-v2'/'runtime-quarantine',bound)
            value=runtime.environment(roots['runtime'],config,lock,artifacts,rebuild=args.rebuild_runtime,quarantine=quarantine,bound=bound)
            holder['native']=native.Native(source,work,store,value,current,deadline)
            return value
        def cleanup():
            if 'native' not in holder:return dict(verified=True,cooperative=True,outstanding=0,no_children_launched=True)
            result=holder['native'].cleanup()
            if hasattr(holder['native'],'port'):
                with __import__('socket').socket() as probe:
                    probe.setsockopt(__import__('socket').SOL_SOCKET,__import__('socket').SO_REUSEADDR,1)
                    probe.bind(('127.0.0.1',holder['native'].port))
                result['listener_absent']=True
            # Rehash runtime after execution, without rebuilding or installing anything.
            value=holder['native'].runtime
            runtime.verify_environment_tree(Path(value['path']),value['manifest']['tree'])
            require(runtime.verify_vendor(config)==value['manifest']['vendor'],'VENDOR_CHANGED')
            require(durable.binding()==bound,'DURABLE_BINDING_CHANGED')
            runtime.unchanged(source,binding)
            require(native.boot()==current,'BOOT_CHANGED')
            return result
        stages=dict(source_lock=checked(lambda:dict(source=binding,lock=file_hash(lock),artifacts=file_hash(artifacts),root_binding=bound)),
                    runtime=checked(selected_runtime),boot=checked(lambda:dict(current=current,historical_exception=history,prior_children=reconciled)),
                    ownership=checked(lambda:holder['native'].ownership()),confinement=checked(lambda:holder['native'].confinement()),
                    startup_ack=checked(lambda:holder['native'].startup()),loopback_tls=checked(lambda:holder['native'].tls()),
                    truth_spine=checked(lambda:holder['native'].truth_spine()),cleanup=cleanup)
        def app_status(stage,value):
            if issuer.get('launch_mode')=='local_app':
                print(canonical(dict(stage=stage,state=value)).decode(),end='',file=sys.stderr,flush=True)
        result=execute(store,stages,source=binding['commit'],boot=current,resume=args.resume,issuer=issuer,
                       evidence=roots['evidence'],status=app_status,controller=lambda:provenance.observe(source,binding,config=config))
        print(canonical(result).decode(),end='')
        return 0 if result['status']=='GREEN' else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(canonical(dict(status='RED',stage='ADMISSION',predicate='EVIDENCE_EXPORT_UNAVAILABLE',
              diagnostic='EVIDENCE_EXPORT_UNAVAILABLE',authority=AUTHORITY,provider_requests=0,native_qualified=False)).decode(),end='')
        raise SystemExit(1)
