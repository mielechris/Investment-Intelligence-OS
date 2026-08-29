import { useEffect, useState } from "react";
import "./MeasurementHealthSuperbatch.css";

type Json = Record<string, unknown>;

function asJson(value: unknown): Json {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Json) : {};
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

async function loadJson(path: string): Promise<Json> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return asJson(await response.json());
}

function pct(value: unknown) {
  return typeof value === "number" ? `${value.toFixed(2)}%` : "—";
}

function money(value: unknown) {
  return typeof value === "number" ? `$${value.toFixed(2)}` : "—";
}

function integer(value: unknown) {
  return typeof value === "number" ? Math.round(value).toLocaleString() : "—";
}

export default function MeasurementHealthSuperbatch() {
  const [benchmark, setBenchmark] = useState<Json>({});
  const [health, setHealth] = useState<Json>({});
  const [cost, setCost] = useState<Json>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const refresh = async () => {
      try {
        const [b, h, c] = await Promise.all([
          loadJson("/benchmark_alpha_attribution.json"),
          loadJson("/data_health_watchdog.json"),
          loadJson("/model_cost_governor.json"),
        ]);
        setBenchmark(b);
        setHealth(h);
        setCost(c);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    };
    refresh();
    const id = window.setInterval(refresh, 30000);
    return () => window.clearInterval(id);
  }, []);

  const paper = asJson(benchmark.paper);
  const controls = asJson(benchmark.controls);
  const spy = asJson(controls.SPY);
  const qqq = asJson(controls.QQQ);
  const cash = asJson(controls.CASH_ZERO);
  const mechanical = asJson(controls.MECHANICAL_50_50_SPY_QQQ);
  const chain = asJson(health.health_chain);
  const today = asJson(cost.today);
  const rolling = asJson(cost.rolling_7d);
  const policy = asJson(cost.policy);
  const modules: Json[] = Array.isArray(health.modules)
    ? health.modules.filter((row): row is Json => typeof row === "object" && row !== null && !Array.isArray(row))
    : [];

  return (
    <section className="mh-shell">
      <header className="mh-hero">
        <div>
          <div className="mh-kicker">BATCH 10L–10M · MEASUREMENT + OPERATING CONTROL + COST GOVERNOR</div>
          <h2>Beat the dumb benchmark. Trust the damn data. Stop lighting money on fire.</h2>
          <p>10L measures IIOS against simple controls. 10M proves the inputs are healthy and exposes model/tool cost before expensive research becomes an invisible tax.</p>
        </div>
        <div className="mh-badge">MEASUREMENT ONLY<br /><span>NO ALLOCATION AUTHORITY</span></div>
      </header>

      <div className="mh-rail">
        <span>AUTO ALLOCATE · FALSE</span><span>AUTO RESTART · FALSE</span><span>AUTO ROUTE · FALSE</span><span>LIVE EXECUTION · FALSE</span>
      </div>

      {error && <div className="mh-error">Browser artifact error: {error}</div>}

      <div className="mh-section">
        <div className="mh-label">10L · BENCHMARK / ALPHA ATTRIBUTION</div>
        <div className="mh-title-row"><h3>{text(benchmark.status, "WAITING")}</h3><span>{benchmark.measurement_contract_ready === true ? "CONTRACT READY" : "WARM UP"}</span></div>
        <div className="mh-metrics">
          <div><small>IIOS PAPER RETURN</small><strong>{pct(paper.return_pct)}</strong></div>
          <div><small>SPY</small><strong>{pct(spy.return_pct)}</strong></div>
          <div><small>QQQ</small><strong>{pct(qqq.return_pct)}</strong></div>
          <div><small>CASH CONTROL</small><strong>{pct(cash.return_pct)}</strong></div>
          <div><small>50/50 SPY·QQQ</small><strong>{pct(mechanical.return_pct)}</strong></div>
        </div>
        <div className="mh-note">No edge claim is allowed until the governed paper sample matures. This layer measures; it does not trade or reallocate.</div>
      </div>

      <div className="mh-section">
        <div className="mh-label">10M · END-TO-END DATA HEALTH</div>
        <div className="mh-title-row"><h3>{text(health.status, "WAITING")}</h3><span>{text(health.healthy_critical_modules, "0")} / {text(health.critical_module_count, "0")} CRITICAL HEALTHY</span></div>
        <div className="mh-chain">
          {Object.entries(chain).map(([key, value]) => <div key={key} className={value === true ? "ok" : "bad"}><small>{key.replaceAll("_", " ")}</small><strong>{value === true ? "YES" : "NO"}</strong></div>)}
        </div>
        <div className="mh-module-grid">
          {modules.map((row) => <div className={`mh-module ${row.state === "HEALTHY" ? "ok" : "bad"}`} key={text(row.module, "UNKNOWN")}>
            <div><strong>{text(row.module, "UNKNOWN")}</strong><span>{text(row.state, "UNKNOWN")}</span></div>
            <small>{row.critical === true ? "CRITICAL" : "NONCRITICAL"} · AGE {typeof row.age_seconds === "number" ? `${Math.round(row.age_seconds)}s` : "—"}</small>
            <p>{text(row.source_status, "NO STATUS")}</p>
          </div>)}
        </div>
      </div>

      <div className="mh-section">
        <div className="mh-label">10M · MODEL / TOOL COST CONTROL</div>
        <div className="mh-title-row"><h3>{text(cost.status, "WAITING")}</h3><span>{text(cost.budget_state, "INSTRUMENTATION GAP")}</span></div>
        {cost.status === "MODEL_COST_GOVERNOR_INSTRUMENTATION_REQUIRED" && (
          <div className="mh-note">NO LOCAL EXACT COST TELEMETRY YET — NO SPEND ESTIMATE INVENTED. The governor is installed first; model call sites must record provider-reported usage before exact local cost accounting becomes complete.</div>
        )}
        <div className="mh-metrics">
          <div><small>TODAY EXACT SPEND</small><strong>{money(today.exact_spend_usd)}</strong></div>
          <div><small>7D EXACT SPEND</small><strong>{money(rolling.exact_spend_usd)}</strong></div>
          <div><small>EXACT COST COVERAGE</small><strong>{pct(rolling.exact_cost_coverage_pct)}</strong></div>
          <div><small>7D REQUESTS</small><strong>{integer(rolling.requests)}</strong></div>
          <div><small>WEB SEARCH CALLS</small><strong>{integer(rolling.web_search_calls)}</strong></div>
        </div>
        <div className="mh-metrics">
          <div><small>DAILY SOFT</small><strong>{money(policy.daily_soft_limit_usd)}</strong></div>
          <div><small>DAILY HARD</small><strong>{money(policy.daily_hard_limit_usd)}</strong></div>
          <div><small>WEEKLY SOFT</small><strong>{money(policy.rolling_7d_soft_limit_usd)}</strong></div>
          <div><small>WEEKLY HARD</small><strong>{money(policy.rolling_7d_hard_limit_usd)}</strong></div>
          <div><small>HOOKS CONNECTED</small><strong>{cost.enforcement_hooks_connected === true ? "YES" : "NO"}</strong></div>
        </div>
        <div className="mh-note">Policy is advisory until explicit model-call hooks are connected. Unknown provider cost remains unpriced. The system does not silently reroute, disable a model, change a provider, or estimate a bill.</div>
      </div>

      <div className="mh-footer"><span>10L · MEASUREMENT ONLY</span><span>10M · HEALTH + COST OBSERVABILITY</span><span>10N · WAIT FOR MATURE OUTCOMES</span><span>LIVE CAPITAL · FALSE</span></div>
    </section>
  );
}
