import assert from 'node:assert/strict';
import test from 'node:test';
import { admitOpportunity, opportunityHash, opportunityFlags } from './opportunitySpine.ts';
const source = 'a'.repeat(40), session = 'b'.repeat(64), backend = 'c'.repeat(64), frontend = 'd'.repeat(64);
const fixture = () => ({schema:'iios-opportunity-northstar-v1', source_commit:source, scope:'OFFLINE_TEST',
  session_parent:session, backend_identity:backend, frontend_identity:frontend, scanner_mode:'FULL_OPPORTUNITY_RADAR',
  status:'GREEN', authority:Object.fromEntries(opportunityFlags.map(k => [k,false])), alpha_status:'PASS',
  scan_count:79, case_count:0, case_decisions:[], yahoo_states:Array(79).fill('PASS'), provider_stages:[], model_disagreement:[],
  signals_detected:0, candidate_count:0, freshness:'WITHIN_AGE_BOUND', armed:false});
async function pins(value: unknown) { return {source,session,backend,frontend,projection:await opportunityHash(value)}; }
test('offline zero-candidate view preserves no-execution authority', async () => {
  const v=fixture(); const result=await admitOpportunity(v,await pins(v)); assert.deepEqual(result,v); assert.notEqual(result,v);
});
test('backend frontend source session and projection identities are independently required', async () => {
  const v=fixture();
  for (const key of ['backend','frontend','source','session','projection'])
    await assert.rejects(admitOpportunity(v,{...await pins(v),[key]:'e'.repeat(key==='source'?40:64)}));
});
test('all authority mutations and unknown payload fields fail closed', async () => {
  for (const flag of opportunityFlags) {
    const v=fixture();v.authority[flag]=true;await assert.rejects(admitOpportunity(v,await pins(v)));
  }
  const v={...fixture(),raw_body:'SYNTHETIC_FORBIDDEN'};await assert.rejects(admitOpportunity(v,await pins(v)));
});
test('missing cycle, Yahoo failure and unverified freshness cannot be GREEN', async () => {
  for (const change of [{scan_count:78},{yahoo_states:Array(79).fill('FAILED')},{freshness:'UNVERIFIED'},{armed:true}]) {
    const v={...fixture(),...change};await assert.rejects(admitOpportunity(v,await pins(v)));
  }
});
test('missing Yahoo represented as YELLOW not zero opportunities', async () => {
  const v={...fixture(),status:'YELLOW',yahoo_states:Array(79).fill('UNAVAILABLE')};
  assert.equal((await admitOpportunity(v,await pins(v))).status,'YELLOW');
});
test('hash uses sorted canonical keys', async () => {
  assert.equal(await opportunityHash({b:2,a:1}),await opportunityHash({a:1,b:2}));
});

import { readFileSync } from 'node:fs';
test('actual Python projection canonical identity is admitted without translation', async () => {
  const root=process.env.IIOS_GATEWAY_TEST_ROOT;
  assert.ok(root);
  const artifact=JSON.parse(readFileSync(`${root}/projection.json`,'utf8'));
  const v=artifact.view;
  const result=await admitOpportunity(v,{source:v.source_commit,session:v.session_parent,
    backend:v.backend_identity,frontend:v.frontend_identity,projection:artifact.hash});
  assert.equal(result.scan_count,79);
});
