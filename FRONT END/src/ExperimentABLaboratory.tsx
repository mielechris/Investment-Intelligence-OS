import { useEffect, useMemo, useState } from "react";
import "./ExperimentABLaboratory.css";

type JsonObject = Record<string, unknown>;
type Experiment = {
  experiment_id?: string;
  upgrade_id?: string;
  title?: string;
  status?: string;
  verdict?: string;
  keep_meaning?: string;
  sample?: JsonObject;
  baseline_arm?: JsonObject | null;
  variant_arm?: JsonObject | null;
  comparison?: JsonObject;
  decision_basis?: string[];
  next_action?: string;
};

type Lab = {
  status?: string;
  purpose?: string;
  generated_at?: string;
  experiments?: Experiment[];
  summary?: {
    experiment_count?: number;
    keep_count?: number;
    reject_count?: number;
    need_more_data_count?: number;
    production_changes_applied?: number;
  };
  decision_dictionary?: Record<string, string>;
  source_state?: JsonObject;
  safety?: Record<string, boolean>;
};

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function percent(value: unknown) {
  const numeric = numberValue(value);
  return numeric === null ? "—" : `${numeric >= 0 ? "+" : ""}${numeric.toFixed(1)}%`;
}

function verdictClass(value: unknown) {
  const verdict = text(value, "NEED_MORE_DATA").toUpperCase();
  if (verdict === "KEEP") return "keep";
  if (verdict === "REJECT") return "reject";
  return "wait";
}

function armLabel(arm: JsonObject | null | undefined) {
  if (!arm) return "NOT AVAILABLE";
  const scenario = text(arm.scenario_id, "");
  if (scenario) return scenario.replaceAll("_", " ");
  const score = numberValue(arm.min_promotion_score);
  const cap = numberValue(arm.max_cases_per_cycle);
  if (score !== null || cap !== null) return `Score ${score ?? "—"} · capacity ${cap ?? "—"}`;
  return text(arm.state, "PERSISTED ARM").replaceAll("_", " ");
}

async function loadLab(signal?: AbortSignal): Promise<Lab> {
  const response = await fetch(`/experiment_ab_laboratory.json?ts=${Date.now()}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`Experiment Lab returned HTTP ${response.status}`);
  return response.json() as Promise<Lab>;
}

export default function ExperimentABLaboratory() {
  const [lab, setLab] = useState<Lab | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try {
        const next = await loadLab(controller.signal);
        if (!disposed) {
          setLab(next);
          setError(null);
        }
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "Experiment lab unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const experiments = useMemo(() => lab?.experiments ?? [], [lab]);

  if (!lab) {
    return (
      <section className="abl-shell abl-waiting">
        <span>BATCH 9Q · EXPERIMENT & A/B LABORATORY</span>
        <h2>{error ? "LAB WARM-UP" : "ASSEMBLING SHADOW EXPERIMENTS"}</h2>
        <p>{error ?? "No experiment verdict is rendered until persisted comparison evidence exists."}</p>
      </section>
    );
  }

  return (
    <section className="abl-shell">
      <div className="abl-hero">
        <div>
          <span>BATCH 9Q · EXPERIMENT & A/B LABORATORY</span>
          <h2>Test the upgrade. Don&apos;t let the upgrade test the portfolio.</h2>
          <p>
            Governed baseline versus shadow variants using persisted IIOS evidence only. KEEP means a variant survives evidence review—not that it enters production.
          </p>
        </div>
        <div className="abl-guard">
          <strong>SHADOW ONLY</strong>
          <span>HUMAN APPROVAL REQUIRED</span>
          <em>LIVE EXECUTION FALSE</em>
        </div>
      </div>

      <div className="abl-safety">
        <span>AUTO APPLY VARIANTS · FALSE</span>
        <span>THRESHOLD AUTHORITY · FALSE</span>
        <span>COMMITTEE / RISK AUTHORITY · FALSE</span>
        <span>CAPITAL AUTHORITY · FALSE</span>
      </div>

      <div className="abl-scoreboard">
        <article><span>EXPERIMENTS</span><strong>{lab.summary?.experiment_count ?? experiments.length}</strong></article>
        <article><span>KEEP</span><strong>{lab.summary?.keep_count ?? 0}</strong></article>
        <article><span>REJECT</span><strong>{lab.summary?.reject_count ?? 0}</strong></article>
        <article><span>NEED MORE DATA</span><strong>{lab.summary?.need_more_data_count ?? 0}</strong></article>
        <article><span>PRODUCTION CHANGES</span><strong>{lab.summary?.production_changes_applied ?? 0}</strong></article>
      </div>

      <div className="abl-dictionary">
        {Object.entries(lab.decision_dictionary ?? {}).map(([key, value]) => (
          <div key={key} className={`is-${verdictClass(key)}`}>
            <strong>{key.replaceAll("_", " ")}</strong>
            <span>{value}</span>
          </div>
        ))}
      </div>

      <section className="abl-experiments">
        <div className="abl-section-title">
          <div><span>ACTIVE EXPERIMENT BOARD</span><h3>Baseline vs variant evidence</h3></div>
          <strong>{text(lab.status, "WARM-UP").replaceAll("_", " ")}</strong>
        </div>
        {experiments.map((experiment, index) => {
          const baseline = experiment.baseline_arm ?? null;
          const variant = experiment.variant_arm ?? null;
          const comparison = experiment.comparison ?? {};
          return (
            <article className="abl-card" key={text(experiment.experiment_id, String(index))}>
              <header>
                <div>
                  <span>{text(experiment.upgrade_id, "UNMAPPED UPGRADE").replaceAll("_", " ")}</span>
                  <h4>{text(experiment.title, "Experiment")}</h4>
                </div>
                <div className={`abl-verdict abl-verdict--${verdictClass(experiment.verdict)}`}>
                  {text(experiment.verdict, "NEED_MORE_DATA").replaceAll("_", " ")}
                </div>
              </header>

              <div className="abl-arms">
                <div>
                  <span>CONTROL · GOVERNED BASELINE</span>
                  <strong>{armLabel(baseline)}</strong>
                  {baseline ? (
                    <p>
                      Capture {text(baseline.captured_count, "—")} · extras {text(baseline.extra_nonbenchmark_ticker_count, "—")} · selections {text(baseline.selection_events, "—")}
                    </p>
                  ) : <p>No valid persisted baseline arm yet.</p>}
                </div>
                <div>
                  <span>VARIANT · SHADOW ONLY</span>
                  <strong>{armLabel(variant)}</strong>
                  {variant ? (
                    <p>
                      Capture {text(variant.captured_count, "—")} · extras {text(variant.extra_nonbenchmark_ticker_count, "—")} · selections {text(variant.selection_events, "—")}
                    </p>
                  ) : <p>No variant is allowed to advance on the current evidence.</p>}
                </div>
              </div>

              {Object.keys(comparison).length ? (
                <div className="abl-deltas">
                  <div><span>Δ captured</span><strong>{text(comparison.marginal_captured_count, "—")}</strong></div>
                  <div><span>Δ non-benchmark</span><strong>{text(comparison.marginal_extra_nonbenchmark_ticker_count, "—")}</strong></div>
                  <div><span>Δ load</span><strong>{percent(comparison.selection_load_delta_pct)}</strong></div>
                  <div><span>Noise acceptable</span><strong>{text(comparison.acceptable_noise, "—")}</strong></div>
                </div>
              ) : null}

              <div className="abl-basis">
                {(experiment.decision_basis ?? []).map((basis) => <p key={basis}>{basis}</p>)}
              </div>
              <footer>
                <span>STATUS · {text(experiment.status, "WARM-UP").replaceAll("_", " ")}</span>
                <strong>NEXT · {text(experiment.next_action, "HUMAN REVIEW").replaceAll("_", " ")}</strong>
              </footer>
            </article>
          );
        })}
      </section>

      <div className="abl-source-state">
        <strong>SOURCE STATE</strong>
        {Object.entries(lab.source_state ?? {}).map(([key, value]) => (
          <span key={key}>{key.replaceAll("_", " ")} · {text(value, "WARM-UP")}</span>
        ))}
      </div>
      {error ? <div className="abl-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}
