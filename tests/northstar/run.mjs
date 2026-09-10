// Owned CI transaction: preserve each attempt and never kill by port/name.
import { spawn, execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync, createWriteStream } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { here, sha } from './prepare.mjs';
process.umask(0o077);
const dir = resolve(here, process.env.NORTHSTAR_ARTIFACTS || 'artifacts/run');
assert(dir.startsWith(resolve(here,'artifacts')+'/') && !existsSync(dir), 'NEW_ARTIFACT_DIRECTORY_REQUIRED');
mkdirSync(dir,{recursive:true,mode:0o700});
function processes() {
  return execFileSync('ps',['-axo','pid=,ppid=,lstart=,comm='],{encoding:'utf8',timeout:5000}).split('\n').flatMap(line=>{
    const m=line.trim().match(/^(\d+)\s+(\d+)\s+(.{24})\s+(.+)$/);
    return m?[{pid:Number(m[1]),parent:Number(m[2]),started:m[3],executableHash:sha(m[4])}]:[];
  });
}
const child = spawn(process.execPath,['node_modules/playwright/cli.js','test',...process.argv.slice(2)],{cwd:here,env:process.env,stdio:['ignore','pipe','pipe']});
const log=createWriteStream(resolve(dir,'runner.log'),{flags:'wx',mode:0o600});
child.stdout.on('data',data=>{log.write(data);process.stdout.write(data)});
child.stderr.on('data',data=>{log.write(data);process.stderr.write(data)});
const owned=new Map(); const observations=[];let rootIdentity;
function observe() {
  const all=processes(), ids=new Set([child.pid]);
  for(let i=0;i<10;i++)for(const row of all)if(ids.has(row.parent))ids.add(row.pid);
  for(const row of all)if(ids.has(row.pid)){
    const key=row.pid+':'+row.started;owned.set(key,row);
    if(row.pid===child.pid)rootIdentity=row;
  }
  observations.push({at:performance.now(),descendants:all.filter(r=>ids.has(r.pid))});
}
observe();const timer=setInterval(observe,1000);
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{
  const now=processes().find(r=>r.pid===child.pid);
  if(now&&JSON.stringify(now)===JSON.stringify(rootIdentity))child.kill('SIGINT');
});
const result=await new Promise(resolve=>{child.once('error',error=>resolve({code:1,error:error.name}));child.once('exit',(code,signal)=>resolve({code,signal}))});
clearInterval(timer);log.end();
let remaining=[];
for(let n=0;n<50;n++){
  const current=processes();remaining=[...owned.values()].filter(r=>current.some(p=>p.pid===r.pid&&p.started===r.started));
  if(!remaining.length)break;
  await new Promise(resolve=>setTimeout(resolve,100));
}
let listeners=[];
try {listeners=execFileSync('lsof',['-nP','-iTCP:5291','-sTCP:LISTEN','-Fp'],{encoding:'utf8',timeout:5000}).trim().split('\n').filter(Boolean)}
catch(error){if(error.status!==1)listeners=['INVENTORY_UNAVAILABLE']}
const ok=result.code===0&&!remaining.length&&!listeners.length;
writeFileSync(resolve(dir,'ownership.json'),JSON.stringify({schema:'iios-ci-owned-process-receipt-v1',result,ok,observations,remaining,listeners},null,2),{flag:'wx',mode:0o600});
process.exitCode=ok?0:1;
