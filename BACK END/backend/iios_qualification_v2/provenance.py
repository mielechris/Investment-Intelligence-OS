"""Controller self-observation and bounded, non-authorizing exception evidence.

Never imports candidate modules, executes a harness, reads credentials, or emits
locals, source text, raw exception messages or unapproved environment values.
"""
import contextlib
import hashlib
import importlib.machinery
import os
from pathlib import Path
import sys
import time
import types
import uuid
from datetime import datetime, timezone
from .state import digest, file_hash, require

PREFIX = 'iios_qualification_v2'
REQUIRED = {PREFIX, *(PREFIX+'.'+n for n in
    ('state', 'runtime', 'native', 'roots', 'preflight_evidence', 'provenance'))}
MAX_FRAMES = 32
CONTROLLER_PREDICATES = frozenset((
    'CONTROLLER_PROCESS', 'CONTROLLER_PROCESS_PRESENT', 'CONTROLLER_PID',
    'CONTROLLER_PARENT_PID', 'CONTROLLER_START_TIME', 'CONTROLLER_CWD',
    'CONTROLLER_INTERPRETER_PIN', 'CONTROLLER_LAUNCHER_PATH', 'CONTROLLER_LAUNCHER_HASH',
    'CONTROLLER_IMAGE_PATH', 'CONTROLLER_IMAGE_HASH', 'CONTROLLER_ARGV_IMAGE',
    'CONTROLLER_ARGV', 'CONTROLLER_SOURCE_ROOT', 'CONTROLLER_BYTECODE_FLAGS',
    'CONTROLLER_ENVIRONMENT', 'CONTROLLER_RECEIPT_REQUIRED', 'CONTROLLER_MODULE_MISSING',
    'CONTROLLER_ENTRYPOINT_MODULE', 'CONTROLLER_MODULE_ROOT', 'CONTROLLER_BYTECODE_OR_LOADER',
    'CONTROLLER_SOURCE_ONLY_LOADER_REQUIRED', 'CONTROLLER_LOADER_ORIGIN',
    'CONTROLLER_BYTECODE_CACHE', 'CONTROLLER_MODULE_HASH', 'CONTROLLER_LOADED_SOURCE_HASH',
    'CONTROLLER_WRAPPER_SUBSTITUTION', 'CONTROLLER_LOADED_CODE_SUBSTITUTION',
    'CONTROLLER_MODULE_SUBSTITUTION', 'CONTROLLER_RECEIPT_SCHEMA', 'CONTROLLER_NONCE',
    'CONTROLLER_STALE', 'CONTROLLER_WALL_TIME', 'CONTROLLER_BINDING', 'CONTROLLER_REPLAY',
))
FRAMEWORK = Path('/Library/Frameworks/Python.framework/Versions/3.14')
LAUNCHER = FRAMEWORK/'bin/python3.14'
IMAGE = FRAMEWORK/'Resources/Python.app/Contents/MacOS/Python'
OPERATIONS = {
    'observe': 'CONTROLLER_OBSERVATION', 'controller_interpreter': 'CONTROLLER_INTERPRETER_BINDING',
    'source_identity': 'SOURCE_INVENTORY', 'unchanged': 'SOURCE_REVALIDATION',
    'environment': 'RUNTIME_ADMISSION', 'verify_environment_tree': 'RUNTIME_TREE_VERIFY',
    'verify_vendor': 'VENDOR_VERIFY', 'verify_framework_inventory': 'FRAMEWORK_VERIFY',
    'command': 'SUBPROCESS', 'file_hash': 'FILE_HASH', 'selected_runtime': 'RUNTIME_ADMISSION',
    'copytree': 'TREE_COPY', '_copytree': 'TREE_COPY', 'copy2': 'FILE_COPY',
    '_iterdir': 'DIRECTORY_ENUMERATION', 'iterdir': 'DIRECTORY_ENUMERATION',
    'walk': 'DIRECTORY_ENUMERATION', '_walk': 'DIRECTORY_ENUMERATION', 'scandir': 'DIRECTORY_ENUMERATION', 'stat': 'FILE_STAT', 'lstat': 'FILE_LSTAT',
    'open': 'FILE_OPEN', 'read_bytes': 'FILE_READ', 'resolve': 'PATH_RESOLVE',
}


def code_digest(code):
    def value(v):
        if isinstance(v, types.CodeType):
            return dict(bytecode=v.co_code.hex(), constants=[value(x) for x in v.co_consts],
                        names=v.co_names, variables=v.co_varnames, free=v.co_freevars,
                        cells=v.co_cellvars, flags=v.co_flags, args=v.co_argcount,
                        posonly=v.co_posonlyargcount, kwonly=v.co_kwonlyargcount,
                        exception_table=getattr(v,'co_exceptiontable',b'').hex())
        if isinstance(v, (tuple, frozenset)):
            parts=[value(x) for x in v]
            return dict(kind=type(v).__name__,items=sorted(parts,key=repr) if isinstance(v,frozenset) else parts)
        return dict(kind=type(v).__name__, value=repr(v))
    return digest(value(code))


def module_inventory(source, binding, modules=None, *, source_only=False):
    source=Path(source).resolve(strict=True)
    modules=sys.modules if modules is None else modules
    selected={n:m for n,m in tuple(modules.items()) if n==PREFIX or n.startswith(PREFIX+'.')}
    require(REQUIRED <= set(selected), 'CONTROLLER_MODULE_MISSING')
    entry=modules.get('__main__')
    if getattr(entry,'__file__',None)==str(source/'BACK END/backend/iios_qualification_v2/cli.py'):
        selected['__main__']=entry
    else:
        require(PREFIX+'.cli' in selected,'CONTROLLER_ENTRYPOINT_MODULE')
    pins={r['path']:r['sha256'] for r in binding['inventory']}
    result=[]
    for name,module in sorted(selected.items()):
        expected='BACK END/backend/iios_qualification_v2/'+('cli.py' if name=='__main__' else
                 '__init__.py' if name==PREFIX else name[len(PREFIX)+1:].replace('.','/')+'.py')
        path=Path(getattr(module,'__file__',''))
        spec=getattr(module,'__spec__',None);loader=getattr(module,'__loader__',None)
        require(path.is_absolute() and path==source/expected and not path.is_symlink() and
                path.resolve(strict=True)==path,'CONTROLLER_MODULE_ROOT')
        controller_module=modules.get('__main__') if name=='__main__' or PREFIX+'.cli' not in modules else modules[PREFIX+'.cli']
        source_loader=getattr(controller_module,'_QualificationSourceLoader',None)
        direct=name=='__main__' and type(loader) is importlib.machinery.SourceFileLoader
        enforced=source_loader is not None and type(loader) is source_loader
        require(enforced or type(loader) is importlib.machinery.SourceFileLoader,'CONTROLLER_BYTECODE_OR_LOADER')
        require(not source_only or enforced or direct,'CONTROLLER_SOURCE_ONLY_LOADER_REQUIRED')
        require(name=='__main__' or (spec is not None and spec.origin==str(path) and spec.loader is loader),
                'CONTROLLER_LOADER_ORIGIN')
        cached=getattr(module,'__cached__',None)
        require(not cached or not Path(cached).exists(),'CONTROLLER_BYTECODE_CACHE')
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        require(pins.get(expected)==sha,'CONTROLLER_MODULE_HASH')
        require(not enforced or getattr(loader,'source_sha256',None)==sha,'CONTROLLER_LOADED_SOURCE_HASH')
        compiled=compile(raw,str(path),'exec',dont_inherit=True,optimize=sys.flags.optimize)
        codes={}
        def collect(c):
            codes[(c.co_qualname,c.co_firstlineno)]=code_digest(c)
            for child in c.co_consts:
                if isinstance(child,types.CodeType):collect(child)
        collect(compiled)
        loaded=[]
        def check(v):
            if isinstance(v,(staticmethod,classmethod)):v=v.__func__
            if isinstance(v,types.FunctionType) and v.__module__==name:
                if hasattr(v,'__wrapped__'):
                    require(code_digest(v.__code__)==code_digest(contextlib.contextmanager(lambda:None).__code__),
                            'CONTROLLER_WRAPPER_SUBSTITUTION')
                    loaded.append(code_digest(v.__code__))
                    v=v.__wrapped__
                c=v.__code__;h=code_digest(c)
                require(c.co_filename==str(path) and codes.get((c.co_qualname,c.co_firstlineno))==h,
                        'CONTROLLER_LOADED_CODE_SUBSTITUTION')
                loaded.append(h)
            elif isinstance(v,type) and v.__module__==name:
                for child in vars(v).values():
                    if isinstance(child,property):
                        for f in (child.fget,child.fset,child.fdel):check(f)
                    elif not isinstance(child,type):check(child)
        for member,v in vars(module).items():
            definitions=[c for (q,_),c in codes.items() if q==member]
            if definitions:
                require(isinstance(v,(types.FunctionType,type)) and v.__module__==name,
                        'CONTROLLER_MODULE_SUBSTITUTION')
            check(v)
        result.append(dict(module=name,path=str(path),sha256=sha,loader_origin='SOURCE_ONLY_COMPILE' if enforced else 'DIRECT_SCRIPT' if direct else 'SOURCE_FILE',
                           loaded_code_sha256=digest(sorted(loaded)),bytecode_cache_present=False))
    return result


def environment_projection(environ):
    # Unknown names and all their values are intentionally excluded, not hashed.
    expected={'PATH':'/usr/bin:/bin:/usr/sbin','LC_ALL':'C','TZ':'UTC',
              'HOME':str(Path.home()),'PYTHONDONTWRITEBYTECODE':'1'}
    return {k:('EXPECTED' if environ.get(k)==v else 'ABSENT' if k not in environ else 'OTHER')
            for k,v in expected.items()} | {
        k:('PRESENT_IGNORED' if k in environ else 'ABSENT')
        for k in ('PYTHONPATH','PYTHONHOME','PYTHONPYCACHEPREFIX')}


def controller_interpreter(config, process):
    """Bind launcher and observed image separately to the already hash-bound inventory."""
    entries=config.get('vendor_framework_inventory_entries',[])
    pins={}
    for role,path in (('launcher',LAUNCHER),('image',IMAGE)):
        rows=[r for r in entries if r.get('path')==str(path.relative_to(FRAMEWORK))]
        require(len(rows)==1 and rows[0].get('type')=='file' and
                isinstance(rows[0].get('sha256'),str) and len(rows[0]['sha256'])==64 and
                all(c in '0123456789abcdef' for c in rows[0]['sha256']), 'CONTROLLER_INTERPRETER_PIN')
        pins[role]=rows[0]['sha256']
    require(config.get('vendor_python')==str(LAUNCHER) and sys.executable==str(LAUNCHER) and
            LAUNCHER.resolve(strict=True)==LAUNCHER, 'CONTROLLER_LAUNCHER_PATH')
    require(file_hash(LAUNCHER)==pins['launcher'], 'CONTROLLER_LAUNCHER_HASH')
    require(process.executable==str(IMAGE) and IMAGE.resolve(strict=True)==IMAGE, 'CONTROLLER_IMAGE_PATH')
    require(process.executable_hash==pins['image'] and file_hash(IMAGE)==pins['image'], 'CONTROLLER_IMAGE_HASH')
    require(bool(process.argv) and process.argv[0]==str(IMAGE), 'CONTROLLER_ARGV_IMAGE')
    return dict(category='PINNED_MACOS_FRAMEWORK_LAUNCHER_AND_IMAGE',
                launcher=str(LAUNCHER),launcher_sha256=pins['launcher'],
                image=str(IMAGE),image_sha256=pins['image'],
                framework_inventory_sha256=config['vendor_framework_inventory_sha256'])


def observe(source,binding,inspector=None,*,config):
    if inspector is None:
        from truth_spine_process_identity import inspect_macos
        inspector=inspect_macos
    source=Path(source);require(source.is_absolute() and source.resolve(strict=True)==source,'CONTROLLER_SOURCE_ROOT')
    st=source.stat();process=inspector(os.getpid())
    require(process is not None,'CONTROLLER_PROCESS_PRESENT')
    require(process.pid==os.getpid(),'CONTROLLER_PID')
    require(process.parent_pid==os.getppid(),'CONTROLLER_PARENT_PID')
    require(bool(process.start_time),'CONTROLLER_START_TIME')
    require(process.cwd==str(source),'CONTROLLER_CWD')
    interpreter=controller_interpreter(config,process)
    entry=source/'BACK END/backend/iios_qualification_v2/cli.py'
    args=list(process.argv);tail=args[5:]
    require(len(args)>=7 and args[1:5]==['-I','-B','-S',str(entry)] and tail[:2]==['--profile','observation'] and
            tail[2:] in ([],['--resume'],['--rebuild-runtime'],['--resume','--rebuild-runtime']), 'CONTROLLER_ARGV')
    require(sys.dont_write_bytecode and sys.flags.dont_write_bytecode and sys.flags.isolated and
            sys.flags.no_site and sys.flags.ignore_environment,'CONTROLLER_BYTECODE_FLAGS')
    projection=environment_projection(os.environ)
    require(all(projection[k]=='EXPECTED' for k in ('PATH','LC_ALL','TZ','HOME','PYTHONDONTWRITEBYTECODE')),
            'CONTROLLER_ENVIRONMENT')
    return dict(interpreter=interpreter,process=dict(pid=process.pid,parent_pid=process.parent_pid,start_time=process.start_time,
                             executable=process.executable,executable_sha256=process.executable_hash),
                argv_category='ISOLATED_OBSERVATION'+('_RESUME' if '--resume' in tail else '')+
                              ('_REBUILD_RUNTIME' if '--rebuild-runtime' in tail else ''),
                argv_sha256=digest(args),environment=projection,environment_sha256=digest(projection),
                source_root=dict(path=str(source),identity_sha256=digest(dict(device=st.st_dev,inode=st.st_ino)),
                                 commit=binding['commit'],inventory_sha256=binding['inventory_sha256']),
                entrypoint=dict(path=str(entry),sha256=file_hash(entry)),
                modules=module_inventory(source,binding,source_only=True),bytecode_disabled=True,
                bytecode_policy='SOURCE_ONLY_COMPILE_NO_CACHE_READ_OR_WRITE_DIRECT_SCRIPT_ENTRY')


def launch_receipt(observation, *, context):
    return dict(schema=1,nonce=uuid.uuid4().hex,created_at=datetime.now(timezone.utc).isoformat(),
                monotonic_ns=time.monotonic_ns(),context=context,observation=observation)


def validate_launch(receipt,observation,*,context,records,now_ns=None):
    now_ns=time.monotonic_ns() if now_ns is None else now_ns
    require(set(receipt)=={'schema','nonce','created_at','monotonic_ns','context','observation'} and
            receipt['schema']==1,'CONTROLLER_RECEIPT_SCHEMA')
    require(isinstance(receipt['nonce'],str) and len(receipt['nonce'])==32 and
            all(c in '0123456789abcdef' for c in receipt['nonce']),'CONTROLLER_NONCE')
    require(0 <= now_ns-receipt['monotonic_ns'] <= 60_000_000_000,'CONTROLLER_STALE')
    created=datetime.fromisoformat(receipt['created_at'])
    require(created.tzinfo is not None and 0 <= (datetime.now(timezone.utc)-created).total_seconds() <= 60,
            'CONTROLLER_WALL_TIME')
    require(receipt['context']==context and receipt['observation']==observation,'CONTROLLER_BINDING')
    require(not any(r['event']=='CONTROLLER_LAUNCH' and r['data']['nonce']==receipt['nonce'] for r in records),
            'CONTROLLER_REPLAY')
    return receipt


def exception_predicate(error):
    return error.args[0] if type(error) is ValueError and len(error.args)==1 and \
        isinstance(error.args[0],str) and error.args[0] in CONTROLLER_PREDICATES else 'BOUNDED_EXCEPTION_EVIDENCE'


def exception_evidence(error,source,*,stage,controller_sha256=None):
    source=Path(source);frames=[];count=0;operation='UNKNOWN';tb=error.__traceback__
    while tb is not None:
        c=tb.tb_frame.f_code;path=Path(c.co_filename)
        relative=str(path.relative_to(source)) if path.is_absolute() and path.is_relative_to(source) else None
        # Only fixed qualification filenames are displayed. External locations remain exact digests.
        trusted=relative in {'BACK END/backend/iios_qualification_v2/'+n+'.py' for n in
            ('__init__','cli','provenance','runtime','native','state','roots','preflight_evidence','child')}
        location=dict(path=relative if trusted else 'EXTERNAL',symbol=c.co_qualname[:160] if trusted else 'EXTERNAL',path_sha256=digest(str(path)),
                      code_sha256=code_digest(c),line=tb.tb_lineno,instruction=tb.tb_lasti)
        frames.append(location);frames=frames[-MAX_FRAMES:];count+=1
        if c.co_name in OPERATIONS:operation=OPERATIONS[c.co_name]
        tb=tb.tb_next
    filename=getattr(error,'filename',None);target='CONTROLLER_PROCESS' if stage=='controller_launch' else 'UNKNOWN'
    if isinstance(filename,(str,bytes)):
        p=Path(os.fsdecode(filename))
        if p==source/'bazel-out' or p.is_relative_to(source/'bazel-out'):target='GENERATED_SOURCE_BAZEL_OUT'
        elif p.is_relative_to(source):target='SOURCE_TREE'
        elif p.is_relative_to(Path.home()/'Library/IIOS/runtime'):target='QUALIFICATION_RUNTIME'
        elif p.is_relative_to('/Library/Frameworks/Python.framework'):target='VENDOR_FRAMEWORK'
        else:target='EXTERNAL'
    return dict(schema=1,stage=stage,predicate=exception_predicate(error),controller_sha256=controller_sha256,
                exception_category=type(error).__name__ if type(error).__module__=='builtins' else 'CUSTOM_EXCEPTION',
                frames=frames,frame_count=count,truncated=count>MAX_FRAMES,
                traceback_sha256=digest(frames),call_site=frames[-1] if frames else None,
                call_site_sha256=digest(frames[-1]) if frames else None,
                operation_category=operation,target_category=target)
