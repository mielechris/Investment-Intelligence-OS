"""Pinned manual entrypoint. Imports cannot precede source/audit admission."""
import sys
sys.dont_write_bytecode=True
_preparation_mode=True
_source_verified=False
_source_hashes={}
_source_prefix=__file__.rsplit('/',2)[0]+'/'


def _preparation_audit(event,args):
    if not _preparation_mode:return
    if event=='compile' and isinstance(args[1],str) and args[1].startswith(_source_prefix):
        if not _source_verified or args[1] not in _source_hashes:raise PermissionError('PREPARATION_SOURCE_UNBOUND')
        raw=args[0].encode('utf-8') if isinstance(args[0],str) else args[0]
        if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=_source_hashes[args[1]]:raise PermissionError('PREPARATION_SOURCE_MUTATION')
    if event.startswith(('socket.','subprocess.','ctypes.')) or event in (
            'os.system','os.fork','os.forkpty','os.exec','os.posix_spawn','os.kill','os.killpg',
            'os.mkdir','os.remove','os.rmdir','os.rename','os.link','os.symlink','os.chmod',
            'os.chown','os.truncate','os.utime','os.setxattr','os.removexattr'):
        raise PermissionError('PREPARATION_EFFECT_DENIED')
    if event=='open':
        path,mode,flags=args
        if isinstance(path,int):
            if path not in (0,1,2):raise PermissionError('PREPARATION_UNBOUND_FD')
        elif isinstance(path,(str,bytes)):
            text=path.decode() if isinstance(path,bytes) else path
            if text.endswith(('.pyc','.pyo')):raise PermissionError('PREPARATION_BYTECODE_DENIED')
            if '\0' in text or '..' in text.split('/') or any(part.lower() in ('credentials','keychains','ledger','ledgers','.ssh','.aws') or part.startswith('~') for part in text.split('/')):
                raise PermissionError('PREPARATION_PROTECTED_PATH')
        else:raise PermissionError('PREPARATION_PATH_TYPE')
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(1|2|8|512|1024|2048)):
            raise PermissionError('PREPARATION_WRITE_DENIED')


sys.addaudithook(_preparation_audit)
import argparse
import hashlib
import errno
import json
import stat
from pathlib import Path
import time
_SOURCE=Path(__file__).resolve().parents[1]
for relative in ('tests/native','scripts','BACK END/backend'):sys.path.insert(0,str(_SOURCE/relative))


def bootstrap_source(path,parent,deadline=None):
    """Verify actual source bytes before the first repository module import."""
    global _source_verified,_source_hashes
    def need(value,code):
        if not value:raise ValueError(code)
    def check():
        if deadline is not None:need(time.clock_gettime_ns(6)<deadline,'PRELAUNCH_DEADLINE')
    check();raw=path.read_bytes();need(len(raw)<=32*1024*1024,'MANIFEST_SIZE')
    def unique(pairs):
        result={}
        for key,value in pairs:need(key not in result,'MANIFEST_DUPLICATE_KEY');result[key]=value
        return result
    manifest=json.loads(raw,object_pairs_hook=unique)
    canonical=(json.dumps(manifest,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    need(hashlib.sha256(canonical).hexdigest()==parent,'MANIFEST_HASH')
    need(manifest['source']['root']==str(_SOURCE),'ENTRYPOINT_SOURCE_ROOT')
    need(time.time()<manifest['expires_at'],'AUTHORIZATION_EXPIRED')
    hashes={};rows=manifest['source']['inventory'];need(type(rows) is list and 0<len(rows)<=100000,'SOURCE_INVENTORY_BOUND')
    for row in rows:
        check();name=row['relative'];p=Path(name)
        need(not p.is_absolute() and '..' not in p.parts and str(p)==name,'SOURCE_INVENTORY_PATH')
        target=_SOURCE/p;need(str(target) not in hashes and target.resolve(strict=True)==target,'SOURCE_PATH_SUBSTITUTION')
        before=target.lstat();need(stat.S_ISREG(before.st_mode),'SOURCE_REGULAR_FILE')
        h=hashlib.sha256()
        with target.open('rb') as stream:
            while True:
                check();block=stream.read(65536)
                if not block:break
                h.update(block)
        after=target.lstat();key=lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        need(key(before)==key(after) and h.hexdigest()==row['sha256'],'SOURCE_HASH_OR_MUTATION')
        hashes[str(target)]=row['sha256']
    need(str(Path(__file__).resolve()) in hashes,'ENTRYPOINT_INVENTORY_REQUIRED')
    _source_hashes=hashes;_source_verified=True;check();return manifest


def review(path,parent,deadline=None):
    manifest=bootstrap_source(path,parent,deadline)
    import iios_native_conductor as core
    from iios_native_admission import admit_source,review_bindings,require_execution_ready
    core.validate_manifest(manifest,parent,now=time.time());admit_source(manifest)
    blockers=review_bindings(manifest)
    if not blockers and manifest.get('native_execution_ready'):
        try:require_execution_ready(manifest)
        except core.QualificationFailure as error:blockers.append(error.detail)
    if deadline is not None:core.require(time.clock_gettime_ns(6)<deadline,core.STAGES[0],'PRELAUNCH_DEADLINE')
    return manifest,{'scope':'NON_PROVIDER_MAC_QUALIFICATION','manifest':parent,
        'status':'YELLOW' if blockers or not manifest.get('native_execution_ready') else 'GREEN',
        'review_only':True,'native_executed':False,'primary_failure':blockers[0] if blockers else None,
        'secondary_failures':blockers[1:],'cleanup_failures':[],'history':manifest['history'],
        'authority':manifest['authority'],'stage_order':list(core.STAGES)}


def main(argv=None):
    global _preparation_mode
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True,type=Path);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--resume-binding',type=Path);p.add_argument('--resume-binding-sha256');p.add_argument('--review',action='store_true');p.add_argument('--authorize-manifest');args=p.parse_args(argv)
    execution_entered=False;dispatcher_entered=False;core=None;export_admission_failure=None
    try:
        initial_start=None if args.review else time.clock_gettime_ns(6)
        manifest,report=review(args.manifest,args.manifest_sha256,None if args.review else initial_start+30_000_000_000)
        import iios_native_conductor as core
        if args.review:
            print(json.dumps(report,sort_keys=True));return 0 if report['status']=='GREEN' else 2
        from iios_native_admission import require_execution_ready
        core.require(args.authorize_manifest==args.manifest_sha256,core.STAGES[0],'EXPLICIT_MANIFEST_AUTHORIZATION')
        require_execution_ready(manifest)
        dispatch=manifest['dispatcher'];core.pin_file(dispatch['path'],dispatch['sha256'])
        resume=None
        if args.resume_binding is not None:
            core.require(args.resume_binding_sha256 is not None,core.STAGES[0],'RESUME_BINDING_PIN_REQUIRED')
            core.pin_file(args.resume_binding,args.resume_binding_sha256);raw=args.resume_binding.read_bytes()
            core.require(hashlib.sha256(raw).hexdigest()==args.resume_binding_sha256,core.STAGES[0],'RESUME_BINDING_MUTATION');resume=json.loads(raw)
        else:core.require(args.resume_binding_sha256 is None,core.STAGES[0],'RESUME_BINDING_PAIR')
        from iios_native_evidence import export_admission_failure
        from iios_native_audit import NativeAudit
        audit=NativeAudit(manifest,args.manifest_sha256);audit.install()
        _preparation_mode=False;execution_entered=True
        module=audit.finder.load('iios_native_dispatcher',dispatch['path'],dispatch['sha256'])
        core.require(time.clock_gettime_ns(6)<initial_start+30_000_000_000,core.STAGES[0],'PRELAUNCH_DEADLINE')
        dispatcher_entered=True
        result=module.run(manifest,args.manifest_sha256,resume_binding=resume,audit=audit,initial_start=initial_start)
        print(json.dumps(result,sort_keys=True));return 0 if result['status']=='GREEN' else 2 if result['status']=='YELLOW' else 1
    except Exception as error:
        if core is not None:detail=core.failure(error,core.STAGES[0],'ENTRYPOINT_EXCEPTION')
        else:
            code=error.args[0] if error.args else 'ENTRYPOINT_EXCEPTION'
            if type(code) is not str or not code or len(code)>95 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in code):code='ENTRYPOINT_EXCEPTION'
            subtype=type(error).__name__
            if not subtype.isascii() or not subtype.replace('_','').isalnum() or len(subtype)>95:subtype='Exception'
            category='AUDIT_POLICY' if isinstance(error,PermissionError) and code.startswith('PREPARATION_') else errno.errorcode.get(getattr(error,'errno',None),'NONE')
            detail={'stage':'SOURCE_AND_CI_ADMISSION','predicate':code,'expected':'PASS','observed':'REJECTED','exception_subtype':subtype,'errno_category':category}
        secondary=[]
        if execution_entered and export_admission_failure is not None:
            try:
                audit.enter(core.STAGES[0])
                result=export_admission_failure(manifest,args.manifest_sha256,detail,initial_start,lambda:time.clock_gettime_ns(6),before_dispatcher=not dispatcher_entered,audit_receipt=audit.receipt)
                print(json.dumps(result,sort_keys=True));return 1
            except Exception as export_error:secondary.append(core.failure(export_error,'EVIDENCE_EXPORT_AND_VERIFICATION','EARLY_FAILURE_EXPORT_EXCEPTION'))
        print(json.dumps({'status':'RED','primary_failure':detail,'secondary_failures':secondary,'native_execution_entered':execution_entered},sort_keys=True));return 1

if __name__=='__main__':raise SystemExit(main())
