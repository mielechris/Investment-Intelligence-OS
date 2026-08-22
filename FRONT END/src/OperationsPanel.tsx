import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

const API_BASE = "http://localhost:8000";

type QueueCounts = { pending: number; running: number; complete: number; error: number; queued?: number };
type IngestionJob = { name: string; interval_seconds: number; last_status: string; last_error: string | null; last_inserted: number; last_dispatched: number; last_completed_at: string | null; next_run_at: string | null };
type OperationsStatus = {
  paper_mode: boolean;
  providers: Array<{ name: string; kind: string; configured: boolean; live: boolean; detail: string }>;
  specialized_providers: Array<Record<string, unknown>>;
  ingestion: { running: boolean; evidence_count: number; dispatch_queue: QueueCounts; committee_queue?: QueueCounts; risk_queue?: QueueCounts; auto_agent_processing?: Record<string, unknown>; jobs: IngestionJob[] };
  dispatcher: QueueCounts;
  committee_escalations?: QueueCounts;
  risk_reviews?: QueueCounts;
};
type DispatchItem = { dispatch_id: string; agent_id: string; route_reason: string; status: string; created_at: string; evidence: { source_name: string; source_kind: string; title: string; summary: string }; result?: { materiality?: string; headline?: string; confidence?: number; disposition?: string } | null };
type EscalationItem = { escalation_id: string; agent_id: string; status: string; confidence: number; materiality: string; created_at: string; packet?: { agent_result?: { headline?: string; view?: string; disposition?: string } }; committee_result?: { headline?: string; summary?: string; disposition?: string } | null };
type RiskItem = {
  risk_review_id: string;
  status: string;
  created_at: string;
  packet?: { committee_result?: { headline?: string; disposition?: string } };
  risk_result?: {
    decision?: string;
    risk_level?: string;
    headline?: string;
    confidence?: number;
    primary_risks?: string[];
    allowed_notional?: number;
    paper_execution_eligible?: boolean;
  } | null;
};
type DispatchResponse = { counts: QueueCounts; items: DispatchItem[] };
type EscalationResponse = { counts: QueueCounts; items: EscalationItem[] };
type RiskResponse = { counts: QueueCounts; items: RiskItem[] };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

const card: CSSProperties = { background: "#080d13", border: "1px solid #263445", borderRadius: "12px", padding: "18px", minWidth: 0 };
const metric: CSSProperties = { ...card, padding: "15px 16px" };

function shortTime(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function OperationsPanel() {
  const [status, setStatus] = useState<OperationsStatus | null>(null);
  const [dispatch, setDispatch] = useState<DispatchResponse | null>(null);
  const [escalations, setEscalations] = useState<EscalationResponse | null>(null);
  const [risk, setRisk] = useState<RiskResponse | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const [nextStatus, nextDispatch, nextEscalations, nextRisk] = await Promise.all([
          getJson<OperationsStatus>("/intelligence/feeds/status"),
          getJson<DispatchResponse>("/intelligence/feeds/dispatch?limit=10"),
          getJson<EscalationResponse>("/intelligence/feeds/committee-escalations?limit=10"),
          getJson<RiskResponse>("/intelligence/feeds/risk-reviews?limit=10"),
        ]);
        if (cancelled) return;
        setStatus(nextStatus); setDispatch(nextDispatch); setEscalations(nextEscalations); setRisk(nextRisk); setLastRefresh(new Date()); setError(null);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Operations feed unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { cancelled = true; window.clearInterval(timer) };
  }, []);

  const ingestionRunning = status?.ingestion.running ?? false;
  const dispatchCounts = dispatch?.counts ?? status?.dispatcher;
  const committeeCounts = escalations?.counts ?? status?.committee_escalations;
  const riskCounts = risk?.counts ?? status?.risk_reviews ?? status?.ingestion.risk_queue;
  const liveProviders = status?.providers.filter((provider) => provider.live && provider.configured).length ?? 0;

  return (
    <section style={{ border: "1px solid #31506d", background: "radial-gradient(circle at top right, rgba(21,91,117,.2), transparent 35%), #05080c", borderRadius: "16px", padding: "24px", marginBottom: "26px", color: "#eef6ff" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", flexWrap: "wrap" }}>
        <div>
          <div style={{ color: "#62b9df", fontSize: "11px", letterSpacing: "4px" }}>FACTORY OPERATIONS // LIVE</div>
          <h2 style={{ margin: "7px 0 6px", fontSize: "27px" }}>24/7 Intelligence Floor</h2>
          <div style={{ color: "#8292a5", fontSize: "13px" }}>Auto-refreshing every 5 seconds · last update {lastRefresh ? lastRefresh.toLocaleTimeString() : "waiting"}</div>
        </div>
        <div style={{ border: `1px solid ${ingestionRunning ? "#32735d" : "#743747"}`, background: ingestionRunning ? "#0b1a15" : "#1c0c10", color: ingestionRunning ? "#70d2aa" : "#e37b8b", borderRadius: "8px", padding: "10px 14px", fontWeight: 800, letterSpacing: "2px", fontSize: "11px" }}>{ingestionRunning ? "INGESTION RUNNING" : "INGESTION OFFLINE"}</div>
      </div>

      {error && <div style={{ marginTop: "16px", border: "1px solid #6e3040", background: "#190a0f", color: "#e67f91", borderRadius: "8px", padding: "12px" }}>Backend operations feed unavailable: {error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "12px", marginTop: "20px" }}>
        <div style={metric}><div style={{ color: "#718195", fontSize: "10px", letterSpacing: "2px" }}>EVIDENCE ARCHIVE</div><strong style={{ fontSize: "27px" }}>{status?.ingestion.evidence_count ?? 0}</strong></div>
        <div style={metric}><div style={{ color: "#718195", fontSize: "10px", letterSpacing: "2px" }}>LIVE PROVIDERS</div><strong style={{ fontSize: "27px" }}>{liveProviders}</strong></div>
        <div style={metric}><div style={{ color: "#718195", fontSize: "10px", letterSpacing: "2px" }}>AGENT QUEUE</div><strong style={{ fontSize: "27px" }}>{dispatchCounts?.pending ?? 0}</strong></div>
        <div style={metric}><div style={{ color: "#718195", fontSize: "10px", letterSpacing: "2px" }}>AGENTS WORKING</div><strong style={{ fontSize: "27px" }}>{dispatchCounts?.running ?? 0}</strong></div>
        <div style={metric}><div style={{ color: "#718195", fontSize: "10px", letterSpacing: "2px" }}>COMMITTEE INBOX</div><strong style={{ fontSize: "27px" }}>{committeeCounts?.queued ?? committeeCounts?.pending ?? 0}</strong></div>
        <div style={metric}><div style={{ color: "#718195", fontSize: "10px", letterSpacing: "2px" }}>RISK INBOX</div><strong style={{ fontSize: "27px" }}>{riskCounts?.pending ?? 0}</strong></div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(310px, 1fr))", gap: "16px", marginTop: "16px" }}>
        <div style={card}>
          <div style={{ color: "#77bce0", fontSize: "10px", letterSpacing: "3px" }}>INGESTION HEARTBEAT</div><h3 style={{ margin: "8px 0 12px" }}>Feed Workers</h3>
          {(status?.ingestion.jobs ?? []).map((job) => <div key={job.name} style={{ borderTop: "1px solid #1f2c3a", padding: "11px 0", display: "grid", gridTemplateColumns: "1fr auto", gap: "10px" }}><div><strong style={{ fontSize: "13px" }}>{job.name}</strong><div style={{ color: "#708194", fontSize: "11px", marginTop: "3px" }}>last {shortTime(job.last_completed_at)} · next {shortTime(job.next_run_at)} · +{job.last_inserted} evidence / {job.last_dispatched} routes</div>{job.last_error && <div style={{ color: "#dc7888", fontSize: "11px", marginTop: "4px" }}>{job.last_error}</div>}</div><span style={{ color: job.last_status === "ok" ? "#65c79f" : job.last_status === "error" ? "#dc7888" : "#c9a657", fontSize: "11px", fontWeight: 800 }}>{job.last_status.toUpperCase()}</span></div>)}
        </div>
        <div style={card}>
          <div style={{ color: "#b78bfa", fontSize: "10px", letterSpacing: "3px" }}>AGENT DISPATCH</div><h3 style={{ margin: "8px 0 12px" }}>Recent Work</h3>
          {(dispatch?.items ?? []).length === 0 ? <div style={{ color: "#6e7d90", fontSize: "13px" }}>No routed work yet.</div> : (dispatch?.items ?? []).slice(0, 7).map((item) => <div key={item.dispatch_id} style={{ borderTop: "1px solid #252b3b", padding: "10px 0" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "10px" }}><strong style={{ fontSize: "12px" }}>{item.evidence.title}</strong><span style={{ color: item.status === "complete" ? "#66caa3" : item.status === "error" ? "#df798b" : "#c9a657", fontSize: "10px", fontWeight: 800 }}>{item.status.toUpperCase()}</span></div><div style={{ color: "#78869a", fontSize: "11px", marginTop: "4px" }}>{item.route_reason}</div>{item.result?.headline && <div style={{ color: "#aeb8c6", fontSize: "11px", marginTop: "5px" }}>{item.result.materiality ?? "—"} · {item.result.headline}</div>}</div>)}
        </div>
      </div>

      <div style={{ ...card, marginTop: "16px", border: "1px solid #5a4427", background: "#100d08" }}>
        <div style={{ color: "#d8ad59", fontSize: "10px", letterSpacing: "3px" }}>COMMITTEE ESCALATION INBOX</div><h3 style={{ margin: "8px 0 12px" }}>High-Materiality Work Sent Upstairs</h3>
        {(escalations?.items ?? []).length === 0 ? <div style={{ color: "#817565", fontSize: "13px" }}>No high-confidence escalations yet.</div> : (escalations?.items ?? []).slice(0, 6).map((item) => { const specialist = item.packet?.agent_result; const title = item.committee_result?.headline ?? specialist?.headline ?? item.agent_id; return <div key={item.escalation_id} style={{ borderTop: "1px solid #332a1c", padding: "11px 0", display: "grid", gridTemplateColumns: "1fr auto", gap: "12px" }}><div><strong style={{ fontSize: "13px" }}>{title}</strong><div style={{ color: "#8e806c", fontSize: "11px", marginTop: "4px" }}>{item.materiality} materiality · confidence {Math.round((item.confidence ?? 0) * 100)}%</div></div><span style={{ color: item.status === "complete" ? "#72caa7" : item.status === "error" ? "#df798b" : "#d8ad59", fontSize: "10px", fontWeight: 800 }}>{item.status.toUpperCase()}</span></div> })}
      </div>

      <div style={{ ...card, marginTop: "16px", border: "1px solid #6a303b", background: "#10080a" }}>
        <div style={{ color: "#e07b8e", fontSize: "10px", letterSpacing: "3px" }}>RISK INBOX // RISK INSPECTION DESK</div><h3 style={{ margin: "8px 0 12px" }}>Committee Work Under Risk Review</h3>
        {(risk?.items ?? []).length === 0 ? <div style={{ color: "#887077", fontSize: "13px" }}>No risk packets yet.</div> : (risk?.items ?? []).slice(0, 6).map((item) => {
          const result = item.risk_result;
          const title = result?.headline ?? item.packet?.committee_result?.headline ?? "Risk review";
          const decision = result?.decision ?? item.status.toUpperCase();
          const primaryRisks = result?.primary_risks?.slice(0, 3) ?? [];
          return <div key={item.risk_review_id} style={{ borderTop: "1px solid #3a2026", padding: "13px 0", display: "grid", gridTemplateColumns: "1fr auto", gap: "12px" }}>
            <div style={{ minWidth: 0 }}>
              <strong style={{ fontSize: "13px" }}>{title}</strong>
              <div style={{ color: "#98747c", fontSize: "11px", marginTop: "4px" }}>
                {result?.risk_level ?? "PENDING"} risk · allowed notional ${Math.round(result?.allowed_notional ?? 0).toLocaleString()} · {result?.paper_execution_eligible ? "paper eligible" : "execution blocked"}
              </div>
              {primaryRisks.length > 0 && <ul style={{ margin: "8px 0 0", paddingLeft: "18px", color: "#b39aa0", fontSize: "11px", lineHeight: 1.45 }}>
                {primaryRisks.map((riskItem, index) => <li key={`${item.risk_review_id}-${index}`}>{riskItem}</li>)}
              </ul>}
            </div>
            <span style={{ color: decision === "WATCH_ONLY" ? "#d8ad59" : decision === "VETOED" ? "#e07b8e" : "#a98b91", fontSize: "10px", fontWeight: 800 }}>{decision}</span>
          </div>
        })}
      </div>
    </section>
  );
}

export default OperationsPanel;
