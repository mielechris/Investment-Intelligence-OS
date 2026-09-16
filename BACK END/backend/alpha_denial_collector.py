"""Bounded, read-only OS-report collection for separately approved dummy trials.

Apple documents subsystem com.apple.sandbox.reporting/category violation and
Sandbox/Violation/Process/Path fields. The log(1) source filter and read bounds
are additional controls. Correlation is not proof of complete confinement.
No collector call is made at import; tests replace only process/OS effects.
"""
from dataclasses import asdict
import hashlib
import json
import os
import re
import subprocess
import time

from alpha_session_contract import require, instant
from alpha_observation_launch import lexical, ENV
from provider_gateway_contract import content_hash, pin, safe_document, locked_authority
from truth_spine_process_identity import inspect_macos

LIMIT = 4096
OPERATIONS = ('file-read-data', 'file-write-create', 'network-outbound', 'network-inbound', 'process-exec')
SOURCE = 'https://developer.apple.com/documentation/security/discovering-and-diagnosing-app-sandbox-violations'


def query(spec, expected):
    safe_document(spec);pin(spec,expected)
    require(set(spec)=={'schema','scope','pid','name','executable','operation','target','start','end',
        'cwd','log_sha256','launch_parent','host_parent','profile_parent','owner_parent','authority'}, 'DENIAL_SCHEMA')
    require(spec['schema']=='iios-bounded-os-denial-v1' and spec['scope']=='DISPOSABLE_DENIAL_ONLY', 'DENIAL_SCOPE')
    require(type(spec['pid']) is int and 0<spec['pid']<2**31 and
        re.fullmatch('[A-Za-z0-9_.-]{1,64}',spec['name']), 'DENIAL_PROCESS')
    for k in ('executable','cwd'):lexical(spec[k])
    # No free-form predicate/target interpolation. Only parent-created dummy
    # filesystem targets and fixed non-provider denial endpoints are admitted.
    target=spec['target'];require(type(target) is str,'DENIAL_TARGET')
    if spec['operation'] in ('file-read-data','file-write-create','process-exec'):
        require(lexical(target).is_relative_to(lexical(spec['cwd'])),'DENIAL_DUMMY_ROOT')
    else:
        require(spec['operation'] in OPERATIONS and target in ('127.0.0.1:38494','192.0.2.1:443'), 'DENIAL_ENDPOINT')
    require(instant(spec['start']).microsecond == instant(spec['end']).microsecond == 0, 'DENIAL_CLOCK_PRECISION')
    require(0<(instant(spec['end'])-instant(spec['start'])).total_seconds()<=10,'DENIAL_WINDOW')
    for key in ('log_sha256','launch_parent','host_parent','profile_parent','owner_parent'):
        require(type(spec[key]) is str and re.fullmatch('[0-9a-f]{64}',spec[key]),'DENIAL_PIN')
    require(spec['authority']==locked_authority() and all(v is False for v in spec['authority'].values()),'DENIAL_AUTHORITY')
    predicate=('subsystem == "com.apple.sandbox.reporting" AND category == "violation" AND '
        'processImagePath == "/usr/libexec/sandboxd" AND '
        'eventMessage CONTAINS "('+str(spec['pid'])+')"')
    return ['/usr/bin/log','show','--style','ndjson','--timezone','UTC','--start',
        instant(spec['start']).strftime('%Y-%m-%d %H:%M:%S+0000'),'--end',
        instant(spec['end']).strftime('%Y-%m-%d %H:%M:%S+0000'),'--predicate',predicate]


def reduce_events(raw, spec):
    """In-memory parse; never retain/hash raw text, arbitrary messages or paths."""
    if type(raw) is not bytes or len(raw)>LIMIT:return {'category':'OVERFLOW','matches':0}
    matches=0
    try:
        text=raw.decode('utf-8','strict')
        require(not any(ord(c)<32 and c not in '\n\r\t' for c in text),'DENIAL_CONTROL')
        for line in text.splitlines():
            if not line:continue
            event=json.loads(line,object_pairs_hook=unique)
            if (event.get('subsystem')!='com.apple.sandbox.reporting' or event.get('category')!='violation' or
                event.get('processImagePath') not in ('/usr/libexec/sandboxd',)):continue
            at=instant(event['timestamp'].replace(' ', 'T',1))
            if not instant(spec['start'])<=at<=instant(spec['end']):continue
            message=event['eventMessage'];require(type(message) is str,'DENIAL_MESSAGE')
            lines=message.splitlines()
            expected=f"Sandbox: {spec['name']}({spec['pid']}) deny(1) {spec['operation']} {spec['target']}"
            # Exact documented message fields; prefix/substring resemblance is not a match.
            required=[expected,f"Violation: deny(1) {spec['operation']} {spec['target']}",
                f"Process: {spec['name']} [{spec['pid']}]",f"Path: {spec['executable']}"]
            if lines[:4]!=required:continue
            if any(line.startswith(('Sandbox:','Violation:','Process:','Path:')) for line in lines[4:]):continue
            matches+=1
        return {'category':'OS_DENIAL_REPORT_MATCH' if matches==1 else 'UNKNOWN','matches':matches}
    except Exception:return {'category':'UNKNOWN','matches':0}


def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,'DENIAL_DUPLICATE_FIELD');result[k]=v
    return result


def collect(spec, expected, *, owner, expected_owner):
    """Execute one fixed log query only after separate native authorization.

    An independently pinned complete ProcessObservation must remain stable around
    capture. Launcher/profile correlation is external reviewed provenance, not an
    invented field in Apple's report. No signal or automatic retry is implemented.
    An overrun reports an unverified collector child and stops later qualification.
    """
    argv=query(spec,expected);pin(owner,expected_owner)
    require(expected_owner==spec['owner_parent'],'DENIAL_OWNER_PARENT')
    require(owner['pid']==spec['pid'] and owner['executable']==spec['executable'] and
        instant(owner['start_time']) <= instant(spec['start']), 'DENIAL_OWNER')
    def observe():
        v=asdict(inspect_macos(spec['pid']));v['argv']=list(v['argv']);return v
    require(observe()==owner,'DENIAL_PID_REUSE')
    with open('/usr/bin/log','rb') as f:
        raw=f.read(4*1024*1024+1)
    require(len(raw)<=4*1024*1024 and hashlib.sha256(raw).hexdigest()==spec['log_sha256'],'DENIAL_TOOL')
    del raw
    start=time.monotonic_ns();last=start;deadline=start+5_000_000_000
    child=subprocess.Popen(argv,cwd=spec['cwd'],env=dict(ENV),stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
    child.stdin.close();buffers={'stdout':bytearray(),'stderr':bytearray()};failure=None
    try:
        for name in buffers:os.set_blocking(getattr(child,name).fileno(),False)
        eof=set()
        while len(eof)<2 or child.poll() is None:
            now=time.monotonic_ns()
            if not last <= now < deadline:failure='CAPTURE_DEADLINE';break
            last=now
            for name,buf in buffers.items():
                if name in eof:continue
                try:block=os.read(getattr(child,name).fileno(),min(512,LIMIT+1-len(buf)))
                except BlockingIOError:continue
                if not block:eof.add(name);continue
                buf.extend(block)
                if len(buf)>LIMIT:failure='OVERFLOW';break
            if failure:break
            time.sleep(.005)
        status=child.poll()
        if status!=0 or buffers['stderr']:failure=failure or 'COLLECTOR_UNVERIFIED'
        result={'category':failure,'matches':0} if failure else reduce_events(bytes(buffers['stdout']),spec)
        if observe()!=owner:result={'category':'IDENTITY_CHANGED','matches':0}
        return {'schema':'iios-os-denial-observation-v1','scope':'DISPOSABLE_DENIAL_ONLY',
            'parent':expected,'owner_parent':expected_owner,**result,'collector_exit':status,
            'collector_pid':child.pid,'collector_exit_verified':status is not None,
            'attribution':'CORRELATED_REPORT_ONLY','confinement_qualified':False,
            'production_qualified':False,'authority':locked_authority()}
    except Exception:
        return {'schema':'iios-os-denial-observation-v1','scope':'DISPOSABLE_DENIAL_ONLY',
            'parent':expected,'owner_parent':expected_owner,'category':'COLLECTION_FAILED','matches':0,
            'collector_exit':child.poll(),'collector_pid':child.pid,'collector_exit_verified':False,
            'attribution':'UNATTRIBUTED','confinement_qualified':False,'production_qualified':False,
            'authority':locked_authority()}
    finally:
        for buf in buffers.values():buf.clear()
        child.stdout.close();child.stderr.close()
