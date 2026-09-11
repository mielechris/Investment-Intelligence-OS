"""Owner-only, fixed-root historical package; no process or network startup.

All inputs are explicit and independently pinned before creation. This command
cannot create a market-day session, a LaunchAgent, or operational authorization.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'BACK END/backend'))
from truth_spine_contract import canonical, digest, seal, verified
from truth_spine_generations import registry_record
from truth_spine_session import HistoricalSession, session_authority
from truth_spine_session_package import BACKEND_FILES, deployment_documents, verify_artifacts
from truth_spine_frontend_provenance import verify, compare_builds

ROOT_NAME = 'iios-northstar-installed-shadow-sb37'
BUILD_NAMES = ('iios-northstar-sb37-build-a', 'iios-northstar-sb37-build-b')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('PACKAGE_SYMLINK')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('PACKAGE_INPUT_TYPE_OR_OWNER')
    return path.read_bytes()


def prospective(source, commit, builds, runtime, runtime_pin, registry):
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source).decode().strip() != commit:
        raise ValueError('SOURCE_COMMIT_MISMATCH')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=source):
        raise ValueError('CLEAN_SOURCE_REQUIRED')
    if tuple(p.name for p in builds) != BUILD_NAMES or any(p.parent != Path('/private/tmp') for p in builds):
        raise ValueError('EXACT_BUILD_ROOTS_REQUIRED')
    a, b = [verify(p, source, commit) for p in builds]; compare_builds(a, b)
    if a['inputs']['policy']['entry'] != 'northstar-session.html':
        raise ValueError('NORTHSTAR_REQUIRED')
    if registry != registry_record(registry['sources']): raise ValueError('SOURCE_REGISTRY_INVALID')
    r = verified(json.loads(regular(runtime/'runtime-manifest.json')))
    if sha(runtime/'runtime-manifest.json') != runtime_pin: raise ValueError('RUNTIME_PIN_MISMATCH')
    expected = {row['path'] for row in r['file_inventory']} | {'runtime-manifest.json'}
    actual = {p.relative_to(runtime).as_posix() for p in runtime.rglob('*') if not p.is_dir()}
    if actual != expected: raise ValueError('RUNTIME_EXTRA_OR_MISSING')
    for row in r['file_inventory']:
        p = runtime/row['path']; data = regular(p)
        if len(data) != row['size'] or sha(p) != row['sha256'] or stat.S_IMODE(p.stat().st_mode) != row['mode']:
            raise ValueError('RUNTIME_ARTIFACT_INVALID')
    lock = dict(line.strip().split('==') for line in (source/'config/production-python-requirements.lock').read_text().splitlines() if line.strip())
    normalize = lambda name: name.lower().replace('_', '-')
    installed = {normalize(d['name']): d['version'] for d in r['dependency_inventory'] if d['name'] != 'pip'}
    if installed != {normalize(k):v for k,v in lock.items()}: raise ValueError('DEPENDENCY_LOCK_MISMATCH')
    files = {}
    for name in BACKEND_FILES:
        p = source/('scripts' if name.endswith('_runner.py') else 'BACK END/backend')/name
        files['release/backend/'+name] = (regular(p), 0o400)
    for row in a['outputs']:
        files['release/frontend/'+row['path']] = (regular(builds[0]/'frontend/dist'/row['path']), 0o400)
    # Do not distribute checkout-bound activation/install scripts or pip. The
    # dependency lock, metadata and all retained package bytes remain pinned.
    runtime_rows = []
    for row in r['file_inventory']:
        name = row['path']; p = Path(name)
        if name != 'bin/python' and not name.startswith('lib/'): continue
        if any(part == 'pip' or part.startswith('pip-') for part in p.parts): continue
        if '__pycache__' in p.parts or p.suffix == '.pyc': raise ValueError('RUNTIME_CACHE')
        data = regular(runtime/name)
        if re.search(rb'/Users/[^/\s]+/', data): raise ValueError('RUNTIME_PRIVATE_PATH')
        mode = 0o500 if name == 'bin/python' else 0o400
        files['runtime/'+name] = (data, mode)
        runtime_rows.append({'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode})
    # CPython's system framework is independently manifest-pinned, not a
    # developer checkout. No activation script, environment or secret is used.
    cfg = b'home = /Library/Frameworks/Python.framework/Versions/3.14/bin\ninclude-system-site-packages = false\nversion = 3.14.7\n'
    files['runtime/pyvenv.cfg'] = (cfg, 0o400)
    runtime_rows.append({'path':'pyvenv.cfg','size':len(cfg),'sha256':hashlib.sha256(cfg).hexdigest(),'mode':0o400})
    runtime_identity = 'historical-python-'+digest({'files': sorted(runtime_rows,key=lambda x:x['path'])})[:16]
    runtime_record = seal({**r, 'runtime_id': runtime_identity, 'runtime_root': str(Path('/private/tmp')/ROOT_NAME/'runtime'),
        'interpreter':str(Path('/private/tmp')/ROOT_NAME/'runtime/bin/python'),
        'release_commit': commit, 'parent_manifest_hash': runtime_pin, 'file_inventory': sorted(runtime_rows,key=lambda x:x['path']),
        'dependency_inventory': [d for d in r['dependency_inventory'] if d['name'] != 'pip']})
    files['runtime/runtime-manifest.json'] = (canonical(runtime_record), 0o400)
    inventory = [{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'mode':f'{mode:04o}'}
                 for name,(data,mode) in sorted(files.items())]
    inputs = [{'store':s['store'],'kind':s['kind'],'sha256':sha(Path(s['path'])),'bytes':Path(s['path']).stat().st_size}
              for s in registry['sources']]
    identity = digest({'source':commit,'files':inventory,'inputs':inputs,'lock':sha(source/'config/production-python-requirements.lock')})
    return files, {'schema':'iios-historical-package-candidate-v1','identity':identity,
        'release':'northstar-historical-'+identity[:16],'source_commit':commit,'files':inventory,'inputs':inputs,
        'runtime_identity':runtime_identity,'frontend_provenance':a,'registry_hash':digest(registry),
        'dependency_lock_sha256':sha(source/'config/production-python-requirements.lock'),
        'rollback_identity':digest({'inputs':inputs,'parent_runtime':runtime_pin})}


def validate_payload(candidate, files):
    expected = {r['path']:r for r in candidate['files']}
    if len(expected) != len(candidate['files']) or set(expected) != set(files):
        raise ValueError('CANDIDATE_INVENTORY_MISMATCH')
    for name,(data,mode) in files.items():
        p=Path(name)
        if (p.is_absolute() or '..' in p.parts or p.as_posix()!=name or not p.parts
                or p.parts[0] not in {'release','runtime'} or mode not in {0o400,0o500}
                or any(x in p.parts for x in ('__pycache__','node_modules','.git')) or p.suffix in {'.pyc','.map'}):
            raise ValueError('CANDIDATE_PATH_OR_MODE_INVALID')
        if expected[name] != {'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'mode':f'{mode:04o}'}:
            raise ValueError('CANDIDATE_BYTES_MISMATCH')
    if {n for n in files if n.startswith('release/backend/')} != {'release/backend/'+n for n in BACKEND_FILES}:
        raise ValueError('CANDIDATE_BACKEND_GRAPH_INVALID')
    identity=digest({'source':candidate['source_commit'],'files':candidate['files'],'inputs':candidate['inputs'],
                     'lock':candidate['dependency_lock_sha256']})
    if candidate['identity'] != identity or candidate['release'] != 'northstar-historical-'+identity[:16]:
        raise ValueError('CANDIDATE_IDENTITY_MISMATCH')


def install(root, candidate, files, registry, *, duration):
    HistoricalSession(datetime.now(timezone.utc),duration)
    validate_payload(candidate,files)
    if root != root.resolve() or root.parent != Path('/private/tmp') or root.name != ROOT_NAME or root.exists():
        raise ValueError('NEW_EXACT_HISTORICAL_ROOT_REQUIRED')
    if registry != registry_record(registry['sources']) or digest(registry) != candidate['registry_hash']:
        raise ValueError('REGISTRY_CHANGED')
    actual = [{'store':s['store'],'kind':s['kind'],'sha256':sha(Path(s['path'])),'bytes':Path(s['path']).stat().st_size}
              for s in registry['sources']]
    if actual != candidate['inputs']: raise ValueError('SOURCE_CHANGED_BEFORE_CREATION')
    os.umask(0o077); root.mkdir(mode=0o700)
    def write(name, data, mode=0o400):
        p=root/name; p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
        with os.fdopen(fd,'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        fd=os.open(p.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    for name,(data,mode) in files.items(): write(name,data,mode)
    for name in ('logs','receipts','projections','rollback'): (root/name).mkdir(mode=0o700)
    # Authority is issued only after immutable file copying has completed.
    at=datetime.now(timezone.utc); session=HistoricalSession(at,duration)
    owners={role:candidate['release']+'-'+role for role in ('scheduler','publisher')}
    authority=session_authority(session,candidate['release'],owners,at)
    manifest=seal({'schema':'iios-full-day-shadow-package-v1','release':candidate['release'],
        'source_commit':candidate['source_commit'],'runtime_identity':candidate['runtime_identity'],
        'frontend_provenance':candidate['frontend_provenance'],'session':session.identity,
        'authority_hash':digest(authority),'source_registry_hash':digest(registry),'files':candidate['files']})
    documents=deployment_documents(root,session,manifest,registry,authority,owners)
    for name,value in documents.items():write(name,canonical(value),0o600)
    write('prospective-package.json',canonical(seal(candidate)))
    verify_artifacts(root,manifest,manifest['content_hash'])
    return {'release':candidate['release'],'session':session.identity,'manifest':manifest['content_hash'],
        'topology_sha256':sha(root/'topology.json'),'authority':digest(authority),'expires':authority['expires_at']}


def main():
    p=argparse.ArgumentParser()
    for name in ('source','build-a','build-b','runtime','registry'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--commit',required=True);p.add_argument('--runtime-sha256',required=True)
    p.add_argument('--candidate-sha256');p.add_argument('--install',action='store_true')
    p.add_argument('--duration',type=int,default=600)
    a=p.parse_args(); registry=verified(json.loads(regular(a.registry)))
    files,candidate=prospective(a.source,a.commit,(a.build_a,a.build_b),a.runtime,a.runtime_sha256,registry)
    if not a.install: print(canonical(seal(candidate)).decode()); return
    if a.candidate_sha256 != digest(candidate): raise ValueError('INDEPENDENT_CANDIDATE_PIN_REQUIRED')
    print(json.dumps(install(Path('/private/tmp')/ROOT_NAME,candidate,files,registry,duration=a.duration)))


if __name__=='__main__': main()
