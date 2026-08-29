import { useEffect, useState } from "react";
import "./MeasurementHealthSuperbatch.css";

type Json = Record<string, any>;

async function loadJson(path: string): Promise<Json> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.json();
}

function pct(value: unknown) {
  return typeof value === "number" ? `${value.toFixed(2)}%` : "—";
}

export default function MeasurementHealthSuperbatch() {
  const [benchmark, setBenchmark] = useState<Json>({});
  const [health, setHealth] = useState<Json>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const refresh = async () => {
      try {
        const [b, h] = await Promise.all([
          loadJson("/benchmark_alpha_attribution.json"),
          loadJson("/data_health_watchdog.json"),
        ]);
        setBenchmark(b);
        setHealth(h);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    };
    refresh();
    const id = window.setInterval(refresh, 30000);
    return () => window.clearInterval(id);
  }, []);

  const paper = benchmark.paper || {};
  const controls = benchmark.controls || {};
  const chain = health.health_chain || {};
  const modules = Array.isArray(health.modules) ? health.modules : [];

  return (
    <section className="mh-shell">
      <header className="mh-hero">
        <div>
          <div className="mh-kicker">BATCH 10L–10M · MEASUREMENT + OPERATING CONTROL</div>
          <h2>Beat the dumb benchmark. Trust the damn data.</h2>
          <p>10L measures IIOS against simple controls. 10M proves the inputs are alive, flowing, fresh, analyzed and consumed before anyone trusts the scoreboard.</p>
        </div>
        <div className="mh-badge">MEASUREMENT ONLY<br /><span>NO ALLOCATION AUTHORITY</span></div>
      </header>

      <div className="mh-rail">
        <span>AUTO ALLOCATE · FALSE</span><span>AUTO RESTART · FALSE</span><span>PROVIDER AUTHORITY · FALSE</span><span>LIVE EXECUTION · FALSE</span>
      </div>

      {error && <div className="mh-error">Browser artifact error: {error}</div>}

      <div className="mh-section">
        <div className="mh-label">10L · BENCHMARK / ALPHA ATTRIBUTION</div>
        <div className="mh-title-row"><h3>{benchmark.status || "WAITING"}</h3><span>{benchmark.measurement_contract_ready ? "CONTRACT READY" : "WARM UP"}</span></div>
        <div className="mh-metrics">
          <div><small>IIOS PAPER RETURN</small><strong>{pct(paper.return_pct)}</strong></div>
          <div><small>SPY</small><strong>{pct(controls.SPY?.return_pct)}</strong></div>
          <div><small>QQQ</small><strong>{pct(controls.QQQ?.return_pct)}</strong></div>
          <div><small>CASH CONTROL</small><strong>{pct(controls.CASH_ZERO?.return_pct)}</strong></div>
          <div><small>50/50 SPY·QQQ</small><strong>{pct(controls.MECHANICAL_50_50_SPY_QQQ?.return_pct)}</strong></div>
        </div>
        <div className="mh-note">No edge claim is allowed until the governed paper sample matures. This layer measures; it does not trade or reallocate.</div>
      </div>

      <div className="mh-section">
        <div className="mh-label">10M · END-TO-END DATA HEALTH</div>
        <div className="mh-title-row"><h3>{health.status || "WAITING"}</h3><span>{health.healthy_critical_modules ?? 0} / {health.critical_module_count ?? 0} CRITICAL HEALTHY</span></div>
        <div className="mh-chain">
          {Object.entries(chain).map(([key, value]) => <div key={key} className={value ? "ok" : "bad"}><small>{key.replaceAll("_", " ")}</small><strong>{value ? "YES" : "NO"}</strong></div>)}
        </div>
        <div className="mh-module-grid">
          {modules.map((row: Json) => <div className={`mh-module ${row.state === "HEALTHY" ? "ok" : "bad"}`} key={row.module}>
            <div><strong>{row.module}</strong><span>{row.state}</span></div>
            <small>AGE {typeof row.age_seconds === "number" ? `${Math.round(row.age_seconds)}s` : "—"}</small>
            <p>{row.source_status || "NO STATUS"}</p>
          </div>)}
        </div>
      </div>

      <div className="mh-footer"><span>10L · MEASUREMENT ONLY</span><span>10M · OBSERVABILITY ONLY</span><span>10N · WAIT FOR MATURE OUTCOMES</span><span>LIVE CAPITAL · FALSE</span></div>
    </section>
  );
}
