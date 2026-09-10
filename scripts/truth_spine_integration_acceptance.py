"""Isolated SB3 preparation/acceptance. Never installs or signals permanent jobs.

Source adapters, ingestion, publisher and health run from the packaged modules.
This runner only copies read-only inputs, constructs bindings and observes output.
"""
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
from datetime import datetime, timedelta, timezone
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(a):
    root=a.root.resolve()
    if root.exists():raise ValueError('NEW_ACCEPTANCE_ROOT_REQUIRED')
    # Validate source and proven frontend before binding a socket or creating
    # any shadow output. There is deliberately no fallback to source/dist.
    from truth_spine_frontend_provenance import verify, validate_outputs
    src=a.source.resolve()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=src,text=True):
        raise ValueError('CLEAN_COMMITTED_SOURCE_REQUIRED')
    frontend=verify(a.frontend_build,src,commit)
    if frontend['input_hash']!=a.frontend_input_hash:raise ValueError('FRONTEND_INPUT_PIN_MISMATCH')
    if sha(a.frontend_build/'frontend-provenance.json')!=a.frontend_manifest_hash:
        raise ValueError('FRONTEND_MANIFEST_PIN_MISMATCH')
    if a.port in {5176,5177,5184,5185,5186,8002}:raise ValueError('PROTECTED_PORT')
    with socket.socket() as s:s.bind(('127.0.0.1',a.port))
    root.mkdir(mode=0o700);inputs=root/'inputs';inputs.mkdir(mode=0o700)
    package=root/'release';package.mkdir(mode=0o700);backend=package/'backend';backend.mkdir(mode=0o700)
    source_hashes={}
    for p in (src/'BACK END/backend').rglob('*.py'):
        if p.name.startswith('test') or '__pycache__' in p.parts:continue
        if p.is_symlink():raise ValueError('SOURCE_SYMLINK')
        rel=p.relative_to(src/'BACK END/backend');target=backend/rel;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,target);target.chmod(0o400);source_hashes[str(p)]=sha(p)
    shutil.copytree(a.frontend_build/'frontend/dist',package/'frontend',symlinks=True)
    validate_outputs(package/'frontend',frontend['outputs'])
    sys_path=str(backend)
    import sys
    sys.path.insert(0,sys_path)
    from truth_spine_contract import canonical,digest,seal
    from truth_spine_adapters import source
    from truth_spine_authority import disabled_document
    from truth_spine_integration import atomic,derived_bindings
    def write(p,x):atomic(p,x)
    snapshots=[]
    for kind,p in [('operational',a.operational),('historical',a.historical)]:
        dest=inputs/(kind+'.db');db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);copy=sqlite3.connect(dest)
        try:db.backup(copy)
        finally:db.close();copy.close()
        dest.chmod(0o400);snapshots.append(source(dest,kind))
    executor=inputs/'executor';shutil.copytree(a.executor,executor,symlinks=False)
    # The retained closed tree is copied, not rewritten. Validate every copied file.
    original_inventory={str(p.relative_to(a.executor)):sha(p) for p in a.executor.rglob('*') if p.is_file()}
    for rel,h in original_inventory.items():
        if (a.executor/rel).is_symlink() or sha(executor/rel)!=h:raise ValueError('EXECUTOR_COPY_MISMATCH')
    selector=executor/'selected-session.json';sel=json.loads(selector.read_bytes());selected=executor/sel['selected_root']/'executor-state.json'
    if not selected.resolve().is_relative_to(executor):raise ValueError('SELECTOR_PATH_INVALID')
    state=json.loads(selected.read_bytes())
    if state['phase']!='SESSION_CLOSED' or state['released_credits']!=0:raise ValueError('CLOSED_ZERO_ALLOWANCE_REQUIRED')
    for session in ['2026-09-08','2026-09-09-canonical-v3','2026-09-09-intraday-recovery']:
        p=executor/'sessions'/session
        for name in ['executor-state.json','executor-state.last-known-valid.json','request-plan.json']:
            snapshots.append(source(p/name,'executor'))
        for receipt in sorted((p/'receipts').glob('*.json')):snapshots.append(source(receipt,'executor'))
    snapshots.append(source(executor/'sessions/2026-09-08/archive-manifest.json','archive'))
    # Locate exact retained historical member list in the copied historical ledger.
    db=sqlite3.connect((inputs/'historical.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        old=None
        for raw, in db.execute("SELECT payload_json FROM ledger_objects WHERE object_type='production_index_universe_snapshot' ORDER BY created_at DESC"):
            if len(json.loads(raw).get('symbols',[]))==518:old=raw.encode();break
    finally:db.close()
    if old is None:raise ValueError('RETAINED_518_CAPTURE_MISSING')
    old_path=inputs/'universe-historical.json';old_path.write_bytes(old);old_path.chmod(0o400)
    snapshots.append(source(old_path,'universe'))
    u=inputs/'universe-current.json';shutil.copyfile(a.universe,u);u.chmod(0o400);snapshots.append(source(u,'universe'))
    for kind,p in [('research',a.stores/'historical-research/latest_historical_market_intelligence.json'),
                   ('event_reconstruction',a.stores/'historical-event-reconstruction/latest_historical_event_reconstruction.json'),
                   ('macro_regime',a.stores/'historical-macro-regime/latest_historical_macro_regime_library.json'),
                   ('validation_9h',a.stores/'market-validation/latest_market_validation.json'),
                   ('shadow_9i',a.stores/'market-validation/browser/shadow_strategy.json'),
                   ('outcomes_9j',a.stores/'market-validation/latest_outcome_learning.json')]:
        dest=inputs/(kind+'.json');shutil.copyfile(p,dest);dest.chmod(0o400);snapshots.append(source(dest,kind))
    cycle=inputs/'source-cycle.json';shutil.copyfile(a.stores/'ExpansionWingProjection/projection-manifest.json',cycle);cycle.chmod(0o400)
    source_cycle=json.loads(cycle.read_bytes())['source_cycle_id']
    runtime=root/'runtime';shutil.copytree(a.runtime,runtime,symlinks=False)
    interpreter=runtime/'bin/python';dependency_hash=sha(runtime/'runtime-manifest.json')
    runtime_files=[{'path':str(p.relative_to(runtime)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(runtime.rglob('*')) if p.is_file()]
    files=[{'path':str(p.relative_to(package)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(package.rglob('*')) if p.is_file()]
    release='truth-integration-'+digest({'files':files})[:16]
    manifest=seal({'schema':'iios-readonly-package-v1','release_id':release,'source_base':commit,
                   'source_state':'CLEAN_COMMITTED_SOURCE','source_inventory_hash':digest({'files':[r for r in files if r['path'].startswith('backend/')]}),
                   'frontend_provenance':frontend,'frontend_input_hash':frontend['input_hash'],'frontend_content_hash':frontend['output_hash'],
                   'files':files,'interpreter_hash':sha(interpreter),'dependency_hash':dependency_hash,
                   'runtime_root':str(runtime),'runtime_files':runtime_files})
    write(package/'manifest.json',manifest)
    receipt_copy=inputs/'accepted-receipt.json';shutil.copyfile(a.receipt,receipt_copy);receipt_copy.chmod(0o400)
    ids={'release':release,'runtime':release+'-python','interpreter':sha(interpreter),'dependencies':dependency_hash,
         'operational_ledger':snapshots[0]['store_id'],'historical_ledger':snapshots[1]['store_id'],
         'event_ledger':release+'-canonical-events','executor_generation':selected.parent.name,
         'source_cycle':source_cycle,'evidence_receipt':sha(a.receipt),'case_namespace':'SOURCE_STORE_AND_OBJECT',
         'projection_generation':release+'-projection','publisher':'readonly-publisher-v1','frontend':digest({'files':[r for r in files if r['path'].startswith('frontend/')]}),
         'scheduler_owner':release+'-scheduler','publisher_owner':release+'-publisher','rollback_parent':digest({'sources':snapshots})}
    ids.update(derived_bindings(root,manifest,snapshots))
    now=datetime.now(timezone.utc);authority=disabled_document(digest(ids),release,ids['scheduler_owner'],ids['publisher_owner'],now.isoformat(),(now+timedelta(hours=4)).isoformat())
    write(root/'authority.json',authority)
    t=seal({'schema':'iios-readonly-topology-v2','mode':'ISOLATED_SHADOW','root':str(root),'identities':ids,
            'sources':snapshots,'authority_path':str(root/'authority.json'),'authority_hash':sha(root/'authority.json'),
            'release_manifest':str(package/'manifest.json'),'release_manifest_hash':sha(package/'manifest.json'),
            'event_ledger_path':str(root/'canonical-events.db'),'selected_state':str(selected),'selected_state_hash':sha(selected),
            'selector_path':str(selector),'selector_hash':sha(selector),'source_cycle_path':str(cycle),'source_cycle_hash':sha(cycle),'phase':state['phase']})
    write(root/'topology.json',t)
    write(root/'preservation.json',seal({'source_files':source_hashes,'executor_inventory':original_inventory,'input_hashes':{str(p.relative_to(root)):sha(p) for p in inputs.rglob('*') if p.is_file()}}))
    for p in package.rglob('*'):
        if p.is_file():p.chmod(0o400)
    return t


def request(port,path,method='GET'):
    try:
        with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}'+path,method=method),timeout=60) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    for key in ['operational','historical','executor','universe','stores','runtime','receipt']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--frontend-build',type=Path,required=True)
    p.add_argument('--frontend-input-hash',required=True)
    p.add_argument('--frontend-manifest-hash',required=True)
    p.add_argument('--port',type=int,required=True);p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
    t=prepare(a);print(json.dumps({'root':str(a.root),'release':t['identities']['release'],'topology':t['content_hash'],'port':a.port}),flush=True)


if __name__=='__main__':main()
