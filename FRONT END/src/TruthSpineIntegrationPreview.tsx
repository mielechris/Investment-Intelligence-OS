import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './TruthSpinePreview.css';
import { validSessionView, sessionReadiness, sessionPhases } from './truthSpineSessionView';
import type { SessionView } from './truthSpineSessionView';
import type { CoverageRow, FactoryView } from './truthSpineFactoryView';

const coverageFields = ['product_classification','exposure','benchmark','universe_coverage','configured_evidence_routes',
  'evidence_availability','candidate_count','case_count','configured_role','completed_result_count','model_route_status',
  'suppression_reason','configured','credential_presence','enabled','connection','last_verified_state','permitted_capabilities',
  'request_count','credit_cost_count','activity_scope','rate_budget_state','authoritative_truth_source','order_allowance',
  'broker_connection','kill_switch','paper_authority','live_authority','paper_scope'];
function show(value: unknown): string {
  if (value === null || value === undefined) return 'UNAVAILABLE';
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (Array.isArray(value)) return value.map(show).join(' · ') || 'None';
  if (typeof value === 'object') return Object.entries(value).map(([k,v]) => `${k}: ${show(v)}`).join(' · ') || 'UNAVAILABLE';
  return String(value);
}
function CoverageCard({ row }: { row: CoverageRow }) {
  return <article className="coverage-card"><h3>{row.name}</h3><p>{row.operational_state} · {row.readiness}</p>
    <p>Evidence: {show(row.evidence_classifications)}</p><p>Authority: all disabled · Paper/live false</p>
    <dl>{coverageFields.filter(k => k in row).map(k => <div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{show(row[k])}</dd></div>)}
      {'paper' in row && <><dt>Retained paper NAV / cash / positions</dt><dd>{show(row.paper)}</dd></>}
      <dt>Source-qualified activity</dt><dd>{show(row.activity_counts)}</dd><dt>Last activity (original event time)</dt><dd>{show(row.last_activity)}</dd>
      <dt>Incident state</dt><dd>{row.incident_state}</dd><dt>Limitation</dt><dd>{row.limitation}</dd></dl>
    <details><summary>Identity, clocks and evidence bindings</summary><dl>
      <dt>Registered ID</dt><dd>{row.id}</dd><dt>Component</dt><dd>{row.component_type}</dd><dt>Phase</dt><dd>{row.phase}</dd>
      <dt>Generation</dt><dd>{row.generation_id}</dd><dt>Source cycle</dt><dd>{row.source_cycle_id}</dd>
      <dt>Last verified capture</dt><dd>{row.last_verified_at}</dd><dt>Freshness</dt><dd>{row.freshness}</dd>
      <dt>Binding set</dt><dd>{row.binding_set_hash} · {row.binding_count} records; first 20 references shown</dd></dl>
      {row.bindings.map(b => <dl key={b.record_id}>{Object.entries(b).map(([k,v]) => <div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{show(v)}</dd></div>)}</dl>)}
      <p>Authority: {show(row.authority)}</p></details></article>;
}
function FactoryCoverage({ factory }: { factory: FactoryView | null }) {
  const groups = [['rooms','24 product-market rooms'],['agents','Eight registered specialists'],['governance','Skeptic, Committee and Risk'],
    ['subsystems','9A / 9B / 9E / 9G / 9H / 9I / 9J'],['routes','Provider, model and MCP routing'],['history','L7/L8 history and memory']] as const;
  return <><section><h2>Full factory coverage</h2><p>Configured identity is not current activity. Missing evidence remains UNAVAILABLE.
    Counts describe explicitly bound retained records only. No provider, model or credential probe is performed.</p></section>
    {groups.map(([key,title]) => <details key={key} className="coverage-section" open={key === 'rooms'}><summary>{title}</summary>
      {!factory ? <p>UNAVAILABLE — no authenticated factory projection.</p> : <div className="truth-grid">{factory[key].map(row => <CoverageCard key={row.id} row={row} />)}</div>}
    </details>)}
    <section><h2>Day Trading · locked observation only</h2>{factory ? <CoverageCard row={factory.day_trading} /> : <p>UNAVAILABLE — no governed paper evidence.</p>}</section>
    <section><h2>Permanent production status</h2><p>{factory?.permanent_production ?? 'UNAVAILABLE'}</p>
      <p>The shadow cannot certify permanent production. All operational authorities remain false.</p></section></>;
}

type View = {
  canonical_url: string; classification: string; phase: string;
  event_time: string | null; observation_time: string | null; publication_time: string;
  decision: string; execution: string; narrative_classification: string;
  paper: { nav: number | null; cash: number | null; position_count: number | null };
  counts_by_source: Record<string, number>;
  classification_counts: Record<string, number>; retention_context: string;
  universe_versions: { capture_id: string; count: number; capture_time: string; source_classes: string[] }[];
};
function validView(value: unknown): value is View {
  if (!value || typeof value !== 'object') return false;
  const x = value as View;
  const age = Date.now() - Date.parse(x.publication_time);
  return x.canonical_url === 'http://127.0.0.1:5176/' && x.classification === 'HISTORICAL'
    && x.decision === 'NO_PAPER_AUTHORITY' && x.execution === 'ABSTAINED'
    && x.narrative_classification === 'NARRATIVE' && Number.isFinite(age) && age >= 0 && age <= 15000
    && x.retention_context === 'RETAINED_READ_ONLY'
    && !!x.classification_counts && Object.entries(x.classification_counts).every(([kind, count]) =>
      ['REPLAY', 'HISTORICAL', 'SIMULATED', 'NARRATIVE', 'LIVE_VERIFIED', 'UNAVAILABLE', 'STALE', 'FAILED_CLOSED', 'DELAYED', 'CACHED'].includes(kind)
      && Number.isSafeInteger(count) && count >= 0)
    && Array.isArray(x.universe_versions) && x.universe_versions.every(u => Number.isInteger(u.count) && u.count > 0);
}
export function Preview() {
  const [view, setView] = useState<View | null>(null);
  const [session, setSession] = useState<SessionView | null>(null);
  const fullSession = new URLSearchParams(window.location.search).get('fullSession') === '1';
  useEffect(() => {
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    const abort = new AbortController();
    async function poll() {
      try {
        const options = { cache: 'no-store' as const, credentials: 'omit' as const, signal: abort.signal };
        const response = fullSession ? await fetch('/truth-spine/full-session', options) : await fetch('/truth-spine/museum', options);
        const value: unknown = await response.json();
        if (!response.ok) throw new Error('UNAVAILABLE');
        if (fullSession) {
          if (!validSessionView(value)) throw new Error('UNAVAILABLE');
          if (!stopped) setSession(value);
        } else {
          if (!validView(value)) throw new Error('UNAVAILABLE');
          if (!stopped) setView(value);
        }
      } catch { if (!stopped) { setView(null); setSession(null); } }
      if (!stopped) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { stopped = true; abort.abort(); clearTimeout(timer); };
  }, [fullSession]);
  if (fullSession) return <main><header><h1>Full-session read-only shadow observer</h1>
    <strong>ISOLATED SHADOW · PERMANENT FACTORY UNCHANGED</strong>
    <p>Not live trading. Not an authoritative market-data provider.</p></header>
    {!session ? <section role="status"><h2>UNAVAILABLE</h2><p>No current authenticated session projection.</p></section> : <>
      <section role="status"><h2>{session.phase}</h2><p>{sessionReadiness(session)}</p>
        <p>Session {session.session}</p><p>Capture {session.capture_status} · Generation {session.source_generation ?? 'UNAVAILABLE'}</p>
        <p>Watermark {session.watermark.count} unique source identities · {session.watermark.identity}</p>
        <p>Source cycle {session.source_cycle ?? 'UNAVAILABLE'} · Generated {session.source_cycle_generated_at ?? 'UNAVAILABLE'}</p>
        <p>A fresh capture is not fresh market evidence. Market readiness remains disabled.</p>
        <p>SESSION_CLOSED is a source session result; INSTALLED_DISABLED is installation status. Neither is inferred from the other.</p></section>
      <details><summary>Session phase timeline</summary><ol>{sessionPhases.map(phase => <li key={phase} aria-current={phase === session.phase ? 'step' : undefined}>
        {phase}{phase === session.phase ? ' · CURRENT' : ''}</li>)}</ol><p>Listed phases are the contract, not proof that every phase has occurred.</p></details>
      <FactoryCoverage factory={session.factory} />
      <div className="truth-grid">{session.sources.map(s => <section key={s.store}><h2>{s.store}</h2>
        <p>{s.records} source-qualified retained records</p><p>{s.classifications.join(' · ') || 'UNAVAILABLE'}</p>
        <dl><dt>Capture end</dt><dd>{s.capture_end}</dd><dt>Observation time</dt><dd>{s.observation_time ?? 'UNAVAILABLE'}</dd>
          <dt>Event time</dt><dd>{s.event_time ?? 'UNAVAILABLE'}</dd><dt>Publication time</dt><dd>{s.publication_time ?? 'UNAVAILABLE'}</dd></dl>
        <p>Cases and agent activity remain qualified by this source, not new shadow activity.</p></section>)}</div>
      <section><h2>Separate universe provenance</h2>{session.universes.map(u => <article key={u.capture_id}>
        <h3>{u.count} captured members</h3><p>{u.capture_id} · {u.capture_time}</p><p>{u.source_classes.join(' · ')}</p>
        <p>Capture-qualified membership, not direct official membership.</p></article>)}</section>
      <details><summary>Owners, authority and observer counters</summary><dl>
        {Object.entries(session.owners).map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        {Object.entries(session.capabilities).map(([k]) => <div key={k}><dt>{k}</dt><dd>False · disabled</dd></div>)}
        {Object.entries(session.counters).map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{v} · this deny-only observer, not retained execution history</dd></div>)}
      </dl></details>
      <section><h2>Incidents and stale dependencies</h2><ul>{session.incidents.map((x,i) => <li key={`${x}-${i}`}>{x}</li>)}</ul>
        <p>Readiness HTTP {session.readiness}. Missing, expired or mismatched dependencies fail closed.</p></section>
      <section><h2>NARRATIVE · Day Trading ABSTAINED</h2><p>MAX and character dialogue may describe persisted events only.
        HISTORICAL, REPLAY, SIMULATED, NARRATIVE and UNAVAILABLE remain distinct. No paper or live orders.</p></section>
    </>}
  </main>;
  return <main><header><p>IIOS · TRUTH SPINE SUPERBATCH 3</p><h1>Historical integration observer</h1>
    <strong>ISOLATED CANDIDATE — PERMANENT FACTORY UNCHANGED</strong>
    <p>Provider, credentials, paid models, paper orders and live execution: disabled.</p></header>
    {!view ? <section role="status"><h2>UNAVAILABLE</h2><p>No fresh authenticated projection is available.</p></section> : <>
      <section><h2>{view.phase}</h2><p>{view.classification} · {view.decision} · {view.execution}</p>
        <p>Installed-disabled is not a closed session. Retained observations are not new activity.</p></section>
      <div className="truth-grid"><section><h2>Versioned market universes</h2>{view.universe_versions.map(u => <article key={u.capture_id}>
        <h3>{u.count} captured members</h3><p>{u.capture_time}</p><p>{u.source_classes.join(' · ')}</p>
        <p>Capture-qualified membership, not direct official membership.</p></article>)}</section>
        <section><h2>Separate source clocks</h2><dl><dt>Event time</dt><dd>{view.event_time ?? 'UNAVAILABLE'}</dd>
          <dt>Observation time</dt><dd>{view.observation_time ?? 'UNAVAILABLE'}</dd><dt>Publication time</dt><dd>{view.publication_time}</dd></dl></section>
        <section><h2>Operational paper reference</h2><p>NAV {view.paper.nav ?? 'UNAVAILABLE'} · Cash {view.paper.cash ?? 'UNAVAILABLE'}</p>
          <p>Positions {view.paper.position_count ?? 'UNAVAILABLE'} · No paper authority</p></section></div>
      <details><summary>Namespaced source reconciliation</summary><dl>{Object.entries(view.counts_by_source).map(([id, count]) => <div key={id}><dt>{id}</dt><dd>{count} retained records</dd></div>)}</dl></details>
      <section><h2>Original evidence classifications</h2><p>Retention is historical context, not evidence classification.</p>
        <dl>{Object.entries(view.classification_counts).map(([kind, count]) => <div key={kind}><dt>{kind}</dt><dd>{count}</dd></div>)}</dl></section>
      <section><h2>Day Trading: ABSTAINED</h2><p>No scanner activation, paper authorization, broker, or trading connection.</p>
        <p>Character commentary is NARRATIVE, never evidence or an operational event.</p></section>
    </>}
  </main>;
}
createRoot(document.getElementById('root')!).render(<Preview />);
