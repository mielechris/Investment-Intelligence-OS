import { useEffect, useMemo, useState } from "react";
import "./AgentPerformanceLeague.css";

type JsonObject = Record<string, unknown>;
type AgentRow = {
  display_rank?: number | null;
  agent_key?: string;
  agent?: string;
  status?: string;
  observations?: number;
  decisive_outcomes?: number;
  aligned_outcomes?: number;
  alignment_rate_pct?: number | null;
  average_confidence?: number | null;
  recent_case_participation?: number;
  league_score?: number | null;
  official_ranking_eligible?: boolean;
  outcome_attribution?: Record<string, number>;
};
type ModelRow = {
  model?: string;
  status?: string;
  task_accuracy?: number | null;
  latency?: number | null;
  cost_per_useful_result?: number | null;
  why_unranked?: string;
};
type League = {
  status?: string;
  purpose?: string;
  summary?: Record<string, number>;
  agent_standings?: AgentRow[];
  model_league?: ModelRow[];
  measurement_contract?: {
    measured_now?: string[];
    measurement_gaps?: string[];
    miss_attribution_rule?: string;
  };
  source_state?: JsonObject;
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
function statusClass(value: unknown) {
  const status = text(value, "WARM_UP").toUpperCase();
  if (status === "OFFICIAL") return "official";
  if (status === "PROVISIONAL") return "provisional";
  return "warm";
}

async function loadLeague(signal?: AbortSignal): Promise<League> {
  const response = await fetch(`/agent_performance_league.json?ts=${Date.now()}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`Agent Performance League returned HTTP ${response.status}`);
  return response.json() as Promise<League>;
}

export default function AgentPerformanceLeague() {
  const [league, setLeague] = useState<League | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try {
        const next = await loadLeague(controller.signal);
        if (!disposed) { setLeague(next); setError(null); }
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "League unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);

  const agents = useMemo(() => league?.agent_standings ?? [], [league]);
  const models = useMemo(() => league?.model_league ?? [], [league]);
  if (!league) {
    return <section className="apl-shell apl-waiting"><span>BATCH 9S · AGENT PERFORMANCE LEAGUE</span><h2>{error ? "LEAGUE WARM-UP" : "BUILDING THE SCOREBOARD"}</h2><p>{error ?? "Waiting for persisted 9J agent outcome evidence."}</p></section>;
  }
  const summary = league.summary ?? {};
  return (
    <section className="apl-shell">
      <div className="apl-hero">
        <div>
          <span>BATCH 9S · AGENT PERFORMANCE LEAGUE</span>
          <h2>Score the desk. Don&apos;t rig the Committee.</h2>
          <p>Agent and model performance is ranked only where persisted outcome evidence exists. Warm-up and measurement gaps stay visible instead of becoming fake precision.</p>
        </div>
        <div className="apl-guard"><strong>SCOREBOARD ONLY</strong><span>HUMAN APPROVAL REQUIRED</span><em>LIVE EXECUTION FALSE</em></div>
      </div>
      <div className="apl-safety"><span>AUTO REWEIGHT AGENTS · FALSE</span><span>AUTO ROUTE MODELS · FALSE</span><span>COMMITTEE / RISK AUTHORITY · FALSE</span><span>CAPITAL AUTHORITY · FALSE</span></div>
      <div className="apl-scoreboard">
        <article><span>SPECIALISTS</span><strong>{text(summary.agent_count, "8")}</strong></article>
        <article><span>OFFICIAL RANKINGS</span><strong>{text(summary.officially_ranked_count, "0")}</strong></article>
        <article><span>PROVISIONAL</span><strong>{text(summary.provisional_count, "0")}</strong></article>
        <article><span>WARM-UP</span><strong>{text(summary.warm_up_count, "0")}</strong></article>
        <article><span>UNATTRIBUTED MISSES</span><strong>{text(summary.unattributed_factory_miss_count, "0")}</strong></article>
      </div>

      <section className="apl-board">
        <div className="apl-section-title"><div><span>EIGHT-SPECIALIST LEAGUE TABLE</span><h3>Outcome-alignment standings</h3></div><strong>{text(league.status).replaceAll("_", " ")}</strong></div>
        <div className="apl-table">
          <div className="apl-row apl-head"><span>Rank</span><span>Desk</span><span>Status</span><span>Decisive</span><span>Aligned</span><span>Alignment</span><span>Avg conf.</span><span>Recent cases</span></div>
          {agents.map((row) => (
            <div className="apl-row" key={text(row.agent_key)}>
              <strong>{row.display_rank ?? "—"}</strong><strong>{text(row.agent)}</strong><span className={`apl-state is-${statusClass(row.status)}`}>{text(row.status).replaceAll("_", " ")}</span><span>{text(row.decisive_outcomes, "0")}</span><span>{text(row.aligned_outcomes, "0")}</span><span>{pct(row.alignment_rate_pct)}</span><span>{pct(typeof row.average_confidence === "number" ? row.average_confidence * 100 : null)}</span><span>{text(row.recent_case_participation, "0")}</span>
              <div className="apl-attribution">
                <span>Saves aligned · {text(row.outcome_attribution?.downside_avoidance_alignment, "0")}</span>
                <span>False-positive misalignments · {text(row.outcome_attribution?.false_positive_misalignment, "0")}</span>
                <span>Foregone-upside misalignments · {text(row.outcome_attribution?.foregone_upside_misalignment, "0")}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="apl-two-col">
        <section className="apl-panel">
          <div className="apl-section-title"><div><span>MODEL LEAGUE</span><h3>Grok · Gemini · OpenAI · Kimi</h3></div><strong>NO FAKE RANKINGS</strong></div>
          <div className="apl-model-grid">
            {models.map((row) => <article key={text(row.model)}><header><strong>{text(row.model)}</strong><span>{text(row.status).replaceAll("_", " ")}</span></header><p>{text(row.why_unranked)}</p><footer>Task accuracy · — &nbsp; Latency · — &nbsp; Cost/useful result · —</footer></article>)}
          </div>
        </section>
        <section className="apl-panel">
          <div className="apl-section-title"><div><span>MEASUREMENT CONTRACT</span><h3>What counts—and what does not</h3></div></div>
          <div className="apl-contract"><div><strong>MEASURED NOW</strong>{(league.measurement_contract?.measured_now ?? []).map((item) => <span key={item}>{item}</span>)}</div><div><strong>MEASUREMENT GAPS</strong>{(league.measurement_contract?.measurement_gaps ?? []).map((item) => <span key={item}>{item}</span>)}</div></div>
          <div className="apl-miss-rule"><strong>MISS ATTRIBUTION RULE</strong><p>{text(league.measurement_contract?.miss_attribution_rule)}</p></div>
        </section>
      </div>
      <div className="apl-footer"><span>OFFICIAL SAMPLE GATE · 20 DECISIVE OUTCOMES PER DESK</span><span>WEIGHT CHANGES · HUMAN REVIEW ONLY</span><span>MODEL ROUTING CHANGES · HUMAN REVIEW ONLY</span></div>
      {error ? <div className="apl-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
