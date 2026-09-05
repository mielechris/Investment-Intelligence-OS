import { useEffect, useMemo, useState } from "react";
import "./ChiefIntelligenceOfficeV2.css";

type Upgrade = {
  upgrade_id?: string;
  title?: string;
  why_it_should_improve_intelligence?: string;
  supporting_evidence?: string[];
  priority_score?: number;
  action_class?: string;
  suggested_implementation_batch?: string;
  engineering_effort?: string;
  safety_governance_risk?: string;
  measurement_goal?: string;
};

type Layer = { layer?: string; name?: string; status?: string };
type OfficeV2 = {
  status?: string;
  question?: string;
  whole_stack_inputs?: Layer[];
  whole_stack_inputs_observed?: number;
  whole_stack_input_count?: number;
  ranked_upgrades?: Upgrade[];
  top_recommendation?: Upgrade | null;
  historical_diagnostics?: {
    studies_ready?: number;
    targets_known?: number;
    event_reconstruction_state?: string;
    regime_normalization_state?: string;
    historical_error_count?: number;
  };
  decision_policy?: Record<string, string>;
  rejected_shortcuts?: string[];
};

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

async function load(signal?: AbortSignal): Promise<OfficeV2> {
  const response = await fetch(`/chief_intelligence_office_v2.json?ts=${Date.now()}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`Chief Intelligence Office V2 HTTP ${response.status}`);
  return response.json() as Promise<OfficeV2>;
}

export default function ChiefIntelligenceOfficeV2() {
  const [office, setOffice] = useState<OfficeV2 | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try { const next = await load(controller.signal); if (!disposed) { setOffice(next); setError(null); } }
      catch (reason) { if (!disposed) setError(reason instanceof Error ? reason.message : "10I unavailable"); }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);

  const upgrades = useMemo(() => office?.ranked_upgrades ?? [], [office]);
  if (!office) return <section className="ciov2-shell"><span>BATCH 10I · CHIEF INTELLIGENCE OFFICE V2</span><h2>WHOLE-STACK REVIEW WARM-UP</h2><p>{error ?? "Waiting for the first whole-stack improvement memo."}</p></section>;

  const hd = office.historical_diagnostics ?? {};
  return (
    <section className="ciov2-shell">
      <div className="ciov2-hero">
        <div>
          <span>BATCH 10I · CHIEF INTELLIGENCE OFFICE V2</span>
          <h2>The factory audits the factory.</h2>
          <p>10I compares measured weaknesses across the modern IIOS stack, separates missing engineering from missing evidence, and ranks the next improvements. Recommendations remain non-binding.</p>
        </div>
        <div className="ciov2-guard"><strong>WHOLE-STACK ADVISORY</strong><span>HUMAN APPROVAL REQUIRED</span><em>LIVE EXECUTION FALSE</em></div>
      </div>

      <div className="ciov2-safety"><span>AUTO APPLY · FALSE</span><span>AUTO WEIGHTS · FALSE</span><span>AUTO ROUTING · FALSE</span><span>CAPITAL AUTHORITY · FALSE</span></div>

      <div className="ciov2-score">
        <article><span>STACK INPUTS OBSERVED</span><strong>{text(office.whole_stack_inputs_observed, "0")} / {text(office.whole_stack_input_count, "0")}</strong></article>
        <article><span>RANKED UPGRADES</span><strong>{upgrades.length}</strong></article>
        <article><span>10H STUDIES READY</span><strong>{text(hd.studies_ready, "0")} / {text(hd.targets_known, "0")}</strong></article>
        <article><span>TOP NEXT ACTION</span><strong>{text(office.top_recommendation?.action_class, "WAIT") .replaceAll("_", " ")}</strong></article>
      </div>

      <section className="ciov2-panel">
        <header><div><span>WHOLE-STACK INPUT MAP</span><h3>What 10I is listening to</h3></div><strong>{text(office.status).replaceAll("_", " ")}</strong></header>
        <div className="ciov2-layers">{(office.whole_stack_inputs ?? []).map((row) => <article key={text(row.layer)}><span>{text(row.layer)}</span><strong>{text(row.name)}</strong><em>{text(row.status, "WAITING").replaceAll("_", " ")}</em></article>)}</div>
      </section>

      <section className="ciov2-panel">
        <header><div><span>10H FEEDBACK</span><h3>Historical intelligence gaps now influence the roadmap</h3></div></header>
        <div className="ciov2-history">
          <article><span>EVENT RECONSTRUCTION</span><strong>{text(hd.event_reconstruction_state).replaceAll("_", " ")}</strong></article>
          <article><span>REGIME NORMALIZATION</span><strong>{text(hd.regime_normalization_state).replaceAll("_", " ")}</strong></article>
          <article><span>HISTORICAL ERRORS</span><strong>{text(hd.historical_error_count, "0")}</strong></article>
        </div>
      </section>

      <section className="ciov2-panel">
        <header><div><span>SELF-IMPROVEMENT MEMO</span><h3>Ranked next upgrades</h3></div><strong>MEASURED · TESTABLE · NON-BINDING</strong></header>
        <div className="ciov2-upgrades">{upgrades.map((upgrade, index) => <article key={text(upgrade.upgrade_id, String(index))}>
          <header><div><span>#{index + 1} · SCORE {text(upgrade.priority_score)}</span><h4>{text(upgrade.title)}</h4></div><strong>{text(upgrade.action_class).replaceAll("_", " ")}</strong></header>
          <p>{text(upgrade.why_it_should_improve_intelligence)}</p>
          <div className="ciov2-evidence">{(upgrade.supporting_evidence ?? []).map((evidence) => <span key={evidence}>{evidence}</span>)}</div>
          <div className="ciov2-fields"><div><span>Measure</span><strong>{text(upgrade.measurement_goal)}</strong></div><div><span>Effort</span><strong>{text(upgrade.engineering_effort)}</strong></div><div><span>Risk</span><strong>{text(upgrade.safety_governance_risk)}</strong></div><div><span>Suggested batch</span><strong>{text(upgrade.suggested_implementation_batch)}</strong></div></div>
        </article>)}</div>
      </section>

      <section className="ciov2-panel">
        <header><div><span>DECISION POLICY</span><h3>Build, wait, shadow or ask a human?</h3></div></header>
        <div className="ciov2-policy">{Object.entries(office.decision_policy ?? {}).map(([key, value]) => <article key={key}><span>{key.replaceAll("_", " ")}</span><p>{value}</p></article>)}</div>
      </section>

      <div className="ciov2-footer"><span>FACTORY SELF-AUDIT · ACTIVE</span><span>RECOMMENDATIONS · NON-BINDING</span><span>10G QUALIFICATION · UNCHANGED</span><span>LIVE EXECUTION · FALSE</span></div>
      {error ? <div className="ciov2-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
