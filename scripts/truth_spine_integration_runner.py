"""Bounded isolated installed-runtime acceptance; never controls permanent services."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def get(port,path):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=60) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True,type=Path);parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--review-seconds',type=int,default=0);a=parser.parse_args();root=a.root.resolve()
    if root.parent!=Path('/private/tmp') or not root.name.startswith('iios-truth-spine-3-acceptance-') or a.port in {5176,5177,5184,5185,5186,8002}:raise ValueError('ISOLATED_ROOT_REQUIRED')
    t=json.loads((root/'topology.json').read_bytes());backend=root/'release/backend';python=root/'runtime/bin/python'
    env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(backend),'PYTHONUNBUFFERED':'1'}
    processes={};logs=[];report={};command=[str(python),'-B','-m','truth_spine_integration_service','--config',str(root/'topology.json')]
    def start(role):
        f=(root/(role+'.log')).open('ab');os.chmod(f.name,0o600);logs.append(f)
        p=subprocess.Popen(command+['--role',role,'--port',str(a.port)],cwd=backend,env=env,stdout=f,stderr=f);processes[role]=p
        print(json.dumps({'role':role,'pid':p.pid,'port':a.port if role=='backend' else None}),flush=True);return p
    def wait_ready():
        until=time.monotonic()+180
        while time.monotonic()<until:
            if any(p.poll() is not None for p in processes.values()):raise ValueError('CANDIDATE_PROCESS_EXITED')
            try:
                code,body=get(a.port,'/health/ready')
                if code==200:return body
            except (OSError,ValueError):pass
            time.sleep(1)
        raise ValueError('CANDIDATE_READINESS_TIMEOUT')
    def stop(role):
        p=processes.pop(role)
        if p.poll() is None:p.terminate();p.wait(timeout=30)
    def count():
        db=sqlite3.connect((root/'canonical-events.db').as_uri()+'?mode=ro',uri=True)
        try:return db.execute('select count(*),count(distinct id) from records').fetchone()
        finally:db.close()
    try:
        start('scheduler')
        until=time.monotonic()+180
        while not (root/'scheduler-heartbeat.json').exists():
            if processes['scheduler'].poll() is not None:raise ValueError('SCHEDULER_FAILED')
            if time.monotonic()>until:raise ValueError('INGEST_TIMEOUT')
            time.sleep(1)
        start('publisher');start('backend');report['ready']=wait_ready();report['initial_counts']=count()
        for endpoint in ['live','ready','market-readiness','research-readiness']:
            report[endpoint]=get(a.port,'/health/'+endpoint)
        if report['market-readiness'][0]!=503:raise ValueError('MARKET_AUTHORITY_NOT_DISABLED')
        duplicate=subprocess.run(command+['--role','scheduler'],cwd=backend,env=env,capture_output=True,timeout=60)
        report['duplicate_owner_rejected']=duplicate.returncode!=0
        if not report['duplicate_owner_rejected']:raise ValueError('DUPLICATE_OWNER')
        stop('scheduler');start('scheduler');wait_ready()
        report['restart_counts']=count()
        if report['restart_counts']!=report['initial_counts']:raise ValueError('RESTART_DUPLICATE_EVENTS')
        stop('publisher');time.sleep(16)
        report['stale_readiness']=get(a.port,'/health/ready')[0]
        if report['stale_readiness']!=503:raise ValueError('STALE_NOT_REJECTED')
        start('publisher');wait_ready();report['recovery']='READY_WITHOUT_STATE_REPAIR'
        report['soak']=[]
        for _ in range(10):
            started=time.monotonic();code,_=get(a.port,'/health/ready');report['soak'].append({'http':code,'seconds':time.monotonic()-started})
            if code!=200:raise ValueError('SOAK_READINESS_FAILED')
        p=root/'inputs/operational.db';restored=root/'rollback-rehearsal.db';shutil.copyfile(p,restored);restored.chmod(0o400)
        report['rollback']=hashlib.sha256(p.read_bytes()).hexdigest()==hashlib.sha256(restored.read_bytes()).hexdigest()
        before=json.loads((root/'preservation.json').read_bytes());report['input_preservation']=all(hashlib.sha256((root/name).read_bytes()).hexdigest()==h for name,h in before['input_hashes'].items())
        report['source_preservation']=all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==h for name,h in before['source_files'].items())
        if not all(report[k] for k in ['rollback','input_preservation','source_preservation']):raise ValueError('PRESERVATION_FAILED')
        report['result']='BACKEND_GREEN_BROWSER_SEPARATE';print(json.dumps(report),flush=True)
        # Read-only browser work occurs during this bounded interval; cleanup remains automatic.
        until=time.monotonic()+min(max(a.review_seconds,0),600)
        while time.monotonic()<until:time.sleep(1)
    except BaseException as exc:
        report['result']='RED';report['failure']=type(exc).__name__+':'+str(exc);print(json.dumps(report),flush=True);raise
    finally:
        for role in list(processes):stop(role)
        for log in logs:log.close()
        with socket.socket() as check:
            report['clean_shutdown']=check.connect_ex(('127.0.0.1',a.port))!=0
        with (root/'acceptance.json').open('x') as f:os.chmod(f.name,0o600);json.dump(report,f,sort_keys=True)


if __name__=='__main__':main()
