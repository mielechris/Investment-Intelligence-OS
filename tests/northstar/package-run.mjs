// Future bounded transaction. Importing this module starts nothing.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn,execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { sha,contentHash,newJSON,canonical } from './package-contract.mjs';

const ownerFields=['pid','parent','group','start','executable','executableHash','command','cwd','packageRoot','port','startupReceipt'];
export function sameOwner(expected,observed){return !!expected && !!observed && ownerFields.every(k=>
  expected[k]!==undefined && observed[k]===expected[k]) && Object.keys(expected).length===ownerFields.length && Object.keys(observed).length===ownerFields.length;}
export async function cleanupRecords(records,deps){
  const errors=[],attempts=[],remaining=[];
  async function record(value){attempts.push(value);try{await deps.persist(value);}catch{errors.push('CLEANUP_EVIDENCE_WRITE_FAILED');}}
  async function verified(entry){
    const receipt=await deps.readStartup(entry);
    assert.equal(contentHash(receipt),entry.fingerprint.startupReceipt,'STARTUP_RECEIPT_CHANGED');
    assert.deepEqual(receipt.fingerprint,Object.fromEntries(Object.entries(entry.fingerprint).filter(([k])=>k!=='startupReceipt')));
    const observed=await deps.inspect(entry);
    if(observed!==null)assert(sameOwner(entry.fingerprint,observed),'PROCESS_FINGERPRINT_MISMATCH');
    return observed;
  }
  for(const signal of ['SIGTERM','SIGKILL']){
    for(const entry of [...records].reverse()){
      try{
        if(await verified(entry)!==null){await deps.signal(entry.fingerprint.pid,signal);await record({pid:entry.fingerprint.pid,signal,result:'SENT'});}
      }catch{errors.push('IDENTITY_OR_CLEANUP_FAILED');await record({pid:entry.fingerprint.pid,signal,result:'FAILED_CLOSED'});}
    }
    try{await deps.pause(signal==='SIGTERM'?5000:1000);}catch{errors.push('CLEANUP_WAIT_FAILED');}
  }
  for(const entry of records){
    try{if(await verified(entry)!==null)remaining.push(entry.fingerprint);}
    catch{remaining.push(entry.fingerprint);errors.push('FINAL_IDENTITY_UNRESOLVED');}
  }
  let listenersStable=false;
  try{
    const first=await deps.listeners();await deps.pause(250);const second=await deps.listeners();
    assert.deepEqual(first,deps.expectedListeners);assert.deepEqual(second,first);listenersStable=true;
    await record({result:'LISTENER_OWNERS_STABLE',first,second});
  }catch{errors.push('LISTENER_OWNERSHIP_UNRESOLVED');}
  return {remaining,errors,attempts,listenersStable};
}
export function acceptedResults(result,cleanup){
  return result.expected===9 && result.unexpected===0 && result.skipped===0 && result.flaky===0 &&
    cleanup.exitCode===0 && cleanup.remaining.length===0 && cleanup.errors.length===0 && cleanup.listenersStable===true;
}
function processes(){
  return execFileSync('/bin/ps',['-axo','pid=,ppid=,pgid=,lstart=,comm='],{encoding:'utf8',env:{PATH:'/usr/bin:/bin',LC_ALL:'C',TZ:'UTC'},timeout:5000})
    .split('\n').flatMap(s=>{const m=s.trim().match(/^(\d+)\s+(\d+)\s+(\d+)\s+(.{24})\s+(.+)$/);return m?[{pid:Number(m[1]),parent:Number(m[2]),group:Number(m[3]),start:m[4],executable:m[5]}]:[];});
}
function inspectOwned(row,contract,startupReceipt){
  const env={PATH:'/usr/bin:/bin',LC_ALL:'C',TZ:'UTC'};
  const command=execFileSync('/bin/ps',['-ww','-p',String(row.pid),'-o','command='],{encoding:'utf8',env,timeout:1000}).trim();
  const cwdRows=execFileSync('/usr/sbin/lsof',['-a','-p',String(row.pid),'-d','cwd','-Fn'],{encoding:'utf8',env,timeout:1000})
    .split('\n').filter(x=>x.startsWith('n'));
  assert.equal(cwdRows.length,1);const cwd=fs.realpathSync(cwdRows[0].slice(1));
  const executable=fs.realpathSync(row.executable);
  return {...row,executable,executableHash:sha(fs.readFileSync(executable)),command,cwd,
    packageRoot:contract.packageRoot,port:Number(new URL(contract.origin).port),startupReceipt};
}
function listenerOwners(port){
  const output=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+port,'-sTCP:LISTEN','-Fpn'],{encoding:'utf8',timeout:1000});
  let pid;return output.split('\n').flatMap(line=>{if(line.startsWith('p'))pid=Number(line.slice(1));
    return line.startsWith('n')?[{pid,address:line.slice(1)}]:[];});
}
export async function run(contractFile,contractHash,evidence,duration='1800'){
  const seconds=Number(duration);assert(Number.isInteger(seconds) && seconds>0 && seconds<=1800,'BOUNDED_DURATION_REQUIRED');
  assert(!fs.existsSync(evidence),'NEW_EVIDENCE_ROOT_REQUIRED');
  const contract=JSON.parse(fs.readFileSync(contractFile));assert.equal(contentHash(contract),contractHash);
  assert.equal(contract.fixtureOnly,false);assert(path.isAbsolute(evidence));
  assert(evidence.startsWith('/private/tmp/iios-truth-spine-3-acceptance-sb38d-clean-') && evidence.includes('/browser/'),'RUN_ROOT_REQUIRED');
  assert.equal(evidence,path.join(contract.packageRoot,'browser/run'),'EXACT_BROWSER_ROOT_REQUIRED');
  assert.equal(fs.realpathSync(path.dirname(evidence)),path.dirname(evidence),'BROWSER_ROOT_ALIAS');
  fs.mkdirSync(evidence,{mode:0o700});
  const here=path.dirname(fileURLToPath(import.meta.url));
  const env={PATH:'/usr/bin:/bin',TMPDIR:evidence,
    PLAYWRIGHT_BROWSERS_PATH:process.env.PLAYWRIGHT_BROWSERS_PATH,
    NORTHSTAR_PACKAGE_CONTRACT:contractFile,NORTHSTAR_PACKAGE_CONTRACT_HASH:contractHash,NORTHSTAR_PACKAGE_EVIDENCE:evidence};
  assert(env.PLAYWRIGHT_BROWSERS_PATH,'PINNED_BROWSER_CACHE_REQUIRED');
  const log=fs.createWriteStream(path.join(evidence,'runner.log'),{fd:fs.openSync(path.join(evidence,'runner.log'),'wx',0o600)});
  const child=spawn(process.execPath,[path.join(here,'node_modules/playwright/cli.js'),'test','--config',path.join(here,'package.playwright.config.mjs'),'--max-failures=1'],
    {cwd:here,env,detached:true,stdio:['ignore','pipe','pipe']});
  child.stdout.pipe(log,{end:false});child.stderr.pipe(log,{end:false});
  const owned=new Map(),errors=[];
  function observe(){const all=processes(),ids=new Set([child.pid]);for(let n=0;n<16;n++)for(const r of all)if(ids.has(r.parent))ids.add(r.pid);
    for(const r of all)if(ids.has(r.pid) || r.group===child.pid){
      const key=r.pid+':'+r.start;if(owned.has(key))continue;
      const observed=inspectOwned(r,contract,'PENDING');delete observed.startupReceipt;
      assert(observed.cwd===here || observed.cwd===evidence,'BROWSER_CWD_NOT_OWNED');
      assert(observed.executable===fs.realpathSync(process.execPath) || observed.executable.startsWith(fs.realpathSync(env.PLAYWRIGHT_BROWSERS_PATH)+'/'),'BROWSER_EXECUTABLE_NOT_PINNED_ROOT');
      assert.equal(observed.executableHash,contract.browserExecutables[observed.executable],'BROWSER_EXECUTABLE_PIN_MISMATCH');
      const record={schema:'iios-browser-observed-startup-v1',fingerprint:observed,packageHash:contract.expected.package_hash,
        backendHash:contract.expected.backend_instance_hash,contractHash};
      const receipt={...record,content_hash:contentHash(record)},file=path.join(evidence,'startup-'+r.pid+'-'+sha(r.start).slice(0,16)+'.json');
      newJSON(file,receipt);
      owned.set(key,{fingerprint:{...observed,startupReceipt:receipt.content_hash},file,receiptHash:sha(canonical(receipt))});
    }return all;}
  function stop(signal='SIGTERM'){
    for(const entry of [...owned.values()].reverse()) {
      try{
        const expected=entry.fingerprint,current=processes().find(r=>r.pid===expected.pid);
        if(!current)continue;
        assert.equal(sha(fs.readFileSync(entry.file)),entry.receiptHash);
        if(sameOwner(expected,inspectOwned(current,contract,expected.startupReceipt)))process.kill(expected.pid,signal);
        else errors.push('UNVERIFIED_CHILD_NOT_SIGNALED');
      }catch{errors.push('INDIVIDUAL_STOP_FAILED');}
    }
  }
  try{observe();}catch{errors.push('INITIAL_PROCESS_INSPECTION_FAILED');}
  const polling=setInterval(()=>{try{observe();}catch{errors.push('PROCESS_INSPECTION_FAILED');}},1000);
  let deadline,expired=false,resolveSignal;
  const interrupted=new Promise(resolve=>{resolveSignal=resolve;});
  const onSignal=()=>{expired=true;try{stop();}catch{errors.push('SIGNAL_CLEANUP_FAILED');}finally{resolveSignal(null);}};
  process.once('SIGTERM',onSignal);process.once('SIGINT',onSignal);
  const exitCode=await Promise.race([
    interrupted,
    new Promise(resolve=>{child.once('error',()=>resolve(1));child.once('exit',code=>resolve(code));}),
    new Promise(resolve=>{deadline=setTimeout(()=>{onSignal();resolve(null);},seconds*1000);})]);
  clearInterval(polling);clearTimeout(deadline);
  let sequence=0;
  const cleanupProof=await cleanupRecords([...owned.values()],{
    inspect:entry=>{const r=processes().find(x=>x.pid===entry.fingerprint.pid);return r?inspectOwned(r,contract,entry.fingerprint.startupReceipt):null;},
    readStartup:entry=>{const bytes=fs.readFileSync(entry.file);assert.equal(sha(bytes),entry.receiptHash);return JSON.parse(bytes);},
    signal:(pid,signal)=>process.kill(pid,signal),pause:ms=>new Promise(resolve=>setTimeout(resolve,ms)),
    listeners:()=>listenerOwners(Number(new URL(contract.origin).port)),
    expectedListeners:[{pid:contract.backendStartup.observation.pid,address:new URL(contract.origin).host}],
    persist:entry=>newJSON(path.join(evidence,'cleanup-attempt-'+String(sequence++).padStart(4,'0')+'.json'),entry),
  });
  process.removeListener('SIGTERM',onSignal);process.removeListener('SIGINT',onSignal);
  child.stdout.unpipe(log);child.stderr.unpipe(log);child.stdout.destroy();child.stderr.destroy();child.unref();
  await new Promise(resolve=>log.end(resolve));
  if(expired)errors.push('BROWSER_DEADLINE_EXCEEDED');
  const cleanup={...cleanupProof,exitCode,errors:[...errors,...cleanupProof.errors]};
  try{if(processes().some(r=>r.group===child.pid))cleanup.errors.push('BROWSER_PROCESS_GROUP_NOT_EMPTY');}
  catch{cleanup.errors.push('BROWSER_FINAL_CENSUS_FAILED');}
  newJSON(path.join(evidence,'cleanup.json'),cleanup);
  const results=JSON.parse(fs.readFileSync(path.join(evidence,'results.json')));
  const rows=fs.readdirSync(evidence,{recursive:true}).sort().flatMap(name=>{
    const p=path.join(evidence,name);assert(!fs.lstatSync(p).isSymbolicLink());if(fs.statSync(p).isDirectory())return [];
    const b=fs.readFileSync(p);return [{path:name,bytes:b.length,sha256:sha(b)}];});
  const receipt={schema:'iios-package-browser-evidence-v1',contract:contractHash,package_hash:contract.expected.package_hash,
    backend_instance_hash:contract.expected.backend_instance_hash,fixtureOnly:false,
    stats:Object.fromEntries(['expected','unexpected','skipped','flaky'].map(k=>[k,results.stats[k]])),cleanup,
    result:acceptedResults(results.stats,cleanup)?'PACKAGE_BROWSER_PASSED':'FAILED',files:rows};
  newJSON(path.join(evidence,'browser-receipt.json'),{...receipt,content_hash:contentHash(receipt)});
  return receipt.result==='PACKAGE_BROWSER_PASSED'?0:1;
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url))
  process.exitCode=await run(...process.argv.slice(2));
