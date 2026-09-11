import { useEffect, useRef, useState } from 'react';
import { useNorthstar } from './northstarContext';
import { factoryCatalog, type CoverageRow } from './truthSpineFactoryView';
import { sessionPhases } from './truthSpineSessionView';
import CinematicCharacterPortrait from './CinematicCharacterPortrait';
import { LIVING_CAST, type LivingCastKey } from './livingCast';
import { boundedNavigation, escapeLayer, selectedOpener, selectionHistoryAction } from './northstarNavigation';

export type CoverageGroup = 'rooms' | 'agents' | 'governance' | 'history' | 'routes' | 'subsystems';
const titles: Record<CoverageGroup, string> = { rooms: '24 Product-Market Rooms', agents: 'Eight Specialist Stations',
  governance: 'Skeptic, Committee and Risk', history: 'L7/L8 History and Memory', routes: 'Provider / Model / MCP Routing', subsystems: 'Factory Subsystems' };
const fields = ['operational_state','readiness','evidence_classifications','product_classification','exposure','benchmark',
  'universe_coverage','configured_evidence_routes','evidence_availability','candidate_count','case_count','configured_role',
  'completed_result_count','model_route_status','suppression_reason','configured','credential_presence','enabled','connection',
  'last_verified_state','permitted_capabilities','request_count','credit_cost_count','activity_scope','rate_budget_state',
  'authoritative_truth_source','order_allowance','broker_connection','kill_switch','paper_authority','live_authority','paper_scope',
  'activity_counts','last_activity','incident_state','limitation','source_cycle_id','generation_id','last_verified_at','freshness','phase',
  'binding_count','binding_set_hash','authority'] as const;
function display(value: unknown): string {
  if (value === null || value === undefined) return 'UNAVAILABLE';
  if (Array.isArray(value)) return value.length ? value.map(display).join(' · ') : 'None';
  if (typeof value === 'object') return Object.entries(value).map(([k,v]) => `${k}: ${display(v)}`).join(' · ') || 'None reported';
  return String(value);
}
export function NorthstarRow({ row }: { row: CoverageRow }) {
  return <div className="northstar-detail"><p>{row.limitation}</p><dl>{fields.filter(k => k in row).map(k =>
    <div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{display(row[k])}</dd></div>)}</dl>
    {'paper' in row && <p>Retained L7 paper snapshot — not a live account: {display(row.paper)}</p>}
    <details><summary>Original evidence identities and timestamps</summary>
      {row.bindings.length ? row.bindings.map(b => <dl key={b.record_id}>{Object.entries(b).map(([k,v]) =>
        <div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{display(v)}</dd></div>)}</dl>) : <p>UNAVAILABLE — no individually bound evidence.</p>}
      <p>Only the first 20 bound references are shown; totals are retained-record counts, not current invocations.</p>
    </details></div>;
}
export function NorthstarGroup({ group }: { group: CoverageGroup }) {
  const { view, status } = useNorthstar(); const rows = view?.factory?.[group];
  const catalog = group === 'governance' ? [['independent_skeptic','Independent Skeptic / Red Team'], ['committee','Investment Committee'], ['risk','Deterministic Risk Inspection']] : factoryCatalog[group];
  const [selected, setSelected] = useState<string | null>(null);
  const [routeError, setRouteError] = useState(false);
  const selectedRef = useRef<string | null>(null); const groupRef = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null); const opener = useRef<HTMLButtonElement | null>(null);
  const resolveOpener = (id: string | null) => selectedOpener(id, [...(groupRef.current?.querySelectorAll<HTMLButtonElement>('[data-northstar-opener]') ?? [])].map(element => ({ id: element.dataset.northstarOpener ?? '', element })));
  useEffect(() => {
    const restore = () => {
      const match = window.location.hash.match(new RegExp(`/coverage/${group}/([^/]+)$`));
      const id = match?.[1] ?? null;
      // Resolve the restored identity, never the last-clicked or array-position opener.
      const target = id ?? selectedRef.current;
      if (target) opener.current = selectedOpener(target, [...(groupRef.current?.querySelectorAll<HTMLButtonElement>('[data-northstar-opener]') ?? [])].map(element => ({ id: element.dataset.northstarOpener ?? '', element })));
      selectedRef.current = id; setSelected(id);
    };
    const timer = setTimeout(restore, 0); window.addEventListener('popstate', restore); window.addEventListener('hashchange', restore);
    return () => { clearTimeout(timer); window.removeEventListener('popstate', restore); window.removeEventListener('hashchange', restore); };
  }, [group]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => { if (selected) heading.current?.focus(); else opener.current?.focus(); });
    return () => cancelAnimationFrame(frame);
  }, [selected]);
  const close = () => {
    const id = selectedRef.current; if (!id) return;
    selectedRef.current = null; setSelected(null);
    opener.current = resolveOpener(id);
    const hash = window.location.hash;
    if (hash.endsWith(`/coverage/${group}/${id}`)) {
      try {
        // Undo our own selection entry, never add another entry just to close.
        if (selectionHistoryAction(history.state, group, id, hash) === 'back') history.back();
        else history.replaceState(null, '', hash.split('/coverage/')[0]);
      } catch { setRouteError(true); } // Closing remains usable even if the browser refuses a URL update.
    }
  };
  const select = (row: { id: string }, button: HTMLButtonElement) => {
    const hash = `${window.location.hash.split('/coverage/')[0] || '#gallery'}/coverage/${group}/${row.id}`;
    if (!boundedNavigation(history, window.location.hash, hash, {northstarSelection:{group,id:row.id,hash}})) { setRouteError(true); return; }
    setRouteError(false); opener.current = button; selectedRef.current = row.id; setSelected(row.id);
  };
  const chosen = rows?.find(r => r.id === selected);
  return <section ref={groupRef} className="northstar-department" data-coverage={group}><header><span>GOVERNED OBSERVATION · {status}</span><h2>{titles[group]}</h2></header>
    {routeError && <p role="alert">Browser navigation update unavailable. No source data or authority changed.</p>}
    {!rows && <p>UNAVAILABLE — configured source-catalog identities only; no verified projection or individual activity.</p>}
    <div className="northstar-room-grid">
      {catalog.map(([id, name]) => { const row = rows?.find(r => r.id === id); return <article key={id} data-coverage-id={id}>
        {group === 'agents' && id in LIVING_CAST && <CinematicCharacterPortrait characterKey={id as LivingCastKey} variant="card" />}
        <h3>{name}</h3><p>{row?.operational_state ?? 'UNAVAILABLE'} · {row?.readiness ?? 'UNAVAILABLE'}</p><p>Evidence: {display(row?.evidence_classifications)}</p>
        <p>{row?.limitation ?? 'NO_VERIFIED_PROJECTION'}</p><button data-northstar-opener={id} onClick={e => select({ id }, e.currentTarget)} aria-expanded={selected === id} aria-controls={selected === id ? `northstar-${group}-selected` : undefined}>Inspect {name}</button>
      </article>; })}
    </div>
    {selected && <section id={`northstar-${group}-selected`} role="region" aria-labelledby={`northstar-${group}-heading`} className="northstar-selected" onKeyDown={e => {
      const target = e.target instanceof Element ? e.target : null;
      const detail = target?.closest('details[open]') as HTMLDetailsElement | null;
      const nested = detail && e.currentTarget.contains(detail) ? detail : null;
      const action = escapeLayer({...e,isComposing:e.nativeEvent.isComposing}, !!target && e.currentTarget.contains(target), !!nested);
      if (action === 'ignore') return;
      e.preventDefault(); e.stopPropagation();
      if (action === 'disclosure') { nested!.open = false; nested!.querySelector('summary')?.focus(); }
      else close();
    }}>
      <button onClick={close}>Back to {titles[group]}</button><h3 id={`northstar-${group}-heading`} ref={heading} tabIndex={-1}>{chosen?.name ?? 'RECORD UNAVAILABLE'}</h3>
      {chosen ? <NorthstarRow row={chosen} /> : <p>No record is invented or substituted for an unknown identity.</p>}
    </section>}
  </section>;
}
export function NorthstarSessionStatus() {
  const { view, status, reason } = useNorthstar();
  const lineage = view?.lineage;
  return <section className="northstar-session-status" aria-label="Full-session status"
    data-package-hash={lineage?.package_hash} data-projection-hash={lineage?.projection_hash}
    data-backend-instance={lineage?.backend_instance_hash} data-source-cycle={view?.source_cycle}>
    <header><span>ISOLATED DENY-ONLY SHADOW · NOT PERMANENT PRODUCTION</span>
    <h1>{lineage ? 'Northstar · Historical Replay' : 'Northstar · Full-Session Observation'}</h1><strong role="status">{status} · {view?.phase ?? 'UNAVAILABLE'}</strong><p>{reason}</p></header>
    {lineage && <p>Historical/replay evidence only. CURRENT describes publication health, not market freshness.
      Original capture watermark: {lineage.common_watermark}. New publication time: {view?.published_at}.</p>}
    {status !== 'CURRENT' && <p role="alert">DEGRADED — all displayed records are the last verified projection, not current activity. No fallback source is used.</p>}
    <p>RUNNING is not LIVE_DATA. CONFIGURED is not CONNECTED. AVAILABLE is not VERIFIED. HISTORICAL is not REPLAY. IDLE is not FAILED. OBSERVATION_ONLY is not AUTHORIZED.</p>
    <dl>{[['Session',view?.session],['Source generation',view?.source_generation],['Source cycle',view?.source_cycle],
      ['Source cycle time',view?.source_cycle_generated_at],['Projection time',view?.published_at],['Capture',view?.capture_status],
      ['Readiness',view?.readiness],['Permanent production',view?.factory?.permanent_production],['Incidents',view?.incidents],
      ['Observer-only counters',view?.counters],['Authority',view?.capabilities]].map(([k,v]) => <div key={String(k)}><dt>{String(k)}</dt><dd>{display(v)}</dd></div>)}</dl>
    {lineage ? <p>SESSION_CLOSED — historical review; no market-session phases were performed.</p>
      : <details><summary>Session timeline — not a claim that a phase occurred</summary><ol>{sessionPhases.map(phase => <li key={phase} aria-current={view?.phase === phase ? 'step' : undefined}>{phase}</li>)}</ol></details>}
  </section>;
}
export function NorthstarDayTrading() {
  const row = useNorthstar().view?.factory?.day_trading;
  return <section className="northstar-department" data-coverage="day-trading"><header><span>LOCKED · FAIL CLOSED</span><h2>Day Trading · OBSERVATION_ONLY</h2></header>
    <p>Paper authority: false · Live authority: false · Order allowance: 0 · Broker connection: false</p>
    <p>No orders or fills are created by this deny-only observer. Historical orders/fills: UNAVAILABLE unless individually provided by governed history.</p>
    {row ? <NorthstarRow row={row} /> : <p>UNAVAILABLE — no governed retained paper snapshot.</p>}</section>;
}
export function NorthstarHistory() {
  const { view } = useNorthstar();
  return <><NorthstarGroup group="history"/><section className="northstar-department"><h2>Separate Universe Identities</h2>
    {view?.universes.map(u => <article key={u.capture_id}><h3>{u.count}-member universe</h3><p>{u.capture_id}</p><p>{u.capture_time} · {u.source_classes.join(' · ')}</p></article>)}
    <details><summary>Original source clocks and classifications</summary>{view?.sources.map(s => <dl key={s.store}>{Object.entries(s).map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{display(v)}</dd></div>)}</dl>)}</details>
    <p>Separate captures are not merged into invented product membership.</p></section></>;
}
