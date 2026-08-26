import { useCallback, useEffect, useState } from "react";
import PaperCapitalControlPanel from "./PaperCapitalControlPanel";
import "./CapitalCommandCenter.css";

const API = "http://127.0.0.1:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type CapitalStatus = {
  case_id: string;
  stage?: string;
  research?: { qualified_buy_candidate?: boolean; unmet_requirements?: string[] };
  thesis?: { status?: string; invalidated?: boolean };
  capital?: { decision?: string; reward_risk?: number; maximum_qualifying_entry?: number };
  permissions?: { capital_approved?: boolean; position_sizing_ready?: boolean; paper_authorization_ready?: boolean; paper_order_permission?: boolean; live_execution?: boolean };
};

type State = { caseId: string | null; status: CapitalStatus | null; pending: string[]; online: boolean; loading: boolean };

function cleanDetail(text: string) {
  try {
    const parsed = JSON.parse(text) as { detail?: string };
    return String(parsed.detail || text);
  } catch { return text; }
}

function stage(value?: string) { return String(value || "UNKNOWN").replaceAll("_", " "); }

export default function CapitalCommandCenter() {
  const [state, setState] = useState<State>({ caseId: window.localStorage.getItem(ACTIVE_CASE_KEY), status: null, pending: [], online: false, loading: true });

  const load = useCallback(async () => {
    const caseId = window.localStorage.getItem(ACTIVE_CASE_KEY);
    if (!caseId) { setState({ caseId: null, status: null, pending: [], online: true, loading: false }); return; }
    try {
      const response = await fetch(`${API}/paper-capital/${caseId}/status`);
      if (response.ok) {
        const status = await response.json() as CapitalStatus;
        setState({ caseId, status, pending: [], online: true, loading: false });
        return;
      }
      const text = cleanDetail(await response.text());
      if (response.status === 409 && /Required governed object missing|Latest Gap Hunter result has no Risk state/i.test(text)) {
        const missing = text.includes(":") ? [text.split(":").slice(1).join(":").trim()] : [text];
        setState({ caseId, status: null, pending: missing, online: true, loading: false });
        return;
      }
      throw new Error(text || `HTTP ${response.status}`);
    } catch {
      setState((current) => ({ ...current, status: null, pending: ["CAPITAL STATE UNAVAILABLE"], online: false, loading: false }));
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  const ready = Boolean(state.status);
  const status = state.status;
  const missing = state.pending[0];

  return (
    <>
      <section className="capital-command-card">
        <div className="capital-command-head">
          <div>
            <div className="capital-command-eyebrow">CAPITAL AUTHORITY CONTROL</div>
            <h2>{state.caseId ? stage(status?.stage || (ready ? "CAPITAL STATE" : "RESEARCH INPUTS PENDING")) : "SELECT A CASE"}</h2>
            <p>{state.loading ? "Loading governed capital state…" : ready ? `Case ${state.caseId} is eligible for capital-state inspection.` : state.caseId ? "Upstream governed research prerequisites are incomplete. Capital remains fail-closed." : "Select an active case in Cases before inspecting capital authority."}</p>
          </div>
          <div className={state.online ? "capital-command-live" : "capital-command-offline"}>{state.online ? "CONTROL ONLINE" : "CONTROL OFFLINE"}</div>
        </div>
        <div className="capital-command-metrics">
          <div><span>Research</span><strong>{status?.research?.qualified_buy_candidate ? "QUALIFIED" : "LOCKED"}</strong></div>
          <div><span>Thesis</span><strong>{stage(status?.thesis?.status)}</strong></div>
          <div><span>Capital</span><strong>{stage(status?.capital?.decision || "NOT EVALUATED")}</strong></div>
          <div><span>Sizing</span><strong>{status?.permissions?.position_sizing_ready ? "ELIGIBLE" : "LOCKED"}</strong></div>
          <div><span>Live Capital</span><strong className="capital-lock">LOCKED</strong></div>
        </div>
        <div className="capital-command-next"><span>{ready ? "GOVERNED STATE" : "BLOCKING PREREQUISITE"}</span><strong>{ready ? `Paper authority: ${status?.permissions?.paper_order_permission ? "READY" : "LOCKED"}` : missing || "Complete qualification and Gap Hunter first."}</strong></div>
      </section>
      {ready && state.caseId && <details className="native-drawer native-drawer--room-detail"><summary>Detailed Capital Chain</summary><div className="native-drawer-body"><PaperCapitalControlPanel caseId={state.caseId} /></div></details>}
    </>
  );
}
