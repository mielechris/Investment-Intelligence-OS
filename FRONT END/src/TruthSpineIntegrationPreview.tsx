import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './TruthSpinePreview.css';

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
  useEffect(() => {
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    const abort = new AbortController();
    async function poll() {
      try {
        const response = await fetch('/truth-spine/museum', { cache: 'no-store', credentials: 'omit', signal: abort.signal });
        const value: unknown = await response.json();
        if (!response.ok || !validView(value)) throw new Error('UNAVAILABLE');
        if (!stopped) setView(value);
      } catch { if (!stopped) setView(null); }
      if (!stopped) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { stopped = true; abort.abort(); clearTimeout(timer); };
  }, []);
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
