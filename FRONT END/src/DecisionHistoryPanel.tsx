import { useEffect, useMemo, useState } from "react";

const API = "http://127.0.0.1:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type AgentChange = {
  agent_key: string;
  agent: string;
  from_disposition?: string;
  to_disposition?: string;
  from_confidence?: number;
  to_confidence?: number;
  confidence_delta?: number;
  headline?: string;
};

type HistoryRound = {
  round_number: number;
  round_type: string;
  created_at?: string;
  evidence_count: number;
  evidence_quality: number;
  critical_flags: string[];
  committee: {
    headline?: string;
    summary?: string;
    disposition?: string;
    confidence?: number;
    dissent?: string;
    bull_case?: string;
    bear_case?: string;
    required_evidence: string[];
  };
  risk: {
    decision?: string;
    triggered_rules: string[];
    allowed_notional?: number;
  };
  execution: {
    execution?: string;
    reason?: string;
  };
  agent_changes: AgentChange[];
};

type CaseHistory = {
  case_id: string;
  topic: string;
  rounds: HistoryRound[];
  round_count: number;
  signal_ladder: {
    current_stage: string;
    stages: string[];
    qualified_buy_candidate_enabled: boolean;
    paper_buy_enabled: boolean;
    next_requirements: string[];
  };
};

function pct(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function stageLabel(stage: string): string {
  return stage.replaceAll("_", " ");
}

function DecisionHistoryPanel() {
  const [caseId, setCaseId] = useState<string | null>(() =>
    window.localStorage.getItem(ACTIVE_CASE_KEY)
  );
  const [history, setHistory] = useState<CaseHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = window.localStorage.getItem(ACTIVE_CASE_KEY);
      setCaseId((current) => (current === next ? current : next));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!caseId) {
      setHistory(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch(`${API}/history/${caseId}`);
        if (!response.ok) throw new Error(`History request failed: ${response.status}`);
        const data = (await response.json()) as CaseHistory;
        if (!cancelled) {
          setHistory(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "History unavailable");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [caseId]);

  const currentStageIndex = useMemo(() => {
    if (!history) return -1;
    return history.signal_ladder.stages.indexOf(history.signal_ladder.current_stage);
  }, [history]);

  const panel = {
    background: "rgba(7, 11, 17, 0.96)",
    border: "1px solid #28313d",
    borderRadius: "14px",
    padding: "22px",
  } as const;
  const label = {
    color: "#758294",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  if (!caseId) return null;

  return (
    <section
      style={{
        margin: "0 28px 28px",
        color: "#f2f5f8",
        fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
      }}
    >
      <div style={{ ...panel, borderColor: "#4b3d68" }}>
        <div style={label}>DECISION MEMORY · SAME CASE</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "20px", alignItems: "start", flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: "7px 0 4px" }}>Re-underwrite history</h2>
            <div style={{ color: "#8996a6", fontSize: "13px" }}>
              {history?.topic ?? "Loading selected case history..."}
            </div>
          </div>
          <div style={{ color: "#768396", fontSize: "12px" }}>
            {history ? `${history.round_count} committee rounds persisted` : "Loading ledger..."}
          </div>
        </div>

        {error && <div style={{ marginTop: "14px", color: "#ff8a9b" }}>{error}</div>}

        {history && (
          <>
            <div style={{ marginTop: "20px", ...panel, padding: "16px", background: "#080c12" }}>
              <div style={label}>SIGNAL LADDER</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(150px, 1fr))", gap: "8px", marginTop: "12px" }}>
                {history.signal_ladder.stages.map((stage, index) => {
                  const reached = index <= currentStageIndex;
                  const current = stage === history.signal_ladder.current_stage;
                  const futureDisabled = stage === "QUALIFIED_BUY_CANDIDATE" || stage === "PAPER_BUY";
                  return (
                    <div
                      key={stage}
                      style={{
                        border: `1px solid ${current ? "#7d69b5" : reached ? "#345f4a" : "#29323e"}`,
                        background: current ? "#211936" : reached ? "#0d1b16" : "#090d12",
                        borderRadius: "9px",
                        padding: "12px",
                      }}
                    >
                      <div style={{ fontWeight: 800, fontSize: "12px" }}>{stageLabel(stage)}</div>
                      <div style={{ marginTop: "5px", color: current ? "#d9ccff" : "#778496", fontSize: "10px", letterSpacing: "1px" }}>
                        {current ? "CURRENT" : futureDisabled ? "FUTURE GATE" : reached ? "REACHED" : "PENDING"}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div style={{ marginTop: "12px", color: "#9aa6b5", fontSize: "12px", lineHeight: 1.5 }}>
                {history.signal_ladder.next_requirements.length
                  ? history.signal_ladder.next_requirements.join(" · ")
                  : "No additional research-gate requirements recorded."}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(270px, 1fr))", gap: "12px", marginTop: "16px" }}>
              {history.rounds.map((round) => (
                <article key={round.round_number} style={{ ...panel, padding: "16px", background: "#080c11" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "10px" }}>
                    <div>
                      <div style={label}>ROUND {round.round_number} · {round.round_type}</div>
                      <div style={{ marginTop: "8px", fontSize: "19px", fontWeight: 900 }}>
                        {round.committee.disposition ?? "—"} · {pct(round.committee.confidence)}
                      </div>
                    </div>
                    <div style={{ textAlign: "right", color: "#7c8999", fontSize: "11px" }}>
                      {round.created_at ? new Date(round.created_at).toLocaleString() : "—"}
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px", marginTop: "14px", fontSize: "12px" }}>
                    <div><span style={label}>Evidence</span><div style={{ marginTop: "4px" }}>{pct(round.evidence_quality)} · {round.evidence_count} items</div></div>
                    <div><span style={label}>Risk</span><div style={{ marginTop: "4px" }}>{round.risk.decision ?? "—"}</div></div>
                    <div><span style={label}>Execution</span><div style={{ marginTop: "4px" }}>{round.execution.execution ?? "—"}</div></div>
                    <div><span style={label}>Desk shifts</span><div style={{ marginTop: "4px" }}>{round.agent_changes.length}</div></div>
                  </div>

                  {round.risk.triggered_rules.length > 0 && (
                    <div style={{ marginTop: "12px", color: "#d7b76a", fontSize: "11px", lineHeight: 1.45 }}>
                      Risk: {round.risk.triggered_rules.join(" · ")}
                    </div>
                  )}

                  {round.agent_changes.length > 0 && (
                    <div style={{ marginTop: "13px" }}>
                      <div style={label}>WHO CHANGED</div>
                      {round.agent_changes.slice(0, 5).map((change) => (
                        <div key={change.agent_key} style={{ marginTop: "7px", borderTop: "1px solid #1e2731", paddingTop: "7px", fontSize: "11px" }}>
                          <strong>{change.agent}</strong>: {change.from_disposition} → {change.to_disposition} · {pct(change.from_confidence)} → {pct(change.to_confidence)}
                        </div>
                      ))}
                    </div>
                  )}

                  <details style={{ marginTop: "14px", color: "#aab5c1", fontSize: "12px" }}>
                    <summary style={{ cursor: "pointer", color: "#91a0b1", fontWeight: 700 }}>Committee reasoning</summary>
                    <div style={{ marginTop: "10px", lineHeight: 1.5 }}><strong>Headline:</strong> {round.committee.headline || "—"}</div>
                    <div style={{ marginTop: "8px", lineHeight: 1.5 }}><strong>Bull:</strong> {round.committee.bull_case || "—"}</div>
                    <div style={{ marginTop: "8px", lineHeight: 1.5 }}><strong>Bear:</strong> {round.committee.bear_case || "—"}</div>
                    <div style={{ marginTop: "8px", lineHeight: 1.5 }}><strong>Dissent:</strong> {round.committee.dissent || "—"}</div>
                    {round.committee.required_evidence.length > 0 && (
                      <div style={{ marginTop: "8px", lineHeight: 1.5 }}><strong>Still needed:</strong> {round.committee.required_evidence.join(" · ")}</div>
                    )}
                  </details>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

export default DecisionHistoryPanel;
