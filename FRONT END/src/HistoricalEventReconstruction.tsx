import { useEffect, useMemo, useState } from "react";
import "./HistoricalEventReconstruction.css";

type EventContext = {
  status?: string;
  candidate_event_type?: string | null;
  association_confidence_pct?: number;
  article_count?: number;
};

type Reconstruction = {
  symbol?: string;
  label?: string;
  status?: string;
  current_event_context?: EventContext;
  analog_event_contexts_ready?: number;
  event_match_summary?: {
    current_event_type?: string | null;
    analog_count?: number;
    event_matched_analog_count?: number;
    event_matching_state?: string;
    event_matched_5d_median_pct?: number | null;
    event_matched_5d_sample?: number;
    event_matched_20d_median_pct?: number | null;
    event_matched_20d_sample?: number;
  };
};

type Payload = {
  status?: string;
  cycle?: { cycle_count?: number; processed_symbols?: string[]; error_count?: number };
  coverage?: {
    provider?: string;
    modern_news_corpus_start?: string;
    price_analog_studies_available?: number;
    symbols_reconstructed?: number;
    symbols_ready?: number;
    current_event_contexts_ready?: number;
    analog_event_contexts_ready?: number;
  };
  reconstructions?: Reconstruction[];
  research_summary?: {
    symbols_known?: number;
    symbols_reconstructed?: number;
    symbols_ready?: number;
    current_contexts_ready?: number;
    analog_contexts_ready?: number;
    errors?: string[];
  };
  measurement_plan?: { future_metric?: string; causal_language_policy?: string };
};

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function pct(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
}

async function load(signal?: AbortSignal): Promise<Payload> {
  const response = await fetch(`/historical_event_reconstruction.json?ts=${Date.now()}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`10J HTTP ${response.status}`);
  return response.json() as Promise<Payload>;
}

export default function HistoricalEventReconstruction() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try {
        const next = await load(controller.signal);
        if (!disposed) { setPayload(next); setError(null); }
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "10J unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);

  const rows = useMemo(() => payload?.reconstructions ?? [], [payload]);
  if (!payload) {
    return <section className="her-shell"><span>BATCH 10J · HISTORICAL EVENT RECONSTRUCTION</span><h2>EVENT CORPUS WARM-UP</h2><p>{error ?? "Waiting for governed historical event evidence."}</p></section>;
  }

  const summary = payload.research_summary ?? {};
  const coverage = payload.coverage ?? {};
  return (
    <section className="her-shell">
      <div className="her-hero">
        <div>
          <span>BATCH 10J · HISTORICAL EVENT RECONSTRUCTION</span>
          <h2>Same chart. Same reason? Prove it.</h2>
          <p>10J reconstructs event evidence around 10H analog dates and compares associated event types. Headlines near a market move are context, not proof of causality.</p>
        </div>
        <div className="her-guard"><strong>EVENT RESEARCH</strong><span>ASSOCIATION ≠ CAUSATION</span><em>LIVE EXECUTION FALSE</em></div>
      </div>

      <div className="her-safety"><span>AUTO TRADE · FALSE</span><span>AUTO WEIGHTS · FALSE</span><span>CAUSAL CLAIM AUTHORITY · FALSE</span><span>CAPITAL AUTHORITY · FALSE</span></div>

      <div className="her-score">
        <article><span>RESEARCH STATUS</span><strong>{text(payload.status).replaceAll("_", " ")}</strong></article>
        <article><span>SYMBOLS READY</span><strong>{text(summary.symbols_ready, "0")} / {text(summary.symbols_known, "0")}</strong></article>
        <article><span>CURRENT CONTEXTS READY</span><strong>{text(summary.current_contexts_ready, "0")}</strong></article>
        <article><span>ANALOG CONTEXTS READY</span><strong>{text(summary.analog_contexts_ready, "0")}</strong></article>
        <article><span>LAST BATCH</span><strong>{(payload.cycle?.processed_symbols ?? []).join(" · ") || "WARM-UP"}</strong></article>
      </div>

      <section className="her-panel">
        <header><div><span>TRUTH + COVERAGE CONTRACT</span><h3>What 10J can actually claim</h3></div><strong>{text(coverage.provider, "GDELT")}</strong></header>
        <div className="her-contract">
          <article><span>MODERN NEWS CORPUS START</span><strong>{text(coverage.modern_news_corpus_start)}</strong><p>Older price analogs remain valid price studies but do not receive invented event labels.</p></article>
          <article><span>EVENT LANGUAGE</span><strong>ASSOCIATED EVENT TYPE</strong><p>{text(payload.measurement_plan?.causal_language_policy)}</p></article>
          <article><span>MEASUREMENT</span><strong>PRICE-ONLY VS EVENT-MATCHED</strong><p>{text(payload.measurement_plan?.future_metric)}</p></article>
        </div>
      </section>

      <section className="her-panel">
        <header><div><span>EVENT RECONSTRUCTION DESK</span><h3>Current context versus historical analog context</h3></div><strong>READ ONLY · ADVISORY</strong></header>
        <div className="her-grid">
          {rows.map((row) => {
            const current = row.current_event_context ?? {};
            const match = row.event_match_summary ?? {};
            return (
              <article key={text(row.symbol)}>
                <header><div><span>{text(row.symbol)}</span><h4>{text(row.label)}</h4></div><em>{text(row.status).replaceAll("_", " ")}</em></header>
                <div className="her-current"><span>CURRENT ASSOCIATED EVENT</span><strong>{text(current.candidate_event_type, "UNCLASSIFIED").replaceAll("_", " ")}</strong><small>{pct(current.association_confidence_pct)} association confidence · {text(current.article_count, "0")} articles</small></div>
                <div className="her-metrics">
                  <div><span>Analog contexts ready</span><strong>{text(row.analog_event_contexts_ready, "0")}</strong></div>
                  <div><span>Event-matched analogs</span><strong>{text(match.event_matched_analog_count, "0")}</strong></div>
                  <div><span>Matched 5D median</span><strong>{pct(match.event_matched_5d_median_pct)}</strong><small>n={text(match.event_matched_5d_sample, "0")}</small></div>
                  <div><span>Matched 20D median</span><strong>{pct(match.event_matched_20d_median_pct)}</strong><small>n={text(match.event_matched_20d_sample, "0")}</small></div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <div className="her-footer"><span>EVENT EVIDENCE · GOVERNED</span><span>CAUSAL CLAIMS · FALSE</span><span>10H PRICE ANALOGS · PRESERVED</span><span>LIVE EXECUTION · FALSE</span></div>
      {error ? <div className="her-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
