import { useEffect, useMemo, useState } from "react";
import "./HistoricalMarketIntelligence.css";

type JsonObject = Record<string, unknown>;
type Pipeline = { stage?: string; state?: string; note?: string };
type Coverage = { symbol?: string; label?: string; start_date?: string | null; end_date?: string | null; row_count?: number; coverage_quality?: string; provider?: string; error?: string | null };
type Study = { symbol?: string; label?: string; status?: string; as_of_date?: string; analog_count?: number; summary?: Record<string, { median_pct?: number; positive_rate_pct?: number; sample_count?: number }> };
type Historical = { status?: string; mode?: string; historical_scope?: JsonObject; cycle?: JsonObject; pipeline?: Pipeline[]; coverage?: Coverage[]; studies?: Study[]; research_summary?: JsonObject; next_research?: string[] };

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}
function pct(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "—"; }
async function load(signal?: AbortSignal): Promise<Historical> {
  const response = await fetch(`/historical_market_intelligence.json?ts=${Date.now()}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`Historical Market Intelligence HTTP ${response.status}`);
  return response.json() as Promise<Historical>;
}

export default function HistoricalMarketIntelligence() {
  const [data, setData] = useState<Historical | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try { const next = await load(controller.signal); if (!disposed) { setData(next); setError(null); } }
      catch (reason) { if (!disposed) setError(reason instanceof Error ? reason.message : "Historical research unavailable"); }
    };
    void refresh(); const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);
  const studies = useMemo(() => (data?.studies ?? []).filter((row) => row.status === "ANALOG_STUDY_READY").slice(0, 8), [data]);
  const coverage = useMemo(() => (data?.coverage ?? []).slice(0, 12), [data]);
  if (!data) return <section className="hmi-shell"><span>BATCH 10H · HISTORICAL MARKET INTELLIGENCE</span><h2>OPENING THE ARCHIVES</h2><p>{error ?? "Waiting for the first governed historical-research cycle."}</p></section>;
  const cycle = data.cycle ?? {}; const summary = data.research_summary ?? {}; const scope = data.historical_scope ?? {};
  return (
    <section className="hmi-shell">
      <div className="hmi-hero"><div><span>BATCH 10H · HISTORICAL MARKET INTELLIGENCE</span><h2>The market closes. The research floor does not.</h2><p>10H continuously studies the deepest trustworthy history actually available, searches for comparable setups, and measures what happened next. It reports real provider coverage instead of pretending modern datasets reach back to the NYSE's origin.</p></div><div className="hmi-guard"><strong>24 / 7 RESEARCH</strong><span>READ ONLY · ADVISORY</span><em>LIVE EXECUTION FALSE</em></div></div>
      <div className="hmi-safety"><span>AUTO TRADE · FALSE</span><span>AUTO WEIGHTS · FALSE</span><span>AUTO EXPOSURE · FALSE</span><span>CAPITAL AUTHORITY · FALSE</span></div>
      <div className="hmi-score"><article><span>RESEARCH STATUS</span><strong>{text(data.status).replaceAll("_", " ")}</strong></article><article><span>CYCLES COMPLETED</span><strong>{text(cycle.cycle_count, "0")}</strong></article><article><span>STUDIES READY</span><strong>{text(summary.studies_ready, "0")}</strong></article><article><span>TARGETS KNOWN</span><strong>{text(summary.targets_known, "0")}</strong></article><article><span>LAST BATCH</span><strong>{Array.isArray(cycle.processed_symbols) ? cycle.processed_symbols.join(" · ") : "—"}</strong></article></div>
      <section className="hmi-panel"><div className="hmi-title"><div><span>RESEARCH CONVEYOR</span><h3>What works after the bell</h3></div><strong>{text(data.mode).replaceAll("_", " ")}</strong></div><div className="hmi-pipeline">{(data.pipeline ?? []).map((row) => <article key={text(row.stage)}><strong>{text(row.stage).replaceAll("_", " ")}</strong><span>{text(row.state).replaceAll("_", " ")}</span>{row.note ? <p>{row.note}</p> : null}</article>)}</div></section>
      <section className="hmi-panel"><div className="hmi-title"><div><span>HISTORICAL ANALOG DESK</span><h3>Current setups versus prior market states</h3></div></div><div className="hmi-studies">{studies.length ? studies.map((study) => { const five = study.summary?.fwd_5d; const twenty = study.summary?.fwd_20d; return <article key={text(study.symbol)}><header><strong>{text(study.symbol)}</strong><span>{text(study.as_of_date)}</span></header><h4>{text(study.label)}</h4><p>{text(study.analog_count, "0")} valid analogs · no future leakage</p><div><span>5D MEDIAN <b>{pct(five?.median_pct)}</b></span><span>5D POSITIVE <b>{pct(five?.positive_rate_pct)}</b></span><span>20D MEDIAN <b>{pct(twenty?.median_pct)}</b></span><span>20D POSITIVE <b>{pct(twenty?.positive_rate_pct)}</b></span></div></article>; }) : <article><strong>WARM UP</strong><p>No valid analog study has been persisted yet. 10H will not invent one.</p></article>}</div></section>
      <section className="hmi-panel"><div className="hmi-title"><div><span>COVERAGE LEDGER</span><h3>How far back the data really goes</h3></div><strong>{text(scope.coverage_policy).replaceAll("_", " ")}</strong></div><div className="hmi-coverage">{coverage.map((row) => <article key={text(row.symbol)}><header><strong>{text(row.symbol)}</strong><span>{text(row.coverage_quality)}</span></header><p>{text(row.start_date, "NOT AVAILABLE")} → {text(row.end_date, "NOT AVAILABLE")}</p><em>{text(row.row_count, "0")} rows · {text(row.provider, "NO PROVIDER")}</em>{row.error ? <small>{row.error}</small> : null}</article>)}</div><p className="hmi-note">{text(scope.note)}</p></section>
      <div className="hmi-footer"><span>ARCHIVES · KEEP WORKING</span><span>ANALOGS · EVIDENCE ONLY</span><span>HISTORY COVERAGE · NEVER FAKED</span><span>HUMAN APPROVAL REQUIRED</span></div>
      {error ? <div className="hmi-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
