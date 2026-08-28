import { useEffect, useMemo, useState } from "react";
import "./Batch10DOperationsBoard.css";

const API =
  import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8002";

type VisibilityCase = {
  case_id?: string;
  ticker?: string | null;
  company?: string | null;
  topic?: string | null;
  current_stage?: string | null;
  continuity_state?: string | null;
  valid_no_capital_outcome?: boolean;
  dead_end?: boolean;
  missing_continuation?: string[];
  committee_disposition?: string | null;
  risk_decision?: string | null;
  qualified_buy_candidate?: boolean;
  capital_stage?: string | null;
  paper_execution_complete?: boolean;
  monitoring_active?: boolean;
  attention?: string;
  deep_watch?: {
    active?: boolean;
    obligation_count?: number;
    material_change_count?: number;
    latest_reunderwrite_disposition?: string | null;
    latest_reunderwrite_confidence?: number | null;
  };
  options_shadow?: {
    mode?: string | null;
    observation_count?: number;
    option_order_permission?: boolean;
  };
  capital_reason?: {
    state?: string;
    reason?: string;
    unmet_requirements?: string[];
    required_evidence?: string[];
    risk_triggered_rules?: string[];
  };
};

type Visibility = {
  policy_version?: string;
  portfolio?: {
    nav?: number | null;
    cash?: number | null;
    position_count?: number | null;
    transaction_count?: number | null;
    capital_deployed?: number | null;
    cash_weight_pct?: number | null;
  };
  summary?: {
    case_count?: number;
    deep_watch_cases?: number;
    open_obligations?: number;
    material_change_cases?: number;
    options_shadow_cases?: number;
    options_observations?: number;
    dead_end_count?: number;
    valid_no_capital_paths?: number;
    paper_positions_opened?: number;
  };
  cases?: VisibilityCase[];
  paper_mode?: boolean;
  options_shadow_only?: boolean;
  option_order_permission?: boolean;
  live_execution?: boolean;
};

async function loadVisibility(): Promise<Visibility> {
  const response = await fetch(`${API}/operations-visibility/overview?limit=25`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`operations visibility returned ${response.status}`);
  }
  return response.json() as Promise<Visibility>;
}

function display(value?: string | null): string {
  return String(value ?? "UNKNOWN").replaceAll("_", " ");
}

function money(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function tone(row: VisibilityCase): string {
  const attention = String(row.attention ?? "NORMAL").toUpperCase();
  if (attention === "DEAD_END") return "bad";
  if (attention === "MATERIAL_CHANGE") return "hot";
  if (row.paper_execution_complete) return "capital";
  if ((row.deep_watch?.obligation_count ?? 0) > 0) return "watch";
  return "normal";
}

export default function Batch10DOperationsBoard() {
  const [data, setData] = useState<Visibility | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const next = await loadVisibility();
        if (!disposed) {
          setData(next);
          setError(null);
        }
      } catch (err) {
        if (!disposed) {
          setError(err instanceof Error ? err.message : "operations visibility unavailable");
        }
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 10_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const cases = useMemo(() => {
    const rank: Record<string, number> = {
      DEAD_END: 0,
      MATERIAL_CHANGE: 1,
      WATCHING: 2,
      NORMAL: 3,
    };
    return [...(data?.cases ?? [])].sort((a, b) => {
      const aRank = rank[String(a.attention ?? "NORMAL").toUpperCase()] ?? 9;
      const bRank = rank[String(b.attention ?? "NORMAL").toUpperCase()] ?? 9;
      if (aRank !== bRank) return aRank - bRank;
      return String(a.ticker ?? a.topic ?? "").localeCompare(String(b.ticker ?? b.topic ?? ""));
    });
  }, [data]);

  const p = data?.portfolio;
  const s = data?.summary;

  return (
    <section className="b10d-ops">
      <header className="b10d-ops__head">
        <div>
          <span>BATCH 10D · CLOSED-LOOP OPERATIONS</span>
          <h3>Paper Fund + Deep Watch Control Board</h3>
          <p>
            Real governed state only. Cash is a valid allocation. Options remain shadow observation only.
          </p>
        </div>
        <div className="b10d-ops__lock">
          <strong>{data?.live_execution === false ? "LIVE EXECUTION LOCKED" : "LIVE STATE UNKNOWN"}</strong>
          <span>
            OPTIONS {data?.options_shadow_only === true ? "SHADOW" : "UNKNOWN"}
            {" · "}OPTION ORDERS {data?.option_order_permission === false ? "FALSE" : "UNKNOWN"}
          </span>
        </div>
      </header>

      {error ? <div className="b10d-ops__error">{error}</div> : null}

      <div className="b10d-ops__summary">
        <div><span>PAPER NAV</span><strong>{money(p?.nav)}</strong><small>{p?.position_count ?? "—"} positions</small></div>
        <div><span>CASH</span><strong>{money(p?.cash)}</strong><small>{p?.cash_weight_pct ?? "—"}% of NAV</small></div>
        <div><span>CAPITAL DEPLOYED</span><strong>{money(p?.capital_deployed)}</strong><small>{s?.paper_positions_opened ?? 0} paper paths</small></div>
        <div><span>DEEP WATCH</span><strong>{s?.deep_watch_cases ?? "—"}</strong><small>{s?.open_obligations ?? "—"} open obligations</small></div>
        <div className={(s?.material_change_cases ?? 0) > 0 ? "alert" : ""}><span>MATERIAL CHANGES</span><strong>{s?.material_change_cases ?? "—"}</strong><small>cases requiring attention</small></div>
        <div><span>OPTIONS SHADOW</span><strong>{s?.options_observations ?? "—"}</strong><small>{s?.options_shadow_cases ?? "—"} observed cases</small></div>
        <div className={(s?.dead_end_count ?? 0) > 0 ? "danger" : ""}><span>DEAD ENDS</span><strong>{s?.dead_end_count ?? "—"}</strong><small>{s?.valid_no_capital_paths ?? "—"} valid no-capital paths</small></div>
      </div>

      <div className="b10d-ops__cases">
        <div className="b10d-ops__columns">
          <span>CASE</span><span>FACTORY STATE</span><span>DEEP WATCH</span><span>OPTIONS</span><span>CAPITAL</span><span>WHY / WHY NOT</span>
        </div>

        {cases.length ? cases.map((row) => {
          const key = row.case_id ?? row.ticker ?? row.topic ?? "case";
          const open = expanded === key;
          return (
            <article className={`b10d-ops__case ${tone(row)}`} key={key}>
              <button type="button" onClick={() => setExpanded(open ? null : key)}>
                <div className="identity">
                  <strong>{row.ticker ?? "NO TICKER"}</strong>
                  <small>{row.company ?? row.topic ?? row.case_id ?? "UNKNOWN CASE"}</small>
                </div>
                <div>
                  <strong>{display(row.current_stage)}</strong>
                  <small>{display(row.committee_disposition)} · RISK {display(row.risk_decision)}</small>
                </div>
                <div>
                  <strong>{row.deep_watch?.obligation_count ?? 0} obligations</strong>
                  <small>{row.deep_watch?.material_change_count ?? 0} material changes</small>
                </div>
                <div>
                  <strong>{display(row.options_shadow?.mode)}</strong>
                  <small>{row.options_shadow?.observation_count ?? 0} observations · orders false</small>
                </div>
                <div>
                  <strong>{display(row.capital_reason?.state)}</strong>
                  <small>{row.paper_execution_complete ? "paper capital deployed" : "no paper execution"}</small>
                </div>
                <div className="reason">
                  <strong>{row.capital_reason?.reason ?? "No governed reason exposed."}</strong>
                  <small>{open ? "CLOSE DETAIL" : "OPEN DETAIL"}</small>
                </div>
              </button>

              {open ? (
                <div className="b10d-ops__detail">
                  <div>
                    <span>CONTINUITY</span>
                    <strong>{display(row.continuity_state)}</strong>
                    <p>Valid no-capital path: {row.valid_no_capital_outcome ? "TRUE" : "FALSE"}</p>
                    <p>Dead end: {row.dead_end ? "TRUE" : "FALSE"}</p>
                  </div>
                  <div>
                    <span>UNMET / REQUIRED</span>
                    {(row.capital_reason?.unmet_requirements ?? []).slice(0, 6).map((item) => <p key={item}>{display(item)}</p>)}
                    {!(row.capital_reason?.unmet_requirements ?? []).length ? <p>No unmet list exposed.</p> : null}
                  </div>
                  <div>
                    <span>RISK / REUNDERWRITE</span>
                    {(row.capital_reason?.risk_triggered_rules ?? []).slice(0, 5).map((item) => <p key={item}>{display(item)}</p>)}
                    <p>Latest deep re-underwrite: {display(row.deep_watch?.latest_reunderwrite_disposition)}</p>
                  </div>
                  <div>
                    <span>NEXT CONTINUATION</span>
                    {(row.missing_continuation ?? []).map((item) => <p key={item}>{display(item)}</p>)}
                    {!(row.missing_continuation ?? []).length ? <p>Governed continuation is intact.</p> : null}
                  </div>
                </div>
              ) : null}
            </article>
          );
        }) : (
          <div className="b10d-ops__empty">No governed cases are available on the operations visibility feed.</div>
        )}
      </div>

      <footer className="b10d-ops__foot">
        <span>{data?.policy_version ?? "operations visibility unavailable"}</span>
        <strong>READ ONLY · PAPER ONLY · OPTIONS SHADOW ONLY</strong>
      </footer>
    </section>
  );
}
