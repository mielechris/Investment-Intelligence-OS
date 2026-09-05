import { useEffect, useMemo, useState } from "react";
import "./HistoricalMacroRegimeLibrary.css";

type SeriesRow = {
  series_id?: string;
  name?: string;
  family?: string;
  tier?: string;
  rows?: number;
  provider?: string;
  provider_error?: string | null;
};

type NormalizedStudy = {
  symbol?: string;
  label?: string;
  status?: string;
  as_of_date?: string;
  candidate_count?: number;
  current_macro_snapshot?: {
    tier_a_dimensions_ready?: number;
    tier_b_dimensions_ready?: number;
    tier_a_backtest_eligible?: Record<string, { value?: number }>;
  };
  macro_normalized_analogs?: Array<{
    date?: string;
    macro_similarity_score?: number;
    price_similarity_score?: number;
  }>;
};

type Payload = {
  status?: string;
  mode?: string;
  coverage?: {
    tier_a_series_ready?: number;
    tier_a_series_required_for_active?: number;
    tier_b_context_series_ready?: number;
    normalized_symbols_ready?: number;
    price_analog_studies_seen?: number;
    revision_policy?: string;
  };
  series_registry?: SeriesRow[];
  normalized_studies?: NormalizedStudy[];
  pipeline?: Array<{ stage?: string; state?: string; note?: string }>;
  research_summary?: { errors?: string[] };
};

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

async function load(signal?: AbortSignal): Promise<Payload> {
  const response = await fetch(`/historical_macro_regime_library.json?ts=${Date.now()}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`10K macro library HTTP ${response.status}`);
  return response.json() as Promise<Payload>;
}

export default function HistoricalMacroRegimeLibrary() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try { const next = await load(controller.signal); if (!disposed) { setPayload(next); setError(null); } }
      catch (reason) { if (!disposed) setError(reason instanceof Error ? reason.message : "10K unavailable"); }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);

  const studies = useMemo(() => payload?.normalized_studies ?? [], [payload]);
  const coverage = payload?.coverage ?? {};
  if (!payload) return <section className="hmr-shell"><span>BATCH 10K · HISTORICAL MACRO + REGIME</span><h2>MACRO LIBRARY WARM-UP</h2><p>{error ?? "Waiting for governed macro history."}</p></section>;

  return (
    <section className="hmr-shell">
      <div className="hmr-hero">
        <div>
          <span>BATCH 10K · HISTORICAL MACRO + REGIME NORMALIZATION</span>
          <h2>Same chart. Different economy.</h2>
          <p>10K asks whether a price analog happened under comparable policy rates, yield curve, volatility and credit conditions. Revised CPI, labor and GDP history stays context-only until point-in-time vintage-safe data exists.</p>
        </div>
        <div className="hmr-guard"><strong>READ-ONLY MACRO RESEARCH</strong><span>TIER B · CONTEXT ONLY</span><em>LIVE EXECUTION FALSE</em></div>
      </div>

      <div className="hmr-safety"><span>AUTO TRADE · FALSE</span><span>AUTO WEIGHTS · FALSE</span><span>AUTO EXPOSURE · FALSE</span><span>CAPITAL AUTHORITY · FALSE</span></div>

      <div className="hmr-score">
        <article><span>STATUS</span><strong>{text(payload.status).replaceAll("_", " ")}</strong></article>
        <article><span>TIER A SERIES</span><strong>{text(coverage.tier_a_series_ready, "0")} / 5</strong></article>
        <article><span>TIER B CONTEXT</span><strong>{text(coverage.tier_b_context_series_ready, "0")} / 4</strong></article>
        <article><span>NORMALIZED SYMBOLS</span><strong>{text(coverage.normalized_symbols_ready, "0")}</strong></article>
      </div>

      <section className="hmr-panel">
        <header><div><span>MACRO PIPELINE</span><h3>What can actually influence analog ranking</h3></div><strong>TIER A ONLY</strong></header>
        <div className="hmr-pipeline">{(payload.pipeline ?? []).map((row) => <article key={text(row.stage)}><span>{text(row.stage).replaceAll("_", " ")}</span><strong>{text(row.state).replaceAll("_", " ")}</strong><p>{text(row.note, "")}</p></article>)}</div>
      </section>

      <section className="hmr-panel">
        <header><div><span>SOURCE REGISTRY</span><h3>Actual governed history loaded</h3></div><strong>FRED · SYSTEM TRUST</strong></header>
        <div className="hmr-series">{(payload.series_registry ?? []).map((row) => <article key={text(row.series_id)}>
          <div><span>{text(row.series_id)}</span><strong>{text(row.name)}</strong></div>
          <em>{text(row.family).replaceAll("_", " ")}</em>
          <p>TIER {text(row.tier)} · {text(row.rows, "0")} ROWS · {row.provider_error ? "PROVIDER WARNING" : text(row.provider, "WAITING")}</p>
        </article>)}</div>
      </section>

      <section className="hmr-panel">
        <header><div><span>MACRO-NORMALIZED ANALOG DESK</span><h3>Price similarity filtered by economic backdrop</h3></div><strong>NO FUTURE-DATED OBSERVATIONS</strong></header>
        <div className="hmr-studies">{studies.map((study) => <article key={text(study.symbol)}>
          <header><div><span>{text(study.symbol)}</span><strong>{text(study.label)}</strong></div><em>{text(study.status).replaceAll("_", " ")}</em></header>
          <p>{text(study.current_macro_snapshot?.tier_a_dimensions_ready, "0")} backtest-eligible dimensions · {text(study.current_macro_snapshot?.tier_b_dimensions_ready, "0")} context-only dimensions</p>
          <div className="hmr-analogs">{(study.macro_normalized_analogs ?? []).slice(0, 4).map((analog) => <span key={`${study.symbol}-${analog.date}`}>{text(analog.date)} · MACRO {text(analog.macro_similarity_score)} · PRICE {text(analog.price_similarity_score)}</span>)}</div>
        </article>)}</div>
      </section>

      <div className="hmr-warning"><strong>REVISION / VINTAGE CONTRACT</strong><span>{text(coverage.revision_policy)}</span></div>
      <div className="hmr-footer"><span>MACRO RESEARCH · ACTIVE WHEN EVIDENCE EXISTS</span><span>TIER B · NOT USED FOR BACKTEST RANKING</span><span>10J EVENT EVIDENCE · PRESERVED</span><span>LIVE EXECUTION · FALSE</span></div>
      {error ? <div className="hmr-error">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
