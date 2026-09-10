import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { validFactory, factoryCatalog } from './truthSpineFactoryView.ts';
import { factoryFixture } from './truthSpineFactory.fixture.ts';
const valid = (x: unknown) => validFactory(x,'unit-session','a'.repeat(64),'d'.repeat(64),'OPENING_OBSERVATION');
test('exact separate configured rooms, registered agents, governance and routes', () => {
  const x = factoryFixture(); assert.ok(valid(x));
  assert.equal(x.rooms.length,24); assert.equal(x.agents.length,8); assert.equal(x.governance.length,3); assert.equal(x.routes.length,10);
  assert.equal(new Set(x.rooms.map(r => r.id)).size,24);
  assert.deepEqual(x.rooms.map(r => [r.id,r.name]),factoryCatalog.rooms);
});
test('missing duplicate wrong and foreign-generation objects are rejected', () => {
  for (const key of ['rooms','agents','governance','routes','history','subsystems'] as const) {
    const x = factoryFixture(); x[key].pop(); assert.equal(valid(x),false);
    const y = factoryFixture(); y[key][1] = y[key][0]; assert.equal(valid(y),false);
    const z = factoryFixture(); z[key][0].source_cycle_id = 'f'.repeat(64); assert.equal(valid(z),false);
  }
  assert.equal(valid({...factoryFixture(),generation_id:'f'.repeat(64)}),false);
});
test('aggregate counts cannot invent individual activity and unavailable remains null', () => {
  const x = factoryFixture(); assert.ok(x.rooms.every(r => r.case_count === null && r.candidate_count === null));
  x.rooms[0].activity_counts.retained_records = 500; assert.equal(valid(x),false);
  const y = factoryFixture(); y.agents[0].completed_result_count = 8; assert.equal(valid(y),false);
  const z = factoryFixture(); z.day_trading.paper = {nav:'10000',cash:'10000',positions:0}; assert.equal(valid(z),false);
});
test('all route and Day Trading authority remains locked without probes', () => {
  for (const change of [{credential_presence:'PRESENT'}, {configured:'CONFIGURED'}, {enabled:true}, {request_count:1},
    {authoritative_truth_source:true}, {credit_cost_count:1}, {connection:'CONNECTED'}]) {
    const x = factoryFixture(); Object.assign(x.routes[0],change); assert.equal(valid(x),false);
  }
  for (const change of [{order_allowance:1},{broker_connection:true},{paper_authority:true},{live_authority:true}]) {
    const x = factoryFixture(); Object.assign(x.day_trading,change); assert.equal(valid(x),false);
  }
  const x = factoryFixture(); x.rooms[0].authority = {} as Record<string,false>; assert.equal(valid(x),false);
});
test('each preserved classification is accepted as evidence, never room LIVE status', () => {
  for (const classification of ['HISTORICAL','REPLAY','SIMULATED','NARRATIVE','UNAVAILABLE','STALE','FAILED_CLOSED']) {
    const x = factoryFixture(), r = x.rooms[0];
    r.binding_count = 1; r.activity_counts.retained_records = 1; r.readiness = 'RETAINED_READ_ONLY'; r.evidence_availability = r.readiness;
    r.evidence_classifications = {[classification]:1};
    r.bindings = [{record_id:'e'.repeat(64),source_store:'unit:L8',record_type:'case',payload_hash:'f'.repeat(64),classification,
      event_time:'2026-09-08T20:00:00Z',observation_time:null,publication_time:null}];
    assert.ok(valid(x)); r.operational_state = 'LIVE'; assert.equal(valid(x),false);
  }
});
test('all required coverage sections survive narrow normal flow with one existing polling owner', () => {
  const source = readFileSync(new URL('./TruthSpineIntegrationPreview.tsx',import.meta.url),'utf8');
  const css = readFileSync(new URL('./TruthSpinePreview.css',import.meta.url),'utf8');
  for (const section of ['24 product-market rooms','Eight registered specialists','Skeptic, Committee and Risk','Provider, model and MCP routing',
    'L7/L8 history and memory','Day Trading · locked observation only','Permanent production status','Session phase timeline']) assert.ok(source.includes(section));
  assert.equal((source.match(/setTimeout\(poll/g) ?? []).length,1);
  assert.match(css,/\.coverage-card \{ min-width: 0/); assert.match(css,/max-width: 700px/);
  assert.doesNotMatch(css,/display:\s*none|overflow:\s*hidden|position:\s*(absolute|fixed)|white-space:\s*nowrap/);
  assert.doesNotMatch(source,/api_key|keychain|method:\s*['"]POST|http.*:8002/);
});
