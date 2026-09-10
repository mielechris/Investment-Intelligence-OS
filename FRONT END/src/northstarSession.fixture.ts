// Explicit OFFLINE fixture; not imported by either production entrypoint.
import { factoryFixture } from './truthSpineFactory.fixture.ts';
import { contentHash } from './northstarSession.ts';
import type { SessionView } from './truthSpineSessionView.ts';
export async function northstarFixture(now = Date.parse('2026-09-11T13:30:00Z')): Promise<SessionView> {
  const at = new Date(now).toISOString(); const factory = factoryFixture();
  factory.session = 'OFFLINE_FIXTURE_NON_LIVE'; factory.published_at = at;
  for (const rows of [factory.rooms, factory.agents, factory.governance, factory.routes, factory.history, factory.subsystems, [factory.day_trading]])
    for (const row of rows) { row.last_verified_at = at; row.binding_set_hash = await contentHash({bindings:row.bindings}); }
  factory.content_hash = await contentHash(factory as unknown as Record<string, unknown>);
  return { schema:'iios-full-session-shadow-browser-v1',session:factory.session,phase:factory.phase,
    scope:'SHADOW_OBSERVATION_NOT_LIVE_TRADING',published_at:at,capture_status:'CURRENT',source_generation:factory.generation_id,
    readiness:200,source_cycle:factory.source_cycle_id,source_cycle_generated_at:at,watermark:{count:0,identity:'b'.repeat(64)},
    owners:{scheduler_owner:'c'.repeat(64)},universes:factory.universes,sources:[],factory,capabilities:factory.day_trading.authority,
    counters:Object.fromEntries(['provider','model','credential','broker','paper','live_execution','operational_ledger_write'].map(k=>[k,0])),
    counter_scope:'DENY_ONLY_SHADOW',narrative_classification:'NARRATIVE',incidents:[],source_session_closed_is_not_installed_disabled:true };
}
