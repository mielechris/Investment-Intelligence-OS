// Same-origin observer metadata only. Query selection never grants authority.
import { validFactory } from './truthSpineFactoryView.ts';
import type { FactoryView } from './truthSpineFactoryView.ts';
export const sessionPhases = ['PREMARKET_PREPARATION', 'PREMARKET_READY', 'OPENING_OBSERVATION',
  'REGULAR_SESSION', 'CLOSING_OBSERVATION', 'POST_CLOSE_RECONCILIATION', 'SESSION_COMPLETE',
  'SHUTDOWN_COMPLETE', 'FAILED_CLOSED'];
const capabilities = ['provider_requests', 'credential_access', 'paid_model_requests', 'paper_order', 'broker',
  'live_execution', 'operational_ledger_write', 'promotion', 'scheduler_authority', 'publisher_authority'];
const counters = ['provider', 'model', 'credential', 'broker', 'paper', 'live_execution', 'operational_ledger_write'];
export type SessionView = {
  lineage?: HistoricalLineage;
  factory: FactoryView | null;
  schema: string; session: string; phase: string; scope: string; published_at: string;
  capture_status: string; source_generation: string | null; readiness: number;
  source_cycle: string | null; source_cycle_generated_at: string | null;
  watermark: { count: number; identity: string }; owners: Record<string, string>;
  universes: { capture_id: string; count: number; capture_time: string; source_classes: string[] }[];
  sources: { store: string; records: number; capture_end: string; classifications: string[];
    observation_time: string | null; event_time: string | null; publication_time: string | null }[];
  capabilities: Record<string, false>; counters: Record<string, number>; incidents: string[];
  counter_scope: string; narrative_classification: string; source_session_closed_is_not_installed_disabled: boolean;
};
const object = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const hash = (x: unknown) => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
const label = (x: unknown) => typeof x === 'string' && /^[A-Za-z0-9_.:-]{1,180}$/.test(x);
const count = (x: unknown) => typeof x === 'number' && Number.isSafeInteger(x) && x >= 0;
const instant = (x: unknown) => typeof x === 'string' && Number.isFinite(Date.parse(x)) && /(?:Z|\+00:00)$/.test(x);
const strings = (x: unknown) => Array.isArray(x) && x.every(label);
export type HistoricalLineage = {
  schema: string; source_commit: string; package_hash: string; package_generation: string;
  runtime_hash: string; frontend_hash: string; admission_hash: string; generation_hash: string;
  initial_cycle_hash: string; owner_manifest_hash: string; completion_hash: string;
  l7_hash: string; l8_hash: string; backend_instance_hash: string; common_watermark: string;
  classification: string; source_cycle: string; projection_hash: string;
};
export function validHistoricalLineage(value: unknown): value is HistoricalLineage {
  if (!object(value)) return false;
  const hashes = ['package_hash','package_generation','runtime_hash','frontend_hash','admission_hash',
    'generation_hash','initial_cycle_hash','owner_manifest_hash','completion_hash','l7_hash','l8_hash',
    'backend_instance_hash','source_cycle','projection_hash'];
  return Object.keys(value).length === hashes.length + 4 && hashes.every(k => hash(value[k]))
    && value.schema === 'iios-northstar-package-binding-v1'
    && typeof value.source_commit === 'string' && /^[a-f0-9]{40}$/.test(value.source_commit)
    && instant(value.common_watermark) && value.classification === 'HISTORICAL_REPLAY';
}
export function validSessionView(value: unknown, now = Date.now()): value is SessionView {
  if (!object(value)) return false;
  const x = value;
  const age = now - Date.parse(String(x.published_at));
  const historical = x.schema === 'iios-historical-northstar-browser-v2';
  if (historical) {
    if (!validHistoricalLineage(x.lineage) || x.phase !== 'SESSION_CLOSED'
      || x.scope !== 'HISTORICAL_REPLAY_NOT_CURRENT_MARKET'
      || x.lineage.generation_hash !== x.source_generation || x.lineage.source_cycle !== x.source_cycle
      || !object(x.factory) || x.lineage.projection_hash !== x.factory.content_hash
      || !object(x.owners) || x.lineage.backend_instance_hash !== x.owners.backend_owner) return false;
  } else if ('lineage' in x) return false;
  if ((!historical && x.schema !== 'iios-full-session-shadow-browser-v1') || !label(x.session)
    || (!historical && (!sessionPhases.includes(String(x.phase)) || x.scope !== 'SHADOW_OBSERVATION_NOT_LIVE_TRADING'))
    || !instant(x.published_at) || !Number.isFinite(age) || age < 0 || age > 15000
    || !['CURRENT', 'STALE', 'UNAVAILABLE'].includes(String(x.capture_status))
    || ![200, 503].includes(Number(x.readiness)) || typeof x.readiness !== 'number'
    || !(x.source_generation === null || hash(x.source_generation))
    || !(x.source_cycle === null || label(x.source_cycle))
    || !(x.source_cycle_generated_at === null || instant(x.source_cycle_generated_at))
    || !object(x.watermark) || !count(x.watermark.count) || !hash(x.watermark.identity)
    || !object(x.capabilities) || Object.keys(x.capabilities).length !== capabilities.length
    || !capabilities.every(k => (x.capabilities as Record<string, unknown>)[k] === false)
    || !object(x.counters) || Object.keys(x.counters).length !== counters.length
    || !counters.every(k => (x.counters as Record<string, unknown>)[k] === 0)
    || x.counter_scope !== 'DENY_ONLY_SHADOW' || x.narrative_classification !== 'NARRATIVE'
    || x.source_session_closed_is_not_installed_disabled !== true || !strings(x.incidents)
    || !object(x.owners) || !Object.entries(x.owners).every(([k,v]) =>
      ['backend_owner', 'scheduler_owner', 'publisher_owner'].includes(k) && hash(v))) return false;
  if (x.factory === null) {
    if (x.readiness !== 503) return false;
  } else {
    if (!validFactory(x.factory, String(x.session), x.source_generation, x.source_cycle, String(x.phase))) return false;
    if (JSON.stringify(x.factory.universes) !== JSON.stringify(x.universes)) return false;
  }
  return Array.isArray(x.sources) && x.sources.every(s => object(s) && label(s.store) && count(s.records)
    && instant(s.capture_end) && strings(s.classifications)
    && ['observation_time', 'event_time', 'publication_time'].every(k => s[k] === null || instant(s[k])))
    && Array.isArray(x.universes) && x.universes.every(u => object(u) && hash(u.capture_id)
      && count(u.count) && instant(u.capture_time) && strings(u.source_classes));
}
export function sessionReadiness(view: SessionView): string {
  if (view.schema === 'iios-historical-northstar-browser-v2')
    return view.readiness === 200 && view.capture_status === 'CURRENT'
      ? 'HISTORICAL_REVIEW_READY · NOT CURRENT MARKET DATA' : 'NOT_READY · HISTORICAL PUBLICATION UNAVAILABLE';
  return view.readiness === 200 && view.capture_status === 'CURRENT'
    && !['FAILED_CLOSED', 'SESSION_COMPLETE', 'SHUTDOWN_COMPLETE'].includes(view.phase)
    ? 'SHADOW_OBSERVATION_READY' : 'NOT_READY · STALE OR CLOSED';
}
