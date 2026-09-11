"""Read-only production-path observer service; no legacy app startup side effects."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from truth_spine_contract import canonical, seal
from truth_spine_integration import atomic, ingest, museum_adapter, read_json, snapshot, topology


def publish_historical_cycle(generation, admission, intent, commit, at, package_hash=None):
    """Shared isolated-publisher derivation; never reads a permanent projection."""
    from truth_spine_lineage import historical_cycle
    return historical_cycle(generation,admission,intent,commit,at,package_hash)


def historical_view(t, manifest, startup, at):
    from truth_spine_lineage import verify_chain, require
    from truth_spine_factory_coverage import factory_coverage
    from truth_spine_contract import digest
    docs=verify_chain(Path(t['root']),manifest)
    a,g=docs['admission'],docs['generation']
    cycle=publish_historical_cycle(g,a,manifest['lineage']['package_generation'],manifest['source_base'],at,t['release_manifest_hash'])
    factory=factory_coverage(g,docs['events'],cycle,'SESSION_CLOSED')
    require(startup and startup.get('content_hash'), 'BACKEND_INSTANCE_RECEIPT_REQUIRED')
    lineage={'schema':'iios-northstar-package-binding-v1','source_commit':manifest['source_base'],
        'package_hash':t['release_manifest_hash'],'package_generation':manifest['lineage']['package_generation'],
        'runtime_hash':manifest['dependency_hash'],'frontend_hash':manifest['frontend_content_hash'],
        'admission_hash':a['content_hash'],'generation_hash':g['content_hash'],
        'initial_cycle_hash':manifest['lineage']['initial_cycle']['sha256'],
        'owner_manifest_hash':a['files']['manifest.json']['source_sha256'],
        'completion_hash':a['files']['completion-receipt.json']['source_sha256'],
        'l7_hash':a['files']['l7/snapshot.db']['source_sha256'],'l8_hash':a['files']['l8/snapshot.db']['source_sha256'],
        'backend_instance_hash':startup['content_hash'],'common_watermark':a['common_watermark'],
        'classification':'HISTORICAL_REPLAY','source_cycle':cycle['source_cycle_id'],
        'projection_hash':factory['content_hash']}
    return {'schema':'iios-historical-northstar-browser-v2','session':g['session'],'phase':'SESSION_CLOSED',
        'scope':'HISTORICAL_REPLAY_NOT_CURRENT_MARKET','published_at':at,'capture_status':'CURRENT',
        'source_generation':g['content_hash'],'readiness':200,'source_cycle':cycle['source_cycle_id'],
        'source_cycle_generated_at':at,'watermark':g['watermark'],
        'owners':{'backend_owner':startup['content_hash'],'scheduler_owner':digest({'owner':t['identities']['scheduler_owner']}),
                  'publisher_owner':digest({'owner':t['identities']['publisher_owner']})},
        'universes':factory['universes'],
        'sources':[{'store':f['store'],'records':f['records'],'capture_end':f['capture_end'],
                    'classifications':f['classifications'],**{k:max(v) if v else None for k,v in f['clocks'].items()}} for f in g['files']],
        'factory':factory,'lineage':lineage,'capabilities':dict.fromkeys(topo_capabilities(),False),
        'counters':dict.fromkeys(('provider','model','credential','broker','paper','live_execution','operational_ledger_write'),0),
        'counter_scope':'DENY_ONLY_SHADOW','narrative_classification':'NARRATIVE',
        'incidents':['HISTORICAL_EVIDENCE_NOT_CURRENT_MARKET'],'source_session_closed_is_not_installed_disabled':True}


def topo_capabilities():
    from truth_spine_authority import CAPABILITIES
    return CAPABILITIES


def historical_response(path, request, backend_startup):
    """No healthy package result is served unless real publisher health passes."""
    from truth_spine_lineage import require
    t,_=topology(path)
    require(t['schema']=='iios-historical-topology-v3','PACKAGE_BACKED_TOPOLOGY_REQUIRED')
    code,body=health(path,'ready')
    if code!=200: return code,body
    root=Path(t['root']);manifest=read_json(Path(t['release_manifest']),t['release_manifest_hash'])
    # Serve the publisher's actual immutable publication; no request-time timestamp refresh.
    pointer=read_json(root/'state/historical-current.json')
    from truth_spine_lineage import contained, file_hash
    publication=contained(root,pointer['path'])
    require(publication.is_relative_to(root/'receipts'),'PUBLICATION_PATH_REQUIRED')
    require(file_hash(publication)==pointer['sha256'],'PUBLICATION_PIN_MISMATCH')
    view=json.loads(publication.read_bytes())
    from truth_spine_contract import utc
    require(0 <= (datetime.now(timezone.utc)-utc(view['published_at'])).total_seconds() <= 15,'HISTORICAL_PUBLICATION_STALE')
    require(view==historical_view(t,manifest,backend_startup,view['published_at']),'HISTORICAL_PUBLICATION_MISMATCH')
    return 200,view['lineage'] if request=='/truth-spine/lineage' else view


def publish_historical_view(t, backend_startup, at):
    from truth_spine_lineage import write_new
    root=Path(t['root']);manifest=read_json(Path(t['release_manifest']),t['release_manifest_hash'])
    view=historical_view(t,manifest,backend_startup,at)
    data=canonical(view);h=hashlib.sha256(data).hexdigest()
    relative='receipts/projection-'+h+'.json'
    write_new(root,relative,data)
    atomic(root/'state/historical-current.json',seal({'path':relative,'sha256':h}))
    return view


def deny_external_io() -> None:
    """Irreversible process-wide boundary in addition to function-level denial."""
    def audit(event, args):
        if event == 'socket.connect': raise PermissionError('OBSERVER_NETWORK_DISABLED')
        if event in {'subprocess.Popen', 'os.system', 'os.exec', 'ctypes.dlopen'}:
            raise PermissionError('OBSERVER_EXECUTION_DISABLED')
        if event == 'open' and isinstance(args[0],str):
            p=Path(args[0])
            if (p.name == '.env' or p.suffix.lower() in {'.keychain','.keychain-db'}
                    or any(part.lower() in {'keychains','credentials'} for part in p.parts)):
                raise PermissionError('OBSERVER_CREDENTIAL_DISABLED')
    sys.addaudithook(audit)


class Lease:
    def __init__(self, root: Path, role: str):
        self.path=root/(role+'.lock'); self.fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try: fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException: os.close(self.fd); raise
        os.ftruncate(self.fd,0);os.write(self.fd,str(os.getpid()).encode());os.fsync(self.fd)
    def close(self):
        fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd)


def heartbeat(t:dict,role:str,now:datetime,startup:dict | None=None):
    atomic(Path(t['root'])/(role+'-heartbeat.json'),seal({
        'schema':'iios-readonly-heartbeat-v1','role':role,'pid':os.getpid(),
        'owner':t['identities'][role+'_owner'],'topology_identity':t['content_hash'],
        'release':t['identities']['release'],'executor_generation':t['identities']['executor_generation'],
        'source_cycle':t['identities']['source_cycle'],'observed_at':now.isoformat(),
        **({'instance_id':startup['instance_id'],'startup_receipt_hash':startup['content_hash']} if startup else {})}))


def probe(t:dict,role:str,now:datetime | None=None):
    from truth_spine_contract import utc
    root=Path(t['root']); h=read_json(root/(role+'-heartbeat.json'))
    # Timestamp after the atomic read: a publisher may advance while package
    # verification is in progress. Never compare a new record to an older probe.
    now=now or datetime.now(timezone.utc)
    if 'instance_id' in h:
        from truth_spine_process_identity import read_receipt
        receipt=read_receipt(root,h['instance_id'])
        if (receipt is None or receipt['content_hash']!=h.get('startup_receipt_hash')
                or receipt['role']!=role or receipt['observation']['pid']!=h['pid']
                or receipt['topology_hash']!=hashlib.sha256((root/'topology.json').read_bytes()).hexdigest()
                or receipt['authority_hash']!=hashlib.sha256((root/'authority.json').read_bytes()).hexdigest()):
            raise ValueError('STARTUP_HEARTBEAT_MISMATCH')
    if (h['owner']!=t['identities'][role+'_owner'] or h['topology_identity']!=t['content_hash']
            or h['release']!=t['identities']['release']
            or h['executor_generation']!=t['identities']['executor_generation']
            or h['source_cycle']!=t['identities']['source_cycle']
            or not 0 <= (now-utc(h['observed_at'])).total_seconds() <= 15):
        raise ValueError('OWNERSHIP_HEARTBEAT_INVALID')
    fd=os.open(root/(role+'.lock'),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        if type(h.get('pid')) is not int or h['pid']<=0 or os.read(fd,64)!=str(h['pid']).encode():
            raise ValueError('OWNER_PID_MISMATCH')
        os.kill(h['pid'],0)  # Existence probe only; no signal is delivered.
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return h
        else:
            fcntl.flock(fd,fcntl.LOCK_UN); raise ValueError('OWNER_NOT_RUNNING')
    finally: os.close(fd)


def health(path:Path,kind:str):
    from truth_spine_contract import utc
    now=datetime.now(timezone.utc)
    if kind=='live': return 200,{'status':'LIVE','pid':os.getpid(),'factory_readiness_claimed':False}
    try:
        t,a=topology(path,now=now)
        manifest=read_json(Path(t['release_manifest']),t['release_manifest_hash'])
        if (str(Path(__file__).resolve().parent)!=str(Path(t['release_manifest']).parent/'backend')
                or str(Path(sys.executable))!=str(Path(manifest['runtime_root'])/'bin/python')
                or hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()!=manifest['interpreter_hash']):
            raise ValueError('MIXED_CHECKOUT_RUNTIME')
        for role in ('scheduler','publisher'): probe(t,role)
        p=read_json(Path(t['root'])/'projection.json')
        now=datetime.now(timezone.utc)
        if (p['topology_identity']!=t['content_hash'] or p['identities']!=t['identities']
                or p['authority']!=a['capabilities']
                or not 0 <= (now-utc(p['published_at'])).total_seconds() <= 15):
            raise ValueError('PROJECTION_STALE_OR_MISMATCHED')
        expected=snapshot(t,a,now=utc(p['published_at']))
        if expected!=p: raise ValueError('PROJECTION_NOT_DERIVED_FROM_RECORDS')
        result={'status':'READY','scope':'READ_ONLY_HISTORICAL_OBSERVER','phase':t['phase'],
                'topology_identity':t['content_hash'],'authority':a['capabilities'],
                'live_research_ready':False,'paper_execution_ready':False}
        if kind=='market-readiness': return 503,{**result,'status':'NOT_READY','reason':'NO_OPERATIONAL_AUTHORIZATION'}
        if kind=='research-readiness': result.update(status='HISTORICAL_REVIEW_READY',validated_memory_ready=False)
        return 200,result
    except (OSError,ValueError,KeyError,TypeError,PermissionError,sqlite3.Error) as exc:
        return 503,{'status':'NOT_READY','reason':type(exc).__name__,'live_research_ready':False}


def serve(path:Path,port:int,startup=None):
    if port in {5176,5177,5184,5185,5186,8002} or not 1024<port<65536:
        raise ValueError('ISOLATED_PORT_REQUIRED')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,code,body,media='application/json'):
            data=canonical(body) if media=='application/json' else body
            self.send_response(code);self.send_header('Content-Type',media);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
            if self.command!='HEAD': self.wfile.write(data)
        def do_GET(self):
            if self.path in {'/truth-spine/full-session','/truth-spine/lineage'}:
                try:
                    code,body=historical_response(path,self.path,startup)
                    return self.send(code,body)
                except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
                    return self.send(503,{'status':'UNAVAILABLE','scope':'HISTORICAL_REPLAY_NOT_CURRENT_MARKET'})
            if self.path.startswith('/health/'):
                kind=self.path.removeprefix('/health/')
                if kind in {'live','ready','market-readiness','research-readiness'}:
                    code,body=health(path,kind);return self.send(code,body)
            if self.path in {'/truth-spine/integration','/truth-spine/museum'}:
                code,body=health(path,'ready')
                if code!=200:return self.send(code,body)
                t,_=topology(path);p=read_json(Path(t['root'])/'projection.json')
                return self.send(200,museum_adapter(p) if self.path.endswith('/museum') else p)
            if self.path.startswith('/review/'):
                # Static assets are fixed by the validated package; no arbitrary filesystem route.
                try:
                    t,_=topology(path); base=Path(t['release_manifest']).parent/'frontend'
                    parsed=urlsplit(self.path)
                    if parsed.query and not (parsed.path=='/review/northstar-session.html' and parse_qs(parsed.query)=={'fullSession':['1']}):raise ValueError()
                    relative=Path(parsed.path.removeprefix('/review/'))
                    if relative.is_absolute() or '..' in relative.parts:raise ValueError()
                    asset=base/relative
                    if asset.is_symlink():raise ValueError()
                    manifest=read_json(Path(t['release_manifest']),t['release_manifest_hash'])
                    row=next((r for r in manifest['files'] if r['path']=='frontend/'+relative.as_posix()),None)
                    if row is None:raise ValueError()
                    data=asset.read_bytes()
                    if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError()
                    media={'.html':'text/html','.js':'text/javascript','.css':'text/css','.webp':'image/webp','.svg':'image/svg+xml'}.get(asset.suffix)
                    if media:return self.send(200,data,media)
                except (OSError,ValueError):pass
            self.send(404,{'status':'NOT_FOUND'})
        do_HEAD=do_GET
        def denied(self):self.send(405,{'status':'READ_ONLY'})
        do_POST=do_PUT=do_PATCH=do_DELETE=denied
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    server.serve_forever()


def run(path:Path,role:str,startup:dict | None=None):
    t,_=topology(path);lease=Lease(Path(t['root']),role);stop=False
    def done(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,done);signal.signal(signal.SIGINT,done)
    try:
        if role=='scheduler':ingest(t)
        while not stop:
            t,a=topology(path);now=datetime.now(timezone.utc)
            if role=='publisher':
                atomic(Path(t['root'])/'projection.json',snapshot(t,a,now=now))
                if t['schema']=='iios-historical-topology-v3':
                    backend_pin=Path(t['root'])/'state/backend-instance.json'
                    if backend_pin.exists():
                        publish_historical_view(t,read_json(backend_pin),now.isoformat())
            heartbeat(t,role,now,startup)
            for _ in range(20):
                if stop:break
                time.sleep(.1)
    finally:lease.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    p.add_argument('--role',choices=['scheduler','publisher','backend'],required=True);p.add_argument('--port',type=int)
    p.add_argument('--instance-id',required=True);p.add_argument('--runner-id',required=True)
    p.add_argument('--created-at',required=True)
    p.add_argument('--strict-lineage',action='store_true')
    a=p.parse_args()
    raw=read_json(a.config)
    if a.strict_lineage or a.config.parent.name.startswith('iios-truth-spine-3-acceptance-sb38d-clean-') or raw['schema']=='iios-historical-topology-v3':
        from truth_spine_integration import activate_topology_sqlite
        activate_topology_sqlite(raw,a.role)
    # No legacy app startup. Validate deny-only topology before the fixed,
    # self-only OS probes; install the irreversible guard before service work.
    t,_=topology(a.config)
    from truth_spine_process_identity import write_startup
    startup=write_startup(Path(t['root']),a.instance_id,a.runner_id,a.role,a.port,a.created_at)
    deny_external_io()
    if a.role=='backend':
        if t['schema']=='iios-historical-topology-v3':
            # Mutable instance selection is confined to the new run's state subtree.
            atomic(Path(t['root'])/'state/backend-instance.json',startup)
        serve(a.config,a.port,startup)
    else:run(a.config,a.role,startup)


if __name__=='__main__':main()
