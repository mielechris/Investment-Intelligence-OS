"""Manual Apple Terminal entrypoint; never launches Terminal or infers authority.

Review mode is source-only. Native execution requires a complete pinned adapter
bundle; migration blockers produce a consolidated YELLOW report before effects.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'BACK END/backend'))
from iios_native_conductor import validate_manifest,digest,canonical,failure,STAGES
from iios_native_admission import admit_source,review_bindings,require_execution_ready


def review(path,parent):
    raw=Path(path).read_bytes();manifest=json.loads(raw)
    validate_manifest(manifest,parent,now=time.time())
    admit_source(manifest)
    blockers=review_bindings(manifest)
    return manifest,{'scope':'NON_PROVIDER_MAC_QUALIFICATION','manifest':parent,
        'status':'YELLOW' if blockers or not manifest.get('native_execution_ready') else 'GREEN',
        'review_only':True,'native_executed':False,'primary_failure':blockers[0] if blockers else None,
        'secondary_failures':blockers[1:],'cleanup_failures':[], 'history':manifest['history'],
        'authority':manifest['authority'],'stage_order':list(STAGES)}


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True,type=Path);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--review',action='store_true');p.add_argument('--authorize-manifest');args=p.parse_args(argv)
    execution_entered=False
    try:
        manifest,report=review(args.manifest,args.manifest_sha256)
        if args.review:
            print(json.dumps(report,sort_keys=True));return 0 if report['status']=='GREEN' else 2
        from iios_native_conductor import require
        require(args.authorize_manifest==args.manifest_sha256,STAGES[0],'EXPLICIT_MANIFEST_AUTHORIZATION')
        require_execution_ready(manifest)
        # Native stage adapters must provide a pinned, reviewed dispatcher; never
        # silently execute the consumed, hard-coded legacy runners.
        dispatch=manifest['dispatcher']
        from iios_native_conductor import pin_file
        pin_file(dispatch['path'],dispatch['sha256'])
        namespace={'__name__':'iios_pinned_native_dispatcher','__file__':dispatch['path']}
        exec(compile(Path(dispatch['path']).read_bytes(),dispatch['path'],'exec'),namespace)
        execution_entered=True
        result=namespace['run'](manifest,args.manifest_sha256)
        print(json.dumps(result,sort_keys=True));return 0 if result['status']=='GREEN' else 2 if result['status']=='YELLOW' else 1
    except Exception as error:
        print(json.dumps({'status':'RED','primary_failure':failure(error,STAGES[0],'ENTRYPOINT_EXCEPTION'),'native_execution_entered':execution_entered},sort_keys=True));return 1

if __name__=='__main__':raise SystemExit(main())
