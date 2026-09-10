import { validSessionView, type SessionView } from './truthSpineSessionView.ts';
import type { CoverageRow, FactoryView } from './truthSpineFactoryView.ts';
import { AUCTION_ROOMS, type AuctionRoomId } from './auctionRegistry.ts';
import type { MuseumOutput } from './museumLiveBinding.ts';

export function northstarFloorOutputs(state: NorthstarState): Record<AuctionRoomId, MuseumOutput> {
  return Object.fromEntries(AUCTION_ROOMS.map(room => {
    const rows = stationRows(state.view?.factory, room.id);
    const bound = rows.some(row => row.binding_count > 0);
    return [room.id, { state: state.status === 'STALE' ? 'STALE' : bound ? 'RETAINED_READ_ONLY' : 'UNAVAILABLE',
      value: bound ? 'Retained bindings only; no current activity inferred' : 'No individually bound evidence; inspect configured station',
      source: FULL_SESSION_ENDPOINT, timestamp: state.view?.factory?.published_at ?? null,
      freshness: state.status, nextObservation: null, count: null, blocker: 'NO_CURRENT_CASE_DOSSIER', eventCategory: null }];
  })) as Record<AuctionRoomId, MuseumOutput>;
}

// Explicit grouping, never inferred individual activity from a department aggregate.
export function stationRows(factory: FactoryView | null | undefined, room: string): CoverageRow[] {
  if (!factory) return [];
  const group: Partial<Record<string, 'agents' | 'routes' | 'rooms' | 'subsystems' | 'history'>> = { research:'agents', external:'routes', expansion:'rooms',
    monitoring:'subsystems', learning:'history', judgment:'history', evidence:'history', replay:'history', thesis:'history', control:'subsystems' };
  if (group[room]) return factory[group[room]!];
  if (room === 'paper' || room === 'portfolio') return [factory.day_trading];
  if (room === 'radar') return factory.subsystems.filter(r => r.id === '9E');
  return [...factory.agents, ...factory.governance].filter(r => r.id === room || (room === 'skeptic' && r.id === 'independent_skeptic'));
}

export const FULL_SESSION_ENDPOINT = '/truth-spine/full-session';
export type NorthstarState = { view: SessionView | null; status: 'UNAVAILABLE' | 'CURRENT' | 'STALE'; reason: string };
export const emptyNorthstar: NorthstarState = { view: null, status: 'UNAVAILABLE', reason: 'NO_VERIFIED_PROJECTION' };
// Same canonical JSON as the source contract (ASCII, sorted keys, trailing LF).
export function canonical(value: unknown): string {
  const sorted = (v: unknown): unknown => Array.isArray(v) ? v.map(sorted) : v !== null && typeof v === 'object'
    ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, x]) => [k, sorted(x)])) : v;
  return JSON.stringify(sorted(value)).replace(/[\u007f-\uffff]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`) + '\n';
}
export async function contentHash(value: Record<string, unknown>): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(Object.fromEntries(Object.entries(value).filter(([k]) => k !== 'content_hash'))));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2, '0')).join('');
}
function exactKeys(value: object, keys: string): boolean {
  const expected = keys.split(' '); const actual = Object.keys(value);
  return actual.length === expected.length && actual.every(k => expected.includes(k));
}
function boundedShape(view: SessionView): boolean {
  const top = 'factory schema session phase scope published_at capture_status source_generation readiness source_cycle source_cycle_generated_at watermark owners universes sources capabilities counters counter_scope narrative_classification incidents source_session_closed_is_not_installed_disabled';
  if (!exactKeys(view, top + ('evidence_classes' in view ? ' evidence_classes' : ''))
      || !exactKeys(view.watermark, 'count identity')) return false;
  if (!view.sources.every(s => exactKeys(s,'store records capture_end classifications event_time observation_time publication_time'))
      || !view.universes.every(u => exactKeys(u,'capture_id count capture_time source_classes'))) return false;
  const f = view.factory;
  if (!f || !exactKeys(f,'schema session generation_id source_cycle_id published_at phase catalog_hash content_hash rooms agents governance routes history subsystems day_trading universes permanent_production limitation')) return false;
  const base = 'id name component_type operational_state readiness evidence_classifications authority source_cycle_id generation_id last_verified_at freshness phase bindings binding_count binding_set_hash activity_counts last_activity incident_state limitation';
  const additions: Record<string,string> = {
    PRODUCT_ROOM:'product_classification exposure benchmark universe_coverage configured_evidence_routes evidence_availability candidate_count case_count',
    SPECIALIST:'configured_role model_route_status suppression_reason completed_result_count',
    GOVERNANCE:'configured_role model_route_status suppression_reason completed_result_count',
    ROUTING_STATUS:'configured credential_presence enabled connection permitted_capabilities request_count credit_cost_count activity_scope rate_budget_state last_verified_state authoritative_truth_source',
    DAY_TRADING:'order_allowance broker_connection kill_switch paper paper_scope paper_authority live_authority',
  };
  return [...f.rooms,...f.agents,...f.governance,...f.history,...f.routes,...f.subsystems,f.day_trading].every(row => {
    const extra = additions[row.component_type];
    const reference = row.id === 'independent_skeptic' && 'registered_agent_reference' in row;
    return exactKeys(row, base + (extra ? ' '+extra : '') + (reference ? ' registered_agent_reference' : ''))
      && (!reference || row.registered_agent_reference === 'skeptic')
      && exactKeys(row.activity_counts,'retained_records current_invocations')
      && row.bindings.every(b => exactKeys(b,'record_id source_store record_type payload_hash classification event_time observation_time publication_time'))
      && (row.component_type !== 'DAY_TRADING' || exactKeys(row.paper as object,'nav cash positions'));
  });
}
export async function admitProjection(value: unknown, previous: SessionView | null, now: number): Promise<SessionView> {
  if (!validSessionView(value, now)) throw Error('PROJECTION_CONTRACT_REJECTED');
  if (!boundedShape(value)) throw Error('UNEXPECTED_PROJECTION_FIELDS');
  if (value.capture_status !== 'CURRENT' || value.factory === null) throw Error('CAPTURE_STALE_OR_UNAVAILABLE');
  const cycleTime = Date.parse(value.source_cycle_generated_at ?? '');
  if (!Number.isFinite(cycleTime) || now < cycleTime || now - cycleTime > 900_000
      || value.factory.published_at !== value.source_cycle_generated_at
      || await contentHash(value.factory as unknown as Record<string, unknown>) !== value.factory.content_hash)
    throw Error('PROJECTION_BINDING_REJECTED');
  for (const row of [...value.factory.rooms,...value.factory.agents,...value.factory.governance,
      ...value.factory.routes,...value.factory.history,...value.factory.subsystems,value.factory.day_trading]) {
    // Full-set hashes can be independently recomputed only for untruncated sets.
    if (row.binding_count <= 20 && await contentHash({ bindings: row.bindings }) !== row.binding_set_hash)
      throw Error('EVIDENCE_BINDING_HASH_REJECTED');
  }
  if (previous && (previous.session !== value.session || Date.parse(previous.published_at) > Date.parse(value.published_at)
      || previous.watermark.count > value.watermark.count)) throw Error('SESSION_OR_GENERATION_REGRESSION');
  // The validated object is never converted into an Expansion snapshot or activity model.
  return JSON.parse(JSON.stringify(value)) as SessionView;
}
export function retainedFailure(state: NorthstarState): NorthstarState {
  return { view: state.view, status: state.view ? 'STALE' : 'UNAVAILABLE', reason: 'UPDATE_REJECTED_OR_UNAVAILABLE' };
}
export function ageProjection(state: NorthstarState, now: number): NorthstarState {
  return state.view && (now < Date.parse(state.view.published_at) || now - Date.parse(state.view.published_at) > 15_000)
    ? { ...state, status: 'STALE', reason: 'LAST_VERIFIED_PROJECTION_EXPIRED' } : state;
}
// One sequential request owner; timer, timeout and abort are disposed together.
export function observeNorthstar(deliver: (state: NorthstarState) => void, fetcher: typeof fetch = fetch,
    clock: () => number = Date.now): () => void {
  let state = emptyNorthstar; let stopped = false; let timer: ReturnType<typeof setTimeout>;
  let abort: AbortController | null = null;
  const tick = setInterval(() => { if (!stopped) { state = ageProjection(state, clock()); deliver(state); } }, 1000);
  async function poll() {
    abort = new AbortController(); const timeout = setTimeout(() => abort?.abort(), 4000);
    try {
      const response = await fetcher(FULL_SESSION_ENDPOINT, { signal: abort.signal, cache: 'no-store', credentials: 'omit', redirect: 'error' });
      if (!response.ok || !/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type') ?? '')) throw Error('HTTP_REJECTED');
      const reader = response.body?.getReader(); if (!reader) throw Error('BODY_UNAVAILABLE');
      let bytes = 0; const chunks: Uint8Array[] = [];
      while (true) { const r = await reader.read(); if (r.done) break; bytes += r.value.byteLength;
        if (bytes > 1_048_576) { await reader.cancel(); throw Error('BODY_TOO_LARGE'); } chunks.push(r.value); }
      const data = new Uint8Array(bytes); let offset = 0; for (const c of chunks) { data.set(c, offset); offset += c.length; }
      const view = await admitProjection(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(data)), state.view, clock());
      if (!stopped) state = { view, status: 'CURRENT', reason: 'VERIFIED_SHADOW_PROJECTION_NOT_LIVE_DATA' };
    } catch { if (!stopped) state = retainedFailure(state); }
    finally { clearTimeout(timeout); if (!stopped) { deliver(state); timer = setTimeout(poll, 5000); } }
  }
  void poll();
  return () => { stopped = true; clearTimeout(timer); clearInterval(tick); abort?.abort(); };
}
