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

  const paper = asJson(benchmark.paper);
  const controls = asJson(benchmark.controls);
  const spy = asJson(controls.SPY);
  const qqq = asJson(controls.QQQ);
  const cash = asJson(controls.CASH_ZERO);
  const mechanical = asJson(controls.MECHANICAL_50_50_SPY_QQQ);
  const chain = asJson(health.health_chain);
  const modules: Json[] = Array.isArray(health.modules)
    ? health.modules.filter((row): row is Json => typeof row === "object" && row !== null && !Array.isArray(row))
    : [];

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
            <small>AGE {typeof row.age_seconds === "number" ? `${Math.round(row.age_seconds)}s` : "—"}</small>
            <p>{text(row.source_status, "NO STATUS")}</p>
          </div>)}
        </div>
      </div>

      <div className="mh-footer"><span>10L · MEASUREMENT ONLY</span><span>10M · OBSERVABILITY ONLY</span><span>10N · WAIT FOR MATURE OUTCOMES</span><span>LIVE CAPITAL · FALSE</span></div>
    </section>
  );
}
