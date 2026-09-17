"""Explicit disposable entrypoint. Never selected by production CLI or CI.

No credential selector, provider route, live grant or account claim is accepted.
The exact immutable descriptor and roots are independently passed to this tool.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
import re
from pathlib import Path
import ssl
import socket
import http.client
import sys
import time

from alpha_session_contract import require
from alpha_session_evidence import json_document,verify_files
from alpha_session_execution import safe_root,read_record,publish
from alpha_observation_launch import lexical,directory
from provider_gateway_contract import content_hash,locked_authority,pin
from truth_spine_observation_roles import admit_roles,record,seed,SCOPE,configuration

ENV={'LANG':'C','LC_ALL':'C','TZ':'UTC'}


def load_config(path,expected,roots,*,now):
    """Reject descriptor/path/env mutations before any child is created."""
    require(type(roots) is dict and set(roots)=={'runtime','release','control','output'},'DISPOSABLE_ROOTS')
    for value in roots.values():lexical(value)
    path=lexical(str(path));require(path==lexical(str(lexical(roots['output']).parent)+'/qualification.json') or
        path==lexical(roots['output']+'/topology.json'),'DISPOSABLE_DESCRIPTOR_PATH')
    fd=safe_root(str(path.parent))
    try:c=read_record(fd,path.name)
    finally:os.close(fd)
    pin(c,expected)
    require(set(c)=={'schema','admission','admission_parent','roots','plan','requests','request_pins'} and
        c['schema']=='iios-disposable-role-config-v1' and c['roots']==roots,'DISPOSABLE_CONFIG')
    cap=admit_roles(c['admission'],c['admission_parent'],approved_roots=roots,now=now);cap.recheck(now)
    d=cap.document();rt=d['runtime']
    require(c['requests']==[{'runtime':rt}]*3 and c['request_pins']==[], 'DISPOSABLE_NO_PROVIDER')
    require(c==configuration(cap),'DISPOSABLE_CONFIG_BINDING')
    require(Path(sys.executable).resolve()==Path(rt['root'])/rt['interpreter'] and
        Path(__file__).resolve()==Path(roots['release'])/'alpha_observation_qualification.py','DISPOSABLE_RUNNING_INPUTS')
    require(hashlib.sha256(Path('/usr/bin/sandbox-exec').read_bytes()).hexdigest()==d['launch']['sandbox_hash'],
        'DISPOSABLE_SANDBOX_HASH')
    # Exact safe environment, not a blacklist: child receives only these values.
    require(dict(os.environ)==ENV,'DISPOSABLE_ENVIRONMENT')
    cert=Path(roots['control'])/'loopback.crt'
    require(hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()==d['launch']['peer_hash'],
        'DISPOSABLE_CERT_PIN')
    return c,cap


def read_only_roundtrip(owner,method):
    """Numeric loopback only, no DNS/redirects, bounded response, no provider."""
    require(method in ('GET','HEAD'),'DISPOSABLE_HTTP_METHOD')
    from alpha_observation_launch import listener_pids
    owner.verify_ready();d=owner.capability.document();launch=d['launch']
    entry=owner.children.active['backend'];owner.children.verify(entry)
    require(listener_pids(launch['port'])==[entry['child'].pid],'DISPOSABLE_LISTENER_OWNER')
    owner.check(launch['stop_ns'])
    context=ssl.create_default_context(cafile=d['roots']['control']+'/loopback.crt')
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.settimeout(min(2,(launch['stop_ns']-time.monotonic_ns())/1e9))
        sock.connect(('127.0.0.1',launch['port']))
        with context.wrap_socket(sock,server_hostname='127.0.0.1') as secured:
            require(hashlib.sha256(secured.getpeercert(binary_form=True)).hexdigest()==launch['peer_hash'],
                'DISPOSABLE_TLS_PEER')
            secured.sendall((method+' /truth-spine/observation HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n').encode('ascii'))
            response=http.client.HTTPResponse(secured,method=method);response.begin()
            require(response.status==200 and response.getheader('Transfer-Encoding') is None,
                'DISPOSABLE_HTTP_RESPONSE')
            length=response.getheader('Content-Length')
            require(type(length) is str and length.isascii() and length.isdecimal() and 0<int(length)<=65536,
                'DISPOSABLE_HTTP_SIZE')
            raw=response.read(65537);require(len(raw)<=65536,'DISPOSABLE_HTTP_SIZE')
            if method=='HEAD':require(raw==b'','DISPOSABLE_HEAD_BODY')
            else:
                require(len(raw)==int(length),'DISPOSABLE_HTTP_SIZE')
                value=json_document(raw)
                require(value['scope']==SCOPE and value['admission_parent']==owner.capability.identity and
                    value['response_parents']==d['seed_parents'] and value['reserved']==value['completed']==0 and
                    value['seeded_records']==3 and value['production_qualified'] is False and
                    value['authority']==locked_authority(),'DISPOSABLE_RESPONSE_SCOPE')
    owner.check(launch['stop_ns']);owner.children.verify(entry)
    return record(owner.capability,dict(method=method,status=200,tls_verified=True,provider_requests=0))


def controlled_denial(allowed,denied,spec,expected,*,owner,owner_parent,comparison_parent):
    """Consume independently pinned dummy trials; never infer denial from errno.

    This collector does not create trials or grant execution authority. Baseline
    and confined trials must already have independently verified ownership and
    matching dummy inputs. Failure/unknown OS evidence stays unattributed.
    """
    from alpha_denial_collector import collect,query
    pin({'allowed':allowed,'denied':denied},comparison_parent);query(spec,expected)
    fields={'scope','operation','target','input_parent','host_parent','uid','profile_parent',
        'owner_parent','outcome','errno','authority'}
    require(all(type(x) is dict and set(x)==fields for x in (allowed,denied)),'DISPOSABLE_COMPARISON_SCHEMA')
    for x in (allowed,denied):
        require(x['scope']=='DISPOSABLE_DENIAL_ONLY' and x['authority']==locked_authority() and
            all(v is False for v in x['authority'].values()),'DISPOSABLE_COMPARISON_SCOPE')
    require(all(allowed[k]==denied[k] for k in ('operation','target','input_parent','host_parent','uid')) and
        allowed['outcome']=='ALLOWED' and allowed['errno'] is None and allowed['profile_parent'] is None and
        denied['outcome']=='DENIED' and type(denied['errno']) is int and denied['errno'] in (1,13),
        'DISPOSABLE_COMPARISON_CONTROL')
    require(type(allowed['uid']) is int and allowed['uid']>0 and
        all(type(x[k]) is str and re.fullmatch('[0-9a-f]{64}',x[k]) for x in (allowed,denied)
            for k in ('input_parent','owner_parent','host_parent')) and allowed['owner_parent']!=denied['owner_parent'],
        'DISPOSABLE_COMPARISON_IDENTITY')
    require(denied['owner_parent']==owner_parent==spec['owner_parent'] and
        all(denied[k]==spec[k] for k in ('operation','target','host_parent','profile_parent')),
        'DISPOSABLE_COMPARISON_PARENT')
    result=collect(spec,expected,owner=owner,expected_owner=owner_parent)
    matched=(result['category']=='OS_DENIAL_REPORT_MATCH' and result['matches']==1 and
        result['collector_exit_verified'] is True and result['collector_exit']==0)
    return dict(schema='iios-controlled-denial-result-v1',scope='DISPOSABLE_DENIAL_ONLY',
        comparison_parent=comparison_parent,query_parent=expected,collector_parent=content_hash(result),
        attribution='CONTROLLED_CORRELATED_DENIAL' if matched else 'UNATTRIBUTED',
        category=result['category'],confinement_qualified=False,production_qualified=False,authority=locked_authority())


def fixed_exception(exc):
    return type(exc).__name__ if type(exc) in (ValueError,PermissionError,OSError,TimeoutError,FileNotFoundError) else 'UNCLASSIFIED_ERROR'


def run_parent(config,cap):
    from truth_spine_full_day_runner import ObservationLifecycle
    d=cap.document();root=lexical(d['roots']['output']);parent=directory(str(root.parent))
    try:
        os.mkdir(root.name,0o700,dir_fd=parent)
        fd=os.open(root.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    finally:os.close(parent)
    owner=None;primary=None;cleanup=None;seeded=0;http=[];stage='SEED_PUBLICATION'
    try:
        publish(fd,'topology.json',config);os.mkdir('requests',0o700,dir_fd=fd)
        req=os.open('requests',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            previous=None
            for i in range(3):
                row=seed(i,previous);pin(row,d['seed_parents'][i]);publish(req,f'{i}.seed.json',row);previous=content_hash(row);seeded+=1
        finally:os.close(req)
        owner=ObservationLifecycle.for_disposable(config,cap)
        stage='STARTUP';owner.start();owner.verify_ready()
        stage='READ_ONLY_HTTP'
        for method in ('GET','HEAD'):http.append(read_only_roundtrip(owner,method))
        # No gateway call or fabricated provider completion exists in this path.
    except Exception as exc:
        primary={'stage':stage,'category':fixed_exception(exc)}
    finally:
        try:
            if owner is not None:cleanup=owner.cleanup()
        except Exception as exc:
            cleanup=record(cap,{'verified':False,'cooperative':False,'category':fixed_exception(exc)})
        result=record(cap,dict(status='FUNCTIONAL_PASS' if primary is None and cleanup and cleanup.get('verified') is True and cleanup.get('cooperative') is True else 'FAILED_CLOSED',schema='iios-disposable-functional-result-v1',admission_parent=cap.identity,
            primary_failure=primary,cleanup=cleanup,provider_requests=0,seed_records=seeded,http=http,
            confinement='UNQUALIFIED_UNTIL_CONTROLLED_COMPARISONS',authority=locked_authority()))
        try:publish(fd,'qualification-result.json',result)
        finally:os.close(fd)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    p.add_argument('--config-sha256');p.add_argument('--approved-roots-json')
    p.add_argument('--role',choices=('scheduler','publisher','backend'));p.add_argument('--port',type=int)
    for name in ('observation-admission','instance-id','runner-id','created-at'):p.add_argument('--'+name)
    args=p.parse_args()
    require(args.config_sha256 is not None and args.approved_roots_json is not None,'DISPOSABLE_INVOCATION_PINS')
    roots=json_document(args.approved_roots_json.encode())
    c,cap=load_config(args.config,args.config_sha256,roots,now=datetime.now(timezone.utc))
    if args.role:
        require(args.observation_admission==cap.identity and args.instance_id and args.runner_id and args.created_at,
            'DISPOSABLE_CHILD_PARENTS')
        from truth_spine_full_day_service import run_bound_observation_role
        return run_bound_observation_role(args,c,cap)
    require(args.observation_admission is None and args.port is None and not any(
        (args.instance_id,args.runner_id,args.created_at)),'DISPOSABLE_PARENT_ARGUMENTS')
    return run_parent(c,cap)


if __name__=='__main__':
    try:
        result=main()
        sys.exit(0 if result is None or result.get('status')=='FUNCTIONAL_PASS' else 4)
    except Exception as exc:
        print(json.dumps({'scope':SCOPE,'status':'FAILED_CLOSED','category':fixed_exception(exc)}))
        sys.exit(4)
