// Offline only: never imports Playwright or executes the operational runner.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { canonical, digest, contentHash, newJSON, safeFile, pinnedJSON, verifyView, geometryEvaluation } from './package-contract.mjs';
import { sameOwner, acceptedResults, cleanupRecords } from './package-run.mjs';

function retainedRoot() {
  const root=process.env.IIOS_SB38D_TEST_ROOT;
  assert(root && path.dirname(root)==='/private/tmp' && path.basename(root).startsWith('iios-sb38d-source-tests-'));
  return fs.mkdtempSync(path.join(root,'node-contract-'));
}
test('geometry probe receives local helpers without leaking or importing page globals',async()=>{
  const names=['runSettlement','geometryFrame','requiredText','obstructionCensus','headingTypography'];
  const source=names.map(name=>`function ${name}(value){return '${name}:'+value;}`).join('\n');
  const context=vm.createContext({});
  const expression=geometryEvaluation(source,async (helpers,value)=>Object.values(helpers).map(fn=>fn(value)),'Gallery');
  assert.deepEqual(Array.from(await vm.runInContext(expression,context)),names.map(name=>name+':Gallery'));
  for(const name of names)assert.equal(context[name],undefined);
  assert.equal(vm.runInContext(geometryEvaluation(source,({geometryFrame},value)=>geometryFrame(value),'Replay'),context),'geometryFrame:Replay');
});
test('canonical byte encoding matches Python and rejects unsupported values',()=>{
  assert.equal(canonical({z:'·',a:{b:1,a:false}}),'{"a":{"a":false,"b":1},"z":"\\u00b7"}\n');
  for(const v of [NaN,Infinity,undefined])assert.throws(()=>canonical({v}));
});
test('evidence is exclusive-create and independently pinned',()=>{
  const root=retainedRoot(),file=path.join(root,'receipt.json'),value={schema:'SYNTHETIC'};
  newJSON(file,value);assert.throws(()=>newJSON(file,{schema:'RELABELED'}));
  assert.deepEqual(pinnedJSON(root,'receipt.json',digest(value)),value);
  assert.throws(()=>pinnedJSON(root,'receipt.json','0'.repeat(64)));
  assert.throws(()=>safeFile(root,'../receipt.json'));
  fs.symlinkSync(file,path.join(root,'alias'));assert.throws(()=>safeFile(root,'alias'));
});
test('cleanup never uses PID alone and fixture/browser partial counts cannot pass',()=>{
  const owner={pid:123,parent:10,group:123,start:'synthetic',executable:'/synthetic/node',executableHash:'a'.repeat(64),
    command:'synthetic',cwd:'/synthetic',packageRoot:'/synthetic/package',port:6000,startupReceipt:'b'.repeat(64)};
  assert(sameOwner(owner,{...owner}));assert(!sameOwner(owner,{...owner,start:'reused'}));assert(!sameOwner(owner,null));
  const stats={expected:9,unexpected:0,skipped:0,flaky:0},cleanup={exitCode:0,remaining:[],errors:[],listenersStable:true};
  assert(acceptedResults(stats,cleanup));
  for(const bad of [{expected:252},{unexpected:1},{skipped:1},{flaky:1}])assert(!acceptedResults({...stats,...bad},cleanup));
  assert(!acceptedResults(stats,{...cleanup,remaining:[owner]}));assert(!acceptedResults(stats,{...cleanup,exitCode:1}));
});
test('package proof rejects fixture scope, stale publication and identity substitution',()=>{
  const at='2026-09-11T00:00:00.000Z',now=Date.parse(at);
  const expected={package_hash:'a'.repeat(64),generation_hash:'b'.repeat(64),backend_instance_hash:'c'.repeat(64)};
  const basis={generation:expected.generation_hash,published_at:at,package_hash:null};
  const body={schema:'iios-northstar-package-contract-v1',fixtureOnly:false,expected,cycleBasis:basis};
  const contract={...body,content_hash:contentHash(body)};
  const cycle=digest({...basis,package_hash:expected.package_hash});
  const factory={source_cycle_id:cycle};factory.content_hash=contentHash(factory);
  const view={schema:'iios-historical-northstar-browser-v2',scope:'HISTORICAL_REPLAY_NOT_CURRENT_MARKET',phase:'SESSION_CLOSED',
    readiness:200,capture_status:'CURRENT',published_at:at,source_generation:expected.generation_hash,source_cycle:cycle,factory,
    lineage:{...expected,projection_hash:factory.content_hash,source_cycle:cycle},owners:{backend_owner:expected.backend_instance_hash},capabilities:{provider:false},counters:{provider:0}};
  assert.equal(verifyView(view,contract,now).projection_hash,factory.content_hash);
  assert.throws(()=>verifyView(view,contract,now+15001));
  assert.throws(()=>verifyView({...view,lineage:{...view.lineage,package_hash:'d'.repeat(64)}},contract,now));
  assert.throws(()=>verifyView({...view,capabilities:{provider:true}},contract,now));
  const fixture={...body,fixtureOnly:true};assert.throws(()=>verifyView(view,{...fixture,content_hash:contentHash(fixture)},now));
  assert.throws(()=>verifyView({...view,owners:{backend_owner:'d'.repeat(64)}},contract,now));
});

function cleanupHarness(){
  const records=[1,2].map(pid=>{
    const fingerprint={pid,parent:100,group:1,start:'SYNTHETIC',executable:'/synthetic/node',executableHash:'a'.repeat(64),
      command:'synthetic '+pid,cwd:'/synthetic',packageRoot:'/synthetic/package',port:6000};
    const doc={schema:'iios-browser-observed-startup-v1',fingerprint},receipt={...doc,content_hash:contentHash(doc)};
    return {fingerprint:{...fingerprint,startupReceipt:receipt.content_hash},receipt};
  });
  const alive=new Map(records.map(r=>[r.fingerprint.pid,r.fingerprint])),signals=[],evidence=[];
  return {records,alive,signals,evidence,deps:{inspect:e=>alive.get(e.fingerprint.pid)??null,readStartup:e=>e.receipt,
    signal:(pid,signal)=>{signals.push([pid,signal]);alive.delete(pid);},pause:()=>{},listeners:()=>[],expectedListeners:[],persist:r=>evidence.push(r)}};
}
test('cleanup rechecks every identity field and never signals a reused PID',async()=>{
  for(const key of ['pid','parent','group','start','executable','executableHash','command','cwd','packageRoot','port','startupReceipt']){
    const h=cleanupHarness();h.alive.set(2,{...h.alive.get(2),[key]:'MISMATCH'});
    const result=await cleanupRecords(h.records,h.deps);
    assert(result.errors.length);assert(result.remaining.length);assert(h.signals.every(([pid])=>pid!==2));
    assert(h.signals.some(([pid])=>pid===1));
  }
});
test('cleanup continues after a signal or persistence exception',async()=>{
  const h=cleanupHarness(),original=h.deps.signal;
  h.deps.signal=(pid,signal)=>{if(pid===2)throw Error('SYNTHETIC_FAILURE');original(pid,signal);};
  h.deps.persist=()=>{throw Error('SYNTHETIC_DISK_FAILURE');};
  const result=await cleanupRecords(h.records,h.deps);
  assert(h.signals.some(([pid])=>pid===1));assert(result.remaining.some(r=>r.pid===2));assert(result.errors.length);
});
test('surviving browser or changed listener owner prevents success',async()=>{
  const h=cleanupHarness();h.deps.signal=()=>{};h.deps.listeners=()=>[{pid:999,address:'127.0.0.1:6000'}];
  const result=await cleanupRecords(h.records,h.deps);
  assert.equal(result.remaining.length,2);assert.equal(result.listenersStable,false);
  assert(!acceptedResults({expected:9,unexpected:0,skipped:0,flaky:0},{...result,exitCode:0}));
});
