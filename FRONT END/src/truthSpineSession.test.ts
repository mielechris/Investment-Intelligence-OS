import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { validSessionView, sessionReadiness } from './truthSpineSessionView.ts';
import { factoryFixture } from './truthSpineFactory.fixture.ts';
import { validHistoricalLineage } from './truthSpineSessionView.ts';
const now = Date.parse('2026-09-10T13:30:00Z');
const fixture = () => ({
  factory: factoryFixture(),
  schema: 'iios-full-session-shadow-browser-v1', session: 'unit-session', phase: 'OPENING_OBSERVATION',
  scope: 'SHADOW_OBSERVATION_NOT_LIVE_TRADING', published_at: new Date(now).toISOString(),
  capture_status: 'CURRENT', source_generation: 'a'.repeat(64), readiness: 200,
  source_cycle: 'd'.repeat(64), source_cycle_generated_at: new Date(now).toISOString(),
  watermark: { count: 2, identity: 'b'.repeat(64) }, owners: { scheduler_owner: 'c'.repeat(64) },
  universes: [517, 518].map((count, i) => ({ capture_id: String(i).repeat(64), count,
    capture_time: '2026-09-09T20:00:00Z', source_classes: ['HISTORICAL'] })),
  sources: [{ store: 'unit:L7', records: 2, capture_end: new Date(now).toISOString(), classifications: ['REPLAY'],
    event_time: '2026-09-08T20:00:00Z', observation_time: '2026-09-08T20:01:00Z', publication_time: '2026-09-08T20:02:00Z' }],
  capabilities: Object.fromEntries(['provider_requests', 'credential_access', 'paid_model_requests', 'paper_order', 'broker',
    'live_execution', 'operational_ledger_write', 'promotion', 'scheduler_authority', 'publisher_authority'].map(k => [k, false])),
  counters: Object.fromEntries(['provider', 'model', 'credential', 'broker', 'paper', 'live_execution', 'operational_ledger_write'].map(k => [k, 0])),
  counter_scope: 'DENY_ONLY_SHADOW', narrative_classification: 'NARRATIVE', incidents: [],
  source_session_closed_is_not_installed_disabled: true,
});
test('historical package lineage requires every independent identity and retains the watermark', () => {
  const hashes = ['package_hash','package_generation','runtime_hash','frontend_hash','admission_hash',
    'generation_hash','initial_cycle_hash','owner_manifest_hash','completion_hash','l7_hash','l8_hash',
    'backend_instance_hash','source_cycle','projection_hash'];
  const lineage = { ...Object.fromEntries(hashes.map(k => [k,'a'.repeat(64)])),
    schema:'iios-northstar-package-binding-v1',source_commit:'b'.repeat(40),
    common_watermark:'2020-01-02T00:00:00Z',classification:'HISTORICAL_REPLAY' };
  assert.equal(validHistoricalLineage(lineage),true);
  for(const key of hashes) {
    const bad: Record<string,unknown>={...lineage};delete bad[key];
    assert.equal(validHistoricalLineage(bad),false);
    assert.equal(validHistoricalLineage({...lineage,[key]:'retained-fixture'}),false);
  }
  assert.equal(validHistoricalLineage({...lineage,classification:'LIVE_VERIFIED'}),false);
  assert.equal(validHistoricalLineage({...lineage,unexpected:true}),false);
  assert.equal(validSessionView({...fixture(),lineage},now),false);
});
test('full-session metadata preserves distinct universes and original clocks', () => {
  const x = fixture(); assert.ok(validSessionView(x, now));
  assert.equal(sessionReadiness(x), 'SHADOW_OBSERVATION_READY');
  assert.deepEqual(x.universes.map(u => u.count), [517, 518]);
  assert.notEqual(x.sources[0].capture_end, x.sources[0].event_time);
});
test('all operational capabilities and observer counters fail closed', () => {
  for (const k of Object.keys(fixture().capabilities)) {
    const x = fixture(); x.capabilities[k] = true; assert.equal(validSessionView(x, now), false);
  }
  for (const k of Object.keys(fixture().counters)) {
    const x = fixture(); x.counters[k] = 1; assert.equal(validSessionView(x, now), false);
  }
});
test('fresh wrapper cannot mask failed capture/readiness and terminal phase', () => {
  for (const change of [{ capture_status: 'STALE' }, { readiness: 503 }, { phase: 'FAILED_CLOSED' }, { phase: 'SHUTDOWN_COMPLETE' }]) {
    const x = { ...fixture(), ...change }; x.factory = factoryFixture(x.phase); assert.ok(validSessionView(x, now));
    assert.match(sessionReadiness(x), /NOT_READY/);
  }
  assert.equal(validSessionView(fixture(), now + 15001), false);
  assert.equal(validSessionView(fixture(), now - 1), false);
});
test('missing malformed and conflicting provenance never becomes usable projection', () => {
  for (const x of [null, {}, { ...fixture(), scope: 'LIVE' }, { ...fixture(), capabilities: {} },
    { ...fixture(), source_generation: 'bad' }, { ...fixture(), phase: 'STAGE_A_RUNNING' },
    { ...fixture(), sources: [{ store: '/private/not-browser-metadata' }] },
    { ...fixture(), narrative_classification: 'LIVE_VERIFIED' }]) assert.equal(validSessionView(x, now), false);
});
test('full-session browser is one read-only poll owner and normal-flow responsive layout', () => {
  const source = readFileSync(new URL('./TruthSpineIntegrationPreview.tsx', import.meta.url), 'utf8');
  const css = readFileSync(new URL('./TruthSpinePreview.css', import.meta.url), 'utf8');
  assert.equal((source.match(/setTimeout\(poll/g) ?? []).length, 1);
  assert.match(source, /fetch\('\/truth-spine\/full-session'/);
  assert.doesNotMatch(source, /method:\s*['"](?:POST|PUT|DELETE|PATCH)|api_key|localhost:8002/);
  assert.match(source, /abort.abort\(\)/); assert.match(source, /clearTimeout\(timer\)/);
  for (const text of ['SESSION_CLOSED', 'INSTALLED_DISABLED', 'NARRATIVE', 'source_generation', 'capture_status', 'session.owners']) assert.ok(source.includes(text));
  assert.match(css, /minmax\(0, 1fr\)/); assert.match(css, /overflow-wrap: anywhere/);
  assert.match(css, /max-width: 700px/); assert.doesNotMatch(css, /position:\s*(fixed|absolute)|white-space:\s*nowrap/);
});
test('full-session route is explicit and historical route never silently switches API', () => {
  const source = readFileSync(new URL('./TruthSpineIntegrationPreview.tsx', import.meta.url), 'utf8');
  assert.match(source, /new URLSearchParams\(window.location.search\).get\('fullSession'\) === '1'/);
  assert.match(source, /fullSession \? await fetch\('\/truth-spine\/full-session', options\) : await fetch\('\/truth-spine\/museum', options\)/);
  for (const query of ['', '?fullSession=0', '?fullSession=true']) {
    assert.equal(new URLSearchParams(query).get('fullSession') === '1', false);
  }
  assert.equal(new URLSearchParams('?fullSession=1').get('fullSession') === '1', true);
});
