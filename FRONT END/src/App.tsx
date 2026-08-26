import { useEffect, useMemo, useState } from "react";
import OpportunityFloor from "./OpportunityFloor";
import FactoryRoom from "./FactoryRoom";
import PaperCapitalControlPanel from "./PaperCapitalControlPanel";

const API = "http://localhost:8002";
const ACTIVE_CASE_KEY = "iios.activeCaseId";

type SystemStatus = {
  version: string;
  paper_mode: boolean;
  automatic_monitoring: boolean;
  semiconductor_memory_intelligence?: boolean;
};

type Agent = {
  key: string;
  name: string;
  room: string;
  status: string;
};

type DashboardCase = {
  case_id: string;
  topic: string;
  created_at?: string;
  health: string;
  committee_disposition?: string;
  committee_confidence?: number;
  evidence_quality?: number;
  latest_evidence_count?: number;
  monitoring_enabled: boolean;
  interval_minutes?: number;
  ticker?: string;
  last_refresh_at?: string;
  latest_return_pct?: number;
  thesis_flags: string[];
  latest_action?: string;
  outcome?: string;
};

type Scorecard = {
  agent_key: string;
  agent?: string;
  observations: number;
  accuracy?: number | null;
  average_confidence: number;
  average_calibration_score: number;
};

type FactoryBootstrap = {
  ingestion: {
    successful_sources: number;
    failed_sources: number;
  };
  quote: {
    current_price?: number | null;
    status?: string;
  };
  factory: {
    case: {
      case_id: string;
      topic: string;
      evidence_summary?: {
        average_quality_score?: number;
      };
    };
    committee: {
      headline: string;
      summary: string;
      confidence: number;
      disposition: string;
      bull_case?: string;
      bear_case?: string;
    };
    risk: {
      decision: string;
      triggered_rules: string[];
    };
    execution: {
      status: string;
      execution: string;
      reason?: string;
    };
  };
  monitor_profile?: {
    interval_minutes: number;
    enabled: boolean;
  } | null;
};

type MemoryReunderwriteResult = {
  case_id: string;
  evidence_summary: {
    evidence_count?: number;
    average_quality_score?: number;
  };
  committee: {
    headline: string;
    summary: string;
    confidence: number;
    disposition: string;
  };
  risk: {
    decision: string;
  };
  execution: {
    execution: string;
  };
  quote?: {
    current_price?: number | null;
    status?: string;
  };
};

async function apiJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function pct(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function returnPct(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function healthTone(health: string): string {
  if (health === "THESIS_BROKEN") return "#ff6379";
  if (health === "REUNDERWRITE_REQUIRED") return "#e6bd5c";
  if (health === "INTACT") return "#59c68c";
  if (health === "CLOSED") return "#8b96a5";
  if (health === "AUTO_WATCH") return "#78b9eb";
  return "#7e8998";
}

function App() {
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [cases, setCases] = useState<DashboardCase[]>([]);
  const [scorecards, setScorecards] = useState<Scorecard[]>([]);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Ready for governed paper research.");
  const [topic, setTopic] = useState(
    "AI infrastructure demand may support semiconductor memory pricing"
  );
  const [ticker, setTicker] = useState("MU.US");
  const [direction, setDirection] = useState("LONG");
  const [referencePrice, setReferencePrice] = useState("");
  const [intervalMinutes, setIntervalMinutes] = useState("240");
  const [activeCaseId, setActiveCaseId] = useState<string | null>(() =>
    window.localStorage.getItem(ACTIVE_CASE_KEY)
  );
  const [factoryResult, setFactoryResult] = useState<FactoryBootstrap | null>(null);
  const [memoryResult, setMemoryResult] = useState<MemoryReunderwriteResult | null>(null);

  const activeCase = useMemo(
    () => cases.find((item) => item.case_id === activeCaseId) ?? null,
    [cases, activeCaseId]
  );

  const selectCase = (caseId: string) => {
    setActiveCaseId(caseId);
    window.localStorage.setItem(ACTIVE_CASE_KEY, caseId);
  };

  const loadDashboard = async () => {
    try {
      const [statusData, agentData, dashboardData, scorecardData] = await Promise.all([
        apiJson<SystemStatus>("/system/status"),
        apiJson<{ agents: Agent[] }>("/agents"),
        apiJson<{ cases: DashboardCase[] }>("/monitoring/dashboard"),
        apiJson<{ scorecards: Scorecard[] }>("/judgment-bank/scorecards/all"),
      ]);
      setSystem(statusData);
      setAgents(agentData.agents);
      setCases(dashboardData.cases);
      setScorecards(scorecardData.scorecards);
      setActiveCaseId((current) => {
        const remembered = current ?? window.localStorage.getItem(ACTIVE_CASE_KEY);
        const rememberedStillExists =
          remembered !== null && dashboardData.cases.some((item) => item.case_id === remembered);
        const nextCaseId = rememberedStillExists
          ? remembered
          : dashboardData.cases[0]?.case_id ?? null;
        if (nextCaseId) {
          window.localStorage.setItem(ACTIVE_CASE_KEY, nextCaseId);
        } else {
          window.localStorage.removeItem(ACTIVE_CASE_KEY);
        }
        return nextCaseId;
      });
      setConnected(true);
    } catch {
      setConnected(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
    const timer = window.setInterval(() => {
      void loadDashboard();
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const runGovernedCase = async () => {
    setBusy(true);
    setNotice("Evidence is being collected and the eight desks are working...");
    try {
      const numericReference = referencePrice.trim()
        ? Number(referencePrice)
        : undefined;
      const result = await apiJson<FactoryBootstrap>("/factory/run-public", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          ticker,
          direction,
          reference_price: numericReference,
          interval_minutes: Number(intervalMinutes),
          auto_watch: true,
          analysis_mode: "llm",
        }),
      });
      setFactoryResult(result);
      setMemoryResult(null);
      selectCase(result.factory.case.case_id);
      setNotice(
        `Case ${result.factory.case.case_id.slice(-8)} entered AUTO WATCH. ${result.ingestion.successful_sources} public sources responded.`
      );
      await loadDashboard();
    } catch (error) {
      setNotice(error instanceof Error ? `Factory error: ${error.message}` : "Factory request failed.");
    } finally {
      setBusy(false);
    }
  };

  const refreshActiveCase = async () => {
    if (!activeCaseId) return;
    setBusy(true);
    setNotice("Refreshing evidence and re-checking the stored thesis...");
    try {
      await apiJson(`/monitoring/refresh/${activeCaseId}`, { method: "POST" });
      setNotice("Automatic-monitoring refresh completed and was written to the ledger.");
      await loadDashboard();
    } catch (error) {
      setNotice(error instanceof Error ? `Monitoring error: ${error.message}` : "Monitoring refresh failed.");
    } finally {
      setBusy(false);
    }
  };

  const runMemoryReunderwrite = async () => {
    if (!activeCaseId) return;
    setBusy(true);
    setNotice("Loading Micron filings, memory-market signals, hyperscaler capex, rates, and MU market data; then rerunning all eight desks...");
    try {
      const result = await apiJson<MemoryReunderwriteResult>(
        `/intelligence/semiconductor-memory/${activeCaseId}/reunderwrite`,
        { method: "POST" }
      );
      setMemoryResult(result);
      setNotice(
        `Memory re-underwrite complete: ${result.evidence_summary.evidence_count ?? 0} items at ${pct(result.evidence_summary.average_quality_score)} quality. Committee ${result.committee.disposition} ${pct(result.committee.confidence)}; Risk ${result.risk.decision}; Execution ${result.execution.execution}.`
      );
      await loadDashboard();
    } catch (error) {
      setNotice(error instanceof Error ? `Memory intelligence error: ${error.message}` : "Memory re-underwrite failed.");
    } finally {
      setBusy(false);
    }
  };

  const panel = {
    background: "rgba(7, 11, 17, 0.92)",
    border: "1px solid #28313d",
    borderRadius: "14px",
    padding: "22px",
  } as const;

  const input = {
    width: "100%",
    boxSizing: "border-box" as const,
    background: "#0d131b",
    border: "1px solid #303b49",
    color: "#f4f4f4",
    borderRadius: "7px",
    padding: "12px 13px",
    fontSize: "14px",
  };

  const smallLabel = {
    color: "#758294",
    fontSize: "10px",
    letterSpacing: "2px",
    textTransform: "uppercase" as const,
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        background:
          "radial-gradient(circle at 20% -10%, #20304a 0%, #0a0d13 35%, #040506 75%)",
        color: "#f2f5f8",
        fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        padding: "28px",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "24px",
          alignItems: "center",
          borderBottom: "1px solid #27313d",
          paddingBottom: "20px",
          marginBottom: "24px",
        }}
      >
        <div>
          <div style={{ ...smallLabel, letterSpacing: "4px" }}>INVESTMENT INTELLIGENCE OS</div>
          <h1 style={{ margin: "7px 0 3px", fontSize: "34px", letterSpacing: "-1px" }}>
            THE INTELLIGENCE FACTORY
          </h1>
          <div style={{ color: "#788596", fontSize: "13px" }}>
            Evidence → 8 desks → Committee → Risk → Monitor → Judgment Bank
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ color: connected ? "#59c68c" : "#ff6379", fontSize: "11px", letterSpacing: "2px" }}>
            {connected ? "SYSTEM ONLINE" : "SYSTEM OFFLINE"}
          </div>
          <div style={{ marginTop: "7px", color: "#9aa6b5", fontSize: "12px" }}>
            v{system?.version ?? "—"} · AUTO MONITOR {system?.automatic_monitoring ? "ARMED" : "—"}
          </div>
          <div
            style={{
              display: "inline-block",
              marginTop: "9px",
              border: "1px solid #8b1e2d",
              background: "#26080d",
              color: "#ff6379",
              padding: "8px 13px",
              borderRadius: "6px",
              fontWeight: 800,
              letterSpacing: "2px",
              fontSize: "11px",
            }}
          >
            PAPER / SHADOW MODE
          </div>
        </div>
      </header>

      <section style={{ ...panel, marginBottom: "22px", borderColor: "#365575" }}>
        <div style={smallLabel}>CASE LAUNCH BAY</div>
        <h2 style={{ margin: "7px 0 15px" }}>Run governed case + auto-watch</h2>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 3fr) 1fr 1fr 1fr 1fr", gap: "10px" }}>
          <input style={input} value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Investment thesis" />
          <input style={input} value={ticker} onChange={(event) => setTicker(event.target.value)} placeholder="Ticker e.g. MU.US" />
          <select style={input} value={direction} onChange={(event) => setDirection(event.target.value)}>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
            <option value="UNSPECIFIED">WATCH ONLY</option>
          </select>
          <input style={input} value={referencePrice} onChange={(event) => setReferencePrice(event.target.value)} placeholder="Ref price optional" inputMode="decimal" />
          <select style={input} value={intervalMinutes} onChange={(event) => setIntervalMinutes(event.target.value)}>
            <option value="60">Every 1h</option>
            <option value="240">Every 4h</option>
            <option value="720">Every 12h</option>
            <option value="1440">Daily</option>
          </select>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center", marginTop: "14px", flexWrap: "wrap" }}>
          <button
            onClick={() => void runGovernedCase()}
            disabled={busy || topic.trim().length < 2}
            style={{
              border: "1px solid #4d7fa9",
              background: busy ? "#202833" : "#173552",
              color: "#d8ecff",
              borderRadius: "7px",
              padding: "12px 18px",
              fontWeight: 800,
              cursor: busy ? "default" : "pointer",
            }}
          >
            {busy ? "FACTORY WORKING..." : "RUN FACTORY + AUTO WATCH"}
          </button>
          <button
            onClick={() => void refreshActiveCase()}
            disabled={busy || !activeCaseId}
            style={{
              border: "1px solid #3a4654",
              background: "#10161e",
              color: activeCaseId ? "#cbd5df" : "#596574",
              borderRadius: "7px",
              padding: "12px 16px",
              fontWeight: 700,
              cursor: busy || !activeCaseId ? "default" : "pointer",
            }}
          >
            REFRESH ACTIVE CASE NOW
          </button>
          <button
            onClick={() => void runMemoryReunderwrite()}
            disabled={busy || !activeCaseId || system?.semiconductor_memory_intelligence !== true}
            style={{
              border: "1px solid #765fa8",
              background: "#211936",
              color: activeCaseId ? "#e6dcff" : "#625a70",
              borderRadius: "7px",
              padding: "12px 16px",
              fontWeight: 800,
              cursor: busy || !activeCaseId ? "default" : "pointer",
            }}
          >
            MEMORY INTEL + 8-DESK REUNDERWRITE
          </button>
          <span style={{ color: "#8d9aaa", fontSize: "13px" }}>{notice}</span>
        </div>
      </section>

      <FactoryRoom />

      <OpportunityFloor />

      <section style={{ marginBottom: "22px" }}>
        <div style={{ ...smallLabel, marginBottom: "10px" }}>SPECIALIST FLOOR · 8 DESKS</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(190px, 1fr))", gap: "12px" }}>
          {agents.map((agent) => (
            <article key={agent.key} style={{ ...panel, padding: "17px" }}>
              <div style={smallLabel}>{agent.room}</div>
              <div style={{ marginTop: "8px", fontWeight: 800, fontSize: "15px" }}>{agent.name}</div>
              <div style={{ marginTop: "10px", color: "#59c68c", fontSize: "10px", letterSpacing: "2px" }}>READY</div>
            </article>
          ))}
        </div>
      </section>

      <section style={{ ...panel, marginBottom: "22px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", gap: "15px" }}>
          <div>
            <div style={smallLabel}>SURVEILLANCE FLOOR</div>
            <h2 style={{ margin: "7px 0 0" }}>Case health board</h2>
          </div>
          <div style={{ color: "#6f7d8e", fontSize: "12px" }}>UI refreshes every 15 seconds</div>
        </div>
        <div style={{ overflowX: "auto", marginTop: "16px" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "980px" }}>
            <thead>
              <tr style={{ color: "#778496", fontSize: "10px", letterSpacing: "1.5px", textAlign: "left" }}>
                <th style={{ padding: "10px" }}>CASE</th>
                <th style={{ padding: "10px" }}>THESIS</th>
                <th style={{ padding: "10px" }}>HEALTH</th>
                <th style={{ padding: "10px" }}>COMMITTEE</th>
                <th style={{ padding: "10px" }}>EVIDENCE</th>
                <th style={{ padding: "10px" }}>RETURN</th>
                <th style={{ padding: "10px" }}>WATCH</th>
                <th style={{ padding: "10px" }}>LAST REFRESH</th>
              </tr>
            </thead>
            <tbody>
              {cases.length === 0 && (
                <tr><td colSpan={8} style={{ padding: "18px 10px", color: "#697688" }}>No persisted cases yet.</td></tr>
              )}
              {cases.map((item) => (
                <tr
                  key={item.case_id}
                  onClick={() => selectCase(item.case_id)}
                  style={{ borderTop: "1px solid #1e2731", cursor: "pointer", background: item.case_id === activeCaseId ? "rgba(55, 91, 126, 0.16)" : "transparent" }}
                >
                  <td style={{ padding: "12px 10px", fontFamily: "monospace", color: "#9fb0c2" }}>{item.case_id.slice(-8)}</td>
                  <td style={{ padding: "12px 10px", maxWidth: "330px" }}>{item.topic}</td>
                  <td style={{ padding: "12px 10px", color: healthTone(item.health), fontWeight: 800 }}>{item.health.replaceAll("_", " ")}</td>
                  <td style={{ padding: "12px 10px" }}>{item.committee_disposition ?? "—"} · {pct(item.committee_confidence)}</td>
                  <td style={{ padding: "12px 10px" }}>
                    {pct(item.evidence_quality)}{item.latest_evidence_count !== undefined ? ` · ${item.latest_evidence_count} items` : ""}
                  </td>
                  <td style={{ padding: "12px 10px" }}>{returnPct(item.latest_return_pct)}</td>
                  <td style={{ padding: "12px 10px", color: item.monitoring_enabled ? "#59c68c" : "#7e8998" }}>
                    {item.monitoring_enabled ? `${item.interval_minutes ?? "—"}m` : "OFF"}
                  </td>
                  <td style={{ padding: "12px 10px", color: "#8996a6" }}>
                    {item.last_refresh_at ? new Date(item.last_refresh_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: "20px", marginBottom: "22px" }}>
        <section style={panel}>
          <div style={smallLabel}>ACTIVE CASE</div>
          <h2 style={{ margin: "7px 0 14px" }}>{activeCase ? activeCase.topic : "Select a case from surveillance"}</h2>
          {activeCase ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "10px" }}>
              <div><span style={smallLabel}>Health</span><div style={{ marginTop: "5px", color: healthTone(activeCase.health), fontWeight: 800 }}>{activeCase.health}</div></div>
              <div><span style={smallLabel}>Ticker</span><div style={{ marginTop: "5px" }}>{activeCase.ticker || "—"}</div></div>
              <div><span style={smallLabel}>Thesis flags</span><div style={{ marginTop: "5px" }}>{activeCase.thesis_flags.length ? activeCase.thesis_flags.join(", ") : "None"}</div></div>
              <div><span style={smallLabel}>Latest action</span><div style={{ marginTop: "5px" }}>{activeCase.latest_action || "WATCH"}</div></div>
            </div>
          ) : (
            <div style={{ color: "#748091" }}>The factory will attach monitoring metadata here after a governed case is created.</div>
          )}
        </section>

        <section style={panel}>
          <div style={smallLabel}>LAST FACTORY PASS</div>
          {memoryResult ? (
            <>
              <h2 style={{ margin: "7px 0 8px" }}>{memoryResult.committee.headline}</h2>
              <p style={{ color: "#aab5c1", lineHeight: 1.5 }}>{memoryResult.committee.summary}</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px", marginTop: "12px" }}>
                <div><span style={smallLabel}>Committee</span><div>{memoryResult.committee.disposition} · {pct(memoryResult.committee.confidence)}</div></div>
                <div><span style={smallLabel}>Risk</span><div>{memoryResult.risk.decision}</div></div>
                <div><span style={smallLabel}>Execution</span><div>{memoryResult.execution.execution}</div></div>
                <div><span style={smallLabel}>Evidence</span><div>{pct(memoryResult.evidence_summary.average_quality_score)} · {memoryResult.evidence_summary.evidence_count ?? 0} items</div></div>
              </div>
            </>
          ) : factoryResult ? (
            <>
              <h2 style={{ margin: "7px 0 8px" }}>{factoryResult.factory.committee.headline}</h2>
              <p style={{ color: "#aab5c1", lineHeight: 1.5 }}>{factoryResult.factory.committee.summary}</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px", marginTop: "12px" }}>
                <div><span style={smallLabel}>Committee</span><div>{factoryResult.factory.committee.disposition} · {pct(factoryResult.factory.committee.confidence)}</div></div>
                <div><span style={smallLabel}>Risk</span><div>{factoryResult.factory.risk.decision}</div></div>
                <div><span style={smallLabel}>Execution</span><div>{factoryResult.factory.execution.execution}</div></div>
                <div><span style={smallLabel}>Quote</span><div>{factoryResult.quote.current_price ?? "—"}</div></div>
              </div>
            </>
          ) : (
            <div style={{ color: "#748091", marginTop: "10px" }}>No factory pass in this browser session.</div>
          )}
        </section>
      </div>

      <PaperCapitalControlPanel
        caseId={activeCaseId}
      />

      <section style={panel}>
        <div style={smallLabel}>JUDGMENT BANK</div>
        <h2 style={{ margin: "7px 0 15px" }}>Agent calibration board</h2>
        {scorecards.length === 0 ? (
          <div style={{ color: "#748091" }}>Scorecards appear after post-mortems create Judgment Bank outcomes.</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(190px, 1fr))", gap: "12px" }}>
            {scorecards.map((card) => (
              <article key={card.agent_key} style={{ border: "1px solid #26313d", borderRadius: "10px", padding: "14px", background: "#080c11" }}>
                <div style={{ fontWeight: 800 }}>{card.agent || card.agent_key}</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "12px", fontSize: "12px" }}>
                  <div><span style={smallLabel}>Calibration</span><div>{pct(card.average_calibration_score)}</div></div>
                  <div><span style={smallLabel}>Accuracy</span><div>{pct(card.accuracy)}</div></div>
                  <div><span style={smallLabel}>Confidence</span><div>{pct(card.average_confidence)}</div></div>
                  <div><span style={smallLabel}>Outcomes</span><div>{card.observations}</div></div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default App;
