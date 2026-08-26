import { useCallback, useEffect, useMemo, useState } from "react";

const API = "http://127.0.0.1:8002";

type Candidate = { ticker?: string; score?: number; priority?: string; eligible_for_promotion?: boolean; promoted_case_id?: string | null };
type OpportunityStatus = { latest_scan?: { scanned_count?: number; queued_count?: number; created_at?: string } | null; queue?: Candidate[]; paper_mode?: boolean; trade_execution_permission?: boolean; live_execution?: boolean };
type AutomationStatus = { config?: { enabled?: boolean; auto_dispatch_enabled?: boolean; interval_minutes?: number; last_scan_at?: string | null; last_scan_status?: string | null }; scheduler_running?: boolean };

type State = { status: OpportunityStatus | null; automation: AutomationStatus | null; online: boolean };

export default function ResearchCommandCard() {
  const [state, setState] = useState<State>({ status: null, automation: null, online: false });
  const load = useCallback(async () => {
    try {
      const [statusResponse, automationResponse] = await Promise.all([fetch(`${API}/opportunities/status`), fetch(`${API}/opportunities/automation`)]);
      if (!statusResponse.ok || !automationResponse.ok) throw new Error("Research command telemetry unavailable");
      setState({ status: await statusResponse.json() as OpportunityStatus, automation: await automationResponse.json() as AutomationStatus, online: true });
    } catch { setState((current) => ({ ...current, online: false })); }
  }, []);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 15000); return () => window.clearInterval(timer); }, [load]);

  const queue = state.status?.queue || [];
  const eligible = queue.filter((item) => item.eligible_for_promotion && !item.promoted_case_id);
  const top = useMemo(() => [...queue].sort((a, b) => Number(b.score || 0) - Number(a.score || 0))[0], [queue]);
  const automation = state.automation?.config;

  return (
    <section className="research-command-card">
      <div className="research-command-head"><div><div className="research-command-eyebrow">RESEARCH COMMAND</div><h2>Intelligence Intake & Opportunity Hunt</h2><p>Discovery and evidence acquisition remain research-only. Nothing on this floor can authorize live capital.</p></div><div className={state.online ? "research-command-live" : "research-command-offline"}>{state.online ? "RESEARCH ONLINE" : "RESEARCH OFFLINE"}</div></div>
      <div className="research-command-metrics">
        <div><span>Queue</span><strong>{queue.length}</strong></div>
        <div><span>Promotion Ready</span><strong>{eligible.length}</strong></div>
        <div><span>Scanner</span><strong>{state.automation?.scheduler_running ? "RUNNING" : "IDLE"}</strong></div>
        <div><span>Cadence</span><strong>{automation?.interval_minutes ? `${automation.interval_minutes}m` : "—"}</strong></div>
        <div><span>Live Execution</span><strong className="research-lock">LOCKED</strong></div>
      </div>
      <div className="research-command-next"><span>TOP CURRENT SIGNAL</span><strong>{top?.ticker ? `${top.ticker} · score ${Math.round(Number(top.score || 0))} · ${top.priority || "unranked"}` : "No queued opportunity signal available."}</strong></div>
    </section>
  );
}
