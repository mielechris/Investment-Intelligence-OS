"""Explicit package-driven runner. Default CLI mode validates only; never installs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from alpha_market_baseline import require, verify_plan
from alpha_session_readiness import FLAGS, final_session_receipt
from provider_gateway_contract import content_hash, pin, safe_document, utc
from provider_gateway_credentials import MacKeychain
from provider_gateway_live_contract import admit, amount, verify_qualification_receipt
from provider_gateway_qualification import qualify, publish, safe_root, verify_runtime
from provider_gateway_transport import NativeHTTPS


def validate_package(package, expected):
    safe_document(package);pin(package, expected)
    require(set(package) == {'schema','scope','plan','plan_parent','requests','external_stages','external_pins'}, 'PACKAGE_SCHEMA')
    require(package['schema']=='iios-alpha-monday-package-v1' and package['scope'] in ('OFFLINE_TEST','LIVE_QUALIFICATION'),'PACKAGE_SCOPE')
    plan=package['plan'];verify_plan(plan,package['plan_parent'])
    require(plan['schema']=='iios-alpha-session-plan-v2' and len(package['requests'])==19,'V2_PREFLIGHT_REQUIRED')
    for i,request in enumerate(package['requests']):
        require(set(request)=={'manifest','account','runtime','expected'},'REQUEST_SCHEMA')
        m,a,r=(request[k] for k in ('manifest','account','runtime'))
        require(m['mode']==package['scope'] and a['bulk_plan']==plan and a['bulk_slot']==i,'REQUEST_SLOT')
        admission=admit(m,a,r,expected=request['expected'],now=plan['rows'][i]['valid_from'])
        verify_runtime(admission)
    requests=package['requests']
    if package['scope']=='LIVE_QUALIFICATION':
        require(len({content_hash(r['runtime']) for r in requests})==1,'ONE_RUNTIME_CLOSURE')
    require(len({r['manifest']['source_commit'] for r in requests})==1 and len({r['account']['cost_unit'] for r in requests})==1,'PACKAGE_IDENTITY')
    require(sum(amount(r['manifest']['maximum_cost']) for r in requests)<=min(amount(r['account']['available_unreserved']) for r in requests),'DAY_BUDGET')
    for stage,receipt in package['external_stages'].items():
        pin(receipt,package['external_pins'][stage])
    require(set(package['external_stages'])==set(package['external_pins']) and
            set(package['external_stages']) <= {'yahoo_discovery','candidates_cases','agents','committee','risk','paper_decision'},'EXTERNAL_SCOPE')
    return plan


def run(package, expected, *, enabled=False, clock=None, wait=None, executor=None, stop=None):
    """No automatic retry or implicit activation. Live boundaries cannot be injected.

    External stage hashes must come from independent governance acceptance; this
    runner never invokes agents, brokers, committees, risk engines or orders.
    """
    plan=validate_package(package,expected)
    if not enabled:
        return {'status':'DISABLED_VALIDATION_ONLY','requests':0,**dict.fromkeys(FLAGS,False)}
    live=package['scope']=='LIVE_QUALIFICATION'
    require(not live or (clock is None and wait is None and executor is None),'LIVE_BOUNDARY')
    if live:
        clock=lambda:datetime.now(timezone.utc).isoformat()
        wait=time.sleep
        def executor(request,previous):
            return qualify(request['manifest'],request['account'],request['runtime'],expected=request['expected'],
                           credential_backend=MacKeychain(),network=NativeHTTPS(),expected_bulk_previous=previous)
    require(callable(clock) and callable(wait) and callable(executor),'RUN_BOUNDARIES')
    stop = stop or (lambda:False)
    require(utc(clock()).date().isoformat()=='2026-09-14','MONDAY_ONLY')
    scope='LIVE_EVIDENCE' if live else 'OFFLINE_TEST'
    evidence={};pins={};previous_stage=None
    def stage(name,result,parents):
        nonlocal previous_stage
        doc={'stage':name,'session':'2026-09-14','scope':scope,'previous':previous_stage,
             'result':result,'evidence_parents':parents,'authority':dict.fromkeys(FLAGS,False)}
        evidence[name]=doc;pins[name]=content_hash(doc);previous_stage=pins[name]
    stage('universe','PASS',[plan['universe_parent']])
    receipts=[];starts=[];previous=None;phase_receipts=[];reason=None
    for i,request in enumerate(package['requests']):
        row=plan['rows'][i]
        target=utc(row['valid_from'])
        if len(starts)>=3:
            from datetime import timedelta
            target=max(target,utc(starts[-3])+timedelta(seconds=60))
        while utc(clock())<target and not stop():
            wait(min(1.0,(target-utc(clock())).total_seconds()))
        if stop():
            reason='COOPERATIVE_SHUTDOWN';break
        if utc(clock())>=utc(row['expires_at']):
            reason='MISSED_INTERVAL_NO_BACKFILL';break
        try:
            receipt=executor(request,previous)
            require(receipt['parents']=={**request['expected'],'reservation':receipt['parents']['reservation']},'RECEIPT_PARENTS')
            verify_qualification_receipt(receipt,content_hash(receipt),parents=receipt['parents'])
            receipts.append(content_hash(receipt));phase_receipts.append(content_hash(receipt))
            require(receipt['result']=='OBSERVED' and receipt['bulk_checks']['freshness']=='WITHIN_AGE_BOUND','OBSERVATION_FAILED')
            starts.append(receipt['dispatch_time'])
            # Completion identity is derived from the trusted executor result and
            # exact day reservation, not from an untrusted self-labeled disk file.
            reservation={'plan':request['account']['bulk_plan_parent'],'slot':i,
                         'source_commit':request['manifest']['source_commit'],'previous':previous}
            completion={'slot':i,'previous':previous,'reservation':content_hash(reservation),
                        'receipt':content_hash(receipt),'result':receipt['result']}
            previous=content_hash(completion)
        except Exception:
            reason='AMBIGUOUS_OR_FAILED_STOP';break
        if i==0 or i in (6,12,18):
            stage(row['phase'].lower(),'PASS',phase_receipts);phase_receipts=[]
    evidence.update(package['external_stages']);pins.update(package['external_pins'])
    try:
        result=final_session_receipt(evidence,pins,scope=scope)
    except ValueError:
        result=final_session_receipt({}, {},scope=scope)
        reason='EXTERNAL_STAGE_EVIDENCE_INVALID'
    result.update(request_receipt_parents=receipts,stop_reason=reason,package_parent=expected)
    if reason:result['status']='RED'
    if live:
        import os
        fd=safe_root(plan['root'])
        try:publish(fd,'FINAL-SESSION.json',result)
        finally:os.close(fd)
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',required=True)
    parser.add_argument('--expected-hash',required=True)
    parser.add_argument('--run',action='store_true',help='Explicitly enable the separately authorized live package')
    args=parser.parse_args()
    path=Path(args.package)
    require(path.is_absolute() and path.resolve()==path and not path.is_symlink(),'PACKAGE_PATH')
    package=json.loads(path.read_text())
    require(not args.run or package.get('scope')=='LIVE_QUALIFICATION','CLI_LIVE_ONLY')
    stopped=[False]
    if args.run:
        import signal
        def shutdown(signum,frame):
            stopped[0]=True
        signal.signal(signal.SIGTERM,shutdown)
        signal.signal(signal.SIGINT,shutdown)
    result=run(package,args.expected_hash,enabled=args.run,stop=lambda:stopped[0])
    # No payload, credential, provider text or exception is emitted.
    print(json.dumps({'status':result['status'],**dict.fromkeys(FLAGS,False)}))


if __name__=='__main__':
    main()


def disabled_installation_rehearsal(spec, expected):
    """Publish only a disabled launch descriptor in a new, pinned rehearsal root.

    No launchctl, service registration, scheduling, process start or activation.
    The caller must independently authorize this exact artifact destination.
    """
    import hashlib
    import os
    import plistlib
    import stat
    safe_document(spec);pin(spec,expected)
    require(set(spec)=={'root','interpreter','entrypoint','package','package_hash'},'REHEARSAL_SCHEMA')
    paths={}
    for kind in ('interpreter','entrypoint','package'):
        row=spec[kind];path=Path(row['path']);st=path.lstat()
        require(path.is_absolute() and path.resolve()==path and stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.getuid(),'REHEARSAL_INPUT_IDENTITY')
        require(hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],'REHEARSAL_INPUT_HASH')
        paths[kind]=path
    package=json.loads(paths['package'].read_text());validate_package(package,spec['package_hash'])
    root=Path(spec['root']);require(root.is_absolute() and root.resolve()==root and not root.exists(),'NEW_REHEARSAL_ROOT_REQUIRED')
    root.mkdir(mode=0o700)
    descriptor={'Label':'com.iios.alpha.session.20260914','Disabled':True,'RunAtLoad':False,'KeepAlive':False,
                'ProgramArguments':[str(paths['interpreter']),'-B',str(paths['entrypoint']),
                                    '--package',str(paths['package']),'--expected-hash',spec['package_hash']]}
    body=plistlib.dumps(descriptor)
    with (root/'disabled.plist').open('xb') as file:file.write(body)
    require(plistlib.loads(body)==descriptor and '--run' not in descriptor['ProgramArguments'],'DISABLED_DESCRIPTOR')
    return {'status':'DISABLED_REHEARSAL_ONLY','plist_sha256':hashlib.sha256(body).hexdigest(),
            'package_parent':spec['package_hash'],'spec_parent':expected,'registered':False,'armed':False,
            **dict.fromkeys(FLAGS,False)}
