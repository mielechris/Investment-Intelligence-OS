import { useEffect, useMemo, useState, type ReactNode } from "react";
import "./PaperFundOperationsDock.css";

const API =
  import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8002";

const ACTIVE_CASE_KEY = "iios.factoryIntelligence.activeCaseId";

type Position = {
  ticker?: string | null;
  quantity?: number | null;
  average_cost?: number | null;
  mark_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_return_pct?: number | null;
};

type Worker = {
  availability: string;
  cadence_minutes: number;
  last_completed_at?: string | null;
  next_due_at?: string | null;
  seconds_until_next_cycle?: number | null;
  cadence_state: string;
  market_phase?: string | null;
};

type CaseResult = {
  case_id?: string | null;
  ticker?: string | null;
  stage: string;
  committee_disposition?: string | null;
  committee_confidence?: number | null;
  capital_stage?: string | null;
  capital_decision?: string | null;
  sizing_decision?: string | null;
  failed_checks: string[];
  unmet_requirements: string[];
  execution_id?: string | null;
  shares?: number | null;
  entry_price?: number | null;
  notional?: number | null;
};

type Operations = {
  generated_at: string;
  refresh_seconds: number;
  portfolio: {
    starting_cash?: number | null;
    nav?: number | null;
    cash?: number | null;
    market_value?: number | null;
    realized_pnl?: number | null;
    unrealized_pnl?: number | null;
    total_pnl?: number | null;
    gross_exposure?: number | null;
    position_count?: number | null;
    transaction_count?: number | null;
    positions: Position[];
    snapshot_count?: number | null;
    cumulative_return_pct?: number | null;
    current_drawdown_pct?: number | null;
    max_drawdown_pct?: number | null;
  };
  observation: Worker & {
    last_scan_status?: string | null;
    last_scan_count?: number | null;
    last_queue_count?: number | null;
    promoted_case_count?: number | null;
    snapshot_count?: number | null;
    latest_promoted_case?: {
      case_id?: string | null;
      ticker?: string | null;
      score?: number | null;
    };
  };
  paper_trading: Worker & {
    paper_execution_window_open: boolean;
    case_count_inspected?: number | null;
    gap_hunts_run?: number | null;
    paper_executions_created?: number | null;
    cycle_duration_seconds?: number | null;
    funnel: {
      inspected: number;
      research_blocked_or_waiting: number;
      capital_or_authorization_path: number;
      waiting_for_regular_session: number;
      paper_positions_opened: number;
      errors_or_fail_closed: number;
    };
    case_results: CaseResult[];
  };
  latest_deepened_case: {
    case_id?: string | null;
    ticker?: string | null;
    topic?: string | null;
    qualified: boolean;
    created_at?: string | null;
  };
  recent_paper_orders: Array<{
    execution_id?: string | null;
    case_id?: string | null;
    status?: string | null;
    execution?: string | null;
    shares?: number | null;
    entry_price?: number | null;
    notional?: number | null;
    created_at?: string | null;
  }>;
  safety: {
    paper_mode: boolean;
    broker_connected: boolean;
    live_capital_locked: boolean;
    committee_override: boolean;
    risk_override: boolean;
    capital_override: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
};

type JourneyRow = {
  key: string;
  status: string;
  label: string;
};

type CaseDetail = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  journey: JourneyRow[];
  committee: {
    disposition: string;
    confidence?: number | null;
  };
  risk: { decision: string };
  qualification: {
    qualified_buy_candidate: boolean;
    status: string;
  };
  paper_execution: {
    execution: string;
    reason?: string | null;
  };
};

async function apiJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(
      (await response.text()) || `IIOS request failed ${response.status}`,
    );
  }
  return response.json() as Promise<T>;
}

function money(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function pointPct(value?: number | null, digits = 2): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(digits)}%`;
}

function ratioPct(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

function displayState(value?: string | null): string {
  return String(value || "UNKNOWN").replaceAll("_", " ");
}

function timeLabel(value?: string | null): string {
  if (!value) return "UNKNOWN";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "UNKNOWN";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function countdown(value?: string | null): string {
  if (!value) return "UNKNOWN";
  const due = new Date(value).getTime();
  if (Number.isNaN(due)) return "UNKNOWN";
  const seconds = Math.max(0, Math.floor((due - Date.now()) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function tone(value?: string | null): string {
  const text = String(value || "UNKNOWN").toUpperCase();

  // Fail-closed / negative semantics must be evaluated before positive
  // substrings such as QUALIFIED or WATCH. This prevents states like
  // RESEARCH_NOT_QUALIFIED from ever rendering as a positive state.
  if (
    text.includes("ERROR") ||
    text.includes("REJECT") ||
    text.includes("BLOCKED") ||
    text.includes("OVERDUE") ||
    text.includes("NO_TRADE") ||
    text.includes("NOT_QUALIFIED") ||
    text.includes("NOT_WATCH") ||
    text.includes("VETO") ||
    text.includes("INVALIDATED")
  ) {
    return "bad";
  }
  if (
    text.includes("WAIT") ||
    text.includes("PENDING") ||
    text.includes("LOCKED") ||
    text.includes("CLOSED") ||
    text.includes("UNKNOWN") ||
    text.includes("NOT_EXECUTED") ||
    text.includes("NO_STATE") ||
    text.includes("NO_SNAPSHOT")
  ) {
    return "warn";
  }
  if (
    text.includes("COMPLETE") ||
    text.includes("OPENED") ||
    text.includes("QUALIFIED") ||
    text.includes("READY") ||
    text.includes("ON_CADENCE") ||
    text.includes("WATCH") ||
    text.includes("APPROVED") ||
    text.includes("ACTIVE") ||
    text === "OPEN"
  ) {
    return "good";
  }
  return "neutral";
}

function Pill({ value }: { value?: string | null }) {
  const label = displayState(value);
  return <span className={`pfo-pill ${tone(value)}`}>{label}</span>;
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <div className="pfo-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function WorkerCard({
  title,
  eyebrow,
  worker,
  children,
}: {
  title: string;
  eyebrow: string;
  worker: Worker;
  children: ReactNode;
}) {
  return (
    <article className="pfo-worker-card">
      <div className="pfo-worker-head">
        <div>
          <span>{eyebrow}</span>
          <h4>{title}</h4>
        </div>
        <Pill value={worker.cadence_state} />
      </div>
      <div className="pfo-worker-clock">
        <div>
          <span>NEXT CYCLE</span>
          <strong>{countdown(worker.next_due_at)}</strong>
        </div>
        <div>
          <span>LAST COMPLETE</span>
          <strong>{timeLabel(worker.last_completed_at)}</strong>
        </div>
        <div>
          <span>MARKET</span>
          <strong>{displayState(worker.market_phase)}</strong>
        </div>
      </div>
      {children}
    </article>
  );
}

function governedGateState(
  gate: JourneyRow,
  detail: CaseDetail | null,
): string {
  if (!detail) return gate.status;
  if (gate.key === "COMMITTEE") {
    return detail.committee.disposition || "UNKNOWN";
  }
  if (gate.key === "RISK") {
    return detail.risk.decision || "UNKNOWN";
  }
  if (gate.key === "QUALIFICATION") {
    return detail.qualification.qualified_buy_candidate
      ? "QUALIFIED"
      : "NOT_QUALIFIED";
  }
  if (gate.key === "PAPER_EXECUTION") {
    return detail.paper_execution.execution || "NOT_EXECUTED";
  }
  return gate.status;
}

export default function PaperFundOperationsDock() {
  const [open, setOpen] = useState(true);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setClock] = useState(0);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(() =>
    window.localStorage.getItem(ACTIVE_CASE_KEY),
  );

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const next = await apiJson<Operations>("/paper-fund/operations");
        if (disposed) return;
        setOperations(next);
        setError(null);
      } catch (err) {
        if (disposed) return;
        setError(
          err instanceof Error ? err.message : "Paper Fund feed unavailable",
        );
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
    const sync = () => {
      setSelectedCaseId(window.localStorage.getItem(ACTIVE_CASE_KEY));
    };
    sync();
    const timer = window.setInterval(sync, 750);
    return () => window.clearInterval(timer);
  }, []);

  const fundFocusCaseId = useMemo(() => {
    return (
      operations?.latest_deepened_case.case_id ??
      operations?.paper_trading.case_results[0]?.case_id ??
      operations?.observation.latest_promoted_case?.case_id ??
      selectedCaseId ??
      null
    );
  }, [operations, selectedCaseId]);

  useEffect(() => {
    if (!fundFocusCaseId) {
      setCaseDetail(null);
      return;
    }
    let disposed = false;
    const load = async () => {
      try {
        const next = await apiJson<CaseDetail>(
          `/experience/factory-intelligence/case/${encodeURIComponent(
            fundFocusCaseId,
          )}`,
        );
        if (!disposed) setCaseDetail(next);
      } catch {
        if (!disposed) setCaseDetail(null);
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [fundFocusCaseId]);

  useEffect(() => {
    const timer = window.setInterval(() => setClock((value) => value + 1), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const nav = operations?.portfolio.nav ?? 10_000;
  const positions = operations?.portfolio.positions ?? [];
  const paperWindow = operations?.paper_trading.paper_execution_window_open;

  return (
    <aside className={`pfo-dock ${open ? "open" : "closed"}`}>
      <button
        type="button"
        className="pfo-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span>PAPER FUND OPS</span>
        <strong>{money(nav)}</strong>
        <em>{open ? "MINIMIZE" : "OPEN LIVE BOARD"}</em>
      </button>

      {open ? (
        <div className="pfo-board">
          <header className="pfo-board-head">
            <div>
              <span>IIOS · BATCH 9C</span>
              <h2>$10K Paper Fund Operations</h2>
              <p>
                Live read-only scoreboard for Observation → Qualification →
                Capital → Paper Execution.
              </p>
            </div>
            <div className="pfo-live-lock">
              <i />
              <strong>PAPER / SHADOW</strong>
              <span>BROKER FALSE · LIVE FALSE</span>
            </div>
          </header>

          {error ? (
            <div className="pfo-error">
              <strong>OPERATIONS FEED OFFLINE</strong>
              <span>{error}</span>
            </div>
          ) : null}

          <section className="pfo-metrics">
            <Metric label="NAV" value={money(operations?.portfolio.nav)} />
            <Metric label="Cash" value={money(operations?.portfolio.cash)} />
            <Metric
              label="Market value"
              value={money(operations?.portfolio.market_value)}
            />
            <Metric
              label="Total P&L"
              value={money(operations?.portfolio.total_pnl)}
              detail={`Return ${pointPct(
                operations?.portfolio.cumulative_return_pct,
              )}`}
            />
            <Metric
              label="Drawdown"
              value={pointPct(operations?.portfolio.current_drawdown_pct)}
              detail={`Max ${pointPct(
                operations?.portfolio.max_drawdown_pct,
              )}`}
            />
            <Metric
              label="Positions"
              value={operations?.portfolio.position_count ?? 0}
              detail={`${operations?.portfolio.transaction_count ?? 0} transactions`}
            />
          </section>

          <section className="pfo-worker-grid">
            <WorkerCard
              eyebrow="DATA FACTORY"
              title="9A Observation Engine"
              worker={
                operations?.observation ?? {
                  availability: "NO_STATE",
                  cadence_minutes: 15,
                  cadence_state: "UNKNOWN",
                }
              }
            >
              <div className="pfo-worker-stats">
                <span>
                  SCANNED <strong>{operations?.observation.last_scan_count ?? 0}</strong>
                </span>
                <span>
                  QUEUED <strong>{operations?.observation.last_queue_count ?? 0}</strong>
                </span>
                <span>
                  PROMOTED <strong>{operations?.observation.promoted_case_count ?? 0}</strong>
                </span>
              </div>
              <div className="pfo-focus-line">
                <span>LATEST PROMOTION</span>
                <strong>
                  {operations?.observation.latest_promoted_case?.ticker ?? "NONE"}
                </strong>
                <em>
                  score {operations?.observation.latest_promoted_case?.score ?? "—"}
                </em>
              </div>
            </WorkerCard>

            <WorkerCard
              eyebrow="MOCK CAPITAL"
              title="9B Governed Paper Trading"
              worker={
                operations?.paper_trading ?? {
                  availability: "NO_STATE",
                  cadence_minutes: 15,
                  cadence_state: "UNKNOWN",
                }
              }
            >
              <div className="pfo-worker-stats">
                <span>
                  CASES <strong>{operations?.paper_trading.case_count_inspected ?? 0}</strong>
                </span>
                <span>
                  DEEPENED <strong>{operations?.paper_trading.gap_hunts_run ?? 0}</strong>
                </span>
                <span>
                  ORDERS <strong>{operations?.paper_trading.paper_executions_created ?? 0}</strong>
                </span>
              </div>
              <div className="pfo-focus-line">
                <span>PAPER WINDOW</span>
                <Pill value={paperWindow ? "OPEN" : "CLOSED"} />
                <em>regular U.S. session only</em>
              </div>
            </WorkerCard>
          </section>

          <section className="pfo-focus-card">
            <div className="pfo-section-head">
              <div>
                <span>GOVERNED CASE JOURNEY</span>
                <h3>
                  Fund focus · {caseDetail?.ticker ?? operations?.latest_deepened_case.ticker ?? "NONE"}
                </h3>
              </div>
              <div className="pfo-focus-meta">
                <Pill
                  value={
                    operations?.latest_deepened_case.qualified
                      ? "QUALIFIED"
                      : caseDetail?.committee.disposition ?? "UNKNOWN"
                  }
                />
                <strong>{ratioPct(caseDetail?.committee.confidence)}</strong>
              </div>
            </div>

            <div className="pfo-gates">
              {(caseDetail?.journey ?? []).map((gate) => {
                const actualState = governedGateState(gate, caseDetail);
                return (
                  <div
                    className={`pfo-gate ${tone(actualState)}`}
                    key={gate.key}
                  >
                    <span>{displayState(gate.key)}</span>
                    <strong>{displayState(actualState)}</strong>
                    <em>{gate.label}</em>
                  </div>
                );
              })}
              {!caseDetail ? (
                <div className="pfo-empty">
                  No governed focus case is available yet.
                </div>
              ) : null}
            </div>
          </section>

          <section className="pfo-funnel-grid">
            <div className="pfo-panel">
              <div className="pfo-section-head">
                <div>
                  <span>CAPITAL FUNNEL</span>
                  <h3>Latest 9B case classifications</h3>
                </div>
                <strong>
                  {operations?.paper_trading.funnel.inspected ?? 0} inspected
                </strong>
              </div>
              <div className="pfo-funnel-metrics">
                <Metric
                  label="Research blocked"
                  value={
                    operations?.paper_trading.funnel
                      .research_blocked_or_waiting ?? 0
                  }
                />
                <Metric
                  label="Capital path"
                  value={
                    operations?.paper_trading.funnel
                      .capital_or_authorization_path ?? 0
                  }
                />
                <Metric
                  label="Waiting session"
                  value={
                    operations?.paper_trading.funnel
                      .waiting_for_regular_session ?? 0
                  }
                />
                <Metric
                  label="Opened"
                  value={
                    operations?.paper_trading.funnel.paper_positions_opened ?? 0
                  }
                />
              </div>
              <div className="pfo-case-list">
                {(operations?.paper_trading.case_results ?? [])
                  .slice(0, 8)
                  .map((row, index) => (
                    <div className="pfo-case-row" key={`${row.case_id}-${index}`}>
                      <div>
                        <strong>{row.ticker ?? "NO TICKER"}</strong>
                        <span>{row.case_id ?? "NO CASE"}</span>
                      </div>
                      <Pill value={row.stage} />
                      <em>{ratioPct(row.committee_confidence)}</em>
                    </div>
                  ))}
                {(operations?.paper_trading.case_results ?? []).length === 0 ? (
                  <div className="pfo-empty">No 9B case classifications yet.</div>
                ) : null}
              </div>
            </div>

            <div className="pfo-panel">
              <div className="pfo-section-head">
                <div>
                  <span>PAPER PORTFOLIO</span>
                  <h3>Positions & governed orders</h3>
                </div>
                <strong>{operations?.portfolio.snapshot_count ?? 0} snapshots</strong>
              </div>

              <div className="pfo-position-list">
                {positions.map((position, index) => (
                  <div className="pfo-position-row" key={`${position.ticker}-${index}`}>
                    <div>
                      <strong>{position.ticker ?? "UNKNOWN"}</strong>
                      <span>{position.quantity ?? 0} shares</span>
                    </div>
                    <div>
                      <span>MARK</span>
                      <strong>{money(position.mark_price)}</strong>
                    </div>
                    <div>
                      <span>P&L</span>
                      <strong>{money(position.unrealized_pnl)}</strong>
                    </div>
                  </div>
                ))}
                {positions.length === 0 ? (
                  <div className="pfo-empty">
                    $10K fund is currently 100% cash. No trade is manufactured to fill the account.
                  </div>
                ) : null}
              </div>

              <div className="pfo-orders">
                {(operations?.recent_paper_orders ?? []).slice(0, 5).map((order) => (
                  <div
                    className="pfo-order-row"
                    key={order.execution_id ?? order.case_id ?? "order"}
                  >
                    <div>
                      <strong>{order.shares ?? 0} shares</strong>
                      <span>{money(order.entry_price)} entry</span>
                    </div>
                    <strong>{money(order.notional)}</strong>
                    <span>{timeLabel(order.created_at)}</span>
                  </div>
                ))}
                {(operations?.recent_paper_orders ?? []).length === 0 ? (
                  <div className="pfo-empty">No governed paper orders have been created yet.</div>
                ) : null}
              </div>
            </div>
          </section>

          <footer className="pfo-footer">
            <div>
              <span>LATEST DEEPENED CASE</span>
              <strong>
                {operations?.latest_deepened_case.ticker ?? "NONE"} ·{" "}
                {operations?.latest_deepened_case.qualified
                  ? "QUALIFIED"
                  : "STILL EARNING QUALIFICATION"}
              </strong>
            </div>
            <div>
              <span>SAFETY RAIL</span>
              <strong>NO BROKER · NO LIVE CAPITAL · GOVERNED PAPER ONLY</strong>
            </div>
          </footer>
        </div>
      ) : null}
    </aside>
  );
}
