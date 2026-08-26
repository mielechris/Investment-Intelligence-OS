import { useCallback, useEffect, useMemo, useState } from "react";

const API = "http://127.0.0.1:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type DashboardCase = {
  case_id: string;
  topic: string;
  ticker?: string;
  health?: string;
  committee_disposition?: string;
  committee_confidence?: number;
  evidence_quality?: number;
  latest_return_pct?: number;
  latest_action?: string;
  monitoring_enabled?: boolean;
};

type FactoryStatus = {
  portfolio?: {
    nav?: number | null;
    cash?: number | null;
    positions?: number | null;
    return_pct?: number | null;
    drawdown_pct?: number | null;
  };
  safety?: { all_invariants?: boolean; live_execution?: boolean };
};

type History = { signal_ladder?: { current_stage?: string; next_requirements?: string[] } };

type State = { cases: DashboardCase[]; factory: FactoryStatus | null; history: History | null; online: boolean; caseId: string | null };

const pct = (value?: number | null) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
const money = (value?: number | null) => value == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
const label = (value?: string) => String(value || "UNKNOWN").replaceAll("_", " ");

export default function PortfolioThesisWarRoom() {
  const [state, setState] = useState<State>({ cases: [], factory: null, history: null, online: false, caseId: window.localStorage.getItem(ACTIVE_CASE_KEY) });

  const load = useCallback(async () => {
    const caseId = window.localStorage.getItem(ACTIVE_CASE_KEY);
    try {
      const [dashboardResponse, factoryResponse] = await Promise.all([
        fetch(`${API}/monitoring/dashboard`),
        fetch(`${API}/factory-room/status`),
      ]);
      if (!dashboardResponse.ok || !factoryResponse.ok) throw new Error("War room telemetry unavailable");
      const dashboard = await dashboardResponse.json() as { cases?: DashboardCase[] };
      const factory = await factoryResponse.json() as FactoryStatus;
      let history: History | null = null;
      if (caseId) {
        const historyResponse = await fetch(`${API}/history/${caseId}`);
        if (historyResponse.ok) history = await historyResponse.json() as History;
      }
      setState({ cases: dashboard.cases || [], factory, history, online: true, caseId });
    } catch {
      setState((current) => ({ ...current, online: false, caseId }));
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, [load]);

  const active = useMemo(() => state.cases.find((item) => item.case_id === state.caseId) ?? null, [state.cases, state.caseId]);
  const nextRequirement = state.history?.signal_ladder?.next_requirements?.[0] || active?.latest_action || "Continue governed monitoring";
  const portfolio = state.factory?.portfolio;
  const safetyLocked = state.factory?.safety?.live_execution === false;

  return (
    <section className="portfolio-war-room">
      <div className="portfolio-war-room-head">
        <div>
          <div className="portfolio-war-room-eyebrow">X5 · PORTFOLIO & THESIS WAR ROOM</div>
          <h2>{active?.ticker || "PORTFOLIO"} · {active ? label(active.health) : "NO ACTIVE THESIS"}</h2>
          <p>{active?.topic || "Select an active case to connect thesis state to paper portfolio context."}</p>
        </div>
        <div className={state.online ? "portfolio-war-room-live" : "portfolio-war-room-offline"}>{state.online ? "WAR ROOM LIVE" : "WAR ROOM OFFLINE"}</div>
      </div>

      <div className="portfolio-war-room-grid">
        <div className="portfolio-war-room-panel">
          <div className="portfolio-war-room-label">PAPER PORTFOLIO</div>
          <div className="portfolio-war-room-metrics">
            <div><span>NAV</span><strong>{money(portfolio?.nav)}</strong></div>
            <div><span>CASH</span><strong>{money(portfolio?.cash)}</strong></div>
            <div><span>POSITIONS</span><strong>{portfolio?.positions ?? "—"}</strong></div>
            <div><span>RETURN</span><strong>{pct(portfolio?.return_pct)}</strong></div>
            <div><span>DRAWDOWN</span><strong>{pct(portfolio?.drawdown_pct)}</strong></div>
          </div>
        </div>

        <div className="portfolio-war-room-panel">
          <div className="portfolio-war-room-label">THESIS INTEGRITY</div>
          <div className="portfolio-war-room-metrics">
            <div><span>SIGNAL</span><strong>{label(state.history?.signal_ladder?.current_stage)}</strong></div>
            <div><span>COMMITTEE</span><strong>{label(active?.committee_disposition)}</strong></div>
            <div><span>CONFIDENCE</span><strong>{active?.committee_confidence == null ? "—" : `${Math.round(active.committee_confidence * 100)}%`}</strong></div>
            <div><span>EVIDENCE</span><strong>{active?.evidence_quality == null ? "—" : `${Math.round(active.evidence_quality * 100)}%`}</strong></div>
            <div><span>CASE RETURN</span><strong>{pct(active?.latest_return_pct)}</strong></div>
          </div>
        </div>
      </div>

      <div className="portfolio-war-room-decision">
        <div><span>NEXT GOVERNED REQUIREMENT</span><strong>{nextRequirement}</strong></div>
        <div><span>CAPITAL AUTHORITY</span><strong className={safetyLocked ? "portfolio-war-room-lock" : ""}>{safetyLocked ? "LIVE CAPITAL LOCKED" : "VERIFY SAFETY STATE"}</strong></div>
      </div>
    </section>
  );
}
