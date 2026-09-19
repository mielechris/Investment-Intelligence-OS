"""One stable command; execution is restricted to the enrolled self-hosted job."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import time

if __package__ in (None,''):
    sys.path.append(str(Path(__file__).resolve().parents[1]))
from iios_qualification_v2.state import AUTHORITY, STAGES, Store, decode, directory, digest, export, file_hash, historical_exception, require, canonical
from iios_qualification_v2 import runtime
from iios_qualification_v2 import native
from iios_qualification_v2 import roots as durable


def execute(store, stages, *, source, boot, resume, issuer, evidence):
    """No retry loop. A caller supplies one ordered set of native stage implementations."""
    require(tuple(stages)==STAGES[:-1], 'STAGE_SET')
    store.begin(source,boot,resume=resume)
    completed=[];failure=None;cleanup=None
    try:
        for name, operation in stages.items():
            store.append('STAGE_STARTED',dict(stage=name,source=source,boot=boot))
            value=operation()
            store.append('STAGE_PASSED',dict(stage=name,source=source,boot=boot,receipt=value))
            completed.append(name)
            if name=='cleanup':cleanup=value
    except BaseException as error:
        failure=dict(stage=name,category=type(error).__name__,predicate=str(error)[:240])
        store.append('STAGE_FAILED',failure)
        if name!='cleanup':
            try:
                cleanup=stages['cleanup']()
                store.append('FAILURE_CLEANUP',cleanup)
            except BaseException as cleanup_error:
                cleanup=dict(verified=False,status='NOT_ESTABLISHED',category=type(cleanup_error).__name__)
                store.append('FAILURE_CLEANUP',cleanup)
    status=('GREEN' if issuer is not None else 'OFFLINE_PASS') if failure is None else 'RED'
    summary=dict(schema='iios-native-qualification-v2',profile='observation',status=status,
                 source=source,boot=boot,issuer=issuer,completed=completed,failure=failure,cleanup=cleanup,
                 authority=AUTHORITY,provider_requests=0,scope='SYNTHETIC_THREE_ROLE_QUALIFICATION_ONLY',
                 root_binding=store.root_binding,production_qualified=False,historical_cleanup='NOT_ESTABLISHED')
    store.append('EXPORT_PENDING',summary)
    try:
        destination=export(store,evidence,summary)
        store.append('FINAL',dict(status=status,export=destination,manifest_sha256=file_hash(Path(destination)/'manifest.json')))
    except BaseException as error:
        summary.update(status='RED',failure=dict(stage='export',category=type(error).__name__))
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
    parser.add_argument('--rebuild-runtime',action='store_true',help='Preserve an incomplete venv under a retired name, then rebuild once')
    args=parser.parse_args(argv)
    os.umask(0o077)
    source=Path(__file__).resolve().parents[3]
    config=decode((source/'config/native-qualification-v2.json').read_bytes())
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
    runtime.ENV['TMPDIR']=str(directory(roots['qualification']/'scratch'))
    issuer=native.selected_host(roots['qualification']/'selected-host.json',config['workflow'])
    require(os.environ.get('GITHUB_SHA')==runtime.command(['/usr/bin/git','rev-parse','HEAD'],cwd=source).strip(),'JOB_SOURCE_SHA')
    import signal
    def cancelled(signum,frame):raise RuntimeError('CONTROLLER_CANCELLED')
    signal.signal(signal.SIGTERM,cancelled)
    current=native.boot();binding=runtime.source_identity(source)
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
            value=runtime.environment(roots['runtime'],config,lock,artifacts,rebuild=args.rebuild_runtime)
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
        result=execute(store,stages,source=binding['commit'],boot=current,resume=args.resume,issuer=issuer,evidence=roots['evidence'])
        print(canonical(result).decode(),end='')
        return 0 if result['status']=='GREEN' else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(canonical(dict(status='RED',stage='ADMISSION',category=type(error).__name__,predicate=str(error)[:240],authority=AUTHORITY,native_qualified=False)).decode(),end='')
        raise SystemExit(1)
