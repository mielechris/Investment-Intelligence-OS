import { useEffect, useMemo, useState } from "react";
import "./MarketValidationStackPanel.css";

type Layer = {
  name: string;
  availability: string;
  path: string;
  age_seconds?: number | null;
  payload?: Record<string, unknown> | null;
};

type ValidationStack = {
  schema_version: string;
  generated_at: string;
  layers: {
    factory_telemetry: Layer;
    market_validation: Layer;
    shadow_strategy: Layer;
    outcome_learning: Layer;
  };
  safety: {
    preview_only: boolean;
    localhost_only: boolean;
    ledger_access: string;
    live_execution: boolean;
  };
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return fallback;
}

function pct(value: unknown): string {
  const number = numberValue(value);
  return number === null ? "—" : `${number.toFixed(1)}%`;
}

function money(value: unknown): string {
  const number = numberValue(value);
  return number === null
    ? "—"
    : number.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      });
}

function ageLabel(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return "WAITING";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function statusClass(value: string): string {
  const normalized = value.toUpperCase();
  if (
    normalized.includes("LIVE") ||
    normalized.includes("AVAILABLE") ||
    normalized.includes("HEALTHY") ||
    normalized.includes("ON_CADENCE") ||
    normalized.includes("COMPLETE")
  ) {
    return "mv-status mv-status--good";
  }
  if (
    normalized.includes("WAIT") ||
    normalized.includes("WARMUP") ||
    normalized.includes("PENDING") ||
    normalized.includes("SKIPPED")
  ) {
    return "mv-status mv-status--warm";
  }
  if (
    normalized.includes("STALE") ||
    normalized.includes("ERROR") ||
    normalized.includes("FAIL") ||
    normalized.includes("OFFLINE")
  ) {
    return "mv-status mv-status--bad";
  }
  return "mv-status";
}

function Status({ value }: { value: string }) {
  return <span className={statusClass(value)}>{value.replaceAll("_", " ")}</span>;
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div className="mv-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function LayerCard({ title, code, layer, children }: { title: string; code: string; layer: Layer; children: React.ReactNode }) {
  const payload = record(layer.payload);
  return (
    <article className="mv-layer-card">
      <header>
        <div>
          <span>{code}</span>
          <h3>{title}</h3>
        </div>
        <div className="mv-layer-state">
          <Status value={layer.availability} />
          <small>{ageLabel(layer.age_seconds)}</small>
        </div>
      </header>
      {layer.payload ? children : (
        <div className="mv-waiting">
          <strong>NO PERSISTED SNAPSHOT YET</strong>
          <p>This layer is waiting for its first eligible market-session output. Nothing is being fabricated.</p>
        </div>
      )}
      {payload.status ? <footer>{text(payload.status)}</footer> : null}
    </article>
  );
}

export default function MarketValidationStackPanel() {
  const [stack, setStack] = useState<ValidationStack | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const response = await fetch("/validation/stack", {
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`validation bridge ${response.status}`);
        const payload = (await response.json()) as ValidationStack;
        if (disposed) return;
        setStack(payload);
        setError(null);
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "validation bridge unavailable");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, []);

  const headline = useMemo(() => {
    if (!stack) return "CONNECTING";
    const layers = Object.values(stack.layers);
    const unavailable = layers.filter((layer) => layer.availability === "STALE").length;
    return unavailable ? `${unavailable} LAYER${unavailable === 1 ? "" : "S"} STALE` : "OBSERVATION STACK ONLINE";
  }, [stack]);

  if (!stack) {
    return (
      <section className="mv-shell">
        <div className="mv-hero">
          <div><span>IIOS MARKET OPERATIONS</span><h2>LIVE FACTORY VALIDATION STACK</h2></div>
          <Status value={error ? "OFFLINE" : "CONNECTING"} />
        </div>
        <div className="mv-waiting"><strong>{error ?? "Opening the read-only market operations bridge…"}</strong></div>
      </section>
    );
  }

  const telemetry = record(stack.layers.factory_telemetry.payload);
  const radar = record(telemetry.radar);
  const fund = record(telemetry.paper_fund);
  const cadence = record(telemetry.cadence);
  const observation = record(cadence.observation);
  const paperTrading = record(cadence.paper_trading);
  const radarCadence = record(cadence.radar);

  const validation = record(stack.layers.market_validation.payload);
  const metrics = record(validation.metrics);
  const shadow = record(stack.layers.shadow_strategy.payload);
  const outcome = record(stack.layers.outcome_learning.payload);
  const recentOutcomes = Array.isArray(outcome.recent_outcomes) ? outcome.recent_outcomes : [];
  const agentScorecards = Array.isArray(outcome.agent_scorecards) ? outcome.agent_scorecards : [];

  return (
    <section className="mv-shell">
      <div className="mv-hero">
        <div>
          <span>IIOS MARKET OPERATIONS · 9E → 9J</span>
          <h2>LIVE FACTORY VALIDATION STACK</h2>
          <p>Opportunity discovery, runtime telemetry, independent grading, shadow strategy and outcome learning — all read-only.</p>
        </div>
        <div className="mv-hero-state">
          <Status value={headline} />
          <small>PREVIEW · LOCALHOST ONLY · LIVE EXECUTION FALSE</small>
        </div>
      </div>

      <div className="mv-flow">
        <span>518-name market</span><b>→</b><span>9E Radar</span><b>→</b><span>8 agents</span><b>→</b><span>Committee / Risk</span><b>→</b><span>Paper</span><b>→</b><span>9H / 9I / 9J learning</span>
      </div>

      <div className="mv-grid">
        <LayerCard title="Factory + Opportunity Radar" code="9E / 9G" layer={stack.layers.factory_telemetry}>
          <div className="mv-metrics-grid">
            <Metric label="Universe" value={text(radar.governed_universe_count, "0")} />
            <Metric label="Radar hits" value={text(radar.screener_hit_count, "0")} />
            <Metric label="Grok candidates" value={text(radar.grok_candidate_count, "0")} />
            <Metric label="Gemini finalists" value={text(radar.gemini_candidate_count, "0")} />
            <Metric label="Promotion queue" value={text(radar.promotion_candidate_count, "0")} />
            <Metric label="NAV" value={money(fund.nav)} detail={`${text(fund.position_count, "0")} positions`} />
          </div>
          <div className="mv-cadence-row">
            <div><span>9A OBSERVATION</span><Status value={text(observation.cadence_state, "UNKNOWN")} /></div>
            <div><span>9B PAPER</span><Status value={text(paperTrading.cadence_state, "UNKNOWN")} /></div>
            <div><span>9E RADAR</span><Status value={text(radarCadence.cadence_state, "UNKNOWN")} /></div>
          </div>
        </LayerCard>

        <LayerCard title="Independent Market Scoreboard" code="9H" layer={stack.layers.market_validation}>
          <div className="mv-metrics-grid">
            <Metric label="Benchmark" value={validation.benchmark_complete === true ? "COMPLETE" : "WAITING"} />
            <Metric label="Detection rate" value={pct(metrics.detection_rate_pct)} />
            <Metric label="Miss rate" value={pct(metrics.opportunity_miss_rate_pct)} />
            <Metric label="Paper fills" value={text(metrics.paper_fill_count, "0")} />
          </div>
          <p className="mv-copy">Independent observer grades IIOS after a fully covered session. Partial days fail closed instead of pretending to be complete.</p>
        </LayerCard>

        <LayerCard title="Shadow Strategy Lab" code="9I" layer={stack.layers.shadow_strategy}>
          <div className="mv-metrics-grid">
            <Metric label="Complete sessions" value={text(shadow.complete_session_count, "0")} />
            <Metric label="Advice unlock" value={text(shadow.minimum_complete_sessions_for_advice, "5")} />
            <Metric label="Recommendations" value={Array.isArray(shadow.recommendations) ? shadow.recommendations.length : 0} />
          </div>
          <p className="mv-copy">Counterfactual score thresholds, radar breadth and case capacity stay shadow-only until enough complete sessions exist.</p>
        </LayerCard>

        <LayerCard title="Outcome Learning Memory" code="9J" layer={stack.layers.outcome_learning}>
          <div className="mv-metrics-grid">
            <Metric label="Complete sessions" value={text(outcome.complete_session_count, "0")} />
            <Metric label="Outcome labels" value={text(outcome.outcome_count, "0")} />
            <Metric label="Mature 5-day" value={text(outcome.mature_5d_count, "0")} />
            <Metric label="Review queue" value={Array.isArray(outcome.judgment_bank_review_queue) ? outcome.judgment_bank_review_queue.length : 0} />
          </div>
          {recentOutcomes.length ? (
            <div className="mv-list">
              {recentOutcomes.slice(0, 4).map((item, index) => {
                const row = record(item);
                return <div key={`${text(row.ticker, "outcome")}-${index}`}><strong>{text(row.ticker, "UNKNOWN")}</strong><span>{text(row.decision_quality_label, text(row.market_outcome_label, "PENDING"))}</span></div>;
              })}
            </div>
          ) : <p className="mv-copy">Waiting for the first complete 9H session before future-return labels can mature.</p>}
        </LayerCard>
      </div>

      {agentScorecards.length ? (
        <section className="mv-agent-strip">
          <div><span>LEARNING MEMORY</span><h3>Agent outcome alignment</h3></div>
          <div className="mv-agent-grid">
            {agentScorecards.slice(0, 8).map((item, index) => {
              const row = record(item);
              return <div key={`${text(row.agent_key, "agent")}-${index}`}><strong>{text(row.agent_key, "AGENT")}</strong><span>{text(row.observations, "0")} observations</span><em>{pct(row.alignment_rate_pct ?? row.accuracy_pct)}</em></div>;
            })}
          </div>
        </section>
      ) : null}
    </section>
  );
}
