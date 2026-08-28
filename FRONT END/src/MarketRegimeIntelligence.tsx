import { useEffect, useMemo, useState } from "react";
import "./MarketRegimeIntelligence.css";

type JsonObject = Record<string, unknown>;
type Dimension = { dimension?: string; state?: string; value?: unknown; evidence?: string };
type Regime = {
  status?: string;
  current_regime?: JsonObject;
  dimensions?: Dimension[];
  regime_tag_contract?: JsonObject;
  factory_context?: JsonObject;
  recommended_next_measurements?: string[];
};

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}
function pct(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
}
function stateClass(value: unknown) {
  return text(value, "MEASUREMENT_GAP").toUpperCase() === "MEASURED" ? "measured" : "gap";
}

async function loadRegime(signal?: AbortSignal): Promise<Regime> {
  const response = await fetch(`/market_regime_intelligence.json?ts=${Date.now()}`, {
    headers: { Accept: "application/json" }, cache: "no-store", signal,
  });
  if (!response.ok) throw new Error(`Market Regime Intelligence returned HTTP ${response.status}`);
  return response.json() as Promise<Regime>;
}

export default function MarketRegimeIntelligence() {
  const [regime, setRegime] = useState<Regime | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try {
        const next = await loadRegime(controller.signal);
        if (!disposed) { setRegime(next); setError(null); }
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "Regime intelligence unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);

  const dimensions = useMemo(() => regime?.dimensions ?? [], [regime]);
  if (!regime) {
    return <section className="mri-shell mri-waiting"><span>BATCH 9T · MARKET REGIME INTELLIGENCE</span><h2>{error ? "REGIME WARM-UP" : "READING THE WATER"}</h2><p>{error ?? "Waiting for persisted 9H cross-sectional evidence."}</p></section>;
  }
  const current = regime.current_regime ?? {};
  const context = regime.factory_context ?? {};
  const contract = regime.regime_tag_contract ?? {};
  return (
    <section className="mri-shell">
      <div className="mri-hero">
        <div>
          <span>BATCH 9T · MARKET REGIME INTELLIGENCE</span>
          <h2>Know the water before you blame the boat.</h2>
          <p>9T classifies only what IIOS can actually measure today. Cross-sectional significant-mover regime is observed from independent 9H evidence; macro, liquidity and volatility dimensions remain measurement gaps until validated inputs exist.</p>
        </div>
        <div className="mri-guard"><strong>CLASSIFICATION ONLY</strong><span>ADVISORY METADATA</span><em>LIVE EXECUTION FALSE</em></div>
      </div>
      <div className="mri-safety"><span>AUTO THRESHOLD CHANGES · FALSE</span><span>AUTO AGENT WEIGHTS · FALSE</span><span>AUTO PORTFOLIO EXPOSURE · FALSE</span><span>CAPITAL AUTHORITY · FALSE</span></div>

      <div className="mri-regime-card">
        <div><span>CURRENT OBSERVED REGIME</span><h3>{text(current.regime_label).replaceAll("_", " ")}</h3><p>Scope · {text(current.scope).replaceAll("_", " ")}</p></div>
        <div className="mri-evidence"><strong>{text(current.evidence_level, "LOW")}</strong><span>EVIDENCE LEVEL</span><em>{text(current.sample_count, "0")} significant movers</em></div>
      </div>

      <div className="mri-scoreboard">
        <article><span>UPSIDE MOVERS</span><strong>{text(current.upside_count, "0")}</strong><em>{pct(current.upside_share_pct)}</em></article>
        <article><span>DOWNSIDE MOVERS</span><strong>{text(current.downside_count, "0")}</strong><em>{pct(current.downside_share_pct)}</em></article>
        <article><span>MEDIAN |MOVE|</span><strong>{pct(current.median_absolute_move_pct)}</strong></article>
        <article><span>MEAN |MOVE|</span><strong>{pct(current.mean_absolute_move_pct)}</strong></article>
        <article><span>EXTREME MOVES</span><strong>{text(current.extreme_move_count, "0")}</strong><em>≥ 7%</em></article>
        <article><span>9H MISS RATE</span><strong>{pct(context["9h_miss_rate_pct"])}</strong></article>
      </div>

      <section className="mri-panel">
        <div className="mri-title"><div><span>REGIME DIMENSIONS</span><h3>Measured versus unknown</h3></div><strong>{text(regime.status).replaceAll("_", " ")}</strong></div>
        <div className="mri-dimensions">
          {dimensions.map((row) => <article key={text(row.dimension)} className={`is-${stateClass(row.state)}`}><header><strong>{text(row.dimension).replaceAll("_", " ")}</strong><span>{text(row.state).replaceAll("_", " ")}</span></header><h4>{text(row.value, row.state === "MEASURED" ? "OBSERVED" : "NOT MEASURED")}</h4><p>{text(row.evidence)}</p></article>)}
        </div>
      </section>

      <div className="mri-two-col">
        <section className="mri-panel"><div className="mri-title"><div><span>REGIME TAG CONTRACT</span><h3>What 9T can attach to learning</h3></div></div><div className="mri-contract"><span>TAG NEW SESSIONS · {text(contract.tag_new_sessions)}</span><span>SCOPE · {text(contract.tagging_scope).replaceAll("_", " ")}</span><span>HISTORICAL BACKFILL · {text(contract.historical_backfill_available)}</span><span>REGIME-SPECIFIC AGENT PERFORMANCE · {text(contract.agent_regime_performance_available)}</span></div><p>{text(contract.agent_regime_performance_note)}</p></section>
        <section className="mri-panel"><div className="mri-title"><div><span>NEXT MEASUREMENTS</span><h3>What closes the regime gaps</h3></div></div><div className="mri-next">{(regime.recommended_next_measurements ?? []).map((item) => <span key={item}>{item}</span>)}</div></section>
      </div>
      <div className="mri-footer"><span>9H CROSS-SECTION · OBSERVED</span><span>MACRO / LIQUIDITY / VOL · NOT INVENTED</span><span>REGIME CHANGES · NEVER EXECUTE</span><span>HUMAN APPROVAL REQUIRED</span></div>
      {error ? <div className="mri-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
