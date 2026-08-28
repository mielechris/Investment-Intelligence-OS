import { useEffect, useMemo, useState } from "react";
import "./ChiefIntelligenceOffice.css";

type Upgrade = {
  upgrade_id?: string;
  title?: string;
  why_it_should_improve_intelligence?: string;
  supporting_evidence?: string[];
  expected_impact?: string;
  engineering_effort?: string;
  data_provider_cost?: string;
  safety_governance_risk?: string;
  production_shadow_research_recommendation?: string;
  suggested_implementation_batch?: string;
  priority_score?: number;
};

type Office = {
  status?: string;
  question?: string;
  generated_at?: string;
  current_weaknesses?: Array<{ area?: string; state?: string; evidence?: string }>;
  improvement_memo?: {
    top_five_upgrades?: Upgrade[];
    rejected_upgrades_and_why?: Array<{ upgrade?: string; reason?: string }>;
  };
  experiments_underway?: Array<Record<string, unknown>>;
  approved_upgrades?: Array<Record<string, unknown>>;
  rejected_upgrades?: Array<{ upgrade?: string; reason?: string }>;
  measured_improvement_after_implementation?: Array<Record<string, unknown>>;
  analysis_coverage?: Record<string, boolean>;
  safety?: Record<string, boolean>;
};

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}

function stateClass(value: unknown) {
  const v = text(value, "UNKNOWN").toUpperCase();
  if (v.includes("ACTIVE") || v.includes("READY") || v.includes("MEASURED")) return "good";
  if (v.includes("WARM") || v.includes("GAP") || v.includes("ATTENTION")) return "warn";
  return "neutral";
}

async function loadOffice(signal?: AbortSignal): Promise<Office> {
  const response = await fetch(`/chief_intelligence_office.json?ts=${Date.now()}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`Chief Intelligence Office returned HTTP ${response.status}`);
  return response.json() as Promise<Office>;
}

export default function ChiefIntelligenceOffice() {
  const [office, setOffice] = useState<Office | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try {
        const next = await loadOffice(controller.signal);
        if (!disposed) {
          setOffice(next);
          setError(null);
        }
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "Office unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const upgrades = useMemo(() => office?.improvement_memo?.top_five_upgrades ?? [], [office]);
  const coverage = useMemo(() => Object.entries(office?.analysis_coverage ?? {}), [office]);

  if (!office) {
    return (
      <section className="cio-shell cio-waiting">
        <span>BATCH 9P · CHIEF INTELLIGENCE OFFICE</span>
        <h2>{error ? "OFFICE WARM-UP" : "STUDYING THE FACTORY"}</h2>
        <p>{error ?? "Waiting for the first advisory improvement memo."}</p>
      </section>
    );
  }

  return (
    <section className="cio-shell">
      <div className="cio-hero">
        <div>
          <span>BATCH 9P · CHIEF INTELLIGENCE OFFICE</span>
          <h2>{office.question ?? "How do we make this investment firm smarter next?"}</h2>
          <p>
            A permanent advisory office that studies IIOS itself, ranks improvements, and routes proposed changes into research, shadow testing, or human review. It cannot change the factory on its own.
          </p>
        </div>
        <div className="cio-guard">
          <strong>ADVISORY ONLY</strong>
          <span>HUMAN APPROVAL REQUIRED</span>
          <em>LIVE EXECUTION FALSE</em>
        </div>
      </div>

      <div className="cio-safety">
        <span>AUTO THRESHOLD CHANGES · FALSE</span>
        <span>AGENT WEIGHT AUTHORITY · FALSE</span>
        <span>COMMITTEE / RISK AUTHORITY · FALSE</span>
        <span>CAPITAL AUTHORITY · FALSE</span>
      </div>

      <div className="cio-grid-head">
        <article>
          <span>CURRENT WEAKNESSES</span>
          <strong>{office.current_weaknesses?.length ?? 0}</strong>
        </article>
        <article>
          <span>PROPOSED UPGRADES</span>
          <strong>{upgrades.length}</strong>
        </article>
        <article>
          <span>EXPERIMENTS UNDERWAY</span>
          <strong>{office.experiments_underway?.length ?? 0}</strong>
        </article>
        <article>
          <span>MEASURED IMPROVEMENTS</span>
          <strong>{office.measured_improvement_after_implementation?.length ?? 0}</strong>
        </article>
      </div>

      <div className="cio-main-grid">
        <section className="cio-panel">
          <header>
            <div><span>FACTORY DIAGNOSTICS</span><h3>Current weaknesses</h3></div>
            <strong>{text(office.status, "WARM-UP").replaceAll("_", " ")}</strong>
          </header>
          <div className="cio-weaknesses">
            {(office.current_weaknesses ?? []).map((row) => (
              <div key={text(row.area)}>
                <span className={`cio-state cio-state--${stateClass(row.state)}`}>{text(row.state)}</span>
                <strong>{text(row.area).replaceAll("_", " ")}</strong>
                <p>{text(row.evidence)}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="cio-panel">
          <header><div><span>ANALYSIS COVERAGE</span><h3>What 9P can actually measure</h3></div></header>
          <div className="cio-coverage">
            {coverage.map(([key, value]) => (
              <div key={key} className={value ? "is-covered" : "is-gap"}>
                <strong>{key.replaceAll("_", " ")}</strong><span>{value ? "MEASURED" : "MEASUREMENT GAP"}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="cio-memo">
        <div className="cio-section-title">
          <div><span>IIOS IMPROVEMENT MEMO</span><h3>Top five upgrades</h3></div>
          <strong>RANKED · EVIDENCE-BACKED · NON-BINDING</strong>
        </div>
        <div className="cio-upgrades">
          {upgrades.map((upgrade, index) => (
            <article key={text(upgrade.upgrade_id, String(index))}>
              <header>
                <div><span>#{index + 1} · SCORE {text(upgrade.priority_score, "—")}</span><h4>{text(upgrade.title)}</h4></div>
                <strong>{text(upgrade.production_shadow_research_recommendation, "RESEARCH")}</strong>
              </header>
              <p>{text(upgrade.why_it_should_improve_intelligence)}</p>
              <div className="cio-evidence">
                {(upgrade.supporting_evidence ?? []).map((evidence) => <span key={evidence}>{evidence}</span>)}
              </div>
              <div className="cio-fields">
                <div><span>Expected impact</span><strong>{text(upgrade.expected_impact)}</strong></div>
                <div><span>Engineering effort</span><strong>{text(upgrade.engineering_effort)}</strong></div>
                <div><span>Data/provider cost</span><strong>{text(upgrade.data_provider_cost)}</strong></div>
                <div><span>Safety/governance risk</span><strong>{text(upgrade.safety_governance_risk)}</strong></div>
                <div><span>Suggested batch</span><strong>{text(upgrade.suggested_implementation_batch)}</strong></div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className="cio-bottom-grid">
        <section className="cio-panel">
          <header><div><span>EXPERIMENT PIPELINE</span><h3>Underway / approved / measured</h3></div></header>
          <div className="cio-pipeline">
            <div><strong>{office.experiments_underway?.length ?? 0}</strong><span>Experiments underway</span></div>
            <div><strong>{office.approved_upgrades?.length ?? 0}</strong><span>Approved upgrades</span></div>
            <div><strong>{office.measured_improvement_after_implementation?.length ?? 0}</strong><span>Measured improvements</span></div>
          </div>
        </section>
        <section className="cio-panel">
          <header><div><span>REJECTED UPGRADES</span><h3>What 9P will not do</h3></div></header>
          <div className="cio-rejected">
            {(office.rejected_upgrades ?? []).map((row) => (
              <div key={text(row.upgrade)}><strong>{text(row.upgrade).replaceAll("_", " ")}</strong><p>{text(row.reason)}</p></div>
            ))}
          </div>
        </section>
      </div>
      {error ? <div className="cio-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
