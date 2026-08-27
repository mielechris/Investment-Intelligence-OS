import { useEffect, useMemo, useState } from "react";
import "./Batch10BCommandLayer.css";

const API =
  import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8002";

type Worker = {
  availability?: string;
  cadence_minutes?: number;
  last_completed_at?: string | null;
  cadence_state?: string;
  market_phase?: string | null;
};

type CaseResult = {
  case_id?: string | null;
  ticker?: string | null;
  stage?: string | null;
  committee_disposition?: string | null;
  committee_confidence?: number | null;
  capital_stage?: string | null;
  capital_decision?: string | null;
  sizing_decision?: string | null;
  failed_checks?: string[];
  unmet_requirements?: string[];
  execution_id?: string | null;
};

type Operations = {
  generated_at?: string;
  portfolio?: {
    nav?: number | null;
    cash?: number | null;
    position_count?: number | null;
    transaction_count?: number | null;
  };
  observation?: Worker & {
    last_scan_status?: string | null;
    last_scan_count?: number | null;
    last_queue_count?: number | null;
    promoted_case_count?: number | null;
    latest_promoted_case?: {
      case_id?: string | null;
      ticker?: string | null;
      score?: number | null;
    } | null;
  };
  paper_trading?: Worker & {
    case_count_inspected?: number | null;
    gap_hunts_run?: number | null;
    paper_executions_created?: number | null;
    case_results?: CaseResult[];
    funnel?: {
      inspected?: number;
      research_blocked_or_waiting?: number;
      capital_or_authorization_path?: number;
      waiting_for_regular_session?: number;
      paper_positions_opened?: number;
      errors_or_fail_closed?: number;
    };
  };
  safety?: {
    paper_mode?: boolean;
    broker_connected?: boolean;
    live_capital_locked?: boolean;
    live_execution?: boolean;
  };
};

type ModelState = {
  id?: string;
  label?: string;
  provider?: string;
  availability?: string;
  configured?: boolean | null;
  observation_status?: string;
  latency_ms?: number | null;
};

type OverviewCase = {
  case_id?: string | null;
  ticker?: string | null;
  stage?: string | null;
  latest_event_at?: string | null;
  committee?: string | null;
  risk?: string | null;
  paper_execution?: string | null;
};

type Overview = {
  generated_at?: string;
  data_state?: string;
  source_availability?: Record<
    string,
    { availability?: string; error_type?: string | null }
  >;
  council?: { models?: ModelState[] };
  cases?: OverviewCase[];
  safety?: { paper_mode?: boolean; live_capital_locked?: boolean };
};

type OpportunityCandidate = {
  opportunity_candidate_id?: string | null;
  opportunity_scan_id?: string | null;
  ticker?: string | null;
  label?: string | null;
  score?: number | null;
  priority?: string | null;
  eligible_for_promotion?: boolean;
  reason_codes?: string[];
  catalyst_categories?: string[];
  news_count?: number | null;
  source_count?: number | null;
  recent_24h_count?: number | null;
  quote_ok?: boolean;
  current_price?: number | null;
  promoted_case_id?: string | null;
  created_at?: string | null;
};

type OpportunityScan = {
  opportunity_scan_id?: string | null;
  universe_count?: number | null;
  scanned_count?: number | null;
  queued_count?: number | null;
  candidates?: OpportunityCandidate[];
  queue?: OpportunityCandidate[];
  created_at?: string | null;
};

type OpportunityStatus = {
  latest_scan?: OpportunityScan | null;
  queue?: OpportunityCandidate[];
  paper_mode?: boolean;
  auto_trade_authority?: boolean;
  trade_execution_permission?: boolean;
  live_execution?: boolean;
};

type SystemStatus = Record<string, unknown>;

type HealthTone = "good" | "warn" | "bad" | "unknown";
type HealthItem = {
  key: string;
  label: string;
  tone: HealthTone;
  state: string;
  detail: string;
};

type RadarRow = {
  key: string;
  ticker: string;
  score: number | null;
  price: number | null;
  priority: string;
  stage: string;
  committee: string;
  risk: string;
  why: string[];
  waiting: string[];
  caseId: string | null;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function ageSeconds(value?: string | null): number | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return null;
  return Math.max(0, (Date.now() - time) / 1000);
}

function display(value?: string | null): string {
  return String(value ?? "UNKNOWN").replaceAll("_", " ");
}

function isKnownState(value?: string | null): boolean {
  const normalized = String(value ?? "").trim().toUpperCase();
  return ![
    "",
    "UNKNOWN",
    "NONE",
    "NOT_STARTED",
    "NO_STATE",
    "PENDING",
  ].includes(normalized);
}

function workerHealth(
  label: string,
  worker: Worker | undefined,
  endpointOk: boolean,
): HealthItem {
  if (!endpointOk) {
    return {
      key: label,
      label,
      tone: "bad",
      state: "OFFLINE",
      detail: "Operations endpoint unavailable",
    };
  }
  if (!worker) {
    return {
      key: label,
      label,
      tone: "unknown",
      state: "UNKNOWN",
      detail: "No worker state exposed",
    };
  }

  const cadence = Math.max(1, Number(worker.cadence_minutes ?? 15));
  const age = ageSeconds(worker.last_completed_at);
  const cadenceState = String(worker.cadence_state ?? "UNKNOWN").toUpperCase();
  const availability = String(worker.availability ?? "UNKNOWN").toUpperCase();

  if (
    availability.includes("OFFLINE") ||
    availability.includes("ERROR") ||
    cadenceState.includes("ERROR")
  ) {
    return {
      key: label,
      label,
      tone: "bad",
      state: "OFFLINE",
      detail: `${availability} · ${cadenceState}`,
    };
  }

  if (age !== null && age > cadence * 60 * 2) {
    return {
      key: label,
      label,
      tone: "warn",
      state: "STALE",
      detail: `Last complete ${Math.round(age / 60)}m ago`,
    };
  }

  if (
    cadenceState.includes("ON_CADENCE") ||
    cadenceState.includes("READY") ||
    cadenceState.includes("ACTIVE")
  ) {
    return {
      key: label,
      label,
      tone: "good",
      state: "HEALTHY",
      detail:
        age === null
          ? cadenceState
          : `Last complete ${Math.max(0, Math.round(age / 60))}m ago`,
    };
  }

  return {
    key: label,
    label,
    tone: "warn",
    state: cadenceState || "UNKNOWN",
    detail: availability,
  };
}

function modelHealth(
  label: string,
  model: ModelState | undefined,
  overviewOk: boolean,
): HealthItem {
  if (!overviewOk) {
    return {
      key: label,
      label,
      tone: "bad",
      state: "OFFLINE",
      detail: "Factory overview unavailable",
    };
  }
  if (!model) {
    return {
      key: label,
      label,
      tone: "unknown",
      state: "UNKNOWN",
      detail: "Dedicated model telemetry is not exposed here",
    };
  }

  const availability = String(model.availability ?? "UNKNOWN").toUpperCase();
  const observation = String(
    model.observation_status ?? "UNKNOWN",
  ).toUpperCase();

  if (
    availability.includes("OFFLINE") ||
    availability.includes("UNAVAILABLE")
  ) {
    return {
      key: label,
      label,
      tone: "bad",
      state: "OFFLINE",
      detail: observation,
    };
  }

  if (
    availability.includes("READY") ||
    observation.includes("AVAILABLE") ||
    observation.includes("COMPLETE")
  ) {
    return {
      key: label,
      label,
      tone: "good",
      state: "HEALTHY",
      detail: `${availability} · ${observation}`,
    };
  }

  if (availability.includes("CONFIGURED")) {
    return {
      key: label,
      label,
      tone: "warn",
      state: "WAITING",
      detail: `${availability} · ${observation}`,
    };
  }

  return {
    key: label,
    label,
    tone: "unknown",
    state: availability,
    detail: observation,
  };
}

function sourceHealth(
  label: string,
  source:
    | { availability?: string; error_type?: string | null }
    | undefined,
  overviewOk: boolean,
): HealthItem {
  if (!overviewOk) {
    return {
      key: label,
      label,
      tone: "bad",
      state: "OFFLINE",
      detail: "Factory overview unavailable",
    };
  }
  if (!source) {
    return {
      key: label,
      label,
      tone: "unknown",
      state: "UNKNOWN",
      detail: "Dedicated health source not exposed",
    };
  }

  const state = String(source.availability ?? "UNKNOWN").toUpperCase();
  if (state === "AVAILABLE") {
    return {
      key: label,
      label,
      tone: "good",
      state: "HEALTHY",
      detail: "Real backend contract available",
    };
  }
  if (state.includes("OFFLINE")) {
    return {
      key: label,
      label,
      tone: "bad",
      state: "OFFLINE",
      detail: source.error_type ?? state,
    };
  }
  return {
    key: label,
    label,
    tone: "warn",
    state,
    detail: source.error_type ?? "Source state incomplete",
  };
}

function featureHealth(
  label: string,
  system: SystemStatus | null,
  needles: string[],
  systemOk: boolean,
): HealthItem {
  if (!systemOk) {
    return {
      key: label,
      label,
      tone: "bad",
      state: "OFFLINE",
      detail: "System status endpoint unavailable",
    };
  }
  if (!system) {
    return {
      key: label,
      label,
      tone: "unknown",
      state: "UNKNOWN",
      detail: "No system status payload",
    };
  }

  const matches = Object.entries(system).filter(([key]) =>
    needles.some((needle) =>
      key.toUpperCase().includes(needle.toUpperCase()),
    ),
  );
  if (!matches.length) {
    return {
      key: label,
      label,
      tone: "unknown",
      state: "UNKNOWN",
      detail: "Dedicated feature heartbeat not exposed",
    };
  }

  const enabled = matches.filter(([, value]) => value === true);
  if (enabled.length) {
    return {
      key: label,
      label,
      tone: "good",
      state: "ENABLED",
      detail: enabled
        .slice(0, 2)
        .map(([key]) => display(key))
        .join(" · "),
    };
  }

  const disabled = matches.filter(([, value]) => value === false);
  if (disabled.length === matches.length) {
    return {
      key: label,
      label,
      tone: "warn",
      state: "DISABLED",
      detail: disabled
        .slice(0, 2)
        .map(([key]) => display(key))
        .join(" · "),
    };
  }

  return {
    key: label,
    label,
    tone: "unknown",
    state: "UNKNOWN",
    detail: "Feature keys exist but do not expose boolean health",
  };
}

export default function Batch10BCommandLayer() {
  const [open, setOpen] = useState(true);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [opportunities, setOpportunities] =
    useState<OpportunityStatus | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [opsError, setOpsError] = useState<string | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [opportunityError, setOpportunityError] = useState<string | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [, setClock] = useState(0);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const value = await getJson<Operations>("/paper-fund/operations");
        if (!disposed) {
          setOperations(value);
          setOpsError(null);
        }
      } catch (error) {
        if (!disposed) {
          setOpsError(
            error instanceof Error
              ? error.message
              : "operations unavailable",
          );
        }
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const value = await getJson<Overview>(
          "/experience/factory-intelligence/overview",
        );
        if (!disposed) {
          setOverview(value);
          setOverviewError(null);
        }
      } catch (error) {
        if (!disposed) {
          setOverviewError(
            error instanceof Error
              ? error.message
              : "overview unavailable",
          );
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

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const value = await getJson<OpportunityStatus>(
          "/opportunities/status",
        );
        if (!disposed) {
          setOpportunities(value);
          setOpportunityError(null);
        }
      } catch (error) {
        if (!disposed) {
          setOpportunityError(
            error instanceof Error
              ? error.message
              : "opportunity status unavailable",
          );
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

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const value = await getJson<SystemStatus>("/system/status");
        if (!disposed) {
          setSystem(value);
          setSystemError(null);
        }
      } catch (error) {
        if (!disposed) {
          setSystemError(
            error instanceof Error
              ? error.message
              : "system status unavailable",
          );
        }
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(
      () => setClock((value) => value + 1),
      1_000,
    );
    return () => window.clearInterval(timer);
  }, []);

  const models = overview?.council?.models ?? [];
  const findModel = (...needles: string[]) =>
    models.find((model) =>
      needles.some((needle) =>
        `${model.id ?? ""} ${model.label ?? ""} ${model.provider ?? ""}`
          .toUpperCase()
          .includes(needle),
      ),
    );

  const opsOk = !opsError && !!operations;
  const overviewOk = !overviewError && !!overview;
  const systemOk = !systemError && !!system;
  const factorySource = overview?.source_availability?.factory;
  const councilSource = overview?.source_availability?.council;

  const health: HealthItem[] = [
    modelHealth("GPT", findModel("OPENAI", "GPT"), overviewOk),
    modelHealth("GROK", findModel("GROK", "XAI"), overviewOk),
    featureHealth("GEMINI", system, ["GEMINI"], systemOk),
    modelHealth("KIMI", findModel("KIMI"), overviewOk),
    workerHealth("9A", operations?.observation, opsOk),
    workerHealth("9B", operations?.paper_trading, opsOk),
    sourceHealth("COMMITTEE", councilSource ?? factorySource, overviewOk),
    sourceHealth("RISK", factorySource, overviewOk),
    operations?.safety?.paper_mode === true &&
    operations?.safety?.live_execution === false
      ? {
          key: "PAPER FUND",
          label: "PAPER FUND",
          tone: "good",
          state: "HEALTHY",
          detail: `NAV ${operations?.portfolio?.nav?.toFixed(2) ?? "—"} · live locked`,
        }
      : {
          key: "PAPER FUND",
          label: "PAPER FUND",
          tone: opsOk ? "warn" : "bad",
          state: opsOk ? "CHECK" : "OFFLINE",
          detail: opsOk
            ? "Paper/live safety state incomplete"
            : "Operations endpoint unavailable",
        },
    featureHealth("STORAGE", system, ["STORAGE"], systemOk),
    featureHealth("LEDGER", system, ["PERSISTENT_LEDGER"], systemOk),
  ];

  const latestScan = opportunities?.latest_scan ?? null;
  const scanCandidates =
    latestScan?.candidates?.length
      ? latestScan.candidates
      : opportunities?.queue ?? [];

  const radar = useMemo<RadarRow[]>(() => {
    const results = operations?.paper_trading?.case_results ?? [];
    const governedCases = overview?.cases ?? [];

    return scanCandidates.slice(0, 10).map((candidate, index) => {
      const ticker = String(candidate.ticker ?? "NO TICKER").toUpperCase();
      const caseId = candidate.promoted_case_id ?? null;
      const result = results.find(
        (row) =>
          (caseId && row.case_id === caseId) ||
          (!caseId && String(row.ticker ?? "").toUpperCase() === ticker),
      );
      const governedCase = governedCases.find(
        (row) =>
          (caseId && row.case_id === caseId) ||
          String(row.ticker ?? "").toUpperCase() === ticker,
      );

      const stage = display(
        result?.stage ??
          governedCase?.stage ??
          (caseId
            ? "PROMOTED"
            : candidate.eligible_for_promotion
              ? "QUEUED"
              : "OBSERVED"),
      );
      const committee = display(
        result?.committee_disposition ?? governedCase?.committee ?? "UNKNOWN",
      );
      const risk = display(governedCase?.risk ?? "UNKNOWN");

      const why: string[] = [];
      if (candidate.catalyst_categories?.length) {
        why.push(
          `Catalysts: ${candidate.catalyst_categories
            .map(display)
            .join(" · ")}`,
        );
      }
      if (candidate.reason_codes?.length) {
        why.push(
          `9A reasons: ${candidate.reason_codes.map(display).join(" · ")}`,
        );
      }
      why.push(
        `${candidate.news_count ?? 0} news records · ${candidate.source_count ?? 0} sources · ${candidate.recent_24h_count ?? 0} within 24h`,
      );
      if (!candidate.reason_codes?.length && !candidate.catalyst_categories?.length) {
        why.push("No additional surfacing reason is exposed by the real feed.");
      }

      const waiting: string[] = [];
      if (caseId) {
        waiting.push("Promoted to a governed case by 9A.");
      } else if (candidate.eligible_for_promotion) {
        waiting.push(
          "Promotion-eligible. 9A remains bounded to at most one promotion per scan.",
        );
      } else {
        waiting.push("Promotion gate not cleared by the backend.");
        waiting.push(
          `Observed gate data: quote ${candidate.quote_ok ? "OK" : "NOT OK"} · news ${candidate.news_count ?? 0} · score ${candidate.score ?? "—"}`,
        );
      }
      if (result?.failed_checks?.length) {
        waiting.push(
          `Failed checks: ${result.failed_checks.map(display).join(" · ")}`,
        );
      }
      if (result?.unmet_requirements?.length) {
        waiting.push(
          `Unmet: ${result.unmet_requirements.map(display).join(" · ")}`,
        );
      }

      return {
        key:
          candidate.opportunity_candidate_id ??
          caseId ??
          `${ticker}-${candidate.created_at ?? index}`,
        ticker,
        score: candidate.score ?? null,
        price: candidate.current_price ?? null,
        priority: display(candidate.priority ?? "UNKNOWN"),
        stage,
        committee,
        risk,
        why,
        waiting,
        caseId,
      };
    });
  }, [operations, overview, scanCandidates]);

  const committeeCount = (overview?.cases ?? []).filter((row) =>
    isKnownState(row.committee),
  ).length;
  const riskCount = (overview?.cases ?? []).filter((row) =>
    isKnownState(row.risk),
  ).length;

  const funnel = [
    ["UNIVERSE", latestScan?.universe_count ?? "—", "latest 9A universe"],
    ["SCANNED", latestScan?.scanned_count ?? operations?.observation?.last_scan_count ?? "—", "latest 9A scan"],
    ["QUEUED", latestScan?.queued_count ?? operations?.observation?.last_queue_count ?? "—", "promotion-eligible queue"],
    ["PROMOTED", operations?.observation?.promoted_case_count ?? "—", "latest 9A cycle"],
    ["DEEP RESEARCH", operations?.paper_trading?.gap_hunts_run ?? "—", "latest 9B deepening"],
    ["COMMITTEE", committeeCount, "governed cases with committee state"],
    ["RISK", riskCount, "governed cases with risk state"],
    ["PAPER", operations?.paper_trading?.paper_executions_created ?? "—", "latest 9B paper executions"],
  ] as const;

  const errors = [
    opsError ? `OPERATIONS: ${opsError}` : null,
    overviewError ? `OVERVIEW: ${overviewError}` : null,
    opportunityError ? `RADAR: ${opportunityError}` : null,
    systemError ? `SYSTEM: ${systemError}` : null,
  ].filter((value): value is string => Boolean(value));

  return (
    <section className={`b10b-command ${open ? "open" : "closed"}`}>
      <button
        className="b10b-command__toggle"
        type="button"
        onClick={() => setOpen((value) => !value)}
      >
        <span>BATCH 10B · REAL COMMAND</span>
        <strong>IIOS HEARTBEAT + LIVE 9A RADAR</strong>
        <em>{open ? "COLLAPSE" : "EXPAND"}</em>
      </button>

      {open ? (
        <div className="b10b-command__body">
          <header className="b10b-head">
            <div>
              <span>GOVERNED TELEMETRY ONLY</span>
              <h2>Real Intelligence Command Layer</h2>
              <p>
                Health and activity are intentionally separate. Every radar row
                below comes from the persisted opportunity scan or governed case
                state. Unknown stays unknown; no mock state is allowed here.
              </p>
            </div>
            <div className="b10b-safety">
              <strong>
                {operations?.safety?.live_capital_locked === true
                  ? "LIVE CAPITAL LOCKED"
                  : "LIVE STATE UNKNOWN"}
              </strong>
              <span>
                BROKER {operations?.safety?.broker_connected === false ? "FALSE" : "UNKNOWN"}
                {" · "}PAPER {operations?.safety?.paper_mode === true ? "TRUE" : "UNKNOWN"}
              </span>
            </div>
          </header>

          {errors.length ? (
            <div className="b10b-errors">
              {errors.map((error) => (
                <span key={error}>{error}</span>
              ))}
            </div>
          ) : null}

          <div className="b10b-health">
            {health.map((item) => (
              <div
                className={`b10b-health__item ${item.tone}`}
                key={item.key}
                title={item.detail}
              >
                <i />
                <span>{item.label}</span>
                <strong>{item.state}</strong>
                <small>{item.detail}</small>
              </div>
            ))}
          </div>

          <div className="b10b-activity">
            <div>
              <span>9A ACTIVITY</span>
              <strong>
                {latestScan?.scanned_count ?? operations?.observation?.last_scan_count ?? "—"} scanned
                {" · "}{latestScan?.queued_count ?? operations?.observation?.last_queue_count ?? "—"} queued
                {" · "}{operations?.observation?.promoted_case_count ?? "—"} promoted
              </strong>
            </div>
            <div>
              <span>9B ACTIVITY</span>
              <strong>
                {operations?.paper_trading?.case_count_inspected ?? "—"} cases
                {" · "}{operations?.paper_trading?.gap_hunts_run ?? "—"} deepened
                {" · "}{operations?.paper_trading?.paper_executions_created ?? "—"} orders
              </strong>
            </div>
          </div>

          <div className="b10b-grid">
            <section className="b10b-panel">
              <header>
                <div>
                  <span>ACTUAL LATEST OPPORTUNITY SCAN</span>
                  <h3>Live 9A Radar</h3>
                </div>
                <strong>{radar.length} visible · UNKNOWN ≠ ZERO</strong>
              </header>

              <div className="b10b-radar">
                {radar.length ? (
                  radar.map((row) => (
                    <article className="b10b-radar__row" key={row.key}>
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded(expanded === row.key ? null : row.key)
                        }
                      >
                        <div>
                          <strong>{row.ticker}</strong>
                          <span>
                            {row.price === null ? "PRICE —" : `$${row.price.toFixed(2)}`}
                            {" · "}{row.caseId ?? "NOT PROMOTED"}
                          </span>
                        </div>
                        <b>{row.score ?? "—"}</b>
                        <em>{row.priority} · {row.stage}</em>
                        <i>{row.committee} · RISK {row.risk}</i>
                        <u>{expanded === row.key ? "CLOSE" : "WHY / WHY NOT"}</u>
                      </button>

                      {expanded === row.key ? (
                        <div className="b10b-explain">
                          <div>
                            <span>WHY 9A SURFACED IT</span>
                            {row.why.map((text, index) => (
                              <p key={index}>{text}</p>
                            ))}
                          </div>
                          <div>
                            <span>WAITING / BLOCKERS</span>
                            {row.waiting.map((text, index) => (
                              <p key={index}>{text}</p>
                            ))}
                          </div>
                          <div>
                            <span>GOVERNED STATE</span>
                            <strong>{row.committee}</strong>
                            <p>Risk: {row.risk}</p>
                            <small>No missing reason is inferred.</small>
                          </div>
                        </div>
                      ) : null}
                    </article>
                  ))
                ) : (
                  <div className="b10b-empty">
                    No candidate rows were returned by the real opportunity feed.
                  </div>
                )}
              </div>
            </section>

            <section className="b10b-panel">
              <header>
                <div>
                  <span>REAL COUNTS ONLY</span>
                  <h3>Governed Funnel Snapshot</h3>
                </div>
                <strong>UNKNOWN ≠ ZERO</strong>
              </header>
              <div className="b10b-funnel">
                {funnel.map(([label, value, detail], index) => (
                  <div className="b10b-funnel__step" key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                    <small>{detail}</small>
                    {index < funnel.length - 1 ? <i>↓</i> : null}
                  </div>
                ))}
              </div>
            </section>
          </div>

          <footer className="b10b-footer">
            <span>
              9A SCAN · {latestScan?.created_at ? new Date(latestScan.created_at).toLocaleTimeString() : "UNKNOWN"}
            </span>
            <span>
              OPS UPDATED · {operations?.generated_at ? new Date(operations.generated_at).toLocaleTimeString() : "UNKNOWN"}
            </span>
            <span>
              OVERVIEW UPDATED · {overview?.generated_at ? new Date(overview.generated_at).toLocaleTimeString() : "UNKNOWN"}
            </span>
            <strong>NO FAKE GREEN LIGHTS · NO MOCK TELEMETRY</strong>
          </footer>
        </div>
      ) : null}
    </section>
  );
}
