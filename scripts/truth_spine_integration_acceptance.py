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


def validate_packaged_frontend(dist, provenance):
    """Dispatch only to the graph named by independently verified provenance.

    Northstar and the engineering preview intentionally have different asset
    contracts.  Selecting a validator from the observed file count would let a
    stale or cross-graph distribution pass, so the entrypoint is the sole
    selector and must be one of the two reviewed values.
    """
    from truth_spine_frontend_provenance import validate_outputs

    try:
        entry = provenance["inputs"]["policy"]["entry"]
    except (KeyError, TypeError):
        raise ValueError("FRONTEND_ENTRYPOINT_INVALID") from None
    if entry == "northstar-session.html":
        return validate_outputs(dist, provenance["outputs"], northstar=True)
    if entry == "truth-integration.html":
        return validate_outputs(dist, provenance["outputs"], northstar=False)
    raise ValueError("FRONTEND_ENTRYPOINT_INVALID")


def prepare(a):
    """Future operational entrypoint. No root exists until every independent pin passes."""
    import sys
    from truth_spine_frontend_provenance import verify, compare_builds
    src = a.source.resolve()
    sys.path.insert(0, str(src/'BACK END/backend'))
    from truth_spine_contract import canonical, digest, seal
    from truth_spine_lineage import (load_spec, admit, historical_generation, write_new,
                                    copy_pinned, file_hash, require)
    from truth_spine_runtime_provenance import validate_inputs, assemble
    from truth_spine_noninterference import load_baseline, observe
    from truth_spine_adapters import source
    from truth_spine_authority import disabled_document
    # Reject a supplied but substituted frontend receipt independently, before
    # inspecting its claims. Missing new CLI pins remain explicit input errors.
    frontend_pin=getattr(a,'frontend_manifest_hash',None)
    if frontend_pin is not None:
        require(file_hash(a.frontend_build/'frontend-provenance.json')==frontend_pin,
                'FRONTEND_MANIFEST_PIN_MISMATCH')
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()
    require(commit == getattr(a,'expected_commit',None), 'ACCEPTED_IMPLEMENTATION_COMMIT_REQUIRED')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=src,text=True), 'CLEAN_COMMITTED_SOURCE_REQUIRED')
    spec = load_spec(a.input_spec,a.input_spec_sha256,commit)
    require(str(a.root.absolute()) == spec['run_root'] and a.port == spec['port'], 'AUTHORIZED_ROOT_PORT_MISMATCH')
    baseline = spec['baseline']
    baseline_spec=load_baseline(Path(baseline['path']),baseline['sha256'])
    validate_inputs(spec['runtime'])
    first = verify(a.frontend_build,src,commit)
    second = verify(a.frontend_build_b,src,commit)
    require(first['inputs']['policy']['entry'] == 'northstar-session.html', 'NORTHSTAR_REQUIRED')
    compare_builds(first,second)
    require(first['input_hash']==a.frontend_input_hash and
            file_hash(a.frontend_build/'frontend-provenance.json')==a.frontend_manifest_hash,
            'FRONTEND_INDEPENDENT_PIN_MISMATCH')
    # Check the complete executor references before admission mutates anything.
    auxiliary = {r['target']:r['pin'] for r in spec['auxiliary']}
    selector = json.loads(Path(auxiliary['executor/selected-session.json']['path']).read_bytes())
    selected = 'executor/'+selector['selected_root']+'/executor-state.json'
    plan_name = 'executor/'+selector['selected_root']+'/request-plan.json'
    require(selected in auxiliary and plan_name in auxiliary, 'EXECUTOR_REFERENCES_NOT_PINNED')
    state = json.loads(Path(auxiliary[selected]['path']).read_bytes())
    require(state['phase']=='SESSION_CLOSED' and state['released_credits']==0 and
            all(v is False for v in state['authority'].values()), 'CLOSED_DENY_ONLY_INPUT_REQUIRED')
    intent = digest({'schema':'iios-package-generation-intent-v1','source_commit':commit,
                     'input_spec_sha256':a.input_spec_sha256,'frontend_input_hash':first['input_hash'],
                     'frontend_output_hash':first['output_hash']})
    from truth_spine_integration_runner import protected_processes, protected_listeners
    before=observe(baseline_spec,process_inventory=protected_processes,listener_inventory=protected_listeners)
    # Availability is checked only after all pin verification; no service starts here.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',a.port))
    root = a.root.absolute()
    from truth_spine_adapters import SQLitePolicy, activate_strict_sqlite, connect_strict_sqlite, create_run_event_store
    policy=SQLitePolicy(str(root),a.input_spec_sha256,intent,'preparation',os.getpid())
    activate_strict_sqlite(policy)
    admission = admit(spec,root,a.input_spec_sha256)
    require(write_new(root,'admission/input-spec.json',a.input_spec.read_bytes())==a.input_spec_sha256,'INPUT_SPEC_COPY_MISMATCH')
    require(write_new(root,'admission/baseline-spec.json',Path(baseline['path']).read_bytes())==baseline['sha256'],'BASELINE_SPEC_COPY_MISMATCH')
    write_new(root,'baselines/before-preparation.json',canonical(before))
    work = root/'working-inputs'
    snapshots = [source(work/'owner/l7/snapshot.db','operational'),source(work/'owner/l8/snapshot.db','historical')]
    kinds = {'research.json':'research','event_reconstruction.json':'event_reconstruction',
             'macro_regime.json':'macro_regime','validation_9h.json':'validation_9h',
             'shadow_9i.json':'shadow_9i','outcomes_9j.json':'outcomes_9j'}
    for name,kind in kinds.items(): snapshots.append(source(work/name,kind))
    for name in sorted(auxiliary):
        if name.startswith('executor/') and (name.endswith('/executor-state.json') or
                name.endswith('/request-plan.json') or '/receipts/' in name):
            snapshots.append(source(work/name,'executor'))
    # Historical universe extraction only opens an admitted working copy.
    from truth_spine_lineage import working_capability
    from truth_spine_adapters import verify_strict_connection
    admission_hash=file_hash(root/'admission/working-copies.json')
    cap=working_capability(admission,admission_hash,'L8_WORKING_COPY')
    db=verify_strict_connection(connect_strict_sqlite(cap),cap)
    try:
        old = next((raw.encode() for raw, in db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_type='production_index_universe_snapshot' ORDER BY created_at DESC")
            if len(json.loads(raw).get('symbols',[]))==518),None)
    finally:
        db.close()
    require(old is not None,'RETAINED_518_CAPTURE_MISSING')
    write_new(root,'working-inputs/universe-historical.json',old)
    snapshots += [source(work/'universe-historical.json','universe'),source(work/'universe-current.json','universe')]
    generation,events = historical_generation(snapshots,admission,intent,admission_hash=admission_hash)
    # The same pure publisher path is used here and by the future isolated service.
    from truth_spine_integration_service import publish_historical_cycle
    cycle = publish_historical_cycle(generation,admission,intent,commit,datetime.now(timezone.utc).isoformat())
    lineage = {'package_generation':intent}
    for name,rel,value in [('admission','admission/working-copies.json',None),
                           ('generation','receipts/generation.json',generation),
                           ('events','receipts/events.json',events),
                           ('initial_cycle','receipts/initial-cycle.json',cycle),
                           ('input_spec','admission/input-spec.json',None)]:
        if value is not None: write_new(root,rel,canonical(value))
        lineage[name]={'path':rel,'sha256':file_hash(root/rel)}
    runtime = assemble(root,spec['runtime'],commit,intent)
    package=root/'release';package.mkdir(mode=0o700);backend=package/'backend';backend.mkdir(mode=0o700)
    for p in sorted((src/'BACK END/backend').rglob('*.py')):
        if p.name.startswith('test') or '__pycache__' in p.parts: continue
        rel=p.relative_to(src/'BACK END/backend')
        target=backend/rel;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        copy_pinned({'path':str(p),'sha256':file_hash(p),'bytes':p.stat().st_size,'mode':p.stat().st_mode&0o777},root,'release/backend/'+str(rel))
    p=src/'scripts/truth_spine_runtime_provenance.py'
    copy_pinned({'path':str(p),'sha256':file_hash(p),'bytes':p.stat().st_size,'mode':p.stat().st_mode&0o777},root,'release/backend/'+p.name)
    p=src/'scripts/truth_spine_northstar_browser.py'
    (package/'proof-sources').mkdir(mode=0o700)
    copy_pinned({'path':str(p),'sha256':file_hash(p),'bytes':p.stat().st_size,'mode':p.stat().st_mode&0o777},root,'release/proof-sources/'+p.name)
    for name in ('package-contract.mjs','package-run.mjs','package.acceptance.mjs','package.playwright.config.mjs'):
        p=src/'tests/northstar'/name
        copy_pinned({'path':str(p),'sha256':file_hash(p),'bytes':p.stat().st_size,'mode':p.stat().st_mode&0o777},root,'release/proof-sources/'+name)
    front=package/'frontend';front.mkdir(mode=0o700)
    for row in first['outputs']:
        p=a.frontend_build/'frontend/dist'/row['path'];(front/row['path']).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        copy_pinned({'path':str(p),'sha256':row['sha256'],'bytes':row['bytes'],'mode':p.stat().st_mode&0o777},front,row['path'])
    validate_packaged_frontend(front,first)
    files=[{'path':str(p.relative_to(package)),'bytes':p.stat().st_size,'sha256':file_hash(p)} for p in sorted(package.rglob('*')) if p.is_file()]
    runtime_files=[{'path':str(p.relative_to(root/'runtime')),'bytes':p.stat().st_size,'sha256':file_hash(p)} for p in sorted((root/'runtime').rglob('*')) if p.is_file()]
    release='truth-integration-'+digest({'files':files,'lineage':lineage,'runtime':runtime['content_hash']})[:24]
    manifest=seal({'schema':'iios-historical-package-v2','release_id':release,'source_base':commit,
        'source_state':'CLEAN_COMMITTED_SOURCE','source_inventory_hash':digest({'files':[r for r in files if r['path'].startswith('backend/')]}),
        'frontend_provenance':first,'frontend_input_hash':first['input_hash'],'frontend_content_hash':first['output_hash'],
        'files':files,'interpreter_hash':runtime['interpreter_sha256'],'dependency_hash':file_hash(root/'runtime/runtime-manifest.json'),
        'runtime_root':str(root/'runtime'),'runtime_files':runtime_files,'lineage':lineage})
    write_new(root,'release/manifest.json',canonical(manifest))
    event_cap=create_run_event_store(policy,file_hash(root/'release/manifest.json'))
    ids={'release':release,'runtime':runtime['runtime_id'],'interpreter':manifest['interpreter_hash'],
         'dependencies':manifest['dependency_hash'],'operational_ledger':snapshots[0]['store_id'],
         'historical_ledger':snapshots[1]['store_id'],'event_ledger':release+'-canonical-events',
         'executor_generation':Path(selected).parent.name,'source_cycle':cycle['source_cycle_id'],
         'evidence_receipt':admission['files']['completion-receipt.json']['source_sha256'],
         'case_namespace':'SOURCE_STORE_AND_OBJECT','projection_generation':release+'-projection',
         'publisher':next(r['sha256'] for r in files if r['path']=='backend/truth_spine_integration_service.py'),
         'frontend':digest({'files':[r for r in files if r['path'].startswith('frontend/')]}),
         'scheduler_owner':release+'-scheduler','publisher_owner':release+'-publisher','rollback_parent':digest({'sources':snapshots})}
    now=datetime.now(timezone.utc)
    authority=disabled_document(digest(ids),release,ids['scheduler_owner'],ids['publisher_owner'],now.isoformat(),(now+timedelta(seconds=spec['duration_seconds']+300)).isoformat())
    write_new(root,'authority.json',canonical(authority))
    t=seal({'schema':'iios-historical-topology-v3','mode':'ISOLATED_SHADOW','root':str(root),'identities':ids,
        'sources':snapshots,'authority_path':str(root/'authority.json'),'authority_hash':file_hash(root/'authority.json'),
        'release_manifest':str(package/'manifest.json'),'release_manifest_hash':file_hash(package/'manifest.json'),
        'event_ledger_path':event_cap.path,'event_receipt_path':event_cap.receipt_path,'event_receipt_hash':event_cap.receipt_hash,
        'selected_state':str(work/selected),'selected_state_hash':file_hash(work/selected),
        'selector_path':str(work/'executor/selected-session.json'),'selector_hash':file_hash(work/'executor/selected-session.json'),
        'source_cycle_path':str(root/'receipts/initial-cycle.json'),'source_cycle_hash':file_hash(root/'receipts/initial-cycle.json'),'phase':'SESSION_CLOSED'})
    write_new(root,'topology.json',canonical(t))
    source_files={str(src/'BACK END'/r['path']):r['sha256'] for r in files if r['path'].startswith('backend/') and r['path']!='backend/truth_spine_runtime_provenance.py'}
    source_files.update({str(src/'FRONT END'/r['path']):r['sha256'] for r in first['inputs']['source_inventory']})
    for name in ('package-contract.mjs','package-run.mjs','package.acceptance.mjs','package.playwright.config.mjs'):
        source_files[str(src/'tests/northstar'/name)]=file_hash(src/'tests/northstar'/name)
    for name in ('truth_spine_runtime_provenance.py','truth_spine_integration_acceptance.py','truth_spine_integration_runner.py',
                 'truth_spine_noninterference.py','truth_spine_northstar_browser.py'):
        source_files[str(src/'scripts'/name)]=file_hash(src/'scripts'/name)
    write_new(root,'preservation.json',canonical(seal({'input_hashes':{str(p.relative_to(root)):file_hash(p) for p in work.rglob('*') if p.is_file()},
        'source_files':source_files,'owner_scope':admission['scope']})))
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=src,text=True),'SOURCE_CHANGED_DURING_PREPARATION')
    after=observe(baseline_spec,process_inventory=protected_processes,listener_inventory=protected_listeners)
    require(before==after,'PREPARATION_NONINTERFERENCE_FAILED')
    write_new(root,'baselines/after-preparation.json',canonical(after))
    return t


def request(port,path,method='GET'):
    try:
        with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}'+path,method=method),timeout=60) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())


def main():
    p=argparse.ArgumentParser()
    for key in ('root','source','input-spec','frontend-build','frontend-build-b'):
        p.add_argument('--'+key,type=Path,required=True)
    for key in ('expected-commit','input-spec-sha256','frontend-input-hash','frontend-manifest-hash'):
        p.add_argument('--'+key,required=True)
    p.add_argument('--port',type=int,required=True)
    a=p.parse_args();t=prepare(a)
    print(json.dumps({'root':str(a.root),'release':t['identities']['release'],'topology':t['content_hash']}))


if __name__=='__main__':main()
