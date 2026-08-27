import { useEffect, useMemo, useState } from "react";
import "./JesseStrategyPanel.css";

const API =
  import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8002";

type BridgeResult = {
  candidate_id?: string | null;
  ticker?: string | null;
  status?: string | null;
  case_id?: string | null;
  already_dispatched?: boolean;
  committee_disposition?: string | null;
  committee_confidence?: number | null;
  error?: string | null;
};

type BridgeRun = {
  jesse_paper_fund_bridge_run_id?: string | null;
  top_three_count?: number | null;
  dispatched_count?: number | null;
  skipped_count?: number | null;
  error_count?: number | null;
  results?: BridgeResult[];
  next_owner?: string | null;
  authority_scope?: string | null;
  created_at?: string | null;
};

type JesseCandidate = {
  ticker?: string | null;
  company?: string | null;
  current_price?: number | null;
  intraday_change_pct?: number | null;
  financial_strength_score?: number | null;
  recommendation?: string | null;
  estimated_probability_next_day_plus_5?: number | null;
  financial_reason_codes?: string[];
  decline_analysis?: {
    classification?: string | null;
    structural_flags?: string[];
    temporary_flags?: string[];
  };
};

type DislocationScan = {
  dislocation_scan_id?: string | null;
  universe_scope?: string | null;
  strict_index_membership?: boolean;
  loser_count?: number | null;
  losers?: JesseCandidate[];
  top_three?: JesseCandidate[];
  opportunity_candidate_ids?: string[];
  bridge?: BridgeRun | null;
  created_at?: string | null;
};

type DislocationStatus = {
  latest_scan?: DislocationScan | null;
  paper_mode?: boolean;
  trade_execution_permission?: boolean;
  live_execution?: boolean;
};

type CaseResult = {
  case_id?: string | null;
  ticker?: string | null;
  stage?: string | null;
  failed_checks?: string[];
  unmet_requirements?: string[];
  execution_id?: string | null;
};

type Operations = {
  generated_at?: string | null;
  portfolio?: {
    nav?: number | null;
    cash?: number | null;
    position_count?: number | null;
  };
  paper_trading?: {
    case_results?: CaseResult[];
  };
  safety?: {
    paper_mode?: boolean;
    broker_connected?: boolean;
    live_capital_locked?: boolean;
    live_execution?: boolean;
  };
};

type Overview = {
  cases?: Array<{
    case_id?: string | null;
    ticker?: string | null;
    risk?: string | null;
    committee?: string | null;
    paper_execution?: string | null;
  }>;
};

type JesseSchedulerStatus = {
  state?: {
    enabled?: boolean;
    dislocation_hour_pt?: number | null;
    dislocation_minute_pt?: number | null;
    last_dislocation_date?: string | null;
  };
  scheduler_running?: boolean;
  calibration?: {
    observation_count?: number | null;
    target_hit_count?: number | null;
    target_hit_rate?: number | null;
    average_next_day_return_pct?: number | null;
    target_upside_pct?: number | null;
    calibrated?: boolean;
    minimum_calibration_observations?: number | null;
  };
};

type JesseRow = {
  key: string;
  candidateId: string | null;
  ticker: string;
  company: string;
  price: number | null;
  decline: number | null;
  strength: number | null;
  recommendation: string;
  probability: number | null;
  classification: string;
  bridge: string;
  caseId: string | null;
  committee: string;
  stage9b: string;
  risk: string;
  paper: string;
  reasons: string[];
  blockers: string[];
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

function text(value?: string | null): string {
  return String(value ?? "UNKNOWN").replaceAll("_", " ");
}

function known(value?: string | null): boolean {
  const normalized = String(value ?? "").trim().toUpperCase();
  return !["", "UNKNOWN", "NONE", "PENDING", "NOT STARTED"].includes(normalized);
}

export default function JesseStrategyPanel() {
  const [open, setOpen] = useState(true);
  const [dislocation, setDislocation] = useState<DislocationStatus | null>(null);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [scheduler, setScheduler] = useState<JesseSchedulerStatus | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      const jobs = await Promise.allSettled([
        getJson<DislocationStatus>("/intelligence/dislocation/status"),
        getJson<Operations>("/paper-fund/operations"),
        getJson<Overview>("/experience/factory-intelligence/overview"),
        getJson<JesseSchedulerStatus>("/intelligence/jesse-scheduler/status"),
      ]);
      if (disposed) return;

      const nextErrors: string[] = [];
      if (jobs[0].status === "fulfilled") setDislocation(jobs[0].value);
      else nextErrors.push(`DISLOCATION: ${String(jobs[0].reason)}`);
      if (jobs[1].status === "fulfilled") setOperations(jobs[1].value);
      else nextErrors.push(`OPERATIONS: ${String(jobs[1].reason)}`);
      if (jobs[2].status === "fulfilled") setOverview(jobs[2].value);
      else nextErrors.push(`OVERVIEW: ${String(jobs[2].reason)}`);
      if (jobs[3].status === "fulfilled") setScheduler(jobs[3].value);
      else nextErrors.push(`JESSE SCHEDULER: ${String(jobs[3].reason)}`);
      setErrors(nextErrors);
    };

    void load();
    const timer = window.setInterval(() => void load(), 10_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const scan = dislocation?.latest_scan ?? null;
  const bridge = scan?.bridge ?? null;
  const bridgeResults = bridge?.results ?? [];
  const caseResults = operations?.paper_trading?.case_results ?? [];
  const overviewCases = overview?.cases ?? [];

  const rows = useMemo<JesseRow[]>(() => {
    const top = scan?.top_three ?? [];
    const ids = scan?.opportunity_candidate_ids ?? [];

    return top.slice(0, 3).map((candidate, index) => {
      const candidateId = ids[index] ?? null;
      const ticker = String(candidate.ticker ?? "UNKNOWN").toUpperCase();
      const bridgeRow = bridgeResults.find(
        (row) =>
          (candidateId && row.candidate_id === candidateId) ||
          String(row.ticker ?? "").toUpperCase() === ticker,
      );
      const caseId = bridgeRow?.case_id ?? null;
      const case9b = caseResults.find(
        (row) =>
          (caseId && row.case_id === caseId) ||
          String(row.ticker ?? "").toUpperCase() === ticker,
      );
      const governed = overviewCases.find(
        (row) =>
          (caseId && row.case_id === caseId) ||
          String(row.ticker ?? "").toUpperCase() === ticker,
      );

      const reasons = [
        ...(candidate.financial_reason_codes ?? []).map(text),
        text(candidate.decline_analysis?.classification),
      ].filter((value) => value !== "UNKNOWN");
      const blockers = [
        ...(case9b?.failed_checks ?? []).map(text),
        ...(case9b?.unmet_requirements ?? []).map(text),
        bridgeRow?.error ? bridgeRow.error : null,
      ].filter((value): value is string => Boolean(value));

      return {
        key: candidateId ?? `${ticker}-${index}`,
        candidateId,
        ticker,
        company: String(candidate.company ?? ticker),
        price: candidate.current_price ?? null,
        decline: candidate.intraday_change_pct ?? null,
        strength: candidate.financial_strength_score ?? null,
        recommendation: text(candidate.recommendation),
        probability: candidate.estimated_probability_next_day_plus_5 ?? null,
        classification: text(candidate.decline_analysis?.classification),
        bridge: text(bridgeRow?.status),
        caseId,
        committee: text(
          bridgeRow?.committee_disposition ?? governed?.committee ?? "UNKNOWN",
        ),
        stage9b: text(case9b?.stage),
        risk: text(governed?.risk),
        paper: text(
          case9b?.execution_id
            ? "PAPER ORDER RECORDED"
            : governed?.paper_execution ?? "UNKNOWN",
        ),
        reasons,
        blockers,
      };
    });
  }, [scan, bridgeResults, caseResults, overviewCases]);

  const dispatched = bridge?.dispatched_count ?? null;
  const committeeCount = bridgeResults.filter((row) => known(row.committee_disposition)).length;
  const seenBy9B = bridgeResults.filter((row) =>
    row.case_id ? caseResults.some((item) => item.case_id === row.case_id) : false,
  ).length;
  const riskCount = bridgeResults.filter((row) =>
    row.case_id
      ? overviewCases.some(
          (item) => item.case_id === row.case_id && known(item.risk),
        )
      : false,
  ).length;
  const paperCount = bridgeResults.filter((row) => {
    if (!row.case_id) return false;
    const result = caseResults.find((item) => item.case_id === row.case_id);
    const view = overviewCases.find((item) => item.case_id === row.case_id);
    return Boolean(result?.execution_id) || known(view?.paper_execution);
  }).length;

  const funnel: Array<[string, number | string | null, string]> = [
    ["TOP LOSERS", scan?.loser_count ?? scan?.losers?.length ?? "—", "Jesse scan"],
    ["TOP 3", scan?.top_three?.length ?? "—", "ranked candidates"],
    ["DISPATCHED", dispatched ?? "—", "eight-agent floor"],
    ["COMMITTEE", committeeCount, "governed decisions"],
    ["9B", seenBy9B, "seen by paper controller"],
    ["RISK", riskCount, "real risk state"],
    ["PAPER", paperCount, "paper execution state"],
  ];

  const calibration = scheduler?.calibration;
  const hitRate = calibration?.target_hit_rate;
  const scheduledHour = scheduler?.state?.dislocation_hour_pt ?? 11;
  const scheduledMinute = scheduler?.state?.dislocation_minute_pt ?? 0;

  return (
    <section className={`jesse-strategy ${open ? "open" : "closed"}`}>
      <button
        type="button"
        className="jesse-strategy__toggle"
        onClick={() => setOpen((value) => !value)}
      >
        <span>BATCH 10C · JESSE STRATEGY</span>
        <strong>DISLOCATION → GOVERNED FACTORY → PAPER FUND</strong>
        <em>{open ? "COLLAPSE" : "EXPAND"}</em>
      </button>

      {open ? (
        <div className="jesse-strategy__body">
          <header className="jesse-strategy__head">
            <div>
              <span>GOVERNED RESEARCH DISPATCH ONLY</span>
              <h2>Jesse → Paper Fund Bridge</h2>
              <p>
                Jesse selects dislocation candidates. The existing eight-agent
                floor, Committee, 9B, Risk, Capital, sizing and authorization
                gates decide whether any candidate ever reaches the paper fund.
              </p>
            </div>
            <div className="jesse-strategy__safety">
              <strong>
                {operations?.safety?.live_capital_locked === true
                  ? "LIVE CAPITAL LOCKED"
                  : "LIVE STATE UNKNOWN"}
              </strong>
              <span>
                JESSE AUTO-TRADE FALSE · BROKER {operations?.safety?.broker_connected === false ? "FALSE" : "UNKNOWN"}
              </span>
            </div>
          </header>

          {errors.length ? (
            <div className="jesse-strategy__errors">
              {errors.map((error) => <span key={error}>{error}</span>)}
            </div>
          ) : null}

          <div className="jesse-strategy__funnel">
            {funnel.map(([label, value, detail], index) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value ?? "—"}</strong>
                <small>{detail}</small>
                {index < funnel.length - 1 ? <i>→</i> : null}
              </div>
            ))}
          </div>

          <div className="jesse-strategy__grid">
            <section className="jesse-strategy__panel">
              <header>
                <div>
                  <span>LATEST JESSE DISLOCATION SCAN</span>
                  <h3>Top 3 Governed Journey</h3>
                </div>
                <strong>{text(scan?.universe_scope)} · UNKNOWN ≠ ZERO</strong>
              </header>

              <div className="jesse-strategy__rows">
                {rows.length ? rows.map((row) => (
                  <article key={row.key}>
                    <button
                      type="button"
                      onClick={() => setExpanded(expanded === row.key ? null : row.key)}
                    >
                      <div>
                        <strong>{row.ticker}</strong>
                        <span>{row.company}</span>
                      </div>
                      <b>{row.strength ?? "—"}</b>
                      <em>
                        {row.recommendation} · {row.probability === null ? "P(+5) —" : `P(+5) ${(row.probability * 100).toFixed(1)}%`}
                      </em>
                      <i>{row.bridge} · 9B {row.stage9b}</i>
                      <u>{expanded === row.key ? "CLOSE" : "WHY / STATE"}</u>
                    </button>

                    {expanded === row.key ? (
                      <div className="jesse-strategy__explain">
                        <div>
                          <span>JESSE CASE</span>
                          <p>Price: {row.price === null ? "UNKNOWN" : `$${row.price.toFixed(2)}`}</p>
                          <p>Day move: {row.decline === null ? "UNKNOWN" : `${row.decline.toFixed(2)}%`}</p>
                          <p>Classification: {row.classification}</p>
                          {row.reasons.map((reason) => <small key={reason}>{reason}</small>)}
                        </div>
                        <div>
                          <span>GOVERNED FACTORY</span>
                          <p>Case: {row.caseId ?? "NOT DISPATCHED"}</p>
                          <p>Committee: {row.committee}</p>
                          <p>9B: {row.stage9b}</p>
                          <p>Risk: {row.risk}</p>
                          <p>Paper: {row.paper}</p>
                        </div>
                        <div>
                          <span>BLOCKERS</span>
                          {row.blockers.length
                            ? row.blockers.map((reason) => <p key={reason}>{reason}</p>)
                            : <p>No explicit blocker is exposed yet.</p>}
                          <small>No missing state is inferred.</small>
                        </div>
                      </div>
                    ) : null}
                  </article>
                )) : (
                  <div className="jesse-strategy__empty">
                    No persisted Jesse Top-3 scan is available yet.
                  </div>
                )}
              </div>
            </section>

            <section className="jesse-strategy__panel jesse-strategy__calibration">
              <header>
                <div>
                  <span>POST-DECISION LEARNING</span>
                  <h3>Jesse Calibration</h3>
                </div>
                <strong>{calibration?.calibrated ? "CALIBRATED" : "LEARNING"}</strong>
              </header>

              <div className="jesse-strategy__metrics">
                <div><span>OBSERVATIONS</span><strong>{calibration?.observation_count ?? "—"}</strong></div>
                <div><span>+5% HITS</span><strong>{calibration?.target_hit_count ?? "—"}</strong></div>
                <div><span>HIT RATE</span><strong>{hitRate === null || hitRate === undefined ? "—" : `${(hitRate * 100).toFixed(1)}%`}</strong></div>
                <div><span>AVG NEXT DAY</span><strong>{calibration?.average_next_day_return_pct === null || calibration?.average_next_day_return_pct === undefined ? "—" : `${calibration.average_next_day_return_pct.toFixed(2)}%`}</strong></div>
                <div><span>MIN SAMPLE</span><strong>{calibration?.minimum_calibration_observations ?? 30}</strong></div>
                <div><span>PAPER NAV</span><strong>{operations?.portfolio?.nav === null || operations?.portfolio?.nav === undefined ? "—" : `$${operations.portfolio.nav.toFixed(2)}`}</strong></div>
              </div>

              <div className="jesse-strategy__schedule">
                <span>DAILY SCAN</span>
                <strong>{String(scheduledHour).padStart(2, "0")}:{String(scheduledMinute).padStart(2, "0")} PT · WEEKDAYS</strong>
                <small>Last scheduled date: {scheduler?.state?.last_dislocation_date ?? "UNKNOWN"}</small>
              </div>
            </section>
          </div>

          <footer className="jesse-strategy__footer">
            <span>SCAN · {scan?.created_at ? new Date(scan.created_at).toLocaleString() : "UNKNOWN"}</span>
            <span>BRIDGE · {bridge?.created_at ? new Date(bridge.created_at).toLocaleString() : "UNKNOWN"}</span>
            <span>OPS · {operations?.generated_at ? new Date(operations.generated_at).toLocaleTimeString() : "UNKNOWN"}</span>
            <strong>JESSE SELECTS · GOVERNANCE DECIDES · PAPER ONLY</strong>
          </footer>
        </div>
      ) : null}
    </section>
  );
}
