import { useEffect, useMemo, useState } from "react";
import "./DataExpansionFactory.css";

type Gap = { gap_id?: string; severity?: string; evidence?: string };
type Source = {
  source_id?: string;
  source_name?: string;
  domain?: string;
  source_class?: string;
  closes_gaps?: string[];
  research_basis?: string;
  access_state?: string;
  intake_stage?: string;
  priority_score?: number;
  current_in_factory?: boolean;
  shadow_feed_connected?: boolean;
  production_feed_enabled?: boolean;
  quality_measurement_state?: string;
  latency_measurement_state?: string;
  coverage_measurement_state?: string;
  data_provider_cost?: string;
  licensing_state?: string;
  credential_state?: string;
  governance_risk?: string;
  recommended_action?: string;
  shadow_acceptance_tests?: string[];
  suggested_implementation_batch?: string;
};
type Inventory = {
  source_id?: string;
  source_name?: string;
  domain?: string;
  implementation_evidence?: string;
  inventory_state?: string;
};
type Factory = {
  status?: string;
  mission?: string;
  generated_at?: string;
  current_source_inventory?: Inventory[];
  data_gaps?: Gap[];
  candidate_sources?: Source[];
  full_candidate_count?: number;
  comparison_dimensions?: string[];
  intake_pipeline?: string[];
  shadow_trials?: unknown[];
  approved_sources?: unknown[];
  rejected_sources?: unknown[];
  summary?: {
    existing_implementation_count?: number;
    identified_gap_count?: number;
    candidate_source_count?: number;
    public_first_party_candidate_count?: number;
    commercial_research_candidate_count?: number;
    internal_measurement_candidate_count?: number;
    shadow_connected_count?: number;
    approved_source_count?: number;
    production_sources_added?: number;
  };
  source_state?: Record<string, unknown>;
  safety?: Record<string, boolean>;
};

function text(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}

function stateClass(value: unknown): string {
  const state = text(value, "UNKNOWN").toUpperCase();
  if (state.includes("READY") || state.includes("PRESENT") || state.includes("OFFICIAL")) return "good";
  if (state.includes("RESEARCH") || state.includes("REQUIRED") || state.includes("NOT_") || state.includes("GAP")) return "warn";
  return "neutral";
}

async function loadFactory(signal?: AbortSignal): Promise<Factory> {
  const response = await fetch(`/data_expansion_factory.json?ts=${Date.now()}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`Data Expansion Factory returned HTTP ${response.status}`);
  return response.json() as Promise<Factory>;
}

export default function DataExpansionFactory() {
  const [factory, setFactory] = useState<Factory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try {
        const next = await loadFactory(controller.signal);
        if (!disposed) {
          setFactory(next);
          setError(null);
        }
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "Data factory unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const candidates = useMemo(() => factory?.candidate_sources ?? [], [factory]);
  const gaps = useMemo(() => factory?.data_gaps ?? [], [factory]);
  const inventory = useMemo(() => factory?.current_source_inventory ?? [], [factory]);

  if (!factory) {
    return (
      <section className="dex-shell dex-waiting">
        <span>BATCH 9R · DATA EXPANSION FACTORY</span>
        <h2>{error ? "DATA FACTORY WARM-UP" : "SCOUTING INTELLIGENCE GAPS"}</h2>
        <p>{error ?? "Waiting for the first governed source-expansion memo."}</p>
      </section>
    );
  }

  return (
    <section className="dex-shell">
      <div className="dex-hero">
        <div>
          <span>BATCH 9R · DATA EXPANSION FACTORY</span>
          <h2>Feed the factory. Don&apos;t poison it.</h2>
          <p>
            Find data that closes a measured intelligence gap, compare it before trusting it, shadow-test it before production, and keep credentials, contracts and spend under human control.
          </p>
        </div>
        <div className="dex-guard">
          <strong>RESEARCH + SHADOW ONLY</strong>
          <span>HUMAN APPROVAL REQUIRED</span>
          <em>LIVE EXECUTION FALSE</em>
        </div>
      </div>

      <div className="dex-safety">
        <span>AUTO CONNECT PROVIDER · FALSE</span>
        <span>PURCHASE / LICENSE AUTHORITY · FALSE</span>
        <span>PRODUCTION FEED AUTHORITY · FALSE</span>
        <span>CAPITAL AUTHORITY · FALSE</span>
      </div>

      <div className="dex-scoreboard">
        <article><span>EXISTING IMPLEMENTATIONS</span><strong>{factory.summary?.existing_implementation_count ?? inventory.length}</strong></article>
        <article><span>MEASURED GAPS</span><strong>{factory.summary?.identified_gap_count ?? gaps.length}</strong></article>
        <article><span>CANDIDATE SOURCES</span><strong>{factory.summary?.candidate_source_count ?? factory.full_candidate_count ?? candidates.length}</strong></article>
        <article><span>SHADOW FEEDS CONNECTED</span><strong>{factory.summary?.shadow_connected_count ?? 0}</strong></article>
        <article><span>PRODUCTION SOURCES ADDED</span><strong>{factory.summary?.production_sources_added ?? 0}</strong></article>
      </div>

      <div className="dex-main-grid">
        <section className="dex-panel">
          <header>
            <div><span>INTELLIGENCE GAP MAP</span><h3>Why we need more data</h3></div>
            <strong>{text(factory.status, "WARM-UP").replaceAll("_", " ")}</strong>
          </header>
          <div className="dex-gaps">
            {gaps.map((gap) => (
              <div key={text(gap.gap_id)}>
                <span className={`dex-state dex-state--${stateClass(gap.severity)}`}>{text(gap.severity)}</span>
                <strong>{text(gap.gap_id).replaceAll("_", " ")}</strong>
                <p>{text(gap.evidence)}</p>
              </div>
            ))}
            {!gaps.length ? <p className="dex-empty">No persisted intelligence gap currently qualifies for source expansion.</p> : null}
          </div>
        </section>

        <section className="dex-panel">
          <header><div><span>CURRENT SOURCE INVENTORY</span><h3>Implementation evidence already in IIOS</h3></div></header>
          <div className="dex-inventory">
            {inventory.map((source) => (
              <div key={text(source.source_id)}>
                <div><strong>{text(source.source_name)}</strong><span>{text(source.domain).replaceAll("_", " ")}</span></div>
                <em>{text(source.inventory_state).replaceAll("_", " ")}</em>
                <small>{text(source.implementation_evidence)}</small>
              </div>
            ))}
          </div>
          <p className="dex-note">Inventory means an implementation path exists. It is not a claim of production health, contractual rights or current availability.</p>
        </section>
      </div>

      <section className="dex-candidates-section">
        <div className="dex-section-title">
          <div><span>EXPANSION QUEUE</span><h3>Ranked source candidates</h3></div>
          <strong>NO SOURCE IS CONNECTED BY THIS SCREEN</strong>
        </div>
        <div className="dex-candidates">
          {candidates.map((source, index) => (
            <article key={text(source.source_id, String(index))}>
              <header>
                <div>
                  <span>#{index + 1} · PRIORITY {text(source.priority_score, "—")}</span>
                  <h4>{text(source.source_name)}</h4>
                  <em>{text(source.domain).replaceAll("_", " ")}</em>
                </div>
                <div className={`dex-class dex-class--${stateClass(source.source_class)}`}>{text(source.source_class).replaceAll("_", " ")}</div>
              </header>
              <p>{text(source.research_basis)}</p>
              <div className="dex-gap-tags">
                {(source.closes_gaps ?? []).map((gap) => <span key={gap}>{gap.replaceAll("_", " ")}</span>)}
              </div>
              <div className="dex-measures">
                <div><span>Coverage</span><strong>{text(source.coverage_measurement_state)}</strong></div>
                <div><span>Latency</span><strong>{text(source.latency_measurement_state)}</strong></div>
                <div><span>Quality</span><strong>{text(source.quality_measurement_state)}</strong></div>
                <div><span>Cost</span><strong>{text(source.data_provider_cost)}</strong></div>
                <div><span>Licensing</span><strong>{text(source.licensing_state)}</strong></div>
                <div><span>Credentials</span><strong>{text(source.credential_state)}</strong></div>
              </div>
              <div className="dex-action">
                <span>{text(source.intake_stage).replaceAll("_", " ")}</span>
                <strong>{text(source.recommended_action).replaceAll("_", " ")}</strong>
              </div>
              <footer>
                <span>SHADOW CONNECTED · {source.shadow_feed_connected ? "TRUE" : "FALSE"}</span>
                <span>PRODUCTION · {source.production_feed_enabled ? "TRUE" : "FALSE"}</span>
                <strong>{text(source.suggested_implementation_batch)}</strong>
              </footer>
            </article>
          ))}
        </div>
      </section>

      <div className="dex-bottom-grid">
        <section className="dex-panel">
          <header><div><span>PROVIDER / SOURCE SCORECARD</span><h3>What must be measured before approval</h3></div></header>
          <div className="dex-rubric">
            {(factory.comparison_dimensions ?? []).map((dimension) => <span key={dimension}>{dimension.replaceAll("_", " ")}</span>)}
          </div>
          <p className="dex-note">A candidate does not get a numerical vendor score until those measurements are persisted. Unknown is better than fake precision.</p>
        </section>

        <section className="dex-panel">
          <header><div><span>GOVERNED INTAKE CONVEYOR</span><h3>Research → shadow → approval</h3></div></header>
          <div className="dex-pipeline">
            {(factory.intake_pipeline ?? []).map((stage, index) => (
              <div key={stage}><span>{String(index + 1).padStart(2, "0")}</span><strong>{stage.replaceAll("_", " ")}</strong></div>
            ))}
          </div>
        </section>
      </div>

      <div className="dex-contract">
        <strong>DATA FACTORY CONTRACT</strong>
        <span>NO AUTO CREDENTIAL REQUESTS</span>
        <span>NO PURCHASE AUTHORITY</span>
        <span>NO LICENSE ACCEPTANCE</span>
        <span>NO PRODUCTION FEED CHANGES</span>
        <span>HUMAN APPROVAL REQUIRED</span>
      </div>
      {error ? <div className="dex-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
