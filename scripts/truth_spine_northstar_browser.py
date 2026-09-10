"""Explicit offline Safari acceptance, NOT a full-session runner or installer.

Only fixture metadata and a pinned frontend are served. No operational imports,
state roots, credentials, provider transport or scheduler are present.
"""
import argparse
import base64
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import re
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.request


def encoded(x): return (json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True)+'\n').encode()


def verify_review_provenance(build_root, source):
    """Read-only verification of the full non-installable source-review contract."""
    path = Path(__file__).with_name('truth_spine_frontend_provenance.py')
    spec = importlib.util.spec_from_file_location('northstar_review_provenance', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = Path(build_root).absolute()
    if any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError('PROVENANCE_SYMLINK')
    record_path = root/'frontend-provenance.json'
    if record_path.is_symlink(): raise ValueError('PROVENANCE_SYMLINK')
    record = json.loads(record_path.read_bytes())
    if set(record) != {'schema','inputs','input_hash','outputs','output_hash','observation','content_hash'} or record['schema'] != 'iios-source-review-build-NOT-INSTALLABLE':
        raise ValueError('REVIEW_PROVENANCE_SCHEMA')
    if module.digest({k:v for k,v in record.items() if k != 'content_hash'}) != record['content_hash']:
        raise ValueError('REVIEW_PROVENANCE_HASH')
    commit = module.git(source, 'rev-parse', 'HEAD').strip()
    expected = module.inputs(source, commit, northstar=True, review=True)
    if record['inputs'] != expected or record['input_hash'] != module.digest(expected):
        raise ValueError('REVIEW_PROVENANCE_INPUTS')
    module.validate_outputs(root/'frontend/dist', record['outputs'], northstar=True)
    if record['output_hash'] != module.digest(record['outputs']): raise ValueError('REVIEW_PROVENANCE_OUTPUTS')
    if json.loads((root/'frontend/build-observation.json').read_bytes()) != record['observation']:
        raise ValueError('REVIEW_PROVENANCE_OBSERVATION')
    return record


def independent_cleanup(steps):
    """Never let one cleanup/persistence exception skip another owned cleanup."""
    results = []
    for name, action in steps:
        try:
            action(); results.append({'step': name, 'ok': True})
        except Exception as exc:
            results.append({'step': name, 'ok': False, 'category': type(exc).__name__})
    return results


class FixtureHTTPServer(ThreadingHTTPServer):
    # Reuse a retired TCP address, never share a listening port. There is one
    # real bind (no throwaway probe with different socket options).
    allow_reuse_address = True
    allow_reuse_port = False
    daemon_threads = False
    block_on_close = True


def socket_inventory():
    """Read-only IPv4/IPv6 census, restricted to the two fixture ports."""
    result=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:5291','-iTCP:5292','-FpcftnT'],capture_output=True,text=True,timeout=5)
    if result.returncode not in (0,1):raise RuntimeError('SOCKET_INVENTORY_UNAVAILABLE')
    rows=[];pid=None;row=None
    for line in result.stdout.splitlines():
        if line.startswith('p'):pid=int(line[1:])
        elif line.startswith('f'):
            row={'pid':pid};rows.append(row)
        elif row is not None and line.startswith('t'):row['family']=line[1:]
        elif row is not None and line.startswith('n'):row['address']=line[1:]
        elif row is not None and line.startswith('TST='):row['state']=line[4:]
    net=subprocess.run(['/usr/sbin/netstat','-an','-p','tcp'],capture_output=True,text=True,timeout=5)
    if net.returncode:raise RuntimeError('SOCKET_STATE_UNAVAILABLE')
    sockets=sorted(line.strip() for line in net.stdout.splitlines() if re.search(r'[.:](5291|5292)\s',line))
    return {'listeners':sorted([r for r in rows if r.get('state')=='LISTEN'],key=lambda r:(r['pid'],r.get('address',''))),'sockets':sockets}


def listener_binding(inventory,port,pid):
    rows=[r for r in inventory['listeners'] if r.get('address','').endswith(':'+str(port))]
    allowed={'127.0.0.1:'+str(port),'[::1]:'+str(port)}
    if not rows or any(r['pid']!=pid or r['address'] not in allowed for r in rows):
        raise RuntimeError('LISTENER_IDENTITY_MISMATCH:'+str(port))
    return rows


def stable_port_clear(record,observe=socket_inventory,*,reject_listener=True,limit=30,interval=.1,wait=time.sleep):
    """Three identical observations, not elapsed time, prove stable absence."""
    previous=None;matches=0
    for _ in range(limit):
        current=observe();record({'at':time.monotonic(),'socket_inventory':current})
        if current['listeners'] and reject_listener:raise RuntimeError('UNOWNED_LISTENER_PRESENT')
        matches=matches+1 if not current['listeners'] and current==previous else (1 if not current['listeners'] else 0)
        if matches>=3:return current
        previous=current;wait(interval)
    raise RuntimeError('PORT_CLEAR_NOT_STABLE')


def stop_verified_process(process,expected,fingerprint):
    if process.poll() is not None:return
    if fingerprint(process.pid)!=expected:raise RuntimeError('DRIVER_IDENTITY_MISMATCH_NO_SIGNAL')
    process.terminate();process.wait(timeout=10)


SAFARI_LAUNCHER='/usr/bin/safaridriver'
SAFARI_HTTP_SERVICE='/System/Library/PrivateFrameworks/WebDriver.framework/Versions/A/XPCServices/com.apple.WebDriver.HTTPService.xpc/Contents/MacOS/com.apple.WebDriver.HTTPService'


def safari_signed_artifact(path,role):
    """Verify executable signing and independently bind every helper resource.

    Apple's shipped XPC resource envelope uses obsolete omit rules. Do not
    pretend that envelope passed: check executable signing, then require an
    exact root-owned, non-writable complete bundle inventory against the pin.
    """
    identifier={'launcher':'com.apple.safaridriver','helper':'com.apple.WebDriver.HTTPService'}[role]
    artifact=system_executable(path)
    requirement='=anchor apple and identifier "'+identifier+'"'
    result=subprocess.run(['/usr/bin/codesign','--verify','--strict','--ignore-resources','-R',requirement,path],capture_output=True,timeout=10)
    if result.returncode:raise RuntimeError('SAFARI_APPLE_CODE_SIGNATURE_INVALID')
    description=subprocess.run(['/usr/bin/codesign','-d','-r-','--verbose=4',path],capture_output=True,text=True,timeout=10)
    if description.returncode:raise RuntimeError('SAFARI_CODE_IDENTITY_UNAVAILABLE')
    bundle={}
    if role=='helper':
        root=Path(path).resolve().parents[2]
        expected={'Contents/Info.plist','Contents/MacOS/com.apple.WebDriver.HTTPService','Contents/_CodeSignature/CodeResources','Contents/version.plist'}
        for p in sorted(root.rglob('*')):
            s=p.lstat()
            if p.is_symlink() or s.st_uid!=0 or s.st_mode & 0o022 or not (p.is_dir() or p.is_file()):raise RuntimeError('SAFARI_BUNDLE_UNTRUSTED')
            if p.is_file():bundle[str(p.relative_to(root))]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':s.st_size,'mode':s.st_mode & 0o777,'uid':s.st_uid}
        if set(bundle)!=expected:raise RuntimeError('SAFARI_BUNDLE_INVENTORY_INVALID')
    return {**artifact,'code_identity':identifier,'code_verified':True,'requirement':requirement,'designated_requirement':description.stdout.strip(),'bundle':bundle,'resource_validation':'EXACT_PINNED_FULL_INVENTORY_NOT_OBSOLETE_ENVELOPE'}


def safari_runtime_artifact(process,pins,role):
    observed=safari_signed_artifact(process['executable'],role)
    admit_safari_artifact({**process,'artifact':observed},pins,role)
    return observed


def admit_safari_artifact(process,pins,role):
    configured=pins[role]['path'];actual=process['executable']
    permitted={configured}
    prefix='/System/Volumes/Preboot/Cryptexes/OS/'
    if role=='helper' and configured.startswith(prefix):
        permitted.add(configured.replace(prefix,'/System/Volumes/Preboot/Cryptexes/Incoming/OS/',1))
    if actual not in permitted:raise RuntimeError('SAFARI_UNMODELED_EXECUTABLE_TRANSITION')
    observed=process.get('artifact',{})
    if observed.get('path')!=actual or observed.get('code_verified') is not True:raise RuntimeError('SAFARI_CODE_IDENTITY_UNAVAILABLE')
    for key in ['sha256','mode','uid','code_identity','code_verified','requirement','designated_requirement','bundle']:
        if key not in observed or observed[key]!=pins[role][key]:raise RuntimeError('SAFARI_EXECUTABLE_PIN_MISMATCH')


def system_executable(path):
    p=Path(path);s=p.stat()
    if s.st_uid!=0 or s.st_mode & 0o022 or not p.is_file():raise RuntimeError('SYSTEM_EXECUTABLE_UNTRUSTED')
    return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'uid':s.st_uid,'mode':s.st_mode & 0o777,'device':s.st_dev,'inode':s.st_ino}


def kernel_process(pid):
    """Kernel executable identity, never argv/name alone, for Safari ownership."""
    result=subprocess.run(['/bin/ps','-p',str(pid),'-o','pid=,ppid=,uid=,lstart='],capture_output=True,text=True,timeout=5,env={**os.environ,'LC_ALL':'C','TZ':'UTC'})
    if result.returncode==1 and not result.stdout.strip():return None
    if result.returncode:raise RuntimeError('PROCESS_IDENTITY_UNAVAILABLE')
    fields=result.stdout.split();path_buffer=ctypes.create_string_buffer(4096)
    lib=ctypes.CDLL('/usr/lib/libproc.dylib');lib.proc_pidpath.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32];lib.proc_pidpath.restype=ctypes.c_int
    if lib.proc_pidpath(int(pid),path_buffer,len(path_buffer))<=0:raise RuntimeError('KERNEL_EXECUTABLE_UNAVAILABLE')
    started=datetime.strptime(' '.join(fields[3:]),'%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc).timestamp()
    return {'pid':int(fields[0]),'ppid':int(fields[1]),'uid':int(fields[2]),'started':started,'executable':str(Path(path_buffer.value.decode()).resolve())}


def safari_processes():
    rows=subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True).splitlines()
    result=[]
    for row in rows:
        fields=row.strip().split(None,1)
        if len(fields)==2 and ('safaridriver' in fields[1] or 'com.apple.WebDriver.HTTPService' in fields[1]):
            process=kernel_process(int(fields[0]))
            if process:result.append(process)  # Unknown/pre-existing variants also block adoption.
    return result


def authenticate_safari_listener(inventory,launcher,listener,baseline,started,now,executables,uid):
    """Bounded launch transaction; no pre-existing helper or arbitrary PPID 1."""
    if baseline:raise RuntimeError('PREEXISTING_SAFARI_AUTOMATION')
    if launcher is None or listener is None:raise RuntimeError('SAFARI_PROCESS_MISSING')
    admit_safari_artifact(launcher,executables,'launcher')
    admit_safari_artifact(listener,executables,'launcher' if listener['pid']==launcher['pid'] else 'helper')
    if launcher['uid']!=uid or launcher['executable']!=executables['launcher']['path'] or launcher['started']<int(started):raise RuntimeError('SAFARI_LAUNCHER_INVALID')
    if listener['uid']!=uid or not int(started)<=listener['started']<=now or now-started>10:raise RuntimeError('SAFARI_LISTENER_LAUNCH_WINDOW')
    if listener['pid']==launcher['pid']:
        role='DIRECT_LAUNCHER'
    elif listener.get('artifact',{}).get('sha256')==executables['helper'].get('sha256') and listener['ppid']==1 and listener.get('artifact',{}).get('code_verified') is True:
        role='APPLE_WEBDRIVER_XPC'
    else:raise RuntimeError('SAFARI_LISTENER_EXECUTABLE_INVALID')
    bindings=listener_binding(inventory,5292,listener['pid'])
    return {'role':role,'launcher':launcher,'listener':listener,'baseline':baseline,'started':started,'verified_at':now,'executables':executables,'bindings':bindings,'association':'EXCLUSIVE_NEW_APPLE_PROCESS_IN_OWNED_LAUNCH_WINDOW','signal_target':'VERIFIED_LAUNCHER_ONLY'}


def stable_safari_ownership(observe,record,receipt,limit=20,wait=time.sleep):
    """Three stable independently verified kernel/binary/socket observations."""
    previous=None;count=0
    for _ in range(limit):
        value=observe();record(value)
        launcher=value['launcher'];listener=value['listener']
        if any(launcher[k]!=receipt[k] for k in ['pid','ppid','uid','started','executable']):raise RuntimeError('SAFARI_STARTUP_RECEIPT_MISMATCH')
        identity={k:value[k] for k in ['launcher','listener','bindings','executables']}
        if previous is not None and (listener['pid']!=previous['listener']['pid'] or listener['started']!=previous['listener']['started']):raise RuntimeError('SAFARI_LISTENER_IDENTITY_CHANGED')
        count=count+1 if previous==identity else 1
        if count==3:return {**value,'stable_observations':count,'startup_receipt':receipt}
        previous=identity;wait(.1)
    raise RuntimeError('SAFARI_OWNERSHIP_NOT_STABLE')


class AcceptanceTransaction:
    """One invocation, one browser session, one shutdown; no real-port retries."""
    def __init__(self,persist):self.persist=persist;self.state='NEW';self.history=[]
    def advance(self,expected,state,**facts):
        if self.state!=expected:raise RuntimeError('ACCEPTANCE_TRANSACTION_ORDER')
        row={'from':expected,'to':state,'at':time.monotonic(),**facts}
        self.persist([*self.history,row])  # publication failure does not advance
        self.history.append(row);self.state=state


def safari_fixture_window(url,window_id=None,activate=False):
    """Bind a native window by exact fixture URL; never select another tab."""
    if not re.fullmatch(r'http://127\.0\.0\.1:5291/review/northstar-session\.html\?fullSession=1(?:#[A-Za-z0-9_-]+)?',url):raise RuntimeError('NATIVE_WINDOW_URL_INVALID')
    if window_id is not None and (type(window_id) is not int or window_id<=0):raise RuntimeError('NATIVE_WINDOW_ID_INVALID')
    if activate and window_id is None:raise RuntimeError('NATIVE_WINDOW_RECEIPT_REQUIRED')
    script='''if application id "com.apple.Safari" is not running then error "SAFARI_NOT_RUNNING"
tell application id "com.apple.Safari"
set matches to {}
repeat with w in windows
if URL of current tab of w is URL_VALUE then set end of matches to id of w
end repeat
if count of matches is not 1 then error "FIXTURE_WINDOW_NOT_UNIQUE"
set selectedID to item 1 of matches
ID_CHECK
ACTIVATE
return selectedID
end tell'''.replace('URL_VALUE',json.dumps(url)).replace('ID_CHECK',f'if selectedID is not {window_id} then error "FIXTURE_WINDOW_ID_CHANGED"' if window_id is not None else '').replace('ACTIVATE','set index of window id selectedID to 1\nactivate' if activate else '')
    try:result=subprocess.run(['/usr/bin/osascript','-e',script],check=True,capture_output=True,text=True,timeout=8)
    except (subprocess.SubprocessError,OSError) as error:raise RuntimeError('NATIVE_WINDOW_ACQUISITION_FAILED:'+type(error).__name__) from None
    value=result.stdout.strip()
    if not value.isdecimal() or int(value)<=0 or (window_id is not None and int(value)!=window_id):raise RuntimeError('NATIVE_WINDOW_RECEIPT_INVALID')
    return int(value)


def acquire_owned_browser_focus(observe,select,expected,record,limit=20,wait=time.sleep,activate_native=None):
    """Acquire foreground before settlement, never change its completed result."""
    first=observe();record({'stage':'foreground-observed','observation':first})
    if first['handle']!=expected:raise RuntimeError('BROWSER_HANDLE_OWNERSHIP_MISMATCH')
    if first['focused'] and first['visible']:return first
    select(expected)  # Exactly one explicit WebDriver window selection.
    if activate_native is not None:record({'stage':'native-window-acquisition','receipt':activate_native(first)})
    for _ in range(limit):
        current=observe();record({'stage':'foreground-reacquisition','observation':current})
        if any(current[k]!=first[k] for k in ['handle','url','identity','active','scroll']):raise RuntimeError('BROWSER_CONTEXT_CHANGED_DURING_FOCUS')
        if current['focused'] and current['visible']:return current
        wait(.05)
    raise RuntimeError('OWNED_BROWSER_FOCUS_UNAVAILABLE')


def verify_prior_cleanup(path,fingerprint):
    """A new sequential diagnostic cannot race a still-running predecessor."""
    if path is None:return
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise RuntimeError('PRIOR_CLEANUP_MISSING')
    record=json.loads(path.read_bytes())
    if record.get('classification') not in ('DIAGNOSTIC_ONLY','GREEN') or not record.get('processes_exited') or not record.get('logs_closed') or not record.get('ports_stable'):
        raise RuntimeError('PRIOR_CLEANUP_INCOMPLETE')
    for pid in record['owned_pids']:
        if fingerprint(pid):raise RuntimeError('PRIOR_OWNED_PROCESS_ALIVE')


@dataclass(frozen=True)
class BoundFixture:
    """Immutable bytes, not a per-request projection constructor."""
    body: bytes
    sha256: str

    @classmethod
    def bind(cls, view):
        body = encoded(view)
        return cls(body, hashlib.sha256(body).hexdigest())

    def response(self):
        if hashlib.sha256(self.body).hexdigest() != self.sha256:
            raise ValueError('FIXTURE_BYTES_CHANGED')
        return self.body


def admit_capture(evidence, data):
    """Rejected images remain evidence but can never enter acceptance totals."""
    reason = None
    if data['beforeIdentity']['binding'] != data['afterIdentity']['binding']:
        reason = 'SCREENSHOT_GENERATION_CHANGED'
    elif not data['screenshotGeometryMatches']:
        reason = 'SCREENSHOT_GEOMETRY_CHANGED'
    elif data.get('responsiveFailure'):
        reason = 'RESPONSIVE_GATE_FAILED'
    if reason:
        data['rejection'] = reason
        evidence.setdefault('rejected_captures', []).append(data)
        raise RuntimeError(reason+':'+data['name'])
    evidence['captures'].append(data)


# Served ONLY by this fixture server, before the unchanged compiled module.
# Native timers/performance remain real; the fixture admission clock is explicit.
# No production source, response fields, polling interval or freshness rule changes.
FIXTURE_BOOTSTRAP = r"""
if(location.origin!=='http://127.0.0.1:5291'||!location.pathname.startsWith('/review/'))throw Error('FIXTURE_ORIGIN_REQUIRED');
const NativeDate=Date, binding=Object.freeze(FIXTURE_BINDING), clock={offset:0};
class FixtureDate extends NativeDate { constructor(...args){super(...(args.length?args:[binding.clock_ms+clock.offset]));} static now(){return binding.clock_ms+clock.offset;} }
window.Date=FixtureDate;
window.__northstarFixture={binding,clock,wallNow:()=>new NativeDate().toISOString(),responses:[]};
const nativeFetch=window.fetch.bind(window);
window.fetch=async(...args)=>{
 const response=await nativeFetch(...args);
 if(new URL(String(args[0]),location.href).pathname==='/truth-spine/full-session'){
  const bytes=await response.clone().arrayBuffer();
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
  const row={sequence:window.__northstarFixture.responses.length+1,sha256:hash,status:response.status,at:new NativeDate().toISOString()};
  window.__northstarFixture.responses.push(row);
  if(hash!==binding.fixture_sha256)throw Error('FIXTURE_RESPONSE_CHANGED');
 }
 return response;
};
window.__northstarErrors=[];
const nativeConsoleError=console.error.bind(console);
console.error=(...args)=>{window.__northstarErrors.push('CONSOLE_ERROR:'+args.map(String).join(' ').slice(0,500));nativeConsoleError(...args);};
addEventListener('error',e=>window.__northstarErrors.push(String(e.message)));
addEventListener('unhandledrejection',()=>window.__northstarErrors.push('UNHANDLED_REJECTION'));
"""


CAPTURE_IDENTITY = r"""
function displayedIdentity() {
 const status=document.querySelector('.northstar-session-status');
 if(!status||!window.__northstarFixture)throw Error('CAPTURE_BINDING_UNAVAILABLE');
 const fields=Object.fromEntries([...status.querySelectorAll(':scope > dl > div')].map(e=>[e.querySelector('dt').textContent,e.querySelector('dd').textContent]));
 // Read the COMMITTED context supplying this DOM; never assign React state,
 // DOM identity attributes or a harness-only projection to manufacture a match.
 const key=Object.keys(status).find(k=>k.startsWith('__reactFiber$'));
 let fiber=status[key],state=null;
 while(fiber?.return)fiber=fiber.return;
 const pending=[fiber?.stateNode?.current];
 while(pending.length){fiber=pending.pop();if(!fiber)continue;const value=fiber.memoizedProps?.value;if(value&&'view' in value&&'status' in value){if(state)throw Error('MULTIPLE_PROJECTION_OWNERS');state=value;}if(fiber.child)pending.push(fiber.child);if(fiber.sibling)pending.push(fiber.sibling);}
 if(!state)throw Error('DISPLAYED_CONTEXT_UNAVAILABLE');
 const fixture=window.__northstarFixture,expected=fixture.binding,v=state.view;
 if(v&&(fields['Source generation']!==v.source_generation||fields['Source cycle']!==v.source_cycle||fields['Projection time']!==v.published_at
     ||v.source_generation!==expected.generation||v.source_cycle!==expected.source_cycle||v.factory?.content_hash!==expected.projection_content_hash||v.published_at!==expected.generated_at))throw Error('DISPLAYED_PROJECTION_BINDING_MISMATCH');
 if(!v&&fields['Source generation']!=='UNAVAILABLE')throw Error('UNAVAILABLE_IDENTITY_MISMATCH');
 return {binding:{generation:v?.source_generation??null,projection_content_hash:v?.factory?.content_hash??null,source_cycle:v?.source_cycle??null,generated_at:v?.published_at??null,status:state.status,fixture_sha256:expected.fixture_sha256},polling_sequence:fixture.responses.length,last_response:fixture.responses.at(-1),wall_time:fixture.wallNow(),fixture_time:new Date().toISOString()};
}
"""


TEXT_GEOMETRY = r"""
function viewportBox(r) { return {space:'viewport-css-px',left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}; }
function outside(rect, box, x, y) {
  if(rect.space!=='viewport-css-px'||box.space!=='viewport-css-px')throw Error('COORDINATE_SPACE_MISMATCH');
  return (x && (rect.left < box.left-2 || rect.right > box.right+2)) ||
    (y && (rect.top < box.top-2 || rect.bottom > box.bottom+2));
}
function requiredText(root) {
  const rect = viewportBox;
  const result = {text:[],clipped:[],decorative:[],overlaps:[]};
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for(let node=walker.nextNode();node;node=walker.nextNode()) {
    if(!node.textContent.trim()) continue;
    const parent=node.parentElement;
    if(parent.closest('script,style,[hidden],[inert]')) continue;
    if(parent.closest('[aria-hidden="true"]')) { result.decorative.push({text:node.textContent.trim(),rect:rect(parent.getBoundingClientRect())}); continue; }
    let hidden=false;
    for(let e=parent;e;e=e.parentElement) {
      const s=getComputedStyle(e);
      if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse') hidden=true;
      if(e.tagName==='DETAILS'&&!e.open&&!e.querySelector('summary')?.contains(parent)) hidden=true;
    }
    if(hidden) continue;
    const range=document.createRange(); range.selectNodeContents(node);
    const boxes=[...range.getClientRects()].filter(r=>r.width&&r.height).map(rect);
    const clips=[];let clipCheckBoxes=boxes;
    for(let e=parent;e&&e!==document.body&&e!==document.documentElement;e=e.parentElement) {
      const s=getComputedStyle(e), b=viewportBox(e.getBoundingClientRect());
      const x=['hidden','clip'].includes(s.overflowX), y=['hidden','clip'].includes(s.overflowY);
      if((x||y)&&clipCheckBoxes.some(r=>outside(r,b,x,y))) clips.push({tag:e.tagName,className:e.className,overflowX:s.overflowX,overflowY:s.overflowY,rect:rect(b)});
      const sx=['auto','scroll'].includes(s.overflowX),sy=['auto','scroll'].includes(s.overflowY);
      if(sx||sy)clipCheckBoxes=clipCheckBoxes.map(r=>({...r,left:sx?Math.max(r.left,b.left):r.left,right:sx?Math.min(r.right,b.right):r.right,top:sy?Math.max(r.top,b.top):r.top,bottom:sy?Math.min(r.bottom,b.bottom):r.bottom})).filter(r=>r.right>r.left&&r.bottom>r.top);
    }
    // A scrollport deliberately hides offscreen rows until scrolled. Preserve
    // every full range above, but compare visible paint for overlap: offscreen
    // rows do not paint over the fixed header. Clipping failures are unchanged.
    let paint=boxes.map(r=>({...r}));
    for(let e=parent;e&&e!==document.body&&e!==document.documentElement;e=e.parentElement){
      const s=getComputedStyle(e),b=e.getBoundingClientRect();
      const x=['auto','scroll'].includes(s.overflowX),y=['auto','scroll'].includes(s.overflowY);
      if(x||y)paint=paint.map(r=>({...r,left:x?Math.max(r.left,b.left):r.left,right:x?Math.min(r.right,b.right):r.right,top:y?Math.max(r.top,b.top):r.top,bottom:y?Math.min(r.bottom,b.bottom):r.bottom})).filter(r=>r.right>r.left&&r.bottom>r.top);
    }
    const item={text:node.textContent.trim(),tag:parent.tagName,className:parent.className,rects:boxes,paintRects:paint,clips};
    result.text.push(item); if(clips.length) result.clipped.push(item);
  }
  for(let i=0;i<result.text.length;i++)for(let j=i+1;j<result.text.length;j++) {
    const a=result.text[i], b=result.text[j];
    if(a.paintRects.some(x=>b.paintRects.some(y=>Math.min(x.right,y.right)-Math.max(x.left,y.left)>2&&Math.min(x.bottom,y.bottom)-Math.max(x.top,y.top)>2)))
      result.overlaps.push([a.text,b.text]);
  }
  return result;
}
"""


DECORATION_GEOMETRY = r"""
function decorationSafety(root) {
  const violations=[], layers=[];
  for(const building of root.querySelectorAll('.auction-building')) {
    const scene=building.querySelector(':scope > .northstar-service-decoration');
    const floors=[...building.querySelectorAll(':scope > .auction-level')];
    if(!scene||!floors.length) { violations.push('MISSING_LOCAL_LAYERS'); continue; }
    const style=getComputedStyle(scene), level=Number(style.zIndex);
    if(getComputedStyle(building).isolation!=='isolate'||scene.getAttribute('aria-hidden')!=='true'
       ||style.position!=='absolute'||!Number.isFinite(level)) violations.push('UNBOUND_DECORATION_CONTEXT');
    for(const e of [scene,...scene.querySelectorAll('*')])
      if(getComputedStyle(e).pointerEvents!=='none')violations.push('DECORATION_INTERCEPTS_POINTER');
    for(const spine of building.querySelectorAll('.auction-evidence-spine')) {
      if(!scene.contains(spine))violations.push('EVIDENCE_SPINE_ESCAPED_LAYER');
      layers.push({kind:'evidence-spine',rect:spine.getBoundingClientRect().toJSON(),z:getComputedStyle(spine).zIndex,
        pointerEvents:getComputedStyle(spine).pointerEvents,containingBlock:spine.offsetParent?.className,
        before:getComputedStyle(spine,'::before').content,after:getComputedStyle(spine,'::after').content});
    }
    for(const floor of floors) {
      const s=getComputedStyle(floor), z=Number(s.zIndex);
      if(s.position!=='relative'||s.isolation!=='isolate'||!Number.isFinite(z)||z<=level)
        violations.push('DECORATION_ABOVE_CONTENT');
      layers.push({decorationZ:style.zIndex,contentZ:s.zIndex,decoration:scene.getBoundingClientRect().toJSON(),content:floor.getBoundingClientRect().toJSON()});
    }
  }
  return {violations,layers};
}
"""


DIALOG_GEOMETRY = r"""
function nativeCardTabProof(events,station,shift) {
 const key=events.findIndex(e=>e.type==='keydown'&&e.key==='Tab'&&e.trusted&&e.shift===shift&&!e.alt&&!e.ctrl&&!e.meta&&!e.prevented);
 if(key<0)return false;
 const tail=events.slice(key+1),focus=tail.findIndex(e=>e.type==='focusin'&&e.trusted&&e.target===station);
 return focus>=0&&!tail.slice(0,focus+1).some(e=>e.type==='programmatic-focus');
}
function headingLineOverlaps(lines) {
 const failures=[];
 for(let i=0;i<lines.length;i++)for(let j=i+1;j<lines.length;j++){
  const a=lines[i],b=lines[j];
  if(Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)&&Math.min(a.right,b.right)>Math.max(a.left,b.left))failures.push([i,j]);
 }
 return failures;
}
function headingTypography(root) {
 return [...root.querySelectorAll('h1,h2,h3,h4')].filter(e=>e.getClientRects().length).map(e=>{
  const s=getComputedStyle(e),ranges=[],groups=new Map(),w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);
  for(let n=w.nextNode();n;n=w.nextNode())if(n.textContent.trim()){
   const r=document.createRange();r.selectNodeContents(n);const boxes=[...r.getClientRects()].filter(b=>b.width&&b.height).map(viewportBox);ranges.push({text:n.textContent,boxes});
   for(const b of boxes){const key=JSON.stringify([b.top,b.bottom]),old=groups.get(key);groups.set(key,old?{...old,left:Math.min(old.left,b.left),right:Math.max(old.right,b.right)}:{...b});}
  }
  const lines=[...groups.values()];
  const adjacent=x=>x?{tag:x.tagName,text:x.textContent,rect:viewportBox(x.getBoundingClientRect())}:null;
  return {tag:e.tagName,text:e.textContent,rect:viewportBox(e.getBoundingClientRect()),ranges,lines,lineOverlaps:headingLineOverlaps(lines),overlapClassification:'CONSERVATIVE_RANGE_BOX_INTERSECTION_NOT_GLYPH_PROOF',fonts:document.fonts.status,
   style:Object.fromEntries(['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','marginTop','marginRight','marginBottom','marginLeft','paddingTop','paddingRight','paddingBottom','paddingLeft','width','minWidth','maxWidth','height','minHeight','maxHeight','transform','position','overflowX','overflowY','writingMode','whiteSpace','textOverflow'].map(k=>[k,s[k]])),
   ancestors:[...function*(p){for(;p&&root.contains(p);p=p.parentElement)yield p;}(e.parentElement)].map(p=>({tag:p.tagName,className:p.className,rect:viewportBox(p.getBoundingClientRect()),fontSize:getComputedStyle(p).fontSize,lineHeight:getComputedStyle(p).lineHeight,transform:getComputedStyle(p).transform})),
   previous:adjacent(e.previousElementSibling),next:adjacent(e.nextElementSibling)};
 });
}
function focusFailures(f) {
 const failures=[];
 if(!f.active||!f.visible||!f.name)failures.push('FOCUS_NOT_VISIBLE');
 const alternative=(f.alternativeIndicators||[]).some(i=>['box-shadow','border','background'].includes(i.kind)&&i.changedFromUnfocused&&i.width>=2&&i.contrast>=3&&i.geometryVerified);
 if((f.outlineStyle!=='solid'||f.outlineWidth<2)&&!alternative||f.opacity!==1)failures.push('FOCUS_INDICATOR_MISSING');
 if(f.clips.length)failures.push('FOCUS_INDICATOR_CLIPPED');
 if(f.covered.length)failures.push('FOCUS_INDICATOR_COVERED');
 if((f.contrast===null||f.contrast<3)&&!alternative)failures.push('FOCUS_CONTRAST_UNPROVEN');
 return failures;
}
function focusMeasurement(root) {
 const e=document.activeElement,s=getComputedStyle(e),r=viewportBox(e.getBoundingClientRect()),width=parseFloat(s.outlineWidth)||0,offset=parseFloat(s.outlineOffset)||0;
 const baseline=window.__northstarUnfocusedStyles?.get(e),alternativeIndicators=[];
 const color=c=>{const v=c?.match(/[\d.]+/g)?.map(Number);return v?.length===3?v:null;};
 const lum=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
 const ratio=(a,b)=>a&&b?(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05):null;
 const shadow=s.boxShadow.match(/^(rgb\([^)]+\)) 0px 0px 0px ([\d.]+)px$/);
 let alternativePad=0;
 if(baseline){
   const adjacent=color(baseline.adjacent),base=color(baseline.backgroundColor);
   const borderWidth=Math.min(...['Top','Right','Bottom','Left'].map(side=>parseFloat(s['border'+side+'Width'])||0));
   const borderUniform=['Top','Right','Bottom','Left'].every(side=>s['border'+side+'Style']==='solid'&&s['border'+side+'Color']===s.borderTopColor);
   alternativeIndicators.push({kind:'border',width:borderWidth,changedFromUnfocused:baseline.border!==s.border,contrast:ratio(color(s.borderTopColor),adjacent),geometryVerified:borderUniform});
   alternativeIndicators.push({kind:'background',width:Math.min(r.width,r.height),changedFromUnfocused:baseline.backgroundColor!==s.backgroundColor,contrast:ratio(color(s.backgroundColor),base),geometryVerified:s.backgroundImage==='none'&&!!base});
   if(shadow){alternativePad=Number(shadow[2]);alternativeIndicators.push({kind:'box-shadow',width:alternativePad,changedFromUnfocused:baseline.boxShadow!==s.boxShadow,contrast:ratio(color(shadow[1]),adjacent),geometryVerified:s.filter==='none'});}
 }
 const pad=s.outlineStyle==='solid'&&width>=2?width+offset:alternativePad;
 const ring={space:'viewport-css-px',left:r.left-pad,right:r.right+pad,top:r.top-pad,bottom:r.bottom+pad};
 const bands=[{...ring,bottom:r.top-offset},{...ring,top:r.bottom+offset},{...ring,right:r.left-offset,top:r.top-offset,bottom:r.bottom+offset},{...ring,left:r.right+offset,top:r.top-offset,bottom:r.bottom+offset}];
 const clips=[],covered=[],ancestors=[];
 const exceeds=(a,b,x=true,y=true)=>(x&&(a.left<b.left||a.right>b.right))||(y&&(a.top<b.top||a.bottom>b.bottom));
 if(exceeds(ring,{left:0,top:0,right:innerWidth,bottom:innerHeight}))clips.push('VIEWPORT');
 let background=null,backgroundElement=null;const backgroundSamples=[];let unknownBackground=false;
 for(let p=e.parentElement;p;p=p.parentElement){const st=getComputedStyle(p),b=p.getBoundingClientRect(),box={left:b.left+p.clientLeft,top:b.top+p.clientTop,right:b.left+p.clientLeft+p.clientWidth,bottom:b.top+p.clientTop+p.clientHeight};
  ancestors.push({tag:p.tagName,className:p.className,box,overflowX:st.overflowX,overflowY:st.overflowY,background:st.backgroundColor,backgroundImage:st.backgroundImage});
  const colors=[st.backgroundColor,...st.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map(c=>typeof c==='string'?c:c[0]);
  for(const color of colors){const v=color.match(/[\d.]+/g)?.map(Number);if(v?.length===3||v?.length===4&&v[3]>0)backgroundSamples.push(v.slice(0,3));}
  if(st.backgroundImage!=='none'&&!st.backgroundImage.includes('gradient('))unknownBackground=true;
  if(exceeds(ring,box,['hidden','clip','auto','scroll'].includes(st.overflowX),['hidden','clip','auto','scroll'].includes(st.overflowY)))clips.push({className:p.className,box});
  if(!background&&st.backgroundColor.startsWith('rgb(')&&st.backgroundImage==='none'){background=st.backgroundColor;backgroundElement=p.className;}
 }
 const rgb=c=>{const a=c?.match(/[\d.]+/g)?.map(Number);return a?.length===3?a:null;};
 const luminance=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
 // An opaque zero-blur outer shadow that extends past the entire outline is
 // its actual adjacent backing, rather than a translucent ancestor gradient.
 // Only this directly measured geometric contract can replace ancestor bounds.
 const backing=s.boxShadow.match(/^(rgb\([^)]+\)) 0px 0px 0px ([\d.]+)px(?:,|$)/);
 const solidBacking=backing&&Number(backing[2])>=pad+1&&s.filter==='none'&&Number(s.opacity)===1?rgb(backing[1]):null;
 const contrastSamples=solidBacking?[solidBacking]:backgroundSamples;
 const fg=rgb(s.outlineColor),contrast=fg&&contrastSamples.length&&(solidBacking||!unknownBackground)?Math.min(...contrastSamples.map(bg=>(Math.max(luminance(fg),luminance(bg))+.05)/(Math.min(luminance(fg),luminance(bg))+.05))):null;
 for(const band of bands){const x=(band.left+band.right)/2,y=(band.top+band.bottom)/2,hit=document.elementFromPoint(x,y);if(hit&&!hit.contains(e)&&!e.contains(hit))covered.push({tag:hit.tagName,className:hit.className,point:[x,y]});}
 const header=root.querySelector('.northstar-dialog-header');if(header&&!header.contains(e)){const h=header.getBoundingClientRect();if(bands.some(b=>Math.min(b.right,h.right)>Math.max(b.left,h.left)&&Math.min(b.bottom,h.bottom)>Math.max(b.top,h.top)))covered.push('FIXED_HEADER');}
 const decoration=obstructionCensus(root).violations.filter(v=>v.kind==='focus');covered.push(...decoration);
 const data={active:root.contains(e),tag:e.tagName,id:e.id,name:e.getAttribute('aria-label')||e.textContent.trim(),role:e.getAttribute('role')||({BUTTON:'button',SUMMARY:'button',A:'link'}[e.tagName]??e.tagName.toLowerCase()),rect:r,ring,bands,outline:s.outline,outlineStyle:s.outlineStyle,outlineWidth:width,outlineOffset:offset,outlineColor:s.outlineColor,boxShadow:s.boxShadow,opacity:Number(s.opacity),focusVisible:e.matches(':focus-visible'),visible:!!r.width&&!!r.height&&s.visibility==='visible'&&s.display!=='none',background,backgroundElement,backgroundSamples,unknownBackground,solidBacking,contrast,ancestors,clips,covered,alternativeIndicators,unfocusedBaseline:baseline||null};
 return {...data,failures:focusFailures(data)};
}
function dialogFailures(d) {
 const failures=[],view={space:'viewport-css-px',left:8,top:8,right:d.viewport[0]-8,bottom:d.viewport[1]-8};
 for(const [name,e] of [['surface',d.surface],['header',d.header],['close',d.close]])if(!e||outside(e.rect,view,true,true))failures.push(name+'_OUTSIDE_VIEWPORT');
 if(!d.closeHit)failures.push('CLOSE_NOT_REACHABLE');
 if(d.role!=='dialog'||d.ariaModal!=='true'||!d.name)failures.push('DIALOG_SEMANTICS_INVALID');
 if(!d.active.contained)failures.push('FOCUS_ESCAPED');
 if(d.body.scroll[2]>d.body.scroll[4]+1||d.surface.scroll[2]>d.surface.scroll[4]+1)failures.push('HORIZONTAL_DIALOG_OVERFLOW');
 if(d.document.bodyPosition!=='fixed'||d.document.htmlOverflow!=='hidden')failures.push('BACKGROUND_NOT_LOCKED');
 if(d.required.clipped.length)failures.push('REQUIRED_TEXT_CLIPPED');
 if(d.required.overlaps.length)failures.push('REQUIRED_TEXT_OVERLAP');
 if(d.typography?.some(h=>h.lineOverlaps.length))failures.push('HEADING_LINE_OVERLAP');
 return failures;
}
function dialogMeasurement() {
 const modal=document.querySelector('.auction-room-modal'),surface=modal?.querySelector(':scope > section');
 if(!surface)throw Error('DIALOG_MISSING');
 const body=surface.querySelector('.northstar-dialog-body')||surface,header=surface.querySelector('.northstar-dialog-header')||surface.querySelector('.auction-interior-heading'),close=surface.querySelector('.auction-close');
 const measure=e=>{if(!e)return null;const s=getComputedStyle(e);return {rect:viewportBox(e.getBoundingClientRect()),width:s.width,height:s.height,minWidth:s.minWidth,maxWidth:s.maxWidth,minHeight:s.minHeight,maxHeight:s.maxHeight,boxSizing:s.boxSizing,overflowX:s.overflowX,overflowY:s.overflowY,position:s.position,zIndex:s.zIndex,padding:[s.paddingTop,s.paddingRight,s.paddingBottom,s.paddingLeft],scroll:[e.scrollLeft,e.scrollTop,e.scrollWidth,e.scrollHeight,e.clientWidth,e.clientHeight]};};
 const r=close.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
 const controls=[...modal.querySelectorAll('button,a[href],summary,input,select,textarea,[tabindex]')].filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length&&!e.closest('[hidden],[inert]')&&![...e.closest('details:not([open])')?.querySelectorAll(':scope > :not(summary)')||[]].some(x=>x.contains(e)));
 return {typography:headingTypography(surface),viewport:[innerWidth,innerHeight],outer:[outerWidth,outerHeight],dpr:devicePixelRatio,at:window.__northstarFixture?.wallNow(),url:location.href,backdrop:measure(modal),surface:measure(surface),header:measure(header),body:measure(body),footer:measure(surface.querySelector('footer')),close:measure(close),closeHit:!!hit&&close.contains(hit),closeName:close.getAttribute('aria-label'),role:modal.getAttribute('role'),ariaModal:modal.getAttribute('aria-modal'),name:document.getElementById(modal.getAttribute('aria-labelledby'))?.textContent,active:{tag:document.activeElement.tagName,id:document.activeElement.id,text:document.activeElement.textContent.slice(0,100),contained:modal.contains(document.activeElement),outline:getComputedStyle(document.activeElement).outline},focusOrder:controls.map(e=>({tag:e.tagName,text:e.getAttribute('aria-label')||e.textContent.slice(0,120),rect:viewportBox(e.getBoundingClientRect())})),required:requiredText(surface),document:{scroll:[scrollX,scrollY],bodyPosition:getComputedStyle(document.body).position,bodyOverflow:getComputedStyle(document.body).overflow,htmlOverflow:getComputedStyle(document.documentElement).overflow,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth}};
}
"""

OBSTRUCTION_GEOMETRY = r"""
function paintRelation(a,b) {
 let i=0;while(i<a.length&&i<b.length&&a[i].key===b[i].key)i++;
 if(i<a.length&&i<b.length)return a[i].z<b[i].z?'BELOW':a[i].z>b[i].z?'ABOVE':a[i].order<b[i].order?'BELOW':'ABOVE';
 if(i<a.length)return a[i].z<0?'BELOW':'ABOVE';
 if(i<b.length)return b[i].z>0?'BELOW':'ABOVE';
 return 'SAME_CONTEXT_UNPROVEN';
}
function obstructionCensus(root) {
 const all=[root,...root.querySelectorAll('*')],index=new Map(all.map((e,i)=>[e,i]));
 const style=new Map(),rect=new Map(),contexts=new Map();
 const css=e=>{if(!style.has(e))style.set(e,getComputedStyle(e));return style.get(e);};
 const label=e=>e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(typeof e.className==='string'?'.'+e.className.trim().replace(/\s+/g,'.'):'');
 const box=e=>{if(!rect.has(e))rect.set(e,viewportBox(e.getBoundingClientRect()));return rect.get(e);};
 const live=e=>{for(let p=e;p;p=p.parentElement){const s=css(p);if(p.hidden||p.inert||s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse')return false;if(p.tagName==='DETAILS'&&!p.open&&!p.querySelector('summary')?.contains(e))return false;}return box(e).width>0&&box(e).height>0;};
 const creates=(s,e)=>s.isolation==='isolate'||s.transform!=='none'||s.filter!=='none'||Number(s.opacity)<1||s.mixBlendMode!=='normal'||['fixed','sticky'].includes(s.position)||(s.zIndex!=='auto'&&(s.position!=='static'||['flex','grid','inline-flex','inline-grid'].includes(css(e.parentElement||root).display)));
 const chain=e=>{if(contexts.has(e))return contexts.get(e);const a=[];for(let p=e;p;p=p.parentElement)if(p===root||creates(css(p),p))a.unshift({key:label(p)+':'+index.get(p),z:Number(css(p).zIndex)||0,order:index.get(p)??-1});contexts.set(e,a);return a;};
 const overlap=(a,b)=>Math.min(a.right,b.right)>Math.max(a.left,b.left)&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top);
 const clip=(r,e)=>{let b={...r};for(let p=e;p;p=p.parentElement){const s=css(p),v=box(p);if(['hidden','clip','auto','scroll'].includes(s.overflowX)){b.left=Math.max(b.left,v.left);b.right=Math.min(b.right,v.right);}if(['hidden','clip','auto','scroll'].includes(s.overflowY)){b.top=Math.max(b.top,v.top);b.bottom=Math.min(b.bottom,v.bottom);}}b.width=Math.max(0,b.right-b.left);b.height=Math.max(0,b.bottom-b.top);return b;};
 const targets=[],layers=[],violations=[],backgrounds=[],positionedContent=[];
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
 for(let n=walker.nextNode();n;n=walker.nextNode())if(n.textContent.trim()&&live(n.parentElement)&&!n.parentElement.closest('[aria-hidden=true],script,style,svg')){
  const range=document.createRange();range.selectNodeContents(n);
  for(const r of range.getClientRects())if(r.width&&r.height){const visible=clip(viewportBox(r),n.parentElement);if(visible.width&&visible.height)targets.push({kind:'text',element:n.parentElement,label:n.textContent.trim(),rect:visible});}
 }
 for(const e of all.filter(e=>e.matches('button,a[href],summary,input,select,textarea,[tabindex]')&&live(e)&&!e.closest('[aria-hidden=true]'))){
  const visible=clip(box(e),e.parentElement);if(visible.width&&visible.height)targets.push({kind:'control',element:e,label:e.getAttribute('aria-label')||e.textContent.trim(),rect:visible});
  if(e===document.activeElement&&css(e).outlineStyle!=='none'){
   const r=box(e),w=parseFloat(css(e).outlineWidth)||0,o=parseFloat(css(e).outlineOffset)||0;
   for(const b of [{left:r.left-o-w,right:r.right+o+w,top:r.top-o-w,bottom:r.top-o},{left:r.left-o-w,right:r.right+o+w,top:r.bottom+o,bottom:r.bottom+o+w},{left:r.left-o-w,right:r.left-o,top:r.top-o,bottom:r.bottom+o},{left:r.right+o,right:r.right+o+w,top:r.top-o,bottom:r.bottom+o}])targets.push({kind:'focus',element:e,label:'Focus: '+(e.getAttribute('aria-label')||e.textContent.trim()),rect:{...b,width:b.right-b.left,height:b.bottom-b.top}});
  }
 }
 const painted=s=>s.backgroundImage!=='none'||!['rgba(0, 0, 0, 0)','transparent'].includes(s.backgroundColor)||parseFloat(s.borderTopWidth)>0||parseFloat(s.borderLeftWidth)>0||s.boxShadow!=='none';
 for(const e of all){if(!live(e))continue;const s=css(e),semantic=!!e.closest('[aria-hidden=true]');
  if(painted(s))backgrounds.push({selector:label(e),rect:box(e),background:s.backgroundImage,color:s.backgroundColor,shadow:s.boxShadow,classification:'OWN_BACKGROUND_NOT_A_FOREGROUND_LAYER'});
  if((['absolute','fixed','sticky'].includes(s.position)||s.transform!=='none')&&!semantic)positionedContent.push({selector:label(e),rect:box(e),position:s.position,transform:s.transform,stack:chain(e)});
  const candidates=[];
  if(semantic&&(painted(s)||e.matches('img,svg')||[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())))candidates.push({pseudo:null,style:s,rect:box(e),stack:chain(e),geometry:'ELEMENT_RECT',clipParent:e.parentElement});
  for(const pseudo of ['::before','::after']){
   const p=getComputedStyle(e,pseudo);if(['none','normal'].includes(p.content)||p.display==='none'||p.visibility==='hidden')continue;
   let cb=e;while(cb!==root&&css(cb).position==='static'&&css(cb).transform==='none')cb=cb.parentElement;
   const c=box(cb),n=v=>v==='auto'?null:Number.parseFloat(v),left=n(p.left),top=n(p.top),right=n(p.right),bottom=n(p.bottom);
   const extraX=p.boxSizing==='border-box'?0:(parseFloat(p.borderLeftWidth)||0)+(parseFloat(p.borderRightWidth)||0)+(parseFloat(p.paddingLeft)||0)+(parseFloat(p.paddingRight)||0);
   const extraY=p.boxSizing==='border-box'?0:(parseFloat(p.borderTopWidth)||0)+(parseFloat(p.borderBottomWidth)||0)+(parseFloat(p.paddingTop)||0)+(parseFloat(p.paddingBottom)||0);
   const w=n(p.width)??(left!==null&&right!==null?cb.clientWidth-left-right:null),h=n(p.height)??(top!==null&&bottom!==null?cb.clientHeight-top-bottom:null);
   let r=box(e),geometry='CONSERVATIVE_HOST_RECT';
   if(p.position==='absolute'&&p.transform==='none'&&w!==null&&h!==null&&(left!==null||right!==null)&&(top!==null||bottom!==null)){
    const width=w+extraX,height=h+extraY,x=c.left+(parseFloat(css(cb).borderLeftWidth)||0)+(left??cb.clientWidth-right-width),y=c.top+(parseFloat(css(cb).borderTopWidth)||0)+(top??cb.clientHeight-bottom-height);
    r={left:x,right:x+width,top:y,bottom:y+height,width,height};geometry='RESOLVED_ABSOLUTE_PSEUDO';
   }
   const stack=[...chain(e)];if(creates(p,e))stack.push({key:label(e)+pseudo,z:Number(p.zIndex)||0,order:pseudo==='::before'?-1:all.length+1});
   candidates.push({pseudo,style:p,rect:r,stack,geometry,clipParent:e});
  }
  for(const d of candidates){const s=d.style,r=clip(d.rect,d.clipParent),intersections=[];
   const entry={selector:label(e)+(d.pseudo||''),destination:document.querySelector('.auction-nav .is-active')?.textContent||'unknown',pseudo:d.pseudo,semanticDecorative:semantic||!!d.pseudo,position:s.position,containingBlock:label(e.offsetParent||e.parentElement||root),z:s.zIndex,transform:s.transform,pointerEvents:s.pointerEvents,content:s.content,rect:d.rect,paintRect:r,geometry:d.geometry,stack:d.stack,background:s.backgroundImage,shadow:s.boxShadow,breakpoint:innerWidth<=700?'narrow':innerWidth<=1100?'medium':'desktop',intersections};
   for(const t of targets){if(!overlap(r,t.rect))continue;
    if(!d.pseudo&&e.contains(t.element))continue;
    let relation=paintRelation(d.stack,chain(t.element));
    // A control's own background may intersect its hit box, but never its
    // separately measured text or outside focus outline. Pointer rule still applies.
    const ownControl=t.kind==='control'&&t.element.contains(e);
    if(ownControl)relation='OWN_CONTROL_BACKGROUND';
    const x=(Math.max(r.left,t.rect.left)+Math.min(r.right,t.rect.right))/2,y=(Math.max(r.top,t.rect.top)+Math.min(r.bottom,t.rect.bottom))/2;
    const hitElement=x>=0&&x<innerWidth&&y>=0&&y<innerHeight?document.elementFromPoint(x,y):null;
    const pointer=s.pointerEvents!=='none'&&t.kind==='control'&&!ownControl&&!!hitElement&&(hitElement===e||e.contains(hitElement))&&!t.element.contains(hitElement);
    const bad=pointer||!['BELOW','OWN_CONTROL_BACKGROUND'].includes(relation);
    const hit={kind:t.kind,target:t.label.slice(0,160),relation,pointerInterception:pointer,hitTarget:hitElement?label(hitElement):null,rect:t.rect,classification:bad?'OBSTRUCTION':'HARMLESS_UNDERLAY'};intersections.push(hit);
    if(bad)violations.push({selector:entry.selector,...hit});
   }
   if(s.pointerEvents!=='none')violations.push({selector:entry.selector,classification:'DECORATION_POINTER_EVENTS_ENABLED'});
   if(!d.pseudo&&e.matches('button,a[href],input,select,textarea,[tabindex]'))violations.push({selector:entry.selector,classification:'DECORATION_KEYBOARD_TARGET'});
   layers.push(entry);
  }
 }
 const hidden=all.filter(e=>!live(e)).map(label);
 return {coordinateSpace:'viewport-css-px',viewport:[innerWidth,innerHeight],scroll:[scrollX,scrollY],layers,backgrounds,positionedContent,hiddenInactive:hidden,violations};
}
"""


SETTLEMENT_GEOMETRY = r"""
// PORTABLE_CORE_BEGIN: plain records and explicitly injected dependencies only.
function settleSignature(sample) {
  if(sample.coordinateSpace!=='viewport-css-px')throw Error('COORDINATE_SPACE_MISMATCH');
  return JSON.stringify([sample.url,sample.destination,sample.viewport,sample.scroll,sample.elements,sample.text]);
}
function stableGeometryPair(a,b) {
  return a.fonts==='loaded'&&b.fonts==='loaded'&&a.pendingAnimations===0&&b.pendingAnimations===0&&settleSignature(a)===settleSignature(b);
}
function createSettlementCore(input) {
  const config=JSON.parse(JSON.stringify(input));
  const samples=[];let previous=null,matches=0,identity=null,result=null;
  const start=config.start,deadline=start+config.timeoutMs;
  if(!Number.isFinite(start)||!Number.isFinite(deadline)||config.timeoutMs<=0)throw Error('SETTLEMENT_CONFIG_INVALID');
  function finish(ok,reason,failureCategory=null) {
    if(!result)result={ok,reason,failureCategory,coordinateSpace:'viewport-css-px',expectedDestination:config.destination??null,fonts:previous?.fonts??'loading',samples,consecutiveMatches:matches,deadline};
    return JSON.parse(JSON.stringify(result));
  }
  function expire(at) {
    if(result)return finish();
    if(at<deadline)return null;
    return finish(false,'LAYOUT_SETTLEMENT_TIMEOUT',samples.length===0?'ZERO_FRAMES':samples.length===1?'ONE_FRAME':matches===0?'CHANGING_GEOMETRY_OR_PREREQUISITES':'INSUFFICIENT_STABLE_FRAMES');
  }
  function accept(record) {
    if(result)return finish();
    const row=JSON.parse(JSON.stringify(record));
    if(!Number.isFinite(row.at)||row.at<start)return finish(false,'TELEMETRY_INVALID','CLOCK_INVALID');
    const expired=expire(row.at);if(expired)return expired;
    const binding=JSON.stringify(row.identity??null);
    if(identity!==null&&identity!==binding)return finish(false,'SETTLEMENT_IDENTITY_CHANGED','IDENTITY_CHANGED');
    identity=binding;
    if(row.prerequisites&&Object.values(row.prerequisites).some(v=>v!==true))return finish(false,'SETTLEMENT_PREREQUISITE_FAILED','PREREQUISITE_FAILED');
    const sample={...row.geometry,at:row.at,signature:settleSignature(row.geometry)};
    samples.push(sample);
    const destinationMatches=!config.destination||sample.destination===config.destination;
    const scrollMatches=!config.scrollTarget||(sample.scroll[0]===config.scrollTarget[0]&&sample.scroll[1]===config.scrollTarget[1]);
    matches=previous&&destinationMatches&&scrollMatches&&stableGeometryPair(previous,sample)?matches+1:0;
    previous=sample;
    // Preserve the accepted, stronger contract: two matching adjacent pairs.
    if(matches>=2)return finish(true,'STABLE_TWO_CONSECUTIVE_FRAMES');
    return null;
  }
  return {accept,expire,fail:category=>finish(false,'SETTLEMENT_ADAPTER_FAILED',category),deadline};
}
function runSettlement(input,deps) {
  return new Promise(resolve=>{
    let core,state='RUNNING',start=0,lastNow=0,lastRecord=null;
    const frames=new Set(),timers=new Set();
    const errorType=error=>['Error','TypeError','RangeError','ReferenceError','SyntaxError'].includes(error?.name)?error.name:'Error';
    const clock=()=>{const value=deps.now();if(!Number.isFinite(value)||value<lastNow)throw new TypeError('CLOCK_INVALID');lastNow=value;return value;};
    const failureEvidence=(stage,error,result)=>({stage,classification:'FAILED_CLOSED',errorType:errorType(error),elapsedMonotonicMs:Math.max(0,lastNow-start),frameCount:result.samples?.length??0,lastValidGeometry:result.samples?.at(-1)??null,identity:lastRecord?.identity??null});
    // One completion guard owns resolution. Cleanup actions execute independently
    // and their rejected promises are consumed before the immutable result exits.
    const finish=(result,stage='settlement',error=null)=>{
      if(state!=='RUNNING'||!result)return;
      state='COMPLETING';
      const value=JSON.parse(JSON.stringify(result));
      if(!value.ok)value.failure=failureEvidence(stage,error,value);
      const cleanups=[];
      for(const [kind,handles,cancel] of [['frame',frames,h=>deps.cancel(h)],['timer',timers,h=>deps.clearTimer(h)]]){
        for(const handle of handles){
          try{cleanups.push(Promise.resolve(cancel(handle)).then(()=>({kind,ok:true}),e=>({kind,ok:false,errorType:errorType(e)})));}
          catch(e){cleanups.push(Promise.resolve({kind,ok:false,errorType:errorType(e)}));}
        }
        handles.clear();
      }
      Promise.all(cleanups).then(cleanup=>{
        value.cleanup=cleanup;
        const broken=cleanup.find(r=>!r.ok);
        if(broken){value.ok=false;value.reason='SETTLEMENT_ADAPTER_FAILED';value.failureCategory='SCHEDULER_CLEANUP_FAILED';value.failure??=failureEvidence('cleanup',{name:broken.errorType},value);}
        state='COMPLETE';resolve(value);
      });
    };
    const failed=(stage,error)=>finish(core?core.fail('ADAPTER_EXCEPTION'):{ok:false,reason:'SETTLEMENT_ADAPTER_FAILED',failureCategory:'ADAPTER_EXCEPTION',samples:[],consecutiveMatches:0},stage,error);
    const retain=(kind,handle)=>{
      if(handle===undefined||handle===null)return;
      const cancel=kind==='frame'?h=>deps.cancel(h):h=>deps.clearTimer(h);
      if(state==='RUNNING')(kind==='frame'?frames:timers).add(handle);
      else {try{Promise.resolve(cancel(handle)).catch(()=>{});}catch{ /* late handle, result already fixed; never reschedule */ }}
    };
    const external=(stage,call,accept)=>{
      if(state!=='RUNNING')return;
      try{
        const value=call();
        if(value&&typeof value.then==='function')Promise.resolve(value).then(accept,e=>failed(stage,e)).catch(e=>failed(stage,e));
        else accept(value);
      }catch(e){failed(stage,e);}
    };
    const schedule=()=>external('frame-scheduler',()=>deps.schedule(tick),handle=>retain('frame',handle));
    const tick=()=>{
      if(state!=='RUNNING')return;
      try{
        const row=deps.telemetry();lastRecord=JSON.parse(JSON.stringify(row));
        const result=core.accept({...lastRecord,at:clock()});
        deps.record?.({stage:'geometry-sample',at:lastNow,result:result?.reason??null});
        if(result)finish(result);else schedule();
      }catch(e){failed('frame-callback',e);}
    };
    try {
      start=clock();core=createSettlementCore({...input,start});
      external('deadline-scheduler',()=>deps.timer(()=>{if(state!=='RUNNING')return;try{finish(core.expire(clock()),'deadline');}catch(e){failed('deadline-callback',e);}},input.timeoutMs),handle=>retain('timer',handle));
      external('readiness',()=>deps.ready(),()=>schedule());
    } catch(e) {failed('initialization',e);}
  });
}
// PORTABLE_CORE_END
function visibleRequiredElement(e) {
  for(let p=e;p;p=p.parentElement){const s=getComputedStyle(p);if(p.hidden||p.inert||s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse')return false;if(p.tagName==='DETAILS'&&!p.open&&!p.querySelector('summary')?.contains(e))return false;}
  return true;
}
function geometryFrame(root) {
  const rect=r=>({left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height});
  const text=[];const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  for(let n=w.nextNode();n;n=w.nextNode())if(n.textContent.trim()&&visibleRequiredElement(n.parentElement)&&!n.parentElement.closest('script,style')){const r=document.createRange();r.selectNodeContents(n);text.push([...r.getClientRects()].map(rect));}
  return {coordinateSpace:'viewport-css-px',url:location.href,destination:document.querySelector('.auction-nav nav .is-active')?.textContent.trim()||null,viewport:[innerWidth,innerHeight,devicePixelRatio,document.documentElement.scrollWidth,document.documentElement.clientWidth],scroll:[scrollX,scrollY,document.scrollingElement.scrollLeft,document.scrollingElement.scrollTop],fonts:document.fonts.status,pendingAnimations:document.getAnimations().filter(a=>a.playState==='running'||a.playState==='pending').length,elements:[root,...root.querySelectorAll('*')].filter(visibleRequiredElement).map(e=>[e.tagName,e.id,e.className,rect(e.getBoundingClientRect()),e.scrollLeft,e.scrollTop,getComputedStyle(e).transform]),text};
}
function geometryTestAdapter(options={}) {
  // Compatibility adapter for the existing injected geometry VM. It uses
  // only that declared geometry/font/scheduler contract, never browser telemetry.
  if(typeof document==='undefined'||typeof requestAnimationFrame!=='function'||typeof setTimeout!=='function')
    throw Error('GEOMETRY_ADAPTER_CAPABILITY_MISSING');
  const root=options.root||document.querySelector('.northstar-full-session');
  if(!root||!visibleRequiredElement(root))throw Error('ACTIVE_DESTINATION_MISSING');
  let clock=0;
  const images=[...root.querySelectorAll('img')];
  return {destination:options.destination??document.querySelector('.auction-nav nav .is-active')?.textContent.trim(),
    now:()=>clock,schedule:fn=>requestAnimationFrame(at=>{clock=at;fn();}),cancel:id=>cancelAnimationFrame(id),
    timer:(fn,ms)=>setTimeout(()=>{clock=ms;fn();},ms),clearTimer:id=>clearTimeout(id),
    ready:()=>Promise.all([document.fonts.ready,...images.map(img=>img.complete?Promise.resolve():new Promise(resolve=>{img.addEventListener('load',resolve,{once:true});img.addEventListener('error',resolve,{once:true});}))]),
    telemetry:()=>({geometry:geometryFrame(root),identity:null})};
}
function browserTelemetryAdapter(options={}) {
  const required=[['window',typeof window!=='undefined'],['document',typeof document!=='undefined'],
    ['performance',typeof performance!=='undefined'&&typeof performance.now==='function'],
    ['frame-scheduler',typeof requestAnimationFrame==='function'&&typeof cancelAnimationFrame==='function'],
    ['timers',typeof setTimeout==='function'&&typeof clearTimeout==='function'],['microtask',typeof queueMicrotask==='function'],
    ['geometry',typeof getComputedStyle==='function'],['capture-identity',typeof displayedIdentity==='function']];
  if(required.some(([,ok])=>!ok))return {ok:false,reason:'BROWSER_CAPABILITY_MISSING',missing:required.filter(([,ok])=>!ok).map(([name])=>name),samples:[],consecutiveMatches:0};
  try {
    if(!document.fonts?.ready||typeof document.hasFocus!=='function'||typeof document.getAnimations!=='function')
      return {ok:false,reason:'BROWSER_CAPABILITY_MISSING',missing:['document-telemetry'],samples:[],consecutiveMatches:0};
    const trace=window.__settlementTrace={events:[],images:[],requests:0,callbacks:0,microtask:false,macrotask:false};
    const mark=(stage,extra={})=>trace.events.push({stage,at:performance.now(),dateNow:Date.now(),visibility:document.visibilityState,hasFocus:document.hasFocus(),scroll:[scrollX,scrollY],...extra});
    mark('capture-requested');
    const root=document.querySelector('.northstar-full-session'),target=document.activeElement;
    if(!root||!target||!visibleRequiredElement(root))throw Error('TARGET_MISSING');
    const rect=e=>{const r=e.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
    const active=()=>({tag:document.activeElement?.tagName??null,id:document.activeElement?.id??null});
    const destination=options.destination??document.querySelector('.auction-nav nav .is-active')?.textContent.trim();
    const initialBinding=displayedIdentity().binding;
    mark('destination-active',{destination});mark('target-located',{...active(),rectangle:rect(target)});
    mark('target-scroll-observed',{rectangle:rect(target)});mark('document-ready',{readyState:document.readyState});mark('visibility-recorded');
    queueMicrotask(()=>{trace.microtask=true;mark('microtask-probe');});
    setTimeout(()=>{trace.macrotask=true;mark('timer-macrotask-probe');},0);
    const images=[...root.querySelectorAll('img')];
    trace.images=images.map((img,i)=>({identity:'image-'+i,complete:img.complete,natural:[img.naturalWidth,img.naturalHeight],
      visible:visibleRequiredElement(img)&&img.getClientRects().length>0,required:!(img.getAttribute('aria-hidden')==='true'||img.alt===''),
      loading:img.loading,sourceClass:img.currentSrc.startsWith(location.origin+'/review/assets/')?'PACKAGED_SAME_ORIGIN_ASSET':img.currentSrc?'OTHER_REDACTED':'EMPTY',elapsed:0}));
    mark('image-inventory-created',{count:images.length});
    let waitPromise=null;
    const deps={now:()=>performance.now(),schedule:fn=>{trace.requests++;mark('frame-request',{counter:trace.requests});return requestAnimationFrame(()=>{trace.callbacks++;mark('frame-callback',{counter:trace.callbacks});fn();});},
      cancel:id=>cancelAnimationFrame(id),timer:(fn,ms)=>setTimeout(fn,ms),clearTimer:id=>clearTimeout(id),record:row=>mark(row.stage,row),
      ready:()=>{
        if(waitPromise)return waitPromise;
        mark('fonts-wait-started');
        const fonts=document.fonts.ready.then(()=>mark('fonts-wait-completed'));
        const waits=images.map((img,i)=>{
          const row=trace.images[i],start=performance.now();mark('image-state',{...row});
          if(img.complete){if(row.required&&row.visible&&!img.naturalWidth)throw Error('REQUIRED_IMAGE_ERROR');return Promise.resolve();}
          mark('image-wait-started',{identity:row.identity});
          return new Promise((resolve,reject)=>{for(const event of ['load','error'])img.addEventListener(event,()=>{
            row.complete=img.complete;row.natural=[img.naturalWidth,img.naturalHeight];row.elapsed=performance.now()-start;row.event=event;
            mark('image-wait-completed',{...row});if(event==='error'&&row.required&&row.visible)reject(Error('REQUIRED_IMAGE_ERROR'));else resolve();
          },{once:true});});
        });
        waitPromise=Promise.all([fonts,...waits]).then(()=>{mark('all-images-wait-completed');mark('animation-state',{pending:document.getAnimations().filter(a=>a.playState==='running'||a.playState==='pending').length});});
        return waitPromise;
      },
      telemetry:()=>{
        const geometry=geometryFrame(root),binding=displayedIdentity().binding;
        const prerequisites={documentReady:document.readyState==='complete',documentVisible:document.visibilityState==='visible',focused:document.hasFocus(),
          targetConnected:target.isConnected,targetVisible:visibleRequiredElement(target)&&rect(target).width>0&&rect(target).height>0,focusUnchanged:document.activeElement===target,
          imagesReady:images.every((img,i)=>img.complete&&(!trace.images[i].required||!trace.images[i].visible||img.naturalWidth>0))};
        mark('telemetry',{rectangle:rect(target),active:active(),modality:window.__modalityEvents?.slice(-4)||[]});
        return JSON.parse(JSON.stringify({geometry,identity:{binding,initialBinding},prerequisites}));
      }};
    return {ok:true,destination,deps,trace,mark};
  } catch {return {ok:false,reason:'BROWSER_ADAPTER_EXCEPTION',samples:[],consecutiveMatches:0};}
}
async function settleNorthstar(options={}) {
  if(options.browser===true) {
    const adapter=browserTelemetryAdapter(options);
    if(!adapter.ok)return adapter;
    const result=await runSettlement({timeoutMs:options.timeoutMs??6000,destination:adapter.destination,scrollTarget:options.scrollTarget},adapter.deps);
    adapter.mark(result.ok?'stable-consecutive-samples':'settlement-finished',{ok:result.ok,reason:result.reason});
    return {...result,trace:adapter.trace};
  }
  try {
    const deps=options.dependencies??geometryTestAdapter(options);
    return await runSettlement({timeoutMs:options.timeoutMs??6000,destination:options.destination??deps.destination,scrollTarget:options.scrollTarget},deps);
  } catch {return {ok:false,reason:'SETTLEMENT_ADAPTER_FAILED',failureCategory:'ADAPTER_EXCEPTION',samples:[],consecutiveMatches:0};}
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnose-gallery', action='store_true')
    parser.add_argument('--diagnose-history', action='store_true')
    parser.add_argument('--diagnose-decoration', action='store_true')
    parser.add_argument('--diagnose-dialogs', action='store_true')
    parser.add_argument('--diagnose-modality', action='store_true')
    parser.add_argument('--diagnose-keyboard-boundary', action='store_true')
    parser.add_argument('--diagnose-settlement', action='store_true')
    parser.add_argument('--diagnose-settlement-async', action='store_true')
    parser.add_argument('--prior-cleanup', type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    output = args.output.absolute()
    cache = source/'FRONT END/node_modules/.cache'
    if not output.is_relative_to(cache) or output.exists() or any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError('NEW_OWNER_ONLY_TEST_OUTPUT_REQUIRED')
    record = verify_review_provenance(args.build_root, source)
    dist = args.build_root/'frontend/dist'
    files = {}
    for row in record['outputs']:
        p = dist/row['path']; data = p.read_bytes()
        if p.is_symlink() or len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('CANDIDATE_CHANGED')
        files['/review/'+row['path']] = data
    os.umask(0o077); output.mkdir(parents=True, mode=0o700)
    transaction=AcceptanceTransaction(lambda rows:(output/'transaction.json').write_bytes(encoded(rows)))
    startup_events=[]
    def startup_event(event):
        startup_events.append({'at':time.monotonic(),**event})
        (output/'startup-events.json').write_bytes(encoded(startup_events))
    def prior_fingerprint(pid):
        result=subprocess.run(['/bin/ps','-p',str(pid),'-o','pid=,ppid=,uid=,lstart=,command='],capture_output=True,text=True,timeout=5)
        if result.returncode not in (0,1):raise RuntimeError('PRIOR_IDENTITY_UNAVAILABLE')
        return result.stdout.strip()
    try:
        verify_prior_cleanup(args.prior_cleanup,prior_fingerprint)
        stable_port_clear(startup_event)
        baseline_safari=safari_processes()
        if baseline_safari:raise RuntimeError('PREEXISTING_SAFARI_AUTOMATION')
        executable_pins={'launcher':safari_signed_artifact(SAFARI_LAUNCHER,'launcher'),'helper':safari_signed_artifact(SAFARI_HTTP_SERVICE,'helper')}
        startup_event({'phase':'SAFARI_BASELINE','processes':baseline_safari,'executables':executable_pins})
        transaction.advance('NEW','PREFLIGHT')
    except Exception as exc:
        startup_event({'incident':type(exc).__name__,'category':str(exc)[:120],'phase':'PRE_BIND'})
        raise
    constructed_at = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    seed = json.loads(subprocess.check_output(['/usr/local/bin/node','--input-type=module','-e',
        "import {northstarFixture} from './src/northstarSession.fixture.ts';console.log(JSON.stringify(await northstarFixture(Date.parse("+json.dumps(constructed_at)+"))));"], cwd=source/'FRONT END'))
    lifecycle_seeds = json.loads(subprocess.check_output(['/usr/local/bin/node','--input-type=module','-e',
        "import {northstarFixture} from './src/northstarSession.fixture.ts';import {sessionPhases} from './src/truthSpineSessionView.ts';import {contentHash,admitProjection} from './src/northstarSession.ts';const values=[];for(const phase of sessionPhases){const x=await northstarFixture(Date.parse("+json.dumps(constructed_at)+"));x.phase=phase;x.factory.phase=phase;for(const rows of [x.factory.rooms,x.factory.agents,x.factory.governance,x.factory.routes,x.factory.history,x.factory.subsystems,[x.factory.day_trading]])for(const row of rows)row.phase=phase;x.factory.content_hash=await contentHash(x.factory);await admitProjection(x,null,Date.parse(x.published_at));values.push(x)}console.log(JSON.stringify(values));"], cwd=source/'FRONT END'))
    lifecycle_fixtures = [(value, BoundFixture.bind(value)) for value in lifecycle_seeds]
    fixture = BoundFixture.bind(seed)
    binding = {'fixture_sha256':fixture.sha256,'generation':seed['source_generation'],
               'source_cycle':seed['source_cycle'],'projection_content_hash':seed['factory']['content_hash'],
               'generated_at':seed['published_at'],'construction_time':constructed_at,
               'clock_ms':round(datetime.fromisoformat(constructed_at).timestamp()*1000)}
    bootstrap = FIXTURE_BOOTSTRAP.replace('FIXTURE_BINDING',json.dumps(binding)).encode()
    html_path = '/review/northstar-session.html'
    original_html = files[html_path]
    # This explicitly recorded fixture-only wrapper is NOT the packaged HTML.
    # All packaged JS/CSS/images remain byte-identical; no release is installed.
    if original_html.count(b'<head>') != 1: raise ValueError('FIXTURE_HTML_ENTRY_INVALID')
    files[html_path] = original_html.replace(b'<head>',b'<head><script src="/review/fixture-clock.js"></script>',1)
    files['/review/fixture-clock.js'] = bootstrap
    binding_receipt = {**binding,'packaged_html_sha256':hashlib.sha256(original_html).hexdigest(),
                       'fixture_wrapper_html_sha256':hashlib.sha256(files[html_path]).hexdigest(),
                       'fixture_bootstrap_sha256':hashlib.sha256(bootstrap).hexdigest()}
    (output/'fixture.json').write_bytes(fixture.body)
    (output/'fixture-binding.json').write_bytes(encoded(binding_receipt))
    for value, bound in lifecycle_fixtures:
        (output/('fixture-'+value['phase']+'.json')).write_bytes(bound.body)
    scenario = {'mode':'current'}; requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            path = self.path.split('?',1)[0]
            request = {'path':path,'at':time.monotonic(),'request_number':len(requests)+1,
                       'wall_time':datetime.now(timezone.utc).isoformat()}
            requests.append(request)
            status = 200
            if path == '/truth-spine/full-session':
                data = fixture.response()
                if scenario['mode'] == 'unavailable': status = 503
                request.update(fixture_sha256=fixture.sha256,generation=binding['generation'],
                               projection_content_hash=binding['projection_content_hash'],status=status)
                media = 'application/json'
            elif path in files:
                data = files[path]; media = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            else: status, data, media = 404, b'NOT_FOUND', 'text/plain'
            self.send_response(status); self.send_header('Content-Type', media); self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control','no-store'); self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(data)
        def mutation(self): self.send_response(405); self.end_headers()
        do_POST = do_PUT = do_PATCH = do_DELETE = mutation
    server=None;thread=None;driver_log=None
    driver = None; sid = None; owned_window=None; native_window=None; evidence = {'classification':'RED','fixture_only':True,'fixture_binding':binding_receipt,'captures':[],'interactions':[], 'artifacts':record['outputs']}
    def wd(method, path, value=None, timeout=30):
        req=urllib.request.Request('http://127.0.0.1:5292'+path, data=None if value is None else json.dumps(value).encode(),
                                   method=method,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=timeout) as r: result=json.load(r)
        if isinstance(result.get('value'),dict) and result['value'].get('error'): raise RuntimeError(result['value']['error'])
        return result.get('value')
    def fingerprint(pid):
        return subprocess.check_output(['ps','-p',str(pid),'-o','pid=,ppid=,uid=,lstart=,command='],text=True).strip()
    def command(method,path,value=None):
        # Every image, including crops, goes through the same immutable capture
        # boundary. Diagnostic callers cannot bypass geometry or identity checks.
        if method == 'GET' and path.endswith('/screenshot'):
            settlement=settle('image-admission:'+path)
            script=CAPTURE_IDENTITY+SETTLEMENT_GEOMETRY+"return {identity:displayedIdentity(),frame:geometryFrame(document.querySelector('.northstar-full-session')),active:{tag:document.activeElement.tagName,id:document.activeElement.id,station:document.activeElement.dataset.roomId||null,name:document.activeElement.getAttribute('aria-label')||document.activeElement.textContent},modality:window.__modalityEvents?.slice(-8)||[]};"
            before=js(script); started=datetime.now(timezone.utc).isoformat()
            image=wd(method,'/session/'+sid+path,value)
            after=js(script)
            receipt={'name':'image-'+str(len(evidence.get('image_admissions',[]))+1),
                'source_commit':record['inputs']['source_commit'],'build_input_hash':record['input_hash'],
                'provenance_hash':record['content_hash'],'output_hash':record['output_hash'],
                'settlement':{'consecutive_matches':settlement['consecutiveMatches'],'samples':[{'at':s['at'],'sha256':hashlib.sha256(s['signature'].encode()).hexdigest(),'fonts':s['fonts'],'scroll':s['scroll']} for s in settlement['samples']]},
                'endpoint':path,'beforeIdentity':before['identity'],'afterIdentity':after['identity'],
                'measurementFrame':before['frame'],'afterScreenshotFrame':after['frame'],
                'screenshotGeometryMatches':before['frame']==after['frame'],
                'active_before':before['active'],'active_after':after['active'],
                'input_modality':before['modality'],'screenshot_start':started,
                'screenshot_end':datetime.now(timezone.utc).isoformat(),
                'sha256':hashlib.sha256(base64.b64decode(image)).hexdigest()}
            receipt['screenshotGeometryMatches'] &= before['active']==after['active']
            admissions={'captures':[]}
            try: admit_capture(admissions,receipt)
            finally:
                evidence.setdefault('image_admissions',[]).append(receipt)
                (output/(receipt['name']+'.json')).write_bytes(encoded(receipt))
            return image
        return wd(method,'/session/'+sid+path,value)
    def js(script): return command('POST','/execute/sync',{'script':script,'args':[]})
    def settle(name, destination=None, scroll_target=None):
        def foreground():
            handle=wd('GET','/session/'+sid+'/window',timeout=8)
            value=wd('POST','/session/'+sid+'/execute/sync',{'script':CAPTURE_IDENTITY+"return {url:location.href,identity:displayedIdentity().binding,active:[document.activeElement.tagName,document.activeElement.id,document.activeElement.textContent],scroll:[scrollX,scrollY,...[...document.querySelectorAll('.northstar-dialog-body')].map(e=>[e.scrollLeft,e.scrollTop])],visible:document.visibilityState==='visible',focused:document.hasFocus()};",'args':[]},timeout=8)
            return {'handle':handle,**value}
        def record_focus(value):
            evidence.setdefault('foreground',[]).append({'settlement':name,**value})
            (output/'foreground.json').write_bytes(encoded(evidence['foreground']))
        def activate_owned(first):
            if native_window is None:raise RuntimeError('NATIVE_WINDOW_RECEIPT_REQUIRED')
            window_id=safari_fixture_window(first['url'],native_window,activate=True)
            return {'window_id':window_id,'handle':owned_window,'url':first['url'],'identity':first['identity']}
        acquire_owned_browser_focus(foreground,lambda handle:wd('POST','/session/'+sid+'/window',{'handle':handle},timeout=8),owned_window,record_focus,activate_native=activate_owned)
        options={'browser':True}
        if destination is not None: options['destination']=destination
        if scroll_target is not None: options['scrollTarget']=scroll_target
        # Independent wall-clock watchdog persists even if WebDriver never
        # returns. Small sync probes observe the original in-page algorithm;
        # diagnostic instrumentation does not substitute elapsed time for frames.
        number=len(evidence.get('settlements',[]))+1
        progress={'name':name,'started':time.monotonic(),'window':None,'probes':[]}
        progress_path=output/('settlement-'+str(number)+'.json')
        progress_path.write_bytes(encoded(progress))
        watchdog=threading.Timer(8,lambda:(output/('settlement-'+str(number)+'-watchdog.json')).write_bytes(encoded({**progress,'outer_timeout':True,'at':time.monotonic()})))
        watchdog.daemon=True;watchdog.start()
        def probe(script):
            return wd('POST','/session/'+sid+'/execute/sync',{'script':script,'args':[]},timeout=8)
        try:
            progress['window']=wd('GET','/session/'+sid+'/window',timeout=8)
            if args.diagnose_settlement_async:
                result=wd('POST','/session/'+sid+'/execute/async',{'script':CAPTURE_IDENTITY+SETTLEMENT_GEOMETRY+'const done=arguments[arguments.length-1];settleNorthstar('+json.dumps(options)+').then(done);','args':[]},timeout=8)
                progress['probes'].append({'at':time.monotonic(),'trace':result.get('trace')})
                progress_path.write_bytes(encoded(progress))
            else:
                probe(CAPTURE_IDENTITY+SETTLEMENT_GEOMETRY+'window.__settlementResult=null;settleNorthstar('+json.dumps(options)+').then(r=>window.__settlementResult=r);return true;')
            deadline=time.monotonic()+7
            while not args.diagnose_settlement_async:
                observed=probe('return {trace:window.__settlementTrace,result:window.__settlementResult};')
                progress['probes'].append({'at':time.monotonic(),'trace':observed['trace']})
                progress_path.write_bytes(encoded(progress))
                if observed['result'] is not None:
                    result=observed['result'];break
                if time.monotonic()>=deadline:raise RuntimeError('SETTLEMENT_OUTER_DEADLINE')
                time.sleep(.05)
        finally:
            watchdog.cancel();watchdog.join(timeout=1)
        # Keep every frame's exact geometry identity without quadratically
        # rewriting repeated full-page boxes for hundreds of interactions.
        # Captures retain full pre/post boxes; timeouts retain raw samples too.
        receipt={k:v for k,v in result.items() if k!='samples'}
        receipt['samples']=[{'at':s['at'],'geometry_sha256':hashlib.sha256(s['signature'].encode()).hexdigest(),
                            'viewport':s['viewport'],'scroll':s['scroll'],'fonts':s['fonts'],
                            'pendingAnimations':s['pendingAnimations'],'destination':s['destination'],
                            'nestedScroll':[[e[0],e[1],e[2],e[4],e[5]] for e in s['elements'] if e[4] or e[5]]}
                           for s in result.get('samples',[])]
        if not result['ok']: receipt['unsettled_frames']=result.get('samples',[])
        evidence.setdefault('settlements',[]).append({'name':name,**receipt})
        (output/'measurements.json').write_bytes(encoded(evidence))
        if not result['ok']: raise RuntimeError('LAYOUT_SETTLEMENT_FAILED: '+name+':'+result['reason'])
        return result
    def wait_for(script, seconds=15):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            if js(script): return
            time.sleep(.15)
        raise RuntimeError('BROWSER_ASSERTION_TIMEOUT: '+script[:100])
    def click(label):
        element=js("return [...document.querySelectorAll('button')].find(e=>e.textContent.trim()==="+json.dumps(label)+")||null;")
        if not element: raise RuntimeError('BUTTON_NOT_FOUND: '+label)
        command('POST','/element/'+element['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
        if label in ['Gallery','Story','Replay','Command','Cases','Expansion Wing','Factory Watch']:
            settle('navigation:'+label,destination=label)
    def inspect_group(group, count, width):
        labels=js("return [...document.querySelectorAll('[data-coverage="+group+"] button')].map(e=>e.textContent)")
        if len(labels)!=count or len(set(labels))!=count: raise RuntimeError('COVERAGE_IDENTITY_INVALID:'+group)
        identities=js("return [...document.querySelectorAll('[data-coverage="+group+"] article')].map(e=>e.dataset.coverageId)")
        if len(set(identities))!=count: raise RuntimeError('DUPLICATE_COVERAGE_IDENTITY')
        for index,label in enumerate(labels+labels[:1]*2):
            evidence['current_step']={'group':group,'index':index,'label':label,'operation':'open','width':width}
            if index%2:
                element=js("const e=[...document.querySelectorAll('button')].find(e=>e.textContent==="+json.dumps(label)+");e.scrollIntoView({block:'center',behavior:'instant'});e.focus({preventScroll:true});return e;")
                settle('keyboard-target:'+label)
                command('POST','/element/'+element['element-6066-11e4-a52e-4f735466cecf']+'/value',{'text':'\ue007'})
            else: click(label)
            wait_for("return document.activeElement.tagName==='H3'")
            heading=js("return document.activeElement.textContent")
            if label != 'Inspect '+heading: raise RuntimeError('ACCESSIBLE_ROOM_IDENTITY_MISMATCH')
            summary=js("return document.querySelector('.northstar-selected summary')")
            if summary:
                command('POST','/element/'+summary['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
                if not js("return document.querySelector('.northstar-selected details').open"): raise RuntimeError('DISCLOSURE_FAILED')
            settle('selection:'+group+':'+label)
            selected=js(TEXT_GEOMETRY+"return requiredText(document.querySelector('.northstar-selected'));")
            evidence.setdefault('selected_text_checks',[]).append({'width':width,'group':group,'label':label,'geometry':selected})
            if selected['clipped'] or selected['overlaps']: raise RuntimeError('SELECTED_REQUIRED_TEXT_FAILED:'+label)
            if index==0: capture(f'{width}-{group}-selected-'+str(len(evidence['interactions'])),width)
            evidence['current_step']['operation']='escape-disclosure'
            active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
            command('POST','/element/'+active+'/value',{'text':'\ue00c'})
            wait_for("return !!document.querySelector('.northstar-selected')&&!document.querySelector('.northstar-selected details').open")
            if not js("return document.activeElement.tagName==='SUMMARY'"): raise RuntimeError('NESTED_ESCAPE_FOCUS_FAILED')
            evidence['current_step']['operation']='escape-panel'
            active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
            command('POST','/element/'+active+'/value',{'text':'\ue00c'})
            wait_for("return !document.querySelector('.northstar-selected')")
            wait_for("return !location.hash.includes('/coverage/')")
            wait_for("return document.activeElement.textContent==="+json.dumps(label))
            focus=js("return {text:document.activeElement.textContent,outline:getComputedStyle(document.activeElement).outlineStyle,rect:document.activeElement.getBoundingClientRect().toJSON()}")
            if focus['text']!=label or focus['rect']['width']<=0: raise RuntimeError('ESCAPE_FOCUS_FAILED')
            hash_before=js('return location.hash')
            active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
            command('POST','/element/'+active+'/value',{'text':'\ue00c'})
            if js("return !!document.querySelector('.northstar-selected')||document.querySelectorAll('button[aria-expanded=true]').length>0||location.hash!=="+json.dumps(hash_before)): raise RuntimeError('CLOSED_ESCAPE_MUTATED_STATE')
            evidence.setdefault('interaction_steps',[]).append({**evidence['current_step'],'result':'PASSED','focus':focus,'hash':hash_before})
            (output/'measurements.json').write_bytes(encoded(evidence))
        evidence['interactions'].append({'width':width,'group':group,'identities':identities,'selections':count,'extra_repeat_cycles':2,'mouse_and_keyboard':True,'escape_focus':True,'disclosures':True})
        return labels
    def polling_proof(name):
        start=time.monotonic(); time.sleep(11)
        samples=[r['at'] for r in requests if r['path']=='/truth-spine/full-session' and r['at']>=start]
        if not 2<=len(samples)<=3 or any(b-a<4.5 for a,b in zip(samples,samples[1:])): raise RuntimeError('POLLING_OWNER_INTERVAL_FAILED')
        evidence.setdefault('polling',[]).append({'name':name,'requests':len(samples),'intervals':[b-a for a,b in zip(samples,samples[1:])]})
    def native_key(key,shift=False):
        actions=([{'type':'keyDown','value':'\ue008'}] if shift else [])+[{'type':'keyDown','value':key},{'type':'keyUp','value':key}]+([{'type':'keyUp','value':'\ue008'}] if shift else [])
        command('POST','/actions',{'actions':[{'type':'key','id':'native-card-keyboard','actions':actions}]})
    def modality_observer():
        js("""if(!window.__modalityEvents){window.__modalityEvents=[];
window.__northstarUnfocusedStyles=new WeakMap();
for(const e of document.querySelectorAll('button,summary,[tabindex]'))if(e!==document.activeElement){const s=getComputedStyle(e);let adjacent=null;for(let p=e.parentElement;p;p=p.parentElement){const st=getComputedStyle(p);if(st.backgroundColor.startsWith('rgb(')&&st.backgroundImage==='none'){adjacent=st.backgroundColor;break;}}window.__northstarUnfocusedStyles.set(e,{border:s.border,backgroundColor:s.backgroundColor,boxShadow:s.boxShadow,adjacent});}
const nativeFocus=HTMLElement.prototype.focus;
HTMLElement.prototype.focus=function(...args){window.__modalityEvents.push({type:'programmatic-focus',target:this.dataset?.roomId||this.tagName});return nativeFocus.apply(this,args);};
for(const type of ['keydown','keyup','pointerdown','focusin'])document.addEventListener(type,e=>{const row={type,key:e.key||null,shift:!!e.shiftKey,alt:!!e.altKey,ctrl:!!e.ctrlKey,meta:!!e.metaKey,trusted:e.isTrusted,target:e.target.dataset?.roomId||e.target.tagName,active:document.activeElement.dataset?.roomId||document.activeElement.tagName,prevented:e.defaultPrevented};window.__modalityEvents.push(row);queueMicrotask(()=>row.prevented=e.defaultPrevented);},true);}return true;""")
    def native_station_tab(width,shift=False):
        before=js('return window.__modalityEvents.length')
        native_key('\ue004',shift)
        settle('native-station-tab')
        station=js('return document.activeElement.dataset?.roomId||null')
        if station:
            proof=js(DIALOG_GEOMETRY+'return nativeCardTabProof(window.__modalityEvents.slice('+str(before)+'),'+json.dumps(station)+','+str(shift).lower()+')')
            data=card_measure('native-shift-tab' if shift else 'native-tab',width,station)
            if not proof or data['tag']!='BUTTON' or data['tabindex']!=0 or data['focus']['failures']:raise RuntimeError('NATIVE_STATION_FOCUS_FAILED:'+station)
        return station
    def card_measure(label,width,station=None):
        settle('card-modality:'+label)
        data=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+DIALOG_GEOMETRY+"""
const e=document.activeElement,s=getComputedStyle(e);
return {focus:focusMeasurement(document.querySelector('.northstar-full-session')),station:e.dataset.roomId||null,tag:e.tagName,tabindex:e.tabIndex,focusMatch:e.matches(':focus'),focusVisible:e.matches(':focus-visible'),border:[s.borderTopWidth,s.borderTopStyle,s.borderTopColor],background:[s.backgroundColor,s.backgroundImage],boxShadow:s.boxShadow,events:window.__modalityEvents.slice(-8),viewport:[innerWidth,innerHeight],outer:[outerWidth,outerHeight],url:location.href,errors:window.__northstarErrors||[]};
""")
        data['input_modality']=label;data['expected_station']=station
        data['beforeIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
        name=f'{width}-modality-{station or data["station"] or "other"}-{label}-{len(evidence.get("modality",[]))+1:04d}'
        (output/(name+'.png')).write_bytes(base64.b64decode(command('GET','/screenshot')))
        data['afterIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
        if data['beforeIdentity']['binding']!=data['afterIdentity']['binding']:raise RuntimeError('MODALITY_CAPTURE_GENERATION_CHANGED')
        # Element screenshot is a crop, not evidence that an external ring fits;
        # full viewport and independently measured outline bands are retained.
        active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
        (output/(name+'-crop.png')).write_bytes(base64.b64decode(command('GET','/element/'+active+'/screenshot')))
        (output/(name+'.json')).write_bytes(encoded(data))
        evidence.setdefault('modality',[]).append({'file':name+'.json','station':data['station'],'input_modality':label,'focus_failures':data['focus']['failures'],'viewport':data['viewport']})
        (output/'measurements.json').write_bytes(encoded(evidence))
        return data
    def modality_diagnosis(width):
        modality_observer()
        ids=js("return [...document.querySelectorAll('[data-room-id]')].map(e=>e.dataset.roomId)")
        if len(ids)!=18 or len(set(ids))!=18:raise RuntimeError('STATION_INVENTORY_INVALID')
        for reverse in [False,True]:
            seen=[];trace=[]
            for step in range(250):
                native_key('\ue004',reverse)
                identity=js("return {station:document.activeElement.dataset?.roomId||null,tag:document.activeElement.tagName,name:document.activeElement.getAttribute('aria-label')||document.activeElement.textContent.slice(0,100)}")
                trace.append(identity)
                if identity['station'] and identity['station'] not in seen:
                    seen.append(identity['station']);card_measure('native-shift-tab' if reverse else 'native-tab',width,identity['station'])
                if len(seen)==18:break
            evidence.setdefault('modality_traversal',[]).append({'width':width,'reverse':reverse,'seen':seen,'trace':trace})
            (output/'measurements.json').write_bytes(encoded(evidence))
        for station in ids:
            select="document.querySelector('[data-room-id="+station+"]')"
            element=js('const e='+select+";e.scrollIntoView({block:'center',behavior:'instant'});e.focus({preventScroll:true});return e;")
            card_measure('programmatic-focus',width,station)
            # Native pointer activation opens the dialog. Record trusted pointer
            # and focus events; never relabel its ensuing restoration as Tab.
            command('POST','/element/'+element['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
            wait_for("return !!document.querySelector('.northstar-station-dialog')")
            card_measure('pointer-activation-dialog-focus',width,station)
            native_key('\ue00c');wait_for("return !document.querySelector('.auction-room-modal')")
            card_measure('restored-after-pointer-open-escape',width,station)
            # A fixture re-poll causes a real accepted context rerender; no state
            # assignment, fake projection or dispatched DOM event is used.
            sequence=js('return window.__northstarFixture.responses.length')
            wait_for('return window.__northstarFixture.responses.length>'+str(sequence))
            card_measure('after-rerender',width,station)
            click('Story');click('Gallery')
            card_measure('after-destination-navigation',width,station)
    def station_dialog_audit(station, width):
        selector='[data-room-id='+station+']'
        def press(key, shift=False):
            keys=([{'type':'keyDown','value':'\ue008'}] if shift else [])+[{'type':'keyDown','value':key},{'type':'keyUp','value':key}]+([{'type':'keyUp','value':'\ue008'}] if shift else [])
            command('POST','/actions',{'actions':[{'type':'key','id':'station-keyboard','actions':keys}]})
        def measure(label):
            settle('station-modal:'+station+':'+label)
            data=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+DIALOG_GEOMETRY+"const d=dialogMeasurement(),focus=focusMeasurement(document.querySelector('.northstar-station-dialog'));return {...d,focus,failures:[...dialogFailures(d),...focus.failures]}")
            data['beforeIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
            (output/f'{width}-{station}-{label}-focus.png').write_bytes(base64.b64decode(command('GET','/screenshot')))
            data['afterIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
            if data['beforeIdentity']['binding']!=data['afterIdentity']['binding']:raise RuntimeError('FOCUS_CAPTURE_GENERATION_CHANGED')
            (output/f'{width}-{station}-{label}-dialog.json').write_bytes(encoded(data))
            if data['failures']:
                (output/f'{width}-{station}-{label}-failure.png').write_bytes(base64.b64decode(command('GET','/screenshot')))
                raise RuntimeError('STATION_DIALOG_FAILED:'+station+':'+label+':'+','.join(data['failures']))
            return data
        element=js('return document.querySelector('+json.dumps(selector)+')')
        original=js('return {scroll:[scrollX,scrollY],hash:location.hash,body:document.body.style.cssText,html:document.documentElement.style.cssText}')
        if js('return document.activeElement.dataset.roomId')!=station:raise RuntimeError('STATION_NATIVE_OPENER_NOT_FOCUSED')
        native_key('\ue007')
        wait_for("return !!document.querySelector('.northstar-dialog-body')")
        top=measure('top')
        if top['body']['scroll'][:2]!=[0,0] or not top['active']['id'].startswith('auction-room-title-'):raise RuntimeError('DIALOG_OPEN_FOCUS_OR_SCROLL')
        capture(f'{width}-{station}-dialog-top',width)
        press('\ue004',True);wrapped=measure('shift-tab')
        press('\ue004');forward=measure('tab-wrap')
        if forward['active']['text']!='×':raise RuntimeError('DIALOG_TAB_WRAP_FAILED')
        def controls():
            return js("return [...document.querySelectorAll('.northstar-station-dialog button,.northstar-station-dialog summary,.northstar-station-dialog [tabindex]')].filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length&&![...function*(p){for(;p;p=p.parentElement)yield p;}(e.parentElement)].some(p=>p.tagName==='DETAILS'&&!p.open&&!p.querySelector('summary')?.contains(e)))")
        def cycle(label,shift=False):
            ordered=controls();seen=[]
            for i in range(1,len(ordered)+1):
                press('\ue004',shift);step=measure(label+'-'+str(i));seen.append(step['focus'])
                active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
                if active!=ordered[(-i if shift else i)%len(ordered)]['element-6066-11e4-a52e-4f735466cecf']:raise RuntimeError('DIALOG_LOGICAL_FOCUS_ORDER_FAILED')
            return seen
        keyboard={'collapsedTab':cycle('collapsed-tab'),'collapsedShiftTab':cycle('collapsed-shift-tab',True)}
        # Open every disclosure with native keyboard Enter. Newly revealed nested
        # summaries join the following tab steps; no fixture or DOM open mutation.
        for i in range(100):
            press('\ue004');step=measure('expand-tab-'+str(i))
            if step['active']['text']=='×':break
            if step['active']['tag']=='SUMMARY' and js("return !document.activeElement.parentElement.open"):
                press('\ue007');measure('expand-enter-'+str(i))
        else:raise RuntimeError('DISCLOSURE_KEYBOARD_BOUND_EXCEEDED')
        disclosures=js("return [...document.querySelectorAll('.northstar-dialog-body details')].map(e=>({open:e.open}))")
        if not all(row['open'] for row in disclosures):raise RuntimeError('DISCLOSURE_KEYBOARD_NOT_EXPANDED')
        keyboard.update({'expandedTab':cycle('expanded-tab'),'expandedShiftTab':cycle('expanded-shift-tab',True)})
        js("const e=document.querySelector('.northstar-dialog-body');e.scrollTo({top:0,left:0,behavior:'instant'});e.focus({preventScroll:true})")
        start=measure('expanded-top');maximum=start['body']['scroll'][3]-start['body']['scroll'][5]
        seen=set();total=set();scrolls=[]
        # Preserve full ranges while proving each text node is reachable. The
        # stable node ordinal comes from the same unchanged expanded DOM.
        position=0
        for _ in range(100):
            js("document.querySelector('.northstar-dialog-body').scrollTo({top:"+str(position)+",behavior:'instant'})")
            sample=measure('scroll-'+str(len(scrolls)))
            ranges=js(TEXT_GEOMETRY+"const e=document.querySelector('.northstar-dialog-body'),r=e.getBoundingClientRect();return requiredText(e).text.flatMap((t,i)=>t.rects.map((b,j)=>({id:i+':'+j,visible:b.top>=r.top+2&&b.bottom<=r.bottom-2&&b.left>=r.left&&b.right<=r.right}))); ")
            for row in ranges:
                total.add(row['id'])
                if row['visible']:seen.add(row['id'])
            scrolls.append({'top':sample['body']['scroll'][1],'failures':sample['failures'],'document':sample['document'],'close':sample['close']})
            if sample['document']['scroll']!=top['document']['scroll']:raise RuntimeError('BACKGROUND_SCROLL_MOVED')
            if position>=maximum:break
            position=min(maximum,position+max(20,int(sample['body']['scroll'][5]*.65)))
        else:raise RuntimeError('DIALOG_SCROLL_BOUND_EXCEEDED')
        if seen!=total:raise RuntimeError('DIALOG_REQUIRED_TEXT_UNREACHABLE:'+station+':'+str(sorted(total-seen)))
        bottom=measure('bottom');capture(f'{width}-{station}-dialog-bottom',width)
        close=js("return document.querySelector('.northstar-dialog-header .auction-close')")
        command('POST','/element/'+close['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
        wait_for('return !document.querySelector(".auction-room-modal")&&document.activeElement.dataset.roomId==='+json.dumps(station))
        settle('station-native-close:'+station)
        restored=js('return {scroll:[scrollX,scrollY],hash:location.hash,body:document.body.style.cssText,html:document.documentElement.style.cssText}')
        if restored!=original:raise RuntimeError('DIALOG_BACKGROUND_RESTORATION_FAILED:'+station)
        if card_measure('restored-after-pointer-close',width,station)['focus']['failures']:raise RuntimeError('RESTORED_OPENER_NOT_VISIBLE:'+station)
        # Reopen and close by Escape twice: only the first press owns a layer.
        element=js('return document.querySelector('+json.dumps(selector)+')')
        native_key(' ')
        wait_for("return !!document.querySelector('.northstar-dialog-body')")
        again=measure('reopen')
        if again['body']['scroll'][:2]!=[0,0]:raise RuntimeError('DIALOG_REOPEN_SCROLL_FAILED')
        press('\ue00c');wait_for('return !document.querySelector(".auction-room-modal")&&document.activeElement.dataset.roomId==='+json.dumps(station));press('\ue00c')
        settle('station-escape-close:'+station)
        after=js('return {scroll:[scrollX,scrollY],hash:location.hash,body:document.body.style.cssText,html:document.documentElement.style.cssText}')
        if after!=original:raise RuntimeError('DIALOG_ESCAPE_RESTORATION_FAILED:'+station)
        if card_measure('restored-after-space-escape',width,station)['focus']['failures']:raise RuntimeError('RESTORED_OPENER_NOT_VISIBLE:'+station)
        evidence.setdefault('station_dialogs',[]).append({'width':width,'station':station,'top':top,'bottom':bottom,'keyboard':keyboard,'shiftTab':wrapped['active'],'tab':forward['active'],'scrolls':scrolls,'text_nodes_reached':len(seen),'disclosures':len(disclosures),'background_before':original,'background_after':after,'native_click_escape_exact_focus':True})
        (output/'measurements.json').write_bytes(encoded(evidence))
    def gallery_audit(width):
        expected=json.loads(subprocess.check_output(['/usr/local/bin/node','--input-type=module','-e',
            "import {AUCTION_ROOMS} from './src/auctionRegistry.ts';console.log(JSON.stringify(AUCTION_ROOMS.map(r=>({id:r.id,name:r.label,short:r.shortLabel}))))"],cwd=source/'FRONT END'))
        records=[]
        modality_observer()
        # Actual native browser traversal, never a programmatic focus setup.
        forward=[]
        for _ in range(100):
            station=native_station_tab(width)
            if station:forward.append(station)
            if len(forward)==18:break
        if forward!=[r['id'] for r in expected]:raise RuntimeError('NATIVE_STATION_FORWARD_ORDER_FAILED')
        # Step beyond the last station, then reverse through every native button.
        native_station_tab(width)
        reverse=[]
        for _ in range(100):
            station=native_station_tab(width,True)
            if station:reverse.append(station)
            if len(reverse)==18:break
        if reverse!=list(reversed(forward)):raise RuntimeError('NATIVE_STATION_REVERSE_ORDER_FAILED')
        evidence.setdefault('station_native_traversal',[]).append({'width':width,'forward':forward,'reverse':reverse})
        for row in expected:
            if js('return document.activeElement.dataset?.roomId||null')!=row['id']:
                if native_station_tab(width)!=row['id']:raise RuntimeError('STATION_SEQUENCE_CHANGED')
            settle('station:'+row['id'])
            data=js(TEXT_GEOMETRY+"""
const id=ID_VALUE,card=document.querySelector('[data-room-id="'+id+'"]');
if(!card)return {missing:true,id};

const r=card.getBoundingClientRect(),s=getComputedStyle(card),t=card.querySelector('.auction-room__output small'),ts=getComputedStyle(t);
const pad=parseFloat(s.outlineWidth)+parseFloat(s.outlineOffset);
const focusBox={space:'viewport-css-px',left:r.left-pad,right:r.right+pad,top:r.top-pad,bottom:r.bottom+pad};
const focusClips=[];for(let e=card.parentElement;e&&e!==document.body&&e!==document.documentElement;e=e.parentElement){const st=getComputedStyle(e);if(outside(focusBox,viewportBox(e.getBoundingClientRect()),['clip','hidden'].includes(st.overflowX),['clip','hidden'].includes(st.overflowY)))focusClips.push(e.className);}
const neighbors=[...document.querySelectorAll('.auction-room')].filter(x=>x!==card).filter(x=>{const b=x.getBoundingClientRect();return Math.min(r.right,b.right)-Math.max(r.left,b.left)>2&&Math.min(r.bottom,b.bottom)-Math.max(r.top,b.top)>2}).map(x=>x.dataset.roomId);
return {id,aria:card.getAttribute('aria-label'),name:card.querySelector('.auction-room__identity b').textContent,rect:r.toJSON(),required:requiredText(card),explanation:t.textContent,explanationRanges:requiredText(t).text,explanationStyle:{display:ts.display,maxHeight:ts.maxHeight,fontSize:ts.fontSize,lineHeight:ts.lineHeight},focus:document.activeElement===card,outline:s.outlineStyle,focusClips,neighbors};
""".replace('ID_VALUE',json.dumps(row['id'])))
            records.append(data)
            evidence.setdefault('gallery_audits',{})[str(width)]={'stations':records}
            (output/'measurements.json').write_bytes(encoded(evidence))
            if data.get('missing') or data['name']!=row['short'] or not data['aria'].startswith('Open '+row['name']+';') or not data['explanationRanges'] or not data['explanation'] or data['required']['clipped'] or data['required']['overlaps'] or data['neighbors'] or not data['focus'] or data['outline']!='solid' or data['focusClips']:
                raise RuntimeError('ARCHITECTURAL_EXPLANATION_OR_FOCUS_FAILED:'+str(width)+':'+row['id'])
            if row['id'] in ['policy','monitoring','learning','judgment']:
                data['decoration']=js(DECORATION_GEOMETRY+"return decorationSafety(document.querySelector('.northstar-full-session'))")
                data['pointer_target']=js("const e=document.querySelector('[data-room-id='+"+json.dumps(row['id'])+"+']'),r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.left+r.width/2,r.top+r.height/2));")
                if data['decoration']['violations'] or not data['pointer_target']:raise RuntimeError('POLICY_DECORATION_OR_POINTER_FAILED')
                capture(f"{width}-{row['id']}-focus",width)
            station_dialog_audit(row['id'],width)
            if args.diagnose_settlement:
                return  # Diagnostic bound: original traversal then first Radar.
        products=js(TEXT_GEOMETRY+SETTLEMENT_GEOMETRY+"""return [...document.querySelectorAll('[data-coverage=rooms] article')].map(e=>({id:e.dataset.coverageId,name:e.querySelector('h3').textContent,explanation:e.querySelectorAll('p')[2].textContent,mandatoryVisible:[e.querySelector('h3'),...e.querySelectorAll('p'),e.querySelector('button')].every(visibleRequiredElement),required:requiredText(e)}));""")
        evidence['gallery_audits'][str(width)]['products']=products
        if len(records)!=18 or len(products)!=24 or len({r['id'] for r in products})!=24:raise RuntimeError('GALLERY_COUNT_FAILED')
        for product in products:
            bound=next((r for r in seed['factory']['rooms'] if r['id']==product['id']),None)
            if not bound or not product['mandatoryVisible'] or product['name']!=bound['name'] or product['explanation']!=bound['limitation'] or not product['required']['text'] or product['required']['clipped']:
                raise RuntimeError('GOVERNED_ROOM_NAME_EXPLANATION_FAILED')
        js("window.scrollTo({top:0,left:0,behavior:'instant'})")
        settle('gallery-top',scroll_target=[0,0])
        factory=js("const e=document.querySelector('.auction-factory');return {scrollTop:e.scrollTop,scrollLeft:e.scrollLeft,overflow:getComputedStyle(e).overflow};")
        evidence.setdefault('factory_scroll',{})[str(width)]=factory
        if factory['scrollTop'] or factory['scrollLeft'] or factory['overflow']!='clip':raise RuntimeError('FACTORY_HIDDEN_SCROLL_REGRESSION')

    def capture(name, width):
        settle('capture:'+name)
        census=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+"return obstructionCensus(document.querySelector('.northstar-full-session'))")
        (output/(name+'-census.json')).write_bytes(encoded(census))
        data=js(TEXT_GEOMETRY+DECORATION_GEOMETRY+SETTLEMENT_GEOMETRY+"""const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
const cards=[...document.querySelectorAll('.northstar-room-grid > article')].filter(visible);
const overlaps=[];for(let i=0;i<cards.length;i++)for(let j=i+1;j<cards.length;j++){if(cards[i].parentElement!==cards[j].parentElement)continue;let a=cards[i].getBoundingClientRect(),b=cards[j].getBoundingClientRect();if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)overlaps.push([i,j]);}
const geometry=requiredText(document.querySelector('.northstar-full-session'));
return {measurementFrame:geometryFrame(document.querySelector('.northstar-full-session')),outerWidth,outerHeight,innerWidth,innerHeight,dpr:devicePixelRatio,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,overflow:Math.max(0,document.documentElement.scrollWidth-document.documentElement.clientWidth),clipped:geometry.clipped,textOverlaps:geometry.overlaps,overlaps,decoration:decorationSafety(document.querySelector('.northstar-full-session')),bannerPosition:getComputedStyle(document.querySelector('.northstar-session-status')).position,url:location.href,timestamp:new Date().toISOString(),errors:window.__northstarErrors||[],routeFailure:document.body.textContent.includes('Browser navigation update unavailable.'),grid:cards.length?getComputedStyle(cards[0].parentElement).gridTemplateColumns:null,state:document.querySelector('[data-shadow-state]').dataset.shadowState};""")
        data['requested']=[width,825]; data['name']=name
        data['obstruction']={'layers':len(census['layers']),'violations':census['violations'],'census':name+'-census.json'}
        data['beforeIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
        data['screenshot_start']=datetime.now(timezone.utc).isoformat()
        (output/(name+'.png')).write_bytes(base64.b64decode(command('GET','/screenshot')))
        data['screenshot_end']=datetime.now(timezone.utc).isoformat()
        data['afterIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
        data['afterScreenshotFrame']=js(SETTLEMENT_GEOMETRY+"return geometryFrame(document.querySelector('.northstar-full-session'))")
        data['screenshotGeometryMatches']=data['measurementFrame']==data['afterScreenshotFrame']
        data['responsiveFailure']=bool(data['innerWidth']!=width or data['innerHeight']!=825 or data['overflow'] or data['clipped'] or data['textOverlaps'] or data['overlaps'] or data['decoration']['violations'] or census['violations'] or data['errors'] or data['routeFailure'] or data['bannerPosition']!='static')
        try: admit_capture(evidence,data)
        finally: (output/'measurements.json').write_bytes(encoded(evidence))

    def plaque_audit(width):
        click('Collector Plaque'); wait_for("return !!document.querySelector('.northstar-collector-plaque')")
        focus=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
        sequence=js('return window.__northstarFixture.responses.length')
        styles=js('return [document.body.style.cssText,document.documentElement.style.cssText]')
        wait_for('return window.__northstarFixture.responses.length>'+str(sequence),12)
        if command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf'] != focus:
            raise RuntimeError('PLAQUE_POLLING_FOCUS_TEARDOWN')
        if styles != js('return [document.body.style.cssText,document.documentElement.style.cssText]'):
            raise RuntimeError('PLAQUE_POLLING_LOCK_TEARDOWN')
        capture(f'{width}-collector-plaque',width)
        data=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+DIALOG_GEOMETRY+"const d=dialogMeasurement();return {dialog:d,failures:dialogFailures(d),focus:focusMeasurement(document.querySelector('.northstar-collector-plaque'))}")
        if data['failures'] or data['focus']['failures']: raise RuntimeError('PLAQUE_MODAL_CONTRACT_FAILED')
        native_key('\ue004');native_key('\ue004',True);native_key('\ue00c')
        wait_for("return !document.querySelector('[aria-modal=true]')&&document.activeElement.hasAttribute('data-northstar-plaque-opener')")
        evidence.setdefault('plaque_audits',[]).append({'width':width,'polling_preserved_focus':True,'measurement':data})

    def lifecycle_audit(width):
        nonlocal fixture, binding
        for value, bound in lifecycle_fixtures:
            # A different, immutable, explicitly named offline scenario. Reload
            # disposes the previous polling owner; no React state is assigned.
            binding={**binding,'fixture_sha256':bound.sha256,'generation':value['source_generation'],
                     'source_cycle':value['source_cycle'],'projection_content_hash':value['factory']['content_hash'],
                     'generated_at':value['published_at']}
            files['/review/fixture-clock.js']=FIXTURE_BOOTSTRAP.replace('FIXTURE_BINDING',json.dumps(binding)).encode()
            fixture=bound
            command('POST','/refresh',{})
            wait_for("return document.querySelector('[data-shadow-state]')?.dataset.shadowState==='CURRENT'&&document.querySelector('.northstar-session-status [role=status]').textContent.includes("+json.dumps(value['phase'])+")")
            capture(f'{width}-lifecycle-'+value['phase'],width)
            evidence.setdefault('lifecycle',[]).append({'width':width,'phase':value['phase'],'fixture_sha256':bound.sha256,'capabilities':value['capabilities'],'counters':value['counters']})
    try:
        startup_event({'phase':'FIXTURE_BIND_REQUESTED','address':'127.0.0.1','port':5291,'socket_inventory':socket_inventory()})
        try:server=FixtureHTTPServer(('127.0.0.1',5291),Handler)
        except Exception as exc:
            startup_event({'phase':'FIXTURE_BIND_FAILED','port':5291,'errno':getattr(exc,'errno',None),'socket_inventory':socket_inventory()});raise
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        evidence['server_fingerprint']=fingerprint(os.getpid())
        listener_binding(socket_inventory(),5291,os.getpid())
        with urllib.request.urlopen('http://127.0.0.1:5291/truth-spine/full-session',timeout=5) as response:
            if response.status!=200 or response.read()!=fixture.response():raise RuntimeError('FIXTURE_HTTP_NOT_READY')
        startup_event({'phase':'FIXTURE_READY','port':5291,'fingerprint':evidence['server_fingerprint'],'socket_inventory':socket_inventory()})
        transaction.advance('PREFLIGHT','FIXTURE_READY',pid=os.getpid())
        pre_driver=socket_inventory()
        if any(r.get('address','').endswith(':5292') for r in pre_driver['listeners']):raise RuntimeError('UNOWNED_WEBDRIVER_LISTENER')
        startup_event({'phase':'WEBDRIVER_START_REQUESTED','port':5292,'socket_inventory':pre_driver})
        driver_log=(output/'webdriver.log').open('xb')
        safari_launch_time=time.time()
        driver=subprocess.Popen([SAFARI_LAUNCHER,'--port','5292'],stdout=driver_log,stderr=driver_log)
        evidence['driver_pid']=driver.pid
        evidence['driver_fingerprint']=fingerprint(driver.pid)
        launcher_receipt=kernel_process(driver.pid)
        startup_event({'phase':'WEBDRIVER_SPAWNED_NOT_READY','fingerprint':evidence['driver_fingerprint']})
        for _ in range(40):
            if driver.poll() is not None:raise RuntimeError('WEBDRIVER_EXITED_BEFORE_READY')
            try:
                status=wd('GET','/status',timeout=1)
                inventory_now=socket_inventory()
                owners={r['pid'] for r in inventory_now['listeners'] if r.get('address','').endswith(':5292')}
                if len(owners)!=1:raise RuntimeError('SAFARI_LISTENER_OWNER_COUNT')
                current_pins={'launcher':safari_signed_artifact(SAFARI_LAUNCHER,'launcher'),'helper':safari_signed_artifact(SAFARI_HTTP_SERVICE,'helper')}
                if current_pins!=executable_pins:raise RuntimeError('SAFARI_EXECUTABLE_CHANGED')
                def observe_owner():
                    sockets=socket_inventory();owners={r['pid'] for r in sockets['listeners'] if r.get('address','').endswith(':5292')}
                    if len(owners)!=1:raise RuntimeError('SAFARI_LISTENER_OWNER_COUNT')
                    launcher=kernel_process(driver.pid);listener=kernel_process(next(iter(owners)))
                    startup_event({'phase':'KERNEL_OWNER_OBSERVED','launcher':launcher,'listener':listener,'socket_inventory':sockets})
                    if not launcher or not listener:raise RuntimeError('SAFARI_PROCESS_MISSING')
                    launcher['artifact']=safari_runtime_artifact(launcher,executable_pins,'launcher')
                    listener['artifact']=safari_runtime_artifact(listener,executable_pins,'launcher' if listener['pid']==driver.pid else 'helper')
                    return authenticate_safari_listener(sockets,launcher,listener,baseline_safari,safari_launch_time,time.time(),executable_pins,os.getuid())
                evidence['safari_ownership']=stable_safari_ownership(observe_owner,lambda x:startup_event({'phase':'SIGNED_OWNER_OBSERVATION','ownership':x}),launcher_receipt)
                if not status.get('ready'):raise RuntimeError('WEBDRIVER_NOT_READY')
                break
            except OSError: time.sleep(.1)
        else:raise RuntimeError('WEBDRIVER_READY_DEADLINE')
        if fingerprint(driver.pid)!=evidence['driver_fingerprint']:raise RuntimeError('WEBDRIVER_START_IDENTITY_CHANGED')
        startup_event({'phase':'BOTH_LISTENERS_READY','socket_inventory':socket_inventory()})
        (output/'startup.json').write_bytes(encoded({'classification':'READY','driver':evidence['driver_fingerprint'],'server':evidence['server_fingerprint'],'fixture':binding_receipt,'listeners':socket_inventory(),'webdriver_ready':status,'safari_ownership':evidence['safari_ownership']}))
        transaction.advance('FIXTURE_READY','READY',ownership=evidence['safari_ownership'])
        session=wd('POST','/session',{'capabilities':{'alwaysMatch':{'browserName':'safari'}}}); sid=session['sessionId']
        owned_window=wd('GET','/session/'+sid+'/window')
        transaction.advance('READY','BROWSER_OPEN',session_id=sid)
        url='http://127.0.0.1:5291/review/northstar-session.html?fullSession=1'
        command('POST','/url',{'url':url}); wait_for("return document.querySelector('[data-shadow-state]')?.dataset.shadowState==='CURRENT'")
        native_window=safari_fixture_window(js('return location.href'))
        evidence['native_window_receipt']={'window_id':native_window,'handle':owned_window,'url':js('return location.href'),'identity':js(CAPTURE_IDENTITY+'return displayedIdentity().binding')}
        (output/'native-window.json').write_bytes(encoded(evidence['native_window_receipt']))
        if not args.diagnose_gallery and not args.diagnose_history and not args.diagnose_decoration and not args.diagnose_dialogs and not args.diagnose_modality and not args.diagnose_keyboard_boundary:
            evidence['detector_regressions']=js(TEXT_GEOMETRY+DECORATION_GEOMETRY+r"""
const host=document.createElement('div');host.style.cssText='position:absolute;left:0;top:0;width:300px;background:black;color:white;font:16px/24px sans-serif';document.body.append(host);
const cases={};
try {
 host.innerHTML='<button style="position:relative;width:150px;height:40px;overflow:hidden"><span>Visible <b>name</b></span><i aria-hidden="true" style="position:absolute;left:250px">ICON</i></button>';
 cases.decorative=requiredText(host).clipped.length===0&&host.firstChild.scrollWidth>host.firstChild.clientWidth;
 host.innerHTML='<div style="width:10px;height:10px;overflow:hidden"><span>Required <b>complete name</b></span></div>';
 cases.realClipping=requiredText(host).clipped.length>0;
 host.innerHTML='<button style="width:140px;white-space:normal;overflow-wrap:anywhere;height:auto"><span>A very long product-market room name <b>with nested spans</b></span><i aria-hidden="true">icon</i></button>';
 cases.longNestedName=requiredText(host).clipped.length===0;
 host.innerHTML='<div style="position:relative;height:40px"><span style="position:absolute;left:0;top:0">First text</span><b style="position:absolute;left:0;top:0">Second text</b></div>';
 cases.realOverlap=requiredText(host).overlaps.length>0;
 host.innerHTML='<details><summary>Reachable disclosure</summary><p>Intentionally collapsed details</p></details>';
 cases.collapsed=requiredText(host).text.length===1;
 host.innerHTML='<div class="auction-building" style="position:relative;isolation:isolate;width:150px;height:80px"><div class="northstar-service-decoration" aria-hidden="true" style="position:absolute;inset:0;z-index:3;pointer-events:auto;background:black"></div><div class="auction-level" style="position:relative;inset:auto;z-index:1;isolation:isolate;width:150px;height:80px">Required content</div></div>';
 const bad=decorationSafety(host);
 cases.realDecorationOverlap=bad.violations.includes('DECORATION_ABOVE_CONTENT')&&bad.violations.includes('DECORATION_INTERCEPTS_POINTER');
 const scene=host.querySelector('.northstar-service-decoration');scene.style.zIndex='0';scene.style.pointerEvents='none';
 const good=decorationSafety(host);
 cases.decorativeUnderlay=good.violations.length===0&&good.layers.length===1&&good.layers[0].decoration.width>0;
 const spine=document.createElement('div');spine.className='auction-evidence-spine';host.firstChild.append(spine);
 cases.escapedSpine=decorationSafety(host).violations.includes('EVIDENCE_SPINE_ESCAPED_LAYER');
 scene.append(spine);spine.style.pointerEvents='none';
 cases.boundSpine=decorationSafety(host).violations.length===0;
 host.innerHTML='<h2 style="width:150px;position:static;font:18px/24px sans-serif;white-space:normal;overflow-wrap:anywhere">Complete long wrapped factory heading remains visible</h2>';
 cases.wrappedHeading=requiredText(host).clipped.length===0&&requiredText(host).text[0].rects.length>1;
 return cases;
} finally { host.remove(); }
""")
            if not all(evidence['detector_regressions'].values()): raise RuntimeError('DETECTOR_REGRESSION_FAILED')
            evidence['obstruction_regressions']=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+r"""
const host=document.createElement('section');host.style.cssText='position:fixed;isolation:isolate;left:0;top:0;width:300px;height:160px;z-index:100;background:black';document.body.append(host);
const style=document.createElement('style');document.head.append(style);
const cases={};
try {
 host.innerHTML='<div aria-hidden="true" class="probe-decor" style="position:absolute;inset:0;z-index:2;pointer-events:none;background:black"></div><button style="position:relative;z-index:1;width:200px;height:80px;outline:3px solid white;outline-offset:3px">Required button text</button>';
 const decor=host.firstChild,button=host.lastChild;button.focus({preventScroll:true});
 let census=obstructionCensus(host);
 cases.realText=census.violations.some(v=>v.kind==='text'&&v.relation==='ABOVE');
 cases.realControl=census.violations.some(v=>v.kind==='control'&&v.relation==='ABOVE');
 cases.realFocus=census.violations.some(v=>v.kind==='focus'&&v.relation==='ABOVE');
 decor.style.pointerEvents='auto';census=obstructionCensus(host);
 cases.pointer=census.violations.some(v=>v.pointerInterception);
 decor.style.zIndex='0';decor.style.pointerEvents='none';census=obstructionCensus(host);
 cases.harmless=census.violations.length===0&&census.layers.some(l=>l.intersections.some(i=>i.classification==='HARMLESS_UNDERLAY'));
 decor.remove();host.className='northstar-pseudo-probe';style.textContent='.northstar-pseudo-probe::after{content:"";position:absolute;left:0;top:0;width:200px;height:80px;z-index:2;background:black;pointer-events:none}';
 census=obstructionCensus(host);cases.pseudo=census.violations.some(v=>v.selector.endsWith('::after')&&v.kind==='text');
 style.textContent='';host.innerHTML='<div hidden><div aria-hidden="true" style="position:absolute;inset:0;background:black"></div><button>Inactive destination</button></div>';
 census=obstructionCensus(host);cases.hidden=census.violations.length===0&&census.hiddenInactive.length===3;
 host.firstChild.hidden=false;census=obstructionCensus(host);cases.activation=census.violations.length>0;
 return cases;
} finally {host.remove();style.remove();}
""")
            if not all(evidence['obstruction_regressions'].values()):raise RuntimeError('OBSTRUCTION_DETECTOR_REGRESSION_FAILED')
            evidence['typography_focus_regressions']=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+DIALOG_GEOMETRY+r"""
const host=document.createElement('section');host.style.cssText='position:fixed;left:0;top:0;width:300px;height:500px;z-index:100;background:#100c08;color:white;isolation:isolate';document.body.append(host);
const cases={};
try {
 for(const [label,width,text] of [['one',280,'Radar'],['two',280,'Governed shadow station'],['multi',150,'Governed shadow station evidence · CURRENT']]){
  host.innerHTML='<h2></h2><p>Complete required explanation below the heading.</p>';
  const h=host.firstChild;h.style.cssText='font:36px/1.4 Georgia;letter-spacing:normal;margin:0 0 16px;height:auto;overflow:visible;overflow-wrap:anywhere;width:'+width+'px';h.textContent=text;
  const measured=headingTypography(host)[0];cases[label]=measured.lineOverlaps.length===0&&requiredText(host).overlaps.length===0&&(label==='one'?measured.lines.length===1:label==='two'?measured.lines.length===2:measured.lines.length>=3);
 }
 host.firstChild.style.lineHeight='.92';cases.realHeadingOverlap=headingTypography(host)[0].lineOverlaps.length>0;
 host.innerHTML='<div style="position:relative;width:280px;height:90px;overflow:auto;margin:10px"><button style="width:200px;height:40px;margin:12px;outline:3px solid #edc88b;outline-offset:3px">Focusable proof</button></div>';
 const scroll=host.firstChild,button=scroll.firstChild;button.focus({preventScroll:true});
 cases.visibleRing=focusMeasurement(host).failures.length===0;
 button.style.outlineStyle='none';cases.missingRing=focusMeasurement(host).failures.includes('FOCUS_INDICATOR_MISSING');button.style.outlineStyle='solid';
 button.style.marginLeft='0';cases.clippedRing=focusMeasurement(host).failures.includes('FOCUS_INDICATOR_CLIPPED');button.style.marginLeft='12px';
 const cover=document.createElement('div');cover.className='northstar-dialog-header';cover.style.cssText='position:absolute;inset:0;background:black;z-index:2';host.append(cover);
 cases.coveredRing=focusMeasurement(host).failures.includes('FOCUS_INDICATOR_COVERED');cover.remove();
 const decor=document.createElement('div');decor.setAttribute('aria-hidden','true');decor.style.cssText='position:absolute;inset:0;background:black;z-index:2;pointer-events:none';host.append(decor);
 cases.decorativeRing=focusMeasurement(host).failures.includes('FOCUS_INDICATOR_COVERED');decor.remove();
 button.style.outlineColor='#100c08';cases.lowContrast=focusMeasurement(host).failures.includes('FOCUS_CONTRAST_UNPROVEN');
 return cases;
} finally {host.remove();}
""")
            if not all(evidence['typography_focus_regressions'].values()):raise RuntimeError('TYPOGRAPHY_FOCUS_DETECTOR_REGRESSION_FAILED')
            polling_proof('before-navigation')
        for width in [1512,1020,386]:
            command('POST','/window/rect',{'width':width,'height':950,'x':0,'y':30})
            for _ in range(5):
                dimensions=js('return {iw:innerWidth,ih:innerHeight,ow:outerWidth,oh:outerHeight}')
                if dimensions['iw']==width and dimensions['ih']==825: break
                w=width+dimensions['ow']-dimensions['iw']; h=825+dimensions['oh']-dimensions['ih']
                subprocess.run(['/usr/bin/osascript','-e',f'tell application "Safari"\nif name of front window contains "Northstar" then set bounds of front window to {{0, 30, {w}, {30+h}}}\nend tell'],check=True,capture_output=True)
                time.sleep(.15)
            click('Gallery')
            if args.diagnose_keyboard_boundary:
                modality_observer()
                # Separate disposable browser probes, not canonical fixture/card
                # mutation. Setup focus is explicitly programmatic; following
                # native keys test implicit versus explicit button tab eligibility.
                js("const p=document.createElement('div');p.id='keyboard-boundary-probe';p.style.cssText='position:fixed;top:12px;left:12px;z-index:100;background:black;color:white';p.innerHTML='<button>Implicit native button probe</button><button tabindex=\"0\">Explicit native button probe</button>';document.body.append(p);p.firstChild.focus();")
                probes=[]
                for _ in range(4):
                    native_key('\ue004');settle('native-button-probe')
                    probes.append(js("return {tag:document.activeElement.tagName,name:document.activeElement.textContent.slice(0,100),tabindex:document.activeElement.getAttribute('tabindex'),events:window.__modalityEvents.slice(-4)}"))
                evidence.setdefault('native_button_probes',[]).append({'width':width,'steps':probes})
                js("document.getElementById('keyboard-boundary-probe').remove()")
                for method in ['element-tab','actions-option-tab']:
                    for reverse in [False,True]:
                        seen=[];trace=[]
                        for step in range(120):
                            if method=='element-tab':
                                active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
                                command('POST','/element/'+active+'/value',{'text':('\ue008' if reverse else '')+'\ue004\ue000'})
                            else:
                                keys=[{'type':'keyDown','value':'\ue00a'}]+([{'type':'keyDown','value':'\ue008'}] if reverse else [])+[{'type':'keyDown','value':'\ue004'},{'type':'keyUp','value':'\ue004'}]+([{'type':'keyUp','value':'\ue008'}] if reverse else [])+[{'type':'keyUp','value':'\ue00a'}]
                                command('POST','/actions',{'actions':[{'type':'key','id':'boundary-keyboard','actions':keys}]})
                            settle('keyboard-boundary:'+method)
                            identity=js("return {station:document.activeElement.dataset?.roomId||null,tag:document.activeElement.tagName,name:document.activeElement.getAttribute('aria-label')||document.activeElement.textContent.slice(0,100)}")
                            trace.append(identity)
                            if identity['station'] and identity['station'] not in seen:
                                seen.append(identity['station']);card_measure(method+('-reverse' if reverse else '-forward'),width,identity['station'])
                            if len(seen)==18:break
                        evidence.setdefault('keyboard_boundary',[]).append({'width':width,'method':method,'reverse':reverse,'seen':seen,'trace':trace})
                        (output/'measurements.json').write_bytes(encoded(evidence))
                evidence['classification']='DIAGNOSTIC_ONLY'
                continue
            if args.diagnose_settlement:
                gallery_audit(width)
                evidence['classification']='DIAGNOSTIC_ONLY';return
            if args.diagnose_modality:
                modality_diagnosis(width)
                evidence['classification']='DIAGNOSTIC_ONLY'
                continue
            if args.diagnose_dialogs:
                ids=js("return [...document.querySelectorAll('[data-room-id]')].map(e=>e.dataset.roomId)")
                if len(ids)!=18 or len(set(ids))!=18:raise RuntimeError('STATION_INVENTORY_INVALID')
                for station in ids:
                    element=js("const e=document.querySelector('[data-room-id='+"+json.dumps(station)+"+']');e.scrollIntoView({block:'center',behavior:'instant'});return e;")
                    command('POST','/element/'+element['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
                    wait_for("return !!document.querySelector('.auction-room-modal')")
                    for position in ['top','bottom']:
                        if position=='bottom':
                            command('POST','/actions',{'actions':[{'type':'key','id':'diagnostic-keyboard','actions':[{'type':'keyDown','value':'\ue008'},{'type':'keyDown','value':'\ue004'},{'type':'keyUp','value':'\ue004'},{'type':'keyUp','value':'\ue008'}]}]})
                        settle('dialog-diagnostic:'+station+':'+position)
                        name=f'{width}-{station}-{position}'
                        data=js(TEXT_GEOMETRY+DIALOG_GEOMETRY+'return dialogMeasurement()')
                        data['focus']=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+DIALOG_GEOMETRY+"return focusMeasurement(document.querySelector('.northstar-station-dialog'))")
                        data['beforeIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
                        (output/(name+'.png')).write_bytes(base64.b64decode(command('GET','/screenshot')))
                        data['afterIdentity']=js(CAPTURE_IDENTITY+'return displayedIdentity()')
                        if data['beforeIdentity']['binding']!=data['afterIdentity']['binding']:raise RuntimeError('DIAGNOSTIC_GENERATION_CHANGED')
                        (output/(name+'.json')).write_bytes(encoded(data))
                        surface=js("return document.querySelector('.auction-room-modal > section')")
                        (output/(name+'-crop.png')).write_bytes(base64.b64decode(command('GET','/element/'+surface['element-6066-11e4-a52e-4f735466cecf']+'/screenshot')))
                    active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
                    command('POST','/element/'+active+'/value',{'text':'\ue00c'})
                    wait_for("return !document.querySelector('.auction-room-modal')&&document.activeElement.dataset.roomId==="+json.dumps(station))
                evidence['classification']='DIAGNOSTIC_ONLY'
                continue
            if args.diagnose_decoration:
                for destination in ['Gallery','Story','Replay','Command','Cases','Expansion Wing','Factory Watch']:
                    click(destination)
                    targets=['monitoring','learning','judgment'] if destination=='Gallery' else [None]
                    for target in targets:
                        if target:
                            js("const e=document.querySelector('[data-room-id='+"+json.dumps(target)+"+']');e.scrollIntoView({block:'center',behavior:'instant'});e.focus({preventScroll:true});")
                        settle('decoration-diagnostic:'+destination+':'+str(target))
                        name=str(width)+'-'+destination.lower().replace(' ','-')+'-'+str(target)
                        census=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+"return obstructionCensus(document.querySelector('.northstar-full-session'))")
                        before_identity=js(CAPTURE_IDENTITY+'return displayedIdentity()')
                        (output/(name+'.png')).write_bytes(base64.b64decode(command('GET','/screenshot')))
                        after_identity=js(CAPTURE_IDENTITY+'return displayedIdentity()')
                        if before_identity['binding']!=after_identity['binding']:raise RuntimeError('DIAGNOSTIC_GENERATION_CHANGED')
                        (output/(name+'-census.json')).write_bytes(encoded({'destination':destination,'target':target,'beforeIdentity':before_identity,'afterIdentity':after_identity,'census':census}))
                        evidence.setdefault('decoration_diagnostics',[]).append({'name':name,'width':width,'violations':len(census['violations'])})
                        if target:
                            element=js("return document.querySelector('[data-room-id='+"+json.dumps(target)+"+']')")
                            (output/(name+'-crop.png')).write_bytes(base64.b64decode(command('GET','/element/'+element['element-6066-11e4-a52e-4f735466cecf']+'/screenshot')))
                            command('POST','/element/'+element['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
                            wait_for("return !!document.querySelector('.auction-room-modal')")
                            settle('diagnostic-dialog:'+target)
                            dialog_census=js(TEXT_GEOMETRY+OBSTRUCTION_GEOMETRY+"return obstructionCensus(document.querySelector('.northstar-full-session'))")
                            (output/(name+'-dialog-census.json')).write_bytes(encoded(dialog_census))
                            (output/(name+'-dialog.png')).write_bytes(base64.b64decode(command('GET','/screenshot')))
                            active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
                            command('POST','/element/'+active+'/value',{'text':'\ue00c'})
                            wait_for("return !document.querySelector('.auction-room-modal')&&document.activeElement.dataset.roomId==="+json.dumps(target))
                if width==386:evidence['classification']='DIAGNOSTIC_ONLY'
                continue
            if args.diagnose_history:
                js(r"""window.__events=[];
const describe=e=>e instanceof Element?{tag:e.tagName,role:e.getAttribute('role'),text:e.textContent.slice(0,100),group:e.closest('[data-coverage]')?.dataset.coverage,selected:!!e.closest('.northstar-selected')}:null;
window.__state=()=>({hash:location.hash,active:describe(document.activeElement),panels:[...document.querySelectorAll('.northstar-selected')].map(e=>({group:e.closest('[data-coverage]').dataset.coverage,title:e.querySelector('h3').textContent,openDisclosures:e.querySelectorAll('details[open]').length})),expanded:[...document.querySelectorAll('button[aria-expanded=true]')].map(describe)});
for(const capture of [true,false])for(const type of ['keydown','keyup','focusin','click'])document.addEventListener(type,e=>window.__events.push({type,capture,key:e.key,code:e.code,isTrusted:e.isTrusted,defaultPrevented:e.defaultPrevented,target:describe(e.target),state:window.__state()}),capture);
for(const type of ['hashchange','popstate'])window.addEventListener(type,()=>window.__events.push({type,state:window.__state()}));
const push=history.pushState;history.pushState=function(...args){window.__events.push({type:'pushState',url:args[2],state:window.__state()});try{return push.apply(this,args);}catch(e){window.__events.push({type:'history-error',name:e.name,message:e.message,state:window.__state()});throw e;}};
""")
                # Repeat the actual C1 navigation/selection path before history,
                # not merely a fresh direct Cases visit.
                capture('diagnostic-gallery',width); inspect_group('rooms',24,width)
                for name in ['Story','Replay','Command']:
                    click(name); capture('diagnostic-'+name.lower(),width)
                inspect_group('agents',8,width); inspect_group('governance',3,width); inspect_group('subsystems',7,width)
                click('Cases'); capture('diagnostic-cases',width)
                labels=js("return [...document.querySelectorAll('[data-coverage=history] button')].map(e=>e.textContent)")
                evidence['history_diagnosis']=[]
                for index,label in enumerate(labels*3):
                    evidence['diagnostic_step']={'index':index,'label':label,'operation':'open'}
                    click(label); wait_for("return document.activeElement.tagName==='H3'")
                    opened=js('return window.__state()')
                    summary=js("return document.querySelector('.northstar-selected summary')")
                    command('POST','/element/'+summary['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
                    before=js('return window.__state()')
                    evidence['diagnostic_step']={'index':index,'label':label,'operation':'escape'}
                    if index==0: capture('diagnostic-history-selected',width)
                    active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
                    command('POST','/element/'+active+'/value',{'text':'\ue00c'})
                    until=time.monotonic()+2
                    while js("return !!document.querySelector('.northstar-selected')") and time.monotonic()<until: time.sleep(.05)
                    after=js('return window.__state()')
                    evidence['history_diagnosis'].append({'label':label,'opened':opened,'before_escape':before,'after_escape':after,'events':js('return window.__events.splice(0)')})
                    (output/f'history-{index}.png').write_bytes(base64.b64decode(command('GET','/screenshot')))
                    if after['panels']:
                        # Observe a second native Escape and focused-panel delivery,
                        # without changing application state or swallowing errors.
                        command('POST','/actions',{'actions':[{'type':'key','id':'diagnostic-keyboard','actions':[{'type':'keyDown','value':'\ue00c'},{'type':'keyUp','value':'\ue00c'}]}]})
                        time.sleep(.4)
                        evidence['history_diagnosis'][-1]['actions_escape']={'state':js('return window.__state()'),'events':js('return window.__events.splice(0)')}
                        break
                evidence['classification']='DIAGNOSTIC_ONLY'; return
            if args.diagnose_gallery:
                evidence['gallery_diagnosis']=[]
                for index in range(18):
                    js(f"document.querySelectorAll('.auction-room')[{index}].scrollIntoView({{block:'center'}})")
                    time.sleep(.1)
                    detail=js(TEXT_GEOMETRY+f"const e=document.querySelectorAll('.auction-room')[{index}];e.focus({{preventScroll:true}});return {{id:e.dataset.roomId,accessibleName:e.getAttribute('aria-label'),viewport:[innerWidth,innerHeight],rect:e.getBoundingClientRect().toJSON(),client:[e.clientWidth,e.clientHeight],scroll:[e.scrollWidth,e.scrollHeight],required:requiredText(e),decorativeGeometry:[...e.querySelectorAll('[aria-hidden=true],.auction-room__character')].map(x=>({{className:x.className,ariaHidden:x.getAttribute('aria-hidden'),rect:x.getBoundingClientRect().toJSON()}})),focus:document.activeElement===e,outline:getComputedStyle(e).outlineStyle}};")
                    evidence['gallery_diagnosis'].append(detail)
                    (output/('diagnose-'+detail['id']+'.png')).write_bytes(base64.b64decode(command('GET','/screenshot')))
                    (output/'measurements.json').write_bytes(encoded(evidence))
                evidence['classification']='DIAGNOSTIC_ONLY'; return
            gallery_audit(width)
            capture(f'{width}-gallery',width)
            js("document.querySelector('.auction-house-mark').scrollIntoView({block:'center',behavior:'instant'})")
            capture(f'{width}-heading',width)
            heading=js("return document.querySelector('.auction-house-mark')")
            crop_before=js(CAPTURE_IDENTITY+'return displayedIdentity()')
            crop_start=datetime.now(timezone.utc).isoformat()
            (output/f'{width}-heading-crop.png').write_bytes(base64.b64decode(command('GET','/element/'+heading['element-6066-11e4-a52e-4f735466cecf']+'/screenshot')))
            crop_after=js(CAPTURE_IDENTITY+'return displayedIdentity()')
            crop={'name':f'{width}-heading-crop','beforeIdentity':crop_before,'afterIdentity':crop_after,'screenshot_start':crop_start,'screenshot_end':datetime.now(timezone.utc).isoformat()}
            if crop_before['binding']!=crop_after['binding']:
                evidence.setdefault('rejected_captures',[]).append(crop);raise RuntimeError('SCREENSHOT_GENERATION_CHANGED:heading-crop')
            evidence.setdefault('element_captures',[]).append(crop)
            timeline=js("return document.querySelector('.northstar-session-status summary')")
            command('POST','/element/'+timeline['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
            if not js("return document.querySelector('.northstar-session-status details').open&&document.querySelector('.northstar-session-status ol').children.length>1"): raise RuntimeError('SESSION_TIMELINE_UNREACHABLE')
            capture(f'{width}-timeline',width)
            command('POST','/element/'+timeline['element-6066-11e4-a52e-4f735466cecf']+'/click',{})
            inspect_group('rooms',24,width)
            for name in ['Story','Replay','Command','Cases','Expansion Wing','Factory Watch']:
                click(name); time.sleep(.15); capture(f'{width}-'+name.lower().replace(' ','-'),width)
                if name=='Command':
                    inspect_group('agents',8,width); inspect_group('governance',3,width); inspect_group('subsystems',7,width)
                    if not js("return document.querySelector('[data-coverage=day-trading]').textContent.includes('OBSERVATION_ONLY')&&document.querySelector('[data-coverage=day-trading]').textContent.includes('LOCKED')"): raise RuntimeError('DAY_TRADING_MISSING')
                if name=='Cases':
                    inspect_group('history',14,width)
                    if not js("return document.body.textContent.includes('517-member universe')&&document.body.textContent.includes('518-member universe')"): raise RuntimeError('UNIVERSES_MISSING')
                if name=='Factory Watch': inspect_group('routes',10,width)
            click('Expansion Wing')
            labels=inspect_group('rooms',24,width)
            click(labels[0]); command('POST','/back',{}); wait_for("return !document.querySelector('.northstar-selected')")
            command('POST','/forward',{}); wait_for("return !!document.querySelector('.northstar-selected')")
            command('POST','/refresh',{}); wait_for("return !!document.querySelector('.northstar-selected')&&document.querySelector('[data-shadow-state]').dataset.shadowState==='CURRENT'")
            polling_proof(str(width)+'-after-refresh')
            # Traverse two different selections rather than only one repeated URL.
            click(labels[1]); command('POST','/back',{}); wait_for("return document.querySelector('.northstar-selected h3')?.textContent==="+json.dumps(labels[0].removeprefix('Inspect ')))
            command('POST','/forward',{}); wait_for("return document.querySelector('.northstar-selected h3')?.textContent==="+json.dumps(labels[1].removeprefix('Inspect ')))
            active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
            command('POST','/element/'+active+'/value',{'text':'\ue00c'})
            wait_for("return document.querySelector('.northstar-selected h3')?.textContent==="+json.dumps(labels[0].removeprefix('Inspect ')))
            active=command('GET','/element/active')['element-6066-11e4-a52e-4f735466cecf']
            command('POST','/element/'+active+'/value',{'text':'\ue00c'})
            wait_for("return document.activeElement.textContent==="+json.dumps(labels[0]))
            click('Gallery');plaque_audit(width)
            lifecycle_audit(width)
            click('Command'); wait_for("return document.querySelectorAll('[data-coverage=agents] article').length===8&&document.querySelectorAll('[data-coverage=governance] article').length===3")
            js('window.__northstarFixture.clock.offset=16000'); wait_for("return document.querySelector('[data-shadow-state]').dataset.shadowState==='STALE'",10)
            js('window.scrollTo(0,document.body.scrollHeight)'); capture(f'{width}-stale-scrolled',width)
            scenario['mode']='unavailable'; command('POST','/refresh',{}); wait_for("return document.querySelector('[data-shadow-state]')?.dataset.shadowState==='UNAVAILABLE'")
            capture(f'{width}-unavailable',width)
            scenario['mode']='current'; wait_for("return document.querySelector('[data-shadow-state]').dataset.shadowState==='CURRENT'",12)
        if {r['path'] for r in requests}-set(files)-{'/truth-spine/full-session','/favicon.ico'}: raise RuntimeError('UNEXPECTED_BROWSER_ROUTE')
        evidence.update(classification='DIAGNOSTIC_ONLY' if any([args.diagnose_gallery,args.diagnose_history,args.diagnose_decoration,args.diagnose_dialogs,args.diagnose_modality,args.diagnose_keyboard_boundary]) else 'GREEN',requests=requests,provider=0,model=0,credential=0,broker=0,paper=0)
    except Exception as exc:
        evidence['failure']=str(exc)[:500]
        startup_event({'phase':'INCIDENT','category':type(exc).__name__,'reason':str(exc)[:160],'socket_inventory':socket_inventory()})
        if sid:
            try:
                evidence['failure_dom']=js("return {state:window.__state?.(),events:window.__events,activeTag:document.activeElement.tagName,activeText:document.activeElement.textContent.slice(0,120),hash:location.hash,panels:[...document.querySelectorAll('.northstar-selected')].map(e=>e.querySelector('h3')?.textContent),errors:window.__northstarErrors||[]}")
                # Failure-only diagnostic, never passed to admit_capture or
                # acceptance totals. A broken settlement must not erase evidence.
                raw=base64.b64decode(wd('GET','/session/'+sid+'/screenshot',timeout=8))
                (output/'diagnostic-NOT-ACCEPTED.png').write_bytes(raw)
                evidence['diagnostic_image']={'classification':'DIAGNOSTIC_ONLY_NOT_ACCEPTED','sha256':hashlib.sha256(raw).hexdigest()}
            except Exception: evidence['failure_dom_unavailable']=True
        raise
    finally:
        evidence['requests']=requests
        def browser_errors():
            if sid: evidence['final_browser_errors']=js('return window.__northstarErrors||[]')
        def close_session():
            if sid: wd('DELETE','/session/'+sid)
        def close_driver():
            if driver is not None and driver.poll() is None:
                identity_now=fingerprint(driver.pid)
                evidence['driver_shutdown_fingerprint']=identity_now
                current=kernel_process(driver.pid)
                if not current or current!=launcher_receipt:raise RuntimeError('SAFARI_SHUTDOWN_RECEIPT_MISMATCH_NO_SIGNAL')
                safari_runtime_artifact(current,executable_pins,'launcher')
                stop_verified_process(driver,evidence.get('driver_fingerprint'),fingerprint)
        def close_server():
            if server is None:return
            evidence['server_shutdown_fingerprint']=fingerprint(os.getpid())
            if evidence['server_shutdown_fingerprint'] != evidence.get('server_fingerprint'):
                raise RuntimeError('SERVER_IDENTITY_MISMATCH')
            if thread is not None:server.shutdown()
        def ports_clear():
            observations=[]
            def record_observation(row):
                observations.append(row);(output/'shutdown-sockets.json').write_bytes(encoded(observations))
            stable_port_clear(record_observation,reject_listener=False)
            evidence['port_5291_closed']=evidence['port_5292_closed']=True
        def owned_exit():
            owned={driver.pid} if driver else set()
            ownership=evidence.get('safari_ownership')
            if ownership:owned.add(ownership['listener']['pid'])
            deadline=time.monotonic()+5
            while True:
                rows=[p for pid in owned if (p:=kernel_process(pid)) is not None]
                evidence['owned_exit_observation']={'at':time.monotonic(),'remaining':rows}
                (output/'owned-exit.json').write_bytes(encoded(evidence['owned_exit_observation']))
                if not rows:return
                if time.monotonic()>=deadline:raise RuntimeError('OWNED_SAFARI_PROCESS_REMAINS_NO_SIGNAL')
                time.sleep(.1)
        cleanup=independent_cleanup([
            ('precleanup_evidence',lambda:(output/'precleanup.json').write_bytes(encoded(evidence))),
            ('browser_errors',browser_errors),('session',close_session),('driver',close_driver),
            ('server',close_server),('server_socket',lambda:server.server_close() if server else None),
            ('server_thread',lambda:thread.join(timeout=5) if thread else None),
            ('driver_log',lambda:driver_log.close() if driver_log else None),('ports',ports_clear),('owned_exit',owned_exit)])
        evidence['cleanup']=cleanup
        if not all(step['ok'] for step in cleanup) or (thread and thread.is_alive()) or evidence.get('final_browser_errors'):
            evidence['classification']='RED'
        # Independent persistence destinations: failure in the aggregate writer
        # must not suppress the cleanup receipt, or vice versa.
        writes=independent_cleanup([
            ('transaction',lambda:transaction.advance(transaction.state,'CLOSED',classification=evidence['classification'],cleanup=cleanup)),
            ('measurements',lambda:(output/'measurements.json').write_bytes(encoded(evidence))),
            ('cleanup_receipt',lambda:(output/'cleanup.json').write_bytes(encoded({'classification':evidence['classification'],'steps':cleanup})))])
        if not all(step['ok'] for step in writes):
            evidence['classification']='RED'
            print(json.dumps({'classification':'RED','failure':'EVIDENCE_PERSISTENCE_FAILED','writes':writes}),flush=True)
            raise RuntimeError('EVIDENCE_PERSISTENCE_FAILED')
    print(json.dumps({'classification':evidence['classification'],'captures':len(evidence['captures']),'output':str(output)}))


if __name__ == '__main__': main()
